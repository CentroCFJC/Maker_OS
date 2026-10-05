"""Collection listing helpers shared by index pages and the dashboard.

All data comes from the SQLite index (meta_json + body), so these are
read-only views over the Markdown source of truth.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date

from ..indexer import list_collection
from .calendar import DayItem, day_map, parse_when, to_day

_CHECK_DONE = re.compile(r"^\s*[-*+]\s*\[[xX]\]", re.MULTILINE)
_CHECK_OPEN = re.compile(r"^\s*[-*+]\s*\[\s\]", re.MULTILINE)


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


def extract(body: str, limit: int = 160) -> str:
    """One-line plain-text excerpt of a Markdown body for cards."""
    text = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    text = re.sub(r"!?\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#>*_`|]+", " ", text)
    text = re.sub(r"^\s*[-*+]\s*\[[xX\s]\]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def check_progress(body: str) -> tuple[int, int]:
    """(done, total) checklist items inside a page body."""
    done = len(_CHECK_DONE.findall(body))
    return done, done + len(_CHECK_OPEN.findall(body))


def project_task_stats(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """Per-project-slug task counts by status (mini kanban summary)."""
    stats: dict[str, dict[str, int]] = {}
    for row in list_collection(conn, "tasks"):
        meta = json.loads(row["meta_json"] or "{}")
        slug = str(meta.get("project") or "")
        if not slug:
            continue
        bucket = stats.setdefault(slug, {"todo": 0, "doing": 0, "done": 0, "total": 0})
        status = str(meta.get("status") or "todo")
        bucket[status] = bucket.get(status, 0) + 1
        bucket["total"] += 1
    return stats


def collection_items(
    conn: sqlite3.Connection, collection: str, task_stats: dict | None = None
) -> list[dict]:
    """Everything an index card/row needs, parsed from meta_json + body."""
    items = []
    for row in list_collection(conn, collection):
        meta = json.loads(row["meta_json"] or "{}")
        due = parse_when(meta.get("due"))
        item = {
            "path": row["path"],
            "title": row["title"],
            "indexed_at": row["indexed_at"],
            "icon": meta.get("icon"),
            "dates": date_span(meta),
            "status": str(meta.get("status") or ""),
            "project": str(meta.get("project") or ""),
            "banner": str(meta.get("banner") or ""),
            "extract": extract(row["body"] or ""),
            "vencido": bool(due and to_day(due) < date.today()),
        }
        done, total = check_progress(row["body"] or "")
        if total:
            item["checks_done"], item["checks_total"] = done, total
        if collection == "projects" and task_stats is not None:
            slug = row["path"].split("/")[1] if "/" in row["path"] else ""
            item["tasks"] = task_stats.get(slug, {"total": 0, "done": 0})
        items.append(item)
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
