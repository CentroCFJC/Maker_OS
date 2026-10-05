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
