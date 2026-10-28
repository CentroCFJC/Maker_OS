"""Obsidian-style wiki vault: folders, tree navigation, moves, graph.

Wiki documentation is a plain Markdown tree under content/wiki/ (the
"vault"). Folders are free-form; pages live anywhere in the tree and
are linked with [[wikilinks]]. This module provides the tree builder,
folder creation, moves (with link rewriting) and the graph data.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field

from .. import frontmatter
from ..indexer import index_file, list_collection, remove_document

WIKILINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")
SLUG_PART = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-_]*$")


def valid_vault_path(path: str) -> bool:
    """Folder/file path inside the vault: slug parts joined by '/'."""
    path = path.strip().strip("/")
    if not path:
        return False
    return all(SLUG_PART.match(part) for part in path.split("/"))


@dataclass
class Folder:
    name: str
    path: str  # relative to wiki/, no leading slash
    folders: list[Folder] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)  # {"path", "title"}

    def sort_all(self) -> None:
        self.folders.sort(key=lambda f: f.name.lower())
        self.files.sort(key=lambda f: f["title"].lower())


def build_tree(conn: sqlite3.Connection, base: str = "") -> Folder:
    """Folders + pages as a tree, scoped to `base` ("" = whole vault)."""
    root = Folder(name=base.rsplit("/", 1)[-1] or "wiki", path=base)
    nodes: dict[str, Folder] = {base: root}
    for doc in list_collection(conn, "wiki"):
        rel = doc["path"][len("wiki/"):]
        if base and not rel.startswith(base + "/"):
            continue
        parts = rel.split("/")
        # Walk/create the folder chain.
        current = base
        for part in parts[:-1]:
            parent_key = current
            current = f"{current}/{part}".strip("/")
            if current not in nodes:
                folder = Folder(name=part, path=current)
                nodes[parent_key].folders.append(folder)
                nodes[current] = folder
        dir_key = "/".join(parts[:-1]) or base
        folder = nodes.get(dir_key, root)
        folder.files.append({"path": doc["path"], "title": doc["title"] or rel})
    root.sort_all()
    for folder in nodes.values():
        folder.sort_all()
    return root


def is_folder(settings, path: str) -> bool:
    """True if the vault path is an existing directory."""
    target = (settings.content_dir / "wiki" / path).resolve()
    root = (settings.content_dir / "wiki").resolve()
    return root in target.parents and target.is_dir()


def create_folder(settings, path: str) -> None:
    (settings.content_dir / "wiki" / path).mkdir(parents=True, exist_ok=True)


def move_page(
    conn: sqlite3.Connection, settings, old_path: str, new_path: str
) -> None:
    """Move a wiki page and rewrite [[links]] that pointed at it.

    `old_path`/`new_path` are doc paths ('wiki/foo/bar', no extension).
    """
    old_file = settings.content_dir / f"{old_path}.md"
    new_file = settings.content_dir / f"{new_path}.md"
    new_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.rename(new_file)
    remove_document(conn, old_path)
    index_file(conn, settings.content_dir, new_file)

    # Rewrite incoming wikilinks: [[old]], [[old|label]], [[old.md]].
    old_rel = old_path[len("wiki/"):]
    new_rel = new_path[len("wiki/"):]
    for doc in list_collection(conn, "wiki"):
        if doc["path"] == new_path:
            continue
        file = settings.content_dir / f"{doc['path']}.md"
        meta, body = frontmatter.read(file)
        if f"[[{old_rel}" not in body:
            continue

        def repl(match: re.Match[str]) -> str:
            target, label = match.group(1), match.group(2)
            target = target.strip()
            if target.endswith(".md"):
                target = target[:-3]
            if target == old_rel or target == old_path:
                return f"[[{new_rel}|{label}]]" if label else f"[[{new_rel}]]"
            return match.group(0)

        updated = WIKILINK.sub(repl, body)
        if updated != body:
            frontmatter.write(file, meta, updated)
            index_file(conn, settings.content_dir, file)


def move_folder(
    conn: sqlite3.Connection, settings, old_path: str, new_path: str
) -> None:
    """Move a folder with all the pages inside; [[links]] are rewritten.

    `old_path`/`new_path` are folder paths relative to wiki/ (no file).
    """
    pages = [
        doc["path"]
        for doc in list_collection(conn, "wiki")
        if doc["path"].startswith(f"wiki/{old_path}/")
    ]
    for path in pages:
        rel = path[len("wiki/"):]
        new_rel = f"{new_path}/{rel[len(old_path) + 1:]}"
        move_page(conn, settings, path, f"wiki/{new_rel}")
    # Drop the now-empty source directories so they don't linger on disk.
    wiki_root = settings.content_dir / "wiki"
    current = settings.content_dir / "wiki" / old_path
    while current != wiki_root:
        try:
            current.rmdir()
        except OSError:  # not empty or a file — stop climbing
            break
        current = current.parent


BRAIN_COLLECTIONS = ("wiki", "avisos", "projects", "tasks", "research", "inventory")


def graph_data(conn: sqlite3.Connection) -> dict:
    """Second-brain graph: nodes = pages of every collection.

    Edges are [[wikilinks]] (resolved by path or last segment, like
    Obsidian) plus task->project and research->project links from
    frontmatter. `collection` on each node drives the theme colors.
    """
    docs: list[tuple[str, sqlite3.Row]] = []
    for slug in BRAIN_COLLECTIONS:
        for doc in list_collection(conn, slug):
            docs.append((slug, doc))

    nodes = [
        {
            "id": doc["path"],
            "title": doc["title"] or doc["path"],
            "collection": collection,
            "folder": doc["path"].rsplit("/", 1)[0]
            if "/" in doc["path"] else "",
        }
        for collection, doc in docs
    ]
    by_rel: dict[str, list[str]] = {}
    by_tail: dict[str, list[str]] = {}
    for _slug, doc in docs:
        rel = doc["path"][len("wiki/"):] if doc["path"].startswith("wiki/") else doc["path"]
        by_rel.setdefault(rel, []).append(doc["path"])
        by_tail.setdefault(doc["path"].rsplit("/", 1)[-1], []).append(doc["path"])

    ids = {n["id"] for n in nodes}
    edges = []
    seen: set[tuple[str, str]] = set()

    def add_edge(source: str, target: str) -> None:
        if source == target or target not in ids:
            return
        edge = tuple(sorted((source, target)))
        if edge not in seen:
            seen.add(edge)
            edges.append({"source": source, "target": target})

    for _collection, doc in docs:
        for match in WIKILINK.finditer(doc["body"] or ""):
            raw = match.group(1).strip()
            if raw.endswith(".md"):
                raw = raw[:-3]
            raw = raw.replace(" ", "-")
            for target in by_rel.get(raw, []) or by_tail.get(raw, []):
                add_edge(doc["path"], target)
        try:
            meta = json.loads(doc["meta_json"] or "{}")
        except ValueError:
            meta = {}
        project = str(meta.get("project") or "").strip()
        if project:
            add_edge(doc["path"], f"projects/{project}/project")
    return {"nodes": nodes, "edges": edges}
