"""Markdown rendering for page bodies (CommonMark, raw HTML disabled)."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

# Raw HTML is disabled on purpose: wiki content is written by the team,
# but defense in depth matters on a lab server. [[wikilinks]] are
# expanded to internal links before rendering.
_md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
# Tables and strikethrough are GFM extensions disabled by the strict
# CommonMark preset; the lab's inventory pages need real tables.
_md.enable(["table", "strikethrough"])

_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

# Obsidian-style callouts: the first line of a blockquote is `[!TYPE]`.
_CALLOUT_HEAD = re.compile(r"^>\s*\[!([A-Za-z]+)\]\s*(.*)$")


def _render_callout(text: str) -> str:
    """Render a `[!TYPE] Título` blockquote as a styled callout div."""
    lines = text.strip().split("\n")
    match = _CALLOUT_HEAD.match(lines[0])
    kind = re.sub(r"[^a-z-]", "", match.group(1).lower()) or "info"
    title_html = _md.renderInline(match.group(2)) if match.group(2) else kind
    body = "\n".join(line.lstrip("> ") for line in lines[1:])
    inner = _md.render(body) if body.strip() else ""
    return (
        f'<div class="callout callout-{kind}">'
        f'<p class="callout-title">{title_html}</p>{inner}</div>'
    )


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

    stripped = body.strip()
    if stripped.startswith(">") and _CALLOUT_HEAD.match(stripped.split("\n", 1)[0]):
        return _render_callout(stripped)
    return _md.render(_WIKILINK.sub(repl, body))
