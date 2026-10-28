"""Application settings.

All runtime configuration comes from environment variables so the same
code runs unchanged in dev, Docker, and the lab machine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes")


def _env_url(name: str) -> str:
    """Normalized external base URL without trailing slash ('' if unset)."""
    value = os.environ.get(name, "").strip().rstrip("/")
    return value


@dataclass(frozen=True)
class Settings:
    """Runtime locations and secrets for one MakerOS instance."""

    content_dir: Path      # shared Markdown tree (git repo)
    private_dir: Path      # per-user private Markdown (never in shared git)
    templates_dir: Path    # content creation templates (project.md, task.md...)
    db_path: Path          # SQLite: index, users, sessions state
    secret_key: str        # session cookie signing key
    base_url: str = ""              # external base URL ('' = derive from request)
    cookie_secure: bool = False     # session cookie Secure flag (true behind HTTPS)
    google_client_id: str = ""      # Google OAuth (Calendar sync); empty = feature off
    google_client_secret: str = ""
    google_redirect_uri: str = ""   # default: {base_url}/google/callback

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(__file__).resolve().parent.parent
        return cls(
            content_dir=_env_path("MAKEROS_CONTENT_DIR", root / "content"),
            private_dir=_env_path("MAKEROS_PRIVATE_DIR", root / "private"),
            templates_dir=_env_path("MAKEROS_TEMPLATES_DIR", root / "templates"),
            db_path=_env_path("MAKEROS_DB_PATH", root / "data" / "makeros.db"),
            secret_key=os.environ.get("MAKEROS_SECRET_KEY", "dev-insecure-change-me"),
            base_url=_env_url("MAKEROS_BASE_URL"),
            cookie_secure=_env_bool("MAKEROS_COOKIE_SECURE"),
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=os.environ.get("GOOGLE_REDIRECT_URI", "").strip(),
        )
