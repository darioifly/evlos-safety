"""No secret may live in a git-tracked file.

The NX admin password shipped as a default in config.py (and in .env.example,
QUICKSTART.md, test_yolo_stream.py) until 30/07/2026. It now comes only from
the gitignored .env.
"""
from pathlib import Path

from config import Settings, ENV_FILE


def test_nx_password_has_no_default_in_tracked_source():
    """The password belongs in .env (gitignored), never in config.py."""
    assert Settings.model_fields["NX_ADMIN_PASSWORD"].default == ""


def test_env_file_is_resolved_from_the_package_not_the_cwd():
    """A cwd-relative env_file silently yields an empty config - and now that
    the password has no fallback, an empty config means every NX call 401s."""
    assert Path(ENV_FILE).is_absolute()
    assert Path(ENV_FILE).name == ".env"
