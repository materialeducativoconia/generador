"""Phase 2: once a tome is written, the Art director styles every picture and the Illustrator paints them in sheets."""

import json
import shutil

import pytest

from app.images import GeneratedImage
from app.vision import Review
from tests.db.test_covers import FakeStorage
from tests.db.test_jobs import OUTLINE, engine, new_tome, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM
from tests.test_artwork import grid
from tests.test_illustrator import png

LINE_ART = png(lambda d: d.ellipse((60, 60, 340, 340), outline="black", width=10))
ART = {"style": "Soft rounded flat vector, thick friendly lines", "characters": [
    {"name": "Rito", "look": "a plush mouse with an orange scarf"}], "prompts": {"1:b2": "Rito smiles next to a cow"}}


def image(id_, subject, kind="line_art", size="full"):
    return {"id": id_, "type": "image", "kind": kind, "subject": subject, "size": size}


SECTION = {"schema_version": 1, "summary": "Animales", "blocks": [
    {"id": "b1", "type": "heading", "level": 2, "text": "La granja"},
    image("b2", "Una vaca feliz"), image("b3", "un granero rojo", kind="illustration", size="half")]}
FIVE = {**SECTION, "blocks": [image(f"x{i}", s) for i, s in enumerate(
    ["una vaca", "un cerdo", "una gallina", "un pato", "un caballo"])]}


class FakeImages:
    """Answers a 2x2 prompt with a 2x2 sheet, anything else with one picture."""

    def __init__(self, single=LINE_ART):
        self.calls, self.single = [], single

    async def generate(self, prompt, *, references=(), aspect_ratio="3:4", resolution="1K"):
        self.calls.append({"prompt": prompt, "references": list(references), "aspect_ratio": aspect_ratio,
                           "resolution": resolution})
        data = grid(2, 2) if "2x2 grid" in prompt else self.single
        return GeneratedImage(data=data, media_type="image/png", model="fake-image", cost_usd=0.04)


class FakeVision:
    def __init__(self, *sheets):
        self.sheets = list(sheets)
        self.calls = 0

    async def review_sheet(self, image, subjects, *, kind):
        self.calls += 1
        verdicts = self.sheets.pop(0) if self.sheets else []
        return [verdicts[i] if i < len(verdicts) else Review(ok=True) for i in range(len(subjects))]


@pytest.fixture(autouse=True)
async def empty_library(raw_db):
    await raw_db.execute("delete from public.assets")


async def written_tome(client, key, user, engine, section=SECTION):
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps({**OUTLINE, "sections": OUTLINE["sections"][:1]})))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    await run_next(engine, ScriptedLLM(json.dumps(section)))
    return sid


async def illustrate(engine, images, vision=None, storage=None, art=ART):
    storage = storage or FakeStorage()
    job = await run_next(engine, ScriptedLLM(json.dumps(art)), images=images, vision=vision or FakeVision(),
                         storage=storage)
    assert job["kind"] == "illustration"
    return storage


async def _value(v):
    return v


async def test_a_finished_tome_queues_one_illustration_job(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)

    jobs = await raw_db.fetch("select id from public.generation_jobs where series_id = $1 and kind = 'illustration'",
                              sid)
    assert len(jobs) == 1


async def test_pictures_are_painted_four_per_call_in_one_style(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine, FIVE)
    images = FakeImages()

    await illustrate(engine, images)

    assert len(images.calls) == 2  # 4 in a 2x2 sheet + 1 alone, instead of 5 calls
    sheet = next(c for c in images.calls if "2x2 grid" in c["prompt"])
    assert sheet["resolution"] == "2K" and "orange scarf" in sheet["prompt"] and "Soft rounded" in sheet["prompt"]
    content = json.loads(await raw_db.fetchval("select content_json from public.lessons where series_id = $1", sid))
    assert all(b["asset_id"] for b in content["blocks"])
    costs = await raw_db.fetch("select cost_usd from public.assets order by cost_usd")
    assert [float(r["cost_usd"]) for r in costs] == [0.01] * 4 + [0.04]  # a sheet's price is shared by its panels
    art = json.loads(await raw_db.fetchval("select art from public.series where id = $1", sid))
    assert art["characters"][0]["name"] == "Rito"


@pytest.mark.skipif(shutil.which("potrace") is None, reason="potrace not installed")
async def test_colouring_pages_are_stored_as_vectors_and_colour_art_is_painted_at_4k(raw_db, google_user, client,
                                                                                     key, engine):
    user = await google_user()
    await written_tome(client, key, user, engine, {**SECTION, "blocks": [
        image("a", "una vaca"), image("b", "un granero", kind="illustration"), image("c", "un tractor",
                                                                                   kind="illustration")]})
    images = FakeImages()

    storage = await illustrate(engine, images)

    assert sorted(c["resolution"] for c in images.calls) == ["1K", "4K"]
    stored = {r["kind"]: (r["media_type"], r["storage_key"]) for r in
              await raw_db.fetch("select kind, media_type, storage_key from public.assets")}
    assert stored["line_art"][0] == "image/svg+xml" and stored["line_art"][1].endswith(".svg")
    assert storage.uploads[("images", stored["line_art"][1])][0].startswith(b"<?xml")


async def test_the_cover_is_the_style_reference(raw_db, google_user, client, key, engine):
    from tests.test_covers import PNG

    user = await google_user()
    sid = await written_tome(client, key, user, engine)
    storage = FakeStorage()
    storage.download = lambda key_, bucket="covers": _value(PNG)
    await raw_db.execute("""update public.series set cover_key = 'c.png', cover = '{"concept": "Un ratón"}'
                             where id = $1""", sid)
    images = FakeImages()

    await illustrate(engine, images, storage=storage)

    assert images.calls and all(len(c["references"]) == 1 for c in images.calls)
    assert all(c["references"][0].startswith(b"\xff\xd8") for c in images.calls)  # a light JPEG, not the 4K file


async def test_repeated_subjects_are_painted_once(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine, {**SECTION, "blocks": [
        image("a", "Una vaca feliz"), image("b", "la vaca feliz.")]})
    images = FakeImages()

    await illustrate(engine, images)

    content = json.loads(await raw_db.fetchval("select content_json from public.lessons where series_id = $1", sid))
    assert len(images.calls) == 1 and content["blocks"][0]["asset_id"] == content["blocks"][1]["asset_id"]


async def test_only_hard_failures_are_repainted_together(raw_db, google_user, client, key, engine):
    user = await google_user()
    await written_tome(client, key, user, engine, FIVE)
    vision = FakeVision([Review(ok=True), Review(ok=False, has_text=True, issues="aparece la palabra CERDO"),
                         Review(ok=False, issues="podría tener más detalle")])
    images = FakeImages()

    await illustrate(engine, images, vision)

    assert len(images.calls) == 3  # two sheets, then one repaint for the panel with text only
    assert "aparece la palabra CERDO" in images.calls[2]["prompt"]


async def test_illustrated_pictures_show_up_in_the_api(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)
    progress = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()
    assert progress["images"] == {"total": 2, "done": 0, "active": 2, "failed": 0}

    storage = await illustrate(engine, FakeImages())

    client._transport.app.state.storage = storage
    detail = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()
    asset_id = detail["lessons"][0]["content_json"]["blocks"][1]["asset_id"]
    assert detail["assets"][asset_id].startswith("https://storage.test/images/")
    progress = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()
    assert progress["images"] == {"total": 2, "done": 2, "active": 0, "failed": 0}


async def test_without_an_image_model_the_job_fails_and_the_tome_stays_ready(raw_db, google_user, client, key,
                                                                            engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)

    await run_next(engine, ScriptedLLM(), images=None)

    job = await raw_db.fetchrow("select status, error from public.generation_jobs where series_id = $1"
                                " and kind = 'illustration'", sid)
    assert job["status"] == "failed" and json.loads(job["error"])["code"] == "not_configured"
    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "ready"


async def test_an_export_made_before_the_pictures_arrived_is_stale(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await written_tome(client, key, user, engine)
    await client.post(f"/api/series/{sid}/exports", json={}, headers=bearer(key, user))

    before = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()["latest_export"]
    await illustrate(engine, FakeImages())
    after = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()["latest_export"]

    assert before["stale"] is False and after["stale"] is True
