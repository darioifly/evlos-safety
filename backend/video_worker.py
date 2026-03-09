"""
Video Worker Process - Separate from FastAPI
Processes camera streams and writes detections to SQLite database
Run this as a separate process: python video_worker.py
"""
import time
import cv2
import numpy as np
import requests
from requests.auth import HTTPBasicAuth
from ultralytics import YOLO
import torch
import os
import threading
from datetime import datetime
from pathlib import Path

from config import settings
from utils.logger import logger
from database import db
from services.nx_witness import nx_client
from services.ptz_client_v2 import initialize_ptz_client, get_ptz_client
from services.ptz_tracker import PTZTrackerManager

# Load configuration from JSON
def load_config():
    """Load configuration from config.json"""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        import json
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        # Return defaults if config.json doesn't exist
        return {
            "model": "yolov8n.pt",
            "confidence": 0.5,
            "device": "cuda:0",
            "minPersons": 1,
            "cooldown": 5,
            "batchSize": 4,
            "streamWidth": 640,
            "streamHeight": 480,
            "frameSampling": 10
        }

# Load config
CONFIG = load_config()

# Configuration from JSON
FRAME_SAMPLING = CONFIG.get("frameSampling", 10)
ALERT_COOLDOWN = CONFIG.get("cooldown", 5)
MIN_PERSONS = CONFIG.get("minPersons", 1)
ALERTS_DIR = Path(__file__).parent / "static" / "alerts"

# Create alerts directory if it doesn't exist
ALERTS_DIR.mkdir(parents=True, exist_ok=True)

class VideoWorker:
    """Processes video streams independently from FastAPI"""

    def __init__(self):
        self.model = None
        self.last_alert_time = {}  # Track last alert per camera
        self.ptz_manager = None  # PTZ tracker manager

    def initialize(self):
        """Initialize YOLO model"""
        logger.info("=" * 60)
        logger.info("Video Worker Starting...")
        logger.info("=" * 60)

        # Load YOLO
        device = CONFIG.get("device", "cuda:0")
        model_name = CONFIG.get("model", "yolov8n.pt")
        logger.info(f"Loading YOLO model {model_name} on {device}...")
        self.model = YOLO(model_name)
        self.model.to(device)
        logger.info(f"✓ Model loaded on {device}")

        # Get cameras from NX Witness
        logger.info("Fetching cameras from NX Witness...")
        cameras = nx_client.get_cameras()
        logger.info(f"Found {len(cameras)} cameras")

        # Initialize camera status in database
        for camera in cameras:
            db.upsert_camera_status(
                camera_id=camera['id'],
                camera_name=camera.get('name', camera['id']),
                online=camera.get('isOnline', False)
            )

        # Initialize PTZ if enabled
        ptz_config = CONFIG.get("ptz", {})
        if ptz_config.get("enabled", False):
            logger.info("Initializing PTZ tracking system...")
            try:
                initialize_ptz_client(
                    base_url=settings.NX_STREAM_SERVER_URL,
                    username=settings.NX_ADMIN_USERNAME,
                    password=settings.NX_ADMIN_PASSWORD
                )
                ptz_client = get_ptz_client()
                self.ptz_manager = PTZTrackerManager(ptz_client, ptz_config, db)
                logger.info("✓ PTZ tracking initialized")
            except Exception as e:
                logger.error(f"Failed to initialize PTZ: {e}")
                self.ptz_manager = None
        else:
            logger.info("PTZ tracking disabled in config")

        logger.info("✓ Video Worker initialized")
        logger.info("=" * 60)

        return cameras

    def process_camera_stream(self, camera):
        """Process a single camera stream continuously in a loop"""
        camera_id = camera['id']
        camera_name = camera.get('name', camera_id)

        logger.info(f"[{camera_name}] Worker thread started")

        while True:
            try:
                # Check if camera is enabled for processing
                camera_status = db.get_camera_status(camera_id)
                if not camera_status or not camera_status.get('enabled', True):
                    # Camera is disabled, wait and check again
                    db.upsert_camera_status(
                        camera_id=camera_id,
                        camera_name=camera_name,
                        online=camera.get('isOnline', False),
                        stream_connected=False
                    )
                    time.sleep(5)  # Check every 5 seconds
                    continue

                # Get stream quality from config
                stream_quality = CONFIG.get("streamQuality", "medium")
                stream_url = nx_client.get_stream_url(camera_id, quality=stream_quality)
                self._process_camera_loop(camera, stream_url)
            except Exception as e:
                logger.error(f"[{camera_name}] Error in worker thread: {e}")
                time.sleep(5)

    def _process_camera_loop(self, camera, stream_url):
        """Internal method to process camera stream"""
        camera_id = camera['id']
        camera_name = camera.get('name', camera_id)

        logger.info(f"[{camera_name}] Connecting to stream...")

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
                logger.error(f"[{camera_name}] Failed to connect: HTTP {response.status_code}")
                db.upsert_camera_status(camera_id, camera_name, online=False, stream_connected=False)
                return

            logger.info(f"[{camera_name}] ✓ Connected to stream")
            db.upsert_camera_status(camera_id, camera_name, online=True, stream_connected=True)

            # Process frames
            bytes_data = bytes()
            frame_count = 0
            fps_start = time.time()
            fps_frames = 0
            resolution_logged = False  # Flag to log resolution once

            for chunk in response.iter_content(chunk_size=4096):
                # Check if camera is still enabled every 100 frames
                if frame_count % 100 == 0:
                    camera_status = db.get_camera_status(camera_id)
                    if not camera_status or not camera_status.get('enabled', True):
                        logger.info(f"[{camera_name}] Camera disabled, stopping stream")
                        db.upsert_camera_status(camera_id, camera_name,
                                              online=camera.get('isOnline', False),
                                              stream_connected=False)
                        return  # Exit the loop and go back to check

                bytes_data += chunk

                # Parse MJPEG
                a = bytes_data.find(b'\xff\xd8')
                b = bytes_data.find(b'\xff\xd9')

                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]

                    # Decode frame
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

                    if frame is not None:
                        # Log actual resolution on first frame
                        if not resolution_logged:
                            actual_height, actual_width = frame.shape[:2]
                            stream_quality = CONFIG.get("streamQuality", "unknown")
                            logger.info(f"[{camera_name}] Stream resolution: {actual_width}x{actual_height} "
                                      f"(quality setting: '{stream_quality}')")
                            resolution_logged = True

                        frame_count += 1
                        fps_frames += 1

                        # Update FPS every 5 seconds
                        if time.time() - fps_start >= 5.0:
                            fps = fps_frames / (time.time() - fps_start)
                            db.upsert_camera_status(camera_id, camera_name,
                                                   online=True, stream_connected=True, fps=fps)
                            fps_frames = 0
                            fps_start = time.time()

                        # Frame sampling
                        if frame_count % FRAME_SAMPLING == 0:
                            self._process_frame(frame, camera_id, camera_name)

        except Exception as e:
            logger.error(f"[{camera_name}] Stream error: {e}")
            db.upsert_camera_status(camera_id, camera_name, online=False, stream_connected=False)

    def _save_alert_images(self, frame, boxes, camera_name, results=None):
        """Save full frame and annotated image with bounding boxes"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        camera_safe_name = camera_name.replace(' ', '_').replace('/', '_')

        # Save full frame (original, no annotations)
        full_filename = f"{camera_safe_name}_{timestamp}_full.jpg"
        full_path = ALERTS_DIR / full_filename
        cv2.imwrite(str(full_path), frame)

        # Save annotated image with bounding boxes for ALL detected objects
        annotated_path = None
        if boxes is not None and len(boxes) > 0:
            # Manual drawing with thin borders (thickness = 1)
            annotated_frame = frame.copy()

            # Color map for different classes
            color_map = {
                'hat': (0, 255, 0),      # Green - compliant
                'helmet': (0, 255, 0),   # Green - compliant
                'vest': (0, 255, 0),     # Green - compliant
                'nohat': (0, 0, 255),    # Red - violation
                'novest': (0, 0, 255),   # Red - violation
                'person': (255, 255, 0), # Yellow - person
            }

            for box in boxes:
                # Get coordinates
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = self.model.names[cls_id]

                # Get color for this class
                color = color_map.get(cls_name.lower(), (255, 255, 255))

                # Draw rectangle with thickness = 1 (half of default 2)
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 1)

                # Draw label with confidence
                label = f"{cls_name} {conf:.2f}"
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)

                # Position label based on class type
                cls_lower = cls_name.lower()
                if 'vest' in cls_lower:
                    # Vest labels on the RIGHT side
                    label_x = x2 - label_size[0] - 4
                    label_bg_x1 = x2 - label_size[0] - 4
                    label_bg_x2 = x2
                else:
                    # Hat/helmet/person labels on the LEFT side
                    label_x = x1 + 2
                    label_bg_x1 = x1
                    label_bg_x2 = x1 + label_size[0] + 4

                # Background for label
                cv2.rectangle(annotated_frame, (label_bg_x1, y1 - label_size[1] - 6),
                            (label_bg_x2, y1), color, -1)

                # Text label
                cv2.putText(annotated_frame, label, (label_x, y1 - 3),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

            annotated_filename = f"{camera_safe_name}_{timestamp}_annotated.jpg"
            annotated_path = ALERTS_DIR / annotated_filename
            cv2.imwrite(str(annotated_path), annotated_frame)

        return str(full_path), str(annotated_path) if annotated_path else None

    def _process_frame(self, frame, camera_id, camera_name):
        """Process single frame with YOLO"""
        # Resize
        stream_width = CONFIG.get("streamWidth", 640)
        stream_height = CONFIG.get("streamHeight", 480)
        frame = cv2.resize(frame, (stream_width, stream_height))

        # Get detection configuration
        confidence = CONFIG.get("confidence", 0.5)
        model_type = CONFIG.get("modelType", "person")
        detection_mode = CONFIG.get("detectionMode", "person")

        # YOLO detection (no class filter - detect all classes the model supports)
        results = self.model(frame, conf=confidence, verbose=False)

        boxes = results[0].boxes
        total_detections = len(boxes) if boxes is not None else 0

        # Count by class for PPE models
        person_count = 0
        helmet_count = 0
        no_helmet_count = 0
        vest_count = 0
        no_vest_count = 0

        # Distance-based detection tracking
        frame_area = stream_width * stream_height
        distance_thresholds = CONFIG.get("distanceThresholds", {})
        very_far_threshold = distance_thresholds.get("veryFarThreshold", 0.05)
        far_threshold = distance_thresholds.get("farThreshold", 0.15)
        close_threshold = distance_thresholds.get("closeThreshold", 0.30)

        # Track detections by distance
        detections_by_distance = {
            "very_far": [],  # < 5% frame area
            "far": [],       # 5-15% frame area
            "medium": [],    # 15-30% frame area
            "close": []      # > 30% frame area
        }

        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = self.model.names[cls_id].lower()
                bbox = tuple(map(int, box.xyxy[0].cpu().numpy()))

                # Calculate bbox size for distance estimation
                bbox_width = bbox[2] - bbox[0]
                bbox_height = bbox[3] - bbox[1]
                bbox_area = bbox_width * bbox_height
                bbox_ratio = bbox_area / frame_area

                # Classify by distance
                if bbox_ratio < very_far_threshold:
                    distance_category = "very_far"
                elif bbox_ratio < far_threshold:
                    distance_category = "far"
                elif bbox_ratio < close_threshold:
                    distance_category = "medium"
                else:
                    distance_category = "close"

                # Store detection with distance info
                detection_info = {
                    "class_name": cls_name,
                    "bbox_ratio": bbox_ratio,
                    "confidence": float(box.conf[0])
                }
                detections_by_distance[distance_category].append(detection_info)

                # Count persons (includes person, head, or any human-like class)
                if 'person' in cls_name or 'head' in cls_name:
                    person_count += 1
                # Count helmets/hats
                elif 'helmet' in cls_name or 'hat' in cls_name:
                    if 'no' in cls_name:
                        no_helmet_count += 1
                    else:
                        helmet_count += 1
                # Count vests
                elif 'vest' in cls_name:
                    if 'no' in cls_name:
                        no_vest_count += 1
                    else:
                        vest_count += 1

        # PTZ Tracking Logic - Zoom on persons with missing PPE or unclear detections
        if self.ptz_manager and model_type == "ppe" and person_count > 0:
            # Check if camera has PTZ capability
            if self.ptz_manager.is_camera_ptz(camera_id):
                tracker = self.ptz_manager.get_or_create_tracker(camera_id, camera_name)

                # Calculate frame area for size threshold (don't zoom if target is already large)
                frame_area = stream_width * stream_height
                min_zoom_threshold = 0.15  # Don't zoom if bbox > 15% of frame

                # Build detections list for PTZ
                detections_for_ptz = []
                if boxes is not None:
                    for box in boxes:
                        cls_id = int(box.cls[0])
                        cls_name = self.model.names[cls_id]
                        conf = float(box.conf[0])
                        bbox = tuple(map(int, box.xyxy[0].cpu().numpy()))

                        # Calculate bbox size relative to frame
                        bbox_width = bbox[2] - bbox[0]
                        bbox_height = bbox[3] - bbox[1]
                        bbox_area = bbox_width * bbox_height
                        bbox_ratio = bbox_area / frame_area

                        # Track: generic "person" OR persons with missing PPE (nohat, novest)
                        # But skip if target is already too large (close to camera)
                        should_track_class = (
                            cls_name.lower() == "person" or
                            cls_name.lower() == "nohat" or
                            cls_name.lower() == "novest"
                        )

                        if should_track_class and bbox_ratio < min_zoom_threshold:
                            detections_for_ptz.append({
                                "bbox": bbox,
                                "confidence": conf,
                                "class_name": cls_name,
                                "bbox_ratio": bbox_ratio
                            })
                        elif should_track_class and bbox_ratio >= min_zoom_threshold:
                            logger.debug(f"[{camera_name}] Skipping zoom on {cls_name} - "
                                       f"target already large ({bbox_ratio*100:.1f}% of frame)")

                # Check if PTZ tracking should be triggered
                if tracker.should_track(detections_for_ptz):
                    logger.info(f"[{camera_name}] Triggering PTZ tracking for {len(detections_for_ptz)} target(s) "
                               f"[classes: {', '.join(set(d['class_name'] for d in detections_for_ptz))}]")
                    tracker.queue_targets(detections_for_ptz)
                    success = tracker.start_tracking(stream_width, stream_height)

                    if success:
                        logger.info(f"[{camera_name}] PTZ zoomed, will analyze next frame for PPE details")

                # Check if we're in zoomed state and should return to home
                elif tracker.state.value == "ZOOMED":
                    # Camera is zoomed, check if we found PPE info
                    if helmet_count > 0 or no_helmet_count > 0 or vest_count > 0 or no_vest_count > 0:
                        # Found PPE details, can return home
                        logger.info(f"[{camera_name}] PPE details detected in zoom, returning to home")
                        tracker.return_to_home()

                # Cleanup timeouts
                if tracker.check_timeout():
                    logger.warning(f"[{camera_name}] PTZ tracking timeout, forcing return to home")
                    tracker.abort_tracking()

        # Determine if we should alert based on mode and time
        should_alert = False
        alert_reason = ""

        if model_type == "ppe":
            # PPE model - check detection mode
            if detection_mode == "dual":
                # Dual mode: check time of day
                current_hour = datetime.now().hour
                day_start = CONFIG.get("schedule", {}).get("dayStartHour", 6)
                day_end = CONFIG.get("schedule", {}).get("dayEndHour", 18)
                is_daytime = day_start <= current_hour < day_end

                if is_daytime:
                    # Day mode: Check for PPE violations
                    require_helmet = CONFIG.get("ppeRules", {}).get("requireHelmet", True)
                    require_vest = CONFIG.get("ppeRules", {}).get("requireVest", True)
                    always_alert = CONFIG.get("ppeRules", {}).get("alwaysAlertOnPerson", False)

                    # Distance-aware PPE violation detection
                    # Only alert on violations we can confidently verify (medium/close distance)
                    alert_on_very_far = distance_thresholds.get("alertOnVeryFar", False)
                    alert_on_far = distance_thresholds.get("alertOnFar", True)
                    alert_on_close = distance_thresholds.get("alertOnClose", True)

                    violations = []
                    confidence_level = "UNKNOWN"

                    # Check close detections (most reliable)
                    if alert_on_close and (detections_by_distance["close"] or detections_by_distance["medium"]):
                        close_violations = [d for d in (detections_by_distance["close"] + detections_by_distance["medium"])
                                           if d["class_name"] in ["nohat", "novest"]]
                        if close_violations:
                            if require_helmet and any(d["class_name"] == "nohat" for d in close_violations):
                                violations.append(f"person(s) without helmet [CONFIRMED - Close]")
                            if require_vest and any(d["class_name"] == "novest" for d in close_violations):
                                violations.append(f"person(s) without vest [CONFIRMED - Close]")
                            confidence_level = "HIGH"

                    # Check far detections (medium reliability)
                    if alert_on_far and not violations and detections_by_distance["far"]:
                        far_violations = [d for d in detections_by_distance["far"]
                                         if d["class_name"] in ["nohat", "novest"]]
                        if far_violations:
                            if require_helmet and any(d["class_name"] == "nohat" for d in far_violations):
                                violations.append(f"person(s) possibly without helmet [MEDIUM - Far]")
                            if require_vest and any(d["class_name"] == "novest" for d in far_violations):
                                violations.append(f"person(s) possibly without vest [MEDIUM - Far]")
                            confidence_level = "MEDIUM"

                    # Check very far detections (low reliability - usually skip)
                    if alert_on_very_far and not violations and detections_by_distance["very_far"]:
                        very_far_persons = [d for d in detections_by_distance["very_far"]
                                           if "person" in d["class_name"]]
                        if very_far_persons:
                            violations.append(f"{len(very_far_persons)} person(s) detected [SUSPICIOUS - Very Far]")
                            confidence_level = "LOW"

                    if violations:
                        should_alert = True
                        alert_reason = f"PPE Detection [{confidence_level}]: {', '.join(violations)}"
                    elif always_alert and person_count >= MIN_PERSONS:
                        # Testing mode: alert on any person detection
                        should_alert = True
                        alert_reason = f"Detection Test: {person_count} person(s) detected"
                else:
                    # Night mode: Check for intrusion (any person)
                    if person_count >= MIN_PERSONS:
                        should_alert = True
                        alert_reason = f"Intrusion: {person_count} person(s) detected"

            elif detection_mode == "ppe":
                # PPE mode: Always check for PPE violations (distance-aware)
                require_helmet = CONFIG.get("ppeRules", {}).get("requireHelmet", True)
                require_vest = CONFIG.get("ppeRules", {}).get("requireVest", True)
                always_alert = CONFIG.get("ppeRules", {}).get("alwaysAlertOnPerson", False)

                alert_on_very_far = distance_thresholds.get("alertOnVeryFar", False)
                alert_on_far = distance_thresholds.get("alertOnFar", True)
                alert_on_close = distance_thresholds.get("alertOnClose", True)

                violations = []
                confidence_level = "UNKNOWN"

                # Check close detections (most reliable)
                if alert_on_close and (detections_by_distance["close"] or detections_by_distance["medium"]):
                    close_violations = [d for d in (detections_by_distance["close"] + detections_by_distance["medium"])
                                       if d["class_name"] in ["nohat", "novest"]]
                    if close_violations:
                        if require_helmet and any(d["class_name"] == "nohat" for d in close_violations):
                            violations.append(f"person(s) without helmet [CONFIRMED]")
                        if require_vest and any(d["class_name"] == "novest" for d in close_violations):
                            violations.append(f"person(s) without vest [CONFIRMED]")
                        confidence_level = "HIGH"

                # Check far detections (medium reliability)
                if alert_on_far and not violations and detections_by_distance["far"]:
                    far_violations = [d for d in detections_by_distance["far"]
                                     if d["class_name"] in ["nohat", "novest"]]
                    if far_violations:
                        if require_helmet and any(d["class_name"] == "nohat" for d in far_violations):
                            violations.append(f"person(s) possibly without helmet [NEEDS VERIFICATION]")
                        if require_vest and any(d["class_name"] == "novest" for d in far_violations):
                            violations.append(f"person(s) possibly without vest [NEEDS VERIFICATION]")
                        confidence_level = "MEDIUM"

                if violations:
                    should_alert = True
                    alert_reason = f"PPE Detection [{confidence_level}]: {', '.join(violations)}"
                elif always_alert and person_count >= MIN_PERSONS:
                    # Testing mode: alert on any person detection
                    should_alert = True
                    alert_reason = f"Detection Test: {person_count} person(s) detected"

            elif detection_mode == "person":
                # Person mode: Always check for intrusion
                if person_count >= MIN_PERSONS:
                    should_alert = True
                    alert_reason = f"Intrusion: {person_count} person(s) detected"
        else:
            # Person detection model - simple intrusion detection
            if person_count >= MIN_PERSONS:
                should_alert = True
                alert_reason = f"Intrusion: {person_count} person(s) detected"

        # Update database with person count (for compatibility)
        db.update_camera_detection(camera_id, person_count)

        if total_detections > 0:
            confidences = boxes.conf.cpu().numpy() if boxes is not None else []
            avg_conf = float(np.mean(confidences)) if len(confidences) > 0 else 0.0

            # Save detection
            db.insert_detection(camera_id, person_count, avg_conf)

            # Create alert if conditions met and cooldown passed
            if should_alert:
                current_time = time.time()
                last_alert = self.last_alert_time.get(camera_id, 0)

                if current_time - last_alert >= ALERT_COOLDOWN:
                    # Save images (full + annotated with bounding boxes)
                    full_path, annotated_path = self._save_alert_images(frame, boxes, camera_name, results)

                    # Create relative paths for database
                    full_rel = f"/static/alerts/{Path(full_path).name}"
                    annotated_rel = f"/static/alerts/{Path(annotated_path).name}" if annotated_path else None

                    db.insert_alert(camera_id, camera_name, person_count, avg_conf,
                                  full_rel, annotated_rel)
                    self.last_alert_time[camera_id] = current_time
                    logger.info(f"[{camera_name}] ALERT: {alert_reason}")

    def run(self):
        """Main worker loop with threading for multiple cameras"""
        cameras = self.initialize()

        logger.info("Starting continuous monitoring with multi-camera threading...")
        logger.info("Press Ctrl+C to stop")
        logger.info("-" * 60)

        # Get all online cameras
        online_cameras = [c for c in cameras if c.get('isOnline', False)]

        if not online_cameras:
            logger.warning("No online cameras found!")
            return

        logger.info(f"Found {len(online_cameras)} online cameras")

        # Create a thread for each online camera
        threads = []
        for camera in online_cameras:
            camera_name = camera.get('name', camera['id'])
            thread = threading.Thread(
                target=self.process_camera_stream,
                args=(camera,),
                daemon=True,
                name=f"Worker-{camera_name}"
            )
            thread.start()
            threads.append(thread)
            logger.info(f"Started thread for camera: {camera_name}")

        logger.info(f"All {len(threads)} camera threads started")
        logger.info("-" * 60)

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
                # Check if any threads have died and restart them
                for i, (thread, camera) in enumerate(zip(threads, online_cameras)):
                    if not thread.is_alive():
                        camera_name = camera.get('name', camera['id'])
                        logger.warning(f"Thread for {camera_name} died, restarting...")
                        new_thread = threading.Thread(
                            target=self.process_camera_stream,
                            args=(camera,),
                            daemon=True,
                            name=f"Worker-{camera_name}"
                        )
                        new_thread.start()
                        threads[i] = new_thread
        except KeyboardInterrupt:
            logger.info("\n✓ Video Worker stopped by user")
        except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(5)


if __name__ == "__main__":
    worker = VideoWorker()
    worker.run()
