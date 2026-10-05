"""Shared fixtures: settings, DB, content tree, app + TestClient."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from makeros import auth
from makeros.config import Settings
from makeros.db import connect, init_schema
from makeros.frontmatter import write
from makeros.main import create_app


@pytest.fixture
def content_dir(tmp_path: Path) -> Path:
    wiki = tmp_path / "content" / "wiki"
    wiki.mkdir(parents=True)
    write(
        wiki / "inicio.md",
        {"title": "Bienvenido a MakerOS", "tags": ["guia"]},
        "# Bienvenido\n\nEste es el inicio. Ver [[guia-del-sistema]].",
    )
    write(
        wiki / "guia-del-sistema.md",
        {"title": "Guía del sistema"},
        "# Guía\n\nCómo funciona el laboratorio.",
    )
    return wiki.parent


@pytest.fixture
def settings(tmp_path: Path, content_dir: Path) -> Settings:
    return Settings(
        content_dir=content_dir,
        private_dir=tmp_path / "private",
        templates_dir=tmp_path / "templates",
        db_path=tmp_path / "data" / "makeros.db",
        secret_key="test-secret",
    )


@pytest.fixture
def conn(settings: Settings):
    conn = connect(settings.db_path)
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def user(conn):
    return auth.create_user(conn, "jacob", "secreto123", role="admin", display_name="Jacob")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def logged_in_client(client: TestClient, settings: Settings) -> TestClient:
    conn = connect(settings.db_path)
    init_schema(conn)
    try:
        auth.create_user(conn, "jacob", "secreto123", role="admin", display_name="Jacob")
    finally:
        conn.close()
    response = client.post(
        "/login", data={"username": "jacob", "password": "secreto123"}, follow_redirects=False
    )
    assert response.status_code == 303
    return client
