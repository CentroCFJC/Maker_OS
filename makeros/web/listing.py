"""Collection listing helpers shared by index pages and the dashboard.

All data comes from the SQLite index (meta_json), so these are read-only
views over the Markdown source of truth.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from ..indexer import list_collection
from .calendar import DayItem, day_map, parse_when


def date_span(meta: dict) -> str:
    """Compact 'start → due' label for list rows and cards (projects)."""
    start = parse_when(meta.get("start"))
    due = parse_when(meta.get("due"))
    if start is None and due is None:
        return ""
    start_s = start.strftime("%Y-%m-%d") if start else ""
    due_s = due.strftime("%Y-%m-%d") if due else ""
    if start_s and due_s:
        return f"{start_s} → {due_s}"
    return start_s or due_s


def collection_items(conn: sqlite3.Connection, collection: str) -> list[dict]:
    """Everything an index card/row needs, parsed from meta_json."""
    items = []
    for row in list_collection(conn, collection):
        meta = json.loads(row["meta_json"] or "{}")
        items.append(
            {
                "path": row["path"],
                "title": row["title"],
                "indexed_at": row["indexed_at"],
                "icon": meta.get("icon"),
                "dates": date_span(meta),
                "status": str(meta.get("status") or ""),
                "project": str(meta.get("project") or ""),
                "banner": str(meta.get("banner") or ""),
            }
        )
    return items


def unassigned_tasks(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Tasks with no project, grouped by status, in canonical order."""
    groups: dict[str, list[dict]] = {key: [] for key in ("todo", "doing", "done")}
    for item in collection_items(conn, "tasks"):
        if item["project"]:
            continue
        groups.setdefault(item["status"], []).append(item)
    return groups


def todays_events(conn: sqlite3.Connection) -> list[DayItem]:
    """Calendar events landing on today (sidebar 'Para hoy' section)."""
    return day_map(conn).get(date.today(), [])
