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
from services import ppe_logic
from services.nx_witness import nx_client
from services.ptz_patrol import patrol
from integrations.evlos_client import evlos_client
from integrations.vlm_verifier import vlm_verifier


# F-002: MJPEG parsing hardening.
# Cap the receive buffer to avoid unbounded growth on malformed streams.
MJPEG_BUFFER_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# (connect_timeout, read_timeout): if no bytes arrive for read_timeout seconds
# the request raises ReadTimeout instead of blocking forever.
MJPEG_TIMEOUT = (10, 30)


def _extract_jpeg(buffer: bytes):
    """Try to extract one complete JPEG from `buffer`.

    Returns (jpeg_bytes_or_None, remaining_buffer).

    Defensive against:
    - EOI of a previous frame appearing before the next SOI in the buffer.
    - Buffer overflow (drop everything before the last SOI; full reset if no SOI).
    """
    a = buffer.find(b"\xff\xd8")  # SOI
    b = buffer.find(b"\xff\xd9")  # EOI

    if a != -1 and b != -1 and b > a:
        return buffer[a:b + 2], buffer[b + 2:]

    if a != -1 and b != -1 and b <= a:
        # EOI of a previous frame still in the buffer; drop up to it.
        return None, buffer[b + 2:]

    if len(buffer) > MJPEG_BUFFER_MAX_BYTES:
        last_soi = buffer.rfind(b"\xff\xd8")
        return None, (buffer[last_soi:] if last_soi != -1 else b"")

    return None, buffer


class CameraWorker:
    """Worker thread for a single camera"""

    def __init__(self, camera_id: str, camera_name: str, model, config: dict, model_lock=None, face_blurrer=None):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.model = model
        self.config = config
        self.model_lock = model_lock  # Lock for thread-safe CUDA inference
        self.face_blurrer = face_blurrer  # Shared FaceBlurrer (or None)
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.last_alert_time = 0
        self.running = False

        # Temporal N-of-M voting: a violation must persist across several
        # analyzed frames before it can alert (kills single-frame flicker).
        self._temporal = self._build_temporal_filter()
        # Per violation-type timestamp of the last alert, for re-alert pacing.
        self._last_type_alert = {}
        # Last mode actually run, to reset temporal voting on day/night flips.
        self._last_mode = None
        # Per-type: last frame that actually SHOWED each violation type
        # (evidence for alerts whose confirming frame happens to be clean).
        self._violation_evidence = {}
        # CUDA-OOM degrade ladder: caps inferenceSize after an OOM.
        self._imgsz_cap = None
        # Zoom-boost: densified sampling until this timestamp (set when a
        # large tracked person is in frame).
        self._boost_until = 0.0

        # Load detection configuration from database
        self.detection_config = db.get_camera_detection_config(camera_id)
        if not self.detection_config:
            # Default to intrusion mode with preset 1
            db.set_camera_detection_mode(camera_id, 'intrusion', 1)
            self.detection_config = db.get_camera_detection_config(camera_id)

        global_confidence = self.config.get('confidence', 0.5)
        logger.info(f"[{camera_name}] Detection mode: {self.detection_config.get('detection_mode', 'intrusion')}, Global confidence: {global_confidence}")

    def _cfg_float(self, key, default):
        """Read a float from hot-reloadable config; a typo must not crash."""
        try:
            return float(self.config.get(key, default))
        except (TypeError, ValueError):
            logger.warning(f"[{self.camera_name}] Invalid config value for "
                           f"'{key}': {self.config.get(key)!r}; using {default}")
            return float(default)

    def _cfg_int(self, key, default):
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            logger.warning(f"[{self.camera_name}] Invalid config value for "
                           f"'{key}': {self.config.get(key)!r}; using {default}")
            return int(default)

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

    def _build_temporal_filter(self):
        """Build the N-of-M temporal filter from config (with safe defaults)."""
        return ppe_logic.TemporalViolationFilter(
            window=self._cfg_int('temporalWindow', 5),
            min_hits=self._cfg_int('temporalMinHits', 3),
            max_age_seconds=self._cfg_float('temporalMaxAgeSeconds', 90.0),
        )

    def _run(self):
        """Main worker loop"""
        logger.info(f"[{self.camera_name}] Worker thread started")

        # Exponential backoff when the stream/inference dies immediately
        # after (re)connecting — e.g. a CUDA crash loop or a dead camera.
        # A run shorter than this counts as a failure.
        MIN_HEALTHY_RUN_SECONDS = 30
        consecutive_failures = 0

        while not self.stop_event.is_set():
            run_started = time.time()
            try:
                # Stream resolution: explicit "WxH" (per-camera override, else
                # global) requests NX's primary high-res stream; falls back to
                # the legacy quality preset. Re-read every reconnect so a
                # config change is picked up without a full restart.
                stream_quality = self.config.get("streamQuality", "medium")
                by_cam = self.config.get("streamResolutionByCamera", {})
                resolution = (by_cam.get(self.camera_name)
                              if isinstance(by_cam, dict) else None)
                resolution = resolution or self.config.get("streamResolution")
                stream_url = nx_client.get_stream_url(
                    self.camera_id, quality=stream_quality, resolution=resolution)
                self._process_stream(stream_url)
            except Exception as e:
                import traceback
                logger.error(f"[{self.camera_name}] Error in worker: {e}\n{traceback.format_exc()}")
                db.upsert_camera_status(
                    camera_id=self.camera_id,
                    camera_name=self.camera_name,
                    stream_connected=False
                )

            if self.stop_event.is_set():
                break

            if time.time() - run_started < MIN_HEALTHY_RUN_SECONDS:
                consecutive_failures += 1
            else:
                consecutive_failures = 0

            # 5s after a healthy run; 10s, 20s ... capped at 300s while broken.
            delay = min(300, 5 * (2 ** min(consecutive_failures, 6)))
            if consecutive_failures:
                logger.warning(
                    f"[{self.camera_name}] Stream died after "
                    f"{time.time() - run_started:.0f}s "
                    f"({consecutive_failures} consecutive failures); "
                    f"retrying in {delay}s"
                )
            # Wait before retry, but check stop_event frequently
            for _ in range(int(delay * 10)):
                if self.stop_event.is_set():
                    break
                time.sleep(0.1)

    def _process_stream(self, stream_url: str):
        """Process camera stream"""
        logger.info(f"[{self.camera_name}] Connecting to stream...")

        try:
            # Connect to stream (F-002: separate connect / read timeouts)
            response = requests.get(
                stream_url,
                auth=nx_client.auth,
                stream=True,
                timeout=MJPEG_TIMEOUT,
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

            for chunk in response.iter_content(chunk_size=4096):
                if self.stop_event.is_set():
                    logger.info(f"[{self.camera_name}] Stop requested, exiting stream")
                    return

                bytes_data += chunk

                # F-002: defensive JPEG extraction (handles EOI-before-SOI and overflow).
                jpg, bytes_data = _extract_jpeg(bytes_data)

                if jpg is not None:
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

                            # Frame sampling. During a zoom-boost window
                            # (large tracked person in view) we sample more
                            # densely: those are the best PPE frames. Never
                            # sample LESS densely than the configured rate.
                            effective_sampling = frame_sampling
                            if time.time() < self._boost_until:
                                effective_sampling = min(frame_sampling,
                                                         max(3, frame_sampling // 3))
                            if frame_count % max(1, effective_sampling) == 0:
                                self._process_frame(frame)
                    except cv2.error as e:
                        # Skip frame on OpenCV decode error to prevent crash
                        logger.warning(f"[{self.camera_name}] Frame decode error, skipping: {e}")
                        continue

        except requests.exceptions.ReadTimeout as e:
            # F-002: idle stream — treat like a normal disconnect, outer loop reconnects.
            logger.warning(f"[{self.camera_name}] Stream read timeout (no data for {MJPEG_TIMEOUT[1]}s): {e}")
            db.upsert_camera_status(self.camera_id, self.camera_name, stream_connected=False)
        except Exception as e:
            logger.error(f"[{self.camera_name}] Stream error: {e}")
            db.upsert_camera_status(self.camera_id, self.camera_name, stream_connected=False)

    def _class_confidence(self) -> dict:
        """Per-class thresholds: config.json overrides on top of defaults."""
        thresholds = dict(ppe_logic.DEFAULT_CLASS_CONFIDENCE)
        overrides = self.config.get('classConfidence', {})
        if isinstance(overrides, dict):
            for cls, value in overrides.items():
                try:
                    thresholds[cls] = float(value)
                except (TypeError, ValueError):
                    pass
        return thresholds

    def _effective_detection_mode(self) -> str:
        """Resolve the mode to run NOW for this camera.

        Cameras set to 'ppe' honour the global dual-mode schedule from
        config.json: PPE compliance during working hours, intrusion
        detection at night (a PPE model on dark/IR frames only produces
        noise, while any person at night IS the event of interest).
        """
        mode = self.detection_config.get('detection_mode', 'intrusion')
        if mode != 'ppe' or self.config.get('detectionMode') != 'dual':
            return mode
        schedule = self.config.get('schedule', {})
        try:
            day_start = int(schedule.get('dayStartHour', 6))
            day_end = int(schedule.get('dayEndHour', 18))
        except (TypeError, ValueError):
            return mode
        hour = datetime.now().hour
        if day_start <= day_end:
            is_day = day_start <= hour < day_end
        else:  # overnight window (e.g. 22 -> 6)
            is_day = hour >= day_start or hour < day_end
        return 'ppe' if is_day else 'intrusion'

    def _realert_seconds(self) -> float:
        """Re-alert pacing: per-camera override (by name) over the global."""
        overrides = self.config.get('realertOverrides', {})
        if isinstance(overrides, dict):
            value = overrides.get(self.camera_name)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
        return self._cfg_float('alertRealertSeconds', 120)

    def _process_frame(self, frame):
        """Process single frame with YOLO"""
        # Scene-aware patrol (PTZ orchestrated by services/ptz_patrol):
        # skip frames while the camera is moving between presets, and skip
        # PPE verdicts on scenes tagged no-PPE (parking, offices...). The
        # dual schedule still applies: at night those scenes run intrusion.
        scene = patrol.get_scene(self.camera_id)
        if scene and scene['in_transit']:
            return

        detection_mode = self._effective_detection_mode()
        if scene and scene['no_ppe'] and detection_mode == 'ppe':
            # Scene where PPE is not required: nothing to check by day.
            db.update_camera_detection(self.camera_id, 0)
            return

        # Reset temporal voting when the effective mode flips (day/night):
        # votes from the previous shift must not combine with fresh noise.
        if detection_mode != self._last_mode:
            if self._last_mode is not None:
                logger.info(f"[{self.camera_name}] Detection mode switch: "
                            f"{self._last_mode} -> {detection_mode}")
                self._temporal.reset()
                self._violation_evidence = {}
            self._last_mode = detection_mode

        # Inference threshold: in PPE mode run at the LOWEST per-class
        # threshold and post-filter per class (violation classes need much
        # stronger evidence than person/compliance classes). In intrusion
        # mode use the preset's confidence, falling back to the global one
        # (clamped: a stale low preset value must not open the floodgates).
        if detection_mode == 'ppe':
            confidence = min(self._class_confidence().values())
        else:
            try:
                preset_conf = float(self.detection_config.get('intrusion_confidence') or 0.0)
            except (TypeError, ValueError):
                preset_conf = 0.0
            confidence = preset_conf if preset_conf >= 0.4 else self._cfg_float('confidence', 0.5)

        # NO pre-resize: the frame goes to YOLO at native resolution and
        # ultralytics letterboxes it to imgsz. The old fixed 640x480 resize
        # both distorted the aspect ratio and destroyed the detail needed
        # to judge PPE on distant workers.
        imgsz = self._cfg_int('inferenceSize', 1280)
        if self._imgsz_cap:
            imgsz = min(imgsz, self._imgsz_cap)

        # Use lock for thread-safe CUDA inference. On CUDA OOM, degrade the
        # inference size (1280 -> 960 -> 640) instead of crash-looping.
        try:
            if self.model_lock:
                with self.model_lock:
                    results = self.model(frame, conf=confidence, imgsz=imgsz, verbose=False)
            else:
                results = self.model(frame, conf=confidence, imgsz=imgsz, verbose=False)
        except RuntimeError as e:
            if 'out of memory' in str(e).lower():
                new_cap = 960 if imgsz > 960 else 640
                if imgsz <= 640:
                    raise  # nothing left to degrade — surface the error
                self._imgsz_cap = new_cap
                logger.error(
                    f"[{self.camera_name}] CUDA OOM at imgsz={imgsz}; "
                    f"degrading inference size to {new_cap}. "
                    f"Consider lowering 'inferenceSize' in config.json."
                )
                return  # skip this frame; next one runs at the lower size
            raise
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

        # Smart dwell: keep the patrol from switching away while someone
        # is in view (night intrusion follows people too).
        if person_count > 0:
            patrol.report_person_seen(self.camera_id)

        # Check if alert should be triggered
        min_persons = self.detection_config.get('intrusion_min_persons', 1)
        alert_cooldown = self.detection_config.get('cooldown_seconds', 5)

        if person_count >= min_persons:
            self._trigger_alert(frame, boxes, person_count, 'intrusion', alert_cooldown)

    # Strict fluorescent hi-vis ranges in HSV (OpenCV H in [0,180]).
    # Deliberately NARROW: the previous broad ranges (red H0-25 + green up
    # to H95 at low saturation) matched rust, brick, vegetation and orange
    # barrier fencing, silently flipping REAL novest detections to 'vest'.
    HIVIS_COLOR_RANGES = {
        'orange': [((5, 120, 120), (20, 255, 255))],
        'yellow': [((20, 100, 140), (40, 255, 255))],
        'green': [((40, 100, 120), (75, 255, 255))],
        # Teal / cyan-green hi-vis vest (H 80-100, high sat): the wesjos model
        # does NOT recognize this colour as a vest and flags it 'novest'.
        # Measured on real Sessa frames (10/07): teal-vested torsos read
        # 0.49-0.73 teal while REAL violations read 0.00 and green FIELD
        # background reads as low-sat 'grassish' (H<75), so this range is a
        # clean, low-risk discriminator.
        'teal': [((80, 60, 60), (100, 255, 255))],
        'red': [((0, 140, 100), (5, 255, 255)),
                ((175, 140, 100), (180, 255, 255))],
    }

    # ROIs smaller than this cannot be judged by colour statistics.
    HIVIS_MIN_ROI_PIXELS = 400

    def _has_hivis_color(self, frame, box_xyxy, threshold=0.20, colors=None):
        """
        Check whether the TORSO region of the person box contains a
        meaningful fraction of FLUORESCENT hi-vis pixels. Used to override a
        confident 'novest' when the person is clearly wearing hi-vis of a
        colour the model doesn't recognize (e.g. teal vests).

        Strict by design: torso band only (central 20-65% of the box, where
        the vest is — excludes head, legs and most background), no ROI
        expansion — a wrong override here suppresses a REAL safety violation.

        Args:
            frame: BGR image (numpy array)
            box_xyxy: Bounding box coordinates [x1, y1, x2, y2]
            threshold: Minimum fraction of hi-vis pixels required
            colors: iterable of range names from HIVIS_COLOR_RANGES

        Returns:
            True if hi-vis colour covers at least `threshold` of the torso band
        """
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = map(int, box_xyxy)
        box_h = y2 - y1
        # Central torso band: the vest sits here; skip head and legs.
        ty1 = max(0, y1 + int(0.20 * box_h))
        ty2 = min(h, y1 + int(0.65 * box_h))
        x1, x2 = max(0, x1), min(w, x2)
        if x2 <= x1 or ty2 <= ty1:
            return False

        roi = frame[ty1:ty2, x1:x2]
        total_pixels = roi.shape[0] * roi.shape[1]
        if total_pixels < self.HIVIS_MIN_ROI_PIXELS:
            # Too small to judge by colour: leave the model's verdict alone.
            return False

        if not colors:
            colors = ('teal',)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hivis_pixels = 0
        for name in colors:
            for lower, upper in self.HIVIS_COLOR_RANGES.get(name, []):
                mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
                hivis_pixels += cv2.countNonZero(mask)

        ratio = hivis_pixels / total_pixels
        if ratio >= threshold:
            logger.info(
                f"[{self.camera_name}] Color override: {ratio:.1%} hi-vis "
                f"({','.join(colors)}) in torso {x2 - x1}x{ty2 - ty1} >= {threshold:.0%}"
            )
            return True
        logger.debug(
            f"[{self.camera_name}] No color override: {ratio:.1%} hi-vis "
            f"in torso {x2 - x1}x{ty2 - ty1} < {threshold:.0%}"
        )
        return False

    def _process_ppe_mode(self, frame, boxes):
        """Process frame in PPE detection mode.

        Decision logic lives in services/ppe_logic.py (pure, unit-tested):
          * violation boxes must be associated with a detected person;
          * persons too small in frame are not judged for PPE;
          * per-class confidence thresholds (violations need >= 0.80);
          * N-of-M temporal voting before any alert.
        """
        require_helmet = self.detection_config.get('ppe_require_helmet', True)
        require_vest = self.detection_config.get('ppe_require_vest', True)
        class_confidence = self._class_confidence()

        # The per-camera preset's ppe_confidence can only make violation
        # verdicts STRICTER than the global per-class thresholds.
        try:
            preset_conf = float(self.detection_config.get('ppe_confidence') or 0.0)
        except (TypeError, ValueError):
            preset_conf = 0.0
        for cls in ('novest', 'nohat'):
            class_confidence[cls] = max(class_confidence.get(cls, 0.80), preset_conf)

        # Canonicalize raw model detections.
        detections = []
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                raw_name = self.model.names[int(box.cls[0])]
                canon = ppe_logic.canonical_class(raw_name)
                if canon is None:
                    continue
                detections.append({
                    'cls_name': canon,
                    'conf': float(box.conf[0]),
                    'xyxy': box.xyxy[0].cpu().numpy(),
                })

        # Colour override: a CONFIDENT novest on someone visibly wearing
        # fluorescent hi-vis is reclassified as vest. DISABLED by default:
        # on real footage (backtest 07/07/2026, blind-judged) every strict
        # override killed a TRUE violation — orange shirts / hi-vis of
        # bystanders inside the novest box fool any colour statistic.
        override_cfg = self.config.get('vestColorOverride', {})
        if isinstance(override_cfg, dict) and override_cfg.get('enabled', False):
            try:
                override_threshold = float(override_cfg.get('threshold', 0.20))
            except (TypeError, ValueError):
                override_threshold = 0.20
            override_colors = override_cfg.get('colors')
            novest_conf = class_confidence.get('novest', 0.80)
            for det in detections:
                if det['cls_name'] == 'novest' and det['conf'] >= novest_conf:
                    if self._has_hivis_color(frame, det['xyxy'],
                                             threshold=override_threshold,
                                             colors=override_colors):
                        det['cls_name'] = 'vest'
                        det['color_override'] = True
                        logger.info(f"[{self.camera_name}] Color override: novest→vest")

        result = ppe_logic.evaluate_ppe(
            detections,
            frame.shape[0],
            class_confidence=class_confidence,
            min_person_height_ratio=self._cfg_float('minPersonHeightRatio', 0.06),
            require_helmet=require_helmet,
            require_vest=require_vest,
            model_class_names=list(self.model.names.values()),
        )

        db.update_camera_detection(self.camera_id, result['person_count'])

        # Smart dwell + zoom boost. A LARGE person box is the signature of
        # a firmware autotracking follow (Mobotix/AXIS zoom-and-track):
        # only that holds the patrol — small/distant persons are always
        # present on a busy site and must not stall the rotation. The same
        # signature densifies the sampling: those are the best PPE frames.
        person_boxes_all = [d for d in result['boxes'] if d['cls_name'] == 'person']
        if person_boxes_all:
            zoom_cfg = self.config.get('zoomBoost', {})
            if not isinstance(zoom_cfg, dict):
                zoom_cfg = {}
            try:
                ratio_thr = float(zoom_cfg.get('personHeightRatio', 0.35))
                boost_secs = float(zoom_cfg.get('seconds', 10))
            except (TypeError, ValueError):
                ratio_thr, boost_secs = 0.35, 10.0
            frame_h = float(frame.shape[0])
            has_large = any((d['xyxy'][3] - d['xyxy'][1]) >= ratio_thr * frame_h
                            for d in person_boxes_all)
            patrol.report_person_seen(self.camera_id, large=has_large)
            if has_large and zoom_cfg.get('enabled', True):
                self._boost_until = time.time() + boost_secs

        if detections:
            summary = ', '.join(f"{d['cls_name']}:{d['conf']:.1%}" for d in detections)
            logger.info(
                f"[{self.camera_name}] PPE detections: {summary} | "
                f"persons={result['person_count']} eligible={result['eligible_count']} "
                f"violations={sorted(result['violations'])} "
                f"ignored_bg={result['ignored_violations']}"
            )

        # Keep the most recent frame that actually SHOWED each violation
        # type, so an alert confirmed on a later (clean) frame still ships
        # real evidence (per-type: mixed-type scenes must not overwrite
        # each other's evidence).
        if result['violations']:
            evidence = (frame.copy(), result['boxes'])
            for viol_type in result['violations']:
                self._violation_evidence[viol_type] = evidence

        # Temporal N-of-M vote: only violations that persist across several
        # analyzed frames may alert.
        confirmed = self._temporal.update(result['violations'])
        if not confirmed:
            return

        # Re-alert pacing: one alert per violation type per realert window,
        # so a persistent violation reminds instead of flooding.
        now = time.time()
        realert_seconds = self._realert_seconds()
        due = sorted(
            t for t in confirmed
            if now - self._last_type_alert.get(t, 0.0) >= realert_seconds
        )
        if not due:
            return

        # Cooldown precheck BEFORE the (expensive) VLM call: _trigger_alert
        # would refuse anyway, and we must not spend seconds of VLM time on
        # an alert that cannot fire.
        alert_cooldown = self.detection_config.get('cooldown_seconds', 5)
        if now - self.last_alert_time < alert_cooldown:
            return

        # Evidence selection: if the confirming frame does not itself show
        # any due violation, fall back to the stored per-type evidence.
        alert_frame, alert_boxes = frame, result['boxes']
        if not (set(due) & result['violations']):
            for viol_type in due:
                stored = self._violation_evidence.get(viol_type)
                if stored:
                    alert_frame, alert_boxes = stored
                    break

        # Second-stage VLM (Qwen-VL via Ollama), fail-open. mode:
        #   "annotate" (default): attach the VLM's one-line description to
        #       the alert but NEVER suppress — measured on 55 live alerts,
        #       the 7B model is unreliable as a gate (says "vest present" on
        #       52/55, blind to real violations), so its verdict must not
        #       gatekeep safety. Precision is handled by minPersonHeightRatio.
        #   "veto": per-type three-way gate (kept for larger models / future).
        #   "off": skip the VLM entirely.
        # Zone suppression stays available but OFF by default (the PTZ preset
        # name is the authoritative zone signal; the VLM zone is fuzzy).
        vlm_note = None
        vlm_cfg = self.config.get('vlmVerifier', {})
        mode = vlm_cfg.get('mode', 'annotate') if isinstance(vlm_cfg, dict) else 'off'
        if isinstance(vlm_cfg, dict) and vlm_cfg.get('enabled', False) and mode != 'off':
            verdict = vlm_verifier.verify(alert_frame, due, vlm_cfg)
            if verdict is not None:
                vlm_note = verdict.get('description')
                suppress_zones = set(vlm_cfg.get('suppressZones', []))
                if suppress_zones and verdict.get('zone') in suppress_zones:
                    logger.info(f"[{self.camera_name}] VLM veto: zone "
                                f"'{verdict.get('zone')}' ({vlm_note or ''})"[:160])
                    for t in due:
                        self._last_type_alert[t] = now
                    return
                if mode == 'veto':
                    kept = [t for t in due if vlm_verifier.confirms(verdict, t)]
                    for t in [t for t in due if t not in kept]:
                        self._last_type_alert[t] = now
                    if not kept:
                        logger.info(f"[{self.camera_name}] VLM veto: "
                                    f"{[verdict.get('vest'), verdict.get('helmet')]} "
                                    f"({vlm_note or ''})"[:160])
                        return
                    due = kept
                vlm_note = verdict.get('description')

        fired = self._trigger_alert(
            alert_frame, None, result['person_count'], 'ppe_violation',
            alert_cooldown, due, alert_boxes, extra_note=vlm_note
        )
        if fired:
            for t in due:
                self._last_type_alert[t] = now

    def _trigger_alert(self, frame, boxes, person_count, alert_type, cooldown,
                       violations=None, processed_boxes=None, extra_note=None):
        """Trigger alert if cooldown period has passed. Returns True if fired."""
        current_time = time.time()

        if current_time - self.last_alert_time < cooldown:
            return False

        self.last_alert_time = current_time

        # Calculate confidence over the boxes that matter (persons + PPE),
        # not over raw model output (which includes irrelevant classes).
        if processed_boxes:
            confidences = [b.get('conf', 0.0) for b in processed_boxes]
        else:
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
            note = f" | {extra_note}" if extra_note else ""
            logger.info(f"[{self.camera_name}] PPE ALERT: {', '.join(violations)} "
                        f"- {person_count} person(s){note}")
        else:
            logger.info(f"[{self.camera_name}] INTRUSION ALERT: {person_count} person(s) detected")

        # Send to external systems (NxWitness, EVLOS)
        # Use cropped image for EVLOS if available, otherwise use annotated
        evlos_image_path = cropped_path if cropped_path else annotated_path
        self._send_external_alerts(boxes, person_count, avg_conf, evlos_image_path,
                                   alert_type, processed_boxes, extra_note)
        return True

    def _send_external_alerts(self, boxes, person_count, avg_conf, annotated_path,
                              alert_type, processed_boxes=None, extra_note=None):
        """Send alerts to external systems (NxWitness, EVLOS)"""
        # Send alert to NxWitness if enabled
        nx_alerts_config = self.config.get("nxWitnessAlerts", {})
        if nx_alerts_config.get("enabled", False):
            logger.info(f"[{self.camera_name}] NxWitness alerts enabled, sending HTTP alert...")
            try:
                # Prepare bounding boxes data. Prefer the processed boxes
                # (per-class filtered, colour-override corrected) over raw
                # model output, which includes sub-threshold noise.
                boxes_data = []
                if processed_boxes:
                    for b in processed_boxes:
                        x1, y1, x2, y2 = map(float, b['xyxy'])
                        boxes_data.append({
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "confidence": float(b.get('conf', 0.0)),
                            "class": b.get('cls_name', 'unknown')
                        })
                elif boxes is not None and len(boxes) > 0:
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
                        image_path=annotated_path,
                        note=extra_note
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

        # Cap the evidence resolution: frames are native-res now (no more
        # 640x480 pre-resize) and 3 JPEGs are written per alert. 1920 wide
        # keeps them readable without bloating disk/EVLOS uploads.
        # Boxes are scaled accordingly.
        max_width = 1920
        frame_h, frame_w = frame.shape[:2]
        scale = 1.0
        if frame_w > max_width:
            scale = max_width / frame_w
            frame = cv2.resize(frame, (max_width, int(frame_h * scale)))
        else:
            # Never mutate the caller's frame in place (evidence frame reuse).
            frame = frame.copy()

        # Face-only anonymization: pixelate detected faces BEFORE any image
        # is written, so full / annotated / cropped all inherit it. Only the
        # face is obscured — helmet, vest and body stay visible. Runs on a
        # copy; the detection frame is untouched.
        face_cfg = self.config.get('faceBlur', {})
        if self.face_blurrer is not None and (not isinstance(face_cfg, dict)
                                              or face_cfg.get('enabled', True)):
            try:
                person_boxes = [
                    [c * scale for c in b['xyxy']]
                    for b in (processed_boxes or [])
                    if b.get('cls_name') == 'person'
                ]
                n_faces = self.face_blurrer.blur_faces(frame, person_boxes=person_boxes)
                if n_faces:
                    logger.info(f"[{self.camera_name}] Face blur: {n_faces} face(s) obscured")
            except Exception as e:
                logger.warning(f"[{self.camera_name}] Face blur failed: {e}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        camera_safe_name = self.camera_name.replace(' ', '_').replace('/', '_')

        # Save full frame (faces blurred, no annotation boxes)
        full_filename = f"{camera_safe_name}_{timestamp}_full.jpg"
        full_path = alerts_dir / full_filename
        cv2.imwrite(str(full_path), frame)

        # Save annotated image
        annotated_path = None
        cropped_path = None

        # Use processed_boxes if available (per-class filtered, corrected
        # cls_name after colour override) — both for the crop region and the
        # annotations. Raw output includes sub-threshold noise that would
        # stretch the crop to irrelevant regions.
        if processed_boxes:
            boxes_to_draw = processed_boxes
        elif boxes is not None and len(boxes) > 0:
            boxes_to_draw = [
                {
                    'xyxy': box.xyxy[0].cpu().numpy(),
                    'conf': float(box.conf[0]),
                    'cls_name': self.model.names[int(box.cls[0])]
                }
                for box in boxes
            ]
        else:
            boxes_to_draw = []

        if boxes_to_draw:
            # Calculate bounding box that contains all drawn detections
            # (coordinates scaled to the possibly-downscaled evidence frame)
            all_x1, all_y1, all_x2, all_y2 = [], [], [], []
            for box_data in boxes_to_draw:
                x1, y1, x2, y2 = (int(v * scale) for v in box_data['xyxy'])
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

            for box_data in boxes_to_draw:
                xyxy = box_data.get('xyxy')
                if xyxy is None:
                    continue
                x1, y1, x2, y2 = (int(v * scale) for v in xyxy)
                conf = box_data.get('conf', 0.0)
                cls_name = box_data.get('cls_name', 'unknown')

                # Get color for this class (default to white if not found)
                color = color_map.get(cls_name.lower(), (255, 255, 255))

                # Draw rectangle with thickness=2
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

                # Draw label with matching color ('*' marks a colour override)
                override_mark = '*' if box_data.get('color_override') else ''
                label = f"{cls_name}{override_mark} {conf:.2f}"
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
        self.face_blurrer = None  # Shared FaceBlurrer for alert-screenshot anonymization

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

        # Initialize the shared face blurrer for alert-screenshot privacy.
        face_cfg = self.config.get('faceBlur', {})
        if not isinstance(face_cfg, dict) or face_cfg.get('enabled', True):
            from services.face_blur import FaceBlurrer
            self.face_blurrer = FaceBlurrer(
                model_path=face_cfg.get('modelPath') if isinstance(face_cfg, dict) else None,
                score_threshold=float(face_cfg.get('scoreThreshold', 0.6)) if isinstance(face_cfg, dict) else 0.6,
                blocks=int(face_cfg.get('blocks', 10)) if isinstance(face_cfg, dict) else 10,
                expand=float(face_cfg.get('expand', 0.15)) if isinstance(face_cfg, dict) else 0.15,
            )
        else:
            logger.info("Face blur disabled by config")

        self._initialized = True
        logger.info("Video Worker Manager initialized")

        # Auto-start workers for cameras that were enabled before shutdown
        self._restore_worker_states()

    # Supervisor: how long to wait after revive before judging the new thread alive.
    WORKER_REVIVE_PROBE_SECONDS = 1.0

    def _start_worker_for_camera(self, camera_id: str, camera_name: str) -> CameraWorker:
        """Build and start one CameraWorker. Registers it under self.workers.
        Does NOT touch db.set_camera_enabled — callers handle persistence."""
        worker = CameraWorker(camera_id, camera_name, self.model, self.config,
                              self.model_lock, getattr(self, 'face_blurrer', None))
        self.workers[camera_id] = worker
        worker.start()
        return worker

    def start_worker(self, camera_id: str, camera_name: str) -> bool:
        """Start worker for a camera"""
        if not self._initialized:
            self.initialize()

        # Stop existing worker if running
        if camera_id in self.workers:
            self.workers[camera_id].stop()

        worker = self._start_worker_for_camera(camera_id, camera_name)
        success = worker.running

        # Save enabled state to database for persistence
        if success:
            db.set_camera_enabled(camera_id, True)

        return success

    def supervise(self) -> Dict:
        """Check liveness of every managed worker thread; revive dead ones.

        Returns a dict {alive: [ids], revived: [ids], still_dead: [ids]}.
        - 'alive' covers workers whose thread.is_alive() at entry.
        - 'revived' covers workers whose thread was dead but a fresh thread
           is running after a brief probe.
        - 'still_dead' covers workers where revival failed or the new thread
           is also dead. The original (dead) entry is left in place; the
           next pass will retry.
        """
        result = {"alive": [], "revived": [], "still_dead": []}

        # Snapshot keys to avoid concurrent-modification surprises.
        for camera_id in list(self.workers.keys()):
            worker = self.workers.get(camera_id)
            if worker is None:
                continue

            thread = getattr(worker, "thread", None)
            if thread is not None and thread.is_alive():
                result["alive"].append(camera_id)
                continue

            # Thread is dead. Revive.
            camera_name = getattr(worker, "camera_name", camera_id)
            thread_name = getattr(thread, "name", "?")
            logger.warning(
                f"Supervisor: worker for camera {camera_id} died "
                f"(thread {thread_name}); reviving"
            )
            try:
                try:
                    worker.stop()
                except Exception:
                    pass
                new_worker = self._start_worker_for_camera(camera_id, camera_name)
                time.sleep(self.WORKER_REVIVE_PROBE_SECONDS)
                new_thread = getattr(new_worker, "thread", None)
                if new_thread is not None and new_thread.is_alive():
                    result["revived"].append(camera_id)
                else:
                    result["still_dead"].append(camera_id)
                    logger.error(
                        f"Supervisor: revival of {camera_id} failed "
                        f"(new thread is also dead)"
                    )
            except Exception as e:
                logger.error(f"Supervisor: revival of {camera_id} raised: {e}")
                result["still_dead"].append(camera_id)

        return result

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
                # Rebuild the temporal filter if its parameters changed
                # (resets the voting window, which is fine on a config change).
                new_temporal = worker._build_temporal_filter()
                if (new_temporal.window != worker._temporal.window
                        or new_temporal.min_hits != worker._temporal.min_hits):
                    worker._temporal = new_temporal
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
                    worker = self._start_worker_for_camera(camera_id, camera_name)
                    success = worker.running

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
