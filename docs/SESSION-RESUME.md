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

Verification state: **49 pytest tests passing, ruff clean**, and the
full flow was smoke-tested over HTTP (login, sidebar, category pages,
create page, block add, htmx inline edit, watcher live reindex).

Git: two commits on `main` (`6aa5895` skeleton, `4b5fd95` Notion UI).
No remote configured yet.

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
make test                     # pytest (49 tests)
make lint                     # ruff
# Docker: cp .env.example .env (set MAKEROS_SECRET_KEY) && make docker-up
```

Env config: `MAKEROS_CONTENT_DIR`, `MAKEROS_PRIVATE_DIR`,
`MAKEROS_TEMPLATES_DIR`, `MAKEROS_DB_PATH`, `MAKEROS_SECRET_KEY`.

## Content seeds that exist

- `content/wiki/`: inicio, guia-del-sistema, plantillas
- `content/research/`: noclip-website, klipper, openscad
- `content/projects/exhibicion-cauce/project.md`
- `content/people/jacob.md`, `content/events/reunion-semanal.md`
- `templates/`: page, project, task, event, research, person, device,
  inventory

## Next steps (Phase 1 per plan)

1. Tasks: kanban by status with drag & drop (Sortable.js + htmx),
   list views, assignment to people, due dates, recurring
   materialization (`repeat` frontmatter).
2. People pages wiring (profile page: their tasks and projects).
3. Activity tracking table + monthly report generator (plan 2.9).
4. My-day view.
5. Later: exhibits live status, inventory, calendar sync, vault,
   AI layer (all degrade gracefully without an LLM).

## Standing rules

- Spanish UI text; English code/comments/commits.
- No emoji anywhere; no CDN assets (vendor into `static/vendor/`).
- Never write credentials into Markdown.
- `private/` is excluded from git (owner-only notes).
- Minimal diffs; every content-file write goes through
  `makeros/frontmatter.py`.
