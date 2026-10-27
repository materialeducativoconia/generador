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
