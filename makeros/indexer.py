"""Index the content/ tree into SQLite and keep it in sync.

The Markdown files are the source of truth; this index is a disposable
derived copy (FTS5 search + fast listing). Writes made through the app
update the index directly; the watchfiles watcher is the safety net for
edits made outside the app (git pull, vim, scripts).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

from watchfiles import watch

from . import frontmatter
from .db import connect
from .frontmatter import FrontmatterError

log = logging.getLogger(__name__)


def _doc_id(content_dir: Path, file_path: Path) -> str:
    """Content-relative document id: 'wiki/inicio' for content/wiki/inicio.md."""
    return str(file_path.resolve().relative_to(content_dir.resolve()).with_suffix(""))


def index_file(conn: sqlite3.Connection, content_dir: Path, file_path: Path) -> str:
    """Parse one file and upsert it into the index. Returns the doc id."""
    doc_id = _doc_id(content_dir, file_path)
    meta, body = frontmatter.read(file_path)
    title = str(meta.get("title") or doc_id.rsplit("/", 1)[-1])
    conn.execute(
        """
        INSERT INTO documents (path, collection, title, body, meta_json, mtime)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            collection = excluded.collection,
            title = excluded.title,
            body = excluded.body,
            meta_json = excluded.meta_json,
            mtime = excluded.mtime,
            indexed_at = datetime('now')
        """,
        (
            doc_id,
            doc_id.split("/", 1)[0],
            title,
            body,
            json.dumps(meta, ensure_ascii=False, default=str),
            file_path.stat().st_mtime,
        ),
    )
    conn.commit()
    return doc_id


def remove_document(conn: sqlite3.Connection, doc_id: str) -> None:
    """Drop a document from the index (its file is gone)."""
    conn.execute("DELETE FROM documents WHERE path = ?", (doc_id,))
    conn.commit()


def reindex_all(conn: sqlite3.Connection, content_dir: Path) -> int:
    """Full rescan: index every .md file, forget deleted ones."""
    content_dir = Path(content_dir).resolve()
    on_disk: set[str] = set()
    for file_path in sorted(content_dir.rglob("*.md")):
        if file_path.name.endswith(".tmp"):
            continue
        try:
            on_disk.add(index_file(conn, content_dir, file_path))
        except (FrontmatterError, OSError) as exc:
            log.warning("skipping unindexable file %s: %s", file_path, exc)
    known = {row["path"] for row in conn.execute("SELECT path FROM documents")}
    for doc_id in known - on_disk:
        remove_document(conn, doc_id)
    return len(on_disk)


def get_document(conn: sqlite3.Connection, doc_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM documents WHERE path = ?", (doc_id,)).fetchone()


def list_collection(conn: sqlite3.Connection, collection: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT path, title, indexed_at, meta_json FROM documents "
        "WHERE collection = ? ORDER BY title",
        (collection,),
    ).fetchall()


def recent_documents(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT path, title, collection, indexed_at FROM documents "
        "ORDER BY indexed_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def collection_counts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT collection, COUNT(*) AS n FROM documents GROUP BY collection ORDER BY collection"
    ).fetchall()


def search_documents(conn: sqlite3.Connection, query: str, limit: int = 50) -> list[sqlite3.Row]:
    """FTS5 full-text search with highlighted snippets.

    Falls back to a quoted phrase when the raw query is not valid FTS
    syntax (e.g. a user typing parentheses or stray quotes).
    """
    sql = """
        SELECT d.path, d.title, d.collection,
               snippet(documents_fts, 1, '<mark>', '</mark>', ' … ', 14) AS snippet
        FROM documents_fts
        JOIN documents d ON d.id = documents_fts.rowid
        WHERE documents_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    try:
        return conn.execute(sql, (query, limit)).fetchall()
    except sqlite3.OperationalError:
        return conn.execute(sql, (f'"{query}"', limit)).fetchall()


class Watcher:
    """Background thread keeping the index fresh for on-disk edits."""

    def __init__(self, content_dir: Path | str, db_path: Path | str) -> None:
        self._content_dir = Path(content_dir)
        self._db_path = Path(db_path)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="makeros-watcher", daemon=True)

    def start(self) -> None:
        if self._content_dir.is_dir():
            self._thread.start()
        else:
            log.warning("content dir %s does not exist; watcher not started", self._content_dir)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        conn = connect(self._db_path)
        try:
            while not self._stop.is_set():
                try:
                    for changes in watch(
                        self._content_dir,
                        stop_event=self._stop,
                        # watchfiles calls the filter as (change, absolute_path).
                        watch_filter=lambda _change, path: path.endswith(".md"),
                    ):
                        for _kind, path_str in changes:
                            path = Path(path_str)
                            try:
                                if path.exists():
                                    index_file(conn, self._content_dir, path)
                                    log.info("reindexed %s", path)
                                else:
                                    remove_document(conn, _doc_id(self._content_dir, path))
                            except (FrontmatterError, OSError, sqlite3.Error):
                                log.exception("failed to index %s", path)
                except Exception:
                    # Never let the watcher thread die: log, back off, re-arm.
                    log.exception("watcher loop crashed; restarting in 1s")
                    self._stop.wait(1.0)
        finally:
            conn.close()
