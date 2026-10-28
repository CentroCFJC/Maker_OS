"""Typed creation forms: per-collection fields for the /nuevo pages.

Each collection gets the form fields that matter for tracking it; the
creation template still seeds the page (empty fields keep the template
value). Field kinds: text, textarea, date, datetime, select, url, banner.
"""

from __future__ import annotations

from ..collections import PROJECT_STATUSES, TASK_STATUSES

RESEARCH_TYPES = {
    "repo": "Repo",
    "paper": "Paper",
    "article": "Artículo",
    "video": "Video",
    "tool": "Herramienta",
}
TASK_PRIORITIES = {"low": "Baja", "normal": "Normal", "high": "Alta", "urgent": "Urgente"}
INVENTORY_TYPES = {
    "impresora-3d": "Impresora 3D",
    "laser": "Láser",
    "herramienta": "Herramienta",
    "equipo": "Equipo",
    "consumible": "Consumible",
}
INVENTORY_CONDITIONS = {
    "nuevo": "Nuevo",
    "bueno": "Bueno",
    "desgastado": "Desgastado",
    "fuera-de-servicio": "Fuera de servicio",
}
DEVICE_STATUS = {"up": "Encendido", "down": "Apagado", "maintenance": "Mantenimiento"}

DEFAULT_FIELDS = [
    {"name": "title", "kind": "text", "label": "Título", "required": True},
    {
        "name": "body",
        "kind": "textarea",
        "label": "Contenido inicial (Markdown, opcional — se usa la plantilla si se omite)",
    },
]

FORM_FIELDS: dict[str, list[dict]] = {
    "projects": [
        {"name": "title", "kind": "text", "label": "Nombre del proyecto", "required": True},
        {"name": "status", "kind": "select", "label": "Estado", "options": PROJECT_STATUSES},
        {"name": "lead", "kind": "people", "label": "Responsable"},
        {"name": "start", "kind": "date", "label": "Inicio"},
        {"name": "due", "kind": "date", "label": "Vencimiento"},
        {"name": "banner", "kind": "banner", "label": "Portada"},
        {
            "name": "body",
            "kind": "textarea",
            "label": "Descripción del proyecto (Markdown, opcional)",
        },
    ],
    "research": [
        {"name": "title", "kind": "text", "label": "Título del recurso", "required": True},
        {"name": "type", "kind": "select", "label": "Tipo", "options": RESEARCH_TYPES},
        {"name": "url", "kind": "url", "label": "URL"},
        {"name": "project", "kind": "text", "label": "Proyecto relacionado (slug, opcional)"},
        {
            "name": "body",
            "kind": "textarea",
            "label": "Por qué importa / resumen (Markdown, opcional)",
        },
    ],
    "tasks": [
        {"name": "title", "kind": "text", "label": "Título de la tarea", "required": True},
        {"name": "project", "kind": "text", "label": "Proyecto (slug, opcional)"},
        {"name": "assignee", "kind": "people", "label": "Asignada a"},
        {"name": "due", "kind": "date", "label": "Vencimiento"},
        {"name": "priority", "kind": "select", "label": "Prioridad", "options": TASK_PRIORITIES},
        {"name": "status", "kind": "select", "label": "Estado", "options": TASK_STATUSES},
        {
            "name": "body",
            "kind": "textarea",
            "label": "Descripción: contexto, pasos, criterio de terminar (Markdown, opcional)",
        },
    ],
    "calendario": [
        {"name": "title", "kind": "text", "label": "Título del evento", "required": True},
        {"name": "start", "kind": "datetime", "label": "Inicio"},
        {"name": "end", "kind": "datetime", "label": "Fin"},
        {"name": "location", "kind": "text", "label": "Lugar"},
        {"name": "people", "kind": "people", "label": "Personas asignadas"},
        {"name": "category", "kind": "event_category", "label": "Categoría"},
        {
            "name": "body",
            "kind": "textarea",
            "label": "Agenda o notas (Markdown, opcional)",
        },
    ],
    "inventory": [
        {
            "name": "title",
            "kind": "text",
            "label": "Nombre del equipo o artículo",
            "required": True,
        },
        {"name": "type", "kind": "select", "label": "Tipo", "options": INVENTORY_TYPES},
        {"name": "model", "kind": "text", "label": "Modelo"},
        {"name": "serial", "kind": "text", "label": "Número de serie"},
        {"name": "location", "kind": "text", "label": "Ubicación"},
        {"name": "condition", "kind": "select", "label": "Estado", "options": INVENTORY_CONDITIONS},
        {
            "name": "body",
            "kind": "textarea",
            "label": "Notas de uso / consumibles (Markdown, opcional)",
        },
    ],
    "people": [
        {"name": "title", "kind": "text", "label": "Nombre visible", "required": True},
        {"name": "username", "kind": "text", "label": "Usuario (username)"},
        {
            "name": "body",
            "kind": "textarea",
            "label": "Skills y equipos a cargo (Markdown, opcional)",
        },
    ],
    "exhibits": [
        {"name": "title", "kind": "text", "label": "Nombre del dispositivo", "required": True},
        {"name": "ip", "kind": "text", "label": "Dirección IP"},
        {"name": "ssh_user", "kind": "text", "label": "Usuario SSH"},
        {"name": "location", "kind": "text", "label": "Ubicación (sala, rack…)"},
        {"name": "responsible", "kind": "text", "label": "Responsable (usuario)"},
        {
            "name": "body",
            "kind": "textarea",
            "label": "Instrucciones de operación (Markdown, opcional)",
        },
    ],
}


def fields_for(collection: str) -> list[dict]:
    """Form spec for a collection; wiki and unknown use the plain form."""
    return FORM_FIELDS.get(collection, DEFAULT_FIELDS)
