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
