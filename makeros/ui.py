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

# Admin-selectable themes: accent (logo palette) + background style.
THEME_ACCENTS = ("rojo", "indigo", "naranja")
THEME_BGS = ("blanco", "suave", "cuadricula")


def theme_accent(conn: sqlite3.Connection) -> str:
    value = get_ui(conn, "theme:accent")
    return value if value in THEME_ACCENTS else "rojo"


def theme_bg(conn: sqlite3.Connection) -> str:
    value = get_ui(conn, "theme:background")
    return value if value in THEME_BGS else "blanco"


# Sidebar "Bases de datos" entries a user may reorder. Collection slugs
# resolve through COLLECTIONS; the rest are fixed chrome entries.
NAV_FIXED = (
    ("inicio", "Inicio", "home", "/"),
    ("explorador", "Explorador", "folder", "/explorador"),
    ("notas", "Mis notas", "lock", "/notas"),
    ("asistente", "Asistente", "cpu", "/asistente"),
)
_NAV_KEY = "nav:"


def nav_ids(conn: sqlite3.Connection, user) -> list[str]:
    """Saved per-user sidebar order (default order for missing entries)."""
    default = ["inicio", *[s for s in COLLECTIONS if s not in ("people", "exhibits", "avisos")],
               "explorador", "notas", "asistente"]
    if user is None:
        return default
    raw = get_ui(conn, _NAV_KEY + user["username"], "")
    saved = [part for part in raw.split(",") if part]
    known = set(default)
    ordered = [entry for entry in saved if entry in known]
    ordered += [entry for entry in default if entry not in ordered]
    return ordered


def set_nav_order(conn: sqlite3.Connection, user, ids: list[str]) -> None:
    """Persist one user's sidebar order (validated against nav_ids)."""
    known = set(nav_ids(conn, None))
    clean = [entry for entry in ids if entry in known]
    if len(clean) != len(known):
        raise ValueError("orden incompleto")
    set_ui(conn, _NAV_KEY + user["username"], ",".join(clean))


def nav_items(conn: sqlite3.Connection, user) -> list[dict]:
    """Sidebar entries in this user's order, ready for the template."""
    icons = collection_icons(conn)
    fixed = {entry_id: (label, icon, href) for entry_id, label, icon, href in NAV_FIXED}
    items = []
    for entry_id in nav_ids(conn, user):
        if entry_id in fixed:
            label, icon, href = fixed[entry_id]
        else:
            info = COLLECTIONS[entry_id]
            label, href = info["label"], f"/{entry_id}"
            icon = icons.get(entry_id, info.get("icon", ""))
        items.append({"id": entry_id, "label": label, "icon": icon, "href": href})
    return items
