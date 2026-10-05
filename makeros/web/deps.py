"""Shared request dependencies: DB connection, settings, current user."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Request

from ..auth import get_user
from ..collections import COLLECTIONS, STATUS_HELP, STATUS_LABELS, TASK_STATUSES
from ..config import Settings
from ..db import connect
from ..indexer import collection_counts
from ..ui import collection_icons
from .icons import icon_names
from .listing import todays_events


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """One SQLite connection per request, closed on completion."""
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


# Annotated aliases keep route signatures readable and satisfy lint
# (no function call in argument defaults).
ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]


async def current_user(request: Request, conn: ConnDep):
    """The logged-in user row, or None (SSR routes redirect themselves)."""
    uid = request.session.get("uid")
    if uid is None:
        return None
    return get_user(conn, uid)


UserDep = Annotated[sqlite3.Row | None, Depends(current_user)]


def base_ctx(
    request: Request, conn: sqlite3.Connection, user: sqlite3.Row | None, **extra: Any
) -> dict[str, Any]:
    """Common template context: user, collection nav with live counts + icons."""
    counts = {row["collection"]: row["n"] for row in collection_counts(conn)}
    ctx: dict[str, Any] = {
        "user": user,
        "counts": counts,
        "collections": COLLECTIONS,
        "nav_icons": collection_icons(conn),
        "icon_list": icon_names(),
        "today_events": todays_events(conn),
        "status_labels": STATUS_LABELS,
        "status_help": STATUS_HELP,
        "task_status_labels": TASK_STATUSES,
    }
    ctx.update(extra)
    return ctx
