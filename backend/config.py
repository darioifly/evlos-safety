"""
Configuration management for Person Detection System
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


# .env lives next to the repo root. Resolve it from this file, NOT from the
# working directory: a cwd-relative path silently yields an EMPTY config when
# the app is started from anywhere but backend/, and secrets have no fallback.
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # NxWitness Configuration
    NX_SERVER_URL: str = "http://192.168.1.31:7001"  # API endpoint (using local server)
    NX_STREAM_SERVER_URL: str = "http://192.168.1.31:7001"  # Stream server (local)
    NX_ADMIN_USERNAME: str = "admin"
    # No default: the password belongs in .env (gitignored), never in a file
    # that git tracks. Empty here means .env is missing or was not found.
    NX_ADMIN_PASSWORD: str = ""

    # Detection Configuration
    YOLO_MODEL: str = "yolov8n.pt"
    CONFIDENCE_THRESHOLD: float = 0.5
    DEVICE: str = "cuda:0"
    MIN_PERSONS_FOR_ALERT: int = 1
    ALERT_COOLDOWN_SECONDS: int = 5

    # Stream Configuration
    STREAM_WIDTH: int = 640
    STREAM_HEIGHT: int = 480
    FRAME_SAMPLING: int = 30  # Process 1 every 30 frames (very low load for testing)
    BATCH_SIZE: int = 4  # Process 4 frames at a time

    # Thread Configuration
    MAX_CAMERAS: int = 20
    PRODUCER_THREADS: int = 20  # 1 per camera
    CONSUMER_THREADS: int = 1   # Only 1 consumer to minimize GIL contention
    FRAME_QUEUE_SIZE: int = 50  # Small queue to prevent accumulation
    IGNORE_CAMERA_STATUS: bool = True  # If true, try to connect to all cameras regardless of reported status

    # Retry Configuration
    STREAM_RETRY_ATTEMPTS: int = 3
    STREAM_RETRY_DELAY: int = 10  # seconds
    STREAM_RETRY_LONG_DELAY: int = 60  # seconds after max retries
    ALERT_RETRY_DELAY: int = 30  # seconds
    MAX_ALERT_BUFFER: int = 1000

    # Alert Screenshot Configuration
    ALERT_SCREENSHOT_DIR: str = "data/alert_screenshots"
    ALERT_SCREENSHOT_RETENTION_DAYS: int = 7  # Auto-cleanup after 7 days
    ALERT_DRAW_BOXES: bool = True  # Draw bounding boxes on screenshots
    ALERT_BOOKMARK_DURATION_SECONDS: int = 300  # 5 minutes

    # Camera Metadata Configuration
    CAMERA_LOCATIONS: dict = {}  # Will be populated from config file or API
    CAMERA_ZONES: dict = {}  # Will be populated from config file or API

    # EVLOS Integration Configuration
    EVLOS_ENABLED: bool = True  # Enable/disable EVLOS integration
    EVLOS_API_URL: str = "https://evlos.ifly.it/api/v1/alerts/upload"
    EVLOS_TIMEOUT: int = 10  # Request timeout in seconds
    EVLOS_MAX_RETRIES: int = 3  # Max retry attempts with exponential backoff
    EVLOS_FAILED_DIR: str = "data/evlos_failed_alerts"  # Directory for failed alerts

    # Server Configuration
    HOST: str = "0.0.0.0"  # bind on all interfaces so LAN PCs can connect
    PORT: int = 7002
    LOG_LEVEL: str = "INFO"  # INFO for cleaner logs (use DEBUG for troubleshooting)
    LOG_DIR: str = "logs"

    # F-001: How often the background task refreshes the shared camera-status
    # snapshot from NxWitness + SQLite. WebSocket clients read from this
    # snapshot so per-tab load stays flat regardless of N clients.
    CAMERA_REFRESH_INTERVAL_SECONDS: int = 5

    # F-010: How often the EVLOS spool drainer runs and how many alerts it
    # tries to re-submit per pass. Defaults aim at ~120 alerts/hour without
    # competing with live traffic.
    EVLOS_DRAINER_INTERVAL_SECONDS: int = 300
    EVLOS_DRAINER_BATCH_SIZE: int = 10

    # Worker supervisor: how often to check CameraWorker.thread liveness and
    # auto-revive dead threads.
    WORKER_SUPERVISOR_INTERVAL_SECONDS: int = 30

    class Config:
        env_file = str(ENV_FILE)
        case_sensitive = True


# Global settings instance
settings = Settings()

if not settings.NX_ADMIN_PASSWORD:
    # Loud, but not fatal: the API/stream calls would fail one by one with an
    # opaque 401 and nobody would connect that to a missing file.
    print(f"WARNING: NX_ADMIN_PASSWORD is empty - set it in {ENV_FILE}. "
          f"Every NxWitness call will fail with 401.")

