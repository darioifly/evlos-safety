"""FaceBlurrer: geometry, pixelation and dedup with an injected fake detector.

The real YuNet model is exercised separately on hardware (validate_faceblur.py);
these tests cover the logic that surrounds it, deterministically.
"""
import numpy as np
import pytest

from services.face_blur import FaceBlurrer, _iou


class FakeDetector:
    """Stand-in for cv2.FaceDetectorYN.

    Returns face boxes (x, y, w, h, ...) whose coordinates are given in the
    space of whatever image size was last set via setInputSize — matching
    the real detector's contract.
    """
    def __init__(self, faces_by_size):
        # {(w, h): [(x, y, fw, fh), ...]}
        self.faces_by_size = faces_by_size
        self._size = None

    def setInputSize(self, size):
        self._size = tuple(size)

    def detect(self, img):
        faces = self.faces_by_size.get(self._size, [])
        if not faces:
            return 1, None
        arr = np.array([[x, y, w, h] + [0.0] * 10 + [0.9] for (x, y, w, h) in faces],
                       dtype=np.float32)
        return 1, arr


def _solid(w, h, value=127):
    return np.full((h, w, 3), value, dtype=np.uint8)


def _put_face(frame, x, y, w, h):
    """Draw a high-contrast pattern where a 'face' is, so pixelation is
    detectable as a change in local variance."""
    for i in range(y, y + h, 2):
        frame[i:i + 1, x:x + w] = 255
    return frame


def test_iou_basic():
    assert _iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert _iou((0, 0, 10, 10), (100, 100, 110, 110)) == 0.0


def test_blurs_detected_face_only():
    frame = _solid(200, 200, 100)
    _put_face(frame, 50, 40, 40, 40)
    before = frame.copy()
    det = FakeDetector({(200, 200): [(50, 40, 40, 40)]})
    fb = FaceBlurrer(detector=det, blocks=4)
    n = fb.blur_faces(frame)
    assert n == 1
    # Face region changed...
    assert not np.array_equal(before[40:80, 50:90], frame[40:80, 50:90])
    # ...but a far-away region did not.
    assert np.array_equal(before[150:190, 150:190], frame[150:190, 150:190])


def test_no_faces_leaves_frame_untouched():
    frame = _solid(200, 200)
    before = frame.copy()
    fb = FaceBlurrer(detector=FakeDetector({}), blocks=4)
    assert fb.blur_faces(frame) == 0
    assert np.array_equal(before, frame)


def test_disabled_when_model_missing(tmp_path):
    fb = FaceBlurrer(model_path=str(tmp_path / "nope.onnx"))
    assert fb.enabled is False
    frame = _solid(100, 100)
    before = frame.copy()
    assert fb.blur_faces(frame) == 0
    assert np.array_equal(before, frame)


def test_person_crop_pass_recovers_small_face():
    # No face at full-frame scale, but one inside the (upscaled) person crop.
    frame = _solid(400, 400, 90)
    # Person occupies (100,100)-(180,300); upscaled crop is 80x200 -> >=320.
    # crop shorter side = 80 -> scale = 320/80 = 4 -> crop size (320, 800).
    det = FakeDetector({
        (400, 400): [],
        (320, 800): [(40, 40, 60, 60)],  # face inside the upscaled crop
    })
    fb = FaceBlurrer(detector=det, blocks=4, crop_upscale_to=320)
    # Mapped-back face ~ (110, 110), 15x15 — give it a pattern so the mosaic
    # is a detectable change.
    _put_face(frame, 110, 110, 15, 15)
    before = frame.copy()
    n = fb.blur_faces(frame, person_boxes=[[100, 100, 180, 300]])
    assert n == 1
    assert not np.array_equal(before[108:128, 108:128], frame[108:128, 108:128])


def test_dedup_across_passes():
    # Same face found by both the full-frame and the crop pass -> blurred once.
    frame = _solid(400, 400, 90)
    det = FakeDetector({
        (400, 400): [(120, 120, 40, 40)],
        (320, 800): [(80, 80, 160, 160)],  # maps back to ~ (120,120)-(160,160)
    })
    fb = FaceBlurrer(detector=det, blocks=4, crop_upscale_to=320)
    n = fb.blur_faces(frame, person_boxes=[[100, 100, 180, 300]])
    assert n == 1


def test_expand_clamps_at_edges():
    frame = _solid(60, 60, 100)
    # Face flush against the top-left corner; expansion must clamp, not crash.
    det = FakeDetector({(60, 60): [(0, 0, 20, 20)]})
    fb = FaceBlurrer(detector=det, blocks=4, expand=0.5)
    assert fb.blur_faces(frame) == 1
