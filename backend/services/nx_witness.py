"""
NxWitness API Client
"""
import base64
import time
import json
import uuid
import os
from typing import Dict, List, Optional, Tuple
import requests
from requests.auth import HTTPBasicAuth
import cv2
import numpy as np

from config import settings
from utils.logger import logger


class NxWitnessClient:
    """Client for interacting with NxWitness VMS API"""

    def __init__(self):
        self.server_url = settings.NX_SERVER_URL  # For API calls
        self.stream_server_url = settings.NX_STREAM_SERVER_URL  # For video streams
        self.username = settings.NX_ADMIN_USERNAME
        self.password = settings.NX_ADMIN_PASSWORD
        self.auth = HTTPBasicAuth(self.username, self.password)

        # Token caching
        self._token: Optional[str] = None
        self._token_timestamp: float = 0
        self._token_ttl: int = 900  # 15 minutes

        # F-026: cache the index of the working endpoint in get_cameras() so we
        # don't pay the failed-attempt latency for the first 3 endpoints on every
        # call. Self-heals: a cached endpoint that starts failing is re-scanned.
        self._cached_endpoint_index: Optional[int] = None

        logger.info(f"Initialized NxWitness client - API: {self.server_url}, Stream: {self.stream_server_url}")

    def _get_auth_token(self) -> str:
        """Get or refresh authentication token"""
        current_time = time.time()

        # Return cached token if still valid
        if self._token and (current_time - self._token_timestamp) < self._token_ttl:
            return self._token

        # Generate new token
        credentials = f"{self.username}:{self.password}"
        self._token = base64.b64encode(credentials.encode()).decode()
        self._token_timestamp = current_time

        logger.debug("Generated new authentication token")
        return self._token

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with authentication"""
        token = self._get_auth_token()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json"
        }

    def get_cameras(self) -> List[Dict]:
        """
        Fetch list of cameras from NxWitness

        Returns:
            List of camera dictionaries with id, name, and online status
        """
        endpoints = [
            "/rest/v1/devices",
            "/api/v1/devices",
            "/rest/v2/devices",
            "/ec2/getCamerasEx"
        ]

        # F-026: try the cached endpoint first; on failure, fall through to scan.
        if self._cached_endpoint_index is not None:
            idx = self._cached_endpoint_index
            try:
                url = f"{self.server_url}{endpoints[idx]}"
                response = requests.get(url, auth=self.auth, timeout=10, verify=False)
                if response.status_code == 200:
                    return self._parse_cameras(response.json())
                logger.warning(f"Cached endpoint {endpoints[idx]} returned {response.status_code}; rescanning")
            except Exception as e:
                logger.warning(f"Cached endpoint {endpoints[idx]} failed ({e}); rescanning")
            # Cache stale: clear and fall through.
            self._cached_endpoint_index = None

        for i, endpoint in enumerate(endpoints):
            try:
                url = f"{self.server_url}{endpoint}"
                logger.debug(f"Trying endpoint: {url}")

                response = requests.get(
                    url,
                    auth=self.auth,
                    timeout=10,
                    verify=False  # For self-signed certs
                )

                if response.status_code == 200:
                    cameras_data = response.json()
                    cameras = self._parse_cameras(cameras_data)
                    logger.debug(f"Successfully fetched {len(cameras)} cameras from {endpoint}")
                    self._cached_endpoint_index = i
                    return cameras
                else:
                    logger.warning(f"Endpoint {endpoint} returned status {response.status_code}")

            except Exception as e:
                logger.warning(f"Failed to fetch from {endpoint}: {e}")
                continue

        logger.error("All endpoints failed to fetch cameras")
        return []

    def _parse_cameras(self, data: any) -> List[Dict]:
        """Parse camera data from various API response formats"""
        cameras = []

        # Handle list response
        if isinstance(data, list):
            items = data
        # Handle dict response with cameras key
        elif isinstance(data, dict):
            items = data.get('cameras', data.get('devices', data.get('items', [])))
        else:
            items = []

        for item in items:
            is_online = self._parse_online_status(item)
            camera = {
                'id': item.get('id', item.get('physicalId', item.get('uuid', 'unknown'))),
                'name': item.get('name', item.get('logicalId', 'Unknown Camera')),
                'isOnline': is_online,
                'url': item.get('url', ''),
                'model': item.get('model', 'Unknown'),
            }
            # Log camera detection at DEBUG level (too verbose for INFO)
            logger.debug(f"Camera {camera['name']} ({camera['id']}): isOnline={is_online}")
            cameras.append(camera)

        return cameras

    def _parse_online_status(self, camera_data: Dict) -> bool:
        """
        Parse online status from various field formats
        Checks multiple fields in priority order based on NX Witness API variants
        """
        # Priority 1: Check 'status' field (most common)
        if 'status' in camera_data:
            status = camera_data['status']
            if isinstance(status, str):
                # Check for online states
                status_lower = status.lower()
                if status_lower in ['online', 'recording', 'connected', 'active']:
                    return True
                # Check for offline states
                if status_lower in ['offline', 'disconnected', 'unauthorized']:
                    return False
            elif isinstance(status, bool):
                return status

        # Priority 2: Check 'isOnline' boolean field
        if 'isOnline' in camera_data:
            return bool(camera_data['isOnline'])

        # Priority 3: Check 'online' boolean field
        if 'online' in camera_data:
            return bool(camera_data['online'])

        # Priority 4: Check 'state' field
        if 'state' in camera_data:
            state = camera_data['state']
            if isinstance(state, str):
                state_lower = state.lower()
                return state_lower in ['online', 'active', 'recording', 'connected']
            return bool(state)

        # Priority 5: Check 'enabled' field
        if 'enabled' in camera_data:
            return bool(camera_data['enabled'])

        # Priority 6: Check 'statusFlags' field
        if 'statusFlags' in camera_data:
            flags = camera_data['statusFlags']
            if isinstance(flags, str):
                return flags.lower() not in ['offline', 'disconnected']
            if isinstance(flags, int):
                return flags != 0

        # If camera is in the list but has no status field, log it
        logger.debug(f"No definitive status field for camera {camera_data.get('name', camera_data.get('id', 'unknown'))}")
        logger.debug(f"Available fields: {list(camera_data.keys())}")

        # Default: if camera is returned by API and we can't determine status, assume offline
        # This is safer than assuming online for cameras that might not be working
        return False

    def get_stream_url(self, camera_id: str, width: int = None, height: int = None,
                       quality: str = None) -> str:
        """
        Get MJPEG stream URL for a camera

        Args:
            camera_id: Camera identifier
            width: Stream width (default from settings) - DEPRECATED if quality is set
            height: Stream height (default from settings) - DEPRECATED if quality is set
            quality: Stream quality preset: "low", "medium", "high", "highest" (overrides width/height)

        Returns:
            MJPEG stream URL
        """
        # Use the dedicated stream server (local NX Witness server)
        base_url = self.stream_server_url

        # Remove curly braces from camera_id (NX Witness doesn't want them in stream URLs)
        clean_camera_id = camera_id.strip('{}')

        # NX Witness MJPEG stream endpoint
        # IMPORTANT: Use .mpjpeg (Motion JPEG) not .mjpeg
        url = f"{base_url}/media/{clean_camera_id}.mpjpeg"

        # Add quality parameter if specified (NX Witness native quality control)
        if quality and quality in ["low", "medium", "high", "highest"]:
            url += f"?resolution={quality}"
            logger.debug(f"Generated stream URL with quality '{quality}': {url}")
        else:
            # Fallback to legacy width/height (not recommended)
            width = width or settings.STREAM_WIDTH
            height = height or settings.STREAM_HEIGHT
            logger.debug(f"Generated stream URL (legacy size {width}x{height}): {url}")

        return url

    def read_stream_frame(self, camera_id: str, timeout: int = 10) -> Optional[np.ndarray]:
        """
        Read a single frame from camera MJPEG stream

        Args:
            camera_id: Camera identifier
            timeout: Request timeout in seconds

        Returns:
            Frame as numpy array or None if failed
        """
        try:
            url = self.get_stream_url(camera_id)
            response = requests.get(
                url,
                auth=self.auth,
                stream=True,
                timeout=timeout,
                verify=False
            )

            if response.status_code != 200:
                logger.error(f"Stream request failed for {camera_id}: HTTP {response.status_code}")
                return None

            # Read MJPEG stream chunks
            bytes_data = bytes()
            for chunk in response.iter_content(chunk_size=1024):
                bytes_data += chunk

                # Find JPEG boundaries
                a = bytes_data.find(b'\xff\xd8')  # JPEG start
                b = bytes_data.find(b'\xff\xd9')  # JPEG end

                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]

                    # Decode JPEG to numpy array
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

                    if frame is not None:
                        return frame

        except Exception as e:
            logger.error(f"Error reading stream for {camera_id}: {e}")
            return None

    def send_alert(self, camera_id: str, camera_name: str = None, person_count: int = 0,
                   confidence: float = 0.0, boxes: List[Dict] = None, metadata: Dict = None,
                   image_path: str = None) -> bool:
        """
        Send alert to NxWitness as Generic Event with camera snapshot

        Note: NxWitness Generic Events don't support uploading external images directly.
        Instead, we use the 'cameraRefs' metadata field to make NxWitness attach
        a snapshot from the camera itself to the event/notification.

        Args:
            camera_id: Camera identifier (UUID)
            camera_name: Human-readable camera name (used as source field)
            person_count: Number of persons detected
            confidence: Detection confidence
            boxes: List of bounding box dictionaries with coordinates and confidence
            metadata: Additional metadata (alert level, camera info, etc.)
            image_path: DEPRECATED - Not used (NxWitness doesn't support external image upload)

        Returns:
            True if alert sent successfully
        """
        try:
            # Try multiple possible alert endpoints
            endpoints = [
                "/api/createEvent",
                "/rest/v1/events",
                "/ec2/addEvent"
            ]

            # Build simple, human-readable description
            # Only essential information that's useful for a person
            alert_level = metadata.get("alertLevel", "low") if metadata else "low"

            # Simple description text (no technical data)
            description = f"Rilevate {person_count} persona/e"
            if confidence >= 0.9:
                description += " (alta confidenza)"
            elif confidence >= 0.7:
                description += " (media confidenza)"

            # Add cameraRefs to metadata so NxWitness attaches camera snapshot
            # This is the proper way to get images in NxWitness notifications
            event_metadata = {
                "cameraRefs": [camera_id]  # NxWitness will attach snapshot from this camera
            }

            # Use camera name as source if provided, otherwise use camera ID
            source = camera_name if camera_name else camera_id

            payload = {
                "source": source,  # Use human-readable camera name
                "caption": f"Rilevamento Persone: {person_count} persona/e",
                "description": description,
                "timestamp": time.time(),
                "eventType": "personDetection",
                "metadata": json.dumps(event_metadata)  # Must be JSON string
            }

            # DETAILED LOGGING
            logger.info(f"[ALERT SEND] Attempting to send alert for camera {camera_name or camera_id}")
            logger.info(f"[ALERT SEND] Person count: {person_count}, Confidence: {confidence:.2%}")
            logger.info(f"[ALERT SEND] Caption: {payload['caption']}")
            logger.info(f"[ALERT SEND] Description: {payload['description']}")
            logger.info(f"[ALERT SEND] Source: {source}")
            logger.info(f"[ALERT SEND] Metadata: cameraRefs={event_metadata['cameraRefs']}")
            logger.info(f"[ALERT SEND] Trying {len(endpoints)} endpoints...")

            for endpoint in endpoints:
                try:
                    url = f"{self.server_url}{endpoint}"
                    logger.info(f"[ALERT SEND] → POST to: {url}")

                    # Send event with metadata containing cameraRefs
                    # NxWitness will automatically attach camera snapshot
                    response = requests.post(
                        url,
                        json=payload,
                        auth=self.auth,
                        timeout=5,
                        verify=False
                    )

                    logger.info(f"[ALERT SEND] ← Response status: {response.status_code}")
                    logger.debug(f"[ALERT SEND] ← Response body: {response.text[:200]}")

                    if response.status_code in [200, 201, 202]:
                        logger.info(f"[ALERT SEND] ✅ SUCCESS! Alert sent for {camera_id}: {person_count} person(s) (with camera snapshot)")
                        return True
                    else:
                        logger.warning(f"[ALERT SEND] ⚠️ Alert endpoint {endpoint} returned {response.status_code}: {response.text[:100]}")

                except requests.exceptions.Timeout as e:
                    logger.error(f"[ALERT SEND] ⏱️ Timeout on {endpoint}: {e}")
                    continue
                except requests.exceptions.ConnectionError as e:
                    logger.error(f"[ALERT SEND] 🔌 Connection error on {endpoint}: {e}")
                    continue
                except Exception as e:
                    logger.error(f"[ALERT SEND] ❌ Failed to send alert to {endpoint}: {type(e).__name__}: {e}")
                    continue

            logger.error(f"[ALERT SEND] ❌ ALL {len(endpoints)} ENDPOINTS FAILED for camera {camera_id}")
            return False

        except Exception as e:
            logger.error(f"Error sending alert for {camera_id}: {e}")
            return False

    def create_bookmark(self, camera_id: str, name: str, duration_seconds: int = None,
                       tags: Dict = None, timestamp: float = None) -> bool:
        """
        Create a bookmark on NxWitness video timeline

        Note: Bookmarks in NxWitness reference video footage by timestamp,
        not external image files. Use Generic Events for image attachments.

        Args:
            camera_id: Camera identifier
            name: Bookmark name/caption
            duration_seconds: Duration of bookmark in seconds (default from settings)
            tags: Dictionary of tags to add to bookmark (key: value pairs)
            timestamp: Unix timestamp for bookmark start (default: current time)

        Returns:
            True if bookmark created successfully
        """
        try:
            # Use provided timestamp or current time
            start_time = timestamp if timestamp else time.time()
            start_time_ms = int(start_time * 1000)

            # Use provided duration or default from settings
            if duration_seconds is None:
                duration_seconds = settings.ALERT_BOOKMARK_DURATION_SECONDS
            duration_ms = duration_seconds * 1000

            # Generate unique GUID for bookmark
            bookmark_guid = str(uuid.uuid4())

            # Clean camera ID (remove curly braces if present)
            clean_camera_id = camera_id.strip('{}')

            # Build tags string (format: key:value,key2:value2)
            tags_str = ""
            if tags:
                tags_str = ",".join([f"{k}:{v}" for k, v in tags.items()])

            # Try multiple bookmark endpoints
            endpoints = [
                "/ec2/bookmarks/add",
                "/api/bookmarks",
                "/rest/v1/bookmarks"
            ]

            for endpoint in endpoints:
                try:
                    # Build URL with query parameters (NxWitness prefers URL params for bookmarks)
                    url = f"{self.server_url}{endpoint}"

                    params = {
                        "guid": bookmark_guid,
                        "cameraId": clean_camera_id,
                        "startTimeMs": start_time_ms,
                        "durationMs": duration_ms,
                        "name": name
                    }

                    # Add tags if present
                    if tags_str:
                        params["tag"] = tags_str

                    response = requests.post(
                        url,
                        params=params,
                        auth=self.auth,
                        timeout=5,
                        verify=False
                    )

                    if response.status_code in [200, 201, 202]:
                        logger.info(f"Bookmark created for {camera_id}: '{name}' (duration: {duration_seconds}s)")
                        return True
                    else:
                        logger.warning(f"Bookmark endpoint {endpoint} returned {response.status_code}: {response.text}")

                except Exception as e:
                    logger.debug(f"Failed to create bookmark at {endpoint}: {e}")
                    continue

            logger.error(f"All bookmark endpoints failed for camera {camera_id}")
            return False

        except Exception as e:
            logger.error(f"Error creating bookmark for {camera_id}: {e}")
            return False

    # ------------------------------------------------------------- PTZ
    # Legacy /api/ptz endpoint (verified live on the deployed server:
    # works over http with Basic auth; ActivatePresetPtzCommand moves the
    # camera and GetActiveObject reflects our activation).

    def _ptz_command(self, camera_id: str, command: str, **extra) -> Optional[Dict]:
        """POST a legacy PTZ command; returns the parsed JSON or None."""
        try:
            payload = {"cameraId": camera_id, "command": command}
            payload.update(extra)
            response = requests.post(
                f"{self.server_url}/api/ptz",
                json=payload,
                headers=self._get_headers(),
                timeout=10,
                verify=False,
            )
            if response.status_code != 200:
                logger.warning(f"PTZ {command} on {camera_id}: HTTP {response.status_code}")
                return None
            data = response.json()
            if data.get('error') not in ('0', 0, None):
                logger.warning(f"PTZ {command} on {camera_id}: {data.get('errorString')}")
                return None
            return data
        except Exception as e:
            logger.warning(f"PTZ {command} on {camera_id} failed: {e}")
            return None

    def ptz_get_presets(self, camera_id: str) -> List[Dict]:
        """Named PTZ presets of a camera: [{'id':..., 'name':...}, ...]."""
        data = self._ptz_command(camera_id, "GetPresetsPtzCommand")
        return data.get('reply', []) if data else []

    def ptz_activate_preset(self, camera_id: str, preset_id: str, speed: float = 1.0) -> bool:
        """Move the camera to a named preset. Returns True on success."""
        data = self._ptz_command(camera_id, "ActivatePresetPtzCommand",
                                 presetId=preset_id, speed=speed)
        return data is not None

    def test_connection(self) -> bool:
        """Test connection to NxWitness server"""
        try:
            cameras = self.get_cameras()
            if cameras:
                logger.info(f"Connection test successful - found {len(cameras)} cameras")
                return True
            else:
                logger.warning("Connection test: No cameras found")
                return False
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


# Global client instance
nx_client = NxWitnessClient()
