"""
EVLOS Integration Client
Sends anomaly alerts to external EVLOS platform via HTTP API
"""
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Union
from concurrent.futures import ThreadPoolExecutor
import requests

from config import settings
from utils.logger import logger


class EVLOSClient:
    """
    Client for sending alerts to EVLOS platform

    Features:
    - Async sending with ThreadPoolExecutor
    - Retry logic with exponential backoff
    - Local fallback storage for failed alerts
    - Configurable via settings
    """

    def __init__(self):
        self.api_url = getattr(settings, 'EVLOS_API_URL', 'http://192.168.1.50:8000/api/v1/alerts/upload')
        self.enabled = getattr(settings, 'EVLOS_ENABLED', False)
        self.timeout = getattr(settings, 'EVLOS_TIMEOUT', 10)
        self.max_retries = getattr(settings, 'EVLOS_MAX_RETRIES', 3)
        self.failed_dir = Path(getattr(settings, 'EVLOS_FAILED_DIR', 'data/evlos_failed_alerts'))

        # Thread pool for async sending
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="evlos")

        # Ensure failed alerts directory exists
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        
        # Camera ID mapping (NxWitness -> EVLOS)
        self.camera_mapping = getattr(settings, 'EVLOS_CAMERA_MAPPING', {})

        # Mapping from internal event types to EVLOS alert types
        self.alert_type_mapping = {
            # Note: person_detection uses smart mapping based on person_count
            'person_intrusion': 'intrusion',
            'helmet_missing': 'no_ppe',
            'vest_missing': 'no_ppe',
            'ppe_missing': 'no_ppe',
            'no_ppe': 'no_ppe',  # Direct mapping for pre-mapped PPE violations
            'ppe_violation': 'no_ppe',  # Alternative naming
            'person_fall': 'fall_detection',
            'fall_detection': 'fall_detection',
            'unauthorized_vehicle': 'vehicle',
            'vehicle_detection': 'vehicle',
            'fire_detection': 'fire',
            'smoke_detection': 'fire',
            'zone_violation': 'zone_violation',
            'crowd_detection': 'crowd',
            'loitering': 'loitering',
            'intrusion': 'intrusion',  # Direct mapping
            'crowd': 'crowd',  # Direct mapping
            'vehicle': 'vehicle',  # Direct mapping
            'fire': 'fire',  # Direct mapping
        }

        logger.info(f"EVLOS Client initialized (enabled={self.enabled}, url={self.api_url})")

    def map_alert_type(self, internal_type: str, person_count: int = 1) -> str:
        """
        Map internal event type to EVLOS alert_type

        Args:
            internal_type: Internal event type string
            person_count: Number of persons detected (for smart mapping)

        Returns:
            EVLOS alert_type string
        """
        # Check explicit mapping first
        if internal_type in self.alert_type_mapping:
            return self.alert_type_mapping[internal_type]

        # Smart mapping based on person count for generic person_detection
        if internal_type == 'person_detection':
            if person_count >= 3:
                return 'crowd'
            else:
                return 'intrusion'

        # Default to "other" for unmapped types
        logger.warning(f"Unknown event type '{internal_type}', mapping to 'other'")
        return 'other'

    def map_severity(self, alert_level: str) -> str:
        """
        Map internal alert level to EVLOS severity

        Args:
            alert_level: Internal alert level (low/medium/high/critical)

        Returns:
            EVLOS severity string
        """
        severity_map = {
            'low': 'low',
            'medium': 'medium',
            'high': 'high',
            'critical': 'critical'
        }
        return severity_map.get(alert_level.lower(), 'medium')

    def send_alert(self,
                   image_data: Union[bytes, str, Path],
                   camera_id: str,
                   alert_type: str = 'person_detection',
                   person_count: int = 1,
                   severity: str = 'medium',
                   confidence: float = None,
                   timestamp: datetime = None) -> Dict:
        """
        Send alert to EVLOS (with retry logic)

        Args:
            image_data: Image as bytes, file path, or Path object
            camera_id: Camera UUID string
            alert_type: Internal alert type (will be mapped to EVLOS type)
            person_count: Number of persons (used for smart mapping)
            severity: Alert severity (low/medium/high/critical)
            confidence: AI confidence score (0.0-1.0)
            timestamp: Event timestamp (default: now)

        Returns:
            dict: {
                'success': bool,
                'alert_id': str or None,
                'error': str or None
            }
        """
        if not self.enabled:
            logger.debug("EVLOS disabled, skipping alert send")
            return {'success': False, 'alert_id': None, 'error': 'EVLOS disabled'}

        # Map internal type to EVLOS type
        evlos_alert_type = self.map_alert_type(alert_type, person_count)

        # Use current timestamp if not provided
        if timestamp is None:
            timestamp = datetime.now()

        # Format timestamp as ISO 8601
        timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f')

        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self._send_request(
                    image_data=image_data,
                    camera_id=camera_id,
                    alert_type=evlos_alert_type,
                    severity=severity,
                    confidence=confidence,
                    timestamp_str=timestamp_str
                )

                if result['success']:
                    logger.info(f"EVLOS alert sent successfully: {evlos_alert_type} from {camera_id} (alert_id={result['alert_id']})")
                    return result
                else:
                    last_error = result['error']

                    # Don't retry on client errors (4xx)
                    if result.get('status_code') and 400 <= result['status_code'] < 500:
                        logger.error(f"EVLOS client error (no retry): {last_error}")
                        break

            except Exception as e:
                last_error = str(e)
                logger.warning(f"EVLOS send attempt {attempt}/{self.max_retries} failed: {last_error}")

            # Exponential backoff before retry (2s, 4s, 8s)
            if attempt < self.max_retries:
                delay = 2 ** attempt
                logger.info(f"Retrying EVLOS send in {delay}s...")
                time.sleep(delay)

        # All retries failed - save to local fallback
        logger.error(f"EVLOS send permanently failed after {self.max_retries} attempts: {last_error}")
        self._save_failed_alert(
            image_data=image_data,
            camera_id=camera_id,
            alert_type=evlos_alert_type,
            severity=severity,
            confidence=confidence,
            timestamp=timestamp,
            error=last_error
        )

        return {
            'success': False,
            'alert_id': None,
            'error': f'Failed after {self.max_retries} retries: {last_error}'
        }

    def _send_request(self,
                      image_data: Union[bytes, str, Path],
                      camera_id: str,
                      alert_type: str,
                      severity: str,
                      confidence: float,
                      timestamp_str: str,
                      timeout: Optional[float] = None) -> Dict:
        """
        Execute HTTP request to EVLOS API

        Returns:
            dict with success, alert_id, error, status_code
        """
        # Prepare image file
        if isinstance(image_data, bytes):
            # Image already as bytes
            image_bytes = image_data
            filename = f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{alert_type}.jpg"
        elif isinstance(image_data, (str, Path)):
            # Read from file path
            file_path = Path(image_data)
            if not file_path.exists():
                return {
                    'success': False,
                    'alert_id': None,
                    'error': f'Image file not found: {file_path}',
                    'status_code': None
                }

            with open(file_path, 'rb') as f:
                image_bytes = f.read()

            # Use actual filename
            filename = file_path.name
        else:
            return {
                'success': False,
                'alert_id': None,
                'error': 'Invalid image_data type (must be bytes, str, or Path)',
                'status_code': None
            }

        # Prepare multipart form data
        files = {
            'file': (filename, image_bytes, 'image/jpeg')
        }

        data = {
            'camera_id': camera_id,
            'alert_type': alert_type,
            'timestamp': timestamp_str,
            'severity': severity,
        }

        # Add confidence if provided
        if confidence is not None:
            data['confidence'] = str(confidence)

        # Send POST request
        try:
            response = requests.post(
                self.api_url,
                files=files,
                data=data,
                timeout=timeout if timeout is not None else self.timeout
            )

            status_code = response.status_code

            if status_code == 200:
                # Success
                try:
                    response_data = response.json()
                    alert_id = response_data.get('alert_id', 'unknown')
                    return {
                        'success': True,
                        'alert_id': alert_id,
                        'error': None,
                        'status_code': status_code
                    }
                except json.JSONDecodeError:
                    # Success but invalid JSON response
                    return {
                        'success': True,
                        'alert_id': 'unknown',
                        'error': None,
                        'status_code': status_code
                    }
            else:
                # HTTP error
                error_msg = f"HTTP {status_code}: {response.text[:200]}"
                return {
                    'success': False,
                    'alert_id': None,
                    'error': error_msg,
                    'status_code': status_code
                }

        except requests.Timeout:
            return {
                'success': False,
                'alert_id': None,
                'error': f'Request timeout after {self.timeout}s',
                'status_code': None
            }
        except requests.ConnectionError as e:
            return {
                'success': False,
                'alert_id': None,
                'error': f'Connection error: {e}',
                'status_code': None
            }
        except Exception as e:
            return {
                'success': False,
                'alert_id': None,
                'error': f'Unexpected error: {e}',
                'status_code': None
            }

    def _save_failed_alert(self,
                          image_data: Union[bytes, str, Path],
                          camera_id: str,
                          alert_type: str,
                          severity: str,
                          confidence: float,
                          timestamp: datetime,
                          error: str):
        """
        Save failed alert to local directory for later manual/automatic retry

        Saves:
        - Image file: YYYYMMDD_HHMMSS_{alert_type}.jpg
        - Metadata JSON: YYYYMMDD_HHMMSS_{alert_type}.json
        """
        try:
            # Generate filename prefix
            filename_prefix = timestamp.strftime('%Y%m%d_%H%M%S') + f"_{alert_type}"

            # Save image
            image_path = self.failed_dir / f"{filename_prefix}.jpg"
            if isinstance(image_data, bytes):
                with open(image_path, 'wb') as f:
                    f.write(image_data)
            elif isinstance(image_data, (str, Path)):
                # Copy file
                source_path = Path(image_data)
                if source_path.exists():
                    with open(source_path, 'rb') as src:
                        with open(image_path, 'wb') as dst:
                            dst.write(src.read())
                else:
                    logger.error(f"Cannot save failed alert: source image not found: {source_path}")
                    return

            # Save metadata JSON
            metadata = {
                'camera_id': camera_id,
                'alert_type': alert_type,
                'severity': severity,
                'confidence': confidence,
                'timestamp': timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                'error': error,
                'api_url': self.api_url,
                'saved_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            }

            json_path = self.failed_dir / f"{filename_prefix}.json"
            with open(json_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Failed alert saved to {self.failed_dir}: {filename_prefix}")

        except Exception as e:
            logger.error(f"Error saving failed alert to disk: {e}")

    # F-010: drain spool of failed alerts.
    # Per safety policy: a spool file is only deleted on a 2xx response.
    # On any non-2xx or transport error the file stays in place.
    # Corrupt JSON sidecars are renamed to *.json.poison so the drainer does
    # not loop on them.
    DRAIN_TIMEOUT_SECONDS = 5

    def drain_failed_alerts(self, max_per_pass: int = 10) -> Dict:
        """Re-submit up to max_per_pass pending failed alerts.

        Iterates JSON sidecars in `self.failed_dir`, oldest first by mtime.
        Returns a dict with attempted, succeeded, failed, remaining counts.
        Skipped silently if disabled or if the directory does not exist.
        """
        result = {"attempted": 0, "succeeded": 0, "failed": 0, "remaining": 0}

        if not self.enabled:
            return result
        if not self.failed_dir.exists():
            return result

        # Collect JSON sidecars, oldest first.
        sidecars = sorted(
            (p for p in self.failed_dir.iterdir() if p.suffix == ".json"),
            key=lambda p: p.stat().st_mtime,
        )

        for sidecar in sidecars[:max_per_pass]:
            result["attempted"] += 1
            jpg_path = sidecar.with_suffix(".jpg")

            # Parse JSON. Quarantine on parse error so we never loop on poison.
            try:
                with open(sidecar, "r") as f:
                    payload = json.load(f)
            except Exception as e:
                logger.warning(
                    f"EVLOS drainer: corrupt sidecar {sidecar.name} ({e}); quarantining"
                )
                try:
                    sidecar.rename(sidecar.with_suffix(".json.poison"))
                    if jpg_path.exists():
                        jpg_path.rename(jpg_path.with_suffix(".jpg.poison"))
                except OSError as rename_err:
                    logger.warning(f"EVLOS drainer: poison rename failed: {rename_err}")
                result["failed"] += 1
                continue

            # Read JPEG bytes.
            try:
                image_bytes = jpg_path.read_bytes()
            except OSError as e:
                logger.info(f"EVLOS drainer: cannot read {jpg_path.name} ({e}); skipping")
                result["failed"] += 1
                continue

            # Re-submit using the existing transport. ONE attempt, short timeout.
            try:
                send_result = self._send_request(
                    image_data=image_bytes,
                    camera_id=payload.get("camera_id", ""),
                    alert_type=payload.get("alert_type", "other"),
                    severity=payload.get("severity", "medium"),
                    confidence=payload.get("confidence"),
                    timestamp_str=str(payload.get("timestamp", "")),
                    timeout=self.DRAIN_TIMEOUT_SECONDS,
                )
            except Exception as e:
                logger.info(f"EVLOS drainer: transport error on {sidecar.name}: {e}")
                result["failed"] += 1
                continue

            status_code = send_result.get("status_code")
            if status_code is not None and 200 <= status_code < 300:
                # Success: delete both files.
                try:
                    sidecar.unlink()
                    if jpg_path.exists():
                        jpg_path.unlink()
                    result["succeeded"] += 1
                except OSError as e:
                    logger.warning(
                        f"EVLOS drainer: sent OK but failed to delete {sidecar.name}: {e}"
                    )
                    result["failed"] += 1
            else:
                # Non-2xx: leave files in place.
                logger.info(
                    f"EVLOS drainer: {sidecar.name} not drained "
                    f"(status={status_code} error={send_result.get('error')})"
                )
                result["failed"] += 1

        # Count what's left.
        try:
            result["remaining"] = sum(
                1 for p in self.failed_dir.iterdir() if p.suffix == ".json"
            )
        except OSError:
            result["remaining"] = -1

        logger.info(
            f"EVLOS drain: attempted={result['attempted']} "
            f"succeeded={result['succeeded']} failed={result['failed']} "
            f"remaining={result['remaining']}"
        )
        return result

    def send_alert_async(self,
                        image_data: Union[bytes, str, Path],
                        camera_id: str,
                        alert_type: str = 'person_detection',
                        person_count: int = 1,
                        severity: str = 'medium',
                        confidence: float = None,
                        timestamp: datetime = None):
        """
        Send alert asynchronously (non-blocking)

        Same parameters as send_alert(), but returns immediately.
        Actual sending happens in background thread.
        """
        if not self.enabled:
            return

        # Submit to thread pool
        future = self.executor.submit(
            self.send_alert,
            image_data=image_data,
            camera_id=camera_id,
            alert_type=alert_type,
            person_count=person_count,
            severity=severity,
            confidence=confidence,
            timestamp=timestamp
        )

        logger.debug(f"EVLOS alert queued for async sending: {alert_type} from {camera_id}")

    def test_connection(self) -> Dict:
        """
        Test connection to EVLOS API with a dummy alert

        Returns:
            dict: {
                'success': bool,
                'message': str,
                'alert_id': str or None
            }
        """
        if not self.enabled:
            return {
                'success': False,
                'message': 'EVLOS integration is disabled (EVLOS_ENABLED=false)',
                'alert_id': None
            }

        logger.info(f"Testing EVLOS connection to {self.api_url}...")

        # Create a small dummy test image (1x1 red pixel JPEG)
        import io
        from PIL import Image

        test_image = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        test_image.save(img_bytes, format='JPEG')
        img_bytes = img_bytes.getvalue()

        # Send test alert
        result = self.send_alert(
            image_data=img_bytes,
            camera_id='0bc7d0b6-a27a-ff29-d9f5-fd2afac4eae4',  # Test UUID
            alert_type='person_detection',
            person_count=1,
            severity='low',
            confidence=0.5,
            timestamp=datetime.now()
        )

        if result['success']:
            return {
                'success': True,
                'message': f"Connection successful! Alert ID: {result['alert_id']}",
                'alert_id': result['alert_id']
            }
        else:
            return {
                'success': False,
                'message': f"Connection failed: {result['error']}",
                'alert_id': None
            }

    def shutdown(self):
        """Shutdown thread pool gracefully"""
        logger.info("Shutting down EVLOS client...")
        self.executor.shutdown(wait=True, cancel_futures=False)
        logger.info("EVLOS client shutdown complete")


# Global EVLOS client instance
evlos_client = EVLOSClient()
