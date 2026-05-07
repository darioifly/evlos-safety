"""F-010: EVLOS drainer tests.

The drainer must:
- Re-submit pending alerts using the existing transport (_send_request).
- Delete spool files only on 2xx.
- Leave spool files untouched on any error.
- Quarantine corrupt JSON sidecars instead of looping on them.
- Respect max_per_pass.
- Drain oldest first (FIFO by mtime).
"""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from integrations.evlos_client import EVLOSClient


def _spool(d: Path, prefix: str, payload: dict):
    (d / f"{prefix}.jpg").write_bytes(b"fake-jpeg-bytes")
    (d / f"{prefix}.json").write_text(json.dumps(payload))


def _spool_payload():
    """Match the real shape written by _save_failed_alert."""
    return {
        "camera_id": "cam1",
        "alert_type": "intrusion",
        "severity": "medium",
        "confidence": 0.9,
        "timestamp": "2026-05-07T10:00:00",
        "error": "previous failure",
        "api_url": "http://test/api",
        "saved_at": "2026-05-07T10:00:00",
    }


@pytest.fixture
def client(tmp_path):
    """An EVLOSClient with the spool directory pointed at tmp_path.

    Built without running __init__ to avoid touching real settings.
    """
    c = EVLOSClient.__new__(EVLOSClient)
    c.enabled = True
    c.failed_dir = tmp_path
    c.api_url = "http://test/api"
    c.timeout = 10
    c.DRAIN_TIMEOUT_SECONDS = 5
    return c


def test_drainer_skipped_when_disabled(client):
    client.enabled = False
    _spool(client.failed_dir, "20260507_100000_intrusion", _spool_payload())
    result = client.drain_failed_alerts(max_per_pass=10)
    assert result == {"attempted": 0, "succeeded": 0, "failed": 0, "remaining": 0}


def test_drainer_resubmits_and_deletes_on_2xx(client):
    _spool(client.failed_dir, "20260507_100000_intrusion", _spool_payload())

    with patch.object(client, "_send_request") as send:
        send.return_value = {
            "success": True, "alert_id": "abc", "error": None, "status_code": 200
        }
        result = client.drain_failed_alerts(max_per_pass=10)

    assert result["attempted"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["remaining"] == 0
    assert not (client.failed_dir / "20260507_100000_intrusion.json").exists()
    assert not (client.failed_dir / "20260507_100000_intrusion.jpg").exists()


def test_drainer_keeps_spool_on_non_2xx(client):
    _spool(client.failed_dir, "20260507_100000_intrusion", _spool_payload())

    with patch.object(client, "_send_request") as send:
        send.return_value = {
            "success": False, "alert_id": None,
            "error": "HTTP 500: x", "status_code": 500,
        }
        result = client.drain_failed_alerts(max_per_pass=10)

    assert result["succeeded"] == 0
    assert result["failed"] == 1
    assert result["remaining"] == 1
    assert (client.failed_dir / "20260507_100000_intrusion.json").exists()
    assert (client.failed_dir / "20260507_100000_intrusion.jpg").exists()


def test_drainer_keeps_spool_on_transport_exception(client):
    _spool(client.failed_dir, "20260507_100000_intrusion", _spool_payload())

    with patch.object(client, "_send_request") as send:
        send.side_effect = ConnectionError("EVLOS down")
        result = client.drain_failed_alerts(max_per_pass=10)

    assert result["succeeded"] == 0
    assert result["failed"] == 1
    assert result["remaining"] == 1
    assert (client.failed_dir / "20260507_100000_intrusion.json").exists()


def test_drainer_quarantines_corrupt_json(client):
    (client.failed_dir / "alert_bad.json").write_text("{not-json")
    (client.failed_dir / "alert_bad.jpg").write_bytes(b"img")

    with patch.object(client, "_send_request") as send:
        result = client.drain_failed_alerts(max_per_pass=10)

    assert result["attempted"] == 1
    assert result["failed"] == 1
    assert (client.failed_dir / "alert_bad.json.poison").exists()
    assert (client.failed_dir / "alert_bad.jpg.poison").exists()
    assert not (client.failed_dir / "alert_bad.json").exists()
    send.assert_not_called()


def test_drainer_respects_max_per_pass(client):
    for i in range(5):
        _spool(client.failed_dir, f"20260507_10000{i}_intrusion", _spool_payload())

    with patch.object(client, "_send_request") as send:
        send.return_value = {"success": True, "alert_id": "x",
                             "error": None, "status_code": 200}
        result = client.drain_failed_alerts(max_per_pass=2)

    assert result["attempted"] == 2
    assert result["succeeded"] == 2
    assert result["remaining"] == 3


def test_drainer_drains_oldest_first(client):
    for i in range(3):
        _spool(client.failed_dir, f"alert_{i:03d}", _spool_payload())
        # Force ascending mtime so alert_000 is oldest.
        ts = time.time() + i
        os.utime(client.failed_dir / f"alert_{i:03d}.json", (ts, ts))
        os.utime(client.failed_dir / f"alert_{i:03d}.jpg", (ts, ts))

    with patch.object(client, "_send_request") as send:
        send.return_value = {"success": True, "alert_id": "x",
                             "error": None, "status_code": 200}
        client.drain_failed_alerts(max_per_pass=1)

    assert not (client.failed_dir / "alert_000.json").exists()
    assert (client.failed_dir / "alert_001.json").exists()
    assert (client.failed_dir / "alert_002.json").exists()


def test_drainer_uses_short_timeout(client):
    """Drainer must call _send_request with the configured short timeout, not self.timeout."""
    _spool(client.failed_dir, "20260507_100000_intrusion", _spool_payload())

    with patch.object(client, "_send_request") as send:
        send.return_value = {"success": True, "alert_id": "x",
                             "error": None, "status_code": 200}
        client.drain_failed_alerts(max_per_pass=1)

    _, kwargs = send.call_args
    assert kwargs.get("timeout") == client.DRAIN_TIMEOUT_SECONDS
