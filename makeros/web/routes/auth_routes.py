"""Login / logout (session cookies)."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ...auth import authenticate
from ..deps import ConnDep, UserDep, base_ctx
from ..templates import templates

router = APIRouter()


@router.get("/login")
async def login_form(request: Request, conn: ConnDep, user: UserDep):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", base_ctx(request, conn, user, error=None)
    )


@router.post("/login")
async def login(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    username: str = Form(...),
    password: str = Form(...),
):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    logged_in = authenticate(conn, username, password)
    if logged_in is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            base_ctx(request, conn, user, error="Usuario o contraseña incorrectos."),
            status_code=401,
        )
    request.session["uid"] = logged_in["id"]
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
