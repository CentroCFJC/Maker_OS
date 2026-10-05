"""Block model: split/join Markdown, fence handling, kinds."""

from makeros.web.blocks import infer_kind, join_blocks, split_blocks


def test_split_simple_body():
    body = "# Título\n\nPárrafo uno.\n\n- a\n- b\n"
    blocks = split_blocks(body)
    assert [b.kind for b in blocks] == ["titulo", "parrafo", "lista"]
    assert blocks[1].text == "Párrafo uno."


def test_split_keeps_fenced_code_whole():
    body = "antes\n\n```python\nx = 1\n\ny = 2\n```\n\ndespués\n"
    blocks = split_blocks(body)
    kinds = [b.kind for b in blocks]
    assert kinds == ["parrafo", "codigo", "parrafo"]
    assert "x = 1" in blocks[1].text and "y = 2" in blocks[1].text
    assert blocks[1].text.startswith("```")


def test_split_table_and_quote_and_checklist():
    body = "| a | b |\n|---|---|\n\n> cita\n\n- [ ] tarea\n"
    assert [b.kind for b in split_blocks(body)] == ["tabla", "cita", "checklist"]


def test_roundtrip_join():
    body = "# T\n\ntexto\n\n```py\na=1\n```\n"
    blocks = split_blocks(body)
    rejoined = join_blocks([b.text for b in blocks])
    assert split_blocks(rejoined) == blocks


def test_empty_body():
    assert split_blocks("") == []
    assert split_blocks("\n\n\n") == []
    assert join_blocks([]) == ""


def test_infer_kind_fallbacks():
    assert infer_kind("Hola mundo") == "parrafo"
    assert infer_kind("---") == "separador"
