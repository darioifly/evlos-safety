"""CameraWorker construction: every attribute the hot path reads must exist.

Regression guard: an edit once displaced the detection_config loading out of
__init__ (into a helper's dead code), which no test caught because none
constructed a real CameraWorker.
"""
from unittest.mock import MagicMock, patch

from services.video_worker_manager import CameraWorker


def _build_worker(config=None, detection_config=None):
    with patch('services.video_worker_manager.db') as mock_db:
        mock_db.get_camera_detection_config.return_value = detection_config or {
            'detection_mode': 'ppe',
            'ppe_require_helmet': 1,
            'ppe_require_vest': 1,
            'ppe_confidence': 0.75,
            'intrusion_confidence': 0.7,
            'cooldown_seconds': 5,
        }
        return CameraWorker('cam1', 'Cam 1', model=MagicMock(),
                            config=config or {}, model_lock=None)


def test_init_loads_detection_config():
    w = _build_worker()
    assert w.detection_config['detection_mode'] == 'ppe'


def test_init_builds_hot_path_state():
    w = _build_worker()
    assert w._temporal is not None
    assert w._last_type_alert == {}
    assert w._last_mode is None
    assert w._violation_evidence is None
    assert w._imgsz_cap is None


def test_init_falls_back_to_intrusion_preset_when_config_missing():
    with patch('services.video_worker_manager.db') as mock_db:
        mock_db.get_camera_detection_config.side_effect = [
            None,
            {'detection_mode': 'intrusion', 'cooldown_seconds': 5},
        ]
        w = CameraWorker('cam1', 'Cam 1', model=MagicMock(),
                         config={}, model_lock=None)
    mock_db.set_camera_detection_mode.assert_called_once_with('cam1', 'intrusion', 1)
    assert w.detection_config['detection_mode'] == 'intrusion'


def test_cfg_helpers_survive_bad_values():
    w = _build_worker(config={'inferenceSize': '1280px', 'alertRealertSeconds': None})
    assert w._cfg_int('inferenceSize', 1280) == 1280
    assert w._cfg_float('alertRealertSeconds', 120) == 120.0


def test_effective_mode_respects_dual_schedule():
    w = _build_worker(config={'detectionMode': 'dual',
                              'schedule': {'dayStartHour': 0, 'dayEndHour': 24}})
    assert w._effective_detection_mode() == 'ppe'
    w2 = _build_worker(config={'detectionMode': 'dual',
                               'schedule': {'dayStartHour': 0, 'dayEndHour': 0}})
    assert w2._effective_detection_mode() == 'intrusion'
