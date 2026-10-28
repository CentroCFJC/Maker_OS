"""Backups: timestamped zip snapshots of the whole instance.

One backup = `content/` (Markdown + uploads), `private/`, `templates/`
and a safe copy of the SQLite database, zipped under
`data/backups/`. Everything needed to restore a running instance.
Backups live outside `content/` so the watcher never indexes them.

Recurring schedule + retention live in `ui_settings`:
`backup:interval_hours` (0 = off), `backup:keep`, `backup:last_at`.
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .ui import get_ui, set_ui

INTERVALS = (
    ("0", "Desactivado"),
    ("1", "Cada hora"),
    ("6", "Cada 6 horas"),
    ("12", "Cada 12 horas"),
    ("24", "Cada día"),
    ("168", "Cada semana"),
)

_NAME_PREFIX = "makeros-backup-"


def backups_dir(settings: Settings) -> Path:
    directory = settings.db_path.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def interval_hours(conn: sqlite3.Connection) -> int:
    raw = get_ui(conn, "backup:interval_hours", "0")
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def keep_count(conn: sqlite3.Connection) -> int:
    raw = get_ui(conn, "backup:keep", "10")
    try:
        return max(1, int(raw))
    except ValueError:
        return 10


def save_schedule(conn: sqlite3.Connection, hours: int, keep: int) -> None:
    set_ui(conn, "backup:interval_hours", str(hours))
    set_ui(conn, "backup:keep", str(keep))


def _copy_db(settings: Settings, target: Path) -> None:
    """Snapshot the live database with SQLite's online backup API."""
    src = sqlite3.connect(settings.db_path)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def create_backup(settings: Settings) -> Path:
    """Write one timestamped zip and prune old ones. Returns the zip path."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    directory = backups_dir(settings)
    destination = directory / f"{_NAME_PREFIX}{stamp}.zip"
    counter = 2
    while destination.exists():  # two runs within the same second
        destination = directory / f"{_NAME_PREFIX}{stamp}-{counter}.zip"
        counter += 1
    roots = (
        ("content", settings.content_dir),
        ("private", settings.private_dir),
        ("templates", settings.templates_dir),
    )

    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        db_copy = Path(tmp) / "makeros.db"
        _copy_db(settings, db_copy)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_copy, "data/makeros.db")
            for arcname, root in roots:
                if not root.exists():
                    continue
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        zf.write(path, f"{arcname}/{path.relative_to(root)}")

    return destination


def record_run(conn: sqlite3.Connection) -> None:
    set_ui(conn, "backup:last_at", str(int(time.time())))


def prune(settings: Settings, keep: int) -> int:
    """Delete the oldest zips beyond `keep`. Returns how many were removed."""
    zips = sorted(backups_dir(settings).glob(f"{_NAME_PREFIX}*.zip"))
    for path in zips[:-keep] if keep > 0 else zips:
        path.unlink(missing_ok=True)
    return max(0, len(zips) - keep)


def list_backups(settings: Settings) -> list[dict]:
    """Newest first."""
    items = []
    for path in sorted(backups_dir(settings).glob(f"{_NAME_PREFIX}*.zip"), reverse=True):
        created = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        items.append(
            {
                "name": path.name,
                "size_mb": path.stat().st_size / (1024 * 1024),
                "created": created.strftime("%Y-%m-%d %H:%M"),
            }
        )
    return items


def due(conn: sqlite3.Connection, settings: Settings) -> bool:
    """Is a recurring backup overdue?"""
    hours = interval_hours(conn)
    if hours == 0:
        return False
    last = get_ui(conn, "backup:last_at", "")
    try:
        last_at = int(last)
    except ValueError:
        return True
    return time.time() - last_at >= hours * 3600
