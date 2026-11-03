"""Another version of a tome: another illustration style, the story changed, or the next tome of its series."""

import json

from tests.db.test_jobs import OUTLINE, engine, new_tome, run_next  # noqa: F401 - engine is a fixture
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM

PLATE = {"id": "p1", "type": "image", "kind": "illustration", "size": "plate", "subject": "Un águila",
         "narration": "Lía vio un águila.", "asset_id": "00000000-0000-0000-0000-000000000001"}


async def _written(raw_db, client, key, engine, user):  # noqa: F811
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    await raw_db.execute(
        """update public.series set genre = 'story_book', house_style = 'acuarela', status = 'ready',
                  "cast" = '[{"character_id": null, "name": "Lía", "look": "a girl", "sheet_key": null}]'::jsonb,
                  plan = '{"story": {"protagonist": "Lía quiere ver un águila"}}'::jsonb,
                  design = '{"theme": "juego", "palette": ["#112233", "#445566", "#778899"], "house_style": "acuarela"}'::jsonb
            where id = $1""", sid)
    await raw_db.execute("""update public.lessons set status = 'generated', content_json = $2::jsonb
                             where series_id = $1""", sid, json.dumps({"schema_version": 1, "blocks": [PLATE]}))
    await raw_db.execute("update public.generation_jobs set status = 'cancelled' where status = 'queued'")
    return sid


async def test_another_style_copies_the_text_and_paints_it_again(raw_db, google_user, client, key, engine):  # noqa: F811
    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)
    before = await raw_db.fetchval("select sum(remaining) from public.credit_buckets b join public.memberships m on m.org_id = b.org_id where m.user_id = $1", user)

    response = await client.post(f"/api/series/{sid}/versions", json={"mode": "style", "house_style": "gouache"},
                                 headers=bearer(key, user))

    assert response.status_code == 202
    new = response.json()["series"]["id"]
    row = await raw_db.fetchrow("select status, source_id, variant, house_style, design->>'house_style' as d, title"
                                " from public.series where id = $1::uuid", new)
    assert dict(row) == {"status": "ready", "source_id": sid, "variant": "style", "house_style": "gouache",
                         "d": "gouache", "title": "Piano desde cero"}
    blocks = [json.loads(r["content_json"])["blocks"][0] for r in await raw_db.fetch(
        "select content_json from public.lessons where series_id = $1::uuid order by position", new)]
    assert len(blocks) == 3 and all(b["narration"] == "Lía vio un águila." and "asset_id" not in b for b in blocks)
    job = await raw_db.fetchrow("select kind, payload from public.generation_jobs where series_id = $1::uuid", new)
    assert job["kind"] == "cover" and json.loads(job["payload"]) == {"illustrate": True}
    spent = before - await raw_db.fetchval("select sum(remaining) from public.credit_buckets b join public.memberships m on m.org_id = b.org_id where m.user_id = $1", user)
    assert spent == 4 + 2  # a cover and three plates at half a credit each, rounded up
    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    assert [v["variant"] for v in detail["versions"]] == ["style"]  # the original lists its new version

    same = await client.post(f"/api/series/{sid}/versions", json={"mode": "style", "house_style": "acuarela"},
                             headers=bearer(key, user))
    assert same.status_code == 422


async def test_the_next_tome_of_the_series_continues_with_the_same_characters(raw_db, google_user, client, key,
                                                                              engine):  # noqa: F811
    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)

    response = await client.post(f"/api/series/{sid}/versions",
                                 json={"mode": "next", "changes": "Ahora en el mar"}, headers=bearer(key, user))

    assert response.status_code == 202
    new = response.json()["series"]["id"]
    row = await raw_db.fetchrow(
        """select n.variant, n.status, n."cast"->0->>'name' as guide, n.design->>'house_style' as style,
                  n.collection_id is not null and n.collection_id = o.collection_id as same_series,
                  n.collection_position > o.collection_position as after
             from public.series n, public.series o where n.id = $1::uuid and o.id = $2""", new, sid)
    assert dict(row) == {"variant": "next", "status": "outlining", "guide": "Lía", "style": "acuarela",
                         "same_series": True, "after": True}
    payload = json.loads(await raw_db.fetchval(
        "select payload from public.generation_jobs where series_id = $1::uuid and kind = 'outline'", new))
    extra = payload["brief"]["extra_instructions"]
    assert "siguiente de la serie" in extra and "Postura" in extra and "Lía quiere ver un águila" in extra
    assert "Ahora en el mar" in extra and payload["brief"]["format"] == "story_book"


async def test_a_new_story_version_needs_a_paid_plan(raw_db, google_user, client, key, engine):  # noqa: F811
    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)
    ok = await client.post(f"/api/series/{sid}/versions", json={"mode": "story", "changes": "Que sea una niña pirata"},
                           headers=bearer(key, user))
    assert ok.status_code == 202
    assert await raw_db.fetchval("select variant from public.series where id = $1::uuid",
                                 ok.json()["series"]["id"]) == "story"

    await raw_db.execute("update public.subscriptions set status = 'canceled' where org_id = (select org_id from public.memberships where user_id = $1)", user)
    locked = await client.post(f"/api/series/{sid}/versions", json={"mode": "story", "changes": "Otra"},
                               headers=bearer(key, user))
    assert locked.status_code == 402


async def test_rewriting_the_text_keeps_every_picture_and_paints_nothing(raw_db, google_user, client, key,
                                                                         engine):  # noqa: F811
    user = await google_user()
    sid = await _written(raw_db, client, key, engine, user)
    await raw_db.execute("update public.series set cover_key = 'covers/x.png' where id = $1", sid)

    response = await client.post(f"/api/series/{sid}/versions",
                                 json={"mode": "text", "changes": "Que suene más a cuento"}, headers=bearer(key, user))

    assert response.status_code == 202
    new = response.json()["series"]["id"]
    rewrite = {"pages": [{"id": "p1", "narration": "Una mañana, Lía miró al cielo y vio un águila enorme.",
                          "question": "¿Qué?"}]}
    await run_next(engine, ScriptedLLM(json.dumps(rewrite)))

    row = await raw_db.fetchrow("select status, variant, cover_key from public.series where id = $1::uuid", new)
    assert dict(row) == {"status": "ready", "variant": "text", "cover_key": "covers/x.png"}
    block = json.loads(await raw_db.fetchval(
        "select content_json from public.lessons where series_id = $1::uuid", new))["blocks"][0]
    assert block["narration"].startswith("Una mañana") and "question" not in block  # no field the page didn't have
    assert block["asset_id"] == PLATE["asset_id"]
    original = json.loads(await raw_db.fetchval("select content_json from public.lessons where series_id = $1", sid))
    assert original["blocks"][0]["narration"] == "Lía vio un águila."
