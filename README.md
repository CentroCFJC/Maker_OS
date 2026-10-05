# MakerOS

Operating system for a prototyping lab — the Centro de Ciencia
Francisco José de Caldas maker lab. **Markdown is the source of
truth**: every project, task, device page and wiki entry is a plain
Markdown file in a git repo. MakerOS indexes them into SQLite and
renders a web UI on top. The data outlives the app.

Self-hosted, no third-party SaaS, Spanish-first UI, works fully
offline — local LLM features (later phases) degrade gracefully when
no model is running.

Full plan: [`docs/PLAN.md`](docs/PLAN.md).

## Status

Phase 0 — skeleton: FastAPI app, Markdown indexing, FTS5 full-text
search, local accounts, wiki rendering.

## Quickstart (dev)

```bash
make setup                # venv + editable install with dev deps
make user u=jacob r=admin # create the admin account (prompts password)
make run                  # http://localhost:8000
```

## Quickstart (Docker)

```bash
cp .env.example .env      # set MAKEROS_SECRET_KEY
make docker-up            # app + Caddy on http://<host>:8080
```

Content lives in `content/` (git it!). Per-user private notes live in
`private/` and must never be pushed to the shared remote.

## Layout

```
content/        Markdown source of truth (projects, tasks, wiki, ...)
templates/      Content templates (project, task, device, research, person)
makeros/        The app
  frontmatter.py  single choke point for every content-file read/write
  db.py           SQLite schema + connection factory
  indexer.py      FTS5 index + watchfiles watcher
  auth.py         Argon2 accounts
  web/            FastAPI routes, Jinja2 templates, static CSS
tests/          pytest suite
docs/PLAN.md    The planning document
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `MAKEROS_SECRET_KEY` | dev value (change it) | session cookie signing |
| `MAKEROS_CONTENT_DIR` | `./content` | shared Markdown tree |
| `MAKEROS_PRIVATE_DIR` | `./private` | per-user private notes (owner-only) |
| `MAKEROS_DB_PATH` | `./data/makeros.db` | SQLite index + users |
