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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from ... import frontmatter
from ...collections import COLLECTIONS, STATUS_FILTERS, STATUS_LABELS, TASK_STATUSES
from ...frontmatter import FrontmatterError
from ...indexer import index_file, remove_document
from ...ui import get_ui, set_ui
from .. import event_store, vault
from ..blocks import BLOCK_SEEDS, infer_kind, join_blocks, split_blocks
from ..calendar import (
    WEEKDAYS_ES,
    build_ics,
    day_map,
    feed_token_ok,
    fmt_when,
    month_grid,
    month_label,
    parse_month,
    parse_when,
    rotate_feed_token,
)
from ..deps import ConnDep, UserDep, base_ctx, get_settings
from ..forms import TASK_PRIORITIES, fields_for
from ..gcal import schedule_sync
from ..icons import is_valid_icon
from ..listing import collection_items, project_task_stats
from ..render import render_markdown
from ..templates import templates
from ..uploads import (
    MAX_UPLOAD_BYTES,
    UPLOAD_EXTENSIONS,
    safe_upload_path,
    uploads_dir,
)

router = APIRouter()

EDIT_ROLES = ("admin", "member")
VIEWS = ("lista", "tarjetas", "kanban", "arbol")
# Collections whose index page has the folder system (cards + tag filter).
FOLDER_COLLECTIONS = ("wiki", "research", "inventory")


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
                "weekend": day.weekday() >= 5,
                "is_today": day == today,
                "items": items_by_day.get(day, []),
            }
            for day in week
        ]
        for week in month_grid(year, month)
    ]
    prev_m = (datetime(year, month, 1) - timedelta(days=1)).strftime("%Y-%m")
    next_m = (datetime(year, month, 28) + timedelta(days=7)).strftime("%Y-%m")
    # "Próximamente": everything dated from today on, soonest first.
    upcoming = [
        {
            "path": item.path,
            "title": item.title,
            "kind": item.kind,
            "time": item.time,
            "date": day.isoformat(),
        }
        for day in sorted(items_by_day)
        if day >= today
        for item in items_by_day[day]
    ][:12]
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
            upcoming=upcoming,
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
    """ICS feed of all dated events.

    Two access paths: a logged-in session cookie, or `?token=` for
    calendar clients that cannot log in (Thunderbird, Apple Calendar).
    401 (not a redirect) so clients surface the auth problem.
    """
    token = request.query_params.get("token", "")
    if user is None and not feed_token_ok(conn, token):
        return Response("Unauthorized\n", status_code=401, media_type="text/plain")
    ics = build_ics(conn, datetime.now(UTC).replace(microsecond=0))
    return Response(content=ics, media_type="text/calendar; charset=utf-8")


@router.post("/calendario/token")
async def rotate_calendar_token(request: Request, conn: ConnDep, user: UserDep):
    """Admins can invalidate leaked feed tokens; a new one is generated."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        raise HTTPException(status_code=403)
    rotate_feed_token(conn)
    return RedirectResponse("/calendario", status_code=303)


@router.get("/media/{file_path:path}")
async def media_file(file_path: str, request: Request, user: UserDep):
    """Serve uploaded page banners (login required)."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings(request)
    target = safe_upload_path(settings, file_path)
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
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="La imagen supera 5 MB")
        stem = re.sub(r"[^a-z0-9]+", "-", page_path.lower()).strip("-") or "pagina"
        name = f"{stem}-{secrets.token_hex(4)}.{ext}"
        (uploads_dir(settings) / name).write_bytes(data)
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
        target = safe_upload_path(settings, banner[len("/media/"):])
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
    # Wiki cards by default; ?vista=arbol keeps the Obsidian tree (DnD).
    if collection == "wiki" and request.query_params.get("vista") == "arbol":
        return _vault_response(request, conn, user, info, "")
    if collection == "calendario":
        # Entering the calendar pulls fresh events in the background
        # (incremental via Google's sync tokens, so usually cheap).
        schedule_sync(get_settings(request))
        return _calendar_response(request, conn, user, info)
    # Per-user list/grid choice: a valid ?vista= param wins and is
    # remembered in a cookie; otherwise the cookie (or "tarjetas") applies.
    vista = request.query_params.get("vista", "")
    if vista in VIEWS:
        remember = vista
    else:
        vista = remember = None
    if vista is None:
        default = "kanban" if collection == "tasks" else "tarjetas"
        vista = request.cookies.get("vista", default)
    # Kanban only exists for tasks; everywhere else it falls back to tarjetas.
    if vista == "kanban" and collection != "tasks":
        vista = "tarjetas"
    items = collection_items(
        conn, collection, task_stats=project_task_stats(conn) if collection == "projects" else None
    )
    # Folder system (research, inventory, ...): ?carpeta= scopes the view
    # to one subtree; folders render as cards on top of the grid.
    carpeta = request.query_params.get("carpeta", "").strip().strip("/")
    folders: list[dict] = []
    tags: list[str] = []
    if collection in FOLDER_COLLECTIONS:
        if carpeta and not vault.valid_vault_path(carpeta):
            raise HTTPException(status_code=400, detail="ruta de carpeta no válida")
        prefix = f"{collection}/{carpeta}/" if carpeta else f"{collection}/"
        items = [item for item in items if item["path"].startswith(prefix)]
        folders = _collection_folders(items, prefix)
        for item in items:
            for tag in item["tags"]:
                if tag not in tags:
                    tags.append(tag)
        tags.sort(key=str.lower)
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
            folders=folders,
            carpeta=carpeta,
            item_tags=tags,
            status_filters=STATUS_FILTERS.get(collection),
            task_groups=task_groups,
        ),
    )
    if remember is not None:
        response.set_cookie("vista", remember)
    return response


def _collection_folders(items: list[dict], prefix: str) -> list[dict]:
    """First-level folder names under `prefix`, with item counts."""
    counts: dict[str, int] = {}
    for item in items:
        if not item["path"].startswith(prefix):
            continue
        rel = item["path"][len(prefix):]
        if "/" not in rel:
            continue
        name = rel.split("/", 1)[0]
        counts[name] = counts.get(name, 0) + 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda kv: kv[0].lower())
    ]


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
    # Prefills: day-click for calendar events, folder for wiki pages.
    fecha = request.query_params.get("fecha", "")
    defaults = {"start": f"{fecha}T09:00"} if fecha and collection == "calendario" else {}
    if collection in FOLDER_COLLECTIONS or collection == "wiki":
        ruta = request.query_params.get("ruta", "").strip().strip("/")
        if ruta and vault.valid_vault_path(ruta):
            defaults["ruta"] = ruta
    ctx = base_ctx(
        request,
        conn,
        user,
        collection_slug=collection,
        collection_label=info["label"],
        form_fields=fields_for(collection),
        defaults=defaults,
    )
    if request.query_params.get("fragmento") == "1":
        # Modal fragment: just the form, for the global popup.
        return templates.TemplateResponse(request, "_new_form.html", ctx)
    return templates.TemplateResponse(request, "page_new.html", ctx)


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
    modal = request.headers.get("hx-request") == "true"
    try:
        response = await _create_page_body(
            request, conn, user, settings, collection, form
        )
    except HTTPException as exc:
        if not modal:
            raise
        # Modal submit failed: re-render the fragment with the error.
        info = COLLECTIONS[collection]
        defaults = {
            field["name"]: str(form.get(field["name"], ""))
            for field in fields_for(collection)
            if field["kind"] in ("text", "date", "datetime", "url")
        }
        return templates.TemplateResponse(
            request,
            "_new_form.html",
            base_ctx(
                request, conn, user,
                collection_slug=collection,
                collection_label=info["label"],
                form_fields=fields_for(collection),
                defaults=defaults,
                error=exc.detail,
            ),
        )
    if modal:
        # htmx swap: close the popup and refresh the page behind it.
        return HTMLResponse(
            "<script>makerosCloseModal(); window.location.reload();</script>"
        )
    return response


def _modal_done() -> HTMLResponse:
    return HTMLResponse(
        "<script>makerosCloseModal(); window.location.reload();</script>"
    )


async def _create_page_body(
    request: Request, conn, user, settings, collection: str, form,
) -> RedirectResponse:
    """Shared creation logic (see create_page); raises HTTPException."""
    title = str(form.get("title", "")).strip()
    body = str(form.get("body", "")).strip()
    if not title:
        raise HTTPException(status_code=400, detail="El título es obligatorio")

    # Calendar events are Google-format rows, not Markdown pages: store
    # the event and push it to Google right away.
    if collection == "calendario":
        start = str(form.get("start", "")).strip()
        end = str(form.get("end", "")).strip()
        location = str(form.get("location", "")).strip()
        if not start or parse_when(start) is None:
            raise HTTPException(status_code=400, detail="Fecha de inicio inválida")
        category = str(form.get("category", "")).strip()
        event_id = event_store.create_local_event(
            conn, title, start, end, location,
            description=body, category=category,
            people=str(form.get("people", "")).strip(),
        )
        schedule_sync(settings, force=True)
        return RedirectResponse(f"/calendario/evento/{event_id}", status_code=303)

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

    # Pages can be born inside a vault folder (?ruta=guias/impresion);
    # the folder prefix applies before collision checking.
    if collection in FOLDER_COLLECTIONS or collection == "wiki":
        ruta = str(form.get("ruta", "")).strip().strip("/")
        if ruta:
            if not vault.valid_vault_path(ruta):
                raise HTTPException(status_code=400, detail="ruta de carpeta no válida")
            page_path = f"{ruta}/{page_path}"

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
    if collection == "calendario":
        # New event: push it to Google in the background right away.
        schedule_sync(settings, force=True)
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
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="La imagen supera 5 MB")
        name = f"{_slugify(stem)}-{secrets.token_hex(4)}.{ext}"
        (uploads_dir(settings) / name).write_bytes(data)
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


@router.post("/{collection}/{page_path:path}/imagenes")
async def upload_block_image(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    archivo: UploadFile,
):
    """Common image upload for page blocks.

    Files land in content/_uploads/<collection>/<page>/<file> and are
    served login-gated through /media/. One route serves projects,
    tasks, research and every other collection.
    """
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    _collection_or_404(collection)
    settings = get_settings(request)
    ext = (archivo.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="formato de imagen no permitido")
    data = archivo.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="la imagen supera los 5 MB")
    if not data:
        raise HTTPException(status_code=400, detail="imagen vacía")

    base = _slugify((archivo.filename or "imagen").rsplit(".", 1)[0]) or "imagen"
    name = f"{base}.{ext}"
    target_dir = uploads_dir(settings) / collection / page_path
    target_dir.mkdir(parents=True, exist_ok=True)
    n = 2
    while (target_dir / name).exists():
        name = f"{base}-{n}.{ext}"
        n += 1
    (target_dir / name).write_bytes(data)

    return JSONResponse({"url": f"/media/{collection}/{page_path}/{name}", "name": name})


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
            "tipo": infer_kind(blocks[block_index].text),
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


@router.post("/{collection}/{page_path:path}/bloques/{block_index:int}/tamano")
async def resize_image_block(
    collection: str,
    page_path: str,
    block_index: int,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    tamano: str = Form(...),
):
    """Corner-drag resize: write the size token into the image alt."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    named = ("pequena", "mediana", "grande", "completa")
    if tamano not in named and not (tamano.isdigit() and 5 <= int(tamano) <= 100):
        raise HTTPException(status_code=400, detail="tamaño no válido")
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    blocks = split_blocks(body)
    if not _valid_index(blocks, block_index):
        raise HTTPException(status_code=404)
    texts = [b.text for b in blocks]
    match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", texts[block_index].strip())
    if match is None:
        raise HTTPException(status_code=400, detail="el bloque no es una imagen")
    alt = match.group(1).split("|")[0].strip()
    texts[block_index] = texts[block_index].replace(
        match.group(0), f"![{alt}|{tamano}]({match.group(2)})", 1
    )
    _save_blocks(conn, settings, file, meta, texts)
    return _block_partial(
        request, user, f"/{collection}/{page_path}", block_index, texts[block_index]
    )


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

    if request.headers.get("HX-Request") == "true":
        # Image blocks open the editor immediately (upload menu ready);
        # every other type lands rendered, ready to edit on demand.
        if tipo == "imagen":
            return templates.TemplateResponse(
                request,
                "_block_form.html",
                {
                    "user": user,
                    "page_url": f"/{collection}/{page_path}",
                    "i": position,
                    "text": texts[position],
                    "tipo": tipo,
                },
            )
        return _block_partial(
            request, user, f"/{collection}/{page_path}", position, texts[position]
        )
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
@router.get("/calendario/evento/{event_id}")
async def event_detail(event_id: str, request: Request, conn: ConnDep, user: UserDep):
    """Event detail (Google-format row): view, open in Google, delete."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    event = event_store.get_event(conn, event_id)
    if event is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "event.html",
        base_ctx(
            request,
            conn,
            user,
            collection_slug="calendario",
            collection_label="Calendario",
            event=event,
            event_when=fmt_when(event["start"])
            + (f" — {fmt_when(event['end'])}" if event["end"] else ""),
        ),
    )


@router.post("/calendario/evento/{event_id}/eliminar")
async def event_delete(event_id: str, request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    event = event_store.get_event(conn, event_id)
    if event is None:
        raise HTTPException(status_code=404)
    event_store.delete_event(conn, event_id)
    # Remove on Google too (local-* ids were never pushed, skip those).
    if not event_id.startswith(event_store.LOCAL_PREFIX):
        from ..gcal import chosen_calendar, client_credentials, delete_remote_event, refresh_access

        refresh = get_ui(conn, "gcal:refresh_token")
        calendar_id = chosen_calendar(conn)
        settings = get_settings(request)
        client_id, client_secret = client_credentials(conn, settings)
        if refresh and calendar_id and client_id and client_secret:
            try:
                access = refresh_access(client_id, client_secret, refresh)
                delete_remote_event(access, calendar_id, event_id)
            except Exception:  # noqa: BLE001 — offline: pull will re-add it
                pass
    return RedirectResponse("/calendario", status_code=303)


@router.get("/wiki/grafos")
async def wiki_graph(request: Request, conn: ConnDep, user: UserDep):
    """Second-brain graph of all collections and their [[links]]."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "grafos.html",
        base_ctx(
            request, conn, user,
            collection_slug="wiki",
            collection_label="Wiki",
            graph=vault.graph_data(conn),
        ),
    )


@router.get("/wiki/grafos/datos")
async def wiki_graph_data(conn: ConnDep, user: UserDep):
    """Graph JSON for the corner popup (lazy-fetched on first open)."""
    if user is None:
        raise HTTPException(status_code=403)
    return JSONResponse(vault.graph_data(conn))


@router.post("/wiki/carpeta")
async def wiki_create_folder(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    ruta: Annotated[str, Form()],
):
    """Create a folder (nested allowed) inside the wiki vault."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    ruta = ruta.strip().strip("/")
    if not vault.valid_vault_path(ruta):
        raise HTTPException(status_code=400, detail="nombre de carpeta no válido")
    vault.create_folder(get_settings(request), ruta)
    return RedirectResponse(f"/wiki/{ruta}", status_code=303)


@router.post("/wiki/carpeta/{folder_path:path}/mover")
async def wiki_move_folder(
    folder_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    destino: Annotated[str, Form()] = "",
):
    """Move a folder (drag & drop); pages inside keep their names."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    folder_path = folder_path.strip().strip("/")
    if not folder_path or not vault.is_folder(settings, folder_path):
        raise HTTPException(status_code=404)
    destino = destino.strip().strip("/")
    if destino and not vault.valid_vault_path(destino):
        raise HTTPException(status_code=400, detail="ruta no válida")
    if destino == folder_path or destino.startswith(folder_path + "/"):
        raise HTTPException(
            status_code=400, detail="no puedes mover una carpeta dentro de sí misma"
        )
    name = folder_path.rsplit("/", 1)[-1]
    nueva = f"{destino}/{name}" if destino else name
    vault.move_folder(conn, settings, folder_path, nueva)
    return RedirectResponse(f"/wiki/{nueva}", status_code=303)


@router.post("/wiki/{page_path:path}/mover")
async def wiki_move_page(
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
    nueva_ruta: Annotated[str, Form()],
):
    """Move/rename a wiki page; incoming [[links]] are rewritten."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file, _doc_id = _resolve_page(settings, "wiki", page_path)
    if not file.is_file():
        raise HTTPException(status_code=404)
    nueva = nueva_ruta.strip().strip("/")
    if not vault.valid_vault_path(nueva):
        raise HTTPException(status_code=400, detail="ruta no válida")
    target = settings.content_dir / "wiki" / f"{nueva}.md"
    if target.exists():
        raise HTTPException(status_code=400, detail="ya existe una página en esa ruta")
    vault.move_page(conn, settings, f"wiki/{page_path}", f"wiki/{nueva}")
    return RedirectResponse(f"/wiki/{nueva}", status_code=303)


@router.get("/tasks/{page_path:path}/editar")
async def task_edit_form(
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    """Modal fragment to edit a task from the kanban view."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    file, meta, _body = _load_for_edit(get_settings(request), "tasks", page_path)
    return templates.TemplateResponse(
        request,
        "_task_edit.html",
        base_ctx(
            request, conn, user,
            page_path=page_path,
            meta=meta,
            priorities=TASK_PRIORITIES,
        ),
    )


@router.post("/tasks/{page_path:path}/editar")
async def task_edit_save(
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    """Save the task-edit modal: frontmatter fields only, body untouched."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, "tasks", page_path)
    form = await request.form()
    modal = request.headers.get("hx-request") == "true"

    def fail(error: str):
        if not modal:
            raise HTTPException(status_code=400, detail=error)
        return templates.TemplateResponse(
            request, "_task_edit.html",
            base_ctx(
                request, conn, user,
                page_path=page_path,
                meta={**meta, **{k: str(form.get(k, "")) for k in
                                 ("title", "status", "assignee", "priority", "due", "project")}},
                priorities=TASK_PRIORITIES,
                error=error,
            ),
        )

    title = str(form.get("title", "")).strip()
    if not title:
        return fail("El título es obligatorio")
    meta["title"] = title
    status = str(form.get("status", "")).strip()
    if status and status not in TASK_STATUSES:
        return fail("Estado no válido")
    meta["status"] = status
    priority = str(form.get("priority", "")).strip()
    if priority and priority not in TASK_PRIORITIES:
        return fail("Prioridad no válida")
    meta["priority"] = priority
    for key in ("assignee", "project"):
        meta[key] = str(form.get(key, "")).strip()
    due = str(form.get("due", "")).strip()
    if due:
        parsed = parse_when(due)
        if parsed is None:
            return fail("Fecha de vencimiento inválida")
        meta["due"] = fmt_when(parsed)
    elif "due" in meta:
        del meta["due"]

    frontmatter.write(file, meta, body)
    index_file(conn, settings.content_dir, file)
    if modal:
        return _modal_done()
    return RedirectResponse(f"/tasks/{page_path}", status_code=303)


@router.post("/{collection}/{page_path:path}/fijar")
async def toggle_pin(
    collection: str,
    page_path: str,
    request: Request,
    conn: ConnDep,
    user: UserDep,
):
    """Pin/unpin a page; pinned pages show on the home dashboard."""
    _collection_or_404(collection)
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file, meta, body = _load_for_edit(settings, collection, page_path)
    meta["pinned"] = not meta.get("pinned")
    frontmatter.write(file, meta, body)
    index_file(conn, settings.content_dir, file)
    return RedirectResponse(f"/{collection}/{page_path}", status_code=303)


def _vault_response(request, conn, user, info, base: str):
    """Navigator (tree of folders/pages) for the vault or one folder."""
    settings = get_settings(request)
    return templates.TemplateResponse(
        request,
        "wiki_home.html",
        base_ctx(
            request, conn, user,
            collection_slug="wiki",
            collection_label=info["label"],
            tree=vault.build_tree(conn, base),
            folder_path=base,
            is_folder=vault.is_folder(settings, base),
        ),
    )


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
        # A folder of any collection (e.g. /wiki/guias) opens its scoped
        # card view; /wiki/<folder> just redirects there.
        if collection in FOLDER_COLLECTIONS and vault.is_folder(settings, page_path):
            return RedirectResponse(
                f"/{collection}?carpeta={page_path}", status_code=303
            )
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
