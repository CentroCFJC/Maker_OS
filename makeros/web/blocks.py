"""Block model: split a Markdown body into editable blocks and back.

MakerOS pages are edited Notion-style, as a list of blocks. The
storage format stays plain Markdown: blocks are blank-line separated
chunks (fenced code blocks are kept whole), and every block operation
writes the file back through the frontmatter module.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# Ordered block menu (the "/ menu" in the editor and the add menu).
# icon = name in the vendored Feather sprite.
BLOCK_TYPES: dict[str, str] = {
    "parrafo": "Párrafo",
    "titulo": "Título",
    "subtitulo": "Subtítulo",
    "lista": "Lista",
    "lista-numerada": "Lista numerada",
    "checklist": "Lista de tareas",
    "tabla": "Tabla",
    "codigo": "Código",
    "cita": "Cita",
    "callout": "Aviso destacado",
    "imagen": "Imagen",
    "divisor": "Divisor",
}
BLOCK_ICONS: dict[str, str] = {
    "parrafo": "type",
    "titulo": "hash",
    "subtitulo": "align-left",
    "lista": "list",
    "lista-numerada": "chevron-right",
    "checklist": "check-square",
    "tabla": "grid",
    "codigo": "code",
    "cita": "message-square",
    "callout": "info",
    "imagen": "image",
    "divisor": "minus",
}

# Markdown seed inserted when adding a block of the given type.
BLOCK_SEEDS: dict[str, str] = {
    "parrafo": "Escribe aquí…",
    "titulo": "# Título",
    "subtitulo": "## Subtítulo",
    "lista": "- Elemento",
    "lista-numerada": "1. Primer paso",
    "checklist": "- [ ] Tarea",
    "tabla": "| Columna 1 | Columna 2 |\n|---|---|\n|  |  |",
    "codigo": "```\ncódigo\n```",
    "cita": "> Cita",
    "callout": "> [!INFO] Título del aviso\n> Texto del aviso.",
    "imagen": "![Descripción de la imagen](https://…)",
    "divisor": "---",
}


class Block(NamedTuple):
    index: int
    kind: str
    text: str


def infer_kind(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        return "codigo"
    if re.match(r"^>\s*\[!", stripped):
        return "callout"
    if stripped.startswith("#"):
        return "titulo"
    if stripped.startswith("|"):
        return "tabla"
    if stripped.startswith(">"):
        return "cita"
    if re.match(r"^!\[", stripped):
        return "imagen"
    if re.match(r"^[-*+]\s\[", stripped):
        return "checklist"
    if re.match(r"^([-*+]|\d+\.)\s", stripped):
        return "lista"
    if re.fullmatch(r"(-{3,}|\*{3,})", stripped):
        return "separador"
    return "parrafo"


def split_blocks(body: str) -> list[Block]:
    """Split a Markdown body into blocks (fence-aware, blank-line separated)."""
    lines = body.strip("\n").split("\n")
    chunks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            current.append(line)
        elif not in_fence and not line.strip() and current:
            chunks.append("\n".join(current).strip("\n"))
            current = []
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current).strip("\n"))
    return [Block(i, infer_kind(t), t) for i, t in enumerate(chunks) if t.strip()]


def join_blocks(texts: list[str]) -> str:
    """Render block texts back to a Markdown body."""
    body = "\n\n".join(t.strip("\n") for t in texts if t.strip())
    return body + "\n" if body else ""
