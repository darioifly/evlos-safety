"""Smart dwell (person-aware patrol), patrol watchdog, VLM verifier plumbing."""
import time
from unittest.mock import MagicMock, patch

import pytest

from services.ptz_patrol import PatrolManager


class FakeNx:
    def __init__(self, presets):
        self.presets = presets
        self.activated = []
        self.cameras = [{'id': '{cam1}', 'name': 'Cam PTZ'}]

    def get_cameras(self):
        return self.cameras

    def ptz_get_presets(self, camera_id):
        return self.presets

    def ptz_activate_preset(self, camera_id, preset_id, speed=1.0):
        self.activated.append((time.time(), preset_id))
        return True


def _manager(nx, dwell=0.05, settle=0.01, hold=0.5, max_hold=1.0):
    m = PatrolManager(nx_client=nx)
    m.configure({'ptzPatrol': {
        'enabled': True,
        'dwellSeconds': dwell,
        'settleSeconds': settle,
        'holdOnPersonSeconds': hold,
        'maxHoldSeconds': max_hold,
        'noPpeNameTags': [],
        'skipPresetNames': [],
        'cameras': {'Cam PTZ': {'enabled': True}},
    }})
    return m


# ------------------------------------------------------------ smart dwell

def test_person_in_view_delays_switch():
    nx = FakeNx([{'id': 'p1', 'name': 'A'}, {'id': 'p2', 'name': 'B'}])
    m = _manager(nx, dwell=0.05, hold=0.4, max_hold=5.0)
    m.start()
    try:
        time.sleep(0.1)
        baseline = len(nx.activated)
        # A person stays in view: switches must (mostly) pause.
        end = time.time() + 0.8
        while time.time() < end:
            m.report_person_seen('{cam1}')
            time.sleep(0.05)
        held = len(nx.activated) - baseline
        # Without hold we'd expect ~13+ activations in 0.8s at dwell 0.05;
        # with hold engaged there must be almost none.
        assert held <= 3, f"patrol kept switching during hold: {held}"
    finally:
        m.stop()


def test_max_hold_caps_the_delay():
    nx = FakeNx([{'id': 'p1', 'name': 'A'}, {'id': 'p2', 'name': 'B'}])
    m = _manager(nx, dwell=0.05, hold=10.0, max_hold=0.3)
    m.start()
    try:
        time.sleep(0.1)
        m.report_person_seen('{cam1}')  # person "parked" in view forever
        baseline = len(nx.activated)
        time.sleep(1.0)
        # max_hold 0.3s: the patrol must have resumed despite the person.
        assert len(nx.activated) > baseline
    finally:
        m.stop()


def test_no_person_no_delay():
    nx = FakeNx([{'id': 'p1', 'name': 'A'}, {'id': 'p2', 'name': 'B'}])
    m = _manager(nx, dwell=0.05, hold=0.5)
    m.start()
    try:
        time.sleep(0.6)
        assert len(nx.activated) >= 5  # free cycling
    finally:
        m.stop()


# --------------------------------------------------------------- watchdog

def test_ensure_alive_restarts_dead_thread():
    nx = FakeNx([{'id': 'p1', 'name': 'A'}, {'id': 'p2', 'name': 'B'}])
    m = _manager(nx)
    m.start()
    try:
        time.sleep(0.1)
        # Simulate a dead patrol thread.
        cam_id = next(iter(m._threads))
        dead = MagicMock()
        dead.is_alive.return_value = False
        m._threads[cam_id] = dead
        revived = m.ensure_alive()
        assert revived == ['Cam PTZ']
        assert m._threads[cam_id].is_alive()
    finally:
        m.stop()


def test_ensure_alive_noop_when_disabled():
    m = PatrolManager(nx_client=FakeNx([]))
    m.configure({'ptzPatrol': {'enabled': False}})
    assert m.ensure_alive() == []


# ------------------------------------------------------------ VLM verifier

def _vlm_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {'message': {'content': __import__('json').dumps(payload)}}
    return resp


def test_vlm_verifier_parses_verdict():
    import numpy as np
    from integrations.vlm_verifier import VlmVerifier
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    verdict_payload = {'vest': 'missing', 'helmet': 'present',
                       'zone': 'work_area', 'people_clearly_visible': 1,
                       'description': 'operaio senza gilet'}
    with patch('integrations.vlm_verifier.requests.post',
               return_value=_vlm_response(verdict_payload)) as post:
        v = VlmVerifier().verify(frame, ['vest_missing'], {'model': 'x'})
    assert v['vest'] == 'missing'
    assert v['zone'] == 'work_area'
    # The image must have been attached.
    body = post.call_args.kwargs['json']
    assert body['messages'][0]['images']


def test_vlm_confirms_only_on_missing():
    from integrations.vlm_verifier import VlmVerifier
    fire = {'vest': 'missing', 'helmet': 'present'}
    assert VlmVerifier.confirms(fire, 'vest_missing') is True
    assert VlmVerifier.confirms(fire, 'helmet_missing') is False
    # cannot_tell must NOT confirm — the whole point of the three-way gate.
    unsure = {'vest': 'cannot_tell', 'helmet': 'cannot_tell'}
    assert VlmVerifier.confirms(unsure, 'vest_missing') is False
    assert VlmVerifier.confirms(unsure, 'helmet_missing') is False


def test_vlm_verifier_fail_open_on_error():
    import numpy as np
    from integrations.vlm_verifier import VlmVerifier
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    with patch('integrations.vlm_verifier.requests.post',
               side_effect=ConnectionError('down')):
        assert VlmVerifier().verify(frame, ['vest_missing'], {}) is None


def test_vlm_verifier_fail_open_on_malformed():
    import numpy as np
    from integrations.vlm_verifier import VlmVerifier
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {'message': {'content': 'non-json garbage'}}
    with patch('integrations.vlm_verifier.requests.post', return_value=resp):
        assert VlmVerifier().verify(frame, ['vest_missing'], {}) is None


def test_vlm_verifier_fail_open_on_missing_field():
    import numpy as np
    from integrations.vlm_verifier import VlmVerifier
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    # Old-schema answer (no 'vest' field) must be treated as no-opinion.
    with patch('integrations.vlm_verifier.requests.post',
               return_value=_vlm_response({'violation_confirmed': True})):
        assert VlmVerifier().verify(frame, ['vest_missing'], {}) is None
