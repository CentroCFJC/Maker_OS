"""Home / dashboard: hero, projects, tasks without project, recent pages."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ...collections import PROJECT_STATUSES
from ...indexer import recent_documents
from ..deps import ConnDep, UserDep, base_ctx
from ..listing import collection_items, project_task_stats, unassigned_tasks
from ..templates import templates

router = APIRouter()

MAX_HOME_PROJECTS = 8


@router.get("/")
async def home(request: Request, conn: ConnDep, user: UserDep, estado: str = "todos"):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if estado not in PROJECT_STATUSES and estado != "todos":
        estado = "todos"
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
        ),
    )
