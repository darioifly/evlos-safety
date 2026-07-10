"""Teal color-override: a teal-vest torso overrides novest; grass / no-vest
do not. Guards the fix for the wesjos model missing teal/green vests."""
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from services.video_worker_manager import CameraWorker


def _worker():
    with patch('services.video_worker_manager.db') as db:
        db.get_camera_detection_config.return_value = {'detection_mode': 'ppe'}
        return CameraWorker('c', 'Cam', model=MagicMock(), config={}, model_lock=None)


def _frame_with_torso(hsv_color, box=(20, 20, 80, 180), size=(200, 200)):
    """Frame filled dark, with the given HSV colour painted across the torso
    band (20-65% of the box height)."""
    frame = np.full((size[1], size[0], 3), 30, dtype=np.uint8)  # dark bg
    x1, y1, x2, y2 = box
    bh = y2 - y1
    ty1 = y1 + int(0.20 * bh); ty2 = y1 + int(0.65 * bh)
    patch_hsv = np.full((ty2 - ty1, x2 - x1, 3), hsv_color, dtype=np.uint8)
    frame[ty1:ty2, x1:x2] = cv2.cvtColor(patch_hsv, cv2.COLOR_HSV2BGR)
    return frame, box


def test_teal_vest_triggers_override():
    w = _worker()
    frame, box = _frame_with_torso((90, 200, 200))  # teal H90, high sat/val
    assert w._has_hivis_color(frame, box, threshold=0.35, colors=('teal',)) is True


def test_dark_torso_no_override():
    w = _worker()
    frame, box = _frame_with_torso((0, 0, 30))  # dark clothing, no hi-vis
    assert w._has_hivis_color(frame, box, threshold=0.35, colors=('teal',)) is False


def test_dull_grass_green_no_teal_override():
    w = _worker()
    # Vegetation: yellow-green hue (H50) at low saturation -> NOT teal.
    frame, box = _frame_with_torso((50, 90, 120))
    assert w._has_hivis_color(frame, box, threshold=0.35, colors=('teal',)) is False


def test_orange_not_matched_when_only_teal_requested():
    w = _worker()
    frame, box = _frame_with_torso((12, 220, 220))  # orange
    assert w._has_hivis_color(frame, box, threshold=0.35, colors=('teal',)) is False


def test_tiny_box_not_judged():
    w = _worker()
    frame, box = _frame_with_torso((90, 200, 200), box=(0, 0, 10, 10), size=(200, 200))
    assert w._has_hivis_color(frame, box, threshold=0.35, colors=('teal',)) is False
