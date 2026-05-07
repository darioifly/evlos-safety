"""F-002: MJPEG parser hardening - buffer cap, find ordering, recovery."""
from services.video_worker_manager import _extract_jpeg, MJPEG_BUFFER_MAX_BYTES


SOI = b"\xff\xd8"
EOI = b"\xff\xd9"


def test_extract_clean_frame():
    frame = SOI + b"PAYLOAD" + EOI
    jpeg, rest = _extract_jpeg(b"junk" + frame + b"trailing")
    assert jpeg == frame
    assert rest == b"trailing"


def test_eoi_before_soi_is_recovered():
    """The classic find() ordering bug: EOI from a previous frame appears
    before the next SOI. Parser must NOT slice [a:b+2] with b<a."""
    buf = EOI + b"garbage" + SOI + b"PAYLOAD" + EOI
    jpeg, rest = _extract_jpeg(buf)
    # First call should drop the stray EOI; second call returns the frame.
    assert jpeg is None
    jpeg2, rest2 = _extract_jpeg(rest)
    assert jpeg2 == SOI + b"PAYLOAD" + EOI
    assert rest2 == b""


def test_partial_frame_returns_no_jpeg_keeps_buffer():
    buf = SOI + b"only-soi-no-eoi-yet"
    jpeg, rest = _extract_jpeg(buf)
    assert jpeg is None
    assert rest == buf


def test_buffer_cap_resets_to_last_soi():
    """At the cap, parser must drop everything before the last SOI to recover
    instead of leaking memory or reconnecting unnecessarily."""
    junk = b"x" * (MJPEG_BUFFER_MAX_BYTES + 100)
    tail = SOI + b"PARTIAL"
    over = junk + tail
    jpeg, rest = _extract_jpeg(over)
    assert jpeg is None
    assert rest == tail


def test_buffer_cap_full_reset_when_no_soi():
    over = b"x" * (MJPEG_BUFFER_MAX_BYTES + 100)
    jpeg, rest = _extract_jpeg(over)
    assert jpeg is None
    assert rest == b""
