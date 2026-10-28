"""Calendar event store: SQLite rows in Google Calendar API format.

Calendar events are NOT Markdown pages (user decision): they live in
the `calendar_events` table, mirroring Google's event JSON so two-way
sync is a direct mapping with no format translation. Events created
here get a `local-<id>` primary key until the background push returns
Google's real id.

Start/end are stored exactly as Google does:
  {"date": "2026-10-21"}                       (all-day)
  {"dateTime": "2026-10-21T17:06:00-05:00", "timeZone": "..."}  (timed)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from datetime import date, datetime

from ..db import connect

LOCAL_PREFIX = "local-"
DEFAULT_TZ = "America/Bogota"

SCHEMA = """
CREATE TABLE IF NOT EXISTS calendar_events (
    id          TEXT PRIMARY KEY,   -- Google id, or "local-<uuid>" until pushed
    summary     TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    start_json  TEXT NOT NULL DEFAULT '{}',
    end_json    TEXT NOT NULL DEFAULT '{}',
    category    TEXT NOT NULL DEFAULT '',
    people       TEXT NOT NULL DEFAULT '',   -- comma-separated person slugs
    status      TEXT NOT NULL DEFAULT 'confirmed',
    updated     TEXT NOT NULL DEFAULT '',
    html_link   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS event_categories (
    id     TEXT PRIMARY KEY,
    label  TEXT NOT NULL,
    color  TEXT NOT NULL DEFAULT '#6d6c68'
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def to_google_when(value: str | date | datetime) -> dict:
    """MakerOS form value ('2026-10-21' or '2026-10-21 17:06') -> Google JSON."""
    if isinstance(value, dict):
        return value
    text = str(value).strip()
    if not text:
        return {}
    if " " in text or "T" in text:
        text = text.replace("T", " ")
        dt = datetime.fromisoformat(text)
        return {"dateTime": dt.isoformat(), "timeZone": DEFAULT_TZ}
    return {"date": text}


def _when_objects(start_json: dict, end_json: dict) -> tuple[object, object]:
    def parse(when: dict):
        if not when:
            return None
        if "dateTime" in when:
            try:
                return datetime.fromisoformat(when["dateTime"])
            except ValueError:
                return None
        if "date" in when:
            try:
                return date.fromisoformat(when["date"])
            except ValueError:
                return None
        return None

    return parse(start_json), parse(end_json)


def create_local_event(
    conn: sqlite3.Connection,
    summary: str,
    start: str,
    end: str = "",
    location: str = "",
    description: str = "",
    category: str = "",
    people: str = "",
) -> str:
    """Insert an event born in MakerOS; pushed to Google on the next sync."""
    event_id = f"{LOCAL_PREFIX}{uuid.uuid4().hex[:20]}"
    start_json = to_google_when(start)
    end_json = to_google_when(end) if end and end.strip() else dict(start_json)
    conn.execute(
        "INSERT INTO calendar_events (id, summary, location, description,"
        " start_json, end_json, category, people, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')",
        (event_id, summary.strip(), location.strip(), description.strip(),
         json.dumps(start_json), json.dumps(end_json), category.strip(),
         people.strip()),
    )
    conn.commit()
    return event_id


def upsert_from_google(conn: sqlite3.Connection, event: dict) -> None:
    """Store/update one event from a Google Calendar API response."""
    if not event.get("id"):
        return
    private = (event.get("extendedProperties") or {}).get("private", {})
    category = private.get("category", "")
    people = private.get("people", "")
    conn.execute(
        "INSERT INTO calendar_events (id, summary, location, description,"
        " start_json, end_json, category, people, status, updated, html_link)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET"
        "   summary=excluded.summary, location=excluded.location,"
        "   description=excluded.description, start_json=excluded.start_json,"
        "   end_json=excluded.end_json, category=excluded.category,"
        "   people=excluded.people, status=excluded.status,"
        "   updated=excluded.updated, html_link=excluded.html_link",
        (
            event["id"],
            event.get("summary", ""),
            event.get("location", "") or "",
            event.get("description", "") or "",
            json.dumps(event.get("start") or {}),
            json.dumps(event.get("end") or {}),
            category,
            people,
            event.get("status", "confirmed"),
            event.get("updated", ""),
            event.get("htmlLink", "") or "",
        ),
    )
    conn.commit()


def replace_local_id(conn: sqlite3.Connection, local_id: str, google_event: dict) -> None:
    """After a successful push: swap the local id for Google's."""
    conn.execute("DELETE FROM calendar_events WHERE id = ?", (local_id,))
    conn.commit()
    upsert_from_google(conn, google_event)


def get_event(conn: sqlite3.Connection, event_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM calendar_events WHERE id = ?", (event_id,)
    ).fetchone()
    if row is None:
        return None
    start, end = _when_objects(
        json.loads(row["start_json"] or "{}"),
        json.loads(row["end_json"] or "{}"),
    )
    return {
        "id": row["id"],
        "summary": row["summary"],
        "location": row["location"],
        "description": row["description"],
        "category": row["category"],
        "people": row["people"],
        "status": row["status"],
        "updated": row["updated"],
        "html_link": row["html_link"],
        "start": start,
        "end": end,
    }


def delete_event(conn: sqlite3.Connection, event_id: str) -> None:
    conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
    conn.commit()


def iter_events(conn: sqlite3.Connection) -> Iterator[dict]:
    """All confirmed events with parsed start/end (date or datetime)."""
    rows = conn.execute(
        "SELECT * FROM calendar_events WHERE status != 'cancelled' ORDER BY id"
    ).fetchall()
    for row in rows:
        start, end = _when_objects(
            json.loads(row["start_json"] or "{}"),
            json.loads(row["end_json"] or "{}"),
        )
        if start is None:
            continue
        yield {
            "id": row["id"],
            "summary": row["summary"],
            "location": row["location"],
            "description": row["description"],
            "category": row["category"],
            "html_link": row["html_link"],
            "start": start,
            "end": end,
        }


def unsynced_local_ids(conn: sqlite3.Connection) -> list[str]:
    """Events born here that still need their first push to Google."""
    return [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM calendar_events WHERE id LIKE ?", (LOCAL_PREFIX + "%",)
        ).fetchall()
    ]


def migrate_from_documents(conn: sqlite3.Connection, content_dir) -> int:
    """One-time move: old Markdown calendar pages -> event rows.

    Old frontmatter dates ('2026-10-21 17:06') convert to Google
    format. The source files are deleted: the calendar is not Markdown
    anymore. Returns how many events were migrated.
    """
    from ..frontmatter import read
    from ..indexer import list_collection, remove_document

    count = 0
    for doc in list_collection(conn, "calendario"):
        meta, _ = read(content_dir / f"{doc['path']}.md")
        event_id = meta.get("gcal_id") or f"{LOCAL_PREFIX}{uuid.uuid4().hex[:20]}"
        start_json = to_google_when(meta.get("start", ""))
        end_json = to_google_when(meta.get("end", "")) if meta.get("end") else {}
        if not start_json:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO calendar_events"
            " (id, summary, location, description, start_json, end_json,"
            "  category, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed')",
            (
                event_id,
                meta.get("title", doc["title"] or "Evento"),
                meta.get("location", "") or "",
                "",
                json.dumps(start_json),
                json.dumps(end_json),
                meta.get("category", "") or "",
            ),
        )
        conn.commit()
        path = content_dir / f"{doc['path']}.md"
        if path.is_file():
            path.unlink()
        remove_document(conn, doc["path"])
        count += 1
    return count


def event_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0]


def open_db(db_path) -> sqlite3.Connection:
    conn = connect(db_path)
    ensure_schema(conn)
    return conn


# ---------- Event categories ----------

# Palette offered in the admin panel (drawn from the logo + supporting hues).
CATEGORY_PALETTE = (
    "#e42c45",  # brand red
    "#f4991f",  # logo orange
    "#29265b",  # logo indigo
    "#3d8a52",  # green
    "#3b6fb5",  # blue
    "#2c7d7d",  # teal
    "#7a4f9e",  # purple
    "#6d6c68",  # gray
)

DEFAULT_CATEGORIES = (
    ("reunion", "Reunión", "#e42c45"),
    ("taller", "Taller", "#f4991f"),
    ("proyecto", "Proyecto", "#29265b"),
    ("otro", "Otro", "#6d6c68"),
)


def seed_categories(conn: sqlite3.Connection) -> None:
    """First-run defaults; existing installations keep their own set."""
    if conn.execute("SELECT COUNT(*) FROM event_categories").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO event_categories (id, label, color) VALUES (?, ?, ?)",
            DEFAULT_CATEGORIES,
        )
        conn.commit()


def list_categories(conn: sqlite3.Connection) -> list[dict]:
    seed_categories(conn)
    return [
        {"id": row["id"], "label": row["label"], "color": row["color"]}
        for row in conn.execute(
            "SELECT id, label, color FROM event_categories ORDER BY id"
        ).fetchall()
    ]


def add_category(conn: sqlite3.Connection, label: str, color: str) -> str | None:
    """Insert a category; returns its id, or None if the color is bad."""
    if color not in CATEGORY_PALETTE:
        return None
    slug = label.strip().lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-").strip("-") or "cat"
    base, n = slug, 2
    while conn.execute(
        "SELECT 1 FROM event_categories WHERE id = ?", (slug,)
    ).fetchone():
        slug = f"{base}-{n}"
        n += 1
    conn.execute(
        "INSERT INTO event_categories (id, label, color) VALUES (?, ?, ?)",
        (slug, label.strip() or slug, color),
    )
    conn.commit()
    return slug


def delete_category(conn: sqlite3.Connection, category_id: str) -> None:
    """Events keep the raw string; they render as 'Otro' once it's gone."""
    conn.execute("DELETE FROM event_categories WHERE id = ?", (category_id,))
    conn.execute("UPDATE calendar_events SET category = '' WHERE category = ?", (category_id,))
    conn.commit()
