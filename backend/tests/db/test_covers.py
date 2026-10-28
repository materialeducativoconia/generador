"""The cover agent: queued after the outline, art-directed by DeepSeek, painted by OpenRouter."""

import json

from app.images import GeneratedImage
from app.references import Reference
from tests.db.test_jobs import OUTLINE, engine, new_tome, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM
from tests.test_covers import PLAN, PNG
from tests.test_themes import DESIGN


class FakeImages:
    def __init__(self):
        self.calls = []

    async def generate(self, prompt, *, references=(), aspect_ratio="3:4", resolution="1K"):
        self.calls.append({"prompt": prompt, "references": list(references), "aspect_ratio": aspect_ratio,
                           "resolution": resolution})
        return GeneratedImage(data=PNG, media_type="image/png", model="fake-image", cost_usd=0.04)


class FakeStorage:
    def __init__(self):
        self.uploads = {}

    async def upload(self, key, data, content_type="application/pdf", bucket="exports"):
        self.uploads[(bucket, key)] = (data, content_type)

    def public_url(self, key, bucket="covers"):
        return f"https://storage.test/{bucket}/{key}"


async def fake_references(queries, **kwargs):
    return [Reference("Piano for Kids", "https://openlibrary.org/works/OL1W",
                      "https://covers.openlibrary.org/b/id/11-M.jpg", PNG)]


async def outlined_tome(client, key, user, engine):
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)), covers=True)
    return sid


async def test_the_outline_queues_a_cover_job(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await outlined_tome(client, key, user, engine)

    kinds = await raw_db.fetch("select kind, status from public.generation_jobs where series_id = $1"
                               " order by created_at", sid)
    assert [(r["kind"], r["status"]) for r in kinds] == [("outline", "succeeded"), ("cover", "queued")]


async def test_cover_job_paints_with_references_and_stores_the_cover(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await outlined_tome(client, key, user, engine)
    images, storage = FakeImages(), FakeStorage()

    job = await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN)), covers=True, images=images,
                         storage=storage, references=fake_references)

    assert job["kind"] == "cover"
    row = await raw_db.fetchrow("select cover_key, cover from public.series where id = $1", sid)
    assert ("covers", row["cover_key"]) in storage.uploads
    assert row["cover_key"].endswith(".jpg") and storage.uploads[("covers", row["cover_key"])][1] == "image/jpeg"
    cover = json.loads(row["cover"])
    assert cover["palette"] == DESIGN["palette"] and cover["references"][0]["title"] == "Piano for Kids"
    call = images.calls[0]
    assert call["resolution"] == "4K"  # sharp enough for a printed cover
    assert call["references"] == [PNG] and "no text" in call["prompt"].lower()
    assert PLAN["illustration_prompt"] in call["prompt"]
    logs = await raw_db.fetch("select prompt_version from public.generation_logs where job_id = $1 order by created_at",
                              job["id"])
    assert [r["prompt_version"] for r in logs] == ["designer@2", "cover@3"]

    client._transport.app.state.storage = storage
    listed = (await client.get("/api/series", headers=bearer(key, user))).json()["series"][0]
    assert listed["cover_url"] == f"https://storage.test/covers/{row['cover_key']}"
    assert listed["cover_status"] == "succeeded" and listed["cover_palette"] == DESIGN["palette"]


async def test_cover_job_without_image_model_fails_without_touching_the_tome(raw_db, google_user, client, key,
                                                                              engine):
    user = await google_user()
    sid = await outlined_tome(client, key, user, engine)

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN)), covers=True, images=None, references=fake_references)

    job = await raw_db.fetchrow("select status, error from public.generation_jobs where series_id = $1"
                                " and kind = 'cover'", sid)
    assert job["status"] == "failed" and json.loads(job["error"])["code"] == "not_configured"
    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "outline_ready"


async def test_a_new_cover_can_be_requested_once_at_a_time(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await outlined_tome(client, key, user, engine)

    busy = await client.post(f"/api/series/{sid}/cover", headers=bearer(key, user))
    await raw_db.execute("update public.generation_jobs set status = 'succeeded' where series_id = $1"
                         " and kind = 'cover'", sid)
    again = await client.post(f"/api/series/{sid}/cover", headers=bearer(key, user))

    assert busy.status_code == 409 and busy.json()["error"]["code"] == "cover_in_progress"
    assert again.status_code == 202
    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    assert detail["cover_status"] == "queued"


async def test_designer_runs_first_and_the_cover_uses_its_palette(raw_db, google_user, client, key, engine):
    from tests.test_themes import DESIGN

    user = await google_user()
    sid = await outlined_tome(client, key, user, engine)
    llm = ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN))

    await run_next(engine, llm, covers=True, images=FakeImages(), storage=FakeStorage(), references=fake_references)

    row = await raw_db.fetchrow("select design, cover from public.series where id = $1", sid)
    assert json.loads(row["design"])["theme"] == "editorial"
    assert json.loads(row["cover"])["palette"] == DESIGN["palette"]
    assert "#C8553D" in llm.calls[1][1]["content"]  # the cover director is told the interior palette
    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    assert detail["design"]["theme"] == "editorial"


async def test_a_new_cover_keeps_the_design(raw_db, google_user, client, key, engine):
    from tests.test_themes import DESIGN

    user = await google_user()
    sid = await outlined_tome(client, key, user, engine)
    await raw_db.execute("update public.series set design = $2::jsonb where id = $1", sid, json.dumps(DESIGN))
    llm = ScriptedLLM(json.dumps(PLAN))  # only the cover director is called

    await run_next(engine, llm, covers=True, images=FakeImages(), storage=FakeStorage(), references=fake_references)

    assert len(llm.calls) == 1


async def test_without_image_model_the_design_is_still_saved(raw_db, google_user, client, key, engine):
    from tests.test_themes import DESIGN

    user = await google_user()
    sid = await outlined_tome(client, key, user, engine)

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN)), covers=True, images=None, references=fake_references)

    assert json.loads(await raw_db.fetchval("select design from public.series where id = $1", sid))["theme"] == "editorial"
