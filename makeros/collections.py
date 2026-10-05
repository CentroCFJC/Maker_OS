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
