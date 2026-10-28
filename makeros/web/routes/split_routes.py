"""Obsidian-style split layout: open up to three pages side by side.

`/dividir?p=wiki/a&p=wiki/b&p=wiki/grafos` renders one column per
`p` param; each column embeds the page with `?panel=1` (no sidebar).
The graph works as a pane like any other page.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..deps import ConnDep, UserDep, base_ctx
from ..templates import templates

router = APIRouter()

MAX_PANES = 3
_PATH = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9/_-]*$")


def _clean(value: str) -> str:
    value = value.strip().strip("/")
    return value if _PATH.match(value) else ""


@router.get("/dividir")
async def split_view(request: Request, conn: ConnDep, user: UserDep):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    panes = []
    for value in request.query_params.getlist("p"):
        value = _clean(value)
        if value:
            panes.append(value)
    if not panes:
        panes = ["wiki"]
    panes = panes[:MAX_PANES]
    return templates.TemplateResponse(
        request,
        "split.html",
        base_ctx(
            request, conn, user,
            panes=panes,
            max_panes=MAX_PANES,
        ),
    )
