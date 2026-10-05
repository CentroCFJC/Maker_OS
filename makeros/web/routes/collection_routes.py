"""Collection pages: category indexes, page creation, block editing.

URL scheme: document path "wiki/inicio" (collection + relative path)
maps 1:1 to URL "/wiki/inicio", so every link anywhere in the app is
just "/" + the indexed doc path. Block operations write the file
through the frontmatter module and refresh the index immediately.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ... import frontmatter
from ...collections import COLLECTIONS
from ...indexer import index_file, list_collection, remove_document
from ..blocks import BLOCK_SEEDS, join_blocks, split_blocks
from ..deps import ConnDep, UserDep, base_ctx, get_settings
from ..render import render_markdown
from ..templates import templates

router = APIRouter()

EDIT_ROLES = ("admin", "member")


def _collection_or_404(collection: str) -> dict[str, str]:
    info = COLLECTIONS.get(collection)
    if info is None:
        raise HTTPException(status_code=404)
    return info


def _resolve_page(settings, collection: str, page_path: str) -> tuple[Path, str]:
    """Resolve a URL to a content file, blocking traversal. Returns (file, doc_id)."""
    if ".." in page_path or page_path.startswith("/") or page_path.endswith("/"):
        raise HTTPException(status_code=404)
    file = settings.content_dir / collection / (page_path + ".md")
    try:
        resolved = file.resolve().relative_to(settings.content_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=404) from None
    return file, str(resolved.with_suffix(""))


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "sin-titulo"


def _template_seed(settings, template: str) -> tuple[dict, str]:
    """Frontmatter + body seed from a creation template, if it exists."""
    path = settings.templates_dir / template
    if not path.is_file():
        return {"title": ""}, ""
    return frontmatter.read(path)


@router.get("/{collection}")
async def collection_index(collection: str, request: Request, conn: ConnDep, user: UserDep):
    info = _collection_or_404(collection)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    items = list_collection(conn, collection)
    return templates.TemplateResponse(
        request,
        "list.html",
        base_ctx(
            request,
            conn,
            user,
            collection_slug=collection,
            collection_label=info["label"],
            items=items,
        ),
    )


@router.get("/{collection}/nuevo")
async def new_page_form(collection: str, request: Request, conn: ConnDep, user: UserDep):
    info = _collection_or_404(collection)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    return templates.TemplateResponse(
        request,
        "page_new.html",
        base_ctx(
            request,
            conn,
            user,
            collection_slug=collection,
            collection_label=info["label"],
        ),
    )


@router.post("/{collection}/nuevo")
async def create_page(
    collection: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    title: str = Form(...),
    body: str = Form(""),
):
    _collection_or_404(collection)
    settings = get_settings(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)

    info = COLLECTIONS[collection]
    meta, seed_body = _template_seed(settings, info["template"])
    if "title" in meta:
        meta["title"] = title
    if "name" in meta:
        meta["name"] = title
    if "title" not in meta and "name" not in meta:
        meta["title"] = title

    page_path = _slugify(title)
    if collection == "projects":
        page_path = f"{page_path}/project"

    candidate = page_path
    n = 2
    file, _doc_id = _resolve_page(settings, collection, candidate)
    while file.exists():
        candidate = f"{page_path}-{n}"
        n += 1
        file, _doc_id = _resolve_page(settings, collection, candidate)

    frontmatter.write(file, meta, body.strip() or seed_body)
    index_file(conn, settings.content_dir, file)
    return RedirectResponse(f"/{collection}/{candidate}", status_code=303)


@router.get("/{collection}/{page_path:path}")
async def page_view(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    info = _collection_or_404(collection)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings(request)
    file, _doc_id = _resolve_page(settings, collection, page_path)
    if not file.is_file():
        raise HTTPException(status_code=404)

    meta, body = frontmatter.read(file)
    blocks = [
        {"i": b.index, "kind": b.kind, "html": render_markdown(b.text)}
        for b in split_blocks(body)
    ]
    title = str(meta.get("title") or meta.get("name") or page_path.rsplit("/", 1)[-1])
    return templates.TemplateResponse(
        request,
        "page.html",
        base_ctx(
            request,
            conn,
            user,
            collection_slug=collection,
            collection_label=info["label"],
            page_path=page_path,
            page_url=f"/{collection}/{page_path}",
            title=title,
            meta=meta,
            blocks=blocks,
            can_edit=user["role"] in EDIT_ROLES,
        ),
    )


def _load_for_edit(settings, collection: str, page_path: str) -> tuple[Path, dict, str]:
    file, _doc_id = _resolve_page(settings, collection, page_path)
    if not file.is_file():
        raise HTTPException(status_code=404)
    meta, body = frontmatter.read(file)
    return file, meta, body


def _save_blocks(conn, settings, file: Path, meta: dict, texts: list[str]) -> None:
    frontmatter.write(file, meta, join_blocks(texts))
    index_file(conn, settings.content_dir, file)


def _block_partial(request, user, page_url: str, index: int, text: str):
    return templates.TemplateResponse(
        request,
        "_block.html",
        {
            "user": user,
            "page_url": page_url,
            "blocks": [{"i": index, "kind": "", "html": render_markdown(text)}],
        },
    )


def _valid_index(blocks: list, index: int) -> bool:
    return 0 <= index < len(blocks)


@router.get("/{collection}/{page_path:path}/bloques/{block_index:int}")
async def get_block(
    collection: str,
    page_path: str,
    block_index: int,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings(request)
    _file, _meta, body = _load_for_edit(settings, collection, page_path)
    blocks = split_blocks(body)
    if not _valid_index(blocks, block_index):
        raise HTTPException(status_code=404)
    return _block_partial(
        request, user, f"/{collection}/{page_path}", block_index, blocks[block_index].text
    )


@router.get("/{collection}/{page_path:path}/bloques/{block_index:int}/editar")
async def edit_block_form(
    collection: str,
    page_path: str,
    block_index: int,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    _file, _meta, body = _load_for_edit(settings, collection, page_path)
    blocks = split_blocks(body)
    if not _valid_index(blocks, block_index):
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "_block_form.html",
        {
            "user": user,
            "page_url": f"/{collection}/{page_path}",
            "i": block_index,
            "text": blocks[block_index].text,
        },
    )


@router.post("/{collection}/{page_path:path}/bloques/{block_index:int}/editar")
async def save_block(
    collection: str,
    page_path: str,
    block_index: int,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    text: str = Form(...),
):
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    blocks = split_blocks(body)
    if not _valid_index(blocks, block_index):
        raise HTTPException(status_code=404)
    texts = [b.text for b in blocks]
    texts[block_index] = text
    _save_blocks(conn, settings, file, meta, texts)

    if request.headers.get("HX-Request") == "true":
        updated = split_blocks(join_blocks(texts))
        return _block_partial(
            request, user, f"/{collection}/{page_path}", block_index, updated[block_index].text
        )
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


@router.post("/{collection}/{page_path:path}/bloques/{block_index:int}/borrar")
async def delete_block(
    collection: str,
    page_path: str,
    block_index: int,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    blocks = split_blocks(body)
    if not _valid_index(blocks, block_index):
        raise HTTPException(status_code=404)
    texts = [b.text for i, b in enumerate(blocks) if i != block_index]
    _save_blocks(conn, settings, file, meta, texts)
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


@router.post("/{collection}/{page_path:path}/bloques/nuevo")
async def add_block(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    tipo: str = Form(...),
    despues: int = Form(-1),
):
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    if tipo not in BLOCK_SEEDS:
        raise HTTPException(status_code=400)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    blocks = split_blocks(body)
    if despues < -1 or despues >= len(blocks):
        raise HTTPException(status_code=404)
    texts = [b.text for b in blocks]
    # despues == -1 means "add at the end" (the page-level add menu).
    position = len(texts) if despues == -1 else despues + 1
    texts.insert(position, BLOCK_SEEDS[tipo])
    _save_blocks(conn, settings, file, meta, texts)
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


@router.post("/{collection}/{page_path:path}/borrar")
async def delete_page(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file, doc_id = _resolve_page(settings, collection, page_path)
    if not file.is_file():
        raise HTTPException(status_code=404)
    file.unlink()
    remove_document(conn, doc_id)
    return RedirectResponse(f"/{collection}", status_code=303)
