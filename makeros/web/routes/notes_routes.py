"""Private notes: a per-user Markdown vault outside the shared repo.

Each user owns `private/<username>/` — folders and .md notes, edited
with the same block UI as every other page. Nothing here is indexed
into the shared FTS; images upload to the user's private folder and
are served owner-only through /notas/media/.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from ... import frontmatter
from ...config import Settings
from ..blocks import BLOCK_SEEDS, infer_kind, join_blocks, split_blocks
from ..deps import ConnDep, UserDep, base_ctx, get_settings
from ..render import render_markdown
from ..templates import templates
from ..uploads import MAX_UPLOAD_BYTES, UPLOAD_EXTENSIONS
from ..vault import valid_vault_path

router = APIRouter()

NOTE_SEED = "Escribe aquí tu nota."

RESERVED = {"nuevo", "carpeta", "media", "bloques"}


# ---------- vault helpers ----------

def _root(settings: Settings, user) -> Path:
    return (settings.private_dir / user["username"]).resolve()


def _resolve(settings: Settings, user, path: str) -> Path:
    """A vault path inside the user's private root (traversal-safe)."""
    path = (path or "").strip().strip("/")
    if not valid_vault_path(path):
        raise HTTPException(status_code=400, detail="ruta no válida")
    root = _root(settings, user)
    target = (root / path).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(status_code=400, detail="ruta no válida")
    return target


def _note_file(settings: Settings, user, path: str) -> Path:
    """The .md file for a note path; 404 if it doesn't exist."""
    file = _resolve(settings, user, path).with_suffix(".md")
    if not file.is_file():
        raise HTTPException(status_code=404)
    return file


def _folder(settings: Settings, user, path: str) -> Path:
    folder = _resolve(settings, user, path)
    if not folder.is_dir():
        raise HTTPException(status_code=404)
    return folder


def _note_meta(file: Path) -> dict:
    meta, _body = frontmatter.read(file)
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return {
        "path": file.with_suffix("").name,
        "title": meta.get("title") or file.stem.replace("-", " "),
        "tags": tags,
        "updated": datetime.fromtimestamp(file.stat().st_mtime)
        .strftime("%Y-%m-%d %H:%M"),
    }


def _scan(settings: Settings, user, base: str = "") -> dict:
    """Folders + note cards inside `base` (relative to the user's root)."""
    root = _root(settings, user)
    folder = _folder(settings, user, base) if base else root
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
    folders, notes = [], []
    for child in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith(("_", ".")):
            continue
        rel = f"{base}/{child.name}".strip("/") if base else child.name
        if child.is_dir():
            count = sum(1 for _ in child.rglob("*.md"))
            folders.append({"name": child.name, "path": rel, "count": count})
        elif child.suffix == ".md":
            meta = _note_meta(child)
            meta["path"] = rel
            notes.append(meta)
    return {"folders": folders, "notes": notes}


def _all_tags(settings: Settings, user, base: str = "") -> list[str]:
    """Tag vocabulary across a folder subtree (for the filter chips)."""
    root = _root(settings, user)
    folder = _resolve(settings, user, base) if base else root
    tags: list[str] = []
    for file in folder.rglob("*.md"):
        for tag in _note_meta(file)["tags"]:
            if tag not in tags:
                tags.append(tag)
    return sorted(tags, key=str.lower)


def _save(settings: Settings, user, file: Path, meta: dict, texts: list[str]) -> None:
    frontmatter.write(file, meta, join_blocks(texts))


def _block_partial(request, user, page_url: str, index: int, text: str):
    return templates.TemplateResponse(
        request,
        "_block.html",
        {"user": user, "page_url": page_url,
         "blocks": [{"i": index, "kind": "", "html": render_markdown(text)}]},
    )


def _note_page_url(path: str) -> str:
    return f"/notas/{path.strip('/')}"


# ---------- navigation ----------

@router.get("/notas")
async def notes_home(request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings(request)
    return templates.TemplateResponse(
        request,
        "notes_home.html",
        base_ctx(
            request, conn, user,
            scan=_scan(settings, user),
            tags=_all_tags(settings, user),
            folder_path="",
        ),
    )


@router.get("/notas/nuevo")
async def notes_new_form(request: Request, conn: ConnDep, user: UserDep):
    """Modal fragment: create a note (folder optional, tags optional)."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    folder = request.query_params.get("carpeta", "").strip().strip("/")
    return templates.TemplateResponse(
        request,
        "_note_form.html",
        base_ctx(request, conn, user, folder=folder),
    )


@router.post("/notas/nuevo")
async def notes_create(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    title: str = Form(""),
    carpeta: str = Form(""),
    tags: str = Form(""),
    cuerpo: str = Form(""),
):
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="falta el título")
    carpeta = carpeta.strip().strip("/")
    if carpeta and not valid_vault_path(carpeta):
        raise HTTPException(status_code=400, detail="ruta de carpeta no válida")

    slug = re.sub(r"[^a-zA-Z0-9-]", "-", title.lower()).strip("-") or "nota"
    if slug in RESERVED:
        slug = f"{slug}-nota"
    parent = _resolve(settings, user, carpeta) if carpeta else _root(settings, user)
    file = parent / f"{slug}.md"
    n = 2
    while file.exists():
        file = parent / f"{slug}-{n}.md"
        n += 1
    meta: dict = {"title": title}
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if tag_list:
        meta["tags"] = tag_list
    _save(settings, user, file, meta, [cuerpo.strip() or NOTE_SEED])

    if request.headers.get("hx-request") == "true":
        return HTMLResponse(
            "<script>makerosCloseModal(); window.location.reload();</script>"
        )
    return RedirectResponse(_note_page_url(carpeta), status_code=303)


@router.post("/notas/carpeta")
async def notes_create_folder(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    ruta: str = Form(""),
):
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    ruta = ruta.strip().strip("/")
    if not valid_vault_path(ruta):
        raise HTTPException(status_code=400, detail="nombre de carpeta no válido")
    _folder = _resolve(settings, user, ruta)
    _folder.mkdir(parents=True, exist_ok=True)
    return RedirectResponse(f"/notas/{ruta}", status_code=303)


@router.get("/notas/media/{name}")
async def notes_media(name: str, request: Request, user: UserDep):
    """Owner-only images for private notes (no shared /media/)."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings(request)
    uploads = (_root(settings, user) / "_uploads").resolve()
    target = (uploads / name).resolve()
    if uploads not in target.parents or not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target)


@router.post("/notas/{path:path}/imagenes")
async def notes_upload_image(path: str, request: Request, user: UserDep, archivo: UploadFile):
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    _note_file(settings, user, path)  # 404 if the note doesn't exist
    ext = (archivo.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="formato de imagen no permitido")
    data = archivo.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="la imagen supera los 5 MB")
    if not data:
        raise HTTPException(status_code=400, detail="imagen vacía")
    base = re.sub(r"[^a-zA-Z0-9-]", "-", (archivo.filename or "imagen").rsplit(".", 1)[0])
    name = f"{base or 'imagen'}.{ext}"
    uploads = _root(settings, user) / "_uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    n = 2
    while (uploads / name).exists():
        name = f"{base}-{n}.{ext}"
        n += 1
    (uploads / name).write_bytes(data)
    return JSONResponse({"url": f"/notas/media/{name}", "name": name})


# ---------- block editing (same UX as every page) ----------

@router.get("/notas/{path:path}/bloques/{block_index:int}")
async def notes_get_block(
    path: str, block_index: int, request: Request, conn: ConnDep, user: UserDep
):
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    _file = _note_file(settings, user, path)
    _meta, body = frontmatter.read(_file)
    blocks = split_blocks(body)
    if not 0 <= block_index < len(blocks):
        raise HTTPException(status_code=404)
    return _block_partial(
        request, user, _note_page_url(path), block_index, blocks[block_index].text
    )


@router.get("/notas/{path:path}/bloques/{block_index:int}/editar")
async def notes_edit_form(
    path: str, block_index: int, request: Request, conn: ConnDep, user: UserDep
):
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    _file = _note_file(settings, user, path)
    _meta, body = frontmatter.read(_file)
    blocks = split_blocks(body)
    if not 0 <= block_index < len(blocks):
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "_block_form.html",
        {"user": user, "page_url": _note_page_url(path), "i": block_index,
         "text": blocks[block_index].text, "tipo": infer_kind(blocks[block_index].text)},
    )


@router.post("/notas/{path:path}/bloques/{block_index:int}/editar")
async def notes_save_block(
    path: str, block_index: int, request: Request, conn: ConnDep, user: UserDep,
    text: str = Form(...),
):
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file = _note_file(settings, user, path)
    meta, body = frontmatter.read(file)
    blocks = split_blocks(body)
    if not 0 <= block_index < len(blocks):
        raise HTTPException(status_code=404)
    texts = [b.text for b in blocks]
    texts[block_index] = text
    _save(settings, user, file, meta, texts)
    if request.headers.get("HX-Request") == "true":
        updated = split_blocks(join_blocks(texts))
        return _block_partial(
            request, user, _note_page_url(path), block_index, updated[block_index].text
        )
    return RedirectResponse(_note_page_url(path), status_code=303)


@router.post("/notas/{path:path}/bloques/{block_index:int}/borrar")
async def notes_delete_block(
    path: str, block_index: int, request: Request, conn: ConnDep, user: UserDep
):
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file = _note_file(settings, user, path)
    meta, body = frontmatter.read(file)
    blocks = split_blocks(body)
    if not 0 <= block_index < len(blocks):
        raise HTTPException(status_code=404)
    texts = [b.text for i, b in enumerate(blocks) if i != block_index]
    _save(settings, user, file, meta, texts)
    return RedirectResponse(_note_page_url(path), status_code=303)


@router.post("/notas/{path:path}/bloques/{block_index:int}/duplicar")
async def notes_duplicate_block(
    path: str, block_index: int, request: Request, conn: ConnDep, user: UserDep
):
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    file = _note_file(settings, user, path)
    meta, body = frontmatter.read(file)
    blocks = split_blocks(body)
    if not 0 <= block_index < len(blocks):
        raise HTTPException(status_code=404)
    texts = [b.text for b in blocks]
    texts.insert(block_index + 1, texts[block_index])
    _save(settings, user, file, meta, texts)
    return RedirectResponse(_note_page_url(path), status_code=303)


@router.post("/notas/{path:path}/bloques/{block_index:int}/mover")
async def notes_move_block(
    path: str, block_index: int, request: Request, conn: ConnDep, user: UserDep,
    hacia: str = Form(...),
):
    if user is None:
        raise HTTPException(status_code=403)
    if hacia not in ("arriba", "abajo"):
        raise HTTPException(status_code=400)
    settings = get_settings(request)
    file = _note_file(settings, user, path)
    meta, body = frontmatter.read(file)
    blocks = split_blocks(body)
    if not 0 <= block_index < len(blocks):
        raise HTTPException(status_code=404)
    swap = block_index - 1 if hacia == "arriba" else block_index + 1
    if not 0 <= swap < len(blocks):
        return RedirectResponse(_note_page_url(path), status_code=303)
    texts = [b.text for b in blocks]
    texts[block_index], texts[swap] = texts[swap], texts[block_index]
    _save(settings, user, file, meta, texts)
    return RedirectResponse(_note_page_url(path), status_code=303)


@router.post("/notas/{path:path}/bloques/{block_index:int}/tamano")
async def notes_resize_block(
    path: str, block_index: int, request: Request, conn: ConnDep, user: UserDep,
    tamano: str = Form(...),
):
    if user is None:
        raise HTTPException(status_code=403)
    named = ("pequena", "mediana", "grande", "completa")
    if tamano not in named and not (tamano.isdigit() and 5 <= int(tamano) <= 100):
        raise HTTPException(status_code=400, detail="tamaño no válido")
    settings = get_settings(request)
    file = _note_file(settings, user, path)
    meta, body = frontmatter.read(file)
    blocks = split_blocks(body)
    if not 0 <= block_index < len(blocks):
        raise HTTPException(status_code=404)
    texts = [b.text for b in blocks]
    match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", texts[block_index].strip())
    if match is None:
        raise HTTPException(status_code=400, detail="el bloque no es una imagen")
    alt = match.group(1).split("|")[0].strip()
    texts[block_index] = texts[block_index].replace(
        match.group(0), f"![{alt}|{tamano}]({match.group(2)})", 1
    )
    _save(settings, user, file, meta, texts)
    return _block_partial(request, user, _note_page_url(path), block_index, texts[block_index])


@router.post("/notas/{path:path}/bloques/nuevo")
async def notes_add_block(
    path: str, request: Request, conn: ConnDep, user: UserDep,
    tipo: str = Form(...), despues: int = Form(-1),
):
    if user is None:
        raise HTTPException(status_code=403)
    if tipo not in BLOCK_SEEDS:
        raise HTTPException(status_code=400)
    settings = get_settings(request)
    file = _note_file(settings, user, path)
    meta, body = frontmatter.read(file)
    blocks = split_blocks(body)
    if despues < -1 or despues >= len(blocks):
        raise HTTPException(status_code=404)
    texts = [b.text for b in blocks]
    position = len(texts) if despues == -1 else despues + 1
    texts.insert(position, BLOCK_SEEDS[tipo])
    _save(settings, user, file, meta, texts)
    if request.headers.get("HX-Request") == "true":
        if tipo == "imagen":
            return templates.TemplateResponse(
                request, "_block_form.html",
                {"user": user, "page_url": _note_page_url(path), "i": position,
                 "text": texts[position], "tipo": tipo},
            )
        return _block_partial(request, user, _note_page_url(path), position, texts[position])
    return RedirectResponse(_note_page_url(path), status_code=303)


# ---------- note / folder view (registered last: catch-all) ----------

@router.get("/notas/{path:path}")
async def notes_view(path: str, request: Request, conn: ConnDep, user: UserDep):
    """A note (block editor) or a folder (scoped card view)."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings(request)
    file = _resolve(settings, user, path).with_suffix(".md")
    if file.is_file():
        meta, body = frontmatter.read(file)
        blocks = split_blocks(body)
        return templates.TemplateResponse(
            request,
            "nota.html",
            base_ctx(
                request, conn, user,
                page_url=_note_page_url(path),
                note_path=path,
                title=meta.get("title") or path.rsplit("/", 1)[-1].replace("-", " "),
                tags=meta.get("tags", []),
                blocks=[
                    {"i": i, "kind": b.kind, "html": render_markdown(b.text)}
                    for i, b in enumerate(blocks)
                ],
            ),
        )
    # Not a note: show the folder's card view.
    _folder(settings, user, path)
    return templates.TemplateResponse(
        request,
        "notes_home.html",
        base_ctx(
            request, conn, user,
            scan=_scan(settings, user, path),
            tags=_all_tags(settings, user, path),
            folder_path=path,
        ),
    )
