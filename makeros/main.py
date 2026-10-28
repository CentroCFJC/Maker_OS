"""Application factory and ASGI entry point (`uvicorn makeros.main:app`)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import count_users
from .config import Settings
from .db import connect, init_schema
from .indexer import Watcher, reindex_all
from .web.gcal import sync as gcal_sync
from .web.routes import (
    admin_routes,
    assistant_routes,
    auth_routes,
    collection_routes,
    explorer_routes,
    gcal_routes,
    home_routes,
    notes_routes,
    profile_routes,
    search_routes,
    split_routes,
)

log = logging.getLogger("makeros")

STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = connect(settings.db_path)
        init_schema(conn)
        if count_users(conn) == 0:
            log.warning(
                "No users yet. Create the admin account with: "
                "`python -m makeros.cli adduser <username> --role admin`"
            )
        total = reindex_all(conn, settings.content_dir)
        # Calendar events live in SQLite (Google format), not Markdown:
        # one-time move of legacy event pages, then the files are gone.
        from .web import event_store

        event_store.ensure_schema(conn)
        migrated = event_store.migrate_from_documents(conn, settings.content_dir)
        if migrated:
            log.info("Migrated %d calendar pages to event rows", migrated)
        conn.close()
        log.info("Indexed %d documents from %s", total, settings.content_dir)

        watcher = Watcher(settings.content_dir, settings.db_path)
        watcher.start()

        async def gcal_loop():
            """Two-way Google Calendar sync every 5 minutes (best effort).

            The loop never dies: one bad cycle (network, revoked token)
            logs and waits for the next one.
            """
            while True:
                await asyncio.sleep(300)
                try:
                    conn = connect(settings.db_path)
                    try:
                        result = gcal_sync(conn, settings)
                        if result.error:
                            log.warning("gcal sync: %s", result.error)
                        elif result.pulled or result.pushed or result.deleted:
                            log.info(
                                "gcal sync: %d pulled, %d pushed, %d deleted",
                                result.pulled, result.pushed, result.deleted,
                            )
                    finally:
                        conn.close()
                except Exception:  # noqa: BLE001 — keep the loop alive
                    log.exception("gcal sync loop crashed; retrying next cycle")

        sync_task = asyncio.create_task(gcal_loop())
        try:
            yield
        finally:
            sync_task.cancel()
            watcher.stop()

    app = FastAPI(title="MakerOS", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=settings.cookie_secure,
    )
    app.state.settings = settings

    # Mount /static before including routers: the generic collection route
    # `/{collection}/{page_path:path}` would otherwise swallow /static/* URLs.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    for router in (
        home_routes.router,
        auth_routes.router,
        search_routes.router,
        admin_routes.router,
        profile_routes.router,
        gcal_routes.router,
        notes_routes.router,
        explorer_routes.router,
        assistant_routes.router,
        split_routes.router,
        collection_routes.router,
    ):
        app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Render Spanish error pages instead of JSON for browser requests."""
        if exc.status_code in (404, 403):
            return HTMLResponse(
                f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
                f"<title>MakerOS — Error {exc.status_code}</title>"
                f"<link rel='stylesheet' href='/static/css/makeros.css'></head>"
                f"<body class='error-page'><main><h1>Error {exc.status_code}</h1>"
                f"<p>{'Página no encontrada.' if exc.status_code == 404 else 'Sin permisos.'}</p>"
                f"<p><a href='/'>Volver al inicio</a></p></main></body></html>",
                status_code=exc.status_code,
            )
        # Anything else (e.g. a 400) keeps FastAPI's JSON behaviour;
        # re-raising here would turn it into a 500.
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    return app


app = create_app()
