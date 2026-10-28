"""Job queue on Postgres (FOR UPDATE SKIP LOCKED) and the handlers the worker runs.

A handler never holds a DB connection while waiting on DeepSeek: claim + commit, call the
model with no connection open, then a second transaction saves the result (ARCHITECTURE.md §5.2b).
"""

import asyncio
import json
import logging
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agents import (PROMPT_VERSION, AgentFailed, Attempt, Brief, apply_fixes, architect, editor, art_director, cover_director, designer,
                        fact_sheet, research_planner, writer)
from app.content import ArtPlan, Design, Outline, OutlineSection
from app.llm import LLM, UpstreamAuthError, UpstreamError
from app.artwork import ImageRequest, plan_sheets, sheet_prompt, slice_sheet
from app.illustrator import (cover_jpeg, line_art_coverage, normalize_subject, prepare_image, reference_image,
                             vectorize)
from app.references import find_covers
from app.vision import Review

log = logging.getLogger("worker")


@dataclass
class Deps:
    engine: AsyncEngine
    llm: LLM
    storage: Any  # app.storage.Storage; pdf_export and cover use it
    images: Any = None  # app.images.OpenRouterImages; None when OPENROUTER_API_KEY is unset
    vision: Any = None  # app.vision.OpenRouterVision, the image Reviewer; None skips the visual review
    references: Callable[..., Awaitable[list]] = find_covers
    web: Any = None  # app.research.Web (Wikipedia, Commons); None skips research and real photos
    edit: bool = True  # the Editor proofreads each section after the Writer


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
    handler = {"outline": _outline, "lesson": _lesson, "pdf_export": _pdf_export, "cover": _cover,
               "illustration": _illustration}[job["kind"]]
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
        log.error("upstream auth/billing error, job %s parked: %s", job["id"], exc)
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
    if deps.web is not None and series["research"] is None:
        research = await _research(deps, job, brief)
        brief.facts = _facts(research)
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
        await enqueue_cover(conn, job["user_id"], job["series_id"])
        await _succeed(conn, job)


async def _research(deps: Deps, job: dict, brief: Brief) -> dict:
    """Researcher: decide if the tome needs sources, read Wikipedia, keep a fact sheet. Never fails the outline."""
    research: dict = {"needed": False}
    try:
        planned = await research_planner(deps.llm, brief)
        await _log_attempts(deps.engine, job, "research", planned.attempts)
        research = {"needed": planned.value.needed, "reason": planned.value.reason, "queries": planned.value.queries}
        if planned.value.needed and planned.value.queries:
            documents = await deps.web.wikipedia(planned.value.queries, lang=brief.language)
            if documents:
                sheet = await fact_sheet(deps.llm, brief, documents)
                await _log_attempts(deps.engine, job, "facts", sheet.attempts)
                research["facts"] = [f.model_dump() for f in sheet.value.facts]
                research["sources"] = [{"title": d.title, "url": d.url} for d in documents]
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "research", exc.attempts)
        log.warning("research skipped for %s: %s", job["series_id"], exc)
    async with deps.engine.begin() as conn:
        await conn.execute(text("update public.series set research = cast(:r as jsonb) where id = :s"),
                           {"s": job["series_id"], "r": json.dumps(research)})
    return research


def _facts(research: dict | None) -> list[str] | None:
    facts = (research or {}).get("facts") or []
    return [f"{f['text']} [{f['source']}]" for f in facts] or None


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
    content, review, edit_attempts = result.value, None, []
    if deps.edit:
        try:
            edited = await editor(deps.llm, brief, outline, position, content)
        except (AgentFailed, UpstreamError) as exc:  # the Writer's text is still worth keeping
            log.warning("editor skipped for lesson %s: %s", job["lesson_id"], exc)
            edit_attempts = getattr(exc, "attempts", [])
        else:
            content, applied = apply_fixes(content, edited.value.fixes)
            review = {"score": edited.value.score, "issues": edited.value.issues, "fixed": applied}
            edit_attempts = edited.attempts
    async with deps.engine.begin() as conn:
        await _lock_series(conn, job)
        await _insert_logs(conn, job, "writer", result.attempts)
        await _insert_logs(conn, job, "editor", edit_attempts)
        await conn.execute(text(
            """update public.lessons set content_json = cast(:c as jsonb), status = 'generated', review = cast(:r as jsonb),
                      content_version = content_version + 1, last_error = null where id = :l"""
        ), {"l": job["lesson_id"], "c": content.model_dump_json(), "r": json.dumps(review) if review else None})
        await conn.execute(text("select public.refresh_series_status(:s)"), {"s": job["series_id"]})
        await _queue_artwork(conn, job)
        await _succeed(conn, job)


COVER_RULES = """Book cover illustration for a printed educational workbook, portrait 3:4, full bleed.
Absolutely NO text, letters, numbers, words, logos or watermarks anywhere in the image.
Keep the top third calm and simple (plain sky or soft background) so a title can sit on top.
Palette: {palette}.
The attached images are covers of real published educational books, given only as references for
quality, genre conventions and composition. Do NOT copy their characters, artwork, layout or branding:
create an original illustration that would sit proudly next to them on a bookstore shelf."""


async def enqueue_cover(conn, user_id, series_id) -> uuid.UUID:
    job_id = uuid.uuid4()
    await conn.execute(text(
        """insert into public.generation_jobs (id, user_id, series_id, kind, status, payload, max_attempts)
           values (:j, :u, :s, 'cover', 'queued', '{}', 3)"""), {"j": job_id, "u": user_id, "s": series_id})
    return job_id


async def _cover(deps: Deps, job: dict) -> None:
    async with deps.engine.connect() as conn:
        series = await _series(conn, job["series_id"])
        sections = (await conn.execute(text(
            "select title from public.lessons where series_id = :s order by position"),
            {"s": job["series_id"]})).scalars().all()
    brief = _brief(series, None)
    title, genre = series["title"] or series["topic"], series["genre"] or ""
    # The Designer runs once per tome; asking for another cover keeps the interior's look.
    design = Design.model_validate(_json(series["design"])) if series["design"] else None
    if design is None:
        try:
            designed = await designer(deps.llm, brief, title, genre, list(sections))
        except AgentFailed as exc:
            await _log_attempts(deps.engine, job, "designer", exc.attempts)
            raise
        design = designed.value
        async with deps.engine.begin() as conn:
            await _insert_logs(conn, job, "designer", designed.attempts)
            await conn.execute(text("update public.series set design = cast(:d as jsonb) where id = :s"),
                               {"s": job["series_id"], "d": design.model_dump_json()})
    if deps.images is None:
        raise JobFailed("not_configured", "Falta OPENROUTER_API_KEY para generar portadas.")
    try:
        result = await cover_director(deps.llm, brief, title, genre, list(sections), design)
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "cover", exc.attempts)
        raise
    await _log_attempts(deps.engine, job, "cover", result.attempts)  # a retry below must not redo this log
    plan = result.value
    plan.palette = design.palette  # cover and interior share one palette
    references = await deps.references(plan.search_queries, limit=4)
    image = await deps.images.generate(
        f"{plan.illustration_prompt}\n\n{COVER_RULES.format(palette=', '.join(plan.palette))}",
        references=[r.data for r in references], aspect_ratio="3:4", resolution="4K")  # 300+ dpi on the shelf
    key = f"{job['user_id']}/{job['series_id']}/{job['id']}.jpg"
    await deps.storage.upload(key, await asyncio.to_thread(cover_jpeg, image.data), "image/jpeg", bucket="covers")
    cover = {"concept": plan.concept, "palette": plan.palette, "model": image.model, "cost_usd": image.cost_usd,
             "references": [{"title": r.title, "source_url": r.source_url, "image_url": r.image_url}
                            for r in references]}
    async with deps.engine.begin() as conn:
        await conn.execute(text(
            "update public.series set cover_key = :k, cover = cast(:c as jsonb) where id = :s"
        ), {"s": job["series_id"], "k": key, "c": json.dumps(cover)})
        await _succeed(conn, job)


MAX_IMAGES_PER_TOME = 48
EXTENSION = {"image/png": "png", "image/svg+xml": "svg", "image/jpeg": "jpg"}


async def _queue_artwork(conn, job: dict) -> None:
    """Once every section is written, one job illustrates the whole tome (style needs the full picture)."""
    ready = (await conn.execute(text("select status = 'ready' from public.series where id = :s"),
                                {"s": job["series_id"]})).scalar_one()
    if not ready:
        return
    await conn.execute(text(
        """insert into public.generation_jobs (user_id, series_id, kind, status, payload, max_attempts)
           select :u, :s, 'illustration', 'queued', '{}', 3
            where exists (select 1 from public.lessons l, jsonb_array_elements(l.content_json->'blocks') b
                           where l.series_id = :s and b->>'type' = 'image' and b->>'asset_id' is null)
              and not exists (select 1 from public.generation_jobs where series_id = :s and kind = 'illustration'
                                 and status in ('queued', 'running'))"""), {"u": job["user_id"], "s": job["series_id"]})


async def _illustration(deps: Deps, job: dict) -> None:
    """Art director + Illustrator + Reviewer over every picture the tome still lacks."""
    async with deps.engine.connect() as conn:
        series = await _series(conn, job["series_id"])
        lessons = (await conn.execute(text(
            "select id::text, position, content_json from public.lessons where series_id = :s order by position"
        ), {"s": job["series_id"]})).mappings().all()
    requests = [ImageRequest(ref=f"{lesson['position']}:{b['id']}", lesson_id=lesson["id"], block_id=b["id"],
                             kind=b["kind"], size=b.get("size", "half"), subject=b["subject"])
                for lesson in lessons for b in (_json(lesson["content_json"]) or {}).get("blocks", [])
                if b.get("type") == "image" and not b.get("asset_id")][:MAX_IMAGES_PER_TOME]
    if not requests:
        async with deps.engine.begin() as conn:
            await _succeed(conn, job)
        return
    design = Design.model_validate(_json(series["design"])) if series["design"] else None
    key = f"tome:{job['series_id']}"  # the style is this tome's own, so library reuse stays inside it

    # Curator: one picture per distinct subject; repeats (and earlier runs) reuse it.
    unique: dict[tuple[str, str], list[ImageRequest]] = {}
    for r in requests:
        unique.setdefault((r.kind, normalize_subject(r.subject)), []).append(r)
    async with deps.engine.begin() as conn:
        for (kind, norm), group in list(unique.items()):
            asset_id = (await conn.execute(text(
                """update public.assets set use_count = use_count + :n
                    where id = (select id from public.assets where kind = :k and style_key = :st and subject_norm = :sn
                                 order by created_at desc limit 1) returning id"""),
                {"n": len(group), "k": kind, "st": key, "sn": norm})).scalar_one_or_none()
            if asset_id:
                for r in group:
                    await _attach_image(conn, r.lesson_id, r.block_id, asset_id)
                del unique[(kind, norm)]
    if not unique:
        async with deps.engine.begin() as conn:
            await _succeed(conn, job)
        return
    if deps.images is None:
        raise JobFailed("not_configured", "Falta OPENROUTER_API_KEY para ilustrar.")

    plan = ArtPlan.model_validate(_json(series["art"])) if series["art"] else None
    todo = [group[0] for group in unique.values()]
    if plan is None:
        cover_concept = (_json(series["cover"]) or {}).get("concept")
        try:
            directed = await art_director(deps.llm, _brief(series, None), series["title"] or series["topic"], design,
                                          cover_concept, todo)
        except AgentFailed as exc:
            await _log_attempts(deps.engine, job, "art", exc.attempts)
            raise
        plan = directed.value
        async with deps.engine.begin() as conn:
            await _insert_logs(conn, job, "art", directed.attempts)
            await conn.execute(text("update public.series set art = cast(:a as jsonb) where id = :s"),
                               {"s": job["series_id"], "a": plan.model_dump_json()})
    if deps.web is not None:
        for r in [r for r in todo if r.kind == "photo"]:
            photo = await deps.web.commons_photo(plan.photo_queries.get(r.ref) or plan.prompts.get(r.ref) or r.subject)
            if photo:
                data, media_type = prepare_image(photo.data, "photo")
                await _store_image(deps, job, key, r, unique[(r.kind, normalize_subject(r.subject))], data,
                                   media_type, None, 1, Review(ok=True), 1, plan,
                                   attribution={"author": photo.author, "license": photo.license,
                                                "source_url": photo.source_url, "credit": photo.credit})
                todo.remove(r)
        if not todo:
            async with deps.engine.begin() as conn:
                await _succeed(conn, job)
            return
    references = []
    if series["cover_key"]:
        try:
            references = [reference_image(await deps.storage.download(series["cover_key"]))]
        except Exception:  # the cover is a style anchor, not a requirement
            log.warning("cover %s unavailable as reference", series["cover_key"])

    feedback: dict[str, str] = {}
    for round_ in range(2):  # paint, then repaint only what failed, all together
        failed: list[ImageRequest] = []

        async def paint(sheet):
            note = "; ".join(f"{r.ref}: {feedback[r.ref]}" for r in sheet.requests if r.ref in feedback) or None
            image = await deps.images.generate(sheet_prompt(sheet, plan, design, note), references=references,
                                               aspect_ratio=sheet.aspect,
                                               resolution=_resolution(sheet))
            panels = [prepare_image(p, sheet.requests[0].kind) for p in
                      slice_sheet(image.data, sheet.cols, sheet.rows)[:len(sheet.requests)]]
            reviews = await _review_sheet(deps, image.data, panels, sheet)
            last_round = round_ == 1
            for r, (data, media_type), review in zip(sheet.requests, panels, reviews):
                if review.ok or last_round:
                    await _store_image(deps, job, key, r, unique[(r.kind, normalize_subject(r.subject))], data,
                                       media_type, image, len(sheet.requests), review, round_ + 1, plan)
                else:
                    failed.append(r)
                    feedback[r.ref] = review.issues or "did not match the request"

        # Sheets are independent: paint them side by side (at most 12 per tome, see MAX_IMAGES_PER_TOME).
        await asyncio.gather(*(paint(sheet) for sheet in plan_sheets(todo)))
        if not failed:
            break
        todo = failed
    async with deps.engine.begin() as conn:
        await _succeed(conn, job)


async def _review_sheet(deps: Deps, sheet_image: bytes, panels: list[tuple[bytes, str]], sheet) -> list[Review]:
    """Deterministic checks per panel, then one vision call for the whole sheet."""
    checks = []
    for data, _ in panels:
        coverage = line_art_coverage(data) if sheet.family == "line" else None
        if coverage is not None and coverage < 0.005:
            checks.append(Review(ok=False, issues="the panel came out blank"))
        elif coverage is not None and coverage > 0.5:
            checks.append(Review(ok=False, issues="too much solid black, use outlines only"))
        else:
            checks.append(None)
    if deps.vision is None:
        return [c or Review(ok=True) for c in checks]
    try:
        seen = await deps.vision.review_sheet(sheet_image, [r.subject for r in sheet.requests],
                                              kind=sheet.requests[0].kind)
    except (UpstreamError, UpstreamAuthError) as exc:  # a reviewer outage must not block the tome
        log.warning("image review skipped: %s", exc)
        seen = [Review(ok=True, issues="sin revisar") for _ in sheet.requests]
    # Only hard failures earn a repaint: text in the picture, the wrong subject, or a deterministic check.
    return [c or (v if v.has_text or not v.matches_subject else Review(ok=True, issues=v.issues))
            for c, v in zip(checks, seen)]


def _resolution(sheet) -> str:
    """Colouring pages are traced to vectors, so pixels only need to carry the shapes; colour art must
    reach print resolution on its own."""
    if sheet.family == "line":
        return "1K" if sheet.cols == 1 else "2K"
    return "2K" if sheet.cols == 1 else "4K"


async def _store_image(deps, job, key, request, group, data, media_type, image, share, review, attempts, plan,
                       attribution=None):
    if request.kind == "line_art" and media_type == "image/png":
        svg = await asyncio.to_thread(vectorize, data)
        if svg:
            data, media_type = svg, "image/svg+xml"
    asset_id = uuid.uuid4()
    storage_key = f"{asset_id}.{EXTENSION.get(media_type, 'jpg')}"
    await deps.storage.upload(storage_key, data, media_type, bucket="images")
    async with deps.engine.begin() as conn:
        await conn.execute(text(
            """insert into public.assets (id, kind, subject, subject_norm, style_key, storage_key, media_type, model,
                                          cost_usd, review, created_by, use_count, attribution)
               values (:id, :k, :subj, :n, :st, :key, :mt, :model, :cost, cast(:review as jsonb), :u, :uses,
                       cast(:attr as jsonb))"""
        ), {"id": asset_id, "k": request.kind, "subj": request.subject, "n": normalize_subject(request.subject),
            "st": key, "key": storage_key, "mt": media_type, "model": image.model if image else "wikimedia-commons",
            "u": job["user_id"], "cost": ((image.cost_usd or 0) / share) if image else 0, "uses": len(group),
            "attr": json.dumps(attribution) if attribution else None,
            "review": json.dumps({"ok": review.ok, "has_text": review.has_text, "issues": review.issues,
                                  "attempts": attempts, "prompt": plan.prompts.get(request.ref)})})
        for r in group:  # every block in the tome that asked for this same subject
            await _attach_image(conn, r.lesson_id, r.block_id, asset_id)


async def _attach_image(conn, lesson_id: str, block_id: str, asset_id) -> None:
    # Row lock: the section may be rewritten meanwhile; we patch whatever content is current.
    content = _json((await conn.execute(text("select content_json from public.lessons where id = :l for update"),
                                        {"l": lesson_id})).scalar_one_or_none())
    for block in (content or {}).get("blocks", []):
        if block["id"] == block_id:
            block["asset_id"] = str(asset_id)
            await conn.execute(text(
                """update public.lessons set content_json = cast(:c as jsonb), content_version = content_version + 1
                    where id = :l"""), {"l": lesson_id, "c": json.dumps(content)})
            return


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
    facts = _facts(_json(series["research"]))
    if stored:
        return Brief(request=stored["request"], audience=stored["audience"], language=stored.get("language", "es"),
                     section_count=stored.get("section_count"), extra_instructions=stored.get("extra_instructions"),
                     facts=facts)
    return Brief(request=series["topic"], audience=(_json(series["audience"]) or {}).get("label", ""),
                 language=series["language"], section_count=series["lesson_count"],
                 extra_instructions=series["extra_instructions"], facts=facts)


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
