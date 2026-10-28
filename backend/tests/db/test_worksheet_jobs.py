"""Phase 8: literacy tomes — decodable text checked in the lesson job, word pictures from a shared library."""

import io
import json

from PIL import Image, ImageDraw

from app.images import GeneratedImage
from tests.db.test_covers import FakeStorage
from tests.db.test_illustrations import FakeVision, empty_library  # noqa: F401  (autouse fixture)
from tests.db.test_jobs import engine, new_tome, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM

METHOD = {"title": "Método de la M", "genre": "worksheets", "known_letters": ["a", "e", "i", "o", "u"],
          "sections": [{"title": "La m", "objectives": ["Leer con m"], "key_points": ["ma me mi mo mu"],
                        "letters": ["m"]}]}
WORDS = ["mamá", "mesa", "mimo", "moto", "mula", "mono"]
FICHAS = {"schema_version": 1, "blocks": [
    {"id": "c", "type": "syllable_chart", "letter": "m",
     "words": [{"word": w, "syllable": w[:2]} for w in WORDS]},
    {"id": "r", "type": "reading", "sentences": [{"text": "Mi mamá me ama.", "picture": "mamá"}]}]}
SLOPPY = {**FICHAS, "blocks": [*FICHAS["blocks"], {"id": "d", "type": "dictation", "words": ["mamá", "sopa"]}]}


def grid_png(n: int) -> bytes:
    im = Image.new("RGB", (200 * n, 200 * n), "white")
    d = ImageDraw.Draw(im)
    for c in range(n):
        for r in range(n):
            d.ellipse((c * 200 + 30, r * 200 + 30, c * 200 + 170, r * 200 + 170), outline="black", width=6)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


class GridImages:
    def __init__(self):
        self.calls = []

    async def generate(self, prompt, *, references=(), aspect_ratio="3:4", resolution="1K"):
        self.calls.append({"prompt": prompt, "references": list(references), "resolution": resolution})
        n = next((k for k in (4, 3, 2) if f"{k}x{k} grid" in prompt), 1)
        return GeneratedImage(data=grid_png(n), media_type="image/png", model="fake-image", cost_usd=0.038)


async def method_tome(client, key, user, engine, *replies):
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(METHOD)))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    await run_next(engine, ScriptedLLM(*(json.dumps(r) for r in replies)))
    return sid


async def test_the_writer_gets_a_second_chance_at_undecodable_words(raw_db, google_user, client, key, engine):
    user = await google_user()
    llm = ScriptedLLM(json.dumps(SLOPPY), json.dumps(FICHAS))
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(METHOD)))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))

    await run_next(engine, llm)

    assert "Letras permitidas" in llm.calls[0][-1]["content"] and "«sopa»" in llm.calls[1][-1]["content"]
    row = await raw_db.fetchrow("select letters, content_json, review from public.lessons where series_id = $1", sid)
    assert json.loads(row["letters"]) == ["m"] and row["review"] is None
    assert [b["id"] for b in json.loads(row["content_json"])["blocks"]] == ["c", "r"]


async def test_words_still_undecodable_are_flagged_on_the_quality_card(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await method_tome(client, key, user, engine, SLOPPY, SLOPPY)

    card = (await client.get(f"/api/series/{sid}/quality", headers=bearer(key, user))).json()

    assert any("letras que el niño aún no conoce" in r for r in card["reasons"]) and card["verdict"] == "revisar"
    assert any("sopa" in i["issue"] for i in card["text"]["issues"])


async def test_worksheet_words_get_pictures_from_one_shared_sheet(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await method_tome(client, key, user, engine, FICHAS)
    images = GridImages()

    storage = FakeStorage()
    job = await run_next(engine, ScriptedLLM(), images=images, vision=FakeVision(), storage=storage)

    assert job["kind"] == "illustration"
    assert len(images.calls) == 1 and "3x3 grid" in images.calls[0]["prompt"]  # six words, one call, no art director
    assert images.calls[0]["references"] == [] and images.calls[0]["resolution"] == "1K"
    blocks = {b["id"]: b for b in json.loads(
        await raw_db.fetchval("select content_json from public.lessons where series_id = $1", sid))["blocks"]}
    assert set(blocks["c"]["pictures"]) == set(WORDS)
    assert blocks["r"]["pictures"]["mamá"] == blocks["c"]["pictures"]["mamá"]
    kinds = await raw_db.fetch("select distinct kind, style_key, media_type from public.assets")
    assert [tuple(k) for k in kinds] in ([("icon", "icon", "image/svg+xml")], [("icon", "icon", "image/png")])

    client._transport.app.state.storage = storage
    lesson = (await client.get(f"/api/series/{sid}", headers=bearer(key, user))).json()["lessons"][0]
    assert lesson["diagrams"]["c"].count('<image href="https://storage.test/images/') == 6


async def test_another_tome_reuses_the_word_pictures(raw_db, google_user, client, key, engine):
    user = await google_user()
    await method_tome(client, key, user, engine, FICHAS)
    await run_next(engine, ScriptedLLM(), images=GridImages(), vision=FakeVision(), storage=FakeStorage())
    second = await method_tome(client, key, user, engine, FICHAS)
    images = GridImages()

    await run_next(engine, ScriptedLLM(), images=images, storage=FakeStorage())

    content = json.loads(await raw_db.fetchval("select content_json from public.lessons where series_id = $1", second))
    assert images.calls == [] and len(content["blocks"][0]["pictures"]) == 6
