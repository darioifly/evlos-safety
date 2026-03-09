"""
Performance metrics tracking
"""
import time
from typing import Dict, List
from collections import defaultdict, deque
from datetime import datetime
import threading


class MetricsCollector:
    """Collect and track system performance metrics"""

    def __init__(self, history_size: int = 100):
        self.history_size = history_size
        self.lock = threading.Lock()

        # Metrics storage
        self.fps_data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_size))
        self.detection_counts: Dict[str, int] = defaultdict(int)
        self.alert_counts: Dict[str, int] = defaultdict(int)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.processing_times: deque = deque(maxlen=history_size)

        # System metrics
        self.start_time = time.time()
        self.total_alerts = 0
        self.total_detections = 0

        # Historical data for charts
        self.history: deque = deque(maxlen=history_size)

    def record_fps(self, camera_id: str, fps: float):
        """Record FPS for a camera"""
        with self.lock:
            self.fps_data[camera_id].append({
                'timestamp': datetime.now().isoformat(),
                'fps': fps
            })

    def record_detection(self, camera_id: str, person_count: int):
        """Record a detection event"""
        with self.lock:
            self.detection_counts[camera_id] += 1
            self.total_detections += 1

    def record_alert(self, camera_id: str):
        """Record an alert sent"""
        with self.lock:
            self.alert_counts[camera_id] += 1
            self.total_alerts += 1

    def record_error(self, component: str):
        """Record an error"""
        with self.lock:
            self.error_counts[component] += 1

    def record_processing_time(self, duration: float):
        """Record frame processing time"""
        with self.lock:
            self.processing_times.append(duration)

    def add_history_point(self, fps: float, detections: int):
        """Add a point to historical data for charts"""
        with self.lock:
            self.history.append({
                'time': datetime.now().strftime('%H:%M:%S'),
                'fps': fps,
                'detections': detections
            })

    def get_avg_fps(self) -> float:
        """Get average FPS across all cameras"""
        with self.lock:
            if not self.fps_data:
                return 0.0
            all_fps = []
            for camera_fps in self.fps_data.values():
                if camera_fps:
                    all_fps.extend([point['fps'] for point in camera_fps])
            return sum(all_fps) / len(all_fps) if all_fps else 0.0

    def get_camera_fps(self, camera_id: str) -> float:
        """Get average FPS for a specific camera"""
        with self.lock:
            camera_fps = self.fps_data.get(camera_id, [])
            if not camera_fps:
                return 0.0
            fps_values = [point['fps'] for point in camera_fps]
            return sum(fps_values) / len(fps_values)

    def get_avg_processing_time(self) -> float:
        """Get average frame processing time in ms"""
        with self.lock:
            if not self.processing_times:
                return 0.0
            return (sum(self.processing_times) / len(self.processing_times)) * 1000

    def get_alerts_today(self) -> int:
        """Get total alerts sent today"""
        return self.total_alerts

    def get_uptime(self) -> float:
        """Get system uptime in hours"""
        return (time.time() - self.start_time) / 3600

    def get_summary(self) -> Dict:
        """Get summary of all metrics"""
        with self.lock:
            return {
                'avgFps': round(self.get_avg_fps(), 2),
                'avgProcessingTime': round(self.get_avg_processing_time(), 2),
                'alertsToday': self.total_alerts,
                'totalDetections': self.total_detections,
                'uptime': round(self.get_uptime(), 2),
                'history': list(self.history),
                'cameraFps': {
                    camera: round(self.get_camera_fps(camera), 2)
                    for camera in self.fps_data.keys()
                },
                'errorCounts': dict(self.error_counts)
            }


# Global metrics instance
metrics = MetricsCollector()
