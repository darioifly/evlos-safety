"""Diagnostic /api/health/details endpoint (Phase 2)."""
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

import main_sqlite as app_module


def _make_fake_db():
    fake_db = MagicMock()
    # PRAGMA journal_mode -> ("wal",)
    fake_db.get_connection.return_value.execute.return_value.fetchone.return_value = ("wal",)
    fake_db.get_unnotified_alerts.return_value = []
    return fake_db


def _make_fake_evlos(enabled: bool, failed_files: int = 0):
    fake_evlos = MagicMock()
    fake_evlos.enabled = enabled
    fake_evlos.executor._max_workers = 4
    fake_evlos.executor._threads = []
    fake_evlos.executor._work_queue.qsize.return_value = 0
    fake_evlos.failed_dir.exists.return_value = failed_files > 0
    fake_evlos.failed_dir.iterdir.return_value = [
        MagicMock(is_file=MagicMock(return_value=True)) for _ in range(failed_files)
    ]
    return fake_evlos


def test_health_details_ok_shape():
    """Note: TestClient is intentionally NOT used as a context manager here so
    the FastAPI lifespan does not run and overwrite our patches."""
    wm = MagicMock(); wm.workers = {}
    with patch.object(app_module, "worker_manager", wm), \
         patch.object(app_module, "db", _make_fake_db()), \
         patch.object(app_module, "evlos_client", _make_fake_evlos(enabled=True)):
        client = TestClient(app_module.app)
        r = client.get("/api/health/details")

    assert r.status_code == 200
    body = r.json()
    for key in ["status", "uptime_seconds", "db", "workers",
                "camera_snapshot", "evlos", "alerts_backlog_unnotified",
                "screenshot_dirs"]:
        assert key in body, f"missing: {key}"


def test_health_details_degraded_when_worker_dead():
    dead_thread = MagicMock(); dead_thread.is_alive.return_value = False
    dead_worker = MagicMock(); dead_worker.thread = dead_thread; dead_worker.camera_id = "cam1"

    wm = MagicMock(); wm.workers = {"cam1": dead_worker}
    with patch.object(app_module, "worker_manager", wm), \
         patch.object(app_module, "db", _make_fake_db()), \
         patch.object(app_module, "evlos_client", _make_fake_evlos(enabled=False)):
        client = TestClient(app_module.app)
        r = client.get("/api/health/details")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert "cam1" in body["workers"]["dead"]
