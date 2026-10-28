"""Ask-the-wiki assistant: FTS5 retrieval + local LLM (RAG).

The assistant searches the whole content index with FTS5, feeds the
best pages as context to the local model (LM Studio, OpenAI-compatible)
and renders the answer with links back to the source pages. Without a
model configured or reachable, the page degrades to a notice — the
platform works fully without it.

Answers can be saved as new wiki pages: the Markdown answer becomes a
file under content/wiki/, written through the frontmatter module like
every other page.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ... import frontmatter
from ...indexer import index_file, search_documents
from .. import llm, vault
from ..deps import ConnDep, UserDep, base_ctx, get_settings
from ..render import render_markdown
from ..templates import templates
from .collection_routes import EDIT_ROLES

router = APIRouter()

SYSTEM_PROMPT = (
    "Eres el asistente de MakerOS, el gestor de documentación de un "
    "laboratorio de prototipado. Responde SIEMPRE en español, breve y "
    "directo, usando solo el contexto de las páginas que se te dan. "
    "Cuando menciones una página del contexto, enlázala con su ruta "
    "relativa entre corchetes dobles, por ejemplo [[guia-del-sistema]]. "
    "Si el contexto no basta para responder, dilo claramente."
)
MAX_SOURCES = 6
MAX_CHUNK = 1500


def _sources_for(conn: sqlite3.Connection, settings, query: str) -> list[dict]:
    """FTS5 hits with a truncated body each — the RAG context.

    FTS5's implicit AND is too strict for natural questions, so an
    empty result falls back to an OR of the query's words.
    """
    hits = search_documents(conn, query, limit=MAX_SOURCES)
    if not hits:
        tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
        if tokens:
            hits = search_documents(conn, " OR ".join(tokens), limit=MAX_SOURCES)
    sources: list[dict] = []
    for doc in hits:
        file = settings.content_dir / f"{doc['path']}.md"
        if not file.is_file():
            continue
        _meta, body = frontmatter.read(file)
        sources.append(
            {
                "path": doc["path"],
                "title": doc["title"] or doc["path"],
                "body": body.strip()[:MAX_CHUNK],
            }
        )
    return sources


@router.get("/asistente")
async def assistant(request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "asistente.html",
        base_ctx(
            request, conn, user,
            llm_ready=llm.configured(conn),
        ),
    )


@router.post("/asistente/preguntar")
async def assistant_ask(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    pregunta: Annotated[str, Form()],
):
    """Answer a question from the docs; returns the answer partial."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    settings = get_settings(request)
    pregunta = pregunta.strip()
    sources: list[dict] = []
    answer = None
    offline_msg = ""
    if not pregunta:
        offline_msg = "Escribe una pregunta sobre la documentación."
    else:
        sources = _sources_for(conn, settings, pregunta)
        if not sources:
            offline_msg = "No encontré páginas relevantes para esa pregunta."
        else:
            context = "\n\n".join(
                f"### Página: {s['path']}\n{s['body']}" for s in sources
            )
            answer = llm.chat(
                conn,
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Contexto:\n\n{context}\n\nPregunta: {pregunta}"},
                ],
            )
            if answer is None:
                offline_msg = (
                    "El modelo no está disponible. Configura LM Studio en el "
                    "panel de administración (Integraciones) y asegúrate de que "
                    "el servidor local está encendido."
                )
    return templates.TemplateResponse(
        request,
        "_assistant_answer.html",
        base_ctx(
            request, conn, user,
            pregunta=pregunta,
            sources=sources,
            answer=answer,
            answer_html=render_markdown(answer) if answer else "",
            offline_msg=offline_msg,
        ),
    )


@router.post("/asistente/guardar")
async def assistant_save(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    respuesta: Annotated[str, Form()],
    ruta: Annotated[str, Form()],
):
    """Save an assistant answer as a new wiki page."""
    if user is None or user["role"] not in EDIT_ROLES:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    ruta = ruta.strip().strip("/")
    if not vault.valid_vault_path(ruta):
        raise HTTPException(status_code=400, detail="ruta no válida")
    # Slug collision: fall back to -2, -3... like page creation does.
    candidate = ruta
    n = 1
    while (settings.content_dir / "wiki" / f"{candidate}.md").exists():
        n += 1
        candidate = f"{ruta}-{n}"
    file = settings.content_dir / "wiki" / f"{candidate}.md"
    frontmatter.write(file, {"title": candidate.rsplit("/", 1)[-1].replace("-", " ")}, respuesta)
    index_file(conn, settings.content_dir, file)
    return RedirectResponse(f"/wiki/{candidate}", status_code=303)
