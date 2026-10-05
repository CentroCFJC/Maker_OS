# MakerOS — Session Resume

> Context file for continuing work on this project in a fresh session.
> Start with: *"Read @docs/PLAN.md and @docs/SESSION-RESUME.md"*.
> Repo: `/home/jacob/Downloads/Dev/MakerOS` (renamed from `LabOS`).

## Project in one paragraph

MakerOS is a standalone, self-hosted web app for the Centro de Ciencia
FJC prototyping lab. **Markdown + YAML frontmatter is the source of
truth** (a git repo under `content/`); the app indexes it into SQLite
(FTS5) and renders a Notion-style web UI on top. Python 3.14 + FastAPI,
SSR + Jinja2 + htmx (vendored, no CDN), Spanish-first UI, English
code/comments. Full plan: `docs/PLAN.md`.

## Status (end of session)

Phases delivered:

- **Phase 0 (skeleton)** — done. FastAPI app, frontmatter module (single
  choke point for all content-file I/O, atomic writes), SQLite schema
  (users, documents, FTS5 index with triggers), watchfiles watcher that
  keeps the index fresh for on-disk edits, Argon2 auth (admin/member/
  viewer), FTS5 search, wiki rendering, CLI (`adduser`, `reindex`),
  Docker Compose (app + Caddy), Makefile.
- **Notion-style UI** — done. Light theme, sidebar with all 8 categories
  and live counts, logo (`assets/logo-CCFJC.png`, served at
  `/static/img/logo.png`), per-category "+ Añadir" page creation with
  template seeding, slug collision handling, projects create
  `<slug>/project.md` directories.
- **Block editor** — done. Pages render as Markdown blocks (titulo,
  parrafo, lista, checklist, tabla, codigo, cita) with add/edit/delete;
  inline edit via htmx; writes go through `makeros/frontmatter.py` and
  refresh the index immediately.
- **Per-page icons + list/grid views** — done. Vendored Feather sprite
  (`static/vendor/feather-sprite.svg`, icon names parsed from it in
  `makeros/web/icons.py`), `icon` frontmatter field set via a visual
  grid picker on each page (`POST /{coll}/{page}/icono`), and a
  per-user list-vs-cards toggle on collection indexes (`vista` cookie).
- **Calendar** — done. The former `events` collection is now
  `calendario` (URL `/calendario`, dir `content/calendario/`). Own SSR
  month grid (`makeros/web/calendar.py`) with event chips and project
  start/due chips, day-click event creation with `start`/`end`/
  `location` frontmatter, and a subscribable ICS feed at
  `/calendario.ics` (the "connect to Google Calendar" path). Google
  two-way OAuth sync is NOT built yet.
- **Design system + responsive UI** — done. CSS tokens come from the
  CCFJC logo (indigo `#29265b`, red `#e42c45`/`#c92038` AA, orange
  `#f4991f`); Schibsted Grotesk display font vendored in
  `static/vendor/`. Sidebar icons per collection (defaults in
  `makeros/collections.py`, admin overrides in the `ui_settings`
  SQLite table via `makeros/ui.py` + `POST /ui/icono/<coll>`), mobile
  off-canvas sidebar with toggle, block-editor controls go inline on
  mobile, card-size slider (localStorage), skip link, focus-visible,
  prefers-reduced-motion. Project skills in `.agents/skills/`
  (frontend-design, accessibility, fastapi) informed this pass.
- **Notion-style dashboard** — done, modeled on the team's old Notion
  page (see `notion-template.png`). Home: indigo hero ("Makerspace"),
  Proyectos section with status filter chips (`?estado=`) and cards
  with status badges, "Tareas sin proyecto" grouped by status with
  counts, Cambios recientes. Sidebar: "Enlaces rápidos", "Para hoy"
  (today's events from the calendar), "Bases de datos". Status
  vocabularies and Spanish labels in `makeros/collections.py`
  (PROJECT_STATUSES/TASK_STATUSES); badge colors are `.st-<value>`
  classes. Content column is full-width (readability cap only on
  long-form `.blocks`). Listing helpers shared by dashboard and index
  pages live in `makeros/web/listing.py`.
- **Rich blocks + banners** — done. Block menu (Obsidian-like): 12
  types incl. tabla, callout (`> [!INFO]`, `[!WARNING]`…), imagen,
  divisor, lista numerada; "/" slash menu inside the editor textarea
  (`data-slash-input` + makeros.js). GFM `table`/`strikethrough`
  enabled in render.py (tables never rendered before). Page banners
  (Notion covers): `banner` frontmatter (URL or `/media/...`),
  upload endpoint stores in `content/_uploads/` (png/jpg/webp/gif,
  5 MB max), served via login-gated `GET /media/{path}`; banners show
  on page + cards. Card-size slider scales cards proportionally
  (`--card-min` + `--card-scale`). IMPORTANT route-order fix:
  `page_view` (catch-all `/{collection}/{page_path:path}`) must stay
  registered LAST in its router — it shadowed the block GET routes
  (inline edit forms 404'd) until it was moved.

Verification state: **81 pytest tests passing, ruff clean**; new flows
smoke-tested over HTTP (tables, callouts, slash menu, banner upload +
media serving, inline edit form GET).

Git: commits on `main` per feature. No remote configured yet.

## Key architecture facts (do not relearn the hard way)

- Doc path `wiki/inicio` == URL `/wiki/inicio` — links are always
  `/{{ doc.path }}`, never double-prefixed. This was the original 404
  bug.
- Routes: `makeros/web/routes/collection_routes.py` is generic for all
  collections. Categories are defined in `makeros/collections.py` —
  adding a category = one entry there + a template in `templates/`.
- Block model: `makeros/web/blocks.py` (split/join, fence-aware).
- SQLite connections need `check_same_thread=False` (FastAPI runs sync
  dependencies and handlers in different threadpool threads) — already
  set in `makeros/db.py`.
- The watchfiles `watch_filter` receives `(change, path)` — two args.
  The watcher loop must never die; it retries on exceptions.
- Edit roles: `("admin", "member")`; viewers get 403 on write endpoints.

## Gotcha: folder rename and 404s

This project folder was renamed `LabOS -> MakerOS` mid-session. A
session started in the old folder gets tool failures / 404-style
"file not found" errors because its working directory is pinned to the
old path. Two mitigations exist:

- A compatibility symlink: `/home/jacob/Downloads/Dev/LabOS ->
  /home/jacob/Downloads/Dev/MakerOS`. It can be deleted; it exists only
  so stale sessions resolve paths.
- If a new session cannot find files, open the repo at
  `/home/jacob/Downloads/Dev/MakerOS` explicitly.

If pages 404 inside the running app instead, remember URLs are
`/<collection>/<page-slug>` (e.g. `/research/klipper`,
`/projects/exhibicion-cauce/project`) — file paths under `content/`
match URLs 1:1.

## How to run

```bash
cd /home/jacob/Downloads/Dev/MakerOS
make setup                    # venv + editable install with dev deps
make user u=jacob r=admin     # prompts password (getpass)
make run                      # http://localhost:8000
make test                     # pytest (81 tests)
make lint                     # ruff
# Docker: cp .env.example .env (set MAKEROS_SECRET_KEY) && make docker-up
```

Env config: `MAKEROS_CONTENT_DIR`, `MAKEROS_PRIVATE_DIR`,
`MAKEROS_TEMPLATES_DIR`, `MAKEROS_DB_PATH`, `MAKEROS_SECRET_KEY`.

## Content seeds that exist

- `content/wiki/`: inicio, guia-del-sistema, plantillas
- `content/research/`: noclip-website, klipper, openscad
- `content/projects/exhibicion-cauce/project.md`
- `content/people/jacob.md`, `content/calendario/reunion-semanal.md`
- `templates/`: page, project, task, event, research, person, device,
  inventory

## Next steps (Phase 1 per plan)

1. Tasks: kanban by status with drag & drop (Sortable.js + htmx),
   list views, assignment to people, due dates, recurring
   materialization (`repeat` frontmatter).
2. People pages wiring (profile page: their tasks and projects).
3. Activity tracking table + monthly report generator (plan 2.9).
4. My-day view.
5. Later: exhibits live status, inventory, Google Calendar two-way
   sync (OAuth; ICS feed already done), vault, AI layer (all degrade
   gracefully without an LLM).

## Standing rules

- Spanish UI text; English code/comments/commits.
- No emoji anywhere; no CDN assets (vendor into `static/vendor/`).
- Never write credentials into Markdown.
- `private/` is excluded from git (owner-only notes).
- Minimal diffs; every content-file write goes through
  `makeros/frontmatter.py`.
