"""
Second-stage alert verification with a local vision-language model
(Qwen-VL via Ollama on the same GPU box).

YOLO stays the fast first stage on every sampled frame. When the temporal
filter confirms a violation and an alert is about to fire, the evidence
frame goes to the VLM with a structured prompt. The VLM:

  * confirms/refutes the violation (kills residual false positives, which
    in turn lets the YOLO thresholds run LOWER — more candidates, same
    precision);
  * classifies the AREA semantically (work area vs parking/office/road) —
    zone policy without any geometry, robust to PTZ tracking that drags
    the camera across zones;
  * returns a one-line description attached to the alert.

Fail-open by design: if the VLM is down, times out, or answers garbage,
the alert fires anyway — the verifier can only ADD confidence, never
silently disable the safety pipeline.

Config (config.json):
    "vlmVerifier": {
      "enabled": false,
      "url": "http://127.0.0.1:11434",
      "model": "qwen2.5vl:7b",
      "timeoutSeconds": 45,
      "suppressZones": ["parking", "office"],
      "minPixelsPersonCrop": 0
    }
"""
import base64
import json

import cv2
import requests

from utils.logger import logger

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["violation_confirmed", "vest_violation", "helmet_violation",
                 "zone", "people", "description"],
    "properties": {
        "violation_confirmed": {"type": "boolean"},
        "vest_violation": {"type": "boolean"},
        "helmet_violation": {"type": "boolean"},
        "zone": {"type": "string",
                 "enum": ["work_area", "parking", "office", "road", "unknown"]},
        "people": {"type": "integer"},
        "description": {"type": "string"},
    },
}

PROMPT = (
    "You are verifying a construction-site CCTV alert produced by an object "
    "detector. Candidate violations on this frame: {violations}.\n"
    "Look carefully at every clearly visible person.\n"
    "- vest_violation: true ONLY if at least one clearly visible person is "
    "plainly NOT wearing a hi-vis vest (any hi-vis colour counts as wearing; "
    "turned/occluded people do not count as violations).\n"
    "- helmet_violation: true ONLY if a clearly visible person is plainly "
    "bare-headed or wears a non-helmet hat.\n"
    "- violation_confirmed: true if at least one of the candidate violations "
    "is really visible.\n"
    "- zone: where the PEOPLE are — an active work area (excavation, crane, "
    "formwork, machinery), a parking/office/container area, a public road, "
    "or unknown.\n"
    "- description: one short factual sentence (Italian) about what you see.\n"
    "Be strict: when you cannot honestly tell, do not confirm."
)


class VlmVerifier:
    """Calls a local Ollama vision model to double-check PPE alerts."""

    def verify(self, frame_bgr, violations, cfg: dict):
        """Verify an about-to-fire alert.

        Args:
            frame_bgr: the evidence frame (numpy BGR).
            violations: list like ['vest_missing', 'helmet_missing'].
            cfg: the 'vlmVerifier' config block.

        Returns a dict (RESPONSE_SCHEMA) or None on any failure — callers
        must treat None as "no opinion" and fail open.
        """
        try:
            url = cfg.get('url', 'http://127.0.0.1:11434').rstrip('/')
            model = cfg.get('model', 'qwen2.5vl:7b')
            timeout = float(cfg.get('timeoutSeconds', 45))

            ok, jpg = cv2.imencode('.jpg', frame_bgr,
                                   [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                return None
            image_b64 = base64.b64encode(jpg.tobytes()).decode()

            human = {'vest_missing': 'person without hi-vis vest',
                     'helmet_missing': 'person without helmet'}
            prompt = PROMPT.format(violations=', '.join(
                human.get(v, v) for v in violations))

            response = requests.post(
                f"{url}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": RESPONSE_SCHEMA,
                    "options": {"temperature": 0},
                    "messages": [{
                        "role": "user",
                        "content": prompt,
                        "images": [image_b64],
                    }],
                },
                timeout=timeout,
            )
            if response.status_code != 200:
                logger.warning(f"VLM verifier: HTTP {response.status_code}")
                return None
            content = response.json().get('message', {}).get('content', '')
            verdict = json.loads(content)
            if not isinstance(verdict, dict) or 'violation_confirmed' not in verdict:
                logger.warning(f"VLM verifier: malformed answer: {content[:200]}")
                return None
            return verdict
        except Exception as e:
            logger.warning(f"VLM verifier failed (fail-open): {e}")
            return None


vlm_verifier = VlmVerifier()
