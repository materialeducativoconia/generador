"""Phase 2: image blocks are painted by the Illustrator, checked by the Reviewer and shared via the Curator."""

import json

import pytest

from app.images import GeneratedImage
from app.vision import Review
from tests.db.test_covers import FakeStorage
from tests.db.test_jobs import OUTLINE, engine, new_tome, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM
from tests.test_illustrator import png

LINE_ART = png(lambda d: d.ellipse((60, 60, 340, 340), outline="black", width=10))
SECTION = {"schema_version": 1, "summary": "Animales", "blocks": [
    {"id": "b1", "type": "heading", "level": 2, "text": "La granja"},
    {"id": "b2", "type": "image", "kind": "line_art", "subject": "Una vaca feliz", "size": "full"},
    {"id": "b3", "type": "image", "kind": "illustration", "subject": "un granero rojo", "size": "half"},
]}


class FakeImages:
    def __init__(self, data=LINE_ART):
        self.calls, self.data = [], data

    async def generate(self, prompt, *, references=(), aspect_ratio="3:4"):
        self.calls.append({"prompt": prompt, "aspect_ratio": aspect_ratio})
        return GeneratedImage(data=self.data, media_type="image/png", model="fake-image", cost_usd=0.03)


class FakeVision:
    def __init__(self, *verdicts):
        self.verdicts = list(verdicts)
        self.calls = 0

    async def review(self, image, *, kind, subject):
        self.calls += 1
        return self.verdicts.pop(0) if self.verdicts else Review(ok=True)


@pytest.fixture(autouse=True)
async def empty_library(raw_db):
    # The library is shared across tomes by design, so earlier tests would feed the Curator.
    await raw_db.execute("delete from public.assets")


async def written_tome(client, key, user, engine, section=SECTION):
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps({**OUTLINE, "sections": OUTLINE["sections"][:1]})))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    await run_next(engine, ScriptedLLM(json.dumps(section)))
    return sid


async def illustrate_all(engine, images, vision=None, storage=None):
    storage = storage or FakeStorage()
    jobs = []
    while True:
        from app.jobs import claim_job

        async with engine.connect() as conn:
            from sqlalchemy import text

            queued = (await conn.execute(text("select count(*) from public.generation_jobs"
                                              " where kind = 'illustration' and status = 'queued'"))).scalar_one()
        if not queued:
            return jobs, storage
        jobs.append(await run_next(engine, None, images=images, vision=vision or FakeVision(), storage=storage))


async def test_a_written_section_queues_one_job_per_image(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)

    rows = await raw_db.fetch("select payload from public.generation_jobs where series_id = $1"
                              " and kind = 'illustration' order by created_at", sid)
    assert [json.loads(r["payload"])["block_id"] for r in rows] == ["b2", "b3"]


async def test_illustrator_paints_stores_and_attaches_the_image(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)
    images = FakeImages()

    jobs, storage = await illustrate_all(engine, images)

    assert {j["kind"] for j in jobs} == {"illustration"} and len(images.calls) == 2
    assert images.calls[0]["aspect_ratio"] == "3:4" and "coloring" in images.calls[0]["prompt"].lower()
    lesson = await raw_db.fetchrow("select content_json, content_version from public.lessons where series_id = $1",
                                   sid)
    blocks = {b["id"]: b for b in json.loads(lesson["content_json"])["blocks"]}
    assert blocks["b2"]["asset_id"] and blocks["b3"]["asset_id"] and lesson["content_version"] == 3
    asset = await raw_db.fetchrow("select kind, subject_norm, style_key, storage_key, media_type from public.assets"
                                  " where id = $1::uuid", blocks["b2"]["asset_id"])
    assert dict(asset) | {"storage_key": None} == {"kind": "line_art", "subject_norm": "vaca feliz", "style_key": "line",
                                                    "storage_key": None, "media_type": "image/png"}
    assert ("images", asset["storage_key"]) in storage.uploads

    client._transport.app.state.storage = storage
    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    assert detail["assets"][blocks["b2"]["asset_id"]].startswith("https://storage.test/images/")
    progress = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()
    assert progress["images"] == {"total": 2, "done": 2, "active": 0, "failed": 0}


async def test_the_curator_reuses_a_matching_image_from_the_library(raw_db, google_user, client, key, engine):
    user = await google_user()
    await written_tome(client, key, user, engine)
    await illustrate_all(engine, FakeImages())
    other = await google_user()
    sid = await written_tome(client, key, other, engine, {**SECTION, "blocks": [
        {"id": "x1", "type": "image", "kind": "line_art", "subject": "la vaca feliz", "size": "full"}]})
    images = FakeImages()

    await illustrate_all(engine, images)

    assert images.calls == []
    content = json.loads(await raw_db.fetchval("select content_json from public.lessons where series_id = $1", sid))
    reused = await raw_db.fetchval("select use_count from public.assets where id = $1::uuid",
                                   content["blocks"][0]["asset_id"])
    assert reused == 2


async def test_a_rejected_image_is_painted_again_with_the_reviewers_notes(raw_db, google_user, client, key, engine):
    user = await google_user()
    await written_tome(client, key, user, engine, {**SECTION, "blocks": [SECTION["blocks"][1]]})
    images = FakeImages()
    vision = FakeVision(Review(ok=False, has_text=True, issues="aparece la palabra VACA"), Review(ok=True))

    await illustrate_all(engine, images, vision)

    assert len(images.calls) == 2 and "aparece la palabra VACA" in images.calls[1]["prompt"]
    review = json.loads(await raw_db.fetchval("select review from public.assets order by created_at desc limit 1"))
    assert review["ok"] is True and review["attempts"] == 2


async def test_a_blank_colouring_page_is_rejected_without_asking_the_reviewer(raw_db, google_user, client, key,
                                                                               engine):
    user = await google_user()
    await written_tome(client, key, user, engine, {**SECTION, "blocks": [SECTION["blocks"][1]]})
    images = FakeImages(png())  # all white
    vision = FakeVision()

    await illustrate_all(engine, images, vision)

    assert len(images.calls) == 2 and vision.calls == 0
    assert "blank" in images.calls[1]["prompt"].lower()


async def test_without_an_image_model_the_job_fails_and_the_section_stays(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)

    await illustrate_all(engine, None)

    errors = await raw_db.fetch("select status, error from public.generation_jobs where series_id = $1"
                                " and kind = 'illustration'", sid)
    assert {(r["status"], json.loads(r["error"])["code"]) for r in errors} == {("failed", "not_configured")}
    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "ready"


async def test_an_export_made_before_the_pictures_arrived_is_stale(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)
    await client.post(f"/api/series/{sid}/exports", json={}, headers=bearer(key, user))

    before = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()["latest_export"]
    await illustrate_all(engine, FakeImages())
    after = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()["latest_export"]

    assert before["stale"] is False and after["stale"] is True
