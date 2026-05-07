"""F-009: screenshot file cleanup walks dirs and respects retention."""
import os
import time

from utils.screenshot import cleanup_screenshot_dir


def test_cleanup_deletes_old_files(tmp_path):
    old = tmp_path / "old.jpg"
    new = tmp_path / "new.jpg"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    eight_days_ago = time.time() - 8 * 86400
    os.utime(old, (eight_days_ago, eight_days_ago))

    deleted = cleanup_screenshot_dir(tmp_path, days=7)
    assert deleted == 1
    assert not old.exists()
    assert new.exists()


def test_cleanup_missing_dir_returns_zero(tmp_path):
    assert cleanup_screenshot_dir(tmp_path / "does-not-exist", days=7) == 0


def test_cleanup_skips_subdirs(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "inner.jpg").write_bytes(b"x")
    old_file = tmp_path / "old.jpg"
    old_file.write_bytes(b"x")
    eight_days_ago = time.time() - 8 * 86400
    os.utime(old_file, (eight_days_ago, eight_days_ago))

    deleted = cleanup_screenshot_dir(tmp_path, days=7)
    assert deleted == 1
    assert not old_file.exists()
    assert (sub / "inner.jpg").exists()
