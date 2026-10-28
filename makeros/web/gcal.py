"""Google Calendar two-way sync (OAuth + Calendar API v3 REST).

One shared lab calendar, connected once by an admin; MakerOS talks
OUTBOUND to Google, so the server needs no public IP (see
docs/GCALENDAR.md). Markdown stays the source of truth: pulled events
become files under content/calendario/, and events born in MakerOS are
pushed to Google and stamped with their remote id (`gcal_id`).

All network calls go through the small module-level `oauth_post` /
`api_get` / `api_post` helpers so tests can monkeypatch them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from ..ui import get_ui, set_ui

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CAL_BASE = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar.events"

# ui_settings keys
KEY_REFRESH = "gcal:refresh_token"
KEY_CALENDAR = "gcal:calendar_id"
KEY_SYNC = "gcal:sync_token"
KEY_CLIENT_ID = "gcal:client_id"
KEY_CLIENT_SECRET = "gcal:client_secret"

ERROR_KEY = "gcal:last_error"


def oauth_post(url: str, data: dict) -> httpx.Response:
    return httpx.post(url, data=data, timeout=15)


def api_get(url: str, headers: dict, params: dict | None = None) -> httpx.Response:
    return httpx.get(url, headers=headers, params=params or {}, timeout=15)


def api_post(url: str, headers: dict, json_body: dict) -> httpx.Response:
    return httpx.post(url, headers=headers, json=json_body, timeout=15)


def auth_url(client_id: str, redirect_uri: str) -> str:
    """Google consent URL: offline access so we get a refresh token."""
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    r = oauth_post(
        TOKEN_URL,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    r.raise_for_status()
    return r.json()


def refresh_access(client_id: str, client_secret: str, refresh_token: str) -> str:
    r = oauth_post(
        TOKEN_URL,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]




def _events_page(access_token: str, calendar_id: str, params: dict) -> httpx.Response:
    return api_get(
        f"{CAL_BASE}/calendars/{calendar_id}/events",
        {"Authorization": f"Bearer {access_token}"},
        params,
    )










@dataclass
class SyncResult:
    pulled: int = 0
    pushed: int = 0
    deleted: int = 0
    error: str = ""


def client_credentials(conn: sqlite3.Connection, settings) -> tuple[str, str]:
    """(id, secret): entered in the admin panel, or env as fallback."""
    client_id = get_ui(conn, KEY_CLIENT_ID) or settings.google_client_id
    client_secret = get_ui(conn, KEY_CLIENT_SECRET) or settings.google_client_secret
    return client_id, client_secret


def is_configured(conn: sqlite3.Connection, settings) -> bool:
    client_id, client_secret = client_credentials(conn, settings)
    return bool(client_id and client_secret)


def is_connected(conn: sqlite3.Connection) -> bool:
    return bool(get_ui(conn, KEY_REFRESH))


def chosen_calendar(conn: sqlite3.Connection) -> str:
    return get_ui(conn, KEY_CALENDAR)






def _local_event_body(event: dict) -> dict:
    """Parsed row -> Google event JSON for the create call."""
    from . import event_store

    body: dict = {"summary": event["summary"]}
    if event["location"]:
        body["location"] = event["location"]
    if event["description"]:
        body["description"] = event["description"]
    private = {}
    if event.get("category"):
        # Round-trips through Google without breaking the event there.
        private["category"] = event["category"]
    if event.get("people"):
        private["people"] = event["people"]
    if private:
        body["extendedProperties"] = {"private": private}
    start = event["start"]
    if isinstance(start, datetime):
        body["start"] = {"dateTime": start.isoformat(), "timeZone": event_store.DEFAULT_TZ}
    else:
        body["start"] = {"date": start.isoformat()}
    end = event["end"] or start
    if isinstance(end, datetime):
        body["end"] = {"dateTime": end.isoformat(), "timeZone": event_store.DEFAULT_TZ}
    else:
        # Google all-day ends are exclusive; ours are inclusive.
        body["end"] = {"date": (end + timedelta(days=1)).isoformat()}
    return body


def delete_remote_event(access: str, calendar_id: str, event_id: str) -> None:
    """Remove an event from Google (the local row is already gone)."""
    r = httpx.delete(
        f"{CAL_BASE}/calendars/{calendar_id}/events/{event_id}",
        headers={"Authorization": f"Bearer {access}"},
        timeout=15,
    )
    # 404/410 = already gone on Google's side: that is what we wanted.
    if r.status_code not in (200, 204, 404, 410):
        r.raise_for_status()


def sync(conn: sqlite3.Connection, settings) -> SyncResult:
    """One two-way sync cycle. Never raises: errors land in the result."""
    from . import event_store

    result = SyncResult()
    refresh = get_ui(conn, KEY_REFRESH)
    calendar_id = chosen_calendar(conn)
    client_id, client_secret = client_credentials(conn, settings)
    if not refresh or not calendar_id or not (client_id and client_secret):
        return result
    try:
        access = refresh_access(client_id, client_secret, refresh)
        sync_token = get_ui(conn, KEY_SYNC)
        # ---- pull (incremental) ----
        params: dict = {"maxResults": 250, "singleEvents": "true"}
        if sync_token:
            params["syncToken"] = sync_token
        while True:
            r = _events_page(access, calendar_id, params)
            r.raise_for_status()
            data = r.json()
            for event in data.get("items", []):
                if event.get("status") == "cancelled":
                    event_store.delete_event(conn, event.get("id", ""))
                    result.deleted += 1
                    continue
                event_store.upsert_from_google(conn, event)
                result.pulled += 1
            if data.get("nextPageToken"):
                params["pageToken"] = data["nextPageToken"]
                continue
            if data.get("nextSyncToken"):
                set_ui(conn, KEY_SYNC, data["nextSyncToken"])
            break
        # ---- push (events born in MakerOS, still on local-* ids) ----
        for local_id in event_store.unsynced_local_ids(conn):
            event = event_store.get_event(conn, local_id)
            if event is None:
                continue
            r = api_post(
                f"{CAL_BASE}/calendars/{calendar_id}/events",
                {"Authorization": f"Bearer {access}"},
                _local_event_body(event),
            )
            r.raise_for_status()
            event_store.replace_local_id(conn, local_id, r.json())
            result.pushed += 1
        set_ui(conn, ERROR_KEY, "")
    except Exception as exc:  # noqa: BLE001 — surfaced in the admin panel
        result.error = str(exc)[:300]
        set_ui(conn, ERROR_KEY, result.error)
    return result


# ---------- Auto-sync scheduling ----------
# Triggers: entering the calendar page, creating a calendario page, and
# the 5-minute loop in main.py. One shared guard keeps them from
# stampeding Google if a user refreshes fast.

_last_sync_at = [0.0]
SYNC_MIN_INTERVAL = 45  # seconds


def _sync_blocking(settings) -> None:
    from ..db import connect

    conn = connect(settings.db_path)
    try:
        sync(conn, settings)
    finally:
        conn.close()


def schedule_sync(settings, force: bool = False) -> bool:
    """Run one sync cycle soon, in a background thread.

    Returns False when a sync ran moments ago (nothing scheduled) or
    when no event loop is available (CLI contexts sync explicitly).
    """
    import asyncio
    import time as _time

    now = _time.monotonic()
    if not force and now - _last_sync_at[0] < SYNC_MIN_INTERVAL:
        return False
    _last_sync_at[0] = now
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    loop.create_task(asyncio.to_thread(_sync_blocking, settings))
    return True
