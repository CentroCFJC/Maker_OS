"""Calendar helpers: date parsing, month grids, ICS feed generation.

Events live as Markdown under content/calendario/ with `start`/`end`
frontmatter (dates or datetimes). Everything here works on the indexed
meta_json, so the calendar view needs no extra storage.

Spanish locale constants: the lab UI is Spanish-first.
"""

from __future__ import annotations

import calendar as _calendar
import json
import secrets
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..indexer import list_collection
from ..ui import get_ui, set_ui

MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
WEEKDAYS_ES = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")

FEED_TOKEN_KEY = "feed:token"


def get_feed_token(conn: sqlite3.Connection) -> str:
    """Feed token for calendar clients; created on first use.

    Calendar apps (Thunderbird, Apple Calendar) cannot log in, so the
    ICS endpoint accepts `?token=` as an alternative to a session cookie.
    """
    token = get_ui(conn, FEED_TOKEN_KEY)
    if not token:
        token = secrets.token_urlsafe(24)
        set_ui(conn, FEED_TOKEN_KEY, token)
    return token


def rotate_feed_token(conn: sqlite3.Connection) -> str:
    token = secrets.token_urlsafe(24)
    set_ui(conn, FEED_TOKEN_KEY, token)
    return token


def feed_token_ok(conn: sqlite3.Connection, token: str) -> bool:
    expected = get_ui(conn, FEED_TOKEN_KEY)
    return bool(expected) and bool(token) and secrets.compare_digest(token, expected)


def parse_when(value) -> date | datetime | None:
    """Accept a date/datetime object or an ISO-like string; None if unusable."""
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("T", " ")
        try:
            try:
                return date.fromisoformat(text)
            except ValueError:
                return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def to_day(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def fmt_when(value: date | datetime) -> str:
    """Canonical frontmatter form: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'."""
    if isinstance(value, datetime):
        if value.second == 0:
            return value.strftime("%Y-%m-%d %H:%M")
        return value.isoformat(sep=" ")
    return value.isoformat()


@dataclass
class DayItem:
    path: str
    title: str
    kind: str  # "event" | "project"
    time: str  # "HH:MM" for timed items, "" otherwise
    cat: str = ""  # event_categories.id ("proyecto" for milestones)


def month_label(year: int, month: int) -> str:
    return f"{MONTHS_ES[month - 1].capitalize()} {year}"


def month_grid(year: int, month: int) -> list[list[date]]:
    """Weeks (Monday-first) covering the month, including partial weeks."""
    return _calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)


def parse_month(value: str, today: date) -> tuple[int, int]:
    """Validate a ?m=YYYY-MM query param; fall back to the current month."""
    try:
        year, month = (int(part) for part in value.split("-"))
        if 1 <= month <= 12 and 1 <= year <= 9999:
            return year, month
    except ValueError:
        pass
    return today.year, today.month


def _dated_items(conn, collection: str, kind: str, start_key: str, end_key: str):
    """Yield (DayItem, start, end) for every document with usable dates.

    Calendar EVENTS no longer come from here — they live in
    calendar_events (Google format) and are mapped by _event_items().
    """
    for row in list_collection(conn, collection):
        meta = json.loads(row["meta_json"] or "{}")
        start = parse_when(meta.get(start_key))
        if start is None:
            continue
        end = parse_when(meta.get(end_key)) or start
        time = ""
        if isinstance(start, datetime) and (start.hour or start.minute):
            time = start.strftime("%H:%M")
        cat = "proyecto" if kind == "project" else ""
        item = DayItem(path=row["path"], title=row["title"], kind=kind, time=time, cat=cat)
        yield item, start, end


def _event_items(conn):
    """Yield (DayItem, start, end) for every event in the store."""
    from . import event_store

    for event in event_store.iter_events(conn):
        time = ""
        if isinstance(event["start"], datetime) and (event["start"].hour or event["start"].minute):
            time = event["start"].strftime("%H:%M")
        yield (
            DayItem(
                path=f"calendario/evento/{event['id']}",
                title=event["summary"] or "Evento",
                kind="event",
                time=time,
                cat=event["category"],
            ),
            event["start"],
            event["end"] or event["start"],
        )


def day_map(conn) -> dict[date, list[DayItem]]:
    """Events and project milestones mapped to the days they land on."""
    days: dict[date, list[DayItem]] = defaultdict(list)
    for item, start, end in _event_items(conn):
        for day in _day_range(to_day(start), to_day(end)):
            days[day].append(item)
    for item, start, end in _dated_items(conn, "projects", "project", "start", "due"):
        for day in {to_day(start), to_day(end)}:
            days[day].append(item)
    return days


def _day_range(start: date, end: date, cap: int = 62) -> list[date]:
    if end < start:
        return [start]
    return [start + timedelta(days=i) for i in range(min((end - start).days, cap) + 1)]


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ics_stamp(value: date | datetime) -> tuple[str, str]:
    """Return (params, value) for DTSTART/DTEND per RFC 5545."""
    if isinstance(value, datetime):
        return "", value.strftime("%Y%m%dT%H%M%S")
    return ";VALUE=DATE", value.strftime("%Y%m%d")


def build_ics(conn, stamp: datetime) -> str:
    """A subscribable ICS feed of all dated calendar events.

    Any calendar client (Google Calendar, Apple Calendar, etc.) can add
    this by URL, which is the "connect to GCalendar" path that needs no
    Google credentials on our side.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MakerOS//Calendario//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for item, start, end in _event_items(conn):
        # A date-only end paired with a timed start is not valid RFC 5545;
        # treat it as midnight of that day.
        if isinstance(start, datetime) and isinstance(end, date) and not isinstance(end, datetime):
            end = datetime.combine(end, datetime.min.time())
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{item.path}@makeros")
        lines.append(f"DTSTAMP:{stamp.strftime('%Y%m%dT%H%M%SZ')}")
        params, value = _ics_stamp(start)
        lines.append(f"DTSTART{params}:{value}")
        if isinstance(start, datetime):
            params, value = _ics_stamp(end)
        else:
            # All-day: DTEND is exclusive, and MakerOS dates are inclusive.
            params, value = _ics_stamp(to_day(end) + timedelta(days=1))
        lines.append(f"DTEND{params}:{value}")
        lines.append(f"SUMMARY:{_ics_escape(item.title)}")
        if item.cat:
            lines.append(f"CATEGORIES:{item.cat}")
        lines.append(f"URL:/{item.path}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
