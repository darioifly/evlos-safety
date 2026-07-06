"""
Face-only anonymization for saved alert screenshots.

Uses OpenCV's YuNet face detector (cv2.FaceDetectorYN) — a real face
detector that returns TIGHT face boxes, so ONLY the face is obscured; the
helmet, vest and body (the safety-relevant content) stay visible.

Design:
  * Detection runs twice for recall: once on the full frame, and once per
    person crop (upscaled), which recovers small/distant faces the
    full-frame pass misses. Both passes only ever blur ACTUAL detected
    faces — never a whole head or body.
  * Faces are pixelated (mosaic), which is irreversible, rather than
    Gaussian-blurred (which can sometimes be partially inverted).
  * Thread-safe: YuNet's detect() mutates detector state, so calls are
    serialized behind a lock (one shared instance across camera workers).
  * Degrades gracefully: if the model is missing or fails to load, blurring
    is disabled and logged once — screenshots are still saved (unblurred),
    the pipeline never crashes on this.
"""
import threading
from pathlib import Path

import cv2
import numpy as np

from utils.logger import logger

DEFAULT_MODEL_REL = "models/face/face_detection_yunet_2023mar.onnx"


def _iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class FaceBlurrer:
    """Detects and pixelates faces in-place. See module docstring."""

    def __init__(self, model_path=None, *, score_threshold=0.6,
                 nms_threshold=0.3, expand=0.15, blocks=10,
                 crop_upscale_to=320, max_upscale=4.0, detector=None):
        self.score_threshold = float(score_threshold)
        self.nms_threshold = float(nms_threshold)
        self.expand = float(expand)
        self.blocks = max(2, int(blocks))
        self.crop_upscale_to = int(crop_upscale_to)
        self.max_upscale = float(max_upscale)
        self._lock = threading.Lock()
        self._detector = detector  # injectable for tests
        self.enabled = True

        if self._detector is None:
            try:
                path = Path(model_path) if model_path else Path(__file__).parent.parent / DEFAULT_MODEL_REL
                if not path.exists():
                    raise FileNotFoundError(path)
                self._detector = cv2.FaceDetectorYN.create(
                    str(path), "", (320, 320),
                    self.score_threshold, self.nms_threshold, 5000,
                )
                logger.info(f"FaceBlurrer: YuNet loaded from {path}")
            except Exception as e:
                self.enabled = False
                logger.error(f"FaceBlurrer disabled (model load failed): {e}")

    # --- detection -----------------------------------------------------

    def _detect(self, img):
        """Return list of (x, y, w, h) face boxes in img coordinates."""
        h, w = img.shape[:2]
        if w < 10 or h < 10:
            return []
        with self._lock:
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(img)
        if faces is None:
            return []
        out = []
        for f in faces:
            out.append((int(f[0]), int(f[1]), int(f[2]), int(f[3])))
        return out

    def _detect_full(self, frame):
        H, W = frame.shape[:2]
        boxes = []
        for (x, y, w, h) in self._detect(frame):
            boxes.append((x, y, x + w, y + h))
        return boxes

    def _detect_in_person(self, frame, person_box):
        """Detect faces inside one person crop, upscaling small crops so
        distant faces become resolvable. Coords mapped back to the frame."""
        H, W = frame.shape[:2]
        px1 = max(0, int(person_box[0])); py1 = max(0, int(person_box[1]))
        px2 = min(W, int(person_box[2])); py2 = min(H, int(person_box[3]))
        if px2 - px1 < 12 or py2 - py1 < 12:
            return []
        crop = frame[py1:py2, px1:px2]
        ch, cw = crop.shape[:2]
        scale = 1.0
        shorter = min(cw, ch)
        if shorter < self.crop_upscale_to:
            scale = min(self.max_upscale, self.crop_upscale_to / shorter)
        if scale > 1.0:
            crop = cv2.resize(crop, (int(cw * scale), int(ch * scale)),
                              interpolation=cv2.INTER_LINEAR)
        boxes = []
        for (x, y, w, h) in self._detect(crop):
            fx1 = px1 + x / scale
            fy1 = py1 + y / scale
            fx2 = px1 + (x + w) / scale
            fy2 = py1 + (y + h) / scale
            boxes.append((fx1, fy1, fx2, fy2))
        return boxes

    # --- blurring ------------------------------------------------------

    def _pixelate(self, frame, box):
        H, W = frame.shape[:2]
        x1, y1, x2, y2 = box
        # Expand a little so the whole face is covered, then clamp.
        bw = x2 - x1
        bh = y2 - y1
        x1 = int(max(0, x1 - bw * self.expand))
        y1 = int(max(0, y1 - bh * self.expand))
        x2 = int(min(W, x2 + bw * self.expand))
        y2 = int(min(H, y2 + bh * self.expand))
        if x2 <= x1 or y2 <= y1:
            return False
        roi = frame[y1:y2, x1:x2]
        rh, rw = roi.shape[:2]
        # Downscale to a fixed number of blocks across the face width, then
        # nearest-neighbour up: a coarse mosaic that anonymizes any face size.
        cells_x = min(self.blocks, rw)
        cells_y = max(1, int(cells_x * rh / rw)) if rw else 1
        small = cv2.resize(roi, (max(1, cells_x), max(1, cells_y)),
                           interpolation=cv2.INTER_LINEAR)
        mosaic = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
        frame[y1:y2, x1:x2] = mosaic
        return True

    def blur_faces(self, frame, person_boxes=None):
        """Detect and pixelate every face in `frame` IN PLACE.

        Returns the number of faces blurred. Never raises on detection
        failure — logs and returns what it managed to blur.
        """
        if not self.enabled or frame is None or frame.size == 0:
            return 0
        try:
            candidates = list(self._detect_full(frame))
            for pb in (person_boxes or []):
                candidates.extend(self._detect_in_person(frame, pb))
        except Exception as e:
            logger.warning(f"FaceBlurrer detection error: {e}")
            return 0

        # Deduplicate overlapping detections from the two passes.
        merged = []
        for box in sorted(candidates, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
            if all(_iou(box, m) < 0.3 for m in merged):
                merged.append(box)

        blurred = 0
        for box in merged:
            if self._pixelate(frame, box):
                blurred += 1
        return blurred
