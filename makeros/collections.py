"""Content collections: the categories of the lab's Markdown tree.

Every category is a directory under content/ with its own index page,
URL scheme (/slug) and creation template. Adding a new category means
adding one entry here.
"""

from __future__ import annotations

# template = file in templates/ used as frontmatter seed when creating.
COLLECTIONS: dict[str, dict[str, str]] = {
    "wiki": {"label": "Wiki", "template": "page.md"},
    "projects": {"label": "Proyectos", "template": "project.md"},
    "tasks": {"label": "Tareas", "template": "task.md"},
    "calendario": {"label": "Calendario", "template": "event.md"},
    "research": {"label": "Repositorios", "template": "research.md"},
    "people": {"label": "Personas", "template": "person.md"},
    "inventory": {"label": "Inventario", "template": "inventory.md"},
    "exhibits": {"label": "Exhibiciones", "template": "device.md"},
}
