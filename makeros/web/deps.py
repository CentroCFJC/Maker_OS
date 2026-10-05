"""Shared request dependencies: DB connection, settings, current user."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Request

from ..auth import get_user
from ..collections import COLLECTIONS
from ..config import Settings
from ..db import connect
from ..indexer import collection_counts


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
    """Common template context: user, collection nav with live counts."""
    counts = {row["collection"]: row["n"] for row in collection_counts(conn)}
    ctx: dict[str, Any] = {"user": user, "counts": counts, "collections": COLLECTIONS}
    ctx.update(extra)
    return ctx
