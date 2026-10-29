"""The worker's job handlers against the local Supabase database, with DeepSeek replaced by a script."""

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.jobs import Deps, claim_job, process_job, reap_stale_jobs
from app.llm import UpstreamError
from tests.db.conftest import LOCAL_SUPABASE_DB_URL
from tests.db.test_me import bearer
from tests.db.test_series_api import NEW_TOME
from tests.fakes import ScriptedLLM

OUTLINE = {
    "title": "Piano desde cero",
    "genre": "tutorial",
    "style_notes": "Claro",
    "sections": [{"title": t, "objectives": ["Tocar"], "key_points": ["Do"]} for t in ("Postura", "Do", "Melodía")],
}
SECTION = {"schema_version": 1, "summary": "Do central", "blocks": [
    {"id": "b1", "type": "heading", "level": 2, "text": "El Do central"},
    {"id": "b2", "type": "keyboard", "start": "C4", "highlight": ["C4"]},
]}


class FailingLLM:
    async def complete(self, *args, **kwargs):
        raise UpstreamError("rate_limited", "429", retry_after=1)


@pytest.fixture
async def engine():
    engine = create_async_engine(LOCAL_SUPABASE_DB_URL.replace("postgresql://", "postgresql+asyncpg://"))
    yield engine
    await engine.dispose()


async def run_next(engine, llm, *, covers=False, **deps):
    if not covers:  # the cover agent runs alongside; most tests are about the text pipeline
        async with engine.begin() as conn:
            await conn.execute(text("update public.generation_jobs set status = 'cancelled'"
                                    " where kind = 'cover' and status = 'queued'"))
    job = await claim_job(engine, "test-worker")
    assert job is not None
    deps.setdefault("edit", False)  # the Editor has its own tests; elsewhere one scripted reply per section
    await process_job(Deps(engine=engine, llm=llm, storage=deps.pop("storage", None), **deps), job)
    return job


async def new_tome(client, key, user):
    response = await client.post("/api/series", json=NEW_TOME, headers=bearer(key, user))
    return uuid.UUID(response.json()["series"]["id"])


async def test_architect_job_turns_the_outline_into_sections(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)

    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))

    series = await raw_db.fetchrow("select status, title, genre, lesson_count from public.series where id = $1", sid)
    assert dict(series) == {"status": "outline_ready", "title": "Piano desde cero", "genre": "tutorial",
                            "lesson_count": 3}
    titles = await raw_db.fetch("select title from public.lessons where series_id = $1 order by position", sid)
    assert [r["title"] for r in titles] == ["Postura", "Do", "Melodía"]
    log = await raw_db.fetchrow("select outcome, prompt_version from public.generation_logs where series_id = $1", sid)
    assert dict(log) == {"outcome": "ok", "prompt_version": "architect@5"}


async def test_writer_jobs_fill_sections_and_finish_the_tome(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))

    for _ in range(3):
        await run_next(engine, ScriptedLLM(json.dumps(SECTION)))

    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "ready"
    lesson = await raw_db.fetchrow(
        "select status, content_version, content_json from public.lessons where series_id = $1 and position = 1", sid)
    assert lesson["status"] == "generated" and lesson["content_version"] == 1
    assert json.loads(lesson["content_json"])["blocks"][1]["type"] == "keyboard"


async def test_writer_prompt_includes_the_approved_outline(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    llm = ScriptedLLM(json.dumps(SECTION))

    await run_next(engine, llm)

    assert "Melodía" in llm.calls[0][1]["content"]  # the whole outline travels in the shared prefix
    assert "sección 1: Postura" in llm.calls[0][-1]["content"]


async def test_rate_limited_job_is_requeued_with_backoff(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)

    job = await run_next(engine, FailingLLM())

    row = await raw_db.fetchrow("select status, attempts, run_after > now() as later from public.generation_jobs"
                                " where id = $1", job["id"])
    assert dict(row) == {"status": "queued", "attempts": 1, "later": True}
    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "outlining"


async def test_invalid_output_twice_fails_the_outline(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)

    await run_next(engine, ScriptedLLM("no", "tampoco"))

    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "outline_failed"
    error = await raw_db.fetchval("select error from public.generation_jobs where series_id = $1", sid)
    assert json.loads(error)["code"] == "invalid_output"
    assert await raw_db.fetchval("select count(*) from public.generation_logs where series_id = $1", sid) == 2


async def test_stale_running_jobs_are_reaped(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)
    await raw_db.execute("update public.generation_jobs set status = 'running', locked_at = now() - interval '1 hour'"
                         " where series_id = $1", sid)

    assert await reap_stale_jobs(engine, lease_seconds=600) >= 1
    assert await raw_db.fetchval("select status from public.generation_jobs where series_id = $1", sid) == "queued"


async def test_read_and_regenerate_a_section(raw_db, google_user, client, key, engine):
    user = await google_user()
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    for _ in range(3):
        await run_next(engine, ScriptedLLM(json.dumps(SECTION)))
    lesson_id = await raw_db.fetchval("select id from public.lessons where series_id = $1 and position = 2", sid)

    lesson = (await client.get(f"/api/lessons/{lesson_id}", headers=bearer(key, user))).json()
    assert lesson["content_json"]["blocks"][0]["text"] == "El Do central"

    response = await client.post(f"/api/lessons/{lesson_id}/regenerate", json={"instructions": "Más ejercicios"},
                                 headers=bearer(key, user))
    assert response.status_code == 202
    llm = ScriptedLLM(json.dumps(SECTION))
    await run_next(engine, llm)
    assert "Más ejercicios" in llm.calls[0][1]["content"]
    assert await raw_db.fetchval("select content_version from public.lessons where id = $1", lesson_id) == 2
    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "ready"


async def test_someone_elses_section_is_404(raw_db, google_user, client, key, engine):
    marta, pedro = await google_user(), await google_user()
    sid = await new_tome(client, key, marta)
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    lesson_id = await raw_db.fetchval("select id from public.lessons where series_id = $1 limit 1", sid)

    assert (await client.get(f"/api/lessons/{lesson_id}", headers=bearer(key, pedro))).status_code == 404


async def test_sections_finishing_at_once_still_finish_the_tome(raw_db, google_user, client, key, engine):
    # Writers run in parallel; each save must see the others' commits or the tome stays "generating".
    import asyncio

    user = await google_user()
    sid = await new_tome(client, key, user)
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=bearer(key, user))
    async with engine.begin() as conn:
        await conn.execute(text("update public.generation_jobs set status = 'cancelled' where kind = 'cover'"))
    jobs = [await claim_job(engine, "test-worker") for _ in range(3)]
    barrier = asyncio.Barrier(3)

    class TogetherLLM(ScriptedLLM):
        async def complete(self, *args, **kwargs):
            await barrier.wait()
            return await super().complete(*args, **kwargs)

    await asyncio.gather(*(process_job(Deps(engine=engine, llm=TogetherLLM(json.dumps(SECTION)), storage=None, edit=False), j)
                           for j in jobs))

    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "ready"
