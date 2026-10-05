"""Wiki: collection index and page rendering."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ... import frontmatter
from ...indexer import get_document, list_collection
from ..deps import ConnDep, UserDep, get_settings
from ..render import render_markdown
from ..templates import templates

router = APIRouter()


@router.get("/wiki")
async def wiki_index(request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    pages = list_collection(conn, "wiki")
    return templates.TemplateResponse(request, "wiki_index.html", {"user": user, "pages": pages})


@router.get("/wiki/{page_path:path}")
async def wiki_page(
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    if user is None:
        return RedirectResponse("/login", status_code=303)

    settings = get_settings(request)
    wiki_dir = (settings.content_dir / "wiki").resolve()
    if ".." in page_path or page_path.endswith("/"):
        raise HTTPException(status_code=404)

    file = wiki_dir / (page_path + ".md")
    try:
        resolved = file.resolve().relative_to(wiki_dir)
    except ValueError:
        raise HTTPException(status_code=404) from None
    if not file.is_file():
        raise HTTPException(status_code=404)

    doc_id = str(resolved.with_suffix(""))
    meta, body = frontmatter.read(file)
    _indexed = get_document(conn, doc_id)  # ensures index fresh on direct file edits
    html = render_markdown(body)
    return templates.TemplateResponse(
        request,
        "wiki_page.html",
        {"user": user, "title": meta.get("title") or page_path, "meta": meta, "html": html},
    )
