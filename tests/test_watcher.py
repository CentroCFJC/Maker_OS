"""Watcher integration: on-disk edits reach the index without a restart."""

import time

from fastapi.testclient import TestClient

from makeros.db import connect
from makeros.frontmatter import write


def _search(client: TestClient, query: str) -> int:
    response = client.get("/search", params={"q": query})
    assert response.status_code == 200
    return response.text.count('class="item-title"')


def _wait_for(condition, timeout: float = 15.0, interval: float = 0.25) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise AssertionError("condition not met before timeout")


def test_watcher_indexes_new_and_deleted_files(settings, content_dir):
    from makeros.main import create_app

    app = create_app(settings)
    with TestClient(app) as client:
        conn = connect(settings.db_path)
        from makeros.auth import create_user

        create_user(conn, "jacob", "secreto123", role="admin")
        conn.close()
        client.post("/login", data={"username": "jacob", "password": "secreto123"})

        # Baseline: the fixture pages are indexed at startup.
        assert _search(client, "zanzibar") == 0

        # A file written on disk (git pull, vim, script) must appear in
        # the search index without any restart.
        write(
            content_dir / "wiki" / "nueva-pagina.md",
            {"title": "Página del watcher"},
            "contenido único zanzibar",
        )
        _wait_for(lambda: _search(client, "zanzibar") == 1)

        # Deleting the file must drop it from the index.
        (content_dir / "wiki" / "nueva-pagina.md").unlink()
        _wait_for(lambda: _search(client, "zanzibar") == 0)


def test_watcher_survives_bad_file(settings, content_dir, monkeypatch):
    """A crash-prone watch loop must not kill the watcher thread."""
    from makeros import indexer
    from makeros.main import create_app

    original = indexer.index_file
    calls = {"n": 0}

    def flaky(conn, content_dir, file_path):
        calls["n"] += 1
        if calls["n"] == 1:
            # First indexing attempt explodes; the loop must survive it.
            raise indexer.FrontmatterError("boom")
        return original(conn, content_dir, file_path)

    monkeypatch.setattr(indexer, "index_file", flaky)
    app = create_app(settings)
    with TestClient(app) as client:
        conn = connect(settings.db_path)
        from makeros.auth import create_user

        create_user(conn, "jacob", "secreto123", role="admin")
        conn.close()
        client.post("/login", data={"username": "jacob", "password": "secreto123"})

        write(
            content_dir / "wiki" / "problematica.md",
            {"title": "Archivo problemático"},
            "palabra buscable quux",
        )
        # The write fires at least two events (create + any settle);
        # after the simulated crash the loop must still index the file.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if _search(client, "quux") == 1:
                break
            time.sleep(0.25)
        assert _search(client, "quux") == 1
        assert calls["n"] >= 2
