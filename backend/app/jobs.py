"""Job queue on Postgres (FOR UPDATE SKIP LOCKED) and the handlers the worker runs.

A handler never holds a DB connection while waiting on DeepSeek: claim + commit, call the
model with no connection open, then a second transaction saves the result (ARCHITECTURE.md §5.2b).
"""

import json
import logging
import random
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agents import PROMPT_VERSION, AgentFailed, Attempt, Brief, architect, writer
from app.content import Outline, OutlineSection
from app.llm import LLM, UpstreamAuthError, UpstreamError

log = logging.getLogger("worker")


@dataclass
class Deps:
    engine: AsyncEngine
    llm: LLM
    storage: Any  # app.storage.Storage; only pdf_export uses it


class JobFailed(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


async def claim_job(engine: AsyncEngine, worker_id: str) -> dict | None:
    async with engine.begin() as conn:
        row = (await conn.execute(text(
            """update public.generation_jobs
                  set status = 'running', locked_at = now(), locked_by = :w, attempts = attempts + 1
                where id = (select id from public.generation_jobs
                             where status = 'queued' and run_after <= now()
                             order by run_after for update skip locked limit 1)
            returning id, user_id, series_id, lesson_id, kind, payload, attempts, max_attempts"""
        ), {"w": worker_id})).mappings().one_or_none()
    if row is None:
        return None
    job = dict(row)
    job["payload"] = json.loads(job["payload"]) if isinstance(job["payload"], str) else job["payload"]
    return job


async def reap_stale_jobs(engine: AsyncEngine, lease_seconds: int = 600) -> int:
    """A worker that died mid-job leaves it `running`; give it back to the queue."""
    async with engine.begin() as conn:
        result = await conn.execute(text(
            """update public.generation_jobs set status = 'queued', locked_at = null, locked_by = null
                where status = 'running' and locked_at < now() - make_interval(secs => :lease)"""
        ), {"lease": lease_seconds})
    return result.rowcount


async def process_job(deps: Deps, job: dict) -> None:
    handler = {"outline": _outline, "lesson": _lesson, "pdf_export": _pdf_export}[job["kind"]]
    try:
        await handler(deps, job)
    except UpstreamError as exc:
        if job["attempts"] < job["max_attempts"]:
            delay = exc.retry_after or (2 ** job["attempts"]) + random.uniform(0, 1)
            await _requeue(deps.engine, job, delay)
        else:
            await _fail(deps.engine, job, exc.code, str(exc))
    except UpstreamAuthError as exc:
        # Wrong key or no balance: don't burn attempts, park the job and shout for the operator.
        log.error("DeepSeek auth/billing error, job %s parked: %s", job["id"], exc)
        await _requeue(deps.engine, job, 300, count_attempt=False)
    except (AgentFailed, JobFailed) as exc:
        await _fail(deps.engine, job, exc.code, str(exc))
    except Exception as exc:  # a bug: keep the queue moving and leave a trace
        log.exception("job %s crashed", job["id"])
        if job["attempts"] < job["max_attempts"]:
            await _requeue(deps.engine, job, 30)
        else:
            await _fail(deps.engine, job, "internal_error", f"Error interno: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _outline(deps: Deps, job: dict) -> None:
    async with deps.engine.connect() as conn:
        series = await _series(conn, job["series_id"])
    brief = _brief(series, job["payload"].get("brief"))
    if job["payload"].get("instructions"):
        brief.extra_instructions = "\n".join(filter(None, [brief.extra_instructions,
                                                           f"Rehaz el esquema: {job['payload']['instructions']}"]))
    try:
        result = await architect(deps.llm, brief)
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "architect", exc.attempts)
        raise
    outline = result.value
    async with deps.engine.begin() as conn:
        await _insert_logs(conn, job, "architect", result.attempts)
        await conn.execute(text("delete from public.lessons where series_id = :s"), {"s": job["series_id"]})
        for position, section in enumerate(outline.sections, 1):
            await conn.execute(text(
                """insert into public.lessons (series_id, position, title, objectives, key_points, status)
                   values (:s, :p, :t, cast(:o as jsonb), cast(:k as jsonb), 'pending')"""
            ), {"s": job["series_id"], "p": position, "t": section.title,
                "o": json.dumps(section.objectives), "k": json.dumps(section.key_points)})
        await conn.execute(text(
            """update public.series set title = :t, genre = :g, plan = cast(:plan as jsonb), lesson_count = :n,
                      status = 'outline_ready', version = version + 1 where id = :s"""
        ), {"s": job["series_id"], "t": outline.title, "g": outline.genre, "n": len(outline.sections),
            "plan": json.dumps({"genre": outline.genre, "style_notes": outline.style_notes})})
        await _succeed(conn, job)


async def _lesson(deps: Deps, job: dict) -> None:
    async with deps.engine.begin() as conn:
        series = await _series(conn, job["series_id"])
        lessons = (await conn.execute(text(
            "select id, position, title, objectives, key_points from public.lessons where series_id = :s"
            " order by position"), {"s": job["series_id"]})).mappings().all()
        await conn.execute(text("update public.lessons set status = 'generating' where id = :l"),
                           {"l": job["lesson_id"]})
    position = next(lesson["position"] for lesson in lessons if lesson["id"] == job["lesson_id"])
    outline = Outline(
        title=series["title"] or series["topic"],
        genre=series["genre"] or "lesson_series",
        style_notes=(_json(series["plan"]) or {}).get("style_notes", ""),
        sections=[OutlineSection(title=lesson["title"], objectives=_json(lesson["objectives"]),
                                 key_points=_json(lesson["key_points"])) for lesson in lessons],
    )
    brief = _brief(series, None)
    if job["payload"].get("instructions"):
        brief.extra_instructions = "\n".join(filter(None, [brief.extra_instructions,
                                                           f"Para esta sección: {job['payload']['instructions']}"]))
    try:
        result = await writer(deps.llm, brief, outline, position)
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "writer", exc.attempts)
        raise
    async with deps.engine.begin() as conn:
        await _lock_series(conn, job)
        await _insert_logs(conn, job, "writer", result.attempts)
        await conn.execute(text(
            """update public.lessons set content_json = cast(:c as jsonb), status = 'generated',
                      content_version = content_version + 1, last_error = null where id = :l"""
        ), {"l": job["lesson_id"], "c": result.value.model_dump_json()})
        await conn.execute(text("select public.refresh_series_status(:s)"), {"s": job["series_id"]})
        await _succeed(conn, job)


async def _pdf_export(deps: Deps, job: dict) -> None:
    from app.exports import run_export  # WeasyPrint is heavy; only load it when exporting

    await run_export(deps, job)


# ---------------------------------------------------------------------------
# Queue state transitions
# ---------------------------------------------------------------------------


async def _lock_series(conn, job: dict) -> None:
    # Serializes parallel section saves so refresh_series_status counts every committed lesson;
    # without it the last two writers can each miss the other and leave the tome "generating".
    await conn.execute(text("select 1 from public.series where id = :s for update"), {"s": job["series_id"]})


async def _succeed(conn, job: dict) -> None:
    await conn.execute(text(
        """update public.generation_jobs set status = 'succeeded', finished_at = now(), error = null,
                  locked_at = null, locked_by = null where id = :j"""), {"j": job["id"]})


async def _requeue(engine: AsyncEngine, job: dict, delay: float, count_attempt: bool = True) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(
            """update public.generation_jobs
                  set status = 'queued', run_after = now() + make_interval(secs => :d),
                      attempts = attempts - :undo, locked_at = null, locked_by = null where id = :j"""
        ), {"j": job["id"], "d": delay, "undo": 0 if count_attempt else 1})
        if job["kind"] == "lesson":
            await conn.execute(text("update public.lessons set status = 'queued' where id = :l"),
                               {"l": job["lesson_id"]})


async def _fail(engine: AsyncEngine, job: dict, code: str, message: str) -> None:
    error = json.dumps({"code": code, "message": message})
    async with engine.begin() as conn:
        await conn.execute(text(
            """update public.generation_jobs set status = 'failed', finished_at = now(), error = cast(:e as jsonb),
                      locked_at = null, locked_by = null where id = :j"""), {"j": job["id"], "e": error})
        if job["kind"] == "outline":
            await conn.execute(text("update public.series set status = 'outline_failed' where id = :s"),
                               {"s": job["series_id"]})
        elif job["kind"] == "lesson":
            await _lock_series(conn, job)
            await conn.execute(text(
                "update public.lessons set status = 'failed', last_error = cast(:e as jsonb) where id = :l"
            ), {"l": job["lesson_id"], "e": error})
            await conn.execute(text("select public.refresh_series_status(:s)"), {"s": job["series_id"]})
        elif job["kind"] == "pdf_export":
            await conn.execute(text(
                "update public.exports set status = 'failed', finished_at = now() where job_id = :j"
            ), {"j": job["id"]})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _series(conn, series_id):
    return (await conn.execute(text("select * from public.series where id = :s"), {"s": series_id})).mappings().one()


def _brief(series, stored: dict | None) -> Brief:
    if stored:
        return Brief(request=stored["request"], audience=stored["audience"], language=stored.get("language", "es"),
                     section_count=stored.get("section_count"), extra_instructions=stored.get("extra_instructions"))
    return Brief(request=series["topic"], audience=(_json(series["audience"]) or {}).get("label", ""),
                 language=series["language"], section_count=series["lesson_count"],
                 extra_instructions=series["extra_instructions"])


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


async def _log_attempts(engine, job, agent, attempts: list[Attempt]) -> None:
    async with engine.begin() as conn:
        await _insert_logs(conn, job, agent, attempts)


async def _insert_logs(conn, job, agent, attempts: list[Attempt]) -> None:
    for n, a in enumerate(attempts, 1):
        u = a.completion.usage or {}
        await conn.execute(text(
            """insert into public.generation_logs
                 (job_id, user_id, series_id, lesson_id, attempt, model, prompt_version, request_messages,
                  response_text, finish_reason, prompt_tokens, completion_tokens, prompt_cache_hit_tokens,
                  prompt_cache_miss_tokens, latency_ms, time_to_first_token_ms, outcome)
               values (:j, :u, :s, :l, :n, :model, :pv, cast(:req as jsonb), :resp, :fin, :pt, :ct, :hit, :miss,
                       :lat, :ttft, cast(:outcome as public.generation_outcome))"""
        ), {"j": job["id"], "u": job["user_id"], "s": job["series_id"], "l": job["lesson_id"], "n": n,
            "model": a.completion.model, "pv": PROMPT_VERSION[agent], "req": json.dumps(a.messages),
            "resp": a.completion.text, "fin": a.completion.finish_reason, "pt": u.get("prompt_tokens"),
            "ct": u.get("completion_tokens"), "hit": u.get("prompt_cache_hit_tokens"),
            "miss": u.get("prompt_cache_miss_tokens"), "lat": a.completion.latency_ms,
            "ttft": a.completion.time_to_first_token_ms, "outcome": a.outcome})
