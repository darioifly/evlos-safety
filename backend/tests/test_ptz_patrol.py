"""Scene-aware PTZ patrol: policy tags, scene state machine, patrol loop."""
import time

import pytest

from services.ptz_patrol import PatrolManager, is_no_ppe_scene

TAGS = ["esterno", "parcheggio", "uffici", "no-ppe"]


class FakeNx:
    def __init__(self, presets):
        self.presets = presets
        self.activated = []
        self.cameras = [{'id': '{cam1}', 'name': 'Dragoni Carrello PTZ'}]

    def get_cameras(self):
        return self.cameras

    def ptz_get_presets(self, camera_id):
        return self.presets

    def ptz_activate_preset(self, camera_id, preset_id, speed=1.0):
        self.activated.append(preset_id)
        return True


def _manager(nx, cameras=None, dwell=0.05, settle=0.02):
    m = PatrolManager(nx_client=nx)
    m.configure({'ptzPatrol': {
        'enabled': True,
        'dwellSeconds': dwell,
        'settleSeconds': settle,
        'noPpeNameTags': TAGS,
        'skipPresetNames': ['Home'],
        'cameras': cameras or {'Dragoni Carrello PTZ': {'enabled': True}},
    }})
    return m


# ------------------------------------------------------------- tag policy

@pytest.mark.parametrize('name,expected', [
    ('Esterno parcheggio', True),
    ('esterno-nord', True),
    ('Uffici', True),
    ('vasca [no-ppe]', True),
    ('Scavo', False),
    ('Vasca 2', False),
    ('', False),
    (None, False),
])
def test_no_ppe_tag_matching(name, expected):
    assert is_no_ppe_scene(name, TAGS) is expected


def test_no_ppe_without_tags_is_false():
    assert is_no_ppe_scene('esterno', []) is False
    assert is_no_ppe_scene('esterno', None) is False


# ---------------------------------------------------------- scene state

def test_patrol_cycles_and_tracks_scene():
    nx = FakeNx([
        {'id': 'p1', 'name': 'Scavo'},
        {'id': 'p2', 'name': 'Esterno'},
        {'id': 'ph', 'name': 'Home'},  # skipped by skipPresetNames
    ])
    m = _manager(nx)
    m.start()
    try:
        time.sleep(0.3)  # a few cycles
    finally:
        m.stop()
    assert 'ph' not in nx.activated
    assert set(nx.activated) == {'p1', 'p2'}
    assert len(nx.activated) >= 3  # cycled more than one lap


def test_scene_state_reports_no_ppe_and_transit():
    nx = FakeNx([
        {'id': 'p1', 'name': 'Scavo'},
        {'id': 'p2', 'name': 'Esterno'},
    ])
    m = _manager(nx, dwell=10, settle=10)  # park on the first spot
    m.start()
    try:
        time.sleep(0.1)
        scene = m.get_scene('{cam1}')
        assert scene is not None
        assert scene['name'] == 'Scavo'
        assert scene['no_ppe'] is False
        assert scene['in_transit'] is True  # settle=10s, still in transit
    finally:
        m.stop()


def test_transit_expires_after_settle():
    nx = FakeNx([
        {'id': 'p1', 'name': 'Esterno'},
        {'id': 'p2', 'name': 'Scavo'},
    ])
    m = _manager(nx, dwell=10, settle=0.05)
    m.start()
    try:
        time.sleep(0.2)
        scene = m.get_scene('{cam1}')
        assert scene['name'] == 'Esterno'
        assert scene['no_ppe'] is True
        assert scene['in_transit'] is False
    finally:
        m.stop()


def test_unmanaged_camera_has_no_scene():
    nx = FakeNx([{'id': 'p1', 'name': 'Scavo'}, {'id': 'p2', 'name': 'Vasca'}])
    m = _manager(nx)
    m.start()
    try:
        time.sleep(0.1)
        assert m.get_scene('{other}') is None
    finally:
        m.stop()


def test_single_preset_does_not_patrol():
    nx = FakeNx([{'id': 'p1', 'name': 'Scavo'}])
    m = _manager(nx)
    m.start()
    try:
        time.sleep(0.2)
        assert nx.activated == []  # nothing to cycle with < 2 spots
    finally:
        m.stop()


def test_disabled_patrol_does_not_start():
    nx = FakeNx([{'id': 'p1', 'name': 'A'}, {'id': 'p2', 'name': 'B'}])
    m = PatrolManager(nx_client=nx)
    m.configure({'ptzPatrol': {'enabled': False,
                               'cameras': {'Dragoni Carrello PTZ': {'enabled': True}}}})
    m.start()
    try:
        time.sleep(0.1)
        assert nx.activated == []
    finally:
        m.stop()
