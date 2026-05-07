"""Worker supervisor: detects dead threads, attempts revival, reports."""
import threading
from unittest.mock import MagicMock, patch

import pytest

from services.video_worker_manager import VideoWorkerManager


def _alive_thread():
    t = threading.Thread(target=lambda: threading.Event().wait(), daemon=True)
    t.start()
    return t


def _dead_thread():
    t = threading.Thread(target=lambda: None)
    t.start()
    t.join()
    return t


def _mock_worker(camera_id: str, alive: bool):
    w = MagicMock()
    w.camera_id = camera_id
    w.camera_name = camera_id
    w.thread = _alive_thread() if alive else _dead_thread()
    w.stop_event = threading.Event()
    w.running = alive
    return w


def _make_mgr():
    """Build a manager without running __init__ (avoids YOLO load + DB)."""
    mgr = VideoWorkerManager.__new__(VideoWorkerManager)
    mgr.workers = {}
    mgr.model = None
    mgr.config = {}
    mgr.model_lock = threading.Lock()
    mgr._initialized = True
    # Speed up the supervisor probe in tests.
    mgr.WORKER_REVIVE_PROBE_SECONDS = 0.0
    return mgr


def test_supervise_reports_alive_workers():
    mgr = _make_mgr()
    mgr.workers = {"cam1": _mock_worker("cam1", alive=True)}

    result = mgr.supervise()

    assert result["alive"] == ["cam1"]
    assert result["revived"] == []
    assert result["still_dead"] == []


def test_supervise_revives_dead_worker():
    mgr = _make_mgr()
    mgr.workers = {"cam1": _mock_worker("cam1", alive=False)}

    revived = _mock_worker("cam1", alive=True)
    with patch.object(mgr, "_start_worker_for_camera", return_value=revived) as start:
        result = mgr.supervise()

    assert result["alive"] == []
    assert result["revived"] == ["cam1"]
    assert result["still_dead"] == []
    start.assert_called_once_with("cam1", "cam1")


def test_supervise_marks_still_dead_when_revival_raises():
    mgr = _make_mgr()
    dead = _mock_worker("cam1", alive=False)
    mgr.workers = {"cam1": dead}

    with patch.object(mgr, "_start_worker_for_camera", side_effect=RuntimeError("boom")):
        result = mgr.supervise()

    assert "cam1" in result["still_dead"]
    assert result["revived"] == []


def test_supervise_marks_still_dead_when_new_thread_also_dead():
    mgr = _make_mgr()
    mgr.workers = {"cam1": _mock_worker("cam1", alive=False)}

    new_dead = _mock_worker("cam1", alive=False)
    with patch.object(mgr, "_start_worker_for_camera", return_value=new_dead):
        result = mgr.supervise()

    assert "cam1" in result["still_dead"]
    assert result["revived"] == []


def test_supervise_does_not_call_revive_for_alive_workers():
    mgr = _make_mgr()
    mgr.workers = {"cam1": _mock_worker("cam1", alive=True)}

    with patch.object(mgr, "_start_worker_for_camera") as start:
        mgr.supervise()

    start.assert_not_called()


def test_supervise_handles_mixed_state():
    mgr = _make_mgr()
    mgr.workers = {
        "cam_alive": _mock_worker("cam_alive", alive=True),
        "cam_dead":  _mock_worker("cam_dead",  alive=False),
    }
    revived = _mock_worker("cam_dead", alive=True)
    with patch.object(mgr, "_start_worker_for_camera", return_value=revived):
        result = mgr.supervise()

    assert result["alive"] == ["cam_alive"]
    assert result["revived"] == ["cam_dead"]
    assert result["still_dead"] == []
