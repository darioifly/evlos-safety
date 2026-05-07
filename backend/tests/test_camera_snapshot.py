"""F-001: CameraStatusSnapshot is the single point of truth fed by ONE refresher."""
from unittest.mock import patch, MagicMock

import pytest

import main_sqlite as app_module


@pytest.fixture(autouse=True)
def reset_snapshot():
    """Reset the global snapshot between tests."""
    snap = app_module.camera_snapshot
    snap.cameras = {}
    snap.last_updated = 0.0
    snap.last_nx_latency_ms = None
    snap.last_error = None
    yield


@pytest.mark.asyncio
async def test_snapshot_refresh_populates_cameras():
    fake_nx = [
        {"id": "cam1", "name": "Cam 1", "isOnline": True},
        {"id": "cam2", "name": "Cam 2", "isOnline": False},
    ]
    fake_db_status = [
        {"camera_id": "cam1", "fps": 12.0, "enabled": 0, "last_update": None,
         "last_detection": None, "person_count": 0, "avg_confidence": 0,
         "online": 0, "stream_connected": 0, "camera_name": "Cam 1"},
    ]

    fake_nx_client = MagicMock()
    fake_nx_client.get_cameras.return_value = fake_nx

    with patch.object(app_module, "nx_client", fake_nx_client), \
         patch.object(app_module, "db") as fake_db:
        fake_db.get_all_camera_status.return_value = fake_db_status

        await app_module._refresh_camera_snapshot_once()

    snap = app_module.camera_snapshot
    assert set(snap.cameras.keys()) == {"cam1", "cam2"}
    assert snap.cameras["cam1"]["fps"] == 12.0
    assert snap.cameras["cam1"]["online"] == 1
    assert snap.cameras["cam2"]["online"] == 0
    assert snap.last_error is None
    assert snap.last_nx_latency_ms is not None
    assert snap.last_updated > 0


@pytest.mark.asyncio
async def test_snapshot_refresh_records_error_on_nx_failure():
    fake_nx_client = MagicMock()
    fake_nx_client.get_cameras.side_effect = RuntimeError("boom")

    with patch.object(app_module, "nx_client", fake_nx_client), \
         patch.object(app_module, "db") as fake_db:
        fake_db.get_all_camera_status.return_value = []

        await app_module._refresh_camera_snapshot_once()

    snap = app_module.camera_snapshot
    assert snap.last_error is not None
    assert "boom" in snap.last_error
