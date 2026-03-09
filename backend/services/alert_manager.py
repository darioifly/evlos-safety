"""
Alert Management with Cooldown and Buffering
"""
import time
import threading
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime
import numpy as np

from config import settings
from utils.logger import logger
from utils.metrics import metrics
from services.nx_witness import nx_client
from utils.screenshot import save_detection_screenshot, cleanup_old_screenshots
from database.db_manager import db
from integrations.evlos_client import evlos_client


class AlertManager:
    """Manage alerts with cooldown, buffering, and retry logic"""

    def __init__(self):
        self.cooldown = settings.ALERT_COOLDOWN_SECONDS
        self.min_persons = settings.MIN_PERSONS_FOR_ALERT
        self.max_buffer_size = settings.MAX_ALERT_BUFFER

        # Tracking
        self.last_alert_time: Dict[str, float] = {}
        self.alert_buffer: deque = deque(maxlen=self.max_buffer_size)
        self.alert_history: deque = deque(maxlen=1000)

        # Camera metadata (will be populated externally)
        self.camera_names: Dict[str, str] = {}
        self.camera_locations: Dict[str, str] = {}
        self.camera_zones: Dict[str, str] = {}

        # Thread safety
        self.lock = threading.Lock()

        # Retry thread
        self.retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
        self.retry_thread.start()

        # Cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        logger.info(f"AlertManager initialized (cooldown={self.cooldown}s, min_persons={self.min_persons})")

    def should_alert(self, camera_id: str, person_count: int) -> bool:
        """
        Check if alert should be triggered

        Args:
            camera_id: Camera identifier
            person_count: Number of persons detected

        Returns:
            True if alert should be sent
        """
        # Check person count threshold
        if person_count < self.min_persons:
            return False

        # Check cooldown
        with self.lock:
            current_time = time.time()
            last_alert = self.last_alert_time.get(camera_id, 0)

            if (current_time - last_alert) >= self.cooldown:
                self.last_alert_time[camera_id] = current_time
                return True

        return False

    def send_alert(self, camera_id: str, person_count: int, confidence: float,
                   frame: np.ndarray = None, boxes: List[Dict] = None) -> bool:
        """
        Send alert to NxWitness with screenshot and bookmark

        Args:
            camera_id: Camera identifier
            person_count: Number of persons detected
            confidence: Detection confidence
            frame: Numpy array of the frame (optional)
            boxes: List of bounding box dictionaries (optional)

        Returns:
            True if alert sent successfully
        """
        timestamp = time.time()

        logger.info(f"[ALERT MANAGER] send_alert() called for camera {camera_id}")
        logger.info(f"[ALERT MANAGER] Persons: {person_count}, Confidence: {confidence:.2%}")
        logger.info(f"[ALERT MANAGER] Frame provided: {frame is not None}, Boxes count: {len(boxes) if boxes else 0}")

        # Calculate alert level
        alert_level = self._calculate_alert_level(person_count, confidence)
        logger.info(f"[ALERT MANAGER] Calculated alert level: {alert_level.upper()}")

        # Save screenshot if frame provided
        screenshot_path = None
        if frame is not None and boxes:
            screenshot_path = save_detection_screenshot(frame, boxes, camera_id, timestamp)

        # Prepare camera metadata
        camera_metadata = {
            "name": self.camera_names.get(camera_id, camera_id),
            "location": self.camera_locations.get(camera_id, "Unknown"),
            "zone": self.camera_zones.get(camera_id, "Unknown")
        }

        # Prepare rich metadata
        metadata = {
            "alertLevel": alert_level,
            "cameraMetadata": camera_metadata,
            "screenshotPath": screenshot_path,
            "timestamp": timestamp
        }

        alert_data = {
            'cameraId': camera_id,
            'persons': person_count,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'boxes': boxes if boxes else [],
            'screenshot': screenshot_path,
            'alertLevel': alert_level,
            'retry_count': 0,
            'eventSent': False,
            'bookmarkCreated': False
        }

        try:
            # 1. Send Generic Event with rich metadata
            event_success = nx_client.send_alert(
                camera_id, person_count, confidence,
                boxes=boxes, metadata=metadata
            )

            alert_data['eventSent'] = event_success

            # 2. Create Bookmark for video timeline
            bookmark_success = False
            if event_success:
                bookmark_success = nx_client.create_bookmark(
                    camera_id=camera_id,
                    name=f"Person Detection - {person_count} person(s) [{alert_level.upper()}]",
                    duration_seconds=settings.ALERT_BOOKMARK_DURATION_SECONDS,
                    tags={
                        "persons": str(person_count),
                        "confidence": f"{confidence:.2f}",
                        "alertLevel": alert_level
                    },
                    timestamp=timestamp
                )
                alert_data['bookmarkCreated'] = bookmark_success

            if event_success:
                # Add to history
                with self.lock:
                    self.alert_history.append(alert_data)
                metrics.record_alert(camera_id)

                bookmark_status = "✓" if bookmark_success else "✗"
                logger.info(
                    f"Alert sent [{alert_level.upper()}]: {camera_id} - "
                    f"{person_count} persons ({confidence:.2%}) "
                    f"[Event: ✓, Bookmark: {bookmark_status}]"
                )

                # Send to EVLOS if enabled (async, non-blocking)
                if evlos_client.enabled and screenshot_path:
                    evlos_client.send_alert_async(
                        image_data=screenshot_path,
                        camera_id=camera_id,
                        alert_type='person_detection',
                        person_count=person_count,
                        severity=alert_level,
                        confidence=confidence,
                        timestamp=datetime.fromtimestamp(timestamp)
                    )
                    logger.info(f"EVLOS alert queued for {camera_id}")

                return True
            else:
                # Buffer for retry
                with self.lock:
                    self.alert_buffer.append(alert_data)
                logger.warning(f"Alert buffered for retry: {camera_id}")
                return False

        except Exception as e:
            logger.error(f"Error sending alert for {camera_id}: {e}")
            # Buffer for retry
            with self.lock:
                self.alert_buffer.append(alert_data)
            return False

    def _calculate_alert_level(self, person_count: int, confidence: float) -> str:
        """
        Calculate alert priority level

        Args:
            person_count: Number of persons detected
            confidence: Detection confidence

        Returns:
            Alert level: "low", "medium", "high", "critical"
        """
        if person_count >= 5 or (person_count >= 3 and confidence >= 0.9):
            return "critical"
        elif person_count >= 3 or (person_count >= 2 and confidence >= 0.85):
            return "high"
        elif person_count >= 2 or confidence >= 0.75:
            return "medium"
        else:
            return "low"

    def _retry_loop(self):
        """Background thread to retry failed alerts"""
        while True:
            try:
                time.sleep(settings.ALERT_RETRY_DELAY)

                with self.lock:
                    if not self.alert_buffer:
                        continue

                    # Get next alert to retry
                    alert = self.alert_buffer.popleft()

                # Retry sending
                success = nx_client.send_alert(
                    alert['cameraId'],
                    alert['persons'],
                    alert['confidence']
                )

                if success:
                    with self.lock:
                        self.alert_history.append(alert)
                    metrics.record_alert(alert['cameraId'])
                    logger.info(f"Retried alert sent successfully: {alert['cameraId']}")
                else:
                    # Put back in buffer if not too old (max 5 minutes)
                    alert['retry_count'] += 1
                    if alert['retry_count'] < 10:
                        with self.lock:
                            self.alert_buffer.append(alert)
                        logger.debug(f"Alert re-queued for retry (attempt {alert['retry_count']})")
                    else:
                        logger.warning(f"Alert dropped after max retries: {alert['cameraId']}")

            except Exception as e:
                logger.error(f"Error in alert retry loop: {e}")
                time.sleep(1)

    def process_detection(self, detection: Dict, frame: np.ndarray = None) -> Optional[Dict]:
        """
        Process detection result and send alert if needed

        Args:
            detection: Detection result from detector (includes boxes, alert_type, detection_mode)
            frame: Numpy array of the frame (optional)

        Returns:
            Alert data if sent, None otherwise
        """
        import os
        camera_id = detection['camera_id']
        person_count = detection['person_count']
        confidence = detection['confidence']
        boxes = detection.get('boxes', [])
        alert_type = detection.get('alert_type')  # 'intrusion', 'ppe_violation', or None
        detection_mode = detection.get('detection_mode', 'intrusion')
        ppe_violations = detection.get('ppe_violations', [])

        logger.debug(f"[ALERT MANAGER] process_detection() called for {camera_id}: mode={detection_mode}, alert_type={alert_type}, persons={person_count}")

        # If worker already determined no alert needed, skip
        if alert_type is None:
            return None

        # Get camera detection config for cooldown
        camera_config = db.get_camera_detection_config(camera_id)
        cooldown = camera_config.get('cooldown_seconds', self.cooldown) if camera_config else self.cooldown

        # Check cooldown
        with self.lock:
            current_time = time.time()
            last_alert = self.last_alert_time.get(camera_id, 0)
            if (current_time - last_alert) < cooldown:
                logger.debug(f"[ALERT MANAGER] Camera {camera_id} in cooldown ({cooldown}s)")
                return None
            self.last_alert_time[camera_id] = current_time

        # Log alert type
        if alert_type == 'intrusion':
            logger.info(f"[ALERT MANAGER] ✅ INTRUSION alert for {camera_id}: {person_count} persons @ {confidence:.2%}")
        elif alert_type == 'ppe_violation':
            violations_str = ', '.join(ppe_violations) if ppe_violations else 'unknown'
            logger.info(f"[ALERT MANAGER] ✅ PPE VIOLATION alert for {camera_id}: {violations_str}")

        # If we reach here, alert should be sent

        # Save screenshot if frame provided
        screenshot_path = None
        if frame is not None and boxes:
            timestamp = time.time()
            screenshot_path = save_detection_screenshot(frame, boxes, camera_id, timestamp)

        # Send alert to NX Witness
        self.send_alert(camera_id, person_count, confidence, frame=frame, boxes=boxes)

        # Convert absolute screenshot path to HTTP-accessible path
        http_screenshot_path = None
        if screenshot_path:
            # Get relative path from screenshots directory
            try:
                screenshot_dir = settings.ALERT_SCREENSHOT_DIR
                rel_path = os.path.relpath(screenshot_path, screenshot_dir)
                # Convert to HTTP path (use forward slashes)
                http_screenshot_path = f"/screenshots/{rel_path.replace(os.sep, '/')}"
            except Exception as e:
                logger.error(f"Error converting screenshot path: {e}")

        # Get camera name
        camera_name = self.camera_names.get(camera_id, camera_id)

        # Save alert to database
        try:
            alert_id = db.insert_alert(
                camera_id=camera_id,
                camera_name=camera_name,
                person_count=person_count,
                avg_confidence=confidence,
                full_image_path=http_screenshot_path,
                cropped_image_path=http_screenshot_path
            )
            logger.info(f"[ALERT MANAGER] 💾 Alert saved to database with ID: {alert_id}")
        except Exception as e:
            logger.error(f"[ALERT MANAGER] ❌ Failed to save alert to database: {e}")

        return {
            'camera_id': camera_id,  # Frontend expects camera_id
            'camera_name': camera_name,  # Add camera name
            'person_count': person_count,  # Frontend expects person_count
            'avg_confidence': confidence,  # Frontend expects avg_confidence
            'boxes': boxes,
            'timestamp': datetime.now().isoformat(),
            'alertLevel': self._calculate_alert_level(person_count, confidence),
            'full_image_path': http_screenshot_path,  # Add image path
            'cropped_image_path': http_screenshot_path  # Use same image for both (annotated)
        }

    def _cleanup_loop(self):
        """Background thread to cleanup old screenshots"""
        while True:
            try:
                # Run cleanup once per day (86400 seconds)
                time.sleep(86400)

                deleted_count = cleanup_old_screenshots()
                if deleted_count > 0:
                    logger.info(f"Screenshot cleanup completed: {deleted_count} files removed")

            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                time.sleep(3600)  # Retry after 1 hour on error

    def set_camera_metadata(self, camera_names: Dict[str, str] = None,
                           camera_locations: Dict[str, str] = None,
                           camera_zones: Dict[str, str] = None):
        """
        Update camera metadata

        Args:
            camera_names: Dictionary mapping camera IDs to names
            camera_locations: Dictionary mapping camera IDs to locations
            camera_zones: Dictionary mapping camera IDs to zones
        """
        if camera_names:
            self.camera_names = camera_names
        if camera_locations:
            self.camera_locations = camera_locations
        if camera_zones:
            self.camera_zones = camera_zones

        logger.info(f"Camera metadata updated: {len(self.camera_names)} names, "
                   f"{len(self.camera_locations)} locations, {len(self.camera_zones)} zones")

    def get_history(self, limit: int = 100, camera_id: str = None) -> List[Dict]:
        """
        Get alert history

        Args:
            limit: Maximum number of alerts to return
            camera_id: Filter by camera ID (optional)

        Returns:
            List of alert dictionaries
        """
        with self.lock:
            history = list(self.alert_history)

        # Filter by camera if specified
        if camera_id:
            history = [a for a in history if a['cameraId'] == camera_id]

        # Return most recent alerts
        return history[-limit:]

    def get_buffer_status(self) -> Dict:
        """Get current buffer status"""
        with self.lock:
            return {
                'buffered_alerts': len(self.alert_buffer),
                'total_alerts': len(self.alert_history),
                'buffer_capacity': self.max_buffer_size
            }

    def update_config(self, cooldown: int = None, min_persons: int = None):
        """Update alert configuration"""
        if cooldown is not None:
            self.cooldown = cooldown
            logger.info(f"Alert cooldown updated to {cooldown}s")

        if min_persons is not None:
            self.min_persons = min_persons
            logger.info(f"Minimum persons threshold updated to {min_persons}")


# Global alert manager instance
alert_manager = AlertManager()
