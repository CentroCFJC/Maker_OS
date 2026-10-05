"""Jinja2 template registry (SSR only, no build chain)."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from .icons import SPRITE_URL

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def icon(name: str | None, cls: str = "icon") -> str:
    """Render a sprite icon inline; empty string when name is unset/blank."""
    if not name:
        return ""
    return Markup(f'<svg class="{cls}" aria-hidden="true">'
                   f'<use href="{SPRITE_URL}#{name}"/></svg>')


templates.env.globals["icon"] = icon
