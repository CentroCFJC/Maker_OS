"""Home / dashboard v0: recent pages, collection counts, search box."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ...indexer import collection_counts, recent_documents
from ..deps import ConnDep, UserDep
from ..templates import templates

router = APIRouter()


@router.get("/")
async def home(request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "user": user,
            "recent": recent_documents(conn, 10),
            "counts": collection_counts(conn),
        },
    )
