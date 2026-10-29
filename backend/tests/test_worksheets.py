"""Phase 8: literacy worksheets drawn by code, with pictures from the shared icon library."""

import io
import re

import pytest
from pydantic import TypeAdapter
from pypdf import PdfReader

from app.content import Block
from app.render import render_pdf
from app.worksheets import render_worksheet, search_grid
from tests.test_diagrams import C
from tests.test_render import tome

block = TypeAdapter(Block).validate_python
EVERY = [
    {"id": "c", "type": "syllable_chart", "letter": "m", "instruction": "Nombra cada dibujo.", "words": [
        {"word": "mamá", "syllable": "ma"}, {"word": "mesa", "syllable": "me"}, {"word": "mimo", "syllable": "mi"},
        {"word": "moto", "syllable": "mo"}, {"word": "mula", "syllable": "mu"}]},
    {"id": "w", "type": "picture_words", "mode": "write", "items": [{"word": "mano"}, {"word": "mono"}]},
    {"id": "p", "type": "picture_words", "mode": "complete", "items": [
        {"word": "mesa", "syllable": "me"}, {"word": "moto", "syllable": "to"}]},
    {"id": "o", "type": "picture_words", "mode": "circle", "items": [
        {"word": "mapa", "syllable": "ma"}, {"word": "pomo", "syllable": "po"}]},
    {"id": "j", "type": "picture_words", "mode": "match", "items": [
        {"word": "mapa", "syllable": "ma"}, {"word": "pomo", "syllable": "po"}, {"word": "pipa", "syllable": "pi"}]},
    {"id": "k", "type": "syllable_cards", "syllables": ["ma", "me", "mi", "mo", "mu", "pa"]},
    {"id": "r", "type": "reading", "sentences": [{"text": "Mi mamá me ama.", "picture": "mamá"},
                                                 {"text": "Memo mima a la mula."}]},
    {"id": "d", "type": "dictation", "words": ["mamá", "mapa", "puma"], "lines": 5},
    {"id": "f", "type": "fill_sentences", "items": [{"text": "Mi ___ es azul.", "answer": "moto"}]},
    {"id": "s", "type": "word_search", "words": ["mamá", "mapa", "puma"], "size": 7},
    {"id": "x", "type": "classify", "columns": ["ma", "pi"], "words": ["mamá", "pipa", "malo", "pino"]},
    {"id": "g", "type": "draw_frames", "count": 3, "instruction": "Dibuja 3 cosas que empiecen con m."},
]


def svg(data, picture=None):
    return str(render_worksheet(block(data), C, "Fredoka", picture))


@pytest.mark.parametrize("data", EVERY, ids=[d["type"] + d["id"] for d in EVERY])
def test_every_worksheet_is_a_sized_svg(data):
    out = svg(data)

    assert out.startswith('<svg class="dg dg-ws') and "viewBox" in out and "opacity=" not in out


def test_words_without_a_drawing_get_a_placeholder_and_drawn_ones_their_picture():
    data = {**EVERY[1], "pictures": {"mano": "a1"}}

    out = svg(data, picture=lambda asset_id: f"https://cdn/{asset_id}.svg")

    assert '<image href="https://cdn/a1.svg"' in out and out.count('class="pic-empty"') == 1


def test_the_chart_highlights_each_syllable_and_complete_hides_it():
    chart, complete = svg(EVERY[0]), svg(EVERY[2])

    assert f'<tspan fill="{C["accent"]}">ma</tspan>' in chart and "Nombra cada dibujo." in chart
    assert complete.count('class="blank"') == 2 and ">to<" not in complete and ">mo<" in complete


def test_every_word_is_hidden_in_the_word_search():
    grid = search_grid(block(EVERY[9]))
    rows = ["".join(r) for r in grid]
    cols = ["".join(r[i] for r in grid) for i in range(len(grid))]

    assert len(grid) == 7 and all(any(w in line for line in rows + cols) for w in ("MAMA", "MAPA", "PUMA"))
    assert search_grid(block(EVERY[9])) == grid  # deterministic: the PDF and the preview agree


def test_text_from_the_model_is_escaped():
    out = svg({"id": "r", "type": "reading", "sentences": [{"text": "<script>a</script> & b"}]})

    assert "<script>" not in out and "&lt;script&gt;" in out


def test_worksheets_print_with_real_text_and_vector_pictures():
    from tests.test_printing import line_art
    from app.illustrator import vectorize

    t = tome(*[{**b, "pictures": {"mamá": "v"}} if b["type"] == "reading" else b for b in EVERY])
    t.images = {"v": (vectorize(line_art()) or b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")}

    pdf, pages = render_pdf(t, paper="Letter", include_answer_key=False)

    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Practiquemos la lectura" in text and "Dictado" in text and re.search(r"Memo\s*mima", text)
    assert not any(p.images for p in PdfReader(io.BytesIO(pdf)).pages)


MATH = [{"id": "n", "type": "counting", "items": [{"object": "manzana", "count": 7}, {"object": "pastel", "count": 3}]},
        {"id": "m", "type": "picture_math", "operations": [
            {"object": "manzana", "a": 4, "op": "+", "b": 3}, {"object": "pastel", "a": 6, "op": "-", "b": 2},
            {"object": "globo", "a": 3, "op": "×", "b": 4}, {"object": "galleta", "a": 8, "op": "÷", "b": 2}]}]


def test_the_code_draws_exactly_the_quantities_of_each_operation():
    counting = svg({**MATH[0], "pictures": {"manzana": "a", "pastel": "p"}}, picture=lambda i: f"https://cdn/{i}")
    maths = svg({**MATH[1], "pictures": {w: w for w in ("manzana", "pastel", "globo", "galleta")}},
                picture=lambda i: f"https://cdn/{i}")

    assert counting.count("https://cdn/a") == 7 and counting.count("https://cdn/p") == 3
    assert maths.count("https://cdn/manzana") == 7  # 4 + 3
    assert maths.count("https://cdn/pastel") == 6 and maths.count('class="cross"') == 2  # 6, two crossed out
    assert maths.count("https://cdn/globo") == 12 and maths.count("https://cdn/galleta") == 8  # 3 groups of 4; 8
    assert "4 + 3 =" in maths and "8 ÷ 2 =" in maths


def test_operations_the_pictures_cannot_show_are_rejected():
    import pytest
    from pydantic import ValidationError

    for bad in ({"object": "x", "a": 2, "op": "-", "b": 5}, {"object": "x", "a": 7, "op": "÷", "b": 2},
                {"object": "x", "a": 9, "op": "×", "b": 9}):
        with pytest.raises(ValidationError):
            block({"id": "m", "type": "picture_math", "operations": [bad]})


def test_the_answer_key_gets_results_computed_by_code():
    from app.render import render_html

    html = render_html(tome(*MATH), paper="A4", include_answer_key=True)

    key = html[html.index('id="solucionario"'):]
    assert "4 + 3 (manzana)" in key and "8 ÷ 2 (galleta)" in key
    assert all(f"<br>{n}" in key for n in ("7", "3", "4", "12"))


def test_counting_draws_the_array_the_instruction_asks_for():
    from app.content import Counting
    from app.worksheets import _icons

    def centers(svg_parts):
        return sorted({round(float(p.split('y="')[1].split('"')[0])) for p in svg_parts})

    pic = lambda word, x, y, w, h: f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>'  # noqa: E731
    assert len(centers(_icons(pic, "huevo", 10, 0, 0, 480, 160, rows=2))) == 2  # 2 rows of 5
    assert len(centers(_icons(pic, "huevo", 10, 0, 0, 480, 160))) == 2  # full rows rather than 6 + 4
    assert len(centers(_icons(pic, "huevo", 12, 0, 0, 480, 300, rows=3))) == 3
    with pytest.raises(ValueError):
        Counting.model_validate({"id": "c", "type": "counting", "items": [{"object": "huevo", "count": 10, "rows": 3}]})
