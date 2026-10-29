import json
import subprocess
import uuid

import httpx
import pytest

from app.jobs import Deps
from app.storage import Storage
from tests.db.test_jobs import OUTLINE, SECTION, engine, new_tome, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.fakes import ScriptedLLM


@pytest.fixture(scope="session")
def storage():
    try:
        env = subprocess.run(["supabase", "status", "-o", "env"], capture_output=True, text=True, timeout=30,
                             cwd="..").stdout
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("supabase CLI not available")
    values = dict(line.split("=", 1) for line in env.splitlines() if "=" in line)
    if "API_URL" not in values:
        pytest.skip("local Supabase not running")
    return Storage(values["API_URL"].strip('"'), values["SERVICE_ROLE_KEY"].strip('"'))


@pytest.fixture
def client_with_storage(client, storage):
    client._transport.app.state.storage = storage
    return client


async def ready_tome(client, key, user, engine):
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    for _ in range(3):
        await run_next(engine, ScriptedLLM(json.dumps(SECTION)))
    return sid


async def test_export_renders_uploads_and_serves_a_signed_pdf(raw_db, google_user, client_with_storage, key,
                                                             engine, storage):
    client = client_with_storage
    user = await google_user()
    sid = await ready_tome(client, key, user, engine)

    created = await client.post(f"/api/series/{sid}/exports", json={"paper": "A4", "include_answer_key": True},
                                headers=bearer(key, user))
    assert created.status_code == 202, created.text
    export_id = created.json()["export"]["id"]

    job = await run_next_with_storage(engine, storage)
    assert job["kind"] == "pdf_export"

    status = (await client.get(f"/api/exports/{export_id}", headers=bearer(key, user))).json()
    assert status["status"] == "succeeded" and status["page_count"] >= 4

    link = await client.get(f"/api/exports/{export_id}/file", headers=bearer(key, user))
    assert link.status_code == 200
    async with httpx.AsyncClient() as http:
        pdf = await http.get(link.json()["url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    await storage.delete(status["storage_key"])


async def test_word_export_uploads_an_editable_docx(raw_db, google_user, client_with_storage, key, engine,
                                                    storage):
    client = client_with_storage
    user = await google_user()
    sid = await ready_tome(client, key, user, engine)

    created = await client.post(f"/api/series/{sid}/exports", json={"format": "docx", "edition": "print"},
                                headers=bearer(key, user))
    export_id = created.json()["export"]["id"]
    await run_next_with_storage(engine, storage)

    status = (await client.get(f"/api/exports/{export_id}", headers=bearer(key, user))).json()
    assert status["status"] == "succeeded" and status["storage_key"].endswith(".docx")
    assert status["options"]["edition"] == "digital"  # Word has no print edition
    link = (await client.get(f"/api/exports/{export_id}/file", headers=bearer(key, user))).json()["url"]
    assert "download=" in link and ".docx" in link
    async with httpx.AsyncClient() as http:
        docx = await http.get(link)
    assert docx.status_code == 200 and docx.content.startswith(b"PK")  # a zip, as every .docx is
    progress = (await client.get(f"/api/series/{sid}/progress", headers=bearer(key, user))).json()
    assert progress["latest_export"] is None  # the PDF panel reopens on PDFs only
    await storage.delete(status["storage_key"])


async def test_export_requires_a_finished_tome(google_user, client_with_storage, key):
    user = await google_user()
    sid = await new_tome(client_with_storage, key, user)

    response = await client_with_storage.post(f"/api/series/{sid}/exports", json={}, headers=bearer(key, user))

    assert response.status_code == 409


async def test_same_content_and_options_reuse_the_previous_export(raw_db, google_user, client_with_storage, key,
                                                                 engine, storage):
    client = client_with_storage
    user = await google_user()
    sid = await ready_tome(client, key, user, engine)
    first = await client.post(f"/api/series/{sid}/exports", json={}, headers=bearer(key, user))
    await run_next_with_storage(engine, storage)

    again = await client.post(f"/api/series/{sid}/exports", json={}, headers=bearer(key, user))

    assert again.status_code == 200
    assert again.json()["export"]["id"] == first.json()["export"]["id"]
    key_ = await raw_db.fetchval("select storage_key from public.exports where id = $1",
                                 uuid.UUID(first.json()["export"]["id"]))
    await storage.delete(key_)


async def run_next_with_storage(engine, storage):
    from app.jobs import claim_job, process_job

    job = await claim_job(engine, "test-worker")
    await process_job(Deps(engine=engine, llm=None, storage=storage), job)
    return job


async def test_export_puts_the_generated_cover_on_page_one(raw_db, google_user, client_with_storage, key, engine,
                                                          storage):
    import io

    from pypdf import PdfReader

    from tests.test_covers import PNG

    client = client_with_storage
    user = await google_user()
    sid = await ready_tome(client, key, user, engine)
    before = await client.post(f"/api/series/{sid}/exports", json={}, headers=bearer(key, user))
    cover_key = f"{user}/{sid}/test-cover.png"
    await storage.upload(cover_key, PNG, "image/png", bucket="covers")
    await raw_db.execute("""update public.series set cover_key = $2, cover = '{"palette": ["#FFF4E0", "#1E3A5F", "#F2994A"]}'
                             where id = $1""", sid, cover_key)

    created = await client.post(f"/api/series/{sid}/exports", json={}, headers=bearer(key, user))
    await run_next_with_storage(engine, storage)  # the export queued before the cover
    await run_next_with_storage(engine, storage)

    assert created.json()["export"]["id"] != before.json()["export"]["id"]  # a new cover is new content
    status = (await client.get(f"/api/exports/{created.json()['export']['id']}", headers=bearer(key, user))).json()
    link = (await client.get(f"/api/exports/{status['id']}/file", headers=bearer(key, user))).json()["url"]
    async with httpx.AsyncClient() as http:
        pdf = (await http.get(link)).content
    assert PdfReader(io.BytesIO(pdf)).pages[0].images


async def test_export_prints_the_illustrations(raw_db, google_user, client_with_storage, key, engine, storage):
    import io

    from pypdf import PdfReader

    from tests.db.test_illustrations import ART, LINE_ART, SECTION, FakeImages, FakeVision, written_tome

    client = client_with_storage
    await raw_db.execute("delete from public.assets where subject_norm = 'vaca feliz'")
    user = await google_user()
    sid = await written_tome(client, key, user, engine, {**SECTION, "blocks": [SECTION["blocks"][1]]})
    await run_next(engine, ScriptedLLM(json.dumps(ART)), images=FakeImages(LINE_ART), vision=FakeVision(),
                   storage=storage)

    created = await client.post(f"/api/series/{sid}/exports", json={}, headers=bearer(key, user))
    await run_next_with_storage(engine, storage)

    link = (await client.get(f"/api/exports/{created.json()['export']['id']}/file", headers=bearer(key, user))).json()
    async with httpx.AsyncClient() as http:
        pdf = PdfReader(io.BytesIO((await http.get(link["url"])).content))
    text = "".join(page.extract_text() for page in pdf.pages)
    assert "Dibujo para colorear" not in text  # the picture printed, not its placeholder
    media = await raw_db.fetchval("select media_type from public.assets where subject_norm = 'vaca feliz'")
    assert media == "image/svg+xml" or any(page.images for page in pdf.pages[1:])  # vector when potrace is there


async def test_print_edition_ships_a_cover_wrap_and_a_preflight(raw_db, google_user, client_with_storage, key, engine,
                                                               storage):
    import io

    from pypdf import PdfReader

    client = client_with_storage
    user = await google_user()
    sid = await ready_tome(client, key, user, engine)

    created = await client.post(f"/api/series/{sid}/exports", json={"paper": "8x10", "edition": "print"},
                                headers=bearer(key, user))
    await run_next_with_storage(engine, storage)

    status = (await client.get(f"/api/exports/{created.json()['export']['id']}", headers=bearer(key, user))).json()
    assert status["preflight"]["rating"] in {"lista", "aceptable", "baja"}
    assert any("24 páginas" in i for i in status["preflight"]["issues"])  # a 3-section test tome is short
    link = (await client.get(status["cover_download_url"], headers=bearer(key, user))).json()["url"]
    async with httpx.AsyncClient() as http:
        wrap = PdfReader(io.BytesIO((await http.get(link)).content))
    assert len(wrap.pages) == 1 and float(wrap.pages[0].mediabox.width) > 2 * 576  # back + spine + front
    await storage.delete(status["storage_key"])
    await storage.delete(status["cover_storage_key"])
