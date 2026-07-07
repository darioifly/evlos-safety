"""
Scene-aware PTZ patrol orchestration.

Problem: the trolley PTZ cameras patrol via their NATIVE firmware tours, so
neither NX Witness nor this system knows which scene the camera is looking
at — a "no-PPE zone" policy (parking, site offices) is impossible.

Solution: WE drive the patrol. Named NX presets ("scavo", "vasca",
"esterno"...) are activated in rotation by this manager via the NX legacy
PTZ API (verified live on the deployed server: ActivatePresetPtzCommand
works and GetActiveObject reflects our activation). Because the system
decides where the camera looks, it always KNOWS the current scene:

  * scenes whose preset name contains one of `noPpeNameTags` (e.g.
    "esterno") are analyzed WITHOUT PPE verdicts during the day (at night
    the dual schedule already switches to intrusion, which stays active);
  * while the camera is moving between presets (`settleSeconds` after each
    activation) analysis is skipped entirely — no motion-blur noise.

The native camera tour must be DISABLED (camera web UI) on cameras managed
here, otherwise the two patrols fight each other.

Config (config.json):
    "ptzPatrol": {
      "enabled": false,
      "dwellSeconds": 60,
      "settleSeconds": 6,
      "noPpeNameTags": ["esterno", "parcheggio", "uffici", "no-ppe"],
      "skipPresetNames": ["Home"],
      "cameras": {
        "Dragoni Carrello PTZ": {"enabled": true, "dwellSeconds": 45}
      }
    }
Cameras are keyed by NAME (what the operator sees in NX).
"""
import threading
import time

from utils.logger import logger


def is_no_ppe_scene(scene_name, tags):
    """True if the preset name carries one of the no-PPE tags."""
    if not scene_name:
        return False
    lowered = scene_name.lower()
    return any(t.lower() in lowered for t in tags or [])


class PatrolManager:
    """Drives named-preset patrols and exposes per-camera scene state."""

    def __init__(self, nx_client=None):
        self.nx = nx_client
        self.config = {}
        self._threads = {}
        self._stop = threading.Event()
        # camera_id -> {'name', 'no_ppe', 'transit_until', 'since'}
        self._scenes = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ config

    def configure(self, app_config: dict):
        self.config = (app_config or {}).get('ptzPatrol', {}) or {}

    @property
    def enabled(self) -> bool:
        return bool(self.config.get('enabled', False))

    def _camera_settings(self, camera_name: str):
        cams = self.config.get('cameras', {}) or {}
        settings = cams.get(camera_name)
        if not isinstance(settings, dict) or not settings.get('enabled', True):
            return None
        return settings

    # ------------------------------------------------------------- state

    def get_scene(self, camera_id: str):
        """Scene state for a managed camera, or None if not managed.

        Returns {'name': str, 'no_ppe': bool, 'in_transit': bool}.
        """
        with self._lock:
            s = self._scenes.get(camera_id)
            if not s:
                return None
            return {
                'name': s['name'],
                'no_ppe': s['no_ppe'],
                'in_transit': time.time() < s['transit_until'],
            }

    def status(self):
        with self._lock:
            return {
                'enabled': self.enabled,
                'cameras': {
                    cid: {
                        'scene': s['name'],
                        'no_ppe': s['no_ppe'],
                        'in_transit': time.time() < s['transit_until'],
                        'since': s['since'],
                    }
                    for cid, s in self._scenes.items()
                },
            }

    # --------------------------------------------------------- lifecycle

    def start(self):
        if not self.enabled:
            logger.info("PTZ patrol: disabled by config")
            return
        if self.nx is None:
            logger.error("PTZ patrol: no NX client, cannot start")
            return
        cameras = {}
        try:
            for cam in self.nx.get_cameras():
                cameras[cam.get('name')] = cam.get('id')
        except Exception as e:
            logger.error(f"PTZ patrol: cannot enumerate cameras: {e}")
            return
        self._stop.clear()
        for cam_name in (self.config.get('cameras', {}) or {}):
            settings = self._camera_settings(cam_name)
            if settings is None:
                continue
            cam_id = cameras.get(cam_name)
            if not cam_id:
                logger.warning(f"PTZ patrol: camera '{cam_name}' not found on NX, skipped")
                continue
            t = threading.Thread(
                target=self._run_camera,
                args=(cam_id, cam_name, settings),
                daemon=True,
                name=f"Patrol-{cam_name}",
            )
            t.start()
            self._threads[cam_id] = t
            logger.info(f"PTZ patrol: started for '{cam_name}'")

    def stop(self):
        self._stop.set()
        for t in self._threads.values():
            t.join(timeout=5)
        self._threads.clear()
        with self._lock:
            self._scenes.clear()

    # -------------------------------------------------------- patrol loop

    def _run_camera(self, cam_id: str, cam_name: str, settings: dict):
        dwell = float(settings.get('dwellSeconds',
                                   self.config.get('dwellSeconds', 60)))
        settle = float(settings.get('settleSeconds',
                                    self.config.get('settleSeconds', 6)))
        tags = self.config.get('noPpeNameTags', [])
        skip_names = {n.lower() for n in self.config.get('skipPresetNames', [])}

        consecutive_failures = 0
        while not self._stop.is_set():
            try:
                presets = [p for p in self.nx.ptz_get_presets(cam_id)
                           if p.get('name', '').lower() not in skip_names]
            except Exception as e:
                logger.warning(f"[{cam_name}] Patrol: preset fetch failed: {e}")
                presets = []
            if len(presets) < 2:
                # Nothing to patrol (0-1 spots): re-check in a minute.
                if self._stop.wait(60):
                    return
                continue

            for preset in presets:
                if self._stop.is_set():
                    return
                name = preset.get('name', preset.get('id', '?'))
                ok = False
                try:
                    ok = self.nx.ptz_activate_preset(cam_id, preset['id'])
                except Exception as e:
                    logger.warning(f"[{cam_name}] Patrol: activate '{name}' failed: {e}")
                if not ok:
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        logger.error(f"[{cam_name}] Patrol: 5 consecutive activation "
                                     f"failures; backing off 300s")
                        if self._stop.wait(300):
                            return
                        consecutive_failures = 0
                    continue
                consecutive_failures = 0
                now = time.time()
                with self._lock:
                    self._scenes[cam_id] = {
                        'name': name,
                        'no_ppe': is_no_ppe_scene(name, tags),
                        'transit_until': now + settle,
                        'since': now,
                    }
                logger.info(f"[{cam_name}] Patrol: scene '{name}'"
                            f"{' [no-PPE]' if is_no_ppe_scene(name, tags) else ''}")
                if self._stop.wait(dwell):
                    return


# Singleton, configured and started by main_sqlite at startup.
patrol = PatrolManager()
