"""Web layer: auth flow, wiki render, search, dashboard."""

from datetime import date

from fastapi.testclient import TestClient


def test_anonymous_is_redirected_to_login(client: TestClient):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_renders(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Contraseña" in response.text


def test_bad_login_shows_error(client: TestClient):
    response = client.post("/login", data={"username": "x", "password": "y"})
    assert response.status_code == 401
    assert "incorrectos" in response.text


def test_login_then_home(logged_in_client: TestClient):
    response = logged_in_client.get("/")
    assert response.status_code == 200
    assert "Jacob" in response.text  # greeting includes the user's name
    assert "Cambios recientes" in response.text


def test_logout(logged_in_client: TestClient):
    response = logged_in_client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert logged_in_client.get("/", follow_redirects=False).status_code == 303


def test_wiki_index_is_the_vault_navigator(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki")
    assert response.status_code == 200
    assert "Bienvenido a MakerOS" in response.text
    assert "Guía del sistema" in response.text
    # Cards by default; the Obsidian tree lives one click away.
    assert "card-grid" in response.text
    assert "Nueva carpeta" in response.text
    assert "vista=arbol" in response.text
    assert "/wiki/grafos" in response.text

    tree = logged_in_client.get("/wiki?vista=arbol")
    assert "vault-tree" in tree.text
    assert "Guía del sistema" in tree.text


def test_wiki_page_renders_markdown_and_wikilink(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki/inicio")
    assert response.status_code == 200
    assert "<h1>Bienvenido</h1>" in response.text
    assert '<a href="/wiki/guia-del-sistema">guia-del-sistema</a>' in response.text


def test_wiki_page_404(logged_in_client: TestClient):
    assert logged_in_client.get("/wiki/no-existe").status_code == 404


def test_wiki_path_traversal_blocked(logged_in_client: TestClient):
    response = logged_in_client.get(
        "/wiki/..%2f..%2f..%2fetc%2fpasswd", follow_redirects=False
    )
    assert response.status_code in (400, 404)
    assert "root:" not in response.text


def test_search_finds_and_highlights(logged_in_client: TestClient):
    response = logged_in_client.get("/search", params={"q": "laboratorio"})
    assert response.status_code == 200
    assert "Guía del sistema" in response.text
    assert "<mark>" in response.text


def test_search_empty_query_is_ok(logged_in_client: TestClient):
    response = logged_in_client.get("/search", params={"q": "  "})
    assert response.status_code == 200


def test_raw_html_in_markdown_is_escaped(logged_in_client: TestClient, settings):
    import time

    from makeros.frontmatter import write

    write(
        settings.content_dir / "wiki" / "malicioso.md",
        {"title": "Prueba XSS"},
        "antes <script>alert(1)</script> después",
    )

    deadline = time.time() + 10
    while time.time() < deadline:
        page = logged_in_client.get("/wiki/malicioso")
        if page.status_code == 200:
            break
        time.sleep(0.2)
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text


# --- Links, categories, creation and blocks ------------------------------


def test_links_use_doc_paths_not_double_prefix(logged_in_client: TestClient):
    # Documents are linked as "/<doc path>", never "/wiki/<doc path>".
    home = logged_in_client.get("/")
    assert 'href="/wiki/inicio"' in home.text
    wiki_index = logged_in_client.get("/wiki")
    assert 'href="/wiki/inicio"' in wiki_index.text
    search = logged_in_client.get("/search", params={"q": "laboratorio"})
    assert 'href="/wiki/guia-del-sistema"' in search.text


def test_unknown_collection_404(logged_in_client: TestClient):
    assert logged_in_client.get("/cosas").status_code == 404


def test_wiki_page_via_generic_route(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki/inicio")
    assert response.status_code == 200
    assert "<h1>Bienvenido</h1>" in response.text


def test_create_page(logged_in_client: TestClient, settings):
    response = logged_in_client.post(
        "/wiki/nuevo", data={"title": "Nueva Página Rara"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/wiki/nueva-pagina-rara"

    file = settings.content_dir / "wiki" / "nueva-pagina-rara.md"
    assert file.is_file()
    page = logged_in_client.get("/wiki/nueva-pagina-rara")
    assert page.status_code == 200
    assert "Nueva Página Rara" in page.text


def test_create_page_slug_collision(logged_in_client: TestClient, settings):
    for _ in range(2):
        response = logged_in_client.post(
            "/wiki/nuevo", data={"title": "Duplicada"}, follow_redirects=False
        )
    assert response.headers["location"] == "/wiki/duplicada-2"
    assert (settings.content_dir / "wiki" / "duplicada-2.md").is_file()


def test_create_project_uses_directory(logged_in_client: TestClient, settings):
    response = logged_in_client.post(
        "/projects/nuevo", data={"title": "Proyecto Prueba"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/projects/proyecto-prueba/project"
    assert (settings.content_dir / "projects" / "proyecto-prueba" / "project.md").is_file()


def test_block_add_and_edit_and_delete(logged_in_client: TestClient, settings):
    from makeros.frontmatter import read

    page_url = "/wiki/inicio"

    # Add a paragraph block at the end.
    response = logged_in_client.post(
        f"{page_url}/bloques/nuevo",
        data={"tipo": "parrafo", "despues": -1},
        follow_redirects=False,
    )
    assert response.status_code == 303
    _meta, body = read(settings.content_dir / "wiki" / "inicio.md")
    assert "Escribe aquí…" in body

    # Edit the first block (the heading).
    response = logged_in_client.post(
        f"{page_url}/bloques/0/editar",
        data={"text": "# Título editado"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    _meta, body = read(settings.content_dir / "wiki" / "inicio.md")
    assert body.startswith("# Título editado")
    assert "Bienvenido" not in body

    # Delete the seed block we just added (now index 2).
    response = logged_in_client.post(
        f"{page_url}/bloques/2/borrar", follow_redirects=False
    )
    assert response.status_code == 303
    _meta, body = read(settings.content_dir / "wiki" / "inicio.md")
    assert "Escribe aquí…" not in body


def test_block_edit_htmx_returns_partial(logged_in_client: TestClient):
    response = logged_in_client.post(
        "/wiki/inicio/bloques/0/editar",
        data={"text": "# Vía htmx"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'id="block-0"' in response.text
    assert "<h1>Vía htmx</h1>" in response.text
    # No full page shell in a partial swap.
    assert "<aside" not in response.text


def test_delete_page(logged_in_client: TestClient, settings):
    logged_in_client.post("/wiki/nuevo", data={"title": "Borrable"})
    response = logged_in_client.post("/wiki/borrable/borrar", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/wiki"
    assert not (settings.content_dir / "wiki" / "borrable.md").exists()


def test_viewer_cannot_edit(logged_in_client: TestClient, settings):
    from makeros import auth
    from makeros.db import connect, init_schema

    conn = connect(settings.db_path)
    init_schema(conn)
    auth.create_user(conn, "mirón", "clave123", role="viewer")
    conn.close()

    logged_in_client.post("/logout")
    logged_in_client.post("/login", data={"username": "mirón", "password": "clave123"})

    # Read access works, edit buttons hidden, write endpoints rejected.
    assert logged_in_client.get("/wiki/inicio").status_code == 200
    page = logged_in_client.get("/wiki/inicio")
    assert "Editar" not in page.text
    assert logged_in_client.get("/wiki/nuevo").status_code == 403
    assert (
        logged_in_client.post(
            "/wiki/inicio/bloques/nuevo", data={"tipo": "parrafo"}
        ).status_code
        == 403
    )


def test_static_assets_are_served(client: TestClient):
    # Regression: the /{collection}/{page_path:path} collection route used to
    # shadow the /static mount and 404 every asset.
    for asset in (
        "/static/css/makeros.css",
        "/static/vendor/htmx.min.js",
        "/static/vendor/feather-sprite.svg",
        "/static/img/logo.png",
    ):
        response = client.get(asset)
        assert response.status_code == 200, asset


def test_icon_registry_lists_sprite_symbols():
    from makeros.web.icons import icon_names

    names = icon_names()
    assert "activity" in names
    assert "zap" in names
    assert names == tuple(sorted(set(names)))


def test_page_icon_can_be_set_and_cleared(logged_in_client: TestClient, settings):
    from makeros import frontmatter

    response = logged_in_client.post(
        "/wiki/inicio/icono", data={"icon": "zap"}, follow_redirects=False
    )
    assert response.status_code == 303
    meta, _ = frontmatter.read(settings.content_dir / "wiki" / "inicio.md")
    assert meta.get("icon") == "zap"

    page = logged_in_client.get("/wiki/inicio")
    assert "feather-sprite.svg#zap" in page.text

    listing = logged_in_client.get("/wiki")
    assert "feather-sprite.svg#zap" in listing.text

    logged_in_client.post("/wiki/inicio/icono", data={"icon": ""})
    meta, _ = frontmatter.read(settings.content_dir / "wiki" / "inicio.md")
    assert "icon" not in meta


def test_invalid_icon_rejected(logged_in_client: TestClient):
    response = logged_in_client.post("/wiki/inicio/icono", data={"icon": "no-existe"})
    assert response.status_code == 400


def test_collection_view_toggle(logged_in_client: TestClient):
    default = logged_in_client.get("/research")
    assert "card-grid" in default.text
    assert "item-list" not in default.text

    grid = logged_in_client.get("/research?vista=lista")
    assert "item-list" in grid.text
    assert "vista=lista" in grid.headers.get("set-cookie", "")

    # The choice is remembered in the cookie.
    remembered = logged_in_client.get("/research")
    assert "item-list" in remembered.text


# ---------- Calendar ----------

def _reindex(settings):
    from makeros.db import connect
    from makeros.indexer import reindex_all

    conn = connect(settings.db_path)
    reindex_all(conn, settings.content_dir)
    conn.close()


def _write(path, meta, body="Agenda."):
    from makeros.frontmatter import write as fm_write

    fm_write(path, meta, body)


def _add_event(settings, summary, start, end="", location="", category=""):
    """Calendar events are SQLite rows (Google format), not files."""
    from makeros.db import connect
    from makeros.web import event_store

    conn = connect(settings.db_path)
    event_store.ensure_schema(conn)
    event_id = event_store.create_local_event(
        conn, summary, start, end, location, category=category
    )
    conn.close()
    return event_id


def test_calendar_view_shows_events_and_projects(logged_in_client: TestClient, settings):
    from datetime import date, timedelta

    day = date.today() + timedelta(days=3)
    nxt = day + timedelta(days=1)
    _add_event(
        settings, "Taller de impresión",
        f"{day.isoformat()} 16:00", f"{day.isoformat()} 18:00", "Sala CAUCE",
    )
    _write(
        settings.content_dir / "projects" / "cauce" / "project.md",
        {"name": "Exhibición CAUCE", "start": day.isoformat(), "due": nxt.isoformat()},
        "Proyecto de exhibición.",
    )
    _reindex(settings)

    month = day.strftime("%Y-%m")
    response = logged_in_client.get(f"/calendario?m={month}")
    assert response.status_code == 200
    assert "Taller de impresión" in response.text
    assert 'class="cal-chip event"' in response.text
    assert 'class="cal-chip project"' in response.text
    assert f"/calendario/nuevo?fecha={day.isoformat()}" in response.text
    assert "weekend" in response.text  # weekend cells flagged
    assert "Próximamente" in response.text
    assert "Conectar con Google Calendar" not in response.text  # moved to admin


def test_calendar_requires_login(client: TestClient):
    response = client.get("/calendario", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_ics_feed(logged_in_client: TestClient, settings):
    from datetime import date, timedelta

    day = date.today() + timedelta(days=2)
    _add_event(
        settings, "Cita con pausa, coma",
        f"{day.isoformat()} 10:00", f"{day.isoformat()} 11:00", "Sala",
    )
    _add_event(settings, "Jornada de puertas abiertas", day.isoformat())

    response = logged_in_client.get("/calendario.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    text = response.text
    assert text.startswith("BEGIN:VCALENDAR")
    assert "SUMMARY:Cita con pausa\\, coma" in text
    assert f"DTSTART:{day.strftime('%Y%m%d')}T100000" in text
    assert "DTSTART;VALUE=DATE:" + day.strftime("%Y%m%d") in text
    # All-day DTEND is exclusive (next day) per RFC 5545.
    assert "DTEND;VALUE=DATE:" + (day + timedelta(days=1)).strftime("%Y%m%d") in text
    assert text.rstrip().endswith("END:VCALENDAR")


def test_ics_feed_token_allows_client_without_login(client: TestClient, settings):
    import re

    from makeros.auth import create_user
    from makeros.db import connect, init_schema

    conn = connect(settings.db_path)
    init_schema(conn)
    create_user(conn, "jacob", "secreto123", role="admin")
    conn.close()

    # The admin panel shows the tokenized feed URL to a logged-in admin.
    client.post(
        "/login", data={"username": "jacob", "password": "secreto123"}
    )
    page = client.get("/admin")
    match = re.search(r"calendario\.ics\?token=([A-Za-z0-9_\-]+)", page.text)
    assert match, "tokenized feed URL missing from calendar page"
    token = match.group(1)

    # A separate client with no session cookie: valid token works,
    # bad token and no token get 401.
    anonymous = TestClient(client.app)
    ok = anonymous.get(f"/calendario.ics?token={token}")
    assert ok.status_code == 200
    assert ok.text.startswith("BEGIN:VCALENDAR")

    assert anonymous.get("/calendario.ics").status_code == 401
    assert anonymous.get("/calendario.ics?token=wrong").status_code == 401


def test_ics_feed_token_rotation(client: TestClient, settings):
    import re

    from makeros.auth import create_user
    from makeros.db import connect, init_schema

    conn = connect(settings.db_path)
    init_schema(conn)
    create_user(conn, "jacob", "secreto123", role="admin")
    conn.close()

    client.post(
        "/login", data={"username": "jacob", "password": "secreto123"}
    )
    token = re.search(
        r"calendario\.ics\?token=([A-Za-z0-9_\-]+)", client.get("/admin").text
    ).group(1)

    response = client.post("/calendario/token", follow_redirects=False)
    assert response.status_code == 303
    new_token = re.search(
        r"calendario\.ics\?token=([A-Za-z0-9_\-]+)", client.get("/admin").text
    ).group(1)
    assert new_token != token

    anonymous = TestClient(client.app)
    assert anonymous.get(f"/calendario.ics?token={token}").status_code == 401
    assert anonymous.get(f"/calendario.ics?token={new_token}").status_code == 200


def test_create_event_with_dates(logged_in_client: TestClient, settings):
    response = logged_in_client.post(
        "/calendario/nuevo",
        data={
            "title": "Reunión de planificación",
            "start": "2026-11-04 15:00",
            "end": "2026-11-04 16:30",
            "location": "Sala CAUCE",
            "body": "Puntos del día.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/calendario/evento/")

    from makeros.db import connect
    from makeros.web import event_store

    conn = connect(settings.db_path)
    event = event_store.get_event(
        conn, response.headers["location"].rsplit("/", 1)[-1]
    )
    conn.close()
    assert event["summary"] == "Reunión de planificación"
    assert event["start"].strftime("%Y-%m-%d %H:%M") == "2026-11-04 15:00"
    assert event["end"].strftime("%Y-%m-%d %H:%M") == "2026-11-04 16:30"
    assert event["location"] == "Sala CAUCE"
    assert event["description"] == "Puntos del día."


def test_create_event_defaults_end_to_start(logged_in_client: TestClient, settings):
    response = logged_in_client.post(
        "/calendario/nuevo", data={"title": "Puntual", "start": "2026-11-10"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    from makeros.db import connect
    from makeros.web import event_store

    conn = connect(settings.db_path)
    event = event_store.get_event(
        conn, response.headers["location"].rsplit("/", 1)[-1]
    )
    conn.close()
    assert event["start"].isoformat() == "2026-11-10"
    assert event["end"].isoformat() == "2026-11-10"


def test_create_event_rejects_bad_date(logged_in_client: TestClient):
    response = logged_in_client.post(
        "/calendario/nuevo", data={"title": "Roto", "start": "mañana"}
    )
    assert response.status_code == 400


def test_new_event_form_prefills_date(logged_in_client: TestClient):
    response = logged_in_client.get("/calendario/nuevo?fecha=2026-12-24")
    assert response.status_code == 200
    assert 'value="2026-12-24T09:00"' in response.text


def test_project_dates_show_on_cards_and_list(logged_in_client: TestClient, settings):
    _write(
        settings.content_dir / "projects" / "farol" / "project.md",
        {"name": "Farol de papel", "start": "2026-10-01", "due": "2026-10-20"},
        "Proyecto.",
    )
    _reindex(settings)

    cards = logged_in_client.get("/projects?vista=tarjetas")
    assert "Farol de papel" in cards.text
    assert "2026-10-01 → 2026-10-20" in cards.text

    listing = logged_in_client.get("/projects")
    assert "2026-10-01 → 2026-10-20" in listing.text


def test_icon_picker_is_a_visual_grid(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki/inicio")
    assert response.status_code == 200
    assert 'class="icon-grid"' in response.text
    assert 'name="icon" value="zap"' in response.text
    assert "makerosFilterIcons" in response.text


# ---------- Sidebar icons + card slider ----------

def test_sidebar_shows_default_collection_icons(logged_in_client: TestClient):
    response = logged_in_client.get("/")
    assert "feather-sprite.svg#book-open" in response.text
    assert "feather-sprite.svg#calendar" in response.text
    assert response.text.count("feather-sprite.svg#") >= 9


def test_admin_can_change_collection_icon(logged_in_client: TestClient):
    response = logged_in_client.post(
        "/ui/icono/wiki", data={"icon": "zap"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/wiki"
    assert "feather-sprite.svg#zap" in logged_in_client.get("/").text

    # The collection page offers the section picker with the active icon.
    page = logged_in_client.get("/wiki")
    assert "section-icon-picker" in page.text

    # Empty value resets to the code default.
    logged_in_client.post("/ui/icono/wiki", data={"icon": ""})
    assert "feather-sprite.svg#book-open" in logged_in_client.get("/").text


def test_invalid_collection_icon_rejected(logged_in_client: TestClient):
    response = logged_in_client.post("/ui/icono/wiki", data={"icon": "no-existe"})
    assert response.status_code == 400


def test_only_admin_changes_collection_icon(logged_in_client: TestClient, settings):
    from makeros import auth
    from makeros.db import connect, init_schema

    conn = connect(settings.db_path)
    init_schema(conn)
    auth.create_user(conn, "socio", "clave123", role="member")
    conn.close()
    logged_in_client.post("/logout")
    logged_in_client.post("/login", data={"username": "socio", "password": "clave123"})

    response = logged_in_client.post("/ui/icono/wiki", data={"icon": "zap"})
    assert response.status_code == 403
    picker = logged_in_client.get("/wiki")
    assert "section-icon-picker" not in picker.text


def test_card_size_slider_in_grid_view(logged_in_client: TestClient):
    response = logged_in_client.get("/research?vista=tarjetas")
    assert response.status_code == 200
    assert 'class="card-size-input"' in response.text
    assert "makerosCardSize" in response.text


def test_vendored_font_served(client: TestClient):
    assert client.get("/static/vendor/schibsted-grotesk.woff2").status_code == 200


# ---------- Homepage dashboard + status filters ----------

def _seed_dashboard(settings):
    from makeros.frontmatter import write as fm_write

    fm_write(
        settings.content_dir / "projects" / "cauce" / "project.md",
        {"name": "CAUCE", "status": "active", "start": "2026-06-01",
         "due": "2026-09-10"},
        "Exhibición interactiva.",
    )
    fm_write(
        settings.content_dir / "projects" / "inactivo" / "project.md",
        {"name": "Proyecto dormido", "status": "paused"},
        "En pausa.",
    )
    fm_write(
        settings.content_dir / "tasks" / "hackaton-vr.md",
        {"title": "Hackaton VR", "status": "todo", "project": ""},
        "Idea pendiente.",
    )
    fm_write(
        settings.content_dir / "tasks" / "con-proyecto.md",
        {"title": "Tarea asignada", "status": "doing", "project": "cauce"},
        "Pertenece a un proyecto.",
    )
    _reindex(settings)


def test_home_dashboard_sections(logged_in_client: TestClient, settings):
    _seed_dashboard(settings)
    response = logged_in_client.get("/")
    assert response.status_code == 200
    assert "Makerspace" in response.text
    assert "Jacob" in response.text  # greeting includes the user's name
    assert "Tareas sin proyecto" in response.text
    assert "Hackaton VR" in response.text            # unassigned task
    assert '<span class="count-pill">1</span>' in response.text  # one pending
    assert "Cambios recientes" in response.text
    # Sidebar sections from the Notion template.
    assert "Enlaces rápidos" in response.text
    assert "Bases de datos" in response.text
    # Active project shows a status badge.
    assert 'st-active">En proceso' in response.text


def test_home_project_filter(logged_in_client: TestClient, settings):
    _seed_dashboard(settings)
    active = logged_in_client.get("/?estado=active")
    assert "CAUCE" in active.text
    assert "Ver todos los proyectos (1)" in active.text  # only the active one

    paused = logged_in_client.get("/?estado=paused")
    assert "Proyecto dormido" in paused.text
    assert "Ver todos los proyectos (1)" in paused.text


def test_projects_page_status_chips(logged_in_client: TestClient, settings):
    _seed_dashboard(settings)
    response = logged_in_client.get("/projects")
    assert "filter-chip" in response.text
    assert "En proceso" in response.text  # chip label
    assert 'st-active">En proceso' in response.text

    filtered = logged_in_client.get("/projects?estado=paused")
    assert "Proyecto dormido" in filtered.text
    assert "CAUCE" not in filtered.text

    # The view toggle keeps the filter.
    grid = logged_in_client.get("/projects?estado=paused&vista=tarjetas")
    assert "estado=paused" in grid.text


def test_sidebar_para_hoy_shows_todays_events(logged_in_client: TestClient, settings):
    _add_event(
        settings, "Reunión de hoy",
        f"{date.today().isoformat()} 15:00", f"{date.today().isoformat()} 16:00",
    )
    response = logged_in_client.get("/")
    assert "Para hoy" in response.text
    assert "Reunión de hoy" in response.text


# ---------- Rich blocks + slash menu ----------

def test_add_menu_lists_all_block_types(logged_in_client: TestClient):
    page = logged_in_client.get("/wiki/inicio")
    for label in ("Tabla", "Aviso destacado", "Imagen", "Divisor",
                   "Lista numerada", "Subtítulo"):
        assert label in page.text


def test_block_editor_has_slash_menu(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki/inicio/bloques/0/editar")
    assert response.status_code == 200
    assert "data-slash-input" in response.text
    assert "data-slash-menu" in response.text
    assert 'data-tipo="tabla"' in response.text
    assert 'data-tipo="callout"' in response.text


def test_add_each_new_block_type(logged_in_client: TestClient, settings):
    for tipo in ("subtitulo", "lista-numerada", "divisor", "imagen", "callout", "tabla"):
        response = logged_in_client.post(
            "/wiki/inicio/bloques/nuevo", data={"tipo": tipo}, follow_redirects=False
        )
        assert response.status_code == 303
    page = logged_in_client.get("/wiki/inicio")
    assert "<hr" in page.text                        # divisor
    assert 'class="callout callout-info"' in page.text
    assert "<table>" in page.text                    # tabla


def test_callout_rendering(logged_in_client: TestClient, settings):
    from makeros.web.render import render_markdown

    html = render_markdown("> [!WARNING] Cuidado\n> Pilas calientes.")
    assert 'class="callout callout-warning"' in html
    assert "Cuidado" in html
    assert "Pilas calientes." in html


def test_banner_upload_and_media(logged_in_client: TestClient, settings):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # minimal stub, format checked by ext
    response = logged_in_client.post(
        "/wiki/inicio/banner",
        files={"archivo": ("portada.png", png, "image/png")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    from makeros import frontmatter

    meta, _ = frontmatter.read(settings.content_dir / "wiki" / "inicio.md")
    assert meta["banner"].startswith("/media/")
    assert meta["banner"].endswith(".png")
    uploads = settings.content_dir / "_uploads"
    assert list(uploads.glob("inicio-*.png"))

    page = logged_in_client.get("/wiki/inicio")
    assert "page-banner" in page.text
    assert "background-image" in page.text

    media = logged_in_client.get(meta["banner"])
    assert media.status_code == 200
    assert media.content == png

    # Anonymous users cannot read media files.
    logged_in_client.post("/logout")
    assert logged_in_client.get(meta["banner"], follow_redirects=False).status_code == 303


def test_banner_from_url_and_removal(logged_in_client: TestClient, settings):
    from makeros import frontmatter

    response = logged_in_client.post(
        "/wiki/inicio/banner",
        data={"url": "https://example.com/portada.jpg"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    meta, _ = frontmatter.read(settings.content_dir / "wiki" / "inicio.md")
    assert meta["banner"] == "https://example.com/portada.jpg"

    logged_in_client.post("/wiki/inicio/banner/borrar")
    meta, _ = frontmatter.read(settings.content_dir / "wiki" / "inicio.md")
    assert "banner" not in meta


def test_banner_rejects_bad_input(logged_in_client: TestClient):
    bad_url = logged_in_client.post("/wiki/inicio/banner", data={"url": "javascript:alert(1)"})
    assert bad_url.status_code == 400
    nothing = logged_in_client.post("/wiki/inicio/banner", data={})
    assert nothing.status_code == 400
    bad_ext = logged_in_client.post(
        "/wiki/inicio/banner", files={"archivo": ("mal.txt", b"x", "text/plain")}
    )
    assert bad_ext.status_code == 400


def test_banner_shows_on_cards(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "research" / "repo-banner.md",
           {"title": "Repo banner"}, "Notas.")
    _reindex(settings)
    logged_in_client.post(
        "/research/repo-banner/banner",
        data={"url": "https://example.com/x.png"},
        follow_redirects=False,
    )
    cards = logged_in_client.get("/research?vista=tarjetas")
    assert "card-banner" in cards.text
    assert "https://example.com/x.png" in cards.text


# ---------- Block menu, template editor, richer cards ----------

def test_block_menu_replaces_overlapping_controls(logged_in_client: TestClient):
    page = logged_in_client.get("/wiki/inicio")
    assert "block-menu" in page.text
    assert "more-vertical" in page.text
    assert "block-controls" not in page.text
    assert "Duplicar" in page.text
    assert "Mover arriba" in page.text


def test_block_duplicate_and_move(logged_in_client: TestClient, settings):
    from makeros import frontmatter

    # Duplicate the heading block.
    response = logged_in_client.post(
        "/wiki/inicio/bloques/0/duplicar", follow_redirects=False
    )
    assert response.status_code == 303
    _meta, body = frontmatter.read(settings.content_dir / "wiki" / "inicio.md")
    assert body.count("# Bienvenido") == 2

    # Move the duplicated heading below the paragraph.
    logged_in_client.post("/wiki/inicio/bloques/1/mover", data={"hacia": "abajo"})
    _meta, body = frontmatter.read(settings.content_dir / "wiki" / "inicio.md")
    chunks = body.split("\n\n")
    assert chunks[0] == "# Bienvenido"
    assert chunks[1].startswith("Este es el inicio")
    assert chunks[2] == "# Bienvenido"

    # Moving the last block up is a no-op redirect, not an error.
    response = logged_in_client.post(
        "/wiki/inicio/bloques/0/mover", data={"hacia": "arriba"}, follow_redirects=False
    )
    assert response.status_code == 303
    bad = logged_in_client.post("/wiki/inicio/bloques/0/mover", data={"hacia": "lados"})
    assert bad.status_code == 400


def test_template_editor_roundtrip(logged_in_client: TestClient, settings):
    form = logged_in_client.get("/wiki/plantilla")
    assert form.status_code == 200
    assert "Plantilla de Wiki" in form.text

    new_template = '---\ntitle: ""\ntags: []\n---\n\nContenido inicial nuevo.'
    response = logged_in_client.post(
        "/wiki/plantilla", data={"text": new_template}, follow_redirects=False
    )
    assert response.status_code == 303
    from makeros import frontmatter

    path = settings.templates_dir / "page.md"
    assert path.is_file()
    meta, body = frontmatter.read(path)
    assert body.strip() == "Contenido inicial nuevo."

    # The template now seeds new pages.
    logged_in_client.post("/wiki/nuevo", data={"title": "Sembrada"})
    _meta, seeded = frontmatter.read(settings.content_dir / "wiki" / "sembrada.md")
    assert seeded.strip() == "Contenido inicial nuevo."


def test_template_editor_rejects_bad_yaml_and_non_admin(logged_in_client: TestClient, settings):
    bad = logged_in_client.post(
        "/wiki/plantilla", data={"text": "---\ntitle: [unclosed\n---\n\nx"}
    )
    assert bad.status_code == 400

    from makeros import auth
    from makeros.db import connect, init_schema

    conn = connect(settings.db_path)
    init_schema(conn)
    auth.create_user(conn, "socio", "clave123", role="member")
    conn.close()
    logged_in_client.post("/logout")
    logged_in_client.post("/login", data={"username": "socio", "password": "clave123"})
    assert logged_in_client.get("/wiki/plantilla").status_code == 403


def test_cards_show_extract_and_task_progress(logged_in_client: TestClient, settings):
    from makeros.frontmatter import write as fm_write

    fm_write(
        settings.content_dir / "projects" / "cauce" / "project.md",
        {"name": "CAUCE", "status": "active", "start": "2026-06-01",
         "due": "2026-09-10"},
        "Exhibición interactiva sobre el agua para el museo.",
    )
    fm_write(
        settings.content_dir / "tasks" / "montar-cauce.md",
        {"title": "Montar estructura", "status": "done", "project": "cauce"},
        "Terminada.",
    )
    fm_write(
        settings.content_dir / "tasks" / "pintar-cauce.md",
        {"title": "Pintar paneles", "status": "todo", "project": "cauce"},
        "Pendiente.",
    )
    fm_write(
        settings.content_dir / "tasks" / "lista-compras.md",
        {"title": "Lista de compras", "status": "todo", "project": ""},
        "- [x] Filamento\n- [ ] PLA transparente\n- [ ] Cinta métrica",
    )
    _reindex(settings)

    cards = logged_in_client.get("/projects?vista=tarjetas")
    assert "Exhibición interactiva sobre el agua para el museo." in cards.text
    assert "progress-bar" in cards.text
    assert "1/2" in cards.text  # project task summary

    task_cards = logged_in_client.get("/tasks?vista=tarjetas")
    assert "1/3" in task_cards.text
    assert "hechas" in task_cards.text


def test_overdue_project_marked_in_cards(logged_in_client: TestClient, settings):
    from datetime import date, timedelta

    from makeros.frontmatter import write as fm_write

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    fm_write(
        settings.content_dir / "projects" / "tarde" / "project.md",
        {"name": "Proyecto atrasado", "status": "active", "due": yesterday},
        "Se pasó de fecha.",
    )
    _reindex(settings)
    cards = logged_in_client.get("/projects?vista=tarjetas")
    assert "vencido" in cards.text


def test_status_chips_have_tooltips(logged_in_client: TestClient):
    page = logged_in_client.get("/projects")
    assert 'title="Solo una idea' in page.text
    home = logged_in_client.get("/")
    assert 'title="Sin filtro' in home.text


def test_card_slider_is_stepped(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "research" / "repo-pasos.md",
           {"title": "Repo pasos"}, "Notas.")
    _reindex(settings)
    response = logged_in_client.get("/research?vista=tarjetas")
    assert 'min="1" max="4" step="1"' in response.text
    assert 'data-step="2"' in response.text   # server default: Normal
    assert "card-size-label" in response.text
    # Elements are gated by step classes in CSS, not stripped from HTML.
    assert "step-4" in response.text or "step-2" in response.text


# ---------- Typed creation forms ----------

def test_project_form_fields_and_creation(logged_in_client: TestClient, settings):
    form = logged_in_client.get("/projects/nuevo")
    assert "Nombre del proyecto" in form.text
    assert "Vencimiento" in form.text
    assert 'name="banner_file"' in form.text
    assert "<option value=\"active\">En proceso</option>" in form.text

    response = logged_in_client.post(
        "/projects/nuevo",
        data={
            "title": "Feria del Libro",
            "status": "active",
            "lead": "jacob",
            "start": "2026-10-19",
            "due": "2026-10-23",
            "body": "Match literario interactivo.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from makeros import frontmatter

    meta, body = frontmatter.read(
        settings.content_dir / "projects" / "feria-del-libro" / "project.md"
    )
    assert meta["title"] == "Feria del Libro"
    assert meta["status"] == "active"
    assert meta["lead"] == "jacob"
    assert meta["start"] == "2026-10-19"
    assert meta["due"] == "2026-10-23"
    assert "Match literario" in body


def test_project_create_with_banner_upload(logged_in_client: TestClient, settings):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    response = logged_in_client.post(
        "/projects/nuevo",
        files={"banner_file": ("portada.png", png, "image/png")},
        data={"title": "Con Portada", "status": "idea"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    from makeros import frontmatter

    meta, _ = frontmatter.read(
        settings.content_dir / "projects" / "con-portada" / "project.md"
    )
    assert meta["banner"].startswith("/media/")


def test_research_and_task_forms(logged_in_client: TestClient, settings):
    form = logged_in_client.get("/research/nuevo")
    assert "Tipo" in form.text and "URL" in form.text

    response = logged_in_client.post(
        "/research/nuevo",
        data={"title": "Klipper docs", "type": "paper",
              "url": "https://example.com/paper", "body": "Bueno."},
        follow_redirects=False,
    )
    assert response.status_code == 303
    from makeros import frontmatter

    meta, _ = frontmatter.read(settings.content_dir / "research" / "klipper-docs.md")
    assert meta["type"] == "paper"
    assert meta["url"] == "https://example.com/paper"

    logged_in_client.post(
        "/tasks/nuevo",
        data={"title": "Cambiar fusor", "project": "cauce", "assignee": "jacob",
              "due": "2026-11-01", "priority": "high"},
    )
    meta, _ = frontmatter.read(settings.content_dir / "tasks" / "cambiar-fusor.md")
    assert meta["project"] == "cauce"
    assert meta["assignee"] == "jacob"
    assert meta["due"] == "2026-11-01"
    assert meta["priority"] == "high"


def test_inventory_form_fields_and_creation(logged_in_client: TestClient, settings):
    form = logged_in_client.get("/inventory/nuevo")
    assert "Número de serie" in form.text
    assert "Fuera de servicio" in form.text

    logged_in_client.post(
        "/inventory/nuevo",
        data={"title": "Prusa MK4", "type": "impresora-3d", "model": "MK4",
              "serial": "SN-123", "location": "Sala CAUCE", "condition": "bueno"},
    )
    from makeros import frontmatter

    meta, _ = frontmatter.read(settings.content_dir / "inventory" / "prusa-mk4.md")
    assert meta["model"] == "MK4"
    assert meta["serial"] == "SN-123"
    assert meta["location"] == "Sala CAUCE"
    assert meta["condition"] == "bueno"


def test_typed_form_validation(logged_in_client: TestClient):
    bad_status = logged_in_client.post(
        "/projects/nuevo", data={"title": "X", "status": "inexistente"}
    )
    assert bad_status.status_code == 400
    bad_url = logged_in_client.post(
        "/research/nuevo", data={"title": "Y", "url": "ftp://mal.com"}
    )
    assert bad_url.status_code == 400
    bad_date = logged_in_client.post(
        "/tasks/nuevo", data={"title": "Z", "due": "pronto"}
    )
    assert bad_date.status_code == 400
    no_title = logged_in_client.post("/wiki/nuevo", data={"title": ""})
    assert no_title.status_code == 400


# ---------- Task kanban + grouped by project ----------

def _seed_tasks(settings):
    from makeros.frontmatter import write as fm_write

    fm_write(
        settings.content_dir / "projects" / "cauce" / "project.md",
        {"name": "CAUCE", "status": "active"},
        "Exhibición.",
    )
    fm_write(
        settings.content_dir / "tasks" / "montar.md",
        {"title": "Montar estructura", "status": "todo", "project": "cauce",
         "due": "2026-12-01", "assignee": "jacob"},
        "Pendiente.",
    )
    fm_write(
        settings.content_dir / "tasks" / "cableado.md",
        {"title": "Cablear sensores", "status": "doing", "project": "cauce"},
        "En marcha.",
    )
    fm_write(
        settings.content_dir / "tasks" / "sueltos.md",
        {"title": "Hackaton VR", "status": "todo", "project": ""},
        "Sin proyecto.",
    )
    _reindex(settings)


def test_tasks_kanban_grouped_by_project(logged_in_client: TestClient, settings):
    _seed_tasks(settings)
    response = logged_in_client.get("/tasks?vista=kanban")
    assert response.status_code == 200
    assert "kanban-col" in response.text
    assert 'data-status="todo"' in response.text
    assert 'data-status="done"' in response.text
    # Project section header links to the project page.
    assert 'href="/projects/cauce/project"' in response.text
    assert "Montar estructura" in response.text
    # Unassigned tasks fall under their own group.
    assert "Sin proyecto" in response.text
    assert "Hackaton VR" in response.text
    # Cards carry their path for the drag & drop endpoint.
    assert 'data-path="tasks/montar"' in response.text
    # Counts per column.
    assert "1" in response.text


def test_tasks_list_grouped_by_project(logged_in_client: TestClient, settings):
    _seed_tasks(settings)
    response = logged_in_client.get("/tasks?vista=lista")
    assert 'class="project-group"' in response.text
    assert 'href="/projects/cauce/project"' in response.text
    assert "Sin proyecto" in response.text


def test_kanban_toggle_only_on_tasks(logged_in_client: TestClient):
    tasks = logged_in_client.get("/tasks")
    assert ">Kanban</a>" in tasks.text
    wiki = logged_in_client.get("/research")
    assert ">Kanban</a>" not in wiki.text
    # Kanban on another collection falls back to the card view.
    fallback = logged_in_client.get("/research?vista=kanban")
    assert 'class="card-grid"' in fallback.text


def test_status_change_endpoint(logged_in_client: TestClient, settings):
    from makeros import frontmatter

    _seed_tasks(settings)
    response = logged_in_client.post(
        "/tasks/montar/estado", data={"estado": "done"}, follow_redirects=False
    )
    assert response.status_code == 303
    meta, _ = frontmatter.read(settings.content_dir / "tasks" / "montar.md")
    assert meta["status"] == "done"

    invalid = logged_in_client.post("/tasks/montar/estado", data={"estado": "perdido"})
    assert invalid.status_code == 400


def test_new_page_breadcrumb_links_to_slug(logged_in_client: TestClient):
    response = logged_in_client.get("/projects/nuevo")
    assert 'href="/projects"' in response.text
    assert 'href="/Proyectos"' not in response.text


def _admin_client(client: TestClient, settings, role="admin"):
    from makeros.auth import create_user
    from makeros.db import connect, init_schema

    conn = connect(settings.db_path)
    init_schema(conn)
    create_user(conn, "jacob", "secreto123", role=role)
    conn.close()
    client.post("/login", data={"username": "jacob", "password": "secreto123"})
    return client


def test_admin_panel_requires_admin(client: TestClient, settings):
    _admin_client(client, settings, role="viewer")
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 303


def test_admin_panel_lists_users_and_config(client: TestClient, settings):
    _admin_client(client, settings)
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Usuarios" in response.text
    assert "jacob" in response.text
    assert "Nombre del sitio" in response.text
    assert "calendario.ics?token=" in response.text
    # Tabs: every panel present, hidden ones only revealed by JS.
    for tab in ("usuarios", "apariencia", "contenido", "integracion", "sistema"):
        assert f'data-tab="{tab}"' in response.text


def test_admin_creates_user_and_sets_role(client: TestClient, settings):
    _admin_client(client, settings)
    created = client.post(
        "/admin/usuarios",
        data={"username": "maria", "password": "clave-segura1", "role": "member",
              "display_name": "María"},
        follow_redirects=False,
    )
    assert created.status_code == 303

    from makeros.db import connect

    conn = connect(settings.db_path)
    row = conn.execute("SELECT * FROM users WHERE username = 'maria'").fetchone()
    conn.close()
    assert row is not None and row["role"] == "member"

    promoted = client.post(
        f'/admin/usuarios/{row["id"]}/rol', data={"role": "admin"}, follow_redirects=False
    )
    assert promoted.status_code == 303
    conn = connect(settings.db_path)
    role_row = conn.execute(
        "SELECT role FROM users WHERE id = ?", (row["id"],)
    ).fetchone()
    assert role_row[0] == "admin"
    conn.close()


def test_admin_rejects_short_password_and_duplicate(client: TestClient, settings):
    _admin_client(client, settings)
    short = client.post(
        "/admin/usuarios", data={"username": "x", "password": "corta", "role": "member"}
    )
    assert short.status_code == 400
    dup = client.post(
        "/admin/usuarios", data={"username": "jacob", "password": "clave-segura1", "role": "member"}
    )
    assert dup.status_code == 400


def test_admin_cannot_demote_or_delete_last_admin(client: TestClient, settings):
    _admin_client(client, settings)
    me = client.post("/admin/usuarios/1/rol", data={"role": "member"})
    assert me.status_code == 400
    delete = client.post("/admin/usuarios/1/eliminar", follow_redirects=False)
    assert delete.status_code == 400


def test_admin_resets_password(client: TestClient, settings):
    _admin_client(client, settings)
    client.post(
        "/admin/usuarios",
        data={"username": "laura", "password": "clave-segura1", "role": "member"},
    )
    from makeros.db import connect

    conn = connect(settings.db_path)
    uid = conn.execute("SELECT id FROM users WHERE username = 'laura'").fetchone()[0]
    conn.close()
    reset = client.post(
        f"/admin/usuarios/{uid}/clave", data={"password": "nueva-clave9"}, follow_redirects=False
    )
    assert reset.status_code == 303

    fresh = TestClient(client.app)
    ok = fresh.post("/login", data={"username": "laura", "password": "nueva-clave9"})
    assert ok.status_code == 200


def test_admin_sets_site_name(client: TestClient, settings):
    _admin_client(client, settings)
    client.post("/admin/config", data={"site_name": "Laboratorio FJC"})
    response = client.get("/")
    assert "Laboratorio FJC" in response.text


# ---------- Profile: avatar, own data, own password ----------

def _png_bytes() -> bytes:
    # 1x1 transparent PNG.
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNg"
        "YGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
    )


def test_profile_avatar_upload_and_remove(logged_in_client: TestClient, settings):
    response = logged_in_client.get("/perfil")
    assert response.status_code == 200
    assert "Foto de perfil" in response.text

    upload = logged_in_client.post(
        "/perfil/avatar",
        files={"avatar": ("yo.png", _png_bytes(), "image/png")},
        follow_redirects=False,
    )
    assert upload.status_code == 303

    from makeros.db import connect

    conn = connect(settings.db_path)
    avatar = conn.execute("SELECT avatar FROM users WHERE username = 'jacob'").fetchone()[0]
    conn.close()
    assert avatar == "avatars/jacob.png"
    assert (settings.content_dir / "_uploads" / avatar).is_file()

    served = logged_in_client.get(f"/media/{avatar}")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")

    home = logged_in_client.get("/")
    assert f'src="/media/{avatar}"' in home.text  # sidebar shows the picture

    removed = logged_in_client.post(
        "/perfil/avatar/quitar", follow_redirects=False
    )
    assert removed.status_code == 303
    assert not (settings.content_dir / "_uploads" / avatar).exists()

    conn = connect(settings.db_path)
    assert conn.execute("SELECT avatar FROM users WHERE username = 'jacob'").fetchone()[0] == ""
    conn.close()


def test_profile_avatar_rejects_bad_extension(logged_in_client: TestClient):
    bad = logged_in_client.post(
        "/perfil/avatar",
        files={"avatar": ("script.svg", b"<svg/>", "image/svg+xml")},
    )
    assert bad.status_code == 400


def test_profile_changes_display_name_and_password(
    logged_in_client: TestClient, settings
):
    name = logged_in_client.post(
        "/perfil/datos", data={"display_name": "Jacob Lab"}, follow_redirects=False
    )
    assert name.status_code == 303
    home = logged_in_client.get("/")
    assert "Jacob Lab" in home.text

    wrong = logged_in_client.post(
        "/perfil/clave", data={"current": "incorrecta", "password": "nueva-clave9"}
    )
    assert "no coincide" in wrong.text

    ok = logged_in_client.post(
        "/perfil/clave",
        data={"current": "secreto123", "password": "nueva-clave9"},
        follow_redirects=False,
    )
    assert ok.status_code == 200
    assert "actualizada" in ok.text

    fresh = TestClient(logged_in_client.app)
    logged = fresh.post(
        "/login", data={"username": "jacob", "password": "nueva-clave9"},
        follow_redirects=False,
    )
    assert logged.status_code == 303


def test_admin_rebuilds_index(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "wiki" / "reindex-prueba.md", {"title": "Prueba Reindex"})
    _reindex(settings)
    response = logged_in_client.post("/admin/reindex", follow_redirects=False)
    assert response.status_code == 303

    from makeros.db import connect

    conn = connect(settings.db_path)
    row = conn.execute(
        "SELECT title FROM documents WHERE path = 'wiki/reindex-prueba'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_admin_sets_theme(logged_in_client: TestClient, settings):
    response = logged_in_client.post(
        "/admin/tema", data={"accent": "indigo", "fondo": "cuadricula"}, follow_redirects=False
    )
    assert response.status_code == 303
    home = logged_in_client.get("/")
    assert 'data-accent="indigo"' in home.text
    assert 'data-bg="cuadricula"' in home.text

    bad = logged_in_client.post("/admin/tema", data={"accent": "verde", "fondo": "blanco"})
    assert bad.status_code == 400

    reset = logged_in_client.post(
        "/admin/tema", data={"accent": "rojo", "fondo": "blanco"}, follow_redirects=False
    )
    assert reset.status_code == 303
    home = logged_in_client.get("/")
    assert 'data-accent="rojo"' in home.text


# ---------- Google Calendar sync ----------

def test_gcal_auth_url_shape():
    from makeros.web import gcal

    url = gcal.auth_url("mi-cliente", "https://fedora.tail120260.ts.net/google/callback")
    assert "accounts.google.com" in url
    assert "client_id=mi-cliente" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "calendar.events" in url
    assert "redirect_uri=https%3A%2F%2Ffedora.tail120260.ts.net%2Fgoogle%2Fcallback" in url


def test_gcal_sync_pull_and_push(settings, monkeypatch):
    from makeros.web import event_store, gcal

    # Local event born in MakerOS: must be pushed.
    _add_event(settings, "Taller local", "2026-11-10 15:00", "2026-11-10 17:00")

    import dataclasses

    from makeros.db import connect, init_schema
    from makeros.ui import set_ui

    settings = dataclasses.replace(
        settings, google_client_id="cid", google_client_secret="secret"
    )

    conn = connect(settings.db_path)
    init_schema(conn)
    event_store.ensure_schema(conn)
    set_ui(conn, gcal.KEY_REFRESH, "refresh-token")
    set_ui(conn, gcal.KEY_CALENDAR, "cal-123")

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    google_events = {
        "items": [
            {
                "id": "g-1",
                "summary": "Reunión remota",
                "start": {"dateTime": "2026-11-05T10:00:00-05:00"},
                "end": {"dateTime": "2026-11-05T11:00:00-05:00"},
                "location": "Sala CAUCE",
                "htmlLink": "https://calendar.google.com/x",
            },
            {"id": "g-2", "summary": "Borrado en Google", "status": "cancelled"},
        ],
        "nextSyncToken": "sync-1",
    }

    def fake_api_get(url, headers, params=None):
        assert url.endswith("/calendars/cal-123/events")
        if "syncToken" in (params or {}):
            return FakeResponse({"items": [], "nextSyncToken": "sync-2"})
        return FakeResponse(google_events)

    created = []

    def fake_api_post(url, headers, json_body):
        created.append(json_body)
        # Google echoes the created event back, id included.
        return FakeResponse({"id": "g-local-1", **json_body})

    def fake_refresh(client_id, client_secret, refresh_token):
        assert refresh_token == "refresh-token"
        return "access-ok"

    monkeypatch.setattr(gcal, "api_get", fake_api_get)
    monkeypatch.setattr(gcal, "api_post", fake_api_post)
    monkeypatch.setattr(gcal, "refresh_access", fake_refresh)

    result = gcal.sync(conn, settings)
    assert result.error == ""
    assert result.pulled == 1
    assert result.pushed == 1
    assert result.deleted == 1  # g-2 was cancelled

    # Pulled event became a Google-format row.
    pulled = event_store.get_event(conn, "g-1")
    assert pulled["summary"] == "Reunión remota"
    assert pulled["location"] == "Sala CAUCE"
    assert pulled["start"].strftime("%Y-%m-%d %H:%M") == "2026-11-05 10:00"
    assert pulled["html_link"] == "https://calendar.google.com/x"

    # Pushed local event got Google's id.
    pushed = event_store.get_event(conn, "g-local-1")
    assert pushed["summary"] == "Taller local"
    assert created[0]["summary"] == "Taller local"
    assert created[0]["start"]["dateTime"].startswith("2026-11-10T15:00")

    from makeros.ui import get_ui

    assert get_ui(conn, gcal.KEY_SYNC) == "sync-1"
    conn.close()


def test_gcal_admin_shows_connect(logged_in_client, monkeypatch):
    from makeros.web import gcal

    monkeypatch.setattr(gcal, "is_configured", lambda conn, settings: True)
    page = logged_in_client.get("/admin")
    assert "Conectar con Google" in page.text


def test_gcal_credentials_saved_via_panel(logged_in_client, settings):
    response = logged_in_client.post(
        "/google/credenciales",
        data={"client_id": "abc.apps.googleusercontent.com", "client_secret": "GOCSPX-x"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    from makeros.db import connect
    from makeros.ui import get_ui

    conn = connect(settings.db_path)
    assert get_ui(conn, "gcal:client_id") == "abc.apps.googleusercontent.com"
    assert get_ui(conn, "gcal:client_secret") == "GOCSPX-x"
    conn.close()
    # With credentials in place, the panel shows the OAuth button.
    page = logged_in_client.get("/admin")
    assert "Conectar con Google" in page.text


# ---------- Event categories ----------

def test_default_categories_seeded_and_chips_colored(logged_in_client, settings):
    from makeros.db import connect
    from makeros.web import event_store

    conn = connect(settings.db_path)
    cats = event_store.list_categories(conn)
    conn.close()
    labels = {c["id"] for c in cats}
    assert {"reunion", "taller", "proyecto", "otro"} <= labels

    _add_event(settings, "Taller de robótica", "2026-11-20 15:00", category="taller")
    page = logged_in_client.get("/calendario?m=2026-11")
    assert "Taller de robótica" in page.text
    # Chip tinted with the taller color (logo orange).
    assert "color-mix(in srgb, #f4991f" in page.text
    # Upcoming list shows the category label.
    assert "Taller" in page.text


def test_create_event_with_category(logged_in_client, settings):
    response = logged_in_client.post(
        "/calendario/nuevo",
        data={
            "title": "Junta directiva",
            "start": "2026-12-01 09:00",
            "end": "2026-12-01 10:00",
            "location": "Sala 2",
            "category": "reunion",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from makeros.db import connect
    from makeros.web import event_store

    conn = connect(settings.db_path)
    event = event_store.get_event(
        conn, response.headers["location"].rsplit("/", 1)[-1]
    )
    conn.close()
    assert event["category"] == "reunion"
    detail = logged_in_client.get(response.headers["location"])
    assert "Reunión" in detail.text


def test_category_roundtrips_through_google(settings, monkeypatch):
    from makeros.web import event_store, gcal

    _add_event(settings, "Charla invitada", "2026-12-05 17:00", category="taller")

    import dataclasses

    from makeros.db import connect, init_schema
    from makeros.ui import set_ui

    settings = dataclasses.replace(
        settings, google_client_id="cid", google_client_secret="secret"
    )
    conn = connect(settings.db_path)
    init_schema(conn)
    event_store.ensure_schema(conn)
    set_ui(conn, gcal.KEY_REFRESH, "refresh-token")
    set_ui(conn, gcal.KEY_CALENDAR, "cal-123")

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    pushed_bodies = []

    def fake_api_post(url, headers, json_body):
        pushed_bodies.append(json_body)
        return FakeResponse({"id": "g-push-1", **json_body})

    def fake_api_get(url, headers, params=None):
        return FakeResponse({
            "items": [
                {
                    "id": "g-pull-1",
                    "summary": "Evento desde Google",
                    "start": {"date": "2026-12-24"},
                    "end": {"date": "2026-12-25"},
                    "extendedProperties": {"private": {"category": "reunion"}},
                }
            ],
            "nextSyncToken": "s1",
        })

    monkeypatch.setattr(gcal, "api_get", fake_api_get)
    monkeypatch.setattr(gcal, "api_post", fake_api_post)
    monkeypatch.setattr(gcal, "refresh_access", lambda *a: "access")

    result = gcal.sync(conn, settings)
    assert result.error == ""
    # Push carried the category in Google's private properties.
    assert pushed_bodies[0]["extendedProperties"]["private"]["category"] == "taller"
    # Pull read it back from Google.
    pulled = event_store.get_event(conn, "g-pull-1")
    assert pulled["category"] == "reunion"
    conn.close()


def test_admin_manages_categories(logged_in_client, settings):
    response = logged_in_client.post(
        "/admin/categorias", data={"label": "Social", "color": "#3d8a52"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = logged_in_client.get("/admin")
    assert "Social" in page.text

    from makeros.db import connect
    from makeros.web import event_store

    conn = connect(settings.db_path)
    cats = {c["id"]: c for c in event_store.list_categories(conn)}
    assert "social" in cats
    # Deleting clears it from events too.
    _add_event(settings, "Fiesta fin de año", "2026-12-20 20:00", category="social")
    deleted = logged_in_client.post(
        "/admin/categorias/social/eliminar", follow_redirects=False
    )
    assert deleted.status_code == 303
    row = conn.execute(
        "SELECT category FROM calendar_events WHERE summary = 'Fiesta fin de año'"
    ).fetchone()
    conn.close()
    assert row["category"] == ""

    bad = logged_in_client.post(
        "/admin/categorias", data={"label": "Rara", "color": "#ff00ff"}
    )
    assert bad.status_code == 400


# ---------- Image uploads in blocks ----------

def test_block_image_upload_per_collection_and_page(logged_in_client, settings):
    _write(settings.content_dir / "projects" / "montaje" / "project.md",
           {"name": "Montaje"}, "Cuerpo del proyecto.")
    _reindex(settings)
    response = logged_in_client.post(
        "/projects/montaje/project/imagenes",
        files={"archivo": ("Foto panel.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    url = response.json()["url"]
    assert url.startswith("/media/projects/montaje/project/")
    assert url.endswith(".png")
    # Stored under the page's own folder, as requested.
    stored = settings.content_dir / "_uploads" / "projects" / "montaje" / "project"
    assert any(stored.iterdir())
    # Served back through the login-gated media route.
    served = logged_in_client.get(url)
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")


def test_block_image_upload_rejects_bad_and_viewers(logged_in_client, settings):
    bad = logged_in_client.post(
        "/wiki/inicio/imagenes",
        files={"archivo": ("malo.svg", b"<svg/>", "image/svg+xml")},
    )
    assert bad.status_code == 400

    from makeros import auth
    from makeros.db import connect, init_schema

    conn = connect(settings.db_path)
    init_schema(conn)
    auth.create_user(conn, "lector", "clave123", role="viewer")
    conn.close()
    logged_in_client.post("/logout")
    logged_in_client.post("/login", data={"username": "lector", "password": "clave123"})
    denied = logged_in_client.post(
        "/wiki/inicio/imagenes",
        files={"archivo": ("x.png", _png_bytes(), "image/png")},
    )
    assert denied.status_code == 403


def test_image_block_form_offers_upload_and_size(logged_in_client, settings):
    _write(
        settings.content_dir / "wiki" / "galeria.md",
        {"title": "Galería"},
        "![Foto vieja|mediana](/media/wiki/galeria/foto.png)",
    )
    _reindex(settings)
    form = logged_in_client.get("/wiki/galeria/bloques/0/editar")
    assert form.status_code == 200
    assert "Subir imagen" in form.text
    assert "Usar URL" in form.text
    assert "Tamaño" not in form.text  # size is set by dragging, not a select


def test_image_size_token_renders_as_class():
    from makeros.web.render import render_markdown

    html = render_markdown("![Panel|pequena](/media/x/panel.png)")
    assert 'class="img-pequena"' in html
    assert 'alt="Panel"' in html
    plain = render_markdown("![Panel](/media/x/panel.png)")
    assert "img-pequena" not in plain and 'alt="Panel"' in plain


def test_adding_image_block_opens_editor_with_upload_menu(logged_in_client, settings):
    _write(settings.content_dir / "wiki" / "fotos.md", {"title": "Fotos"}, "Un párrafo.")
    _reindex(settings)
    response = logged_in_client.post(
        "/wiki/fotos/bloques/nuevo",
        data={"tipo": "imagen", "despues": "-1"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    # The editor opens immediately: upload + URL + size tools present.
    assert "Subir imagen" in response.text
    assert "Usar URL" in response.text
    assert "Descripción de la imagen" in response.text  # seed text inside


def test_adding_text_block_renders_in_place(logged_in_client, settings):
    _write(settings.content_dir / "wiki" / "texto.md", {"title": "Texto"}, "Base.")
    _reindex(settings)
    response = logged_in_client.post(
        "/wiki/texto/bloques/nuevo",
        data={"tipo": "parrafo", "despues": "0"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    # Non-image blocks land rendered, not in edit mode.
    assert "bloques/nuevo" in response.text  # block menu present
    assert 'id="block-' in response.text


def test_resize_image_block_endpoint(logged_in_client, settings):
    _write(
        settings.content_dir / "wiki" / "ajuste.md",
        {"title": "Ajuste"},
        "![Panel](/media/wiki/ajuste/panel.png)",
    )
    _reindex(settings)
    response = logged_in_client.post(
        "/wiki/ajuste/bloques/0/tamano", data={"tamano": "mediana"}
    )
    assert response.status_code == 200
    assert 'class="img-mediana"' in response.text

    from makeros import frontmatter

    meta, body = frontmatter.read(settings.content_dir / "wiki" / "ajuste.md")
    assert "|mediana" in body

    # Resizing keeps an existing token instead of stacking them.
    response = logged_in_client.post(
        "/wiki/ajuste/bloques/0/tamano", data={"tamano": "pequena"}
    )
    assert response.status_code == 200
    meta, body = frontmatter.read(settings.content_dir / "wiki" / "ajuste.md")
    assert "pequena" in body and "mediana" not in body

    # Freeform tiny sizes: any integer 5-100 sticks.
    tiny = logged_in_client.post(
        "/wiki/ajuste/bloques/0/tamano", data={"tamano": "12"}
    )
    assert tiny.status_code == 200
    assert "width:12%" in tiny.text
    from makeros import frontmatter as fm

    _, body = fm.read(settings.content_dir / "wiki" / "ajuste.md")
    assert "|12" in body

    bad = logged_in_client.post(
        "/wiki/ajuste/bloques/0/tamano", data={"tamano": "enorme"}
    )
    assert bad.status_code == 400
    too_big = logged_in_client.post(
        "/wiki/ajuste/bloques/0/tamano", data={"tamano": "250"}
    )
    assert too_big.status_code == 400


# ---------- Wiki vault: folders, navigation, moves, graph ----------

def test_vault_folder_creation_and_navigation(logged_in_client, settings):
    created = logged_in_client.post(
        "/wiki/carpeta", data={"ruta": "guias/impresion"}, follow_redirects=False
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/wiki/guias/impresion"
    assert (settings.content_dir / "wiki" / "guias" / "impresion").is_dir()

    folder = logged_in_client.get("/wiki/guias/impresion", follow_redirects=False)
    # A folder URL redirects to the scoped card view.
    assert folder.status_code == 303
    assert folder.headers["location"] == "/wiki?carpeta=guias/impresion"
    scoped = logged_in_client.get(folder.headers["location"])
    assert scoped.status_code == 200
    assert "vault-breadcrumb" in scoped.text
    assert 'href="/wiki?carpeta=guias"' in scoped.text

    bad = logged_in_client.post("/wiki/carpeta", data={"ruta": "../mal"})
    assert bad.status_code == 400


def test_create_wiki_page_inside_folder(logged_in_client, settings):
    response = logged_in_client.post(
        "/wiki/nuevo",
        data={"title": "Calibrar la Prusa", "ruta": "guias/impresion",
              "body": "Pasos de calibración."},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/wiki/guias/impresion/calibrar-la-prusa"
    assert (settings.content_dir / "wiki" / "guias" / "impresion"
            / "calibrar-la-prusa.md").is_file()

    # The card view shows the new page; the tree nests it in its folder.
    wiki = logged_in_client.get("/wiki")
    assert "Calibrar la Prusa" in wiki.text
    tree = logged_in_client.get("/wiki?vista=arbol")
    assert "vault-folder" in tree.text


def test_move_page_rewrites_wikilinks(logged_in_client, settings):
    _write(settings.content_dir / "wiki" / "origen.md",
           {"title": "Origen"}, "Contenido.")
    _write(settings.content_dir / "wiki" / "enlazador.md",
           {"title": "Enlazador"}, "Mira [[origen]] y [[origen|la página]].")
    _reindex(settings)

    moved = logged_in_client.post(
        "/wiki/origen/mover",
        data={"nueva_ruta": "guias/movida"},
        follow_redirects=False,
    )
    assert moved.status_code == 303
    assert moved.headers["location"] == "/wiki/guias/movida"
    assert (settings.content_dir / "wiki" / "guias" / "movida.md").is_file()
    assert not (settings.content_dir / "wiki" / "origen.md").exists()

    from makeros import frontmatter

    _, body = frontmatter.read(settings.content_dir / "wiki" / "enlazador.md")
    assert "[[guias/movida]]" in body
    assert "[[guias/movida|la página]]" in body
    assert "[[origen]]" not in body

    # Old URL is gone; new one renders with rewritten links working.
    assert logged_in_client.get("/wiki/origen").status_code == 404
    fresh = logged_in_client.get("/wiki/enlazador")
    assert 'href="/wiki/guias/movida"' in fresh.text


def test_wiki_graph_shows_nodes_and_edges(logged_in_client, settings):
    _write(settings.content_dir / "wiki" / "nodo-a.md",
           {"title": "Nodo A"}, "Sobre [[nodo-b]] y [[wiki/nodo-c]].")
    _write(settings.content_dir / "wiki" / "nodo-b.md",
           {"title": "Nodo B"}, "Vuelve a [[nodo-a]].")
    _reindex(settings)

    page = logged_in_client.get("/wiki/grafos")
    assert page.status_code == 200
    assert "graph-canvas" in page.text
    assert '"Nodo A"' in page.text
    assert '"source": "wiki/nodo-a"' in page.text
    assert '"target": "wiki/nodo-b"' in page.text


def test_assistant_page_shows_offline_state(logged_in_client):
    page = logged_in_client.get("/asistente")
    assert page.status_code == 200
    assert "Modelo sin configurar" in page.text
    assert "/asistente/preguntar" in page.text


def test_assistant_answer_with_local_model(logged_in_client, settings, monkeypatch):
    _write(settings.content_dir / "wiki" / "prusa.md",
           {"title": "Prusa"}, "La Prusa se calibra con el paso a paso.")
    _reindex(settings)

    from makeros.web import llm

    monkeypatch.setattr(llm, "chat", lambda conn, messages: "La [[prusa]] se calibra así.")
    response = logged_in_client.post(
        "/asistente/preguntar", data={"pregunta": "cómo calibrar la prusa"}
    )
    assert response.status_code == 200
    assert "La <a href=\"/wiki/prusa\"" in response.text
    assert 'href="/wiki/prusa"' in response.text  # source chip
    assert "Guardar como página" in response.text


def test_assistant_offline_when_model_unreachable(logged_in_client, settings, monkeypatch):
    from makeros.web import llm

    monkeypatch.setattr(llm, "chat", lambda conn, messages: None)
    response = logged_in_client.post(
        "/asistente/preguntar", data={"pregunta": "qué es MakerOS"}
    )
    assert response.status_code == 200
    assert "modelo no está disponible" in response.text


def test_assistant_save_creates_wiki_page(logged_in_client, settings):
    saved = logged_in_client.post(
        "/asistente/guardar",
        data={"respuesta": "Respuesta del asistente.", "ruta": "guias/resumen"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"] == "/wiki/guias/resumen"
    file = settings.content_dir / "wiki" / "guias" / "resumen.md"
    assert file.is_file()
    assert "Respuesta del asistente." in file.read_text(encoding="utf-8")

    bad = logged_in_client.post(
        "/asistente/guardar", data={"respuesta": "x", "ruta": "../mal"}
    )
    assert bad.status_code == 400


def test_move_folder_moves_pages_and_rewrites_links(logged_in_client, settings):
    _write(settings.content_dir / "wiki" / "viejo" / "pagina.md",
           {"title": "Página"}, "Contenido.")
    _write(settings.content_dir / "wiki" / "enlazador.md",
           {"title": "Enlazador"}, "Mira [[viejo/pagina]].")
    _reindex(settings)

    moved = logged_in_client.post(
        "/wiki/carpeta/viejo/mover", data={"destino": "archivo"},
        follow_redirects=False,
    )
    assert moved.status_code == 303
    assert moved.headers["location"] == "/wiki/archivo/viejo"
    assert (settings.content_dir / "wiki" / "archivo" / "viejo" / "pagina.md").is_file()
    assert not (settings.content_dir / "wiki" / "viejo").exists()

    from makeros import frontmatter

    _, body = frontmatter.read(settings.content_dir / "wiki" / "enlazador.md")
    assert "[[archivo/viejo/pagina]]" in body

    # A folder cannot be moved into itself.
    denied = logged_in_client.post(
        "/wiki/carpeta/archivo/mover", data={"destino": "archivo/viejo"}
    )
    assert denied.status_code == 400


def test_split_view_renders_panes(logged_in_client: TestClient):
    response = logged_in_client.get("/dividir?p=wiki/inicio&p=wiki/grafos")
    assert response.status_code == 200
    assert 'src="/wiki/inicio?panel=1"' in response.text
    assert 'src="/wiki/grafos?panel=1"' in response.text
    # No panes: the wiki navigator alone.
    default = logged_in_client.get("/dividir")
    assert 'src="/wiki?panel=1"' in default.text


def test_panel_mode_hides_sidebar(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki/inicio?panel=1")
    assert response.status_code == 200
    assert 'class="sidebar"' not in response.text
    assert "content-panel" in response.text
    # Normal render keeps the sidebar.
    normal = logged_in_client.get("/wiki/inicio")
    assert 'class="sidebar"' in normal.text


def test_sidebar_hides_people_and_shows_assistant(logged_in_client: TestClient):
    response = logged_in_client.get("/")
    assert '<a class="nav-item" href="/people">' not in response.text
    assert 'href="/asistente"' in response.text


def test_assignment_forms_list_people(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "people" / "ana.md", {"title": "Ana"}, "Skills.")
    _reindex(settings)
    tasks = logged_in_client.get("/tasks/nuevo")
    assert '<option value="ana">Ana</option>' in tasks.text
    project = logged_in_client.get("/projects/nuevo")
    assert '<option value="ana">Ana</option>' in project.text
    event_form = logged_in_client.get("/calendario/nuevo")
    assert '<option value="ana">Ana</option>' in event_form.text


def test_event_created_with_assigned_people(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "people" / "ana.md", {"title": "Ana"}, "Skills.")
    _reindex(settings)
    response = logged_in_client.post(
        "/calendario/nuevo",
        data={"title": "Reunión de planeación", "start": "2026-11-05 10:00",
              "people": "ana", "category": "reunion"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    from makeros.db import connect

    conn = connect(settings.db_path)
    row = conn.execute(
        "SELECT people FROM calendar_events ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert row["people"] == "ana"
    conn.close()

    # The event page shows the person as a chip.
    event_url = response.headers["location"]
    page = logged_in_client.get(event_url)
    assert 'href="/people/ana"' in page.text


def test_greeting_rotates_by_date():
    from datetime import date

    from makeros.web.greetings import GREETINGS, greeting_for

    assert "Ana" in greeting_for("Ana", date(2026, 10, 26))
    assert greeting_for("Ana", date(2026, 10, 26)) == greeting_for("Ana", date(2026, 10, 26))
    assert len(GREETINGS) == 30


def test_kanban_is_default_for_tasks(logged_in_client: TestClient, settings):
    _seed_tasks(settings)
    response = logged_in_client.get("/tasks")
    assert 'class="kanban"' in response.text
    # Cards carry the quick-edit modal trigger.
    assert "kanban-edit" in response.text
    assert "/editar?fragmento=1" in response.text


def test_new_form_fragment_renders_for_modal(logged_in_client: TestClient):
    response = logged_in_client.get("/tasks/nuevo?fragmento=1")
    assert response.status_code == 200
    assert "<!doctype" not in response.text
    assert 'hx-post="/tasks/nuevo"' in response.text
    assert 'data-modal-title' in response.text


def test_modal_create_task_via_htmx(logged_in_client: TestClient, settings):
    response = logged_in_client.post(
        "/tasks/nuevo",
        data={"title": "Tarea desde modal", "status": "todo", "priority": "high"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "makerosCloseModal()" in response.text
    assert (settings.content_dir / "tasks" / "tarea-desde-modal.md").is_file()


def test_modal_create_error_rerenders_fragment(logged_in_client: TestClient):
    response = logged_in_client.post(
        "/tasks/nuevo",
        data={"title": "Tarea mala", "due": "no-es-fecha"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Fecha inválida" in response.text
    assert 'hx-post="/tasks/nuevo"' in response.text


def test_task_edit_modal_roundtrip(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "tasks" / "editar-me.md",
           {"title": "Editar me", "status": "todo", "assignee": "", "priority": ""},
           "Contexto.")
    _reindex(settings)

    form = logged_in_client.get("/tasks/editar-me/editar?fragmento=1")
    assert form.status_code == 200
    assert 'value="Editar me"' in form.text
    assert 'hx-post="/tasks/editar-me/editar"' in form.text

    saved = logged_in_client.post(
        "/tasks/editar-me/editar",
        data={"title": "Editar me", "status": "done", "priority": "high",
              "assignee": "", "project": "", "due": ""},
        headers={"HX-Request": "true"},
    )
    assert saved.status_code == 200
    assert "makerosCloseModal()" in saved.text

    from makeros import frontmatter

    meta, _body = frontmatter.read(settings.content_dir / "tasks" / "editar-me.md")
    assert meta["status"] == "done"
    assert meta["priority"] == "high"

    bad = logged_in_client.post(
        "/tasks/editar-me/editar",
        data={"title": "X", "status": "estado-falso", "priority": "", "assignee": "",
              "project": "", "due": ""},
        headers={"HX-Request": "true"},
    )
    assert "Estado no válido" in bad.text


def test_admin_user_modal_flow(logged_in_client: TestClient):
    form = logged_in_client.get("/admin/usuarios/nuevo?fragmento=1")
    assert form.status_code == 200
    assert 'hx-post="/admin/usuarios"' in form.text

    created = logged_in_client.post(
        "/admin/usuarios",
        data={"username": "nuevo", "password": "clavebuena8", "role": "member"},
        headers={"HX-Request": "true"},
    )
    assert created.status_code == 200
    assert "makerosCloseModal()" in created.text

    duplicate = logged_in_client.post(
        "/admin/usuarios",
        data={"username": "nuevo", "password": "clavebuena8"},
        headers={"HX-Request": "true"},
    )
    assert "ese usuario ya existe" in duplicate.text


def test_sidebar_hides_exhibits(logged_in_client: TestClient):
    response = logged_in_client.get("/")
    assert '<a class="nav-item" href="/exhibits">' not in response.text




def test_private_notes_vault(logged_in_client: TestClient, settings):
    from makeros import frontmatter

    home = logged_in_client.get("/notas")
    assert home.status_code == 200
    assert "Mis notas" in home.text

    # Create a note with tags inside a folder, via the modal endpoint.
    created = logged_in_client.post(
        "/notas/nuevo",
        data={"title": "Idea de sensor", "carpeta": "ideas", "tags": "pcb, sensor"},
        headers={"HX-Request": "true"},
    )
    assert created.status_code == 200
    file = settings.private_dir / "jacob" / "ideas" / "idea-de-sensor.md"
    assert file.is_file()

    # The folder shows on the vault home; the note card carries its tags.
    home = logged_in_client.get("/notas")
    assert 'href="/notas/ideas"' in home.text
    folder_view = logged_in_client.get("/notas/ideas")
    assert "Idea de sensor" in folder_view.text

    # Tag filter chips come from the notes' frontmatter.
    assert 'data-tag="pcb"' in folder_view.text

    # The note itself opens with the block editor.
    note = logged_in_client.get("/notas/ideas/idea-de-sensor")
    assert note.status_code == 200
    assert 'data-edit-url="/notas/ideas/idea-de-sensor/bloques/' in note.text

    added = logged_in_client.post(
        "/notas/ideas/idea-de-sensor/bloques/nuevo",
        data={"tipo": "parrafo", "despues": "-1"},
        headers={"HX-Request": "true"},
    )
    assert added.status_code == 200
    _meta, body = frontmatter.read(file)
    assert len(body) > 20

    # Traversal outside the private root is rejected.
    bad = logged_in_client.get("/notas/../etc")
    assert bad.status_code in (400, 404)

    # Private notes never leak into the shared search index.
    frontmatter.write(file, {"title": "Idea de sensor"}, "secreto-confidencial-xyz")
    search = logged_in_client.get("/search?q=secreto-confidencial-xyz")
    assert "0 resultado(s)" in search.text
    assert "result-snippet" not in search.text
def test_explorer_shows_all_content(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "tasks" / "explorar-me.md", {"title": "Explorar me"}, "Tarea.")
    _write(settings.content_dir / "wiki" / "guias" / "profundas" / "nota.md",
           {"title": "Nota profunda"}, "Anidada.")
    _reindex(settings)

    page = logged_in_client.get("/explorador")
    assert page.status_code == 200
    assert 'href="/tasks/explorar-me"' in page.text
    assert "Nota profunda" in page.text
    # Folders render as tree nodes.
    assert "guias" in page.text


def test_home_has_avisos_board_and_week(logged_in_client: TestClient, settings):
    response = logged_in_client.get("/")
    assert response.status_code == 200
    assert "Avisos" in response.text
    assert "Esta semana" in response.text
    assert (settings.content_dir / "avisos" / "tablero.md").is_file()
    assert 'href="/avisos/tablero"' in response.text


def test_pin_page_shows_on_home(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "tasks" / "fijame.md",
           {"title": "Fijame", "status": "todo"}, "Tarea importante.")
    _reindex(settings)

    pinned = logged_in_client.post("/tasks/fijame/fijar", follow_redirects=False)
    assert pinned.status_code == 303
    from makeros import frontmatter

    meta, _body = frontmatter.read(settings.content_dir / "tasks" / "fijame.md")
    assert meta["pinned"] is True

    home = logged_in_client.get("/")
    assert 'href="/tasks/fijame"' in home.text
    assert "Fijado" in home.text

    unpinned = logged_in_client.post("/tasks/fijame/fijar", follow_redirects=False)
    assert unpinned.status_code == 303
    home = logged_in_client.get("/")
    assert "Fijado" not in home.text


def test_week_events_on_home(logged_in_client: TestClient, settings):
    from datetime import date

    today = date.today().isoformat()
    _add_event(settings, "Taller de hoy", f"{today} 15:00")
    response = logged_in_client.get("/")
    assert "Taller de hoy" in response.text
    assert 'href="/calendario' in response.text


def test_sidebar_has_notes_explorer_avisos(logged_in_client: TestClient):
    response = logged_in_client.get("/")
    assert 'href="/notas"' in response.text
    assert 'href="/explorador"' in response.text
    assert "Editar tablero" in response.text  # avisos lives on home now


def test_blocks_are_click_to_edit(logged_in_client: TestClient):
    """Obsidian-style editing: rendered blocks carry their edit URL."""
    response = logged_in_client.get("/wiki/inicio")
    assert 'data-edit-url="/wiki/inicio/bloques/' in response.text


def test_research_folders_and_tag_filter(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "research" / "impresion" / "klipper.md",
           {"title": "Klipper", "tags": ["firmware"]}, "Repo de firmware.")
    _write(settings.content_dir / "research" / "marlin.md", {"title": "Marlin"}, "Repo.")
    _reindex(settings)

    page = logged_in_client.get("/research")
    assert 'href="/research?carpeta=impresion"' in page.text
    assert 'data-tag="firmware"' in page.text

    scoped = logged_in_client.get("/research?carpeta=impresion")
    assert "Klipper" in scoped.text
    assert "Marlin" not in scoped.text

    # Notes born inside a folder via the creation modal.
    created = logged_in_client.post(
        "/research/nuevo",
        data={"title": "Voron Docs", "ruta": "impresion", "body": ""},
        headers={"HX-Request": "true"},
    )
    assert created.status_code == 200
    assert (settings.content_dir / "research" / "impresion" / "voron-docs.md").is_file()


def test_avisos_board_live_polling(logged_in_client: TestClient):
    """The home board refreshes itself via polling (no page reload)."""
    home = logged_in_client.get("/")
    assert 'hx-get="/avisos/tablero/contenido"' in home.text
    assert "every 15s" in home.text
    endpoint = logged_in_client.get("/avisos/tablero/contenido")
    assert endpoint.status_code == 200
    assert "<!doctype" not in endpoint.text  # fragment, not a page


def test_explorer_views_and_address_bar(logged_in_client: TestClient, settings):
    _write(settings.content_dir / "research" / "impresion" / "vorn.md",
           {"title": "Vorn Docs"}, "Repo.")
    _reindex(settings)

    root = logged_in_client.get("/explorador")
    assert root.status_code == 200
    assert "explorer-toolbar" in root.text
    assert 'href="/explorador?carpeta=wiki"' in root.text
    # Tree pane always present in card/list views.
    assert "explorer-tree-pane" in root.text

    cards = logged_in_client.get("/explorador?carpeta=research&vista=tarjetas")
    assert 'href="/explorador?carpeta=research/impresion&vista=tarjetas"' in cards.text

    inside = logged_in_client.get("/explorador?carpeta=research/impresion&vista=lista")
    assert "Vorn Docs" in inside.text
    assert 'href="/research/impresion/vorn"' in inside.text

    # Unknown route falls back to the root instead of a 404.
    lost = logged_in_client.get("/explorador?carpeta=no/existe")
    assert lost.status_code == 200
    assert "explorer-toolbar" in lost.text
