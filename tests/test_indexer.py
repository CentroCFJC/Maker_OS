"""Indexer: upserts, full reindex, deletes, FTS5 search."""

from makeros.frontmatter import write
from makeros.indexer import (
    get_document,
    index_file,
    list_collection,
    reindex_all,
    remove_document,
    search_documents,
)


def test_index_file_and_search(conn, content_dir):
    index_file(conn, content_dir, content_dir / "wiki" / "inicio.md")
    results = search_documents(conn, "bienvenido")
    assert [r["path"] for r in results] == ["wiki/inicio"]


def test_reindex_all_counts_and_forgots_deleted(conn, content_dir):
    assert reindex_all(conn, content_dir) == 2
    assert len(list_collection(conn, "wiki")) == 2

    (content_dir / "wiki" / "guia-del-sistema.md").unlink()
    assert reindex_all(conn, content_dir) == 1
    assert get_document(conn, "wiki/guia-del-sistema") is None


def test_reindex_updates_changed_title(conn, content_dir):
    reindex_all(conn, content_dir)
    write(
        content_dir / "wiki" / "inicio.md",
        {"title": "Título nuevo"},
        "contenido actualizado con palabra única zanzibar",
    )
    reindex_all(conn, content_dir)
    doc = get_document(conn, "wiki/inicio")
    assert doc["title"] == "Título nuevo"
    assert search_documents(conn, "zanzibar")


def test_remove_document(conn, content_dir):
    index_file(conn, content_dir, content_dir / "wiki" / "inicio.md")
    remove_document(conn, "wiki/inicio")
    assert search_documents(conn, "bienvenido") == []
    assert get_document(conn, "wiki/inicio") is None


def test_search_with_bad_fts_syntax_falls_back_to_phrase(conn, content_dir):
    reindex_all(conn, content_dir)
    # Raw parentheses would be a syntax error in MATCH; fallback must not raise.
    assert search_documents(conn, "(bienvenido") is not None


def test_reindex_ignores_tmp_files(conn, content_dir, tmp_path):
    # Simulate an in-flight atomic write: a .md.tmp file must never be indexed.
    (content_dir / "wiki" / "draft.md.tmp").write_text("---\ntitle: X\n---\nbody")
    assert reindex_all(conn, content_dir) == 2
    assert get_document(conn, "wiki/draft") is None
