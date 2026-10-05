"""Frontmatter module: parse, dump, atomic write round-trips."""

from makeros.frontmatter import (
    FrontmatterError,
    append_body,
    dump,
    parse,
    read,
    update_meta,
    write,
)


def test_parse_with_frontmatter():
    meta, body = parse("---\ntitle: Hola\ntags: [a, b]\n---\n\nCuerpo\n")
    assert meta["title"] == "Hola"
    assert meta["tags"] == ["a", "b"]
    assert body.strip() == "Cuerpo"


def test_parse_without_frontmatter():
    meta, body = parse("Solo texto.\n")
    assert meta == {}
    assert body == "Solo texto.\n"


def test_parse_invalid_yaml_raises():
    try:
        parse("---\ntitle: [unclosed\n---\ncuerpo")
        raise AssertionError("expected FrontmatterError")
    except FrontmatterError:
        pass


def test_dump_roundtrip_is_stable():
    text = dump({"title": "X", "tags": ["a", "b"]}, "Cuerpo\n")
    meta, body = parse(text)
    assert meta == {"title": "X", "tags": ["a", "b"]}
    assert dump(meta, body) == text


def test_unicode_roundtrip(tmp_path):
    path = tmp_path / "café.md"
    write(path, {"title": "Diseño — prueba", "tags": ["ñ"]}, "Contenido con acentos: áéíóú\n")
    meta, body = read(path)
    assert meta["title"] == "Diseño — prueba"
    assert "acentos" in body


def test_write_is_atomic_no_tmp_left(tmp_path):
    path = tmp_path / "page.md"
    write(path, {"title": "T"}, "body\n")
    assert path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_update_meta_preserves_body(tmp_path):
    path = tmp_path / "page.md"
    write(path, {"title": "T", "status": "todo"}, " cuerpo intacto\n")
    update_meta(path, {"status": "done"})
    meta, body = read(path)
    assert meta["title"] == "T"
    assert meta["status"] == "done"
    assert body.strip() == "cuerpo intacto"


def test_append_body_appends(tmp_path):
    path = tmp_path / "log.md"
    write(path, {"title": "T"}, "| fecha | quien |\n|---|---|")
    append_body(path, "\n| 2026-10-05 | jacob |")
    _meta, body = read(path)
    assert body.endswith("| jacob |")
