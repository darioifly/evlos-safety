"""RTSP transport: URL building, credential redaction, resolution parsing,
time-based analysis cadence."""
import time

import pytest

from services.nx_witness import NxWitnessClient, redact_url
from services.video_worker_manager import (
    CameraWorker, _parse_resolution, RTSP_CAPTURE_OPTIONS)


@pytest.fixture
def client():
    c = NxWitnessClient.__new__(NxWitnessClient)  # no network in __init__
    c.stream_server_url = "http://192.168.1.31:7001"
    c.username = "admin"
    c.password = "Sicurezza12!"
    return c


def test_rtsp_url_strips_braces_and_keeps_port(client):
    url = client.get_rtsp_url("{01c1f42a-6045-82ca-0567-af02b6e04645}")
    assert url == ("rtsp://admin:Sicurezza12%21@192.168.1.31:7001/"
                   "01c1f42a-6045-82ca-0567-af02b6e04645?stream=0")


def test_rtsp_url_secondary_stream(client):
    assert client.get_rtsp_url("abc", stream_index=1).endswith("/abc?stream=1")


def test_rtsp_url_percent_encodes_credentials(client):
    """A '@' or '/' in the password must not break the userinfo boundary."""
    client.password = "p@ss/word:x"
    url = client.get_rtsp_url("abc")
    assert url.startswith("rtsp://admin:p%40ss%2Fword%3Ax@192.168.1.31:7001/")
    assert url.count("@") == 1


def test_rtsp_url_defaults_port_when_missing(client):
    client.stream_server_url = "http://192.168.1.31"
    assert "192.168.1.31:7001/" in client.get_rtsp_url("abc")


def test_rtsp_url_tolerates_scheme_less_setting(client):
    client.stream_server_url = "192.168.1.31:7001"
    assert client.get_rtsp_url("abc").startswith(
        "rtsp://admin:Sicurezza12%21@192.168.1.31:7001/")


def test_redact_url_hides_credentials(client):
    assert redact_url(client.get_rtsp_url("abc")) == (
        "rtsp://***@192.168.1.31:7001/abc?stream=0")
    assert "Sicurezza" not in redact_url(client.get_rtsp_url("abc"))


def test_redact_url_leaves_credential_free_urls_alone():
    assert redact_url("http://192.168.1.31:7001/media/abc.mpjpeg") == (
        "http://192.168.1.31:7001/media/abc.mpjpeg")
    assert redact_url(None) == ""


@pytest.mark.parametrize("value,expected", [
    ("1280x720", (1280, 720)),
    ("1280X720", (1280, 720)),
    (None, None),
    ("", None),
    ("highest", None),
    ("0x720", None),
    ("axb", None),
])
def test_parse_resolution(value, expected):
    assert _parse_resolution(value) == expected


def test_capture_options_force_tcp_and_a_socket_timeout():
    """Without a timeout a dead peer blocks read() forever and the worker
    never reaches its reconnect backoff."""
    assert "rtsp_transport;tcp" in RTSP_CAPTURE_OPTIONS
    assert "timeout;" in RTSP_CAPTURE_OPTIONS


def _worker(config):
    w = CameraWorker.__new__(CameraWorker)  # no DB / YOLO in __init__
    w.camera_name = "test-cam"
    w.config = config
    w._boost_until = 0.0
    return w


def test_analysis_interval_matches_the_mjpeg_era_cadence():
    """0.5 analyzed fps == the old 5 fps MJPEG stream at frameSampling 10."""
    assert _worker({"analysisFps": 0.5})._analysis_interval() == 2.0


def test_analysis_interval_defaults_when_unset():
    assert _worker({})._analysis_interval() == 2.0


@pytest.mark.parametrize("bad", [0, -1, "abc", None])
def test_analysis_interval_never_divides_by_zero(bad):
    """0 or garbage must degrade to 'analyze every frame', not crash."""
    assert _worker({"analysisFps": bad})._analysis_interval() >= 0.0


def test_boost_factor_is_one_outside_the_boost_window():
    assert _worker({"analysisFpsBoostFactor": 3.0})._boost_factor() == 1.0


def test_boost_factor_densifies_inside_the_window():
    w = _worker({"analysisFpsBoostFactor": 3.0})
    w._boost_until = time.time() + 10
    assert w._boost_factor() == 3.0
    # A boost must never make sampling SPARSER than the base rate.
    w.config = {"analysisFpsBoostFactor": 0.2}
    assert w._boost_factor() == 1.0
