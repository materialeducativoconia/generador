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

    async def download(self, key, bucket="covers"):
        return self.uploads[(bucket, key)][0]


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
    assert [r["prompt_version"] for r in logs] == ["designer@4", "cover@6"]

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


async def test_a_picked_house_style_paints_the_cover_with_its_reference_and_finish(raw_db, google_user, client, key,
                                                                                  engine):
    from tests.db.test_jobs import NEW_TOME

    user = await google_user()
    created = await client.post("/api/series", json={**NEW_TOME, "house_style": "gouache"}, headers=bearer(key, user))
    sid = created.json()["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)), covers=True)
    images, storage = FakeImages(), FakeStorage()
    storage.uploads[("images", "style-lab/r/gouache.jpg")] = (PNG, "image/jpeg")
    await raw_db.execute("""insert into public.style_samples (run, style, subject, status, key, chosen)
                            values (gen_random_uuid(), 'gouache', 'x', 'done', 'style-lab/r/gouache.jpg', true)""")

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN)), covers=True, images=images,
                   storage=storage, references=fake_references)

    design = json.loads(await raw_db.fetchval("select design from public.series where id = $1", sid))
    assert design["house_style"] == "gouache" and "risograph" in design["art_style"]
    call = images.calls[0]
    assert len(call["references"]) == 2 and "style reference" in call["prompt"]
    await raw_db.execute("delete from public.style_samples where key = 'style-lab/r/gouache.jpg'")


async def test_visitors_preview_only_the_free_house_styles(google_user, client, key):
    from tests.db.test_jobs import NEW_TOME

    anon = await google_user(anonymous=True)
    paid_only = await client.post("/api/series", json={**NEW_TOME, "page_count": 2, "section_count": 1,
                                                       "house_style": "collage"}, headers=bearer(key, anon))
    assert paid_only.status_code == 403 and paid_only.json()["error"]["code"] == "plan_required"
    free = await client.post("/api/series", json={**NEW_TOME, "page_count": 2, "section_count": 1,
                                                  "house_style": "acuarela"}, headers=bearer(key, anon))
    assert free.status_code == 202


class Reader:
    """The Reviewer reading the painted title: one reading per painting."""

    def __init__(self, *readings):
        self.readings = list(readings)

    async def read_text(self, image):
        return self.readings.pop(0), 0.001


async def _picture_book(raw_db, client, key, user, engine, monkeypatch):
    async def no_cast(*args, **kwargs):  # casting has its own tests
        return [], 0.0
    monkeypatch.setattr("app.casting.cast_tome", no_cast)
    sid = await outlined_tome(client, key, user, engine)
    await raw_db.execute("update public.series set genre = 'picture_book' where id = $1", sid)
    return sid, await raw_db.fetchval("select title from public.series where id = $1", sid)


async def test_a_picture_book_cover_has_its_title_painted_in_and_read_back(raw_db, google_user, client, key, engine,
                                                                               monkeypatch):
    user = await google_user()
    sid, title = await _picture_book(raw_db, client, key, user, engine, monkeypatch)
    images = FakeImages()

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN)), covers=True, images=images,
                   storage=FakeStorage(), references=fake_references, vision=Reader(title.upper()))

    assert len(images.calls) == 1 and f"«{title}»" in images.calls[0]["prompt"]
    assert json.loads(await raw_db.fetchval("select cover from public.series where id = $1", sid))["lettered"] == title
    client._transport.app.state.storage = FakeStorage()
    tome = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    assert tome["cover_lettered"] is True
    listed = (await client.get("/api/series", headers=bearer(key, user))).json()["series"]
    assert [t["cover_lettered"] for t in listed if t["id"] == str(sid)] == [True]  # the library card too
    # A new title would leave the old one painted on the cover: it asks first, then paints a new cover.
    refused = await client.patch(f"/api/series/{sid}/title", json={"title": "Otro título"}, headers=bearer(key, user))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "lettered_cover"
    renamed = await client.patch(f"/api/series/{sid}/title", json={"title": "Otro título", "repaint": True},
                                 headers=bearer(key, user))
    assert renamed.status_code == 200
    assert await raw_db.fetchval("select count(*) from public.generation_jobs where series_id = $1 and kind = 'cover'"
                                 " and status = 'queued'", sid) == 1


async def test_a_title_painted_wrong_twice_falls_back_to_art_without_words(raw_db, google_user, client, key, engine,
                                                                               monkeypatch):
    user = await google_user()
    sid, title = await _picture_book(raw_db, client, key, user, engine, monkeypatch)
    images = FakeImages()

    await run_next(engine, ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN)), covers=True, images=images,
                   storage=FakeStorage(), references=fake_references, vision=Reader("Titlo mal", "Otra cosa"))

    assert len(images.calls) == 3
    assert "lettered «Titlo mal»" in images.calls[1]["prompt"] and "no text" in images.calls[2]["prompt"].lower()
    cover = json.loads(await raw_db.fetchval("select cover from public.series where id = $1", sid))
    assert cover["lettered"] is None and cover["cost_usd"] == round(3 * 0.04 + 2 * 0.001, 4)


async def test_a_new_cover_of_a_written_story_puts_its_hero_in_front_as_the_plates_draw_her(
        raw_db, google_user, client, key, engine, monkeypatch):
    user = await google_user()
    sid, title = await _picture_book(raw_db, client, key, user, engine, monkeypatch)
    await raw_db.execute("update public.series set genre = 'story_book', plan = coalesce(plan, '{}'::jsonb)"
                         " || '{\"story\": {\"protagonist\": \"Lucía, una niña curiosa\"}}' where id = $1", sid)
    asset = await raw_db.fetchval(
        """insert into public.assets (kind, subject, subject_norm, style_key, storage_key, media_type, created_by, aspect)
           values ('illustration', 'Lucía', 'lucia', 'tome:x', 'lucia.png', 'image/png', $1, '3:4') returning id""", user)
    await raw_db.execute("update public.lessons set content_json = $2 where series_id = $1 and position = 1", sid,
                         json.dumps({"blocks": [{"id": "p1", "type": "image", "size": "plate", "asset_id": str(asset)}]}))
    storage = FakeStorage()
    storage.uploads[("images", "lucia.png")] = (PNG, "image/png")
    images, llm = FakeImages(), ScriptedLLM(json.dumps(DESIGN), json.dumps(PLAN))

    await run_next(engine, llm, covers=True, images=images, storage=storage, references=fake_references)

    assert "Lucía, una niña curiosa" in llm.calls[-1][1]["content"]
    assert len(images.calls[0]["references"]) == 2 and "pages of this very book" in images.calls[0]["prompt"]
