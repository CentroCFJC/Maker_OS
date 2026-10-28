"""Admin panel: user management and instance configuration.

Admin-only surface, linked from the sidebar (clicking the user's
name). Non-admins get a 404-free 303 to home; viewers never see it.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import auth
from ...indexer import reindex_all
from ...ui import THEME_ACCENTS, THEME_BGS, set_ui
from .. import event_store, llm
from ..calendar import get_feed_token, rotate_feed_token
from ..deps import ConnDep, UserDep, base_ctx, get_settings
from ..templates import templates
from .gcal_routes import gcal_status

router = APIRouter()

MIN_PASSWORD_LEN = 8


def _auth_fail(user):
    """Redirect target if the requester may not use the panel, else None."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=303)
    return None


def _admin_response(request: Request, conn: sqlite3.Connection, user):
    settings = get_settings(request)
    base = settings.base_url or str(request.base_url)
    llm_base_url, llm_model = llm.llm_config(conn)
    return templates.TemplateResponse(
        request,
        "admin.html",
        base_ctx(
            request,
            conn,
            user,
            users=auth.list_users(conn),
            roles=auth.ROLES,
            event_categories=event_store.list_categories(conn),
            category_palette=event_store.CATEGORY_PALETTE,
            accents=THEME_ACCENTS,
            bgs=THEME_BGS,
            feed_url=f"{base}/calendario.ics?token={get_feed_token(conn)}",
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            **gcal_status(conn, settings),
        ),
    )


@router.get("/admin")
async def admin_panel(request: Request, conn: ConnDep, user: UserDep):
    if (fail := _auth_fail(user)) is not None:
        return fail
    return _admin_response(request, conn, user)


@router.get("/admin/usuarios/nuevo")
async def admin_user_form(request: Request, conn: ConnDep, user: UserDep):
    """Fragment for the 'Añadir usuario' modal."""
    if (fail := _auth_fail(user)) is not None:
        return fail
    return templates.TemplateResponse(
        request,
        "_admin_user_form.html",
        base_ctx(request, conn, user, roles=auth.ROLES),
    )


@router.post("/admin/usuarios")
async def admin_create_user(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = "member",
    display_name: Annotated[str, Form()] = "",
):
    if (fail := _auth_fail(user)) is not None:
        return fail
    modal = request.headers.get("hx-request") == "true"

    def fail_form(error: str):
        if not modal:
            raise HTTPException(status_code=400, detail=error)
        return templates.TemplateResponse(
            request,
            "_admin_user_form.html",
            base_ctx(
                request, conn, user,
                roles=auth.ROLES,
                error=error,
                username=username,
                display_name=display_name,
            ),
        )

    username = username.strip().lower()
    if not username:
        return fail_form("falta el usuario")
    if len(password) < MIN_PASSWORD_LEN:
        return fail_form(f"la contraseña necesita {MIN_PASSWORD_LEN} caracteres mínimo")
    try:
        auth.create_user(conn, username, password, role=role, display_name=display_name)
    except ValueError:
        return fail_form("rol no válido")
    except sqlite3.IntegrityError:
        return fail_form("ese usuario ya existe")
    if modal:
        return HTMLResponse(
            "<script>makerosCloseModal(); window.location.reload();</script>"
        )
    return RedirectResponse("/admin#usuarios", status_code=303)


@router.post("/admin/usuarios/{user_id}/rol")
async def admin_set_role(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    user_id: int,
    role: Annotated[str, Form()],
):
    if (fail := _auth_fail(user)) is not None:
        return fail
    try:
        auth.update_role(conn, user_id, role)
    except LookupError:
        raise HTTPException(status_code=404, detail="usuario no encontrado") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="rol no válido") from None
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return RedirectResponse("/admin#usuarios", status_code=303)


@router.post("/admin/usuarios/{user_id}/clave")
async def admin_reset_password(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    user_id: int,
    password: Annotated[str, Form()],
):
    if (fail := _auth_fail(user)) is not None:
        return fail
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400, detail=f"la contraseña necesita {MIN_PASSWORD_LEN} caracteres mínimo"
        )
    try:
        auth.set_password(conn, user_id, password)
    except LookupError:
        raise HTTPException(status_code=404, detail="usuario no encontrado") from None
    return RedirectResponse("/admin#usuarios", status_code=303)


@router.post("/admin/usuarios/{user_id}/eliminar")
async def admin_delete_user(
    request: Request, conn: ConnDep, user: UserDep, user_id: int
):
    if (fail := _auth_fail(user)) is not None:
        return fail
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="no puedes eliminarte a ti mismo")
    try:
        auth.delete_user(conn, user_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="usuario no encontrado") from None
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return RedirectResponse("/admin#usuarios", status_code=303)


@router.post("/admin/config")
async def admin_config(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    site_name: Annotated[str, Form()] = "",
):
    if (fail := _auth_fail(user)) is not None:
        return fail
    set_ui(conn, "site:name", site_name.strip())
    return RedirectResponse("/admin#integracion", status_code=303)


@router.post("/admin/llm")
async def admin_llm(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    base_url: Annotated[str, Form()] = "",
    modelo: Annotated[str, Form()] = "",
):
    """Point the assistant at a local OpenAI-compatible server."""
    if (fail := _auth_fail(user)) is not None:
        return fail
    llm.save_config(conn, base_url, modelo)
    return RedirectResponse("/admin#integracion", status_code=303)


@router.post("/admin/token")
async def admin_rotate_feed_token(request: Request, conn: ConnDep, user: UserDep):
    if (fail := _auth_fail(user)) is not None:
        return fail
    rotate_feed_token(conn)
    return RedirectResponse("/admin#integracion", status_code=303)


@router.post("/admin/tema")
async def admin_theme(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    accent: Annotated[str, Form()] = "rojo",
    fondo: Annotated[str, Form()] = "blanco",
):
    """Instance-wide theme: accent color (logo palette) + background."""
    if (fail := _auth_fail(user)) is not None:
        return fail
    if accent not in THEME_ACCENTS or fondo not in THEME_BGS:
        raise HTTPException(status_code=400, detail="tema no válido")
    set_ui(conn, "theme:accent", "" if accent == "rojo" else accent)
    set_ui(conn, "theme:background", "" if fondo == "blanco" else fondo)
    return RedirectResponse("/admin#apariencia", status_code=303)


@router.post("/admin/reindex")
async def admin_reindex(request: Request, conn: ConnDep, user: UserDep):
    """Rebuild the FTS index from scratch (after big git pulls or manual
    edits made while the app was down)."""
    if (fail := _auth_fail(user)) is not None:
        return fail
    settings = get_settings(request)
    reindex_all(conn, settings.content_dir)
    return RedirectResponse("/admin#sistema", status_code=303)


@router.post("/admin/categorias")
async def admin_add_category(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    label: Annotated[str, Form()],
    color: Annotated[str, Form()],
):
    """Add an event category (slug id is derived from the label)."""
    if (fail := _auth_fail(user)) is not None:
        return fail
    if event_store.add_category(conn, label, color) is None:
        raise HTTPException(status_code=400, detail="color no válido")
    return RedirectResponse("/admin#categorias", status_code=303)


@router.post("/admin/categorias/{category_id}/eliminar")
async def admin_delete_category(
    request: Request, conn: ConnDep, user: UserDep, category_id: str
):
    if (fail := _auth_fail(user)) is not None:
        return fail
    event_store.delete_category(conn, category_id)
    return RedirectResponse("/admin#categorias", status_code=303)
