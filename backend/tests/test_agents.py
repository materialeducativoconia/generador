import json

import pytest

from app.agents import AgentFailed, Brief, architect, writer
from app.llm import Completion
from tests.fakes import ScriptedLLM


BRIEF = Brief(request="Método de piano para principiantes", audience="Adultos", language="es", section_count=3)

OUTLINE = {
    "title": "Piano desde cero",
    "genre": "tutorial",
    "style_notes": "Claro y motivador",
    "sections": [{"title": f"Lección {i}", "objectives": ["Tocar"], "key_points": ["Do"]} for i in range(1, 4)],
}

SECTION = {"schema_version": 1, "summary": "Do central", "blocks": [{"id": "b1", "type": "paragraph", "text": "Hola"}]}


async def test_architect_returns_a_validated_outline():
    llm = ScriptedLLM(json.dumps(OUTLINE))

    result = await architect(llm, BRIEF)

    assert result.value.genre == "tutorial"
    assert len(result.value.sections) == 3
    assert "Método de piano" in llm.calls[0][-1]["content"]


async def test_architect_splits_a_one_section_tome_into_themes():
    thin = {"title": "Sumas", "genre": "worksheets", "sections": [{"title": "Sumas", "pages": 8}]}
    llm = ScriptedLLM(json.dumps(thin), json.dumps(OUTLINE))

    result = await architect(llm, Brief(request="sumas para preescolar", audience="Preescolar", page_count=9))

    assert "al menos 2" in llm.calls[0][-1]["content"]
    assert "al menos 2 temas" in llm.calls[1][-1]["content"] and "repite el título" in llm.calls[1][-1]["content"]
    assert len(result.value.sections) == 3
    assert len(result.attempts) == 2


async def test_architect_repairs_invalid_json_once():
    llm = ScriptedLLM('{"title": "Piano", "genre": "novela", "sections": []}', json.dumps(OUTLINE))

    result = await architect(llm, BRIEF)

    assert result.value.title == "Piano desde cero"
    assert len(llm.calls) == 2
    assert "no es válida" in llm.calls[1][-1]["content"]  # the validation error is sent back to the model
    assert [a.outcome for a in result.attempts] == ["invalid_output", "ok"]


async def test_architect_gives_up_after_the_repair_attempt():
    llm = ScriptedLLM("no es json", "tampoco")

    with pytest.raises(AgentFailed) as exc:
        await architect(llm, BRIEF)

    assert exc.value.code == "invalid_output"
    assert len(exc.value.attempts) == 2


async def test_architect_reports_truncated_output():
    llm = ScriptedLLM(Completion(text='{"title": "Pia', finish_reason="length", model="fake"))

    with pytest.raises(AgentFailed) as exc:
        await architect(llm, BRIEF)

    assert exc.value.code == "too_long"


async def test_writer_prompt_keeps_the_stable_prefix_first_for_context_caching():
    from app.content import Outline

    outline = Outline.model_validate(OUTLINE)
    llm_a, llm_b = ScriptedLLM(json.dumps(SECTION)), ScriptedLLM(json.dumps(SECTION))

    await writer(llm_a, BRIEF, outline, position=1)
    await writer(llm_b, BRIEF, outline, position=2)

    a, b = llm_a.calls[0], llm_b.calls[0]
    assert a[:-1] == b[:-1]  # system + series/outline identical across sections
    assert "Lección 2" in b[-1]["content"]


def test_brand_characters_only_for_personal_use():
    personal = Brief(request="Libro de colorear de Elsa", audience="Preescolar", brand_characters=True).describe()
    for_sale = Brief(request="Libro de colorear de Elsa", audience="Preescolar").describe()

    assert "uso personal" in personal and "nunca uses personajes" not in personal
    assert "nunca uses personajes" in for_sale


def test_the_users_format_reaches_the_architect():
    assert "(genre): coloring_book" in Brief(request="x", audience="y", format="coloring_book").describe()
    assert "(genre)" not in Brief(request="x", audience="y").describe()


async def test_a_picture_book_section_always_prints_as_plates():
    from app.content import Outline

    outline = Outline.model_validate({**OUTLINE, "genre": "picture_book",
                                      "sections": [{"title": "Aves", "objectives": ["Conocer"], "key_points": ["Kakapo"],
                                                    "pages": 1}]})
    loose = {"blocks": [{"id": "b1", "type": "image", "kind": "illustration", "size": "full",
                         "subject": "un kakapo en el bosque", "caption": "Lámina 1 — Kakapo", "notes": ["Es verde."]}]}
    llm = ScriptedLLM(json.dumps(loose), json.dumps(loose))

    result = await writer(llm, BRIEF, outline, position=1)

    assert "plate" in llm.calls[0][-1]["content"]  # the page budget asks for plates, not full pictures
    assert "lámina" in llm.calls[1][-1]["content"]  # one chance to fix it
    plate = result.value.blocks[0]
    assert plate.size == "plate" and plate.question == "Kakapo"


async def test_a_story_book_prints_pages_with_narration_and_lays_them_out():
    from app.agents import Brief, Outline, writer
    from app.content import OutlineSection
    from app.layout import lay_out
    from tests.fakes import ScriptedLLM

    loose = {"blocks": [{"id": "p1", "type": "image", "kind": "illustration", "size": "full", "subject": "Leo ve un T-Rex",
                         "narration": "Leo abrió la puerta y… ¡un T-Rex!"}]}
    fixed = {"blocks": [{"id": "p1", "type": "image", "kind": "illustration", "size": "plate", "subject": "Leo ve un T-Rex",
                         "narration": "Leo abrió la puerta y… ¡un T-Rex!"},
                        {"id": "p2", "type": "image", "kind": "illustration", "size": "plate", "subject": "El T-Rex sonríe",
                         "narration": "—¡Hola! —dijo el T-Rex."}]}
    outline = Outline(title="Hay un T-Rex en mi casa", genre="story_book", style_notes="",
                      sections=[OutlineSection(title="La visita", objectives=["Conocer al T-Rex"], key_points=["llega"], pages=3)])
    llm = ScriptedLLM(json.dumps(loose), json.dumps(fixed))
    result = await writer(llm, Brief(request="un cuento de dinosaurios", audience="Preescolar"), outline, 1)

    assert "narration" in llm.calls[0][0]["content"] and len(llm.calls) == 2  # the loose picture got one fix
    content = result.value
    assert all(b.size == "plate" and b.narration and not b.question for b in content.blocks)
    lay_out(content, position=1, pages=3, house_style="enciclopedia", story=True)
    assert [b.layout for b in content.blocks] == ["band", "spread"]
