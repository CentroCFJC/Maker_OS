"""Google Calendar OAuth connection + manual sync (admin-only).

Redirect URI: GOOGLE_REDIRECT_URI if set, else {base_url}/google/callback
— with tailscale serve this is https://<machine>.<tailnet>.ts.net.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ...ui import get_ui, set_ui
from .. import gcal
from ..deps import ConnDep, UserDep, get_settings

router = APIRouter()


def _auth_fail(user):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=303)
    return None


def _redirect_uri(settings, base_url: str) -> str:
    if settings.google_redirect_uri:
        return settings.google_redirect_uri
    return f"{base_url}/google/callback"


@router.post("/google/credenciales")
async def gcal_credentials(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    client_id: Annotated[str, Form()] = "",
    client_secret: Annotated[str, Form()] = "",
):
    """Save the OAuth client credentials entered in the admin panel."""
    if (fail := _auth_fail(user)) is not None:
        return fail
    set_ui(conn, gcal.KEY_CLIENT_ID, client_id.strip())
    set_ui(conn, gcal.KEY_CLIENT_SECRET, client_secret.strip())
    return RedirectResponse("/admin#integracion", status_code=303)


@router.get("/google/login")
async def gcal_login(request: Request, conn: ConnDep, user: UserDep):
    if (fail := _auth_fail(user)) is not None:
        return fail
    client_id, client_secret = gcal.client_credentials(conn, get_settings(request))
    if not (client_id and client_secret):
        raise HTTPException(
            status_code=400, detail="falta el ID de cliente o el secreto de Google"
        )
    settings = get_settings(request)
    base = settings.base_url or str(request.base_url).rstrip("/")
    return RedirectResponse(
        gcal.auth_url(client_id, _redirect_uri(settings, base)), 303
    )


@router.get("/google/callback")
async def gcal_callback(
    request: Request, conn: ConnDep, user: UserDep, error: str = "", code: str = ""
):
    """Google sends the browser back here with the authorization code."""
    if (fail := _auth_fail(user)) is not None:
        return fail
    settings = get_settings(request)
    base = settings.base_url or str(request.base_url).rstrip("/")
    if error or not code:
        set_ui(conn, gcal.ERROR_KEY, f"Google rechazó el permiso: {error or 'sin código'}")
        return RedirectResponse("/admin#integracion", status_code=303)
    try:
        client_id, client_secret = gcal.client_credentials(conn, settings)
        tokens = gcal.exchange_code(
            client_id,
            client_secret,
            code,
            _redirect_uri(settings, base),
        )
        refresh = tokens.get("refresh_token", "")
        if not refresh:
            # Offline access already granted before: ask consent again.
            set_ui(conn, gcal.ERROR_KEY, "Google no devolvió refresh_token; reconecta.")
            return RedirectResponse("/admin#integracion", status_code=303)
        set_ui(conn, gcal.KEY_REFRESH, refresh)
        set_ui(conn, gcal.KEY_SYNC, "")  # full re-sync on next cycle
        set_ui(conn, gcal.ERROR_KEY, "")
    except Exception as exc:  # noqa: BLE001 — shown in the panel
        set_ui(conn, gcal.ERROR_KEY, str(exc)[:300])
    return RedirectResponse("/admin#integracion", status_code=303)


@router.post("/google/calendario")
async def gcal_choose(
    request: Request,
    conn: ConnDep,
    user: UserDep,
    calendar_id: Annotated[str, Form()],
):
    """The ONE shared calendar id, pasted by the admin."""
    if (fail := _auth_fail(user)) is not None:
        return fail
    if not gcal.is_connected(conn):
        raise HTTPException(status_code=400, detail="no hay conexión con Google")
    set_ui(conn, gcal.KEY_CALENDAR, calendar_id.strip())
    set_ui(conn, gcal.KEY_SYNC, "")  # changing calendars: full re-pull
    gcal.schedule_sync(get_settings(request), force=True)
    return RedirectResponse("/admin#integracion", status_code=303)


@router.post("/google/desconectar")
async def gcal_disconnect(request: Request, conn: ConnDep, user: UserDep):
    if (fail := _auth_fail(user)) is not None:
        return fail
    for key in (
        gcal.KEY_REFRESH, gcal.KEY_CALENDAR, gcal.KEY_SYNC,
        gcal.KEY_CALENDARS, gcal.ERROR_KEY,
    ):
        set_ui(conn, key, "")
    return RedirectResponse("/admin#integracion", status_code=303)


def gcal_status(conn, settings) -> dict:
    """Panel context: connection state for the Integraciones tab."""
    client_id, _ = gcal.client_credentials(conn, settings)
    return {
        "gcal_configured": gcal.is_configured(conn, settings),
        "gcal_client_id": client_id,
        "gcal_connected": gcal.is_connected(conn),
        "gcal_calendar_id": gcal.chosen_calendar(conn),
        "gcal_error": get_ui(conn, gcal.ERROR_KEY),
    }
