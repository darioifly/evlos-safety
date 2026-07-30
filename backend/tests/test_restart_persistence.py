"""A restart must bring every enabled camera back.

Regression guard for 30/07/2026: stop_all() persisted enabled=False for every
camera on shutdown, so the next start found an empty enabled set, logged
"No cameras were previously enabled" and ran ZERO detection workers - while
/api/cameras/status kept serving stale fps, so it still looked alive.
"""
import pytest

from services import video_worker_manager as vwm


class _FakeWorker:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True
        return True


class _FakeDb:
    def __init__(self):
        self.calls = []

    def set_camera_enabled(self, camera_id, enabled):
        self.calls.append((camera_id, enabled))


@pytest.fixture
def manager(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(vwm, "db", fake_db)
    m = vwm.VideoWorkerManager()
    m.workers = {"cam-a": _FakeWorker(), "cam-b": _FakeWorker()}
    m.fake_db = fake_db
    return m


def test_stop_all_does_not_disable_any_camera(manager):
    """Shutdown is not a user decision to stop watching."""
    manager.stop_all()
    assert manager.fake_db.calls == []
    assert manager.workers == {}


def test_stop_worker_still_persists_for_the_toggle_api(manager):
    """An explicit toggle-off must survive a restart."""
    manager.stop_worker("cam-a")
    assert manager.fake_db.calls == [("cam-a", False)]


def test_stop_worker_persist_false_leaves_the_flag(manager):
    manager.stop_worker("cam-a", persist=False)
    assert manager.fake_db.calls == []


def test_restore_reenables_everything_stop_all_left_enabled(manager, monkeypatch):
    """The full restart cycle: stop_all() then _restore_worker_states() must
    start exactly the cameras that were running."""
    enabled = [{"camera_id": "cam-a", "camera_name": "A"},
               {"camera_id": "cam-b", "camera_name": "B"}]
    manager.fake_db.get_enabled_cameras = lambda: enabled
    manager.stop_all()

    started = []
    monkeypatch.setattr(vwm.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        manager, "_start_worker_for_camera",
        lambda cid, name: started.append(cid) or _running_worker())
    manager._restore_worker_states()

    assert started == ["cam-a", "cam-b"]


def _running_worker():
    w = _FakeWorker()
    w.running = True
    return w


def test_failed_restore_keeps_the_camera_enabled(manager, monkeypatch):
    """A camera that is merely offline right now must not be dropped from the
    watch list forever."""
    manager.fake_db.get_enabled_cameras = lambda: [
        {"camera_id": "cam-a", "camera_name": "A"}]

    def boom(camera_id, camera_name):
        raise RuntimeError("NX not up yet")

    monkeypatch.setattr(manager, "_start_worker_for_camera", boom)
    manager._restore_worker_states()

    assert manager.fake_db.calls == []
