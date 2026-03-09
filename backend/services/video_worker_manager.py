"""
Dynamic Video Worker Manager
Manages per-camera video processing threads that can be started/stopped on demand
"""
import threading
import time
import cv2
import numpy as np
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from ultralytics import YOLO

from config import settings
from utils.logger import logger
from database import db
from services.nx_witness import nx_client
from services.alert_manager import alert_manager
from integrations.evlos_client import evlos_client


class CameraWorker:
    """Worker thread for a single camera"""

    def __init__(self, camera_id: str, camera_name: str, model, config: dict, model_lock=None):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.model = model
        self.config = config
        self.model_lock = model_lock  # Lock for thread-safe CUDA inference
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.last_alert_time = 0
        self.running = False

        # Load detection configuration from database
        self.detection_config = db.get_camera_detection_config(camera_id)
        if not self.detection_config:
            # Default to intrusion mode with preset 1
            db.set_camera_detection_mode(camera_id, 'intrusion', 1)
            self.detection_config = db.get_camera_detection_config(camera_id)

        global_confidence = self.config.get('confidence', 0.5)
        logger.info(f"[{camera_name}] Detection mode: {self.detection_config.get('detection_mode', 'intrusion')}, Global confidence: {global_confidence}")

    def start(self):
        """Start the worker thread"""
        if self.running:
            logger.warning(f"[{self.camera_name}] Worker already running")
            return False

        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"Worker-{self.camera_name}"
        )
        self.thread.start()
        self.running = True
        logger.info(f"[{self.camera_name}] Worker started")
        return True

    def stop(self):
        """Stop the worker thread"""
        if not self.running:
            return False

        logger.info(f"[{self.camera_name}] Stopping worker...")
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.running = False

        # Update database status
        db.upsert_camera_status(
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            stream_connected=False
        )
        logger.info(f"[{self.camera_name}] Worker stopped")
        return True

    def _run(self):
        """Main worker loop"""
        logger.info(f"[{self.camera_name}] Worker thread started")

        while not self.stop_event.is_set():
            try:
                # Get stream quality from config
                stream_quality = self.config.get("streamQuality", "medium")
                stream_url = nx_client.get_stream_url(self.camera_id, quality=stream_quality)
                self._process_stream(stream_url)
            except Exception as e:
                import traceback
                logger.error(f"[{self.camera_name}] Error in worker: {e}\n{traceback.format_exc()}")
                db.upsert_camera_status(
                    camera_id=self.camera_id,
                    camera_name=self.camera_name,
                    stream_connected=False
                )
                # Wait before retry, but check stop_event frequently
                for _ in range(50):  # 5 seconds with 100ms checks
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.1)

    def _process_stream(self, stream_url: str):
        """Process camera stream"""
        logger.info(f"[{self.camera_name}] Connecting to stream...")

        try:
            # Connect to stream
            response = requests.get(
                stream_url,
                auth=nx_client.auth,
                stream=True,
                timeout=10,
                verify=False
            )

            if response.status_code != 200:
                logger.error(f"[{self.camera_name}] Failed to connect: HTTP {response.status_code}")
                db.upsert_camera_status(self.camera_id, self.camera_name, stream_connected=False)
                return

            logger.info(f"[{self.camera_name}] Connected to stream")
            db.upsert_camera_status(self.camera_id, self.camera_name, stream_connected=True)

            # Process frames
            bytes_data = bytes()
            frame_count = 0
            fps_start = time.time()
            fps_frames = 0
            frame_sampling = self.config.get("frameSampling", 10)
            max_buffer_size = 5 * 1024 * 1024  # 5MB max buffer to prevent memory issues

            for chunk in response.iter_content(chunk_size=4096):
                if self.stop_event.is_set():
                    logger.info(f"[{self.camera_name}] Stop requested, exiting stream")
                    return

                bytes_data += chunk

                # Prevent memory accumulation by limiting buffer size
                if len(bytes_data) > max_buffer_size:
                    # Find last complete JPEG and discard everything before it
                    last_start = bytes_data.rfind(b'\xff\xd8')
                    if last_start > 0:
                        bytes_data = bytes_data[last_start:]

                # Parse MJPEG
                a = bytes_data.find(b'\xff\xd8')
                b = bytes_data.find(b'\xff\xd9')

                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]

                    try:
                        # Decode frame
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

                        if frame is not None:
                            frame_count += 1
                            fps_frames += 1

                            # Update FPS every 5 seconds
                            if time.time() - fps_start >= 5.0:
                                fps = fps_frames / (time.time() - fps_start)
                                db.upsert_camera_status(self.camera_id, self.camera_name,
                                                       stream_connected=True, fps=fps)
                                fps_frames = 0
                                fps_start = time.time()

                            # Frame sampling
                            if frame_count % frame_sampling == 0:
                                self._process_frame(frame)
                    except cv2.error as e:
                        # Skip frame on OpenCV decode error to prevent crash
                        logger.warning(f"[{self.camera_name}] Frame decode error, skipping: {e}")
                        continue

        except Exception as e:
            logger.error(f"[{self.camera_name}] Stream error: {e}")
            db.upsert_camera_status(self.camera_id, self.camera_name, stream_connected=False)

    def _process_frame(self, frame):
        """Process single frame with YOLO"""
        # Resize
        stream_width = self.config.get("streamWidth", 640)
        stream_height = self.config.get("streamHeight", 480)
        frame = cv2.resize(frame, (stream_width, stream_height))

        # Get detection mode
        detection_mode = self.detection_config.get('detection_mode', 'intrusion')

        # YOLO detection with global confidence threshold from config.json
        # The global confidence setting from /#config takes precedence over preset-specific values
        confidence = self.config.get('confidence', 0.5)

        # Use lock for thread-safe CUDA inference
        if self.model_lock:
            with self.model_lock:
                results = self.model(frame, conf=confidence, verbose=False)
        else:
            results = self.model(frame, conf=confidence, verbose=False)
        boxes = results[0].boxes

        # Process based on detection mode
        if detection_mode == 'intrusion':
            self._process_intrusion_mode(frame, boxes)
        else:  # ppe mode
            self._process_ppe_mode(frame, boxes)

    def _process_intrusion_mode(self, frame, boxes):
        """Process frame in intrusion detection mode"""
        # Count persons
        person_count = 0
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = self.model.names[cls_id].lower()
                if 'person' in cls_name or 'head' in cls_name:
                    person_count += 1

        # Update database
        db.update_camera_detection(self.camera_id, person_count)

        # Check if alert should be triggered
        min_persons = self.detection_config.get('intrusion_min_persons', 1)
        alert_cooldown = self.detection_config.get('cooldown_seconds', 5)

        if person_count >= min_persons:
            self._trigger_alert(frame, boxes, person_count, 'intrusion', alert_cooldown)

    def _count_persons_without_vest(self, persons: list, vests: list) -> int:
        """
        Count how many persons don't have an overlapping vest detection.
        Uses Intersection over Union (IoU) to determine if vest overlaps with person.

        Args:
            persons: List of person detections with 'xyxy' coordinates
            vests: List of vest detections with 'xyxy' coordinates

        Returns:
            Number of persons without a matching vest
        """
        def calculate_iou(box1, box2):
            """Calculate Intersection over Union between two boxes"""
            x1 = max(box1[0], box2[0])
            y1 = max(box1[1], box2[1])
            x2 = min(box1[2], box2[2])
            y2 = min(box1[3], box2[3])

            intersection = max(0, x2 - x1) * max(0, y2 - y1)
            area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
            area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
            union = area1 + area2 - intersection

            return intersection / union if union > 0 else 0

        def vest_overlaps_person(person_box, vest_box):
            """Check if vest bounding box overlaps with person (vest should be inside person)"""
            # Check if vest center is within person bounding box
            vest_center_x = (vest_box[0] + vest_box[2]) / 2
            vest_center_y = (vest_box[1] + vest_box[3]) / 2

            in_person = (person_box[0] <= vest_center_x <= person_box[2] and
                        person_box[1] <= vest_center_y <= person_box[3])

            # Also check IoU as fallback
            iou = calculate_iou(person_box, vest_box)

            return in_person or iou > 0.1  # Low IoU threshold since vest is smaller than person

        persons_without_vest = 0
        for person in persons:
            has_vest = False
            for vest in vests:
                if vest_overlaps_person(person['xyxy'], vest['xyxy']):
                    has_vest = True
                    break
            if not has_vest:
                persons_without_vest += 1

        return persons_without_vest

    def _has_hivis_color(self, frame, box_xyxy, threshold=0.08):
        """
        Check if ROI contains hi-vis colored pixels.
        Used to override false 'novest' detections when vest is actually present.

        Handles multiple scenarios:
        - Closed vests (full ROI analysis)
        - Open vests (lateral strips)
        - Distant persons (center vertical strip + relaxed color thresholds)

        Args:
            frame: BGR image (numpy array)
            box_xyxy: Bounding box coordinates [x1, y1, x2, y2]
            threshold: Minimum percentage of hi-vis pixels required (default 8%)

        Returns:
            True if hi-vis color detected above threshold
        """
        x1, y1, x2, y2 = map(int, box_xyxy)

        # Expand ROI by 30% to capture more area (hi-vis might be partially outside box)
        box_w = x2 - x1
        box_h = y2 - y1
        expand_x = int(box_w * 0.30)
        expand_y = int(box_h * 0.30)
        x1 -= expand_x
        y1 -= expand_y
        x2 += expand_x
        y2 += expand_y

        # Ensure coordinates are within frame bounds
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return False

        roi = frame[y1:y2, x1:x2]

        if roi.size == 0:
            return False

        roi_h, roi_w = roi.shape[:2]
        total_pixels = roi_h * roi_w

        # Determine if this is a "distant" person (small bounding box)
        # Small boxes have more background noise, need different strategy
        is_distant = (roi_w * roi_h) < 5000  # Less than ~70x70 pixels

        # Hi-vis color ranges in HSV (calibrated from construction site screenshots)
        # Format: (H_min, S_min, V_min), (H_max, S_max, V_max)
        # Note: In HSV, red wraps around - H=0 and H=170-180 are both red
        hi_vis_ranges = [
            ((0, 70, 50), (10, 255, 255)),      # Red (pure red, H=0-10)
            ((170, 70, 50), (180, 255, 255)),   # Red-wrap (red at high hue values)
            ((0, 80, 80), (25, 255, 255)),      # Orange (includes red-orange)
            ((25, 80, 120), (45, 255, 255)),    # Yellow
            ((45, 60, 80), (95, 255, 255)),     # Green (lime/fluo)
        ]

        # Relaxed ranges for distant persons (lower saturation due to distance/compression)
        # Note: In HSV, red wraps around (H=0 and H=170-180 are both red)
        hi_vis_ranges_relaxed = [
            ((0, 50, 40), (10, 255, 255)),      # Red - lower S,V for distant/dark red
            ((170, 50, 40), (180, 255, 255)),   # Red-wrap - for distant
            ((0, 50, 50), (25, 255, 255)),      # Orange - lower S,V for distant
            ((25, 50, 80), (50, 255, 255)),     # Yellow - extended range
            ((40, 40, 60), (100, 255, 255)),    # Green - extended range
        ]

        def count_hivis_pixels(img_region, ranges):
            """Count hi-vis pixels in an image region"""
            if img_region.size == 0:
                return 0
            hsv = cv2.cvtColor(img_region, cv2.COLOR_BGR2HSV)
            count = 0
            for lower, upper in ranges:
                mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
                count += cv2.countNonZero(mask)
            return count

        # Choose color ranges based on distance
        color_ranges = hi_vis_ranges_relaxed if is_distant else hi_vis_ranges

        # Strategy 1: Check full ROI (for closed vests)
        hivis_full = count_hivis_pixels(roi, color_ranges)
        full_ratio = hivis_full / total_pixels

        # Strategy 2: Check lateral strips (for OPEN vests - color visible on sides)
        # Analyze left 25% and right 25% of the ROI
        strip_width = max(1, roi_w // 4)
        left_strip = roi[:, :strip_width]
        right_strip = roi[:, -strip_width:]

        lateral_pixels = left_strip.shape[0] * left_strip.shape[1] * 2
        hivis_lateral = count_hivis_pixels(left_strip, color_ranges) + count_hivis_pixels(right_strip, color_ranges)
        lateral_ratio = hivis_lateral / lateral_pixels if lateral_pixels > 0 else 0

        # Strategy 3: Check CENTER vertical strip (for distant persons)
        # The torso/vest should be in the center, background on edges
        center_margin = max(1, roi_w // 4)  # Skip 25% on each side
        center_strip = roi[:, center_margin:-center_margin] if roi_w > center_margin * 2 else roi
        center_pixels = center_strip.shape[0] * center_strip.shape[1] if center_strip.size > 0 else 1
        hivis_center = count_hivis_pixels(center_strip, color_ranges)
        center_ratio = hivis_center / center_pixels

        # Debug logging
        distance_label = "DISTANT" if is_distant else "CLOSE"
        logger.debug(f"[{self.camera_name}] ColorCheck [{distance_label}] ROI: {roi_w}x{roi_h}, "
                    f"Full: {full_ratio:.1%}, Lateral: {lateral_ratio:.1%}, Center: {center_ratio:.1%}")

        # Thresholds adjusted for distance
        full_threshold = threshold * 0.5 if is_distant else threshold  # 4% for distant, 8% for close
        lateral_threshold = 0.10 if is_distant else 0.15  # 10% for distant, 15% for close
        center_threshold = 0.05 if is_distant else 0.10   # 5% for distant, 10% for close

        if full_ratio >= full_threshold:
            logger.info(f"[{self.camera_name}] Color override [{distance_label}]: full ROI {full_ratio:.1%} >= {full_threshold:.1%}")
            return True

        if lateral_ratio >= lateral_threshold:
            logger.info(f"[{self.camera_name}] Color override [{distance_label}]: lateral {lateral_ratio:.1%} >= {lateral_threshold:.1%}")
            return True

        if center_ratio >= center_threshold:
            logger.info(f"[{self.camera_name}] Color override [{distance_label}]: center {center_ratio:.1%} >= {center_threshold:.1%}")
            return True

        logger.debug(f"[{self.camera_name}] No color override [{distance_label}] - full: {full_ratio:.1%}, lateral: {lateral_ratio:.1%}, center: {center_ratio:.1%}")
        return False

    def _process_ppe_mode(self, frame, boxes):
        """Process frame in PPE detection mode

        Supports two model types:
        1. Models with explicit no_vest/novest class (e.g., helmet_vest.pt)
        2. Models with only vest class (e.g., workspace_safety.pt) - uses person/vest overlap logic
        """
        # Count persons and PPE violations
        person_count = 0
        ppe_violations = []

        require_helmet = self.detection_config.get('ppe_require_helmet', True)
        require_vest = self.detection_config.get('ppe_require_vest', True)

        if boxes is not None and len(boxes) > 0:
            # Group detections by type
            persons = []      # person detections with bounding box coords
            helmets = []
            vests = []
            no_helmets = []
            no_vests = []

            # Classes to ignore (not relevant for vest/helmet PPE detection)
            ignored_classes = {
                'machinery', 'vehicle', 'safety cone',  # construction_safety.pt
                'mask', 'no-mask',  # construction_safety.pt
                'ear', 'ear-mufs', 'face', 'face-guard', 'face-mask',  # sh17 - body parts/other PPE
                'foot', 'hands', 'head', 'tool', 'glasses', 'gloves',  # sh17 - body parts/other PPE
                'shoes', 'safety-suit', 'medical-suit'  # sh17 - other PPE
            }

            # Diagnostic: log all detected classes
            all_detections = []
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = self.model.names[cls_id].lower()
                conf = float(box.conf[0])

                # Skip ignored classes
                if cls_name in ignored_classes:
                    continue

                xyxy = box.xyxy[0].cpu().numpy()  # Get bounding box coordinates

                box_data = {
                    'box': box,
                    'conf': conf,
                    'xyxy': xyxy,  # [x1, y1, x2, y2]
                    'cls_name': cls_name
                }
                all_detections.append(f"{cls_name}:{conf:.1%}")

                if cls_name == 'person':
                    persons.append(box_data)
                elif 'helmet' in cls_name or 'hat' in cls_name:
                    if 'no' in cls_name:
                        no_helmets.append(box_data)
                    else:
                        helmets.append(box_data)
                elif 'vest' in cls_name:
                    if 'no' in cls_name:
                        # COLOR OVERRIDE: Check if hi-vis color is present despite 'novest' detection
                        vest_color_override = self.config.get('vestColorOverride', {})
                        if vest_color_override.get('enabled', True):
                            threshold = vest_color_override.get('threshold', 0.15)
                            if self._has_hivis_color(frame, xyxy, threshold=threshold):
                                # Hi-vis color detected - override novest, consider vest as present
                                # Change cls_name to 'vest' so annotation shows green box
                                box_data['cls_name'] = 'vest'
                                box_data['color_override'] = True  # Flag for logging
                                vests.append(box_data)
                                logger.info(f"[{self.camera_name}] Color override: novest→vest (hi-vis detected in ROI)")
                            else:
                                no_vests.append(box_data)
                        else:
                            no_vests.append(box_data)
                    else:
                        vests.append(box_data)

            person_count = len(persons)

            # Log all detections for diagnostics
            if all_detections:
                logger.info(f"[{self.camera_name}] PPE detections: {', '.join(all_detections)} | persons={len(persons)} helmets={len(helmets)} vests={len(vests)} no_helmets={len(no_helmets)} no_vests={len(no_vests)}")

            # Check for PPE violations
            # Determine if model has explicit "no" classes (like NO-Safety Vest, NO-Hardhat)
            model_classes_lower = [name.lower() for name in self.model.names.values()]
            has_explicit_no_vest = any('no' in c and 'vest' in c for c in model_classes_lower)
            has_explicit_no_helmet = any('no' in c and ('helmet' in c or 'hat' in c) for c in model_classes_lower)

            # Helmet: use no_helmet detections directly
            if require_helmet and len(no_helmets) > 0:
                ppe_violations.append('helmet_missing')

            # Vest: different logic based on model type
            if require_vest:
                if len(no_vests) > 0:
                    # Explicit NO-Safety Vest detected - definitely a violation
                    ppe_violations.append('vest_missing')
                elif not has_explicit_no_vest:
                    # Model doesn't have NO-Vest class, use fallback overlap logic
                    if len(persons) > 0 and len(vests) == 0:
                        # No vests detected at all - violation
                        ppe_violations.append('vest_missing')
                    elif len(persons) > 0 and len(vests) > 0:
                        # Check if each person has a vest (using bounding box overlap)
                        persons_without_vest = self._count_persons_without_vest(persons, vests)
                        if persons_without_vest > 0:
                            ppe_violations.append('vest_missing')
                # If model HAS explicit NO-Vest class but none detected, no violation

        # Update database
        db.update_camera_detection(self.camera_id, person_count)

        # Trigger alert only if PPE violations detected
        if ppe_violations:
            alert_cooldown = self.detection_config.get('cooldown_seconds', 5)
            # Combine all processed boxes for annotation (with corrected cls_name after color override)
            processed_boxes = persons + helmets + no_helmets + vests + no_vests
            self._trigger_alert(frame, boxes, person_count, 'ppe_violation', alert_cooldown, ppe_violations, processed_boxes)

    def _trigger_alert(self, frame, boxes, person_count, alert_type, cooldown, violations=None, processed_boxes=None):
        """Trigger alert if cooldown period has passed"""
        current_time = time.time()

        if current_time - self.last_alert_time < cooldown:
            return

        self.last_alert_time = current_time

        # Calculate confidence
        confidences = boxes.conf.cpu().numpy() if boxes is not None else []
        avg_conf = float(np.mean(confidences)) if len(confidences) > 0 else 0.0

        # Save detection
        db.insert_detection(self.camera_id, person_count, avg_conf)

        # Save alert images (use processed_boxes for correct annotation colors after color override)
        full_path, annotated_path, cropped_path = self._save_alert_images(frame, boxes, processed_boxes)

        # Create relative paths
        full_rel = f"/static/alerts/{Path(full_path).name}"
        annotated_rel = f"/static/alerts/{Path(annotated_path).name}" if annotated_path else None

        # Insert alert into database
        db.insert_alert(self.camera_id, self.camera_name, person_count, avg_conf,
                      full_rel, annotated_rel)

        # Log alert
        if alert_type == 'ppe_violation':
            logger.info(f"[{self.camera_name}] PPE ALERT: {', '.join(violations)} - {person_count} person(s)")
        else:
            logger.info(f"[{self.camera_name}] INTRUSION ALERT: {person_count} person(s) detected")

        # Send to external systems (NxWitness, EVLOS)
        # Use cropped image for EVLOS if available, otherwise use annotated
        evlos_image_path = cropped_path if cropped_path else annotated_path
        self._send_external_alerts(boxes, person_count, avg_conf, evlos_image_path, alert_type)

    def _send_external_alerts(self, boxes, person_count, avg_conf, annotated_path, alert_type):
        """Send alerts to external systems (NxWitness, EVLOS)"""
        # Send alert to NxWitness if enabled
        nx_alerts_config = self.config.get("nxWitnessAlerts", {})
        if nx_alerts_config.get("enabled", False):
            logger.info(f"[{self.camera_name}] NxWitness alerts enabled, sending HTTP alert...")
            try:
                # Prepare bounding boxes data
                boxes_data = []
                if boxes is not None and len(boxes) > 0:
                    for box in boxes:
                        x1, y1, x2, y2 = map(float, box.xyxy[0].cpu().numpy())
                        boxes_data.append({
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "confidence": float(box.conf[0]),
                            "class": self.model.names[int(box.cls[0])]
                        })

                # Send event to NxWitness if enabled (with image attachment)
                if nx_alerts_config.get("sendEvents", True):
                    success = nx_client.send_alert(
                        camera_id=self.camera_id,
                        camera_name=self.camera_name,
                        person_count=person_count,
                        confidence=avg_conf,
                        boxes=boxes_data,
                        image_path=annotated_path
                    )
                    if success:
                        logger.info(f"[{self.camera_name}] ✅ Alert event sent to NxWitness (with image)")
                    else:
                        logger.warning(f"[{self.camera_name}] ⚠️ Failed to send alert to NxWitness")

                # Create bookmark on NxWitness timeline if enabled
                if nx_alerts_config.get("createBookmarks", True):
                    bookmark_duration = nx_alerts_config.get("bookmarkDuration", 300)
                    bookmark_success = nx_client.create_bookmark(
                        camera_id=self.camera_id,
                        name=f"{alert_type.upper()} - {person_count} person(s)",
                        duration_seconds=bookmark_duration,
                        tags={
                            "persons": str(person_count),
                            "confidence": f"{avg_conf:.2f}",
                            "type": alert_type
                        }
                    )
                    if bookmark_success:
                        logger.info(f"[{self.camera_name}] ✅ Bookmark created on NxWitness")
                    else:
                        logger.warning(f"[{self.camera_name}] ⚠️ Failed to create bookmark")
            except Exception as e:
                logger.error(f"[{self.camera_name}] Error sending NxWitness alert: {e}")

        # Send to EVLOS if enabled
        if evlos_client.enabled and annotated_path:
            try:
                # Determine alert level based on person count
                if person_count >= 3:
                    alert_level = 'high'
                elif person_count == 2:
                    alert_level = 'medium'
                else:
                    alert_level = 'low'

                # Strip braces from camera_id if present
                clean_camera_id = self.camera_id.strip('{}')

                # Determine EVLOS alert type
                if alert_type == 'ppe_violation':
                    evlos_alert_type = 'no_ppe'
                else:
                    evlos_alert_type = 'person_detection'

                evlos_client.send_alert_async(
                    image_data=annotated_path,
                    camera_id=clean_camera_id,
                    alert_type=evlos_alert_type,
                    person_count=person_count,
                    severity=alert_level,
                    confidence=avg_conf,
                    timestamp=datetime.now()
                )
                logger.info(f"[{self.camera_name}] 📤 EVLOS alert queued for {clean_camera_id}")
            except Exception as e:
                logger.error(f"[{self.camera_name}] Error sending EVLOS alert: {e}")

    def _save_alert_images(self, frame, boxes, processed_boxes=None):
        """Save full frame, annotated image, and smart-cropped version

        Args:
            frame: Original frame
            boxes: YOLO detection boxes (used for coordinates)
            processed_boxes: Optional list of processed box dicts with corrected cls_name
                             (used for annotation colors after color override)
        """
        alerts_dir = Path(__file__).parent.parent / "data" / "static" / "alerts"
        alerts_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        camera_safe_name = self.camera_name.replace(' ', '_').replace('/', '_')

        # Save full frame (original, no blur)
        full_filename = f"{camera_safe_name}_{timestamp}_full.jpg"
        full_path = alerts_dir / full_filename
        cv2.imwrite(str(full_path), frame)

        # Save annotated image with face blur applied
        annotated_path = None
        cropped_path = None
        if boxes is not None and len(boxes) > 0:
            # Calculate bounding box that contains all detections
            all_x1, all_y1, all_x2, all_y2 = [], [], [], []
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                all_x1.append(x1)
                all_y1.append(y1)
                all_x2.append(x2)
                all_y2.append(y2)

            # Get overall bounding box
            min_x = min(all_x1)
            min_y = min(all_y1)
            max_x = max(all_x2)
            max_y = max(all_y2)

            # Add margin (20% on each side)
            margin_percent = 0.20
            width = max_x - min_x
            height = max_y - min_y
            margin_x = int(width * margin_percent)
            margin_y = int(height * margin_percent)

            # Apply margin with bounds checking
            frame_h, frame_w = frame.shape[:2]
            crop_x1 = max(0, min_x - margin_x)
            crop_y1 = max(0, min_y - margin_y)
            crop_x2 = min(frame_w, max_x + margin_x)
            crop_y2 = min(frame_h, max_y + margin_y)

            # Create annotated frame copy
            annotated_frame = frame.copy()

            # Color map for different classes (BGR format for OpenCV)
            # Supports multiple PPE model formats
            color_map = {
                # Person/Head classes - Cyan
                'person': (255, 255, 0),
                'head': (255, 255, 0),
                'face': (255, 255, 0),
                # Compliant PPE - Green
                'hat': (0, 255, 0),
                'helmet': (0, 255, 0),
                'hardhat': (0, 255, 0),  # construction_safety.pt
                'head_helmet': (0, 255, 0),  # workspace_safety.pt
                'vest': (0, 255, 0),
                'safety vest': (0, 255, 0),  # construction_safety.pt
                'safety-vest': (0, 255, 0),  # sh17 model
                'mask': (0, 255, 0),
                'face-mask': (0, 255, 0),  # sh17 model
                'face-guard': (0, 255, 0),  # sh17 model
                'gloves': (0, 255, 0),  # sh17 model
                'glasses': (0, 255, 0),
                'ear-mufs': (0, 255, 0),  # sh17 model
                'shoes': (0, 255, 0),
                'safety-suit': (0, 255, 0),  # sh17 model
                'medical-suit': (0, 255, 0),  # sh17 model
                # Violations - Red
                'nohat': (0, 0, 255),
                'no-hat': (0, 0, 255),
                'no-hardhat': (0, 0, 255),  # construction_safety.pt
                'head_nohelmet': (0, 0, 255),  # workspace_safety.pt
                'novest': (0, 0, 255),
                'no-vest': (0, 0, 255),
                'no-safety vest': (0, 0, 255),  # construction_safety.pt
                'no-mask': (0, 0, 255),
                # Other classes - Cyan (info only)
                'ear': (255, 255, 0),
                'hands': (255, 255, 0),
                'foot': (255, 255, 0),
                'tool': (255, 165, 0),  # Orange
                # Ignored classes (kept for reference)
                'safety cone': (0, 255, 255),
                'machinery': (255, 165, 0),
                'vehicle': (255, 165, 0),
            }

            # Use processed_boxes if available (has corrected cls_name after color override)
            # Otherwise fall back to YOLO boxes
            if processed_boxes:
                boxes_to_draw = processed_boxes
            else:
                boxes_to_draw = [
                    {
                        'xyxy': box.xyxy[0].cpu().numpy(),
                        'conf': float(box.conf[0]),
                        'cls_name': self.model.names[int(box.cls[0])]
                    }
                    for box in boxes
                ]

            for box_data in boxes_to_draw:
                xyxy = box_data.get('xyxy')
                if xyxy is None:
                    continue
                x1, y1, x2, y2 = map(int, xyxy)
                conf = box_data.get('conf', 0.0)
                cls_name = box_data.get('cls_name', 'unknown')

                # Get color for this class (default to white if not found)
                color = color_map.get(cls_name.lower(), (255, 255, 255))

                # Draw rectangle with thickness=2
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

                # Draw label with matching color
                label = f"{cls_name} {conf:.2f}"
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)

                # Position label based on class type to avoid overlap
                cls_lower = cls_name.lower()

                if 'vest' in cls_lower:
                    # Vest labels on the RIGHT side (top-right corner)
                    label_x = x2 - label_size[0] - 4
                    label_bg_x1 = x2 - label_size[0] - 4
                    label_bg_x2 = x2
                    label_y = y1 - 4
                    label_bg_y1 = y1 - label_size[1] - 8
                    label_bg_y2 = y1

                elif 'hat' in cls_lower or 'helmet' in cls_lower:
                    # Hat/Helmet labels on the LEFT side (top-left corner)
                    label_x = x1 + 4
                    label_bg_x1 = x1
                    label_bg_x2 = x1 + label_size[0] + 8
                    label_y = y1 - 4
                    label_bg_y1 = y1 - label_size[1] - 8
                    label_bg_y2 = y1

                else:
                    # Person/Head labels at the BOTTOM (below the rectangle)
                    label_x = x1 + 4
                    label_bg_x1 = x1
                    label_bg_x2 = x1 + label_size[0] + 8
                    label_y = y2 + label_size[1] + 4
                    label_bg_y1 = y2
                    label_bg_y2 = y2 + label_size[1] + 8

                # Background for label (filled rectangle with same color)
                cv2.rectangle(annotated_frame,
                            (label_bg_x1, label_bg_y1),
                            (label_bg_x2, label_bg_y2),
                            color, -1)

                # Text label (black text for better readability)
                cv2.putText(annotated_frame, label, (label_x, label_y),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

            # Save full annotated image
            annotated_filename = f"{camera_safe_name}_{timestamp}_annotated.jpg"
            annotated_path = alerts_dir / annotated_filename
            cv2.imwrite(str(annotated_path), annotated_frame)

            # Save cropped version with margin (for EVLOS)
            cropped_frame = annotated_frame[crop_y1:crop_y2, crop_x1:crop_x2]
            cropped_filename = f"{camera_safe_name}_{timestamp}_cropped.jpg"
            cropped_path = alerts_dir / cropped_filename
            cv2.imwrite(str(cropped_path), cropped_frame)

        return str(full_path), str(annotated_path) if annotated_path else None, str(cropped_path) if cropped_path else None


class VideoWorkerManager:
    """Manages multiple camera workers"""

    def __init__(self):
        self.workers: Dict[str, CameraWorker] = {}
        self.model = None
        self.config = {}
        self._initialized = False
        self.model_lock = threading.Lock()  # Lock for thread-safe CUDA inference

    def initialize(self):
        """Initialize YOLO model and load config"""
        if self._initialized:
            return

        logger.info("Initializing Video Worker Manager...")

        # Load config
        config_path = Path(__file__).parent.parent / "config.json"
        if config_path.exists():
            import json
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {
                "model": "yolov8n.pt",
                "confidence": 0.5,
                "device": "cuda:0",
                "minPersons": 1,
                "cooldown": 5,
                "frameSampling": 10,
                "streamWidth": 640,
                "streamHeight": 480,
                "streamQuality": "medium"
            }

        # Load YOLO model
        device = self.config.get("device", "cuda:0")
        model_name = self.config.get("model", "yolov8n.pt")

        # Resolve model path relative to backend directory
        if not Path(model_name).is_absolute():
            backend_dir = Path(__file__).parent.parent
            model_path = backend_dir / model_name
            if model_path.exists():
                model_name = str(model_path)
            else:
                logger.warning(f"Model not found at {model_path}, using original path: {model_name}")

        logger.info(f"Loading YOLO model {model_name} on {device}...")
        self.model = YOLO(model_name)
        self.model.to(device)

        # Log model classes for verification
        logger.info(f"YOLO model loaded on {device}")
        logger.info(f"Model classes: {list(self.model.names.values())}")

        self._initialized = True
        logger.info("Video Worker Manager initialized")

        # Auto-start workers for cameras that were enabled before shutdown
        self._restore_worker_states()

    def start_worker(self, camera_id: str, camera_name: str) -> bool:
        """Start worker for a camera"""
        if not self._initialized:
            self.initialize()

        # Stop existing worker if running
        if camera_id in self.workers:
            self.workers[camera_id].stop()

        # Create and start new worker
        worker = CameraWorker(camera_id, camera_name, self.model, self.config, self.model_lock)
        self.workers[camera_id] = worker
        success = worker.start()

        # Save enabled state to database for persistence
        if success:
            db.set_camera_enabled(camera_id, True)

        return success

    def stop_worker(self, camera_id: str) -> bool:
        """Stop worker for a camera"""
        if camera_id not in self.workers:
            logger.warning(f"No worker found for camera {camera_id}")
            return False

        worker = self.workers[camera_id]
        result = worker.stop()
        del self.workers[camera_id]

        # Save disabled state to database for persistence
        if result:
            db.set_camera_enabled(camera_id, False)

        return result

    def get_worker_status(self, camera_id: str) -> bool:
        """Check if worker is running for a camera"""
        if camera_id not in self.workers:
            return False
        return self.workers[camera_id].running

    def reload_config(self):
        """Reload configuration from config.json and update all workers"""
        logger.info("Reloading configuration...")
        config_path = Path(__file__).parent.parent / "config.json"
        if config_path.exists():
            import json
            with open(config_path, 'r') as f:
                self.config = json.load(f)

            # Update config and detection_config for all running workers
            # The global confidence from config.json is used for all detection thresholds
            global_confidence = self.config.get('confidence', 0.5)
            logger.info(f"Global confidence threshold set to: {global_confidence}")

            for camera_id, worker in self.workers.items():
                worker.config = self.config
                # Reload detection_config from database (for non-confidence settings like detection_mode)
                new_detection_config = db.get_camera_detection_config(camera_id)
                if new_detection_config:
                    worker.detection_config = new_detection_config
                logger.info(f"[{worker.camera_name}] Config updated, using global confidence: {global_confidence}")

            logger.info("Configuration reloaded successfully")
            return True
        else:
            logger.warning("Config file not found, keeping existing configuration")
            return False

    def stop_all(self):
        """Stop all workers"""
        logger.info("Stopping all video workers...")
        for camera_id in list(self.workers.keys()):
            self.stop_worker(camera_id)
        logger.info("All video workers stopped")

    def _restore_worker_states(self):
        """Restore worker states from database on startup"""
        try:
            enabled_cameras = db.get_enabled_cameras()
            if not enabled_cameras:
                logger.info("No cameras were previously enabled")
                return

            logger.info(f"Restoring {len(enabled_cameras)} camera worker(s) from previous session...")

            for i, camera in enumerate(enabled_cameras):
                camera_id = camera['camera_id']
                camera_name = camera['camera_name']

                try:
                    # Create worker without calling start_worker to avoid double-setting enabled flag
                    worker = CameraWorker(camera_id, camera_name, self.model, self.config, self.model_lock)
                    self.workers[camera_id] = worker
                    success = worker.start()

                    if success:
                        logger.info(f"✓ Restored worker for camera: {camera_name}")
                    else:
                        logger.warning(f"✗ Failed to restore worker for camera: {camera_name}")
                        # Remove from enabled list if failed to start
                        db.set_camera_enabled(camera_id, False)

                    # Add delay between worker starts to prevent memory spikes
                    if i < len(enabled_cameras) - 1:
                        time.sleep(1.0)  # 1 second delay between each worker start

                except Exception as e:
                    logger.error(f"Error restoring worker for {camera_name}: {e}")
                    db.set_camera_enabled(camera_id, False)

            logger.info("Worker state restoration completed")
        except Exception as e:
            logger.error(f"Failed to restore worker states: {e}")
