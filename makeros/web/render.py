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

# Image sizes: markdown-it renders `![alt|grande](url)` with the size
# token inside alt; post-processing turns it into a classed <img>.
_IMG_TAG = re.compile(r"<img([^>]*)>")
_ALT_ATTR = re.compile(r'alt="([^"]*)"')
SIZE_CLASS = {"pequena": "img-pequena", "mediana": "img-mediana",
              "grande": "img-grande", "completa": "img-completa"}

# Obsidian-style callouts: the first line of a blockquote is `[!TYPE]`.
_CALLOUT_HEAD = re.compile(r"^>\s*\[!([A-Za-z]+)\]\s*(.*)$")


def _size_images(html: str) -> str:
    """`![texto|mediana](url)` -> <img class="img-mediana" alt="texto">."""

    def repl(match: re.Match[str]) -> str:
        attrs = match.group(1)
        alt_m = _ALT_ATTR.search(attrs)
        if alt_m is None or "|" not in alt_m.group(1):
            return match.group(0)
        text, _, token = alt_m.group(1).rpartition("|")
        token = token.strip().lower().replace("\u00fa", "u")
        if token in SIZE_CLASS:
            attrs = attrs[: alt_m.start(1)] + text.strip() + attrs[alt_m.end(1):]
            return f'<img class="{SIZE_CLASS[token]}"{attrs}>'
        if token.isdigit() and 5 <= int(token) <= 100:
            attrs = attrs[: alt_m.start(1)] + text.strip() + attrs[alt_m.end(1):]
            pct = int(token)
            return (
                f'<img class="img-pct" style="width:{pct}%;max-width:{pct}%"{attrs}>'
            )
        return match.group(0)

    return _IMG_TAG.sub(repl, html)


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
    return _size_images(_md.render(_WIKILINK.sub(repl, body)))
