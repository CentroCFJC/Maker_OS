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
  on page + cards. IMPORTANT route-order fix: `page_view` (catch-all
  `/{collection}/{page_path:path}`) must stay registered LAST in its
  router — it shadowed the block GET routes (inline edit forms 404'd)
  until it was moved.
- **Card density steps** — done. The card slider is stepped (1–4), not
  continuous; text size never changes. Steps set `data-step` on
  .card-grid (CSS `--card-min` + `.step-2/3/4` visibility rules):
  1 Compacta (título + estado, 150px), 2 Normal (portada y
  actualización, 220px, server default), 3 Detallada (fechas y
  progreso, 330px), 4 Completa (descripción, 460px). Saved per browser
  in localStorage (`makeros-card-step`).
- **Typed creation forms** — done. `/nuevo` renders a per-collection
  form from `makeros/web/forms.py` (`FORM_FIELDS` + `fields_for`);
  `create_page` reads the raw form dynamically (`await request.form()`)
  and validates by kind (text/date/datetime/select/url/banner).
  Projects: nombre, estado, responsable, inicio, vencimiento, portada
  (upload/URL at creation), descripción. Research: tipo, URL, proyecto.
  Tasks: proyecto, asignación, vencimiento, prioridad, estado.
  Inventory: tipo, modelo, serie, ubicación, condición. Events: start/
  end via datetime-local (day-click prefills T09:00). Exhibits: ip,
  ssh_user, ubicación, responsable. Empty fields keep the template seed
  value; events without end keep end=start.
- **Block 3-dot menu + templates + rich cards** — done. Blocks hover
  menu (more-vertical): Editar, Duplicar, Mover arriba/abajo,
  Añadir debajo (full type list), Eliminar (routes: `.../duplicar`,
  `.../mover` with `hacia`). Per-collection template editor
  (`/{collection}/plantilla`, admin only) writes the seed template
  applied to every new page; invalid YAML → 400. Cards no longer
  scale text: the slider only sets `--card-min`; cards show banner,
  status badge, dates (red "vencido" when due is past), a 2-line
  extract of the body, progress bars (project task counts done/
  total, task checklist counts) — computed in `makeros/web/listing.py`.
  Filter chips (estado) have Spanish tooltips (`STATUS_HELP` in
  collections.py) explaining each status.

- **Task kanban + project grouping** — done (Phase 1 core started).
  `/tasks` has three views: Lista, Kanban, Tarjetas. Lista and Kanban
  group tasks under their project (section title links to the project
  page; unassigned tasks under "Sin proyecto"). Kanban: 4 columns
  (Pendiente/En proceso/Bloqueada/Terminada), drag & drop via vendored
  Sortable.js → `POST /{coll}/{page}/estado` writes `status` back to
  frontmatter. Status chips still filter; `vista=kanban` on non-task
  collections falls back to lista. Fixed breadcrumb bug: page_new.html
  linked `collection_label` ("Proyectos" → 404) instead of the slug.

Verification state: **99 pytest tests passing, ruff clean**; new flows
smoke-tested over HTTP (kanban markup, drag-drop status write, sortable
serving, breadcrumb fix).

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
make test                     # pytest (99 tests)
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

1. People pages wiring (profile page: their tasks and projects).
2. Activity tracking table + monthly report generator (plan 2.9).
3. My-day view.
4. Later: exhibits live status, inventory, AI extras (digest, template
   drafting) — ask-the-wiki RAG assistant is DONE (see below).

Latest delivered (this session):

- **CRITICAL modal gotcha (fixed)** — content injected via plain
  `fetch()` + `innerHTML` is NOT processed by htmx: every `hx-post`
  modal form was inert (submit fell back to a native GET, 200, nothing
  saved). Fix: `makerosProcessModal()` calls `htmx.process()` on the
  modal body after injection (with a retry until deferred htmx loads).
  ANY future modal content needs this. Server-side event creation +
  GCal push/pull verified working end-to-end against the live server.
- **Explorer = Windows-style** — /explorador: address bar with
  navigable route segments (`?carpeta=wiki/guias`), two panes (sticky
  tree pane left, content right), view toggle Tarjetas/Lista/Árbol.
  `_scope()` in explorer_routes walks the content tree; unknown routes
  fall back to root (no 404). Root shows all collections as folder cards.
- **Avisos = home-only board** — removed from the sidebar (kept in the
  graph legend). Home board auto-refreshes: htmx polling
  (`every 15s` → `GET /avisos/tablero/contenido`, bare fragment from
  home_routes; shares ensure_tablero).
- **Home layout** — Avisos and Esta semana each full-width (no longer
  side-by-side), Fijado after, then Proyectos + recent aside.
- **Brain popup polish** — FAB ink explicit per theme
  (`--brain-fab-ink`: white in light mode / deep ink in dark mode;
  set stroke+color — don't rely on currentColor through `<use>`).
  Popup scales with viewport (clamp(560px, 62vw, 1240px) ×
  clamp(420px, 78vh, 960px)) and is corner-drag resizable from the
  bottom-left handle (persisted in localStorage `makeros-brain-size`;
  canvas follows via dispatched window resize).
- **Second-brain popup** — floating button bottom-right (desktop only,
  hidden <900px) opens a corner panel with the graph of ALL collections
  (`BRAIN_COLLECTIONS`: wiki, avisos, projects, tasks, research,
  inventory): edges = wikilinks (resolved by path OR last segment,
  Obsidian-style) + task/research → project links from frontmatter.
  Visualization-only sim in makeros.js (`makerosStartBrain`), lazy
  JSON fetch (`GET /wiki/grafos/datos`), node colors from `--brain-*`
  CSS vars (light/dark variants), legend with section dots.
  `/wiki/grafos` full page now shows all collections too (drag/click
  interactive). `graph_data` rewritten — `docs` is a list of
  (collection, row) tuples there, don't unpack as plain rows.
- **Wiki cards default** — /wiki is now the card view (folders +
  tags + cards, like research); tree kept at `?vista=arbol`
  (DnD there); /wiki/<folder> redirects to /wiki?carpeta=<path>.
  FOLDER_COLLECTIONS = ("wiki", "research", "inventory").
- **Folder system on Repositorios/Inventario** — `?carpeta=` scopes the
  collection index (FOLDER_COLLECTIONS = research, inventory): folder
  cards on top (`_collection_folders`), breadcrumb, "+ Añadir" prefills
  the folder, `ruta` accepted for those collections in nuevo/create.
  Tag filter chips from item frontmatter tags (generic JS: `.tag-filter`
  chips with `data-tag` filter `.tagged-card`s by `data-tags`;
  data-filter-scope attribute). Cards show tag chips (step-3).
  `collection_items` items now carry `tags`.
- **UI alignment pass** — one 32px control height in `.header-actions`
  (primary, ghost, icon-picker summaries like "Nueva carpeta"), global
  `:focus-visible` accent rings, nicer `.item-empty` states.
- **Tasks: 3 states** — "Bloqueada" removed from `TASK_STATUSES`
  (todo/doing/done only); kanban grid 3 columns; blocked CSS deleted.
- **Richer kanban cards** — bold title, project chip (links to the
  project), priority chip (color-coded high/urgent), 2-line extract,
  dates + assignee. `priority` added to `collection_items`;
  `priority_labels` (forms.TASK_PRIORITIES) in base_ctx.
- **Modal backdrop** — lighter: `rgb(15 14 26 / 22%)` + 1px blur
  (single global dialog, applies to every popup).
- **Notes = full private vault** — `notes_routes.py` rewritten:
  `/notas` is a card view (folders as cards on top + note cards with
  tag chips), folder nav at `/notas/<folder>`, note pages at
  `/notas/<path>` with the SAME block editor (per-path block
  endpoints `/notas/{path}/bloques/...`). Create note via modal
  (`_note_form.html`: title, folder, tags, body; POST /notas/nuevo,
  hx → close+reload). Tag filter chips (client-side, from note
  frontmatter). Traversal-safe `_resolve` (must stay under
  `private/<user>/`); `_uploads` dir skipped from listings. NOTES:
  frontmatter.read returns (meta, body) 2-tuple; block partial ctx
  NEEDS `page_url` or all block URLs render empty (ChainableUndefined).
- **Live block editing (Obsidian-style)** — blocks are click-to-edit:
  `.block-content` carries `data-edit-url`; clicking (links excluded)
  swaps in the editor via `htmx.ajax`. Enter saves + renders + opens
  the next block (or creates a trailing paragraph at page end);
  Shift+Enter = newline; Ctrl+Enter / Escape / blur = save & close;
  "/" slash menu unchanged (Enter picks while open). Flow logic in
  makeros.js (`makerosBlockFlow`, delegated handlers; textarea-only —
  image URL input excluded). `_block_form` now shows a hint row +
  Cerrar. Auto-resizes. Works on notes pages too (same partial).
- **Page header + tags + card polish** — page title row is a
  `.page-header-row` (title left, Fijar/Dividir right, aligned top);
  tags render as pill chips below with a "en portada" pin chip when
  pinned. Cards: hover lift + shadow, meta pinned to card bottom with
  a divider, tighter icon, better title/leading.
- **Private notes** — `/notas`: one Markdown page per user at
  `private/<username>/notas.md`, full block editor via dedicated routes
  (`notes_routes.py`, page_url "/notas"; registered before the
  collection catch-all). Never indexed into shared FTS; images upload
  to `private/<user>/_uploads/` and serve owner-only through
  `/notas/media/{name}`. Sidebar: "Mis notas" (icon `lock`).
- **Explorer** — `/explorador`: Obsidian-style tree of ALL content
  (collection roots + nested folders), links use the path=URL
  convention (`explorer_routes.content_tree`). Sidebar entry
  ("Explorador"). Hidden collections (people, exhibits) are skipped.
- **Home upgrades** — top row: shared "Avisos" board (new `avisos`
  COLLECTIONS entry; `content/avisos/tablero.md` seeded on first home
  visit by `home_routes.ensure_tablero`; editable with blocks at
  /avisos/tablero) + "Esta semana" strip (7 day columns, events
  color-coded by category, today highlighted; `week_events()` —
  Jinja gotcha: dict key `items` is shadowed by dict.items, use
  `events`) + "Fijado" (`pinned: true` frontmatter; toggle button on
  every page header, POST `/{coll}/{page}/fijar`;
  `pinned_pages()` in explorer_routes, avisos excluded).
- **Global modal system** — `<dialog id="makeros-modal">` in base.html +
  `makerosOpenModal(url)` / `makerosCloseModal()` in makeros.js (fetches
  `?fragmento=1` fragments; backdrop/Escape/X close; htmx posts swap into
  `#makeros-modal-body`; server returns a tiny
  `makerosCloseModal(); reload()` script on success, or re-renders the
  fragment with a `modal-error` banner on failure). Used by: "+ Añadir"
  on list pages, calendar "+ Añadir evento" + day-cell "+", home hero
  buttons, admin "Añadir usuario" (GET /admin/usuarios/nuevo?fragmento=1
  → `_admin_user_form.html`). Form fields live in the
  `_form_fields.html` macro `render_form_fields` (Jinja gotcha: macro
  name must NOT shadow a parameter). `create_page` is split:
  `create_page` (modal plumbing) + `_create_page_body` (logic).
- **Kanban first** — tasks default to `vista=kanban`; cards are
  clickable → quick-edit modal (`_task_edit.html`, GET/POST
  `/tasks/{path}/editar`: title/status/assignee/priority/due/project,
  frontmatter only). Pencil button on each card. Drag-vs-click guard:
  `makerosKanbanDragBlocked()`.
- **Home** — hero greeting rotates through 30 date-based lines
  (`makeros/web/greetings.py`, day-of-year % 30); task groups use the
  kanban pastel colors (todo/doing/blocked/done, dark variants too).
- **Admin polish** — segmented pill tab bar (sticky), tab content in a
  card, accent-dot active state, row hover, focus rings; add-user via
  modal.
- **Exhibiciones hidden** — sidebar + admin Contenido skip
  `exhibits` (collection still exists).
- **Cards default** — collection pages default to `vista=tarjetas`
  (cookie default changed); `?vista=lista` still switches.
- **Split layout (Obsidian-style)** — `/dividir?p=wiki/a&p=wiki/b&p=wiki/c`
  (max 3 panes, `split_routes.py` + `split.html`): columns of iframes
  loading pages with `?panel=1` (base_ctx `panel` hides the sidebar via
  `.content-panel`). "Dividir" button on page headers + wiki navigator.
  Pane head: change path, close, add pane. Graph works as a pane.
- **Personas moved to admin** — sidebar skips the `people` collection;
  admin panel has a "Personas" tab (list + create; creation posts to
  `/people/nuevo`). `/people/<slug>` pages still exist.
- **People assignment** — field kind `people` in `forms.py` (select fed
  by base_ctx `people` list): tasks `assignee`, projects `lead`, calendar
  events `people`. Calendar events store `people` (comma slugs) in a new
  `calendar_events.people` column (migration in db.py AND in
  `event_store.SCHEMA` — both must stay in sync), round-tripping through
  Google `extendedProperties.private.people`. Event page shows chips.
- **Sidebar collapse button** — moved from the bottom row into a
  `.brand-row` at the top, right of the MakerOS title (icon swaps
  chevrons-left/right; empty-rail click still expands).
- **Vault drag & drop** — pages and folders in the wiki navigator are
  draggable; drop on a folder (or the empty area = current folder) to
  move. `vault.move_folder` moves all pages + rewrites `[[links]]`;
  endpoint `POST /wiki/carpeta/{path}/mover` (registered BEFORE the
  generic `/{page_path}/mover` or it gets swallowed).
- **RAG assistant** — `/asistente`: FTS5 retrieval (OR fallback for
  natural questions) + local LLM via `makeros/web/llm.py`
  (OpenAI-compatible, LM Studio default `http://localhost:1234/v1`;
  base URL + model set in admin → Integraciones; `llm.chat` returns
  None when offline → UI degrades). Answers cite source pages and can
  be saved as new wiki pages (`POST /asistente/guardar`). Sidebar has
  an "Asistente" entry (icon `cpu`).

Deployment (lab server, IP/Tailscale — see `docs/DEPLOY.md`):
- `MAKEROS_BASE_URL` = external address (ICS feed links).
- `MAKEROS_COOKIE_SECURE=1` only behind HTTPS (tailscale serve);
  never on plain HTTP over IP.
- ICS feed: `/calendario.ics?token=...` (token in `ui_settings`,
  admin-rotatable at `POST /calendario/token`). Google Calendar
  "Desde la URL" cannot fetch a private/tailnet address — tailnet
  clients only; Google OAuth needs the ts.net domain.

Admin panel (`/admin`, linked from sidebar user name, admin-only):
users CRUD (create, role change, password reset, delete; last-admin
and self-delete guarded) + config: site name (`ui_settings`
`site:name`, shown on home hero) and ICS feed token. Code:
`makeros/web/routes/admin_routes.py`, `templates/admin.html`,
auth helpers in `makeros/auth.py`.

UI: home is two-column (content + right aside with "Cambios
recientes"), section titles have accent bars; kanban lanes have
pastel tints (todo yellow, doing blue, blocked rose, done green)
keyed off `data-status` on `.kanban-col`.

Profile (`/perfil`, every account): avatar upload/remove (stored in
`content/_uploads/avatars/`, served login-gated via `/media/`,
`users.avatar` column — ALTER TABLE migration in `db.py`
`init_schema`), own display name, own password change. Sidebar user
name links to `/perfil` (members) or `/admin` (admins). Avatars and
banners share `makeros/web/uploads.py` helpers.

Admin panel also has: creation-template links per collection and
"Reconstruir índice" (`POST /admin/reindex`). Login card is
redesigned (logo + site name from `ui_settings`); `select` elements
are globally restyled to match the design system.

Theming: dark/light toggle lives next to the logout icon button in the
sidebar (icon-only) and on the standalone centered login page (no
sidebar there). Per-browser (`localStorage` `makeros-theme`, restored
pre-paint). Admin "Apariencia" tab: accent + background buttons that
auto-apply (instant DOM change + background fetch POST /admin/tema,
errors surface in #theme-status). Backgrounds: "Plano"/"Difuminado"
(lava: layered accent/orange/ink radial gradients)/"Puntos" (faint
16% accent dots). Login is a standalone template (no base.html).

Page/section icons: pickers are icon-only buttons LEFT of the page
title (page.html) / collection title (list.html, calendar.html);
_section_icon_picker.html shows the current icon, admin click opens
the grid. Dark mode: cal-day.out-month uses themed vars now.

Google Calendar sync (docs/GCALENDAR.md): `makeros/web/gcal.py`
(OAuth + Calendar API v3 via httpx, no google client lib). Credentials
(ID de cliente / Secreto) pasted in Admin → Integraciones, stored in
`ui_settings` `gcal:client_id/secret`; env GOOGLE_CLIENT_ID/SECRET
fallback. After OAuth connect, admin pastes the ONE calendar ID (no
calendarList call — it 403'd with events-only scope, so it's gone).
Auto-sync: entering /calendario pulls (45s debounce via
`schedule_sync`), creating a calendario page pushes immediately, a 5
min loop in main.py covers other pages. All syncs run in background
threads (`asyncio.to_thread`), never block requests. Redirect URI =
{MAKEROS_BASE_URL}/google/callback. Pull is incremental (syncToken) →
Markdown with gcal_id; push local events without gcal_id → Google;
cancellations delete files. Errors stored in `gcal:last_error`, shown
in admin, cleared on success. Network calls in module helpers
(oauth_post/api_get/api_post) for test monkeypatching.

Backgrounds: "Plano" / "Difuminado" (animated lava: drifting blurred
blobs on a fixed ::before layer, reduced-motion aware) / "Cuadrícula"
(faint graph-paper grid; replaced "Puntos").

Image blocks, final UX: add block opens the editor immediately;
toolbar is minimal (Subir imagen + URL field + Usar URL); the seed
`![Descripción de la imagen](…)` is REPLACED on insert (never appended
— that caused two images). Size is NOT a select: rendered images get
a corner drag handle (`.img-handle`, JS wraps img in `.img-wrap`),
drag snaps to 35/65/90/100% and POSTs
`/{coll}/{page}/bloques/{i}/tamano` (alt token update, returns block
partial). Blocks have prominent segmentation (10px padding, hover bg
+ inset ring). `makerosSetImageSize` is gone.

Block IMAGE uploads: common route
`POST /{collection}/{page}/imagenes` (members) stores under
`content/_uploads/<collection>/<page>/<slug>.<ext>` and returns JSON
`{url: /media/...}`; the block editor (imagen type) shows "Subir
imagen" + a Tamaño select that writes an alt token
`![texto|mediana](url)`; `render.py` `_size_images` post-processes
markdown-it output into `class="img-mediana"` (pequena 35% / mediana
65% / grande 90% / completa 100%). Jinja uses ChainableUndefined so a
hot-reloaded template with missing context keys degrades to empty
instead of a 500 (stale-process trap hit twice).

Event CATEGORIES: `event_categories` table (id slug / label / color;
defaults reunion/taller/proyecto/otro, logo palette; admin CRUD in the
admin "Categorías" tab, palette restricted to CATEGORY_PALETTE). Events
carry `category`; it round-trips through Google via
`extendedProperties.private.category`. Chips are tinted with
color-mix inline styles (light/dark aware); project milestones render
as the 'proyecto' category; Próximamente/event detail/ICS show labels.

Wiki vault (Obsidian direction, `makeros/web/vault.py`): /wiki is a
TREE NAVIGATOR (wiki_home.html, recursive Jinja macro, folders =
details/summary); folder URLs /wiki/<folder> render the scoped
navigator + breadcrumb (page_view falls back to is_folder). Create
folder: POST /wiki/carpeta {ruta} (nested ok, slug-validated). Create
page inside folder: page_new has a "ruta" field (?ruta= prefills; the
prefix applies BEFORE collision loop — file must be re-resolved or it
writes to the wrong path). Move/rename: POST /wiki/{page}/mover
{nueva_ruta} → vault.move_page (renames file, reindexes, rewrites
[[links]] in ALL wiki pages that pointed at the old path; form lives
in page.html footer, wiki only). Graph: GET /wiki/grafos →
graph_data(conn) nodes+edges (WIKILINK regex on bodies) rendered on a
canvas with a vanilla-JS force layout (drag, hover highlight, click
opens). RAG-ready: FTS5 over the vault + this graph structure are the
retrieval substrate for the LMStudio layer (PLAN 2.10, not built yet).
Wiki creation forms keep working; tests for the generic list/card
views now use /research instead of /wiki.

Calendar events are NOT Markdown anymore (user decision): they live in
the `calendar_events` SQLite table in Google Calendar API format
(`makeros/web/event_store.py`): id (Google id or `local-<uuid>` until
pushed), summary, location, description, start_json/end_json
({"date"} all-day | {"dateTime"} timed), status, html_link. Lifecycle:
create via /calendario/nuevo → `local-` row + force sync pushes to
Google; pull upserts rows; cancelled in Google deletes the row; delete
in MakerOS (`POST /calendario/evento/{id}/eliminar`) deletes row +
DELETE on Google. Chips link to `/calendario/evento/{id}` (event.html:
facts cards, "Abrir en Google", delete; edits happen in Google and pull
back). One-time migration in main.py lifespan converts legacy
calendario docs to rows and deletes the files. `day_map`/`build_ics`/
`todays_events`/sidebar counts read the store now. Calendar layout:
`.cal-wrap` grid — month grid (fluid, capped 1360px) + "Próximamente"
aside on the right, stacks under 1000px.

Sidebar is position: FIXED (sticky kept scrolling away — the old
`html, body {height: 100%}` capped its sticky container; now
`body {min-height: 100%}` and the sidebar is simply fixed; .content
gets margin-left: 240px; mobile off-canvas resets margin and disables
the rail). Collapse button (chevrons-left, .sidebar-collapse) toggles
`html[data-sidebar="collapsed"]`: 64px icon-only rail (labels/search/
user-meta hidden), state in localStorage `makeros-sidebar`, restored
pre-paint by the head script. Image drag resize is FREEFORM: 5-100%
saved as a numeric alt token (`![alt|12](url)` → img-pct inline width);
named sizes still work.

Deployment: `make serve` = uvicorn (127.0.0.1:8000, `SERVE_BIND`
overridable to 0.0.0.0 for LAN) + `tailscale serve --bg` + auto
`MAKEROS_BASE_URL` (from `tailscale status --json` Self.DNSName) and
`MAKEROS_COOKIE_SECURE=1`. `make serve-stop` = `tailscale serve
reset` (clears ALL serve configs on the machine) + kill; warns if a
sudo-owned process survives. `make serve-status` inspects uvicorn, pid
file, tailscale serve, ports. PID in .makeros.pid (gitignored), log in
.makeros.log. Tailnet URL: machine part via `tailscale set
--hostname=...`; tailnet part fixed by the Tailscale account (custom
domains need public DNS+ACME — not possible for a tailnet-only
server; ts.net is the way). Never run `make serve` with sudo.

## Standing rules

- Spanish UI text; English code/comments/commits.
- No emoji anywhere; no CDN assets (vendor into `static/vendor/`).
- Never write credentials into Markdown.
- `private/` is excluded from git (owner-only notes).
- Minimal diffs; every content-file write goes through
  `makeros/frontmatter.py`.
