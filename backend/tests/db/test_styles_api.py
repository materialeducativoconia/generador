"""Phase 9: the style library — upload references, the style job reads them, tomes use the result."""

import json

from tests.db.test_covers import FakeImages, FakeStorage, fake_references
from tests.db.test_jobs import OUTLINE, engine, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.db.test_series_api import NEW_TOME
from tests.fakes import ScriptedLLM
from tests.test_covers import PLAN
from tests.test_styles import reference_pdf
from tests.test_themes import DESIGN

READING = {"best_pages": [2, 5], "score": 8, "palette": ["#FFFFFF", "#222222", "#E8762C"],
           "heading_look": "script", "frame": "dashed", "ornament": "estrellas", "color_use": "bw",
           "illustration_style": "thick black outline clip-art", "traits": ["Pestaña «Ficha N»"],
           "suits": "Cuadernillos de lectoescritura para preescolar"}


class LibraryStorage(FakeStorage):
    def __init__(self, files=None):
        super().__init__()
        self.files, self.deleted = files or {}, []

    async def upload_url(self, key, bucket):
        return f"https://storage.test/upload/{bucket}/{key}?token=t"

    async def download_private(self, key, bucket):
        return self.files[key]

    async def signed_urls(self, keys, bucket, expires_in=3600):
        return {k: f"https://storage.test/signed/{bucket}/{k}" for k in keys}

    async def delete(self, key, bucket="exports"):
        self.deleted.append((bucket, key))


class StyleVision:
    def __init__(self):
        self.calls = []

    async def analyze_style(self, sheet, pages):
        self.calls.append(pages)
        return READING, 0.004


async def uploaded_style(client, key, user, engine, storage):
    client._transport.app.state.storage = storage
    created = (await client.post("/api/styles", json={"name": "Método 20 días", "content_type": "application/pdf",
                                                      "size": 1000}, headers=bearer(key, user))).json()
    sid = created["style"]["id"]
    source = next(iter(k for k in [f"{user}/{sid}/source.pdf"]))
    storage.files[source] = reference_pdf(10)
    await client.post(f"/api/styles/{sid}/analyze", headers=bearer(key, user))
    await run_next(engine, ScriptedLLM(), vision=StyleVision(), storage=storage)
    return created, sid


async def test_an_uploaded_reference_becomes_a_ready_style(raw_db, google_user, client, key, engine):
    user = await google_user()
    storage = LibraryStorage()

    created, sid = await uploaded_style(client, key, user, engine, storage)

    assert created["upload_url"].startswith("https://storage.test/upload/references/")
    listed = (await client.get("/api/styles", headers=bearer(key, user))).json()["styles"]
    assert len(listed) == 1 and listed[0]["status"] == "ready" and listed[0]["score"] == 8
    assert len(listed[0]["previews"]) == 2 and listed[0]["traits"] == ["Pestaña «Ficha N»"]
    design = listed[0]["design"]
    assert design["head_font"] == "Pacifico" and design["frame"] == "dashed" and design["style_id"] == sid
    assert all(("references", f"{user}/{sid}/best-{n}.jpg") in storage.uploads for n in (1, 2))


async def test_other_users_never_see_or_use_a_style(raw_db, google_user, client, key, engine):
    owner, other = await google_user(), await google_user("otra@example.com")
    _, sid = await uploaded_style(client, key, owner, engine, LibraryStorage())

    assert (await client.get("/api/styles", headers=bearer(key, other))).json()["styles"] == []
    assert (await client.delete(f"/api/styles/{sid}", headers=bearer(key, other))).status_code == 404
    tome = (await client.post("/api/series", json={**NEW_TOME, "style_id": sid}, headers=bearer(key, other))).json()
    assert await raw_db.fetchval("select style_id from public.series where id = $1",
                                 tome["series"]["id"]) is None


async def test_a_tome_made_with_a_style_skips_the_designer(raw_db, google_user, client, key, engine):
    user = await google_user()
    _, style = await uploaded_style(client, key, user, engine, LibraryStorage())
    tome = (await client.post("/api/series", json={**NEW_TOME, "style_id": style}, headers=bearer(key, user))).json()
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)), covers=True)
    llm = ScriptedLLM(json.dumps(PLAN))  # only the cover director: no Designer reply scripted

    await run_next(engine, llm, covers=True, images=FakeImages(), storage=FakeStorage(), references=fake_references)

    design = json.loads(await raw_db.fetchval("select design from public.series where id = $1", tome["series"]["id"]))
    assert design["style_id"] == style and design["head_font"] == "Pacifico"
    assert "thick black outline" in llm.calls[0][-1]["content"]


async def test_the_designer_can_pick_a_library_style(raw_db, google_user, client, key, engine):
    user = await google_user()
    _, style = await uploaded_style(client, key, user, engine, LibraryStorage())
    tome = (await client.post("/api/series", json=NEW_TOME, headers=bearer(key, user))).json()
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)), covers=True)
    llm = ScriptedLLM(json.dumps({**DESIGN, "style_id": style}), json.dumps(PLAN))

    await run_next(engine, llm, covers=True, images=FakeImages(), storage=FakeStorage(), references=fake_references)

    assert "Método 20 días" in llm.calls[0][-1]["content"]  # the Designer saw the library
    design = json.loads(await raw_db.fetchval("select design from public.series where id = $1", tome["series"]["id"]))
    assert design["style_id"] == style and design["frame"] == "dashed"


async def test_deleting_a_style_removes_its_files(raw_db, google_user, client, key, engine):
    user = await google_user()
    storage = LibraryStorage()
    _, sid = await uploaded_style(client, key, user, engine, storage)

    response = await client.delete(f"/api/styles/{sid}", headers=bearer(key, user))

    assert response.status_code == 204 and ("references", f"{user}/{sid}/source.pdf") in storage.deleted
    assert (await client.get("/api/styles", headers=bearer(key, user))).json()["styles"] == []
