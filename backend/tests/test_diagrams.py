"""Phase 5: diagrams drawn by code — exact, free, instant, with real text."""

import io
import re

import pytest
from pydantic import TypeAdapter, ValidationError
from pypdf import PdfReader

from app.content import Block, SectionContent
from app.diagrams import render_diagram
from app.render import render_pdf
from tests.test_render import tome

C = {"ink": "#2D2A5A", "accent": "#E8762C", "tint": "#F8D3B5", "soft": "#FDF1E8", "line": "#D5D4DE", "muted": "#7F7D9A"}
block = TypeAdapter(Block).validate_python

STAFF = {"id": "s", "type": "staff", "time": "4/4", "show_names": True, "notes": [
    {"pitch": "C4"}, {"pitch": "D4"}, {"pitch": "E4", "duration": "half"}, {"pitch": "F#5", "duration": "eighth"},
    {"pitch": "rest", "duration": "quarter"}, {"pitch": "G4", "duration": "whole"}]}
EVERY = [
    STAFF,
    {"id": "t", "type": "timeline", "events": [{"when": "1492", "label": "Llegada de Colón a América"},
                                               {"when": "1810", "label": "Independencia"}]},
    {"id": "c", "type": "cycle", "steps": ["Evaporación", "Condensación", "Precipitación", "Escorrentía"]},
    {"id": "p", "type": "cycle", "closed": False, "steps": ["Semilla", "Brote", "Planta", "Flor", "Fruto"]},
    {"id": "b", "type": "bar_chart", "labels": ["Lunes", "Martes", "Miércoles"], "values": [3, 7.5, 5], "unit": "mm"},
    {"id": "n", "type": "number_line", "start": 0, "end": 10, "marks": [3], "blanks": [7]},
    {"id": "f", "type": "fraction", "fractions": [{"numerator": 1, "denominator": 4},
                                                 {"numerator": 2, "denominator": 3}], "shape": "circle"},
    {"id": "g", "type": "fraction", "fractions": [{"numerator": 3, "denominator": 5}], "shape": "bar", "shaded": False},
    {"id": "k", "type": "clock", "times": ["7:30", "12:15"], "show_time": True},
]


def svg(data, font="Fredoka"):
    return str(render_diagram(block(data), C, font))


@pytest.mark.parametrize("data", EVERY, ids=[d["type"] + d["id"] for d in EVERY])
def test_every_diagram_is_a_sized_svg_in_the_theme_colours(data):
    out = svg(data)

    assert out.startswith('<svg class="dg') and 'width="' in out and "viewBox" in out
    assert C["accent"] in out or C["ink"] in out
    assert "opacity=" not in out  # WeasyPrint clips an <svg> that carries an opacity attribute


def test_staff_names_notes_in_spanish_and_draws_the_clef_and_bars():
    out = svg(STAFF)

    assert "\U0001D11E" in out  # treble clef glyph, from the bundled Noto Music font
    assert all(f">{n}<" in out for n in ("Do", "Re", "Mi", "Fa♯", "Sol"))
    assert "♯" in out and out.count('class="bar"') >= 1


def test_text_from_the_model_is_escaped():
    out = svg({"id": "t", "type": "timeline", "events": [{"when": "<b>", "label": "a & b"},
                                                         {"when": "2", "label": "<script>x</script>"}]})

    assert "<script>" not in out and "&lt;script&gt;" in out and "a &amp; b" in out


def test_number_line_leaves_boxes_for_the_blanks():
    out = svg({"id": "n", "type": "number_line", "start": 0, "end": 10, "blanks": [7]})

    assert out.count('class="blank"') == 1 and ">7<" not in out and ">6<" in out


def test_clock_hands_point_at_the_time():
    out = svg({"id": "k", "type": "clock", "times": ["3:00"]})

    hour = re.search(r'class="hour"[^>]*x2="([\d.]+)" y2="([\d.]+)"', out)
    assert hour and float(hour.group(1)) > 90 and abs(float(hour.group(2)) - 90) < 1  # 3 o'clock points right


def test_invalid_diagrams_are_rejected():
    for bad in ({"id": "n", "type": "number_line", "start": 5, "end": 1},
                {"id": "f", "type": "fraction", "fractions": [{"numerator": 5, "denominator": 4}]},
                {"id": "b", "type": "bar_chart", "labels": ["a", "b"], "values": [1]},
                {"id": "k", "type": "clock", "times": ["25:00"]}):
        with pytest.raises(ValidationError):
            block(bad)


def test_diagrams_print_as_vectors_with_real_text():
    t = tome(*EVERY)

    pdf, _ = render_pdf(t, paper="6x9", include_answer_key=False)

    reader = PdfReader(io.BytesIO(pdf))
    text = "".join(p.extract_text() for p in reader.pages)
    assert "Condensación" in text and "Independencia" in text and "Miércoles" in text
    assert not any(p.images for p in reader.pages)
    fonts = {f["/BaseFont"] for p in reader.pages for f in p["/Resources"].get("/Font", {}).values()}
    assert any("Noto-Music" in f for f in fonts)


def test_writer_catalog_knows_the_diagrams():
    from app.agents import WRITER_SYSTEM

    for kind in ("staff", "timeline", "cycle", "bar_chart", "number_line", "fraction", "clock"):
        assert f"- {kind} {{" in WRITER_SYSTEM
    assert SectionContent.model_validate({"schema_version": 1, "blocks": EVERY})
