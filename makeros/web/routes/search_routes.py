"""Full-text search over the whole content index."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ...indexer import search_documents
from ..deps import ConnDep, UserDep
from ..templates import templates

router = APIRouter()


@router.get("/search")
async def search(request: Request, conn: ConnDep, user: UserDep, q: str = ""):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    results = search_documents(conn, q) if q.strip() else []
    return templates.TemplateResponse(
        request, "search.html", {"user": user, "q": q, "results": results}
    )
