"""Home / dashboard: greeting, category quick access, recent pages."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ...indexer import recent_documents
from ..deps import ConnDep, UserDep, base_ctx
from ..templates import templates

router = APIRouter()


@router.get("/")
async def home(request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "home.html",
        base_ctx(request, conn, user, recent=recent_documents(conn, 10)),
    )
