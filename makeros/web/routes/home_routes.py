"""Home / dashboard: hero, avisos board, week strip, pinned pages, projects."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ... import frontmatter
from ...collections import PROJECT_STATUSES
from ...indexer import index_file, recent_documents
from .. import event_store
from ..calendar import WEEKDAYS_ES
from ..deps import ConnDep, UserDep, base_ctx, get_settings
from ..greetings import greeting_for
from ..listing import collection_items, project_task_stats, unassigned_tasks
from ..render import render_markdown
from ..templates import templates
from .explorer_routes import pinned_pages

router = APIRouter()

MAX_HOME_PROJECTS = 8

TABLERO_SEED = (
    "Deja aquí los mensajes importantes para el equipo: cambios, "
    "cortes de luz, mantenimientos, avisos generales."
)


def ensure_tablero(settings, conn) -> str:
    """The shared board page; seeded on first visit. Returns its body."""
    file = settings.content_dir / "avisos" / "tablero.md"
    if not file.is_file():
        file.parent.mkdir(parents=True, exist_ok=True)
        frontmatter.write(file, {"title": "Tablero de avisos"}, TABLERO_SEED)
        index_file(conn, settings.content_dir, file)
    _meta, body = frontmatter.read(file)
    return body


def week_events(conn, today: date | None = None) -> list[dict]:
    """Next 7 days, each with its events (calendar rows)."""
    today = today or date.today()
    by_day: dict[date, list[dict]] = defaultdict(list)
    for event in event_store.iter_events(conn):
        start = event["start"]
        day = start.date() if hasattr(start, "date") else start
        if today <= day <= today + timedelta(days=6):
            time = start.strftime("%H:%M") if hasattr(start, "strftime") else ""
            by_day[day].append(
                {
                    "id": event["id"],
                    "title": event["summary"],
                    "time": time,
                    "category": event.get("category", ""),
                }
            )
    return [
        {
            "label": WEEKDAYS_ES[day.weekday()],
            "number": day.day,
            "today": day == today,
            "events": by_day.get(day, []),
        }
        for day in (today + timedelta(days=i) for i in range(7))
    ]


@router.get("/avisos/tablero/contenido")
async def avisos_board_content(request: Request, conn: ConnDep, user: UserDep):
    """Rendered board body — polled by the home page for live sync."""
    if user is None:
        raise HTTPException(status_code=403)
    settings = get_settings(request)
    return templates.TemplateResponse(
        request,
        "_avisos_board.html",
        {"user": user, "avisos_html": render_markdown(ensure_tablero(settings, conn))},
    )


@router.get("/")
async def home(request: Request, conn: ConnDep, user: UserDep, estado: str = "todos"):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if estado not in PROJECT_STATUSES and estado != "todos":
        estado = "todos"
    settings = get_settings(request)
    projects = collection_items(conn, "projects", task_stats=project_task_stats(conn))
    if estado != "todos":
        projects = [p for p in projects if p["status"] == estado]
    return templates.TemplateResponse(
        request,
        "home.html",
        base_ctx(
            request,
            conn,
            user,
            estado=estado,
            project_statuses=PROJECT_STATUSES,
            projects=projects[:MAX_HOME_PROJECTS],
            total_projects=len(projects),
            task_groups=unassigned_tasks(conn),
            recent=recent_documents(conn, 10),
            greeting=greeting_for(user["display_name"] or user["username"]),
            avisos_html=render_markdown(ensure_tablero(settings, conn)),
            week_days=week_events(conn),
            pinned=pinned_pages(conn),
        ),
    )
