"""File explorer: the whole content tree in one Obsidian-style view.

Walks every collection's indexed documents and renders them as a
collapsible folder tree — the graphical way to browse all Markdown in
one place. Links follow the URL = content-path convention.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ...collections import COLLECTIONS
from ...indexer import list_collection
from ..deps import ConnDep, UserDep, base_ctx
from ..templates import templates

router = APIRouter()

# Collections with their own surface (admin panel); not in the explorer.
HIDDEN = {"people", "exhibits"}


def _node(name: str, url: str) -> dict:
    return {"name": name, "url": url, "folders": [], "files": []}


def content_tree(conn) -> list[dict]:
    """Collection roots with nested folders and page leaves."""
    roots: list[dict] = []
    for slug, info in COLLECTIONS.items():
        if slug in HIDDEN:
            continue
        root = _node(info["label"], f"/{slug}")
        root["slug"] = slug
        nodes = {"": root}
        for doc in list_collection(conn, slug):
            rel = doc["path"][len(slug) + 1:]
            parts = rel.split("/")
            current = ""
            for part in parts[:-1]:
                parent = nodes[current]
                current = f"{current}/{part}".strip("/")
                if current not in nodes:
                    node = _node(part, f"/{slug}/{current}")
                    parent["folders"].append(node)
                    nodes[current] = node
            nodes[current]["files"].append(
                {"title": doc["title"] or rel, "url": "/" + doc["path"]}
            )
        if root["folders"] or root["files"]:
            roots.append(root)
    return roots


def pinned_pages(conn) -> list[dict]:
    """Pages with `pinned: true` in frontmatter (any collection)."""
    pinned = []
    for slug in COLLECTIONS:
        if slug == "avisos":  # the board already has its home section
            continue
        for doc in list_collection(conn, slug):
            try:
                meta = json.loads(doc["meta_json"] or "{}")
            except ValueError:
                continue
            if meta.get("pinned"):
                pinned.append(
                    {"title": doc["title"] or doc["path"], "url": "/" + doc["path"]}
                )
    return pinned


def _scope(tree: list[dict], carpeta: str) -> tuple[list[dict], list[dict], list[dict]]:
    """(address-bar segments, folders, files) at `carpeta` ("wiki/guias")."""
    parts = carpeta.split("/") if carpeta else []
    segments, acc = [], ""
    for part in parts:
        acc = f"{acc}/{part}".strip("/")
        segments.append({"name": part, "carpeta": acc})
    node = None
    for i, part in enumerate(parts):
        if i == 0:
            node = next((n for n in tree if n.get("slug") == part), None)
        else:
            children = node["folders"] if node else []
            node = next((n for n in children if n["name"] == part), None)
        if node is None:
            raise HTTPException(status_code=404)
    if node:
        return segments, node["folders"], node["files"]
    return segments, tree, []


@router.get("/explorador")
async def explorer(request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    tree = content_tree(conn)
    carpeta = request.query_params.get("carpeta", "").strip().strip("/")
    vista = request.query_params.get("vista", "tarjetas")
    if vista not in ("tarjetas", "lista", "arbol"):
        vista = "tarjetas"
    if carpeta:
        try:
            segments, folders, files = _scope(tree, carpeta)
        except HTTPException:
            # Unknown route: fall back to the root instead of a 404 page.
            segments, folders, files = [], tree, []
    else:
        segments, folders, files = [], tree, []
    return templates.TemplateResponse(
        request,
        "explorador.html",
        base_ctx(
            request, conn, user,
            tree=tree,
            segments=segments,
            folders=folders,
            files=files,
            carpeta=carpeta,
            vista=vista,
        ),
    )
