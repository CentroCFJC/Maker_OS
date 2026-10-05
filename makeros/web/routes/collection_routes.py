"""Collection pages: category indexes, page creation, block editing.

URL scheme: document path "wiki/inicio" (collection + relative path)
maps 1:1 to URL "/wiki/inicio", so every link anywhere in the app is
just "/" + the indexed doc path. Block operations write the file
through the frontmatter module and refresh the index immediately.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response

from ... import frontmatter
from ...collections import COLLECTIONS, STATUS_FILTERS, STATUS_LABELS
from ...frontmatter import FrontmatterError
from ...indexer import index_file, remove_document
from ...ui import set_ui
from ..blocks import BLOCK_SEEDS, join_blocks, split_blocks
from ..calendar import (
    WEEKDAYS_ES,
    build_ics,
    day_map,
    fmt_when,
    month_grid,
    month_label,
    parse_month,
    parse_when,
)
from ..deps import ConnDep, UserDep, base_ctx, get_settings
from ..forms import fields_for
from ..icons import is_valid_icon
from ..listing import collection_items, project_task_stats
from ..render import render_markdown
from ..templates import templates

router = APIRouter()

EDIT_ROLES = ("admin", "member")
VIEWS = ("lista", "tarjetas", "kanban")

# Page banners: uploaded files land in content/_uploads/ and are served
# back through /media/. Banners may also be plain remote URLs.
UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_BANNER_BYTES = 5 * 1024 * 1024


def _uploads_dir(settings) -> Path:
    uploads = settings.content_dir / "_uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


def _safe_upload_path(settings, name: str) -> Path | None:
    """Resolve a /media/ name inside the uploads dir, blocking traversal."""
    uploads = _uploads_dir(settings).resolve()
    target = (uploads / name).resolve()
    if target == uploads or uploads not in target.parents:
        return None
    return target


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


def _calendar_response(request: Request, conn, user, info: dict[str, str]):
    """Month grid of events and project milestones (/calendario)."""
    today = datetime.now().date()
    year, month = parse_month(request.query_params.get("m", ""), today)
    items_by_day = day_map(conn)
    weeks = [
        [
            {
                "date": day,
                "iso": day.isoformat(),
                "in_month": day.month == month,
                "is_today": day == today,
                "items": items_by_day.get(day, []),
            }
            for day in week
        ]
        for week in month_grid(year, month)
    ]
    prev_m = (datetime(year, month, 1) - timedelta(days=1)).strftime("%Y-%m")
    next_m = (datetime(year, month, 28) + timedelta(days=7)).strftime("%Y-%m")
    return templates.TemplateResponse(
        request,
        "calendar.html",
        base_ctx(
            request,
            conn,
            user,
            collection_slug="calendario",
            collection_label=info["label"],
            weeks=weeks,
            weekdays=WEEKDAYS_ES,
            month_title=month_label(year, month),
            prev_month=prev_m,
            next_month=next_m,
            feed_url=f"{request.base_url}calendario.ics",
        ),
    )


@router.post("/ui/icono/{collection}")
async def set_collection_icon(
    collection: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    icon: str = Form(""),
):
    """Admins can restyle the sidebar: set (or reset) a collection's icon."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        raise HTTPException(status_code=403)
    _collection_or_404(collection)
    icon = icon.strip()
    if icon and not is_valid_icon(icon):
        raise HTTPException(status_code=400)
    set_ui(conn, f"icon:{collection}", icon)
    return RedirectResponse(f"/{collection}", status_code=303)


@router.get("/calendario.ics")
async def calendar_ics(request: Request, conn: ConnDep, user: UserDep):
    """ICS feed of all dated events; subscribable from Google Calendar."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ics = build_ics(conn, datetime.now(UTC).replace(microsecond=0))
    return Response(content=ics, media_type="text/calendar; charset=utf-8")


@router.get("/media/{file_path:path}")
async def media_file(file_path: str, request: Request, user: UserDep):
    """Serve uploaded page banners (login required)."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings(request)
    target = _safe_upload_path(settings, file_path)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target)


@router.post("/{collection}/{page_path:path}/banner")
async def set_banner(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    archivo: Annotated[UploadFile | None, File()] = None,
    url: str = Form(""),
):
    """Set a page banner: upload a file or paste an image URL."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)

    if archivo is not None and archivo.filename:
        ext = Path(archivo.filename).suffix.lower().lstrip(".")
        if ext not in UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Formato de imagen no permitido")
        data = await archivo.read()
        if len(data) > MAX_BANNER_BYTES:
            raise HTTPException(status_code=400, detail="La imagen supera 5 MB")
        stem = re.sub(r"[^a-z0-9]+", "-", page_path.lower()).strip("-") or "pagina"
        name = f"{stem}-{secrets.token_hex(4)}.{ext}"
        (_uploads_dir(settings) / name).write_bytes(data)
        meta["banner"] = f"/media/{name}"
    elif url.strip():
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="La URL debe empezar por http(s)://")
        meta["banner"] = url
    else:
        raise HTTPException(status_code=400, detail="Sube un archivo o pega una URL")

    frontmatter.write(file, meta, body)
    index_file(conn, settings.content_dir, file)
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


@router.post("/{collection}/{page_path:path}/banner/borrar")
async def delete_banner(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    """Remove a page banner (and its uploaded file, if any)."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    banner = meta.pop("banner", None)
    if banner and banner.startswith("/media/"):
        target = _safe_upload_path(settings, banner[len("/media/"):])
        if target is not None and target.is_file():
            target.unlink()
    frontmatter.write(file, meta, body)
    index_file(conn, settings.content_dir, file)
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


@router.get("/{collection}")
async def collection_index(collection: str, request: Request, conn: ConnDep, user: UserDep):
    info = _collection_or_404(collection)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if collection == "calendario":
        return _calendar_response(request, conn, user, info)
    # Per-user list/grid choice: a valid ?vista= param wins and is
    # remembered in a cookie; otherwise the cookie (or "lista") applies.
    vista = request.query_params.get("vista", "")
    if vista in VIEWS:
        remember = vista
    else:
        vista = remember = None
    if vista is None:
        vista = request.cookies.get("vista", "lista")
    # Kanban only exists for tasks; everywhere else it falls back to lista.
    if vista == "kanban" and collection != "tasks":
        vista = "lista"
    items = collection_items(
        conn, collection, task_stats=project_task_stats(conn) if collection == "projects" else None
    )
    # Optional status filter (chips on projects/tasks index pages).
    estado = request.query_params.get("estado", "todos")
    if estado not in STATUS_FILTERS.get(collection, {}) and estado != "todos":
        estado = "todos"
    if estado != "todos":
        items = [item for item in items if item["status"] == estado]
    # Tasks are grouped by their project (kanban or list per project).
    task_groups = None
    if collection == "tasks":
        task_groups = _group_by_project(conn, items)
    response = templates.TemplateResponse(
        request,
        "list.html",
        base_ctx(
            request,
            conn,
            user,
            collection_slug=collection,
            collection_label=info["label"],
            items=items,
            vista=vista,
            estado=estado,
            status_filters=STATUS_FILTERS.get(collection),
            task_groups=task_groups,
        ),
    )
    if remember is not None:
        response.set_cookie("vista", remember)
    return response


def _group_by_project(conn, items: list[dict]) -> list[dict]:
    """Group task items under their project; unassigned tasks go last."""
    titles: dict[str, str] = {}
    for project in collection_items(conn, "projects"):
        slug = project["path"].split("/")[1] if "/" in project["path"] else project["path"]
        titles[slug] = project["title"] or slug
    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item["project"], []).append(item)
    ordered = sorted((s for s in grouped if s), key=lambda s: titles.get(s, s).lower())
    if "" in grouped:
        ordered.append("")
    return [
        {
            "slug": slug,
            "title": titles.get(slug, slug) if slug else "Sin proyecto",
            "items": grouped[slug],
        }
        for slug in ordered
    ]


@router.get("/{collection}/nuevo")
async def new_page_form(collection: str, request: Request, conn: ConnDep, user: UserDep):
    info = _collection_or_404(collection)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    # Day-click prefill for calendar events.
    fecha = request.query_params.get("fecha", "")
    defaults = {"start": f"{fecha}T09:00"} if fecha and collection == "calendario" else {}
    return templates.TemplateResponse(
        request,
        "page_new.html",
        base_ctx(
            request,
            conn,
            user,
            collection_slug=collection,
            collection_label=info["label"],
            form_fields=fields_for(collection),
            defaults=defaults,
        ),
    )


@router.post("/{collection}/nuevo")
async def create_page(
    collection: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    """Create a page from the collection's typed form + seed template."""
    _collection_or_404(collection)
    settings = get_settings(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)

    form = await request.form()
    title = str(form.get("title", "")).strip()
    body = str(form.get("body", "")).strip()
    if not title:
        raise HTTPException(status_code=400, detail="El título es obligatorio")

    info = COLLECTIONS[collection]
    meta, seed_body = _template_seed(settings, info["template"])
    if "title" in meta:
        meta["title"] = title
    if "name" in meta:
        meta["name"] = title
    if "title" not in meta and "name" not in meta:
        meta["title"] = title

    # Typed fields per collection; empty values keep the template seed.
    for field in fields_for(collection):
        name, kind = field["name"], field["kind"]
        if name in ("title", "body", "banner"):
            continue
        value = str(form.get(name, "")).strip()
        if not value:
            continue
        if kind in ("date", "datetime"):
            parsed = parse_when(value)
            if parsed is None:
                raise HTTPException(
                    status_code=400, detail=f"Fecha inválida en «{field['label']}»"
                )
            meta[name] = fmt_when(parsed)
        elif kind == "select":
            if value not in field["options"]:
                raise HTTPException(
                    status_code=400, detail=f"Valor inválido en «{field['label']}»"
                )
            meta[name] = value
        elif kind == "url":
            if not value.startswith(("http://", "https://")):
                raise HTTPException(
                    status_code=400, detail=f"La URL de «{field['label']}» debe empezar por http(s)://"
                )
            meta[name] = value
        else:
            meta[name] = value

    # Calendar events: an event without an explicit end lasts until its start.
    if collection == "calendario" and meta.get("start") and not meta.get("end"):
        meta["end"] = meta["start"]

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

    # Optional banner straight from the creation form.
    _apply_banner_form(form, settings, meta, page_path.rsplit("/", 1)[0])

    frontmatter.write(file, meta, body or seed_body)
    index_file(conn, settings.content_dir, file)
    return RedirectResponse(f"/{collection}/{candidate}", status_code=303)


def _apply_banner_form(form, settings, meta: dict, stem: str) -> None:
    """Store an uploaded or remote banner from the creation form."""
    upload = form.get("banner_file")
    filename = getattr(upload, "filename", "") or ""
    if filename:
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext not in UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Formato de imagen no permitido")
        data = upload.file.read()
        if len(data) > MAX_BANNER_BYTES:
            raise HTTPException(status_code=400, detail="La imagen supera 5 MB")
        name = f"{_slugify(stem)}-{secrets.token_hex(4)}.{ext}"
        (_uploads_dir(settings) / name).write_bytes(data)
        meta["banner"] = f"/media/{name}"
        return
    url = str(form.get("banner_url", "")).strip()
    if url:
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="La URL debe empezar por http(s)://")
        meta["banner"] = url


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


@router.post("/{collection}/{page_path:path}/bloques/{block_index:int}/duplicar")
async def duplicate_block(
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
    texts = [b.text for b in blocks]
    texts.insert(block_index + 1, texts[block_index])
    _save_blocks(conn, settings, file, meta, texts)
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


@router.post("/{collection}/{page_path:path}/bloques/{block_index:int}/mover")
async def move_block(
    collection: str,
    page_path: str,
    block_index: int,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    hacia: str = Form(...),
):
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    if hacia not in ("arriba", "abajo"):
        raise HTTPException(status_code=400)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    blocks = split_blocks(body)
    if not _valid_index(blocks, block_index):
        raise HTTPException(status_code=404)
    swap_with = block_index - 1 if hacia == "arriba" else block_index + 1
    if not _valid_index(blocks, swap_with):
        return RedirectResponse(f"/{collection}/{page_path}", status_code=303)
    texts = [b.text for b in blocks]
    texts[block_index], texts[swap_with] = texts[swap_with], texts[block_index]
    _save_blocks(conn, settings, file, meta, texts)
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


@router.post("/{collection}/{page_path:path}/estado")
async def set_status(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    estado: str = Form(...),
):
    """Change a page's status (kanban drag & drop writes here)."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    estado = estado.strip()
    if estado not in STATUS_LABELS:
        raise HTTPException(status_code=400, detail="Estado desconocido")
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    meta["status"] = estado
    frontmatter.write(file, meta, body)
    index_file(conn, settings.content_dir, file)
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


@router.get("/{collection}/plantilla")
async def template_form(collection: str, request: Request, conn: ConnDep, user: UserDep):
    """Edit the seed template applied to every new page of a collection."""
    info = _collection_or_404(collection)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    path = settings.templates_dir / info["template"]
    current = ""
    if path.is_file():
        meta, body = frontmatter.read(path)
        current = frontmatter.dump(meta, body)
    return templates.TemplateResponse(
        request,
        "template_form.html",
        base_ctx(
            request,
            conn,
            user,
            collection_slug=collection,
            collection_label=info["label"],
            template_name=info["template"],
            current=current,
        ),
    )


@router.post("/{collection}/plantilla")
async def template_save(
    collection: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    text: str = Form(...),
):
    info = _collection_or_404(collection)
    if user is None or user["role"] != "admin":
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    try:
        meta, body = frontmatter.parse(text)
    except FrontmatterError as exc:
        raise HTTPException(
            status_code=400, detail=f"YAML de plantilla inválido: {exc}"
        ) from None
    frontmatter.write(settings.templates_dir / info["template"], meta, body)
    return RedirectResponse(f"/{collection}", status_code=303)


@router.post("/{collection}/{page_path:path}/icono")
async def set_icon(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    icon: str = Form(""),
):
    """Set (or clear, when empty) the page's icon in its frontmatter."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    icon = icon.strip()
    if icon and not is_valid_icon(icon):
        raise HTTPException(status_code=400)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    if icon:
        meta["icon"] = icon
    else:
        meta.pop("icon", None)
    frontmatter.write(file, meta, body)
    index_file(conn, settings.content_dir, file)
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


# The catch-all page view must be registered LAST: the block/banner
# routes below it in the URL space would otherwise be shadowed by its
# {page_path:path} converter (first match wins in Starlette).
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
