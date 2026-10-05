"""Markdown + YAML frontmatter parsing and writing.

Every read or write of a content file in MakerOS goes through this
module, so the on-disk format stays uniform no matter who writes
(the web UI, the MCP server, or a person with vim). Writes are atomic
(.tmp + rename) because the file watcher must never index half-written
files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter as _fm
import yaml


class FrontmatterError(Exception):
    """A file could not be parsed as Markdown with YAML frontmatter."""


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Split raw file text into (frontmatter dict, Markdown body).

    Files without a leading '---' block are valid: they parse as
    (empty frontmatter, body).
    """
    if not text.startswith("---"):
        return {}, text
    try:
        post = _fm.loads(text)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(post.metadata, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    return dict(post.metadata), post.content


def dump(meta: dict[str, Any], body: str) -> str:
    """Render (frontmatter, body) back to full file text."""
    post = _fm.Post(body)
    post.metadata = dict(meta)
    return _fm.dumps(post, sort_keys=True)


def read(path: Path | str) -> tuple[dict[str, Any], str]:
    """Read a content file from disk."""
    return parse(Path(path).read_text(encoding="utf-8"))


def write(path: Path | str, meta: dict[str, Any], body: str) -> None:
    """Atomically write a content file (frontmatter + body)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(dump(meta, body), encoding="utf-8")
    tmp.replace(path)


def update_meta(path: Path | str, changes: dict[str, Any]) -> dict[str, Any]:
    """Merge frontmatter fields without touching the body."""
    meta, body = read(path)
    meta.update(changes)
    write(path, meta, body)
    return meta


def append_body(path: Path | str, text: str) -> None:
    """Append text to a document's body (e.g. maintenance log entries)."""
    meta, body = read(path)
    if body and not body.endswith("\n"):
        body += "\n"
    write(path, meta, body + text)
