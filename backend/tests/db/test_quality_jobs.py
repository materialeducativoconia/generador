"""Phase 6: the Editor proofreads each section inside the lesson job, and the tome gets a quality card."""

import json

from tests.db.test_jobs import OUTLINE, SECTION, engine, new_tome, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM

FIX = {"score": 4, "issues": ["Faltaba la tilde en «Dó»."], "fixes": [
    {"block_id": "b1", "field": "text", "text": "El Do central, la nota de partida"}]}


async def outlined(client, key, user, engine):
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps({**OUTLINE, "sections": OUTLINE["sections"][:1]})))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    return sid


async def test_the_editor_corrects_the_section_before_it_is_saved(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await outlined(client, key, user, engine)

    job = await run_next(engine, ScriptedLLM(json.dumps(SECTION), json.dumps(FIX)), edit=True)

    row = await raw_db.fetchrow("select content_json, review from public.lessons where series_id = $1", sid)
    assert json.loads(row["content_json"])["blocks"][0]["text"] == "El Do central, la nota de partida"
    assert json.loads(row["review"]) == {"score": 4, "issues": FIX["issues"], "fixed": 1}
    versions = await raw_db.fetch("select prompt_version from public.generation_logs where job_id = $1", job["id"])
    assert {"writer@7", "editor@1"} <= {v["prompt_version"] for v in versions}


async def test_a_failing_editor_keeps_the_writers_text(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await outlined(client, key, user, engine)

    await run_next(engine, ScriptedLLM(json.dumps(SECTION), "no es json", "tampoco"), edit=True)

    row = await raw_db.fetchrow("select status, content_json, review from public.lessons where series_id = $1", sid)
    assert row["status"] == "generated" and row["review"] is None
    assert json.loads(row["content_json"])["blocks"][0]["text"] == "El Do central"


async def test_quality_card_sums_up_text_art_and_print(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await outlined(client, key, user, engine)
    await run_next(engine, ScriptedLLM(json.dumps(SECTION), json.dumps({**FIX, "score": 2})), edit=True)

    card = (await client.get(f"/api/series/{sid}/quality", headers=bearer(key, user))).json()

    assert card["text"]["score"] == 2 and card["text"]["fixed"] == 1
    assert card["text"]["issues"] == [{"section": 1, "issue": "Faltaba la tilde en «Dó»."}]
    assert card["print"] is None and card["verdict"] == "revisar"
    assert any("texto" in r.lower() for r in card["reasons"])
