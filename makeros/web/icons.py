"""Icon registry for the vendored Feather sprite.

The sprite (static/vendor/feather-sprite.svg, Feather Icons 4.29.2, MIT)
is the single source of truth for which icons exist: names are parsed
from its <symbol> ids, so the picker menu can never drift out of sync
with the shipped asset.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

SPRITE_PATH = Path(__file__).resolve().parent / "static" / "vendor" / "feather-sprite.svg"
SPRITE_URL = "/static/vendor/feather-sprite.svg"

_SYMBOL = re.compile(r'<symbol id="([^"]+)"')


@lru_cache(maxsize=1)
def icon_names() -> tuple[str, ...]:
    """All icon ids in the sprite, sorted."""
    text = SPRITE_PATH.read_text(encoding="utf-8")
    return tuple(sorted(set(_SYMBOL.findall(text))))


def is_valid_icon(name: str) -> bool:
    return name in icon_names()
