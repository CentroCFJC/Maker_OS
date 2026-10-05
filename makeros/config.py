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


@dataclass(frozen=True)
class Settings:
    """Runtime locations and secrets for one MakerOS instance."""

    content_dir: Path      # shared Markdown tree (git repo)
    private_dir: Path      # per-user private Markdown (never in shared git)
    templates_dir: Path    # content creation templates (project.md, task.md...)
    db_path: Path          # SQLite: index, users, sessions state
    secret_key: str        # session cookie signing key

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(__file__).resolve().parent.parent
        return cls(
            content_dir=_env_path("MAKEROS_CONTENT_DIR", root / "content"),
            private_dir=_env_path("MAKEROS_PRIVATE_DIR", root / "private"),
            templates_dir=_env_path("MAKEROS_TEMPLATES_DIR", root / "templates"),
            db_path=_env_path("MAKEROS_DB_PATH", root / "data" / "makeros.db"),
            secret_key=os.environ.get("MAKEROS_SECRET_KEY", "dev-insecure-change-me"),
        )
