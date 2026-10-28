"""Profile page: own display name, password change, avatar upload.

Every account (viewer included) manages its own identity here; admins
manage other accounts from /admin. Avatars are stored in
content/_uploads/avatars/ and served through the login-gated /media/.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from ... import auth
from ..deps import ConnDep, UserDep, base_ctx, get_settings
from ..templates import templates
from ..uploads import MAX_UPLOAD_BYTES, UPLOAD_EXTENSIONS, safe_upload_path, uploads_dir

router = APIRouter()

MIN_PASSWORD_LEN = 8
AVATAR_DIR = "avatars"


def _profile_response(request: Request, conn, user, message: str = ""):
    return templates.TemplateResponse(
        request,
        "perfil.html",
        base_ctx(request, conn, user, message=message),
    )


def _save_avatar(request: Request, conn, user, upload: UploadFile) -> str:
    """Write the uploaded image and return its /media/ path."""
    ext = (upload.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="formato de imagen no permitido")
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400, detail="la imagen supera los 5 MB"
        )
    if not data:
        raise HTTPException(status_code=400, detail="imagen vacía")
    # One avatar per account: username is unique, so it doubles as the key.
    name = f"{AVATAR_DIR}/{user['username']}.{ext}"
    uploads_dir(get_settings(request)).joinpath(AVATAR_DIR).mkdir(parents=True, exist_ok=True)
    uploads_dir(get_settings(request)).joinpath(name).write_bytes(data)
    auth.set_avatar(conn, user["id"], name)
    return name


@router.get("/perfil")
async def profile(request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _profile_response(request, conn, user)


@router.post("/perfil/avatar")
async def profile_avatar(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    avatar: Annotated[UploadFile, File()],
):
    """Upload a new profile picture."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    _save_avatar(request, conn, user, avatar)
    return RedirectResponse("/perfil", status_code=303)


@router.post("/perfil/avatar/quitar")
async def profile_avatar_remove(request: Request, conn: ConnDep, user: UserDep):
    """Remove the current profile picture."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["avatar"]:
        target = safe_upload_path(get_settings(request), user["avatar"])
        if target and target.is_file():
            target.unlink()
    auth.set_avatar(conn, user["id"], "")
    return RedirectResponse("/perfil", status_code=303)


@router.post("/perfil/datos")
async def profile_details(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    display_name: Annotated[str, Form()] = "",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    auth.set_display_name(conn, user["id"], display_name.strip() or user["username"])
    return RedirectResponse("/perfil", status_code=303)


@router.post("/perfil/clave")
async def profile_password(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    current: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    """Change your own password; the current one must still verify."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not auth.verify_password(user["password_hash"], current):
        return _profile_response(
            request, conn, user, message="La contraseña actual no coincide."
        )
    if len(password) < MIN_PASSWORD_LEN:
        return _profile_response(
            request, conn, user,
            message=f"La nueva contraseña necesita {MIN_PASSWORD_LEN} caracteres mínimo.",
        )
    auth.set_password(conn, user["id"], password)
    return _profile_response(request, conn, user, message="Contraseña actualizada.")
