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
    assert "Buenas, Jacob" in response.text
    assert "Cambios recientes" in response.text


def test_logout(logged_in_client: TestClient):
    response = logged_in_client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert logged_in_client.get("/", follow_redirects=False).status_code == 303


def test_wiki_index_lists_pages(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki")
    assert response.status_code == 200
    assert "Bienvenido a MakerOS" in response.text
    assert "Guía del sistema" in response.text


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
    default = logged_in_client.get("/wiki")
    assert "item-list" in default.text
    assert "card-grid" not in default.text

    grid = logged_in_client.get("/wiki?vista=tarjetas")
    assert "card-grid" in grid.text
    assert "vista=tarjetas" in grid.headers.get("set-cookie", "")

    # The choice is remembered in the cookie.
    remembered = logged_in_client.get("/wiki")
    assert "card-grid" in remembered.text

    back = logged_in_client.get("/wiki?vista=lista")
    assert "item-list" in back.text
    assert "card-grid" not in back.text


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


def test_calendar_view_shows_events_and_projects(logged_in_client: TestClient, settings):
    from datetime import date, timedelta

    day = date.today() + timedelta(days=3)
    nxt = day + timedelta(days=1)
    _write(
        settings.content_dir / "calendario" / "taller.md",
        {"title": "Taller de impresión", "start": f"{day.isoformat()} 16:00",
         "end": f"{day.isoformat()} 18:00", "location": "Sala CAUCE"},
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
    assert "calendario.ics" in response.text  # feed URL on the connect panel


def test_calendar_requires_login(client: TestClient):
    response = client.get("/calendario", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_ics_feed(logged_in_client: TestClient, settings):
    from datetime import date, timedelta

    day = date.today() + timedelta(days=2)
    _write(
        settings.content_dir / "calendario" / "cita.md",
        {"title": "Cita con pausa, coma", "start": f"{day.isoformat()} 10:00",
         "end": f"{day.isoformat()} 11:00", "location": "Sala"},
    )
    _write(
        settings.content_dir / "calendario" / "dia-completo.md",
        {"title": "Jornada de puertas abiertas", "start": day.isoformat(),
         "end": day.isoformat()},
    )
    _reindex(settings)

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
    assert response.headers["location"] == "/calendario/reunion-de-planificacion"

    from makeros import frontmatter

    meta, body = frontmatter.read(
        settings.content_dir / "calendario" / "reunion-de-planificacion.md"
    )
    assert meta["start"] == "2026-11-04 15:00"
    assert meta["end"] == "2026-11-04 16:30"
    assert meta["location"] == "Sala CAUCE"


def test_create_event_defaults_end_to_start(logged_in_client: TestClient, settings):
    logged_in_client.post("/calendario/nuevo", data={"title": "Puntual", "start": "2026-11-10"})
    from makeros import frontmatter

    meta, _ = frontmatter.read(settings.content_dir / "calendario" / "puntual.md")
    assert meta["start"] == "2026-11-10"
    assert meta["end"] == "2026-11-10"


def test_create_event_rejects_bad_date(logged_in_client: TestClient):
    response = logged_in_client.post(
        "/calendario/nuevo", data={"title": "Roto", "start": "mañana"}
    )
    assert response.status_code == 400


def test_new_event_form_prefills_date(logged_in_client: TestClient):
    response = logged_in_client.get("/calendario/nuevo?fecha=2026-12-24")
    assert response.status_code == 200
    assert 'value="2026-12-24"' in response.text


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
    assert "Icono de la sección" in page.text

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
    assert "Icono de la sección" not in picker.text


def test_card_size_slider_in_grid_view(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki?vista=tarjetas")
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
    assert "Buenas, Jacob" in response.text
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
    _write(
        settings.content_dir / "calendario" / "reunion-hoy.md",
        {"title": "Reunión de hoy", "start": f"{date.today().isoformat()} 15:00",
         "end": f"{date.today().isoformat()} 16:00"},
    )
    _reindex(settings)
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
    logged_in_client.post(
        "/wiki/inicio/banner",
        data={"url": "https://example.com/x.png"},
        follow_redirects=False,
    )
    cards = logged_in_client.get("/wiki?vista=tarjetas")
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


def test_card_slider_is_stepped(logged_in_client: TestClient):
    response = logged_in_client.get("/wiki?vista=tarjetas")
    assert 'min="1" max="4" step="1"' in response.text
    assert 'data-step="2"' in response.text   # server default: Normal
    assert "card-size-label" in response.text
    # Elements are gated by step classes in CSS, not stripped from HTML.
    assert "step-4" in response.text or "step-2" in response.text
