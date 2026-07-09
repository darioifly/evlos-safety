"""
Second-stage alert verification with a local vision-language model
(Qwen-VL via Ollama on the same GPU box).

YOLO stays the fast first stage on every sampled frame. When the temporal
filter confirms a violation and an alert is about to fire, the evidence
frame goes to the VLM with a structured prompt. The VLM returns a
THREE-WAY verdict per item — missing / present / cannot_tell — and the
worker fires only on `missing`.

Why three-way: forcing a yes/no boolean made Qwen rubber-stamp violations
even when its own description said "not possible to determine" (observed in
production 09/07/2026: distant/angled frames fired anyway). An explicit
`cannot_tell` lets uncertainty suppress the alert instead of confirming it,
which is what makes it safe to run YOLO at a low novest threshold — the VLM
is the precision gate, so it must actually gate.

  * zone: semantic classification (work vs parking/office/road). NOTE: on
    this site the VLM zone is fuzzy (it labels office/staging as parking),
    so zone suppression is OFF by default; the authoritative zone signal is
    the PTZ patrol preset name. The field is kept for logging/telemetry.
  * description: one-line Italian summary attached to the alert.

Fail-open by design: if the VLM is down, times out, or answers garbage,
the alert fires anyway — the verifier can only ADD precision, never
silently disable the safety pipeline.

Config (config.json):
    "vlmVerifier": {
      "enabled": false,
      "url": "http://127.0.0.1:11434",
      "model": "qwen2.5vl:7b",
      "timeoutSeconds": 30,
      "suppressZones": []
    }
"""
import base64
import json

import cv2
import requests

from utils.logger import logger

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["vest", "helmet", "zone", "people_clearly_visible", "description"],
    "properties": {
        "vest": {"type": "string", "enum": ["missing", "present", "cannot_tell"]},
        "helmet": {"type": "string", "enum": ["missing", "present", "cannot_tell"]},
        "zone": {"type": "string",
                 "enum": ["work_area", "parking", "office", "road", "unknown"]},
        "people_clearly_visible": {"type": "integer"},
        "description": {"type": "string"},
    },
}

PROMPT = (
    "You are verifying a construction-site CCTV alert produced by an object "
    "detector. The detector flagged: {violations}. Faces are pixelated for "
    "privacy — judge PPE from the body, torso and head shape.\n"
    "Assess every CLEARLY VISIBLE person. For each item answer with exactly "
    "one of: missing / present / cannot_tell.\n"
    "- vest = 'missing' ONLY if at least one clearly visible person is plainly "
    "NOT wearing a hi-vis vest (any hi-vis colour counts as present). "
    "'present' if everyone clearly visible wears one. 'cannot_tell' if people "
    "are too far, too small, too dark, or turned away to judge honestly.\n"
    "- helmet = same three-way logic for a hard hat.\n"
    "- CRUCIAL: when you are not sure, answer 'cannot_tell'. Do NOT guess "
    "'missing'. A wrong 'missing' raises a false alarm.\n"
    "- zone: where the people are (active work area / parking / office / road / "
    "unknown).\n"
    "- description: one short factual sentence in Italian.\n"
)

# Map internal violation type -> the schema field that decides it.
_TYPE_FIELD = {'vest_missing': 'vest', 'helmet_missing': 'helmet'}


class VlmVerifier:
    """Calls a local Ollama vision model to double-check PPE alerts."""

    def verify(self, frame_bgr, violations, cfg: dict):
        """Verify an about-to-fire alert.

        Returns a dict (RESPONSE_SCHEMA) or None on any failure — callers
        must treat None as "no opinion" and fail open.
        """
        try:
            url = cfg.get('url', 'http://127.0.0.1:11434').rstrip('/')
            model = cfg.get('model', 'qwen2.5vl:7b')
            timeout = float(cfg.get('timeoutSeconds', 30))

            ok, jpg = cv2.imencode('.jpg', frame_bgr,
                                   [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                return None
            image_b64 = base64.b64encode(jpg.tobytes()).decode()

            human = {'vest_missing': 'a person without a hi-vis vest',
                     'helmet_missing': 'a person without a helmet'}
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
            if not isinstance(verdict, dict) or 'vest' not in verdict:
                logger.warning(f"VLM verifier: malformed answer: {content[:200]}")
                return None
            return verdict
        except Exception as e:
            logger.warning(f"VLM verifier failed (fail-open): {e}")
            return None

    @staticmethod
    def confirms(verdict: dict, violation_type: str) -> bool:
        """True only if the VLM explicitly says this item is 'missing'.

        'present' and 'cannot_tell' both mean DO NOT fire this type.
        """
        field = _TYPE_FIELD.get(violation_type)
        return bool(field) and verdict.get(field) == 'missing'


vlm_verifier = VlmVerifier()
