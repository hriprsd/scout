"""Content-addressed hashing for card invalidation."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except (OSError, PermissionError):
        return "unreadable"
    return h.hexdigest()[:12]
