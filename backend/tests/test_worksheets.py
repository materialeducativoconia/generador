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
    {"id": "z", "type": "maze", "start": "conejo", "goal": "zanahoria", "rows": 8, "cols": 8,
     "instruction": "Ayuda al conejo a llegar a su zanahoria."},
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


HARD = {"id": "h", "type": "word_search", "size": 12, "diagonal": True, "backwards": True,
        "words": ["planeta", "estrella", "cometa", "luna", "sol", "galaxia", "órbita", "satélite", "marte", "venus"]}


def test_harder_word_searches_hide_every_word_diagonally_or_backwards():
    from app.worksheets import search_layout

    grid, placed = search_layout(block(HARD))
    assert set(placed) == set(HARD["words"])  # none left out, even crowded
    for word, cells in placed.items():
        letters = "".join(grid[r][c] for r, c in cells)
        assert letters == word.upper().replace("Ó", "O").replace("É", "E")
        steps = {(b[0] - a[0], b[1] - a[1]) for a, b in zip(cells, cells[1:])}
        assert len(steps) == 1  # a straight line
    directions = {next(iter({(b[0] - a[0], b[1] - a[1]) for a, b in zip(c, c[1:])})) for c in placed.values()}
    assert directions - {(0, 1), (1, 0)}  # some diagonal or backwards words, as asked


def test_young_word_searches_stay_across_or_down():
    from app.worksheets import search_layout

    _, placed = search_layout(block(EVERY[9]))
    for cells in placed.values():
        assert {(b[0] - a[0], b[1] - a[1]) for a, b in zip(cells, cells[1:])} <= {(0, 1), (1, 0)}


def test_a_word_search_with_too_many_letters_is_rejected():
    with pytest.raises(ValueError):
        block({"id": "s", "type": "word_search", "size": 6, "words": ["abcdef"] * 4})


@pytest.mark.parametrize("rows,cols", [(4, 4), (8, 8), (20, 16), (5, 12)])
def test_the_maze_has_exactly_one_way_through_every_cell(rows, cols):
    from app.worksheets import STEP, maze_layout

    b = block({"id": "m", "type": "maze", "rows": rows, "cols": cols})
    walls, path = maze_layout(b)
    opened = sum(1 for r in range(rows) for c in range(cols) for d in STEP if not walls[r][c] & d) - 2
    assert opened == 2 * (rows * cols - 1)  # a spanning tree: every cell reached, no loops
    assert path[0] == (0, 0) and path[-1] == (rows - 1, cols - 1)
    for (r0, c0), (r1, c1) in zip(path, path[1:]):  # each step goes through an open wall
        d = next(d for d, step in STEP.items() if step == (r1 - r0, c1 - c0))
        assert not walls[r0][c0] & d
    assert maze_layout(b) == (walls, path)  # deterministic


def test_the_maze_draws_who_searches_and_what_they_look_for():
    out = svg(EVERY[12], picture=lambda asset_id: f"https://cdn/{asset_id}.svg")

    assert out.count('class="pic-empty"') == 2 and "conejo" in out and "zanahoria" in out


def test_the_answer_key_draws_the_word_search_and_maze_solutions():
    from app.render import render_html

    html = render_html(tome(EVERY[9], EVERY[12]), paper="A4", include_answer_key=True)

    key = html[html.index('id="solucionario"'):]
    assert "dg-ws-key ws-word-search" in key and "dg-ws-key ws-maze" in key and "<polyline" in key
    assert "Sopa de letras" in key and "Laberinto" in key
