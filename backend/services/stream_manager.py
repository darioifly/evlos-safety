"""
Multi-Process Stream Manager with Producer-Consumer Pattern
Uses separate worker processes for YOLO to avoid GIL blocking
"""
import time
import threading
import queue
from typing import Dict, List, Optional, Tuple
import numpy as np
import cv2
import requests

from config import settings
from utils.logger import logger
from utils.metrics import metrics
from services.nx_witness import nx_client
from services.worker_pool import WorkerPool
from services.alert_manager import alert_manager


class StreamProducer(threading.Thread):
    """Producer thread that reads frames from a camera stream"""

    def __init__(self, camera_id: str, camera_name: str, frame_queue: queue.Queue, status_dict: Dict, start_delay: float = 0):
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.frame_queue = frame_queue
        self.status_dict = status_dict
        self.running = True
        self.start_delay = start_delay  # Stagger connection attempts

        # Retry configuration
        self.retry_attempts = 0
        self.max_retries = settings.STREAM_RETRY_ATTEMPTS
        self.retry_delay = settings.STREAM_RETRY_DELAY
        self.long_delay = settings.STREAM_RETRY_LONG_DELAY

        # Frame sampling
        self.frame_counter = 0
        self.frame_sampling = settings.FRAME_SAMPLING

        # FPS tracking
        self.fps_counter = 0
        self.fps_start_time = time.time()

        # Detection config cache (refreshed periodically)
        self._detection_config = None
        self._config_refresh_time = 0
        self._config_refresh_interval = 30  # Refresh config every 30 seconds

    def _get_detection_config(self) -> dict:
        """Get detection config for this camera, with caching"""
        current_time = time.time()
        if self._detection_config is None or (current_time - self._config_refresh_time) > self._config_refresh_interval:
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            self._detection_config = db.get_camera_detection_config(self.camera_id) or {}
            self._config_refresh_time = current_time
        return self._detection_config

    def run(self):
        """Main producer loop"""
        logger.info(f"[{self.camera_name}] Stream producer started (delay: {self.start_delay:.1f}s)")

        # Stagger connection attempts to avoid overwhelming the server
        if self.start_delay > 0:
            time.sleep(self.start_delay)

        while self.running:
            try:
                self._read_stream()
            except Exception as e:
                logger.error(f"[{self.camera_name}] Error in producer: {e}")
                self._handle_error()

        logger.info(f"[{self.camera_name}] Stream producer stopped")

    def _read_stream(self):
        """Read frames from MJPEG stream"""
        try:
            # Check if camera is online according to API status before attempting connection
            if self.camera_id in self.status_dict:
                api_online = self.status_dict[self.camera_id].get('online', False)
                if not api_online and not settings.IGNORE_CAMERA_STATUS:
                    logger.debug(f"[{self.camera_name}] Skipping connection attempt - camera offline according to API")
                    self._update_status(online=False)
                    time.sleep(30)  # Wait 30 seconds before checking again
                    return

            stream_url = nx_client.get_stream_url(self.camera_id)
            logger.info(f"[{self.camera_name}] Connecting to stream: {stream_url}")

            # Open stream with authentication - increased timeout for multiple concurrent connections
            response = requests.get(
                stream_url,
                auth=nx_client.auth,
                stream=True,
                timeout=30,  # Increased from 10 to 30 seconds
                verify=False
            )

            if response.status_code != 200:
                logger.error(f"[{self.camera_name}] Stream connection failed: HTTP {response.status_code} - {response.reason}")
                logger.error(f"[{self.camera_name}] Response headers: {dict(response.headers)}")
                self._handle_error()
                return

            # Reset retry counter on successful connection
            self.retry_attempts = 0
            self._update_status(online=True)
            logger.info(f"[{self.camera_name}] Connected to stream successfully")

            # Read MJPEG stream
            bytes_data = bytes()
            frame_count = 0
            chunk_count = 0

            for chunk in response.iter_content(chunk_size=4096):
                if not self.running:
                    break

                chunk_count += 1
                if chunk_count == 1:
                    logger.debug(f"[{self.camera_name}] Receiving data chunks from stream...")
                    logger.debug(f"[{self.camera_name}] First chunk size: {len(chunk)} bytes")
                    logger.debug(f"[{self.camera_name}] First 100 bytes (raw): {chunk[:100]}")
                    # Try to decode as text to see if it's an error message
                    try:
                        text = chunk.decode('utf-8', errors='ignore')[:200]
                        logger.debug(f"[{self.camera_name}] First chunk as text: {text}")
                    except:
                        pass

                bytes_data += chunk

                # Parse MJPEG boundaries
                a = bytes_data.find(b'\xff\xd8')  # JPEG start
                b = bytes_data.find(b'\xff\xd9')  # JPEG end

                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]

                    # Decode frame HERE in producer thread (not main process)
                    frame = cv2.imdecode(
                        np.frombuffer(jpg, dtype=np.uint8),
                        cv2.IMREAD_COLOR
                    )

                    if frame is not None:
                        if frame_count == 0:
                            logger.debug(f"[{self.camera_name}] First frame decoded successfully!")
                        self._process_frame(frame)
                        frame_count += 1

            # If loop ended normally (not exception), stream disconnected
            if self.running:
                if frame_count == 0:
                    # Stream connected but no frames received - camera likely offline
                    logger.warning(f"[{self.camera_name}] Stream connected but no frames received (received {chunk_count} data chunks)")
                    if chunk_count == 0:
                        logger.warning(f"[{self.camera_name}] No data chunks received at all - stream may be empty")
                    self._update_status(online=False)
                    # Use longer delay for cameras that don't send frames
                    time.sleep(self.long_delay)
                else:
                    logger.warning(f"[{self.camera_name}] Stream ended after {frame_count} frames ({chunk_count} chunks)")
                    self._update_status(online=False)
                    # Wait before reconnecting
                    time.sleep(self.retry_delay)

        except requests.exceptions.Timeout as e:
            logger.warning(f"[{self.camera_name}] Stream timeout: {e}")
            self._handle_error()
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"[{self.camera_name}] Connection error: {e}")
            self._handle_error()
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.camera_name}] Request error: {e}")
            self._handle_error()
        except Exception as e:
            logger.error(f"[{self.camera_name}] Unexpected stream error: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[{self.camera_name}] Traceback: {traceback.format_exc()}")
            self._handle_error()

    def _process_frame(self, frame: np.ndarray):
        """Process and queue decoded frame"""
        self.frame_counter += 1

        # Frame sampling - only process every Nth frame
        if self.frame_counter % self.frame_sampling != 0:
            return

        # Resize frame if needed
        if frame.shape[1] != settings.STREAM_WIDTH or frame.shape[0] != settings.STREAM_HEIGHT:
            frame = cv2.resize(frame, (settings.STREAM_WIDTH, settings.STREAM_HEIGHT))

        # Get detection config for this camera
        detection_config = self._get_detection_config()

        # Add to queue (non-blocking)
        try:
            self.frame_queue.put_nowait({
                'camera_id': self.camera_id,
                'frame': frame,
                'timestamp': time.time(),
                'detection_config': detection_config
            })
        except queue.Full:
            # Drop frame if queue is full
            logger.debug(f"Frame queue full, dropping frame from {self.camera_id}")
            metrics.record_error("queue_full")

        # Update FPS
        self._update_fps()

    def _update_fps(self):
        """Calculate and update FPS metrics"""
        self.fps_counter += 1
        current_time = time.time()
        elapsed = current_time - self.fps_start_time

        if elapsed >= 5.0:  # Update every 5 seconds
            fps = self.fps_counter / elapsed
            metrics.record_fps(self.camera_id, fps)

            # Update status
            self._update_status(online=True, fps=fps)

            # Reset counters
            self.fps_counter = 0
            self.fps_start_time = current_time

    def _handle_error(self):
        """Handle stream errors with retry logic"""
        self._update_status(online=False)

        self.retry_attempts += 1

        if self.retry_attempts <= self.max_retries:
            delay = self.retry_delay
            logger.info(f"Retrying {self.camera_id} in {delay}s (attempt {self.retry_attempts}/{self.max_retries})")
        else:
            delay = self.long_delay
            logger.warning(f"Max retries reached for {self.camera_id}, waiting {delay}s")

        time.sleep(delay)

    def _update_status(self, online: bool, fps: float = 0.0):
        """Update camera stream connection status"""
        if self.camera_id in self.status_dict:
            # Update stream connection status but preserve 'online' (API status)
            self.status_dict[self.camera_id].update({
                'stream_connected': online,
                'fps': fps,
                'lastUpdate': time.time()
            })
        else:
            # Initialize if not exists
            self.status_dict[self.camera_id] = {
                'online': False,
                'stream_connected': online,
                'fps': fps,
                'lastUpdate': time.time()
            }

    def stop(self):
        """Stop the producer thread"""
        self.running = False


class BatchCollector(threading.Thread):
    """
    Batch collector thread that collects frames and sends them to worker pool.
    Runs in main process, just collects frames and submits to multiprocess workers.
    """

    def __init__(self, frame_queue: queue.Queue, worker_pool: WorkerPool, result_handler=None):
        super().__init__(daemon=True)
        self.frame_queue = frame_queue
        self.worker_pool = worker_pool
        self.result_handler = result_handler
        self.running = True
        self.batch_size = settings.BATCH_SIZE

    def run(self):
        """Main batch collector loop"""
        logger.info("Started batch collector")

        while self.running:
            try:
                # Collect batch of frames
                batch = self._collect_batch()

                if batch:
                    # Cache frames in result handler for alert screenshots
                    if self.result_handler:
                        for frame_data in batch:
                            camera_id = frame_data.get('camera_id')
                            frame = frame_data.get('frame')
                            if camera_id and frame is not None:
                                self.result_handler.cache_frame(camera_id, frame)

                    # Submit batch to worker pool (non-blocking)
                    self.worker_pool.submit_batch(batch)
                else:
                    time.sleep(0.01)  # Small delay if no frames

            except Exception as e:
                logger.error(f"Error in batch collector: {e}")
                metrics.record_error("batch_collector")
                time.sleep(0.1)

        logger.info("Stopped batch collector")

    def _collect_batch(self) -> List[Dict]:
        """Collect a batch of frames from queue"""
        batch = []
        timeout = 0.1

        try:
            # Get first frame (blocking with timeout)
            frame_data = self.frame_queue.get(timeout=timeout)
            batch.append(frame_data)

            # Collect more frames (non-blocking) up to batch_size
            while len(batch) < self.batch_size:
                try:
                    frame_data = self.frame_queue.get_nowait()
                    batch.append(frame_data)
                except queue.Empty:
                    break

        except queue.Empty:
            pass

        return batch


class ResultHandler:
    """
    Handles detection results from worker pool.
    Registered as callback with WorkerPool.
    """

    def __init__(self, status_dict: Dict, websocket_manager, camera_names: Dict, event_loop):
        self.status_dict = status_dict
        self.websocket_manager = websocket_manager
        self.camera_names = camera_names
        self.event_loop = event_loop
        # Frame cache to store frames temporarily for alert screenshots
        self.frame_cache: Dict[str, np.ndarray] = {}
        self.frame_cache_lock = threading.Lock()
        self.frame_cache_max_size = 100  # Max frames to keep in cache

    def cache_frame(self, camera_id: str, frame: np.ndarray):
        """
        Cache a frame for potential use in alerts.
        Only keeps the most recent frame per camera.

        Args:
            camera_id: Camera identifier
            frame: Numpy array of the frame
        """
        with self.frame_cache_lock:
            # Keep only most recent frame per camera to save memory
            self.frame_cache[camera_id] = frame.copy()

            # Limit cache size
            if len(self.frame_cache) > self.frame_cache_max_size:
                # Remove oldest (first) entry
                oldest_key = next(iter(self.frame_cache))
                del self.frame_cache[oldest_key]

    def get_cached_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """
        Retrieve cached frame for camera.

        Args:
            camera_id: Camera identifier

        Returns:
            Cached frame or None if not found
        """
        with self.frame_cache_lock:
            return self.frame_cache.get(camera_id)

    def handle_results(self, detections: List[Dict]):
        """
        Handle batch of detection results from workers.
        Called by WorkerPool result handler thread.
        """
        import asyncio

        for detection in detections:
            try:
                camera_id = detection['camera_id']
                person_count = detection['person_count']
                confidence = detection['confidence']

                # Update camera status
                if camera_id in self.status_dict:
                    self.status_dict[camera_id].update({
                        'persons': person_count,
                        'lastDetection': time.time(),
                        'confidence': confidence
                    })

                # Get frame from detection result (passed directly from worker)
                # This ensures the frame matches the detection, avoiding cache timing issues
                frame = detection.get('frame')

                # Fallback to cached frame if not available (shouldn't happen normally)
                if frame is None:
                    frame = self.get_cached_frame(camera_id)

                # Send alert if needed (now with frame)
                alert_data = alert_manager.process_detection(detection, frame=frame)

                if alert_data:
                    # Ensure camera_name is set from ResultHandler (AlertManager in worker may not have it)
                    alert_data['camera_name'] = self.camera_names.get(camera_id, camera_id)

                    # Broadcast alert via WebSocket using run_coroutine_threadsafe
                    asyncio.run_coroutine_threadsafe(
                        self.websocket_manager.broadcast({
                            'type': 'alert',
                            'data': alert_data
                        }),
                        self.event_loop
                    )

                    # Update last alert time in status
                    self.status_dict[camera_id]['lastAlert'] = alert_data['timestamp']

                # Broadcast camera status update using run_coroutine_threadsafe
                asyncio.run_coroutine_threadsafe(
                    self.websocket_manager.broadcast({
                        'type': 'camera_status',
                        'data': {
                            'cameraId': camera_id,
                            'persons': person_count,
                            'online': self.status_dict[camera_id].get('online', False)
                        }
                    }),
                    self.event_loop
                )

            except Exception as e:
                logger.error(f"Error handling detection result: {e}")


class StreamManager:
    """Manage all camera streams with producer-consumer pattern"""

    def __init__(self, websocket_manager, event_loop=None):
        self.websocket_manager = websocket_manager
        self.event_loop = event_loop  # Store event loop for thread-safe async calls
        self.frame_queue = queue.Queue(maxsize=settings.FRAME_QUEUE_SIZE)
        self.camera_status: Dict = {}
        self.camera_names: Dict = {}  # Map camera_id to name
        self.camera_api_status: Dict = {}  # Store API-reported online status (source of truth)

        self.producers: List[StreamProducer] = []
        self.batch_collectors: List[BatchCollector] = []

        # NEW: Worker pool for multiprocess YOLO
        self.worker_pool = WorkerPool(num_workers=settings.CONSUMER_THREADS)
        self.result_handler = None

        self.running = False

        logger.info("StreamManager initialized with multiprocess workers")

    def start(self, cameras: List[Dict], auto_start_workers: bool = False):
        """
        Start stream processing infrastructure (workers must be manually enabled per camera)

        Args:
            cameras: List of camera dictionaries with id and name
            auto_start_workers: If True, automatically start workers for all online cameras.
                               If False (default), workers must be manually enabled via toggle_camera()
        """
        if self.running:
            logger.warning("StreamManager already running")
            return

        self.running = True
        logger.info(f"Starting StreamManager with {len(cameras)} cameras (auto_start_workers={auto_start_workers})")

        # Start worker pool (multiprocess)
        self.worker_pool.start()

        # Create and register result handler
        self.result_handler = ResultHandler(
            self.camera_status,
            self.websocket_manager,
            self.camera_names,
            self.event_loop
        )
        self.worker_pool.register_callback(self.result_handler.handle_results)

        # Start batch collector threads (collect frames and submit to workers)
        num_collectors = max(1, settings.CONSUMER_THREADS // 2)  # Fewer collectors than workers
        for i in range(num_collectors):
            collector = BatchCollector(self.frame_queue, self.worker_pool, self.result_handler)
            collector.start()
            self.batch_collectors.append(collector)
            logger.info(f"Started batch collector {i+1}/{num_collectors}")

        # Initialize camera data but don't start producers unless auto_start_workers=True
        for camera in cameras:
            # Store camera name and API status
            camera_id = camera['id']
            camera_name = camera.get('name', camera_id)
            api_online = camera.get('isOnline', False)

            self.camera_names[camera_id] = camera_name
            self.camera_api_status[camera_id] = api_online  # Store API-reported status

            # Initialize camera status - use API status as initial value
            # Workers start as disabled by default
            self.camera_status[camera_id] = {
                'online': api_online,
                'stream_connected': False,
                'fps': 0,
                'person_count': 0,
                'lastUpdate': time.time(),
                'enabled': False  # Workers disabled by default
            }

        # Only start producers if auto_start_workers is True
        if auto_start_workers:
            producer_index = 0
            for camera in cameras:
                camera_id = camera['id']
                camera_name = camera.get('name', camera_id)
                api_online = camera.get('isOnline', False)

                # Check if we should ignore camera status
                if not settings.IGNORE_CAMERA_STATUS:
                    if not api_online:
                        logger.info(f"Skipping offline camera: {camera_id} (API status: offline)")
                        continue
                else:
                    if not api_online:
                        logger.info(f"Camera {camera_id} reported as offline by API, but IGNORE_CAMERA_STATUS=true - attempting connection anyway")

                # Stagger connection attempts (2 seconds between each camera)
                # This prevents overwhelming the NX Witness server with simultaneous connections
                start_delay = producer_index * 2.0

                producer = StreamProducer(
                    camera_id,
                    camera_name,
                    self.frame_queue,
                    self.camera_status,
                    start_delay=start_delay
                )
                producer.start()
                self.producers.append(producer)
                self.camera_status[camera_id]['enabled'] = True
                producer_index += 1
                logger.info(f"Scheduled producer for camera: {camera_name} (starts in {start_delay}s)")

            logger.info(f"StreamManager started with {len(self.producers)} producers and {len(self.batch_collectors)} batch collectors")
        else:
            logger.info(f"StreamManager started with {len(self.batch_collectors)} batch collectors (workers disabled, use toggle_camera to enable)")

    def stop(self):
        """Stop all stream processing"""
        if not self.running:
            return

        logger.info("Stopping StreamManager...")
        self.running = False

        # Stop all producers
        for producer in self.producers:
            producer.stop()

        # Stop all batch collectors
        for collector in self.batch_collectors:
            collector.running = False

        # Stop worker pool (this stops worker processes)
        self.worker_pool.stop()

        # Don't wait for threads - they're daemon threads and will terminate automatically
        self.producers.clear()
        self.batch_collectors.clear()

        logger.info("StreamManager stopped")

    def get_status(self) -> Dict:
        """Get status of all cameras with names and both API + stream status"""
        # Add camera names to status
        status_with_names = {}

        # Include all cameras, even those without status updates yet
        all_camera_ids = set(self.camera_names.keys()) | set(self.camera_status.keys())


        for camera_id in all_camera_ids:
            # Get status or use default
            status = self.camera_status.get(camera_id, {
                'online': self.camera_api_status.get(camera_id, False),
                'stream_connected': False,
                'fps': 0,
                'person_count': 0,
                'lastUpdate': time.time(),
                'enabled': False
            })

            # Add camera name
            status_with_names[camera_id] = {
                **status,
                'camera_id': camera_id,
                'camera_name': self.camera_names.get(camera_id, camera_id),
                'apiStatus': self.camera_api_status.get(camera_id, False)
            }

        return status_with_names

    def refresh_api_status(self, cameras: List[Dict]):
        """
        Refresh camera online status from NX Witness API
        This should be called periodically to update the source of truth
        """
        for camera in cameras:
            camera_id = camera['id']
            api_online = camera.get('isOnline', False)

            # Update stored API status
            self.camera_api_status[camera_id] = api_online

            # Update the 'online' field in camera_status
            if camera_id in self.camera_status:
                self.camera_status[camera_id]['online'] = api_online
                logger.debug(f"Updated API status for {camera_id}: online={api_online}")
            else:
                # Initialize status if camera wasn't tracked before
                self.camera_status[camera_id] = {
                    'online': api_online,
                    'stream_connected': False,
                    'fps': 0,
                    'persons': 0,
                    'lastUpdate': time.time()
                }
                # Also store the name if we have it
                if camera_id not in self.camera_names:
                    self.camera_names[camera_id] = camera.get('name', camera_id)

    def toggle_camera(self, camera_id: str) -> bool:
        """
        Toggle worker for a specific camera (start/stop)

        Args:
            camera_id: Camera ID to toggle

        Returns:
            bool: True if camera is now enabled, False if disabled
        """
        # Check if camera has an active producer
        producer_found = None
        for producer in self.producers:
            if producer.camera_id == camera_id:
                producer_found = producer
                break

        if producer_found:
            # Camera is running - stop it
            logger.info(f"Stopping worker for camera: {camera_id}")
            producer_found.stop()
            producer_found.join(timeout=2.0)
            self.producers.remove(producer_found)

            # Update status to show worker disabled
            if camera_id in self.camera_status:
                self.camera_status[camera_id].update({
                    'enabled': False,
                    'stream_connected': False,
                    'fps': 0,
                    'person_count': 0
                })

            logger.info(f"Worker stopped for camera: {camera_id}")
            return False
        else:
            # Camera is not running - start it
            logger.info(f"Starting worker for camera: {camera_id}")

            # Get camera name from stored names or use ID
            camera_name = self.camera_names.get(camera_id, camera_id)

            # Initialize status if not exists
            if camera_id not in self.camera_status:
                api_online = self.camera_api_status.get(camera_id, True)
                self.camera_status[camera_id] = {
                    'online': api_online,
                    'stream_connected': False,
                    'fps': 0,
                    'person_count': 0,
                    'lastUpdate': time.time(),
                    'enabled': True
                }
            else:
                self.camera_status[camera_id]['enabled'] = True

            # Start new producer (no delay for manual start)
            producer = StreamProducer(
                camera_id,
                camera_name,
                self.frame_queue,
                self.camera_status,
                start_delay=0
            )
            producer.start()
            self.producers.append(producer)

            logger.info(f"Worker started for camera: {camera_name}")
            return True

    def restart_camera(self, camera_id: str):
        """Restart stream for a specific camera"""
        # Find and stop the producer
        for producer in self.producers:
            if producer.camera_id == camera_id:
                producer.stop()
                producer.join(timeout=2.0)
                self.producers.remove(producer)
                break

        # Start new producer (no delay for manual restart)
        camera_name = self.camera_names.get(camera_id, camera_id)
        producer = StreamProducer(
            camera_id,
            camera_name,
            self.frame_queue,
            self.camera_status,
            start_delay=0
        )
        producer.start()
        self.producers.append(producer)

        logger.info(f"Restarted stream for camera: {camera_name}")
