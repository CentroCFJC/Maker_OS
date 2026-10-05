"""Markdown rendering for page bodies (CommonMark, raw HTML disabled)."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

# Raw HTML is disabled on purpose: wiki content is written by the team,
# but defense in depth matters on a lab server. [[wikilinks]] are
# expanded to internal links before rendering.
_md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})

_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def _wikilink_target(target: str) -> str:
    target = target.strip()
    if target.endswith(".md"):
        target = target[:-3]
    return target.replace(" ", "-")


def render_markdown(body: str) -> str:
    """Markdown body -> HTML, expanding [[wikilinks]] to /wiki/... links."""

    def repl(match: re.Match[str]) -> str:
        target = _wikilink_target(match.group(1))
        label = match.group(2) or target
        return f"[{label}](/wiki/{target})"

    return _md.render(_WIKILINK.sub(repl, body))
