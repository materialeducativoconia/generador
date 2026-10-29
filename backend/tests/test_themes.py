import io
import json

import pytest
from pypdf import PdfReader

from app.agents import Brief, designer
from app.content import Design, SectionContent
from app.render import Tome, TomeSection, render_html, render_pdf
from typing import get_args

from app.content import ArtStyle, CoverLayout
from app.themes import ART_STYLES, COVER_LAYOUTS, THEMES
from tests.fakes import ScriptedLLM

DESIGN = {"theme": "editorial", "palette": ["#FBF7F0", "#2B2A4C", "#C8553D"], "ornament": "hojas",
          "rationale": "Adultos: serif editorial, sobria."}


PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def tome(design):
    content = SectionContent.model_validate({"schema_version": 1, "summary": "", "blocks": [
        {"id": "b1", "type": "heading", "level": 2, "text": "El Do central"},
        {"id": "b2", "type": "callout", "variant": "key_idea", "text": "Busca las dos teclas negras."}]})
    return Tome(title="Piano desde cero", genre="tutorial", audience="Adultos", author=None,
                sections=[TomeSection(position=1, title="Postura", content=content)],
                design=Design.model_validate(design) if design else None)


async def test_designer_picks_a_known_theme():
    llm = ScriptedLLM(json.dumps(DESIGN))

    result = await designer(llm, Brief(request="piano", audience="Adultos"), "Piano desde cero", "tutorial", ["Postura"])

    assert result.value.theme == "editorial"
    assert all(name in llm.calls[0][0]["content"] for name in THEMES)  # every theme is described to the model


async def test_designer_picks_an_illustration_and_avoids_recent_tomes():
    llm = ScriptedLLM(json.dumps({**DESIGN, "illustration": "acuarela", "cover_layout": "band"}))
    recent = [Design.model_validate({**DESIGN, "illustration": "vector"})]

    result = await designer(llm, Brief(request="x", audience="y"), "T", "tutorial", [], recent=recent)

    assert result.value.art_style == ART_STYLES["acuarela"][1] and result.value.cover_layout == "band"
    assert "no los repitas" in llm.calls[0][1]["content"] and "#C8553D" in llm.calls[0][1]["content"]


def test_curated_lists_match_the_design_schema():
    assert set(ART_STYLES) == set(get_args(ArtStyle)) and set(COVER_LAYOUTS) == set(get_args(CoverLayout))


@pytest.mark.parametrize("layout", ["plate", "band", "framed"])
def test_every_cover_layout_prints(layout):
    t = tome({**DESIGN, "cover_layout": layout})
    t.cover_image = PNG

    assert f'class="cover art {layout}"' in render_html(t, paper="A4", include_answer_key=False)


async def test_designer_repairs_an_unknown_theme():
    llm = ScriptedLLM(json.dumps({**DESIGN, "theme": "neon"}), json.dumps(DESIGN))

    result = await designer(llm, Brief(request="x", audience="y"), "T", "tutorial", [])

    assert result.attempts[0].outcome == "invalid_output" and result.value.theme == "editorial"


def test_theme_sets_fonts_opener_and_palette():
    html = render_html(tome(DESIGN), paper="A4", include_answer_key=False)

    assert "Fraunces-Variable.ttf" in html and 'class="sec opener-numeral"' in html
    assert "#C8553D" in html and 'class="orn' in html


def test_without_a_design_the_classic_theme_is_used():
    html = render_html(tome(None), paper="A4", include_answer_key=False)

    assert 'class="sec opener-plain"' in html


@pytest.mark.parametrize("theme", list(THEMES))
def test_every_theme_renders_and_embeds_its_fonts(theme):
    pdf, _ = render_pdf(tome({**DESIGN, "theme": theme}), paper="A4", include_answer_key=False)

    fonts = {font["/BaseFont"] for page in PdfReader(io.BytesIO(pdf)).pages
             for font in (page.get("/Resources", {}).get("/Font", {}) or {}).values()}
    t = THEMES[theme]
    assert any(t.head.replace(" ", "-") in f for f in fonts), fonts
    assert any(t.body.replace(" ", "-") in f for f in fonts), fonts
