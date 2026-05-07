"""F-026: NxWitness endpoint cache - first call scans, subsequent calls reuse."""
from unittest.mock import patch, MagicMock

import pytest

from services.nx_witness import NxWitnessClient


@pytest.fixture
def client():
    # Construct without running __init__ (which reads settings + creates auth).
    c = NxWitnessClient.__new__(NxWitnessClient)
    c.server_url = "http://test:7001"
    c.stream_server_url = c.server_url
    c.auth = ("u", "p")
    c._cached_endpoint_index = None
    return c


def _resp(status, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else []
    return r


def test_first_call_scans_until_success(client):
    """When 1st and 2nd endpoints fail, 3rd succeeds, cache is set to 2."""
    responses = [_resp(404), _resp(404), _resp(200, [{"id": "cam1", "name": "C1"}])]
    with patch("services.nx_witness.requests.get", side_effect=responses) as g:
        cams = client.get_cameras()
    assert g.call_count == 3
    assert client._cached_endpoint_index == 2
    assert len(cams) == 1


def test_second_call_uses_cache(client):
    client._cached_endpoint_index = 2
    with patch("services.nx_witness.requests.get",
               return_value=_resp(200, [{"id": "cam1", "name": "C1"}])) as g:
        client.get_cameras()
    assert g.call_count == 1


def test_cache_self_heals_on_failure(client):
    """Cached endpoint now fails; client re-scans and updates the cache."""
    client._cached_endpoint_index = 2
    responses = [_resp(404), _resp(200, [])]  # cached fails, then 1st in list works
    with patch("services.nx_witness.requests.get", side_effect=responses) as g:
        client.get_cameras()
    # 1 call to cached + 1 to find a new one.
    assert g.call_count == 2
    assert client._cached_endpoint_index == 0


def test_all_endpoints_fail_returns_empty_and_clears_cache(client):
    """If everything fails the cache should not be left pointing at a bad index."""
    client._cached_endpoint_index = 2
    responses = [_resp(500), _resp(404), _resp(404), _resp(404), _resp(404)]
    with patch("services.nx_witness.requests.get", side_effect=responses):
        cams = client.get_cameras()
    assert cams == []
    assert client._cached_endpoint_index is None
