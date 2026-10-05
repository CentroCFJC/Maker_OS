"""Web layer: auth flow, wiki render, search, dashboard."""

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
