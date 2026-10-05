"""Login / logout (session cookies)."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ...auth import authenticate
from ...collections import COLLECTIONS
from ..deps import ConnDep, UserDep
from ..templates import templates

router = APIRouter()


@router.get("/login")
async def login_form(request: Request, user: UserDep):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"user": None, "error": None, "collections": COLLECTIONS, "counts": {}},
    )


@router.post("/login")
async def login(
    request: Request,
    conn: ConnDep,
    username: str = Form(...),
    password: str = Form(...),
):
    user = authenticate(conn, username, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"user": None, "error": "Usuario o contraseña incorrectos.",
             "collections": COLLECTIONS, "counts": {}},
            status_code=401,
        )
    request.session["uid"] = user["id"]
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
