"""Phase 6: the Editor proofreads every section and the layout checker repairs badly broken pages."""

import json

from app.agents import Brief, apply_fixes, editor
from app.content import EditReview, Fix, Outline, SectionContent
from app.render import render_checked
from tests.fakes import ScriptedLLM
from tests.test_render import tome

CONTENT = SectionContent.model_validate({"schema_version": 1, "summary": "", "blocks": [
    {"id": "b1", "type": "paragraph", "text": "El agua se evapora con el frio."},
    {"id": "b2", "type": "list", "items": ["nubes", "lluvia"]},
    {"id": "b3", "type": "exercise", "kind": "open", "prompt": "¿Cuánto es 7 x 8?", "answer": "54"}]})
OUTLINE = Outline(title="El agua", genre="lesson_series", sections=[{"title": "El ciclo", "objectives": ["Explicar"]}])


def review(*fixes, score=3, issues=("La respuesta de 7 x 8 es incorrecta.",)):
    return json.dumps({"score": score, "issues": list(issues), "fixes": list(fixes)})


async def test_editor_reads_the_section_with_its_facts_and_objectives():
    llm = ScriptedLLM(review())
    brief = Brief(request="ciclo del agua", audience="Primaria", facts=["El agua se evapora con el calor del Sol."])

    result = await editor(llm, brief, OUTLINE, 1, CONTENT)

    assert result.value.score == 3
    system, user = llm.calls[0][0]["content"], llm.calls[0][-1]["content"]
    assert "respuesta" in system.lower() and "ortografía" in system.lower()
    assert "calor del Sol" in user and "Explicar" in user and '"b3"' in user


def test_fixes_rewrite_only_known_text_fields():
    fixes = EditReview.model_validate(json.loads(review(
        {"block_id": "b1", "field": "text", "text": "El agua se evapora con el calor del Sol."},
        {"block_id": "b2", "field": "items", "index": 1, "text": "lluvia (precipitación)"},
        {"block_id": "b3", "field": "answer", "text": "56"},
        {"block_id": "zz", "field": "text", "text": "bloque que no existe"},
        {"block_id": "b2", "field": "items", "index": 9, "text": "fuera de rango"},
        {"block_id": "b1", "field": "answer", "text": "un párrafo no tiene respuesta"},
    ))).fixes

    fixed, applied = apply_fixes(CONTENT, fixes)

    assert applied == 3
    blocks = {b.id: b for b in fixed.blocks}
    assert blocks["b1"].text.endswith("calor del Sol.") and blocks["b2"].items == ["nubes", "lluvia (precipitación)"]
    assert blocks["b3"].answer == "56"
    assert CONTENT.blocks[2].answer == "54"  # the writer's version is left untouched


def test_a_fix_that_breaks_the_block_is_dropped():
    too_long = Fix.model_construct(block_id="b1", field="text", index=None, text="x" * 5000)

    fixed, applied = apply_fixes(CONTENT, [too_long])

    assert applied == 0 and fixed.blocks[0].text == CONTENT.blocks[0].text


def _pushed_figure_tome():
    from tests.test_illustrator import png

    t = tome({"id": "p1", "type": "paragraph", "text": "Colorea el dibujo. " * 30},
             {"id": "p2", "type": "paragraph", "text": "Usa tus colores favoritos. " * 25},
             {"id": "f", "type": "image", "kind": "line_art", "subject": "una vaca", "size": "full", "asset_id": "a"})
    t.images = {"a": (png(lambda d: d.ellipse((40, 40, 360, 360), outline="black", width=8)), "image/png")}
    return t


def test_a_picture_pushed_to_the_next_page_is_fitted_into_the_gap():
    pdf, pages, layout = render_checked(_pushed_figure_tome(), paper="A4", include_answer_key=False)

    assert layout["fixed"] == ["una vaca"] and pages == 2  # cover + one page, not a half-empty page and a picture
    assert pdf.startswith(b"%PDF")


def test_nearly_empty_pages_are_reported():
    t = tome({"id": "p1", "type": "paragraph", "text": "Línea. " * 520}, {"id": "p2", "type": "paragraph", "text": "Fin."})

    _, pages, layout = render_checked(t, paper="A4", include_answer_key=False)

    assert any(f"Página {pages}" in i and "casi vacía" in i for i in layout["issues"])
