"""Content collections: the categories of the lab's Markdown tree.

Every category is a directory under content/ with its own index page,
URL scheme (/slug) and creation template. Adding a new category means
adding one entry here.
"""

from __future__ import annotations

# template = file in templates/ used as frontmatter seed when creating.
# icon = default sidebar icon (name in the vendored Feather sprite).
COLLECTIONS: dict[str, dict[str, str]] = {
    "wiki": {"label": "Wiki", "template": "page.md", "icon": "book-open"},
    "projects": {"label": "Proyectos", "template": "project.md", "icon": "layers"},
    "tasks": {"label": "Tareas", "template": "task.md", "icon": "check-square"},
    "calendario": {"label": "Calendario", "template": "event.md", "icon": "calendar"},
    "research": {"label": "Repositorios", "template": "research.md", "icon": "compass"},
    "people": {"label": "Personas", "template": "person.md", "icon": "users"},
    "inventory": {"label": "Inventario", "template": "inventory.md", "icon": "package"},
    "exhibits": {"label": "Exhibiciones", "template": "device.md", "icon": "monitor"},
}

# Frontmatter status vocabularies (see templates/project.md, task.md).
# Labels are Spanish; the raw values stay ASCII in files and URLs.
PROJECT_STATUSES = {
    "idea": "Idea",
    "planning": "Planificación",
    "active": "En proceso",
    "paused": "En pausa",
    "done": "Completado",
    "archived": "Archivado",
}
TASK_STATUSES = {
    "todo": "Pendiente",
    "doing": "En proceso",
    "blocked": "Bloqueada",
    "done": "Terminada",
}
STATUS_LABELS = {**PROJECT_STATUSES, **TASK_STATUSES}
# Tooltips for the filter chips, shown on hover.
STATUS_HELP = {
    "todos": "Sin filtro: todas las páginas de la colección.",
    "idea": "Solo una idea: todavía no se planifica ni se ejecuta.",
    "planning": "En planificación: se define el alcance y las tareas.",
    "active": "En curso: hay trabajo activo ahora mismo.",
    "paused": "En pausa: se retomará más adelante.",
    "done": "Completado: el trabajo está terminado.",
    "archived": "Archivado: se conserva solo como historial.",
    "todo": "Pendiente: todavía sin empezar.",
    "doing": "En proceso: alguien está trabajando en ella.",
    "blocked": "Bloqueada: espera algo externo para avanzar.",
}
# Collections whose index page gets status filter chips.
STATUS_FILTERS = {"projects": PROJECT_STATUSES, "tasks": TASK_STATUSES}
