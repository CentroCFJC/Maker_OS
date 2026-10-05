"""Shared request dependencies: DB connection, settings, current user."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from ..auth import get_user
from ..config import Settings
from ..db import connect


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
