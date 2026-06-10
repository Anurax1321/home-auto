"""Tiny JSON persistence helpers for runtime state (settings, triggers).

config.yaml is the hand-edited baseline; these files hold the bits the dashboard
can change at runtime. We keep them out of the YAML so editing from the UI never
rewrites the user's commented config, and we write atomically (write a temp file,
then rename) so a crash mid-write can't leave a half-written, unparsable file.

Nothing secret is ever stored here.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def data_dir() -> Path:
    """Directory for runtime state files.

    Defaults to ./data; override with the HOME_AUTO_DATA_DIR env var (handy for
    tests, which point it at a temp directory). The directory is created lazily
    by the writer, not here.
    """
    return Path(os.environ.get("HOME_AUTO_DATA_DIR", "data"))


def read_json(path: Path) -> object | None:
    """Return the parsed JSON at `path`, or None if it is missing/unreadable.

    A corrupt or unreadable file is treated as "no data" rather than crashing
    the service: the caller falls back to defaults.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        return None


def write_json(path: Path, data: object) -> None:
    """Atomically write `data` as JSON to `path`, creating parent dirs.

    Writes to a temp file in the same directory and renames it into place so a
    reader never sees a partially written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same-directory temp file guarantees the rename is atomic (same filesystem).
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        # Don't leave the temp file lying around if anything went wrong.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
