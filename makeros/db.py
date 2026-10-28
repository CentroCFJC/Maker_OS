"""SQLite storage layer: connection factory and schema.

SQLite holds only derived or private state (index, users, sessions,
later: activity log and vault). The Markdown tree remains the source of
truth for everything narrative.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'member'
                  CHECK (role IN ('admin', 'member', 'viewer')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT UNIQUE NOT NULL,   -- relative to content/, no extension
    collection TEXT NOT NULL,          -- top-level dir: wiki, projects, tasks...
    title      TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    meta_json  TEXT NOT NULL DEFAULT '{}',
    mtime      REAL NOT NULL DEFAULT 0,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ui_settings (
    key   TEXT PRIMARY KEY,             -- e.g. 'icon:wiki' (sidebar overrides)
    value TEXT NOT NULL
);

-- Calendar events live here (NOT Markdown): Google Calendar API
-- format, synced both ways with the connected Google calendar.
CREATE TABLE IF NOT EXISTS calendar_events (
    id          TEXT PRIMARY KEY,      -- Google id, or "local-<uuid>" until pushed
    summary     TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    start_json  TEXT NOT NULL DEFAULT '{}',  -- {"date": "..."} | {"dateTime": "..."}
    end_json    TEXT NOT NULL DEFAULT '{}',
    category    TEXT NOT NULL DEFAULT '',    -- event_categories.id
    status      TEXT NOT NULL DEFAULT 'confirmed',
    updated     TEXT NOT NULL DEFAULT '',
    html_link   TEXT NOT NULL DEFAULT ''
);

-- User-manageable event categories with a display color (logo palette).
CREATE TABLE IF NOT EXISTS event_categories (
    id     TEXT PRIMARY KEY,   -- slug, e.g. 'taller' (stable across Google sync)
    label  TEXT NOT NULL,
    color  TEXT NOT NULL DEFAULT '#6d6c68'
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, body,
    content = 'documents',
    content_rowid = 'id'
);

-- Keep the FTS index in sync with the documents table.
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts (rowid, title, body)
    VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts (documents_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts (documents_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
    INSERT INTO documents_fts (rowid, title, body)
    VALUES (new.id, new.title, new.body);
END;
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a SQLite connection with the settings MakerOS relies on.

    Callers own the connection and close it when done (per-request or
    per-thread). `check_same_thread=False` is safe because each
    connection is handed off, never shared concurrently: FastAPI runs
    sync dependencies and handlers in a thread pool, so the creating
    thread and the using thread can differ, but access stays serialized.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables, FTS index and triggers if missing."""
    conn.executescript(SCHEMA)
    # Lightweight migrations for databases created before the column
    # existed (ALTER TABLE has no IF NOT EXISTS for columns).
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "avatar" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT ''")
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(calendar_events)")}
    if "category" not in columns:
        conn.execute("ALTER TABLE calendar_events ADD COLUMN category TEXT NOT NULL DEFAULT ''")
    if "people" not in columns:
        conn.execute("ALTER TABLE calendar_events ADD COLUMN people TEXT NOT NULL DEFAULT ''")
    conn.commit()
