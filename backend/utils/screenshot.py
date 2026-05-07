"""
Screenshot utilities for alert management
"""
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import cv2
import numpy as np

from config import settings
from utils.logger import logger


def ensure_screenshot_dir() -> str:
    """
    Ensure screenshot directory exists

    Returns:
        Path to screenshot directory
    """
    screenshot_dir = settings.ALERT_SCREENSHOT_DIR
    os.makedirs(screenshot_dir, exist_ok=True)
    return screenshot_dir


def save_detection_screenshot(frame: np.ndarray, boxes: List[Dict],
                              camera_id: str, timestamp: float = None) -> Optional[str]:
    """
    Save screenshot with bounding boxes drawn

    Args:
        frame: Numpy array of the frame
        boxes: List of bounding box dictionaries with x1, y1, x2, y2, confidence
        camera_id: Camera identifier
        timestamp: Unix timestamp (default: current time)

    Returns:
        Path to saved screenshot or None if failed
    """
    try:
        # Ensure directory exists
        screenshot_dir = ensure_screenshot_dir()

        # Use provided timestamp or current time
        if timestamp is None:
            timestamp = time.time()

        # Format timestamp for filename
        dt = datetime.fromtimestamp(timestamp)
        timestamp_str = dt.strftime("%Y%m%d_%H%M%S")

        # Clean camera ID for filename
        clean_camera_id = camera_id.replace("{", "").replace("}", "").replace("/", "_")

        # Build filename
        filename = f"{clean_camera_id}_{timestamp_str}.jpg"
        filepath = os.path.join(screenshot_dir, filename)

        # Copy frame to avoid modifying original
        annotated_frame = frame.copy()

        # Draw bounding boxes if enabled and boxes are present
        if settings.ALERT_DRAW_BOXES and boxes:
            annotated_frame = draw_bounding_boxes(annotated_frame, boxes)

        # Save as JPEG
        success = cv2.imwrite(filepath, annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        if success:
            logger.debug(f"Screenshot saved: {filepath}")
            return filepath
        else:
            logger.error(f"Failed to save screenshot: {filepath}")
            return None

    except Exception as e:
        logger.error(f"Error saving screenshot for {camera_id}: {e}")
        return None


def draw_bounding_boxes(frame: np.ndarray, boxes: List[Dict]) -> np.ndarray:
    """
    Draw bounding boxes on frame

    Args:
        frame: Numpy array of the frame
        boxes: List of bounding box dictionaries with x1, y1, x2, y2, confidence

    Returns:
        Frame with bounding boxes drawn
    """
    # Color mapping for alert levels (BGR format for OpenCV)
    colors = {
        'high': (0, 0, 255),      # Red
        'medium': (0, 165, 255),  # Orange
        'low': (0, 255, 0)        # Green
    }

    for box in boxes:
        try:
            # Extract coordinates
            x1 = int(box['x1'])
            y1 = int(box['y1'])
            x2 = int(box['x2'])
            y2 = int(box['y2'])
            confidence = box.get('confidence', 0.0)

            # Determine color based on confidence
            if confidence >= 0.85:
                color = colors['high']
            elif confidence >= 0.70:
                color = colors['medium']
            else:
                color = colors['low']

            # Draw rectangle
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Prepare label - use actual class name from detection
            class_name = box.get('class', 'Person')
            # Capitalize first letter for display
            display_name = class_name.capitalize() if class_name else 'Person'
            label = f"{display_name} {confidence:.2%}"
            label_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

            # Draw label background
            cv2.rectangle(
                frame,
                (x1, y1 - label_size[1] - baseline - 5),
                (x1 + label_size[0], y1),
                color,
                -1  # Filled
            )

            # Draw label text
            cv2.putText(
                frame,
                label,
                (x1, y1 - baseline - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),  # White text
                1
            )

        except Exception as e:
            logger.warning(f"Error drawing bounding box: {e}")
            continue

    return frame


def cleanup_screenshot_dir(path, days: int) -> int:
    """Delete files in `path` older than `days` days. (F-009)

    Args:
        path: pathlib.Path or str pointing at a directory.
        days: retention window in days.

    Returns:
        Number of files deleted. Tolerates a missing directory (returns 0)
        and per-file OSError (logged at debug, continues).
    """
    try:
        path_str = str(path)
        if not os.path.isdir(path_str):
            return 0

        cutoff_time = time.time() - (days * 24 * 60 * 60)
        deleted = 0

        for entry in os.listdir(path_str):
            full = os.path.join(path_str, entry)
            try:
                if not os.path.isfile(full):
                    continue
                if os.path.getmtime(full) < cutoff_time:
                    os.remove(full)
                    deleted += 1
            except OSError as e:
                logger.debug(f"cleanup_screenshot_dir: skip {full}: {e}")

        return deleted
    except Exception as e:
        logger.error(f"cleanup_screenshot_dir error on {path}: {e}")
        return 0


def cleanup_old_screenshots(retention_days: int = None) -> int:
    """
    Remove screenshots older than retention period

    Args:
        retention_days: Number of days to keep screenshots (default from settings)

    Returns:
        Number of files deleted
    """
    try:
        # Use provided retention or default from settings
        if retention_days is None:
            retention_days = settings.ALERT_SCREENSHOT_RETENTION_DAYS

        screenshot_dir = settings.ALERT_SCREENSHOT_DIR

        # Check if directory exists
        if not os.path.exists(screenshot_dir):
            return 0

        # Calculate cutoff time
        cutoff_time = time.time() - (retention_days * 24 * 60 * 60)

        deleted_count = 0

        # Iterate through files in directory
        for filename in os.listdir(screenshot_dir):
            filepath = os.path.join(screenshot_dir, filename)

            # Skip if not a file
            if not os.path.isfile(filepath):
                continue

            # Check file age
            file_mtime = os.path.getmtime(filepath)

            if file_mtime < cutoff_time:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.debug(f"Deleted old screenshot: {filename}")
                except Exception as e:
                    logger.warning(f"Failed to delete {filename}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old screenshots (retention: {retention_days} days)")

        return deleted_count

    except Exception as e:
        logger.error(f"Error during screenshot cleanup: {e}")
        return 0


def get_screenshot_stats() -> Dict:
    """
    Get statistics about stored screenshots

    Returns:
        Dictionary with count, total size, oldest and newest timestamps
    """
    try:
        screenshot_dir = settings.ALERT_SCREENSHOT_DIR

        if not os.path.exists(screenshot_dir):
            return {
                'count': 0,
                'total_size_mb': 0,
                'oldest': None,
                'newest': None
            }

        files = []
        total_size = 0

        for filename in os.listdir(screenshot_dir):
            filepath = os.path.join(screenshot_dir, filename)

            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files.append({
                    'name': filename,
                    'mtime': stat.st_mtime,
                    'size': stat.st_size
                })
                total_size += stat.st_size

        if not files:
            return {
                'count': 0,
                'total_size_mb': 0,
                'oldest': None,
                'newest': None
            }

        # Sort by modification time
        files.sort(key=lambda x: x['mtime'])

        return {
            'count': len(files),
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'oldest': datetime.fromtimestamp(files[0]['mtime']).isoformat(),
            'newest': datetime.fromtimestamp(files[-1]['mtime']).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting screenshot stats: {e}")
        return {
            'count': 0,
            'total_size_mb': 0,
            'oldest': None,
            'newest': None
        }
