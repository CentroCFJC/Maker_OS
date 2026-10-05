"""UI customization overrides (sidebar icons per collection, etc.).

Lives in SQLite (`ui_settings`), not Markdown: these describe app chrome
rather than lab content. Keys are namespaced ('icon:<collection>');
values are validated against the icon registry before writing.
"""

from __future__ import annotations

import sqlite3

from .collections import COLLECTIONS
from .web.icons import is_valid_icon

_ICON_PREFIX = "icon:"


def get_ui(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM ui_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_ui(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert one override. Empty value deletes the row (back to default)."""
    if value:
        conn.execute(
            "INSERT INTO ui_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    else:
        conn.execute("DELETE FROM ui_settings WHERE key = ?", (key,))
    conn.commit()


def collection_icons(conn: sqlite3.Connection) -> dict[str, str]:
    """Effective icon per collection: user override over the code default."""
    icons = {slug: info.get("icon", "") for slug, info in COLLECTIONS.items()}
    rows = conn.execute(
        "SELECT key, value FROM ui_settings WHERE key LIKE ?", (_ICON_PREFIX + "%",)
    ).fetchall()
    for row in rows:
        slug = row["key"][len(_ICON_PREFIX):]
        if slug in icons and is_valid_icon(row["value"]):
            icons[slug] = row["value"]
    return icons
