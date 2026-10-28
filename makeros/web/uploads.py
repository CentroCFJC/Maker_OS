"""Shared upload storage for page banners and user avatars.

Files land in `content/_uploads/` (login-gated behind /media/). All
writes go through here so traversal protection lives in one place.
"""

from __future__ import annotations

from pathlib import Path

UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def uploads_dir(settings) -> Path:
    uploads = settings.content_dir / "_uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


def safe_upload_path(settings, name: str) -> Path | None:
    """Resolve a /media/ name inside the uploads dir, blocking traversal."""
    uploads = uploads_dir(settings).resolve()
    target = (uploads / name).resolve()
    if target == uploads or uploads not in target.parents:
        return None
    return target
