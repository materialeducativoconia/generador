"""Phase 7: pay less per tome — colouring pages shared between tomes, and every tome shows what it cost."""

import json

from app.llm import Completion
from tests.db.test_illustrations import (ART, FIVE, SECTION, FakeImages, empty_library, illustrate,  # noqa: F401
                                         image, written_tome)
from tests.db.test_jobs import OUTLINE, engine, new_tome, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM


async def test_generic_colouring_pages_are_reused_by_other_tomes(raw_db, google_user, client, key, engine):
    user = await google_user()
    await written_tome(client, key, user, engine, FIVE)
    await illustrate(engine, FakeImages())
    second = await written_tome(client, key, user, engine, {**SECTION, "blocks": [image("y", "un cerdo")]})
    images = FakeImages()

    await run_next(engine, ScriptedLLM(), images=images)

    content = json.loads(await raw_db.fetchval("select content_json from public.lessons where series_id = $1", second))
    assert images.calls == [] and content["blocks"][0]["asset_id"]
    shared = await raw_db.fetchval("select use_count from public.assets where subject_norm = 'cerdo'")
    assert shared == 2


async def test_pages_with_the_tomes_own_characters_stay_in_that_tome(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)  # b2 is painted as "Rito smiles next to a cow"

    await illustrate(engine, FakeImages())

    keys = dict(await raw_db.fetch("select subject_norm, style_key from public.assets"))
    assert keys["vaca feliz"] == f"tome:{sid}"


async def test_the_quality_card_shows_what_the_tome_cost(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)
    usage = {"prompt_tokens": 3000, "completion_tokens": 2000, "prompt_cache_hit_tokens": 2000,
             "prompt_cache_miss_tokens": 1000}
    outline = Completion(json.dumps({**OUTLINE, "sections": OUTLINE["sections"][:1]}), "stop", "fake", usage)
    await run_next(engine, ScriptedLLM(outline))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    await run_next(engine, ScriptedLLM(json.dumps(FIVE)))
    await illustrate(engine, FakeImages())  # two calls at $0.04
    await raw_db.execute("""update public.series set cover = '{"cost_usd": 0.09, "spent_usd": 0.18}' where id = $1""",
                         sid)

    cost = (await client.get(f"/api/series/{sid}/quality", headers=bearer(key, user))).json()["cost"]

    # DeepSeek: 2000 cached x $0.028/M + 1000 missed x $0.28/M + 2000 out x $0.42/M
    assert cost["text_usd"] == round(0.000056 + 0.00028 + 0.00084, 4)
    assert cost["images_usd"] == 0.08 and cost["cover_usd"] == 0.18
    assert cost["total_usd"] == round(cost["text_usd"] + 0.08 + 0.18, 4)
    assert cost["minutes"] is not None and cost["minutes"] >= 0
