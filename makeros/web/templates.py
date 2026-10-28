"""Jinja2 template registry (SSR only, no build chain)."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import ChainableUndefined
from markupsafe import Markup

from .blocks import BLOCK_ICONS, BLOCK_SEEDS, BLOCK_TYPES
from .icons import SPRITE_URL

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# A missing context key renders as empty instead of blowing up the page
# (e.g. a hot-reloaded template while the process predates a feature).
templates.env.undefined = ChainableUndefined


def icon(name: str | None, cls: str = "icon") -> str:
    """Render a sprite icon inline; empty string when name is unset/blank."""
    if not name:
        return ""
    return Markup(f'<svg class="{cls}" aria-hidden="true">'
                   f'<use href="{SPRITE_URL}#{name}"/></svg>')


templates.env.globals["icon"] = icon
templates.env.globals["block_types"] = BLOCK_TYPES
templates.env.globals["block_icons"] = BLOCK_ICONS
templates.env.globals["block_seeds"] = BLOCK_SEEDS
