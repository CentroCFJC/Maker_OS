"""Application factory and ASGI entry point (`uvicorn makeros.main:app`)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import count_users
from .config import Settings
from .db import connect, init_schema
from .indexer import Watcher, reindex_all
from .web.routes import auth_routes, collection_routes, home_routes, search_routes

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
        conn.close()
        log.info("Indexed %d documents from %s", total, settings.content_dir)

        watcher = Watcher(settings.content_dir, settings.db_path)
        watcher.start()
        try:
            yield
        finally:
            watcher.stop()

    app = FastAPI(title="MakerOS", version="0.1.0", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
    app.state.settings = settings

    for router in (
        home_routes.router,
        auth_routes.router,
        search_routes.router,
        collection_routes.router,
    ):
        app.include_router(router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
        raise exc

    return app


app = create_app()
