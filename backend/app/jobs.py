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
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agents import (PROMPT_VERSION, AgentFailed, Attempt, Brief, apply_fixes, architect, art_director,
                        brand_strategist, cover_director, designer, editor, fact_sheet, identity_designer,
                        program_review, program_sheet, research_planner, writer)
from app.content import ArtPlan, Brand, Design, Outline, OutlineSection
from app.identity import describe, guard, initials, look_key
from app import credits
from app.free_images import FREE_STYLE
from app.plans import SAMPLE_PAGES
from app.llm import LLM, UpstreamAuthError, UpstreamError
from app.artwork import ImageRequest, plan_sheets, sheet_prompt, slice_sheet
from app.illustrator import (ASPECT, cover_jpeg, line_art_coverage, normalize_subject, prepare_image, reference_image,
                             vectorize)
from app.references import find_covers
from app.styles import contact_sheet, read_spec, sample_pages, theme_from_spec
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
    search: Any = None  # app.curriculum.ProgramSearch (official programs on the web); None skips it
    edit: bool = True  # the Editor proofreads each section after the Writer
    finder: Any = None  # app.free_images.Finder (openly licensed pictures); the free preview's first stop
    free_images: Any = None  # app.free_images.WorkersAI; None leaves the preview with what the Finder found


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
               "illustration": _illustration, "style": _style, "identity": _identity}[job["kind"]]
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
    if (deps.web is not None or deps.search is not None) and series["research"] is None:
        research = await _research(deps, job, brief)
        brief.facts, brief.program = _facts(research), _program(research)
    if job["payload"].get("instructions"):
        brief.extra_instructions = "\n".join(filter(None, [brief.extra_instructions,
                                                           f"Rehaz el esquema: {job['payload']['instructions']}"]))
    try:
        result = await architect(deps.llm, brief)
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "architect", exc.attempts)
        raise
    outline = result.value
    review, review_attempts = None, []
    if brief.program:  # Program reviewer: does the outline follow the reference syllabus?
        try:
            checked = await program_review(deps.llm, brief, outline)
            review, review_attempts = checked.value.model_dump(), checked.attempts
        except (AgentFailed, UpstreamError) as exc:
            log.warning("program review skipped for %s: %s", job["series_id"], exc)
            review_attempts = getattr(exc, "attempts", [])
    design, design_attempts = None, []
    if not series["design"]:  # the look is chosen now, so the outline review can show it before anything is written
        try:
            design, design_attempts = await _design(deps, job, series, brief, outline.title, outline.genre,
                                                    [x.title for x in outline.sections])
        except (AgentFailed, UpstreamError) as exc:  # the cover job tries again
            log.warning("designer skipped for %s: %s", job["series_id"], exc)
    async with deps.engine.begin() as conn:
        await _insert_logs(conn, job, "architect", result.attempts)
        await _insert_logs(conn, job, "designer", design_attempts)
        await _insert_logs(conn, job, "program_review", review_attempts)
        if review:
            await conn.execute(text(
                """update public.series set research = jsonb_set(research, '{program,review}', cast(:r as jsonb))
                    where id = :s and research ? 'program'"""), {"s": job["series_id"], "r": json.dumps(review)})
        if design:
            await conn.execute(text("update public.series set design = cast(:d as jsonb) where id = :s"),
                               {"s": job["series_id"], "d": design.model_dump_json()})
        await conn.execute(text("delete from public.lessons where series_id = :s"), {"s": job["series_id"]})
        for position, section in enumerate(outline.sections, 1):
            await conn.execute(text(
                """insert into public.lessons (series_id, position, title, objectives, key_points, letters, pages,
                                               status)
                   values (:s, :p, :t, cast(:o as jsonb), cast(:k as jsonb), cast(:lt as jsonb), :pg, 'pending')"""
            ), {"s": job["series_id"], "p": position, "t": section.title, "lt": json.dumps(section.letters),
                "pg": section.pages,
                "o": json.dumps(section.objectives), "k": json.dumps(section.key_points)})
        await conn.execute(text(
            """update public.series set title = :t, genre = :g, plan = cast(:plan as jsonb), lesson_count = :n,
                      status = 'outline_ready', version = version + 1 where id = :s"""
        ), {"s": job["series_id"], "t": outline.title, "g": outline.genre, "n": len(outline.sections),
            "plan": json.dumps({"genre": outline.genre, "style_notes": outline.style_notes,
                                "known_letters": outline.known_letters})})
        # The free preview's cover comes from the free Illustrator; the paid one is painted when the tome is bought.
        cover_job = await enqueue_cover(conn, job["user_id"], job["series_id"], free=bool(series["preview"]))
        await credits.move_charge(conn, job["id"], cover_job, "Portada")  # paid when the tome was created
        if series["preview"]:  # the free preview shows the first pages written, at our cost
            await _queue_sample(conn, job)
        await _succeed(conn, job)


async def _queue_sample(conn, job: dict) -> None:
    lesson_id = (await conn.execute(text(
        "select id from public.lessons where series_id = :s order by position limit 1"), {"s": job["series_id"]})
    ).scalar_one_or_none()
    if lesson_id is None:
        return
    await conn.execute(text(
        """insert into public.generation_jobs (user_id, series_id, lesson_id, kind, status, payload)
           values (:u, :s, :l, 'lesson', 'queued', cast(:p as jsonb))"""),
        {"u": job["user_id"], "s": job["series_id"], "l": lesson_id,
         "p": json.dumps({"sample_pages": SAMPLE_PAGES})})
    await conn.execute(text("update public.lessons set status = 'queued' where id = :l"), {"l": lesson_id})


async def _research(deps: Deps, job: dict, brief: Brief) -> dict:
    """Researcher: decide if the tome needs sources, read Wikipedia, keep a fact sheet. Never fails the outline."""
    research: dict = {"needed": False}
    try:
        planned = await research_planner(deps.llm, brief)
        await _log_attempts(deps.engine, job, "research", planned.attempts)
        research = {"needed": planned.value.needed, "reason": planned.value.reason, "queries": planned.value.queries}
        if deps.search is not None and planned.value.program_queries:
            research["program"] = await _program_search(deps, job, brief, planned.value.program_queries)
        if deps.web is not None and planned.value.needed and planned.value.queries:
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


async def _program_search(deps: Deps, job: dict, brief: Brief, queries: list[str]) -> dict:
    """Program searcher + Program sheet: official programs and proven methods from the web, with their links."""
    found = await asyncio.gather(*(deps.search.search(q, language=brief.language) for q in queries[:3]),
                                 return_exceptions=True)
    findings = [f for f in found if not isinstance(f, BaseException) and f.text]
    for f in found:
        if isinstance(f, BaseException):
            log.warning("program search failed for %s: %s", job["series_id"], f)
    sources = list({s["url"]: s for f in findings for s in f.sources}.values())
    out = {"queries": queries[:3], "sources": sources, "points": [], "program": "", "method": "",
           "cost_usd": round(sum(f.cost_usd or 0 for f in findings), 4),
           "findings": [{"query": f.query, "text": f.text} for f in findings]}  # kept for the testing panel
    if not findings:
        return out
    try:
        sheet = await program_sheet(deps.llm, brief, findings, sources)
    except (AgentFailed, UpstreamError) as exc:  # the links stay for the panel; the Architect works without
        await _log_attempts(deps.engine, job, "program", getattr(exc, "attempts", []))
        log.warning("program sheet skipped for %s: %s", job["series_id"], exc)
        return out
    await _log_attempts(deps.engine, job, "program", sheet.attempts)
    out.update(program=sheet.value.program, method=sheet.value.method,
               points=[p.model_dump() for p in sheet.value.points],
               levels=[lv.model_dump() for lv in sheet.value.levels])
    return out


def _program(research: dict | None) -> list[str] | None:
    program = (research or {}).get("program") or {}
    lines = [f"{p['text']} [programa {p['source']}]" for p in program.get("points") or []]
    if lines and program.get("method"):
        lines.insert(0, f"Método: {program['method']}")
    if lines and program.get("program"):
        lines.insert(0, f"Programa: {program['program']}")
    return lines or None


def _facts(research: dict | None) -> list[str] | None:
    facts = (research or {}).get("facts") or []
    return [f"{f['text']} [{f['source']}]" for f in facts] or None


async def _lesson(deps: Deps, job: dict) -> None:
    async with deps.engine.begin() as conn:
        series = await _series(conn, job["series_id"])
        lessons = (await conn.execute(text(
            "select id, position, title, objectives, key_points, letters, pages from public.lessons"
            " where series_id = :s"
            " order by position"), {"s": job["series_id"]})).mappings().all()
        await conn.execute(text("update public.lessons set status = 'generating' where id = :l"),
                           {"l": job["lesson_id"]})
    position = next(lesson["position"] for lesson in lessons if lesson["id"] == job["lesson_id"])
    plan = _json(series["plan"]) or {}
    outline = Outline(
        title=series["title"] or series["topic"],
        genre=series["genre"] or "lesson_series",
        style_notes=plan.get("style_notes", ""),
        known_letters=plan.get("known_letters", []),
        sections=[OutlineSection(title=lesson["title"], objectives=_json(lesson["objectives"]),
                                 key_points=_json(lesson["key_points"]), letters=_json(lesson["letters"]) or [],
                                 pages=lesson["pages"])
                  for lesson in lessons],
    )
    brief = _brief(series, None)
    sample = job["payload"].get("sample_pages")
    if sample:  # the free preview: only the section's first pages, to show what the tome will look like
        section = outline.sections[position - 1]
        section.pages = min(section.pages or sample, sample)
        brief.extra_instructions = "\n".join(filter(None, [brief.extra_instructions,
                                                           f"Esta sección es una muestra: escribe solo sus primeras "
                                                           f"{section.pages} páginas, con su mejor contenido."]))
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
    if result.notes:  # words with letters the child has not learnt yet, after the Writer's second try
        review = {"score": None, "issues": [], "fixed": 0, **(review or {}), "letters": result.notes[:20]}
    async with deps.engine.begin() as conn:
        await _lock_series(conn, job)
        await _insert_logs(conn, job, "writer", result.attempts)
        await _insert_logs(conn, job, "editor", edit_attempts)
        await conn.execute(text(
            """update public.lessons set content_json = cast(:c as jsonb), status = 'generated', review = cast(:r as jsonb),
                      content_version = content_version + 1, last_error = null, sample = :sample where id = :l"""
        ), {"l": job["lesson_id"], "c": content.model_dump_json(), "r": json.dumps(review) if review else None,
            "sample": bool(sample)})
        await conn.execute(text("select public.refresh_series_status(:s)"), {"s": job["series_id"]})
        await _queue_artwork(conn, job, sample=bool(sample))
        await _succeed(conn, job)


COVER_RULES = """Book cover illustration for a printed educational workbook, portrait 3:4, full bleed.
Absolutely NO text, letters, numbers, words, logos or watermarks anywhere in the image.
Keep the top third calm and simple (plain sky or soft background) so a title can sit on top.
Palette: {palette}.
The attached images are covers of real published educational books, given only as references for
quality, genre conventions and composition. Do NOT copy their characters, artwork, layout or branding:
create an original illustration that would sit proudly next to them on a bookstore shelf."""


async def enqueue_cover(conn, user_id, series_id, free: bool = False) -> uuid.UUID:
    job_id = uuid.uuid4()
    await conn.execute(text(
        """insert into public.generation_jobs (id, user_id, series_id, kind, status, payload, max_attempts)
           values (:j, :u, :s, 'cover', 'queued', cast(:p as jsonb), 3)"""),
        {"j": job_id, "u": user_id, "s": series_id, "p": json.dumps({"free": True} if free else {})})
    return job_id


async def _design(deps: Deps, job: dict, series, brief: Brief, title: str, genre: str,
                  sections: list[str]) -> tuple[Design, list[Attempt]]:
    """The tome's look: its identity, the style the user pinned, or the Designer's pick among their library and
    the themes."""
    async with deps.engine.connect() as conn:
        if series["identity_id"]:  # the collection's editorial line: every tome looks the same, no Designer call
            identity = (await conn.execute(text(
                "select design from public.identities where id = :id and status = 'ready'"),
                {"id": series["identity_id"]})).scalar_one_or_none()
            if identity:
                return Design.model_validate(_json(identity)), []
        library = {str(r["id"]): r for r in (await conn.execute(text(
            """select id, name, spec, design from public.styles where user_id = :u and status = 'ready'
                order by created_at desc limit 12"""), {"u": job["user_id"]})).mappings().all()}
        recent = [Design.model_validate(_json(d)) for d in (await conn.execute(text(
            """select design from public.series where user_id = :u and id <> :s and design is not null
                order by created_at desc limit 5"""), {"u": job["user_id"], "s": job["series_id"]})).scalars()]
    pinned = library.get(str(series["style_id"])) if series["style_id"] else None
    if pinned:  # the user chose a style for this tome: no Designer call at all
        return Design.model_validate(_json(pinned["design"])), []
    try:
        designed = await designer(deps.llm, brief, title, genre, sections, [
            {"id": k, "name": r["name"], **{f: (_json(r["spec"]) or {}).get(f) for f in ("suits", "traits")}}
            for k, r in library.items()], recent)
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "designer", exc.attempts)
        raise
    design = designed.value
    chosen = library.get(design.style_id or "")
    design = Design.model_validate(_json(chosen["design"])) if chosen else design.model_copy(update={"style_id": None})
    return design, designed.attempts


async def _cover(deps: Deps, job: dict) -> None:
    async with deps.engine.connect() as conn:
        series = await _series(conn, job["series_id"])
        sections = (await conn.execute(text(
            "select title from public.lessons where series_id = :s order by position"),
            {"s": job["series_id"]})).scalars().all()
    brief = _brief(series, None)
    title, genre = series["title"] or series["topic"], series["genre"] or ""
    # The Designer runs with the Architect; this is the fallback when it failed there.
    design = Design.model_validate(_json(series["design"])) if series["design"] else None
    if design is None:
        design, attempts = await _design(deps, job, series, brief, title, genre, list(sections))
        async with deps.engine.begin() as conn:
            await _insert_logs(conn, job, "designer", attempts)
            await conn.execute(text("update public.series set design = cast(:d as jsonb) where id = :s"),
                               {"s": job["series_id"], "d": design.model_dump_json()})
    free = bool(job["payload"].get("free"))
    if deps.images is None and not free:
        raise JobFailed("not_configured", "Falta OPENROUTER_API_KEY para generar portadas.")
    try:
        result = await cover_director(deps.llm, brief, title, genre, list(sections), design)
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "cover", exc.attempts)
        raise
    await _log_attempts(deps.engine, job, "cover", result.attempts)  # a retry below must not redo this log
    plan = result.value
    plan.palette = design.palette  # cover and interior share one palette
    if free:
        await _free_cover(deps, job, plan)
        return
    references = await deps.references(plan.search_queries, limit=4)
    image = await deps.images.generate(
        f"{plan.illustration_prompt}\n\n{COVER_RULES.format(palette=', '.join(plan.palette))}",
        references=[r.data for r in references], aspect_ratio="3:4", resolution="4K")  # 300+ dpi on the shelf
    key = f"{job['user_id']}/{job['series_id']}/{job['id']}.jpg"
    await deps.storage.upload(key, await asyncio.to_thread(cover_jpeg, image.data), "image/jpeg", bucket="covers")
    prior = _json(series["cover"]) or {}  # "Otra portada" adds up: the tome paid for every cover it painted
    spent = (prior.get("spent_usd") or prior.get("cost_usd") or 0) + (image.cost_usd or 0)
    cover = {"concept": plan.concept, "palette": plan.palette, "model": image.model, "cost_usd": image.cost_usd,
             "spent_usd": round(spent, 4),
             "references": [{"title": r.title, "source_url": r.source_url, "image_url": r.image_url}
                            for r in references]}
    async with deps.engine.begin() as conn:
        await conn.execute(text(
            "update public.series set cover_key = :k, cover = cast(:c as jsonb) where id = :s"
        ), {"s": job["series_id"], "k": key, "c": json.dumps(cover)})
        await _succeed(conn, job)


async def _free_cover(deps: Deps, job: dict, plan) -> None:
    """The preview's cover at no cost: the free Illustrator if it is available, else the typeset cover (title on
    the palette). `free` marks it so buying the tome paints the premium one."""
    key, model = None, None
    if deps.free_images is not None:
        try:
            image = await deps.free_images.generate(
                f"{plan.illustration_prompt}\n\n{COVER_RULES.format(palette=', '.join(plan.palette))}",
                aspect_ratio="3:4")
        except UpstreamError as exc:
            log.warning("free cover skipped: %s", exc)
        else:
            key, model = f"{job['user_id']}/{job['series_id']}/{job['id']}.jpg", image.model
            await deps.storage.upload(key, await asyncio.to_thread(cover_jpeg, image.data), "image/jpeg",
                                      bucket="covers")
    cover = {"concept": plan.concept, "palette": plan.palette, "model": model, "cost_usd": 0, "spent_usd": 0,
             "free": True}
    async with deps.engine.begin() as conn:
        await conn.execute(text(
            "update public.series set cover_key = coalesce(:k, cover_key), cover = cast(:c as jsonb) where id = :s"
        ), {"s": job["series_id"], "k": key, "c": json.dumps(cover)})
        await _succeed(conn, job)


MAX_IMAGES_PER_TOME = 48
MAX_ICONS_PER_TOME = 240  # worksheet pictures: 15 sheets of 16 at most, and the library reuses most of them
ICON_LIBRARY = "icon"  # style key of the worksheet pictures every tome shares
# Where each worksheet block keeps the words that get a picture.
PICTURED = {"syllable_chart": ("words", "word"), "picture_words": ("items", "word"), "reading": ("sentences", "picture"),
            "fill_sentences": ("items", "answer"), "word_search": ("words", None), "counting": ("items", "object"),
            "picture_math": ("operations", "object")}


def _picture_requests(lessons) -> list[ImageRequest]:
    """Image blocks still without a picture, then worksheet words without one (capped separately)."""
    images, icons = [], []
    for lesson in lessons:
        for b in (_json(lesson["content_json"]) or {}).get("blocks", []):
            ref = f"{lesson['position']}:{b['id']}"
            if b.get("type") == "image" and not b.get("asset_id"):
                images.append(ImageRequest(ref=ref, lesson_id=lesson["id"], block_id=b["id"], kind=b["kind"],
                                           size=b.get("size", "half"), subject=b["subject"]))
            elif b.get("type") in PICTURED:
                field, attr = PICTURED[b["type"]]
                words = [i if attr is None else i.get(attr) for i in b.get(field) or []]
                for w in dict.fromkeys(w for w in words if w and w not in (b.get("pictures") or {})):
                    icons.append(ImageRequest(ref=f"{ref}:{w}", lesson_id=lesson["id"], block_id=b["id"],
                                              kind="icon", size="icon", subject=w, word=w))
    return images[:MAX_IMAGES_PER_TOME] + icons[:MAX_ICONS_PER_TOME]
EXTENSION = {"image/png": "png", "image/svg+xml": "svg", "image/jpeg": "jpg"}


async def _queue_artwork(conn, job: dict, sample: bool = False) -> None:
    """Once every section is written, one job illustrates the whole tome (style needs the full picture).
    The free preview's sample is illustrated right away: a colouring book without drawings shows nothing."""
    ready = (await conn.execute(text("select status = 'ready' from public.series where id = :s"),
                                {"s": job["series_id"]})).scalar_one()
    if not ready and not sample:
        return
    await conn.execute(text(
        """insert into public.generation_jobs (user_id, series_id, kind, status, payload, max_attempts)
           select :u, :s, 'illustration', 'queued', cast(:p as jsonb), 3
            where exists (select 1 from public.lessons l, jsonb_array_elements(l.content_json->'blocks') b
                           where l.series_id = :s and (b->>'type' = 'image' and b->>'asset_id' is null
                                                        or b->>'type' = any(cast(:pictured as text[]))))
              and not exists (select 1 from public.generation_jobs where series_id = :s and kind = 'illustration'
                                 and status in ('queued', 'running'))"""),
        {"u": job["user_id"], "s": job["series_id"], "pictured": list(PICTURED),
         "p": json.dumps({"free": True} if sample else {})})


async def _illustration(deps: Deps, job: dict) -> None:
    """Art director + Illustrator + Reviewer over every picture the tome still lacks."""
    async with deps.engine.connect() as conn:
        series = await _series(conn, job["series_id"])
        lessons = (await conn.execute(text(
            "select id::text, position, content_json from public.lessons where series_id = :s order by position"
        ), {"s": job["series_id"]})).mappings().all()
    requests = _picture_requests(lessons)
    free = bool(job["payload"].get("free"))  # the free preview's sample: library, web and free Illustrator only
    if free:
        requests = requests[:MAX_FREE_PICTURES]
    if not requests:
        async with deps.engine.begin() as conn:
            await _succeed(conn, job)
        return
    design = Design.model_validate(_json(series["design"])) if series["design"] else None
    key = f"tome:{job['series_id']}"  # colour art and pages with the tome's characters stay in the tome
    # Generic colouring pages (no recurring character) are shared by every tome for the same audience.
    shared = f"line:{normalize_subject((_json(series['audience']) or {}).get('label', ''))}"

    # Curator: one picture per distinct subject; repeats (and earlier runs) reuse it.
    unique: dict[tuple[str, str], list[ImageRequest]] = {}
    for r in requests:
        unique.setdefault((r.kind, normalize_subject(r.subject)), []).append(r)
    async with deps.engine.begin() as conn:
        for (kind, norm), group in list(unique.items()):
            asset_id = (await conn.execute(text(
                """update public.assets set use_count = use_count + :n
                    where id = (select id from public.assets where kind = :k and subject_norm = :sn
                                   and style_key = any(cast(:st as text[]))
                                 order by style_key = :own desc, created_at desc limit 1) returning id"""),
                {"n": len(group), "k": kind, "own": key, "sn": norm,
                 "st": {"line_art": [key, shared], "icon": [ICON_LIBRARY]}.get(kind, [key]) + ([FREE_STYLE] if free else [])
                 })).scalar_one_or_none()
            if asset_id:
                for r in group:
                    await _attach_image(conn, r.lesson_id, r.block_id, asset_id, r.word)
                del unique[(kind, norm)]
    if not unique:
        async with deps.engine.begin() as conn:
            await _succeed(conn, job)
        return
    if free:
        await _free_pictures(deps, job, series, design, unique)
        return
    if deps.images is None:
        raise JobFailed("not_configured", "Falta OPENROUTER_API_KEY para ilustrar.")

    plan = ArtPlan.model_validate(_json(series["art"])) if series["art"] else None
    todo = [group[0] for group in unique.values()]
    if plan is None and any(r.kind != "icon" for r in todo):  # worksheet pictures need no art direction
        cover_concept = (_json(series["cover"]) or {}).get("concept")
        try:
            directed = await art_director(deps.llm, _brief(series, None), series["title"] or series["topic"], design,
                                          cover_concept, [r for r in todo if r.kind != "icon"])
        except AgentFailed as exc:
            await _log_attempts(deps.engine, job, "art", exc.attempts)
            raise
        plan = directed.value
        async with deps.engine.begin() as conn:
            await _insert_logs(conn, job, "art", directed.attempts)
            await conn.execute(text("update public.series set art = cast(:a as jsonb) where id = :s"),
                               {"s": job["series_id"], "a": plan.model_dump_json()})
    plan = plan or ArtPlan(style="Simple clean black line icons.")
    if deps.web is not None:
        for r in [r for r in todo if r.kind == "photo"]:
            photo = await deps.web.commons_photo(plan.photo_queries.get(r.ref) or plan.prompts.get(r.ref) or r.subject)
            if photo:
                data, media_type = prepare_image(photo.data, "photo")
                await _store_image(deps, job, (key, shared), r, unique[(r.kind, normalize_subject(r.subject))], data,
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
            # Worksheet pictures are shared by every tome, so they never borrow this tome's cover style.
            image = await deps.images.generate(sheet_prompt(sheet, plan, design, note),
                                               references=[] if sheet.family == "icon" else references,
                                               aspect_ratio=sheet.aspect,
                                               resolution=sheet.resolution)
            panels = [prepare_image(p, sheet.requests[0].kind) for p in
                      slice_sheet(image.data, sheet.cols, sheet.rows)[:len(sheet.requests)]]
            reviews = await _review_sheet(deps, image.data, panels, sheet)
            last_round = round_ == 1
            for r, (data, media_type), review in zip(sheet.requests, panels, reviews):
                if review.ok or last_round:
                    await _store_image(deps, job, (key, shared), r, unique[(r.kind, normalize_subject(r.subject))], data,
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


async def _free_pictures(deps: Deps, job: dict, series, design, unique: dict) -> None:
    """The preview's pictures at no cost. The Art director (text only) writes English prompts; then for each
    subject the Finder looks for an openly licensed picture and, failing that, the free Illustrator paints it.
    Whatever they bring joins the free library. A subject neither can serve stays as an empty frame."""
    todo = [group[0] for group in unique.values()]
    try:
        directed = await art_director(deps.llm, _brief(series, None), series["title"] or series["topic"], design,
                                      (_json(series["cover"]) or {}).get("concept"), todo)
        plan = directed.value
        await _log_attempts(deps.engine, job, "art", directed.attempts)
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "art", exc.attempts)
        plan = ArtPlan(style="Simple clean children's book pictures.")

    async def one(r: ImageRequest) -> None:
        prompt = plan.prompts.get(r.ref) or r.subject
        query = plan.photo_queries.get(r.ref) or " ".join(prompt.split(",")[0].split()[:6])
        found = None
        if r.kind == "photo" and deps.web is not None:
            found = await deps.web.commons_photo(query)
        if found is None and r.kind != "icon" and deps.finder is not None:
            found = await deps.finder.find(query, r.kind, accept=lambda data: _shows(deps, data, r))
        image = None
        if found is None and deps.free_images is not None:
            try:
                image = await deps.free_images.generate(f"{FREE_STYLE_PROMPT.get(r.kind, '')}{prompt}. {plan.style}",
                                                        aspect_ratio=ASPECT.get(r.size, "3:4"))
            except UpstreamError as exc:
                log.warning("free picture skipped for %s: %s", r.ref, exc)
                return
        if found is None and image is None:
            return
        data, media_type = prepare_image(found.data if found else image.data, r.kind)
        attribution = {"author": found.author, "license": found.license, "source_url": found.source_url,
                       "credit": f"{found.author}, {found.license}"} if found else None
        await _store_image(deps, job, (FREE_STYLE, FREE_STYLE), r, unique[(r.kind, normalize_subject(r.subject))],
                           data, media_type, image, 1, Review(ok=True), 1, plan, attribution=attribution,
                           style_key=FREE_STYLE, source="openverse" if found else None)

    await asyncio.gather(*(one(r) for r in todo))
    async with deps.engine.begin() as conn:
        await _succeed(conn, job)


async def _shows(deps: Deps, data: bytes, r: ImageRequest) -> bool:
    """The Reviewer's word on a picture found on the web (a fraction of a cent); without it, the kind check alone."""
    if deps.vision is None:
        return True
    try:
        verdict = (await deps.vision.review_sheet(data, [r.subject], kind=r.kind))[0]
    except (UpstreamError, UpstreamAuthError):
        return False
    return verdict.matches_subject and not verdict.has_text


MAX_FREE_PICTURES = 8  # a two-page sample rarely needs more; worksheet words beyond it stay as text
FREE_STYLE_PROMPT = {
    "line_art": "Black and white colouring page for children, clean thick outlines, pure white background, "
                "no shading, no grey, no text. ",
    "icon": "Simple flat icon for a children's worksheet, white background, no text. ",
    "colour": "Children's book illustration, no text, no letters. ",
    "photo": "Realistic photo, no text. ",
}


async def _review_sheet(deps: Deps, sheet_image: bytes, panels: list[tuple[bytes, str]], sheet) -> list[Review]:
    """Deterministic checks per panel, then one vision call for the whole sheet."""
    checks = []
    for data, _ in panels:
        coverage = line_art_coverage(data) if sheet.family in ("line", "icon") else None
        if coverage is not None and coverage < 0.005:
            checks.append(Review(ok=False, issues="the panel came out blank"))
        elif coverage is not None and coverage > (0.3 if sheet.family == "line" else 0.5):  # silhouettes
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
    return [replace(c or (v if v.has_text or not v.matches_subject else Review(ok=True, issues=v.issues)),
                    cost_usd=v.cost_usd) for c, v in zip(checks, seen)]


async def _store_image(deps, job, keys, request, group, data, media_type, image, share, review, attempts, plan,
                       attribution=None, style_key=None, source=None):
    prompt = plan.prompts.get(request.ref) or request.subject
    generic = not any(c.name.lower() in f"{prompt} {request.subject}".lower() for c in plan.characters)
    key = style_key or (ICON_LIBRARY if request.kind == "icon" else keys[1] if request.kind == "line_art" and generic
                        else keys[0])
    if request.kind in ("line_art", "icon") and media_type == "image/png":
        svg = await asyncio.to_thread(vectorize, data)
        if svg:
            data, media_type = svg, "image/svg+xml"
    asset_id = uuid.uuid4()
    storage_key = f"{asset_id}.{EXTENSION.get(media_type, 'jpg')}"
    await deps.storage.upload(storage_key, data, media_type, bucket="images")
    async with deps.engine.begin() as conn:
        await conn.execute(text(
            """insert into public.assets (id, kind, subject, subject_norm, style_key, storage_key, media_type, model,
                                          cost_usd, review, created_by, use_count, attribution, series_id)
               values (:id, :k, :subj, :n, :st, :key, :mt, :model, :cost, cast(:review as jsonb), :u, :uses,
                       cast(:attr as jsonb), :s)"""
        ), {"id": asset_id, "k": request.kind, "subj": request.subject, "n": normalize_subject(request.subject),
            "st": key, "key": storage_key, "mt": media_type, "model": image.model if image else source or "wikimedia-commons",
            "u": job["user_id"], "s": job["series_id"], "uses": len(group),
            "cost": ((image.cost_usd or 0) / share) if image else 0,
            "attr": json.dumps(attribution) if attribution else None,
            "review": json.dumps({"ok": review.ok, "has_text": review.has_text, "issues": review.issues,
                                  "cost_usd": review.cost_usd,
                                  "attempts": attempts, "prompt": plan.prompts.get(request.ref)})})
        for r in group:  # every block in the tome that asked for this same subject
            await _attach_image(conn, r.lesson_id, r.block_id, asset_id, r.word)


async def _attach_image(conn, lesson_id: str, block_id: str, asset_id, word: str | None = None) -> None:
    # Row lock: the section may be rewritten meanwhile; we patch whatever content is current.
    content = _json((await conn.execute(text("select content_json from public.lessons where id = :l for update"),
                                        {"l": lesson_id})).scalar_one_or_none())
    for block in (content or {}).get("blocks", []):
        if block["id"] == block_id:
            if word:
                block.setdefault("pictures", {})[word] = str(asset_id)
            else:
                block["asset_id"] = str(asset_id)
            await conn.execute(text(
                """update public.lessons set content_json = cast(:c as jsonb), content_version = content_version + 1
                    where id = :l"""), {"l": lesson_id, "c": json.dumps(content)})
            return


async def _style(deps: Deps, job: dict) -> None:
    """Style library: sample the user's reference file, let one vision call pick the best pages and read their
    style, and turn that into a Design (app.styles)."""
    style_id = job["payload"]["style_id"]
    async with deps.engine.connect() as conn:
        style = (await conn.execute(text("select * from public.styles where id = :id and user_id = :u"),
                                    {"id": style_id, "u": job["user_id"]})).mappings().one_or_none()
    if style is None:  # deleted meanwhile
        async with deps.engine.begin() as conn:
            await _succeed(conn, job)
        return
    if deps.vision is None:
        raise JobFailed("not_configured", "Falta OPENROUTER_API_KEY para analizar estilos.")
    try:
        data = await deps.storage.download_private(style["source_key"], bucket="references")
        pages = await asyncio.to_thread(sample_pages, data, style["source_type"])
    except Exception as exc:  # a broken or missing upload will not get better on retry
        log.warning("style %s unreadable: %s", style_id, exc)
        raise JobFailed("unreadable", "No pudimos leer el archivo. Sube un PDF o una imagen válidos.") from exc
    raw, cost = await deps.vision.analyze_style(await asyncio.to_thread(contact_sheet, pages), len(pages))
    spec = read_spec(raw, len(pages))
    best = [pages[i - 1] for i in spec.best_pages] or pages[:3]
    keys = []
    for n, page in enumerate(best, 1):  # previews for the library page, private like the upload
        key = f"{job['user_id']}/{style_id}/best-{n}.jpg"
        await deps.storage.upload(key, page, "image/jpeg", bucket="references")
        keys.append(key)
    design = theme_from_spec(spec, name=style["name"], style_id=str(style_id))
    async with deps.engine.begin() as conn:
        await conn.execute(text(
            """update public.styles set status = 'ready', spec = cast(:spec as jsonb), design = cast(:d as jsonb),
                      pages = cast(:p as jsonb), error = null where id = :id"""),
            {"id": style_id, "spec": json.dumps({**spec.model_dump(), "cost_usd": cost}),
             "d": design.model_dump_json(), "p": json.dumps(keys)})
        await _succeed(conn, job)


async def _identity(deps: Deps, job: dict) -> None:
    """Mis identidades: the Brand strategist proposes three editorial lines, the Identity designer gives each a
    visual system, and the Brand guard (app.identity) keeps them printable and unlike anything already in use."""
    identity_id = job["payload"]["identity_id"]
    async with deps.engine.connect() as conn:
        row = (await conn.execute(text("select brief from public.identities where id = :id and user_id = :u"),
                                  {"id": identity_id, "u": job["user_id"]})).mappings().one_or_none()
        if row is None:  # deleted meanwhile
            mine, popular, hint = [], [], None
        else:
            mine = [Design.model_validate(_json(d)) for d in (await conn.execute(text(
                """select design from public.identities where user_id = :u and status = 'ready' and id <> :id"""),
                {"u": job["user_id"], "id": identity_id})).scalars()]
            # Other users' lines, as bare look combinations only: no names, no briefs.
            popular = [Design.model_validate(_json(d)) for d in (await conn.execute(text(
                """select (array_agg(design))[1] from public.identities where status = 'ready' and user_id <> :u
                    group by design->>'theme', design->>'illustration', design->>'cover_layout', design->>'head_font'
                   having count(*) >= 2 order by count(*) desc limit 12"""), {"u": job["user_id"]})).scalars()]
            brief = _json(row["brief"])
            hint = None
            if brief.get("style_id"):
                spec = (await conn.execute(text(
                    "select spec from public.styles where id = :id and user_id = :u and status = 'ready'"),
                    {"id": brief["style_id"], "u": job["user_id"]})).scalar_one_or_none()
                spec = _json(spec) or {}
                hint = "; ".join(filter(None, [spec.get("suits"), *spec.get("traits", [])[:4]])) or None
    if row is None:
        async with deps.engine.begin() as conn:
            await _succeed(conn, job)
        return
    text_brief = "\n".join(filter(None, [
        f"Qué publica: {brief['about']}", f"Público: {brief.get('audience') or 'variado'}",
        f"Personalidad deseada: {brief['personality']}" if brief.get("personality") else None,
        f"Idioma: {brief.get('language', 'es')}"]))
    try:
        strategy = await brand_strategist(deps.llm, text_brief, [describe(d) for d in mine])
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "brand", exc.attempts)
        raise
    await _log_attempts(deps.engine, job, "brand", strategy.attempts)
    try:
        styled = await identity_designer(deps.llm, strategy.value, [describe(d) for d in [*mine, *popular]], hint)
    except AgentFailed as exc:
        await _log_attempts(deps.engine, job, "identity", exc.attempts)
        raise
    looks = guard(styled.value.looks, {look_key(d) for d in [*mine, *popular]})
    candidates = []
    for look, direction in zip(looks, strategy.value.directions):
        brand = Brand.model_validate(direction.model_dump(exclude={"visual_idea"}))
        brand.initials = (brand.initials or initials(brand.name))[:3]
        candidates.append(look.model_copy(update={"brand": brand, "identity_id": str(identity_id),
                                                  "rationale": direction.visual_idea or look.rationale}).model_dump())
    async with deps.engine.begin() as conn:
        await _insert_logs(conn, job, "identity", styled.attempts)
        await conn.execute(text(
            """update public.identities set status = 'choosing', candidates = cast(:c as jsonb), error = null
                where id = :id"""), {"id": identity_id, "c": json.dumps(candidates)})
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
        await credits.refund_job(conn, job["id"])  # the user pays for results, not for our failures
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
        elif job["kind"] == "style":
            await conn.execute(text("update public.styles set status = 'failed', error = :m where id = :id"),
                               {"id": job["payload"]["style_id"], "m": message})
        elif job["kind"] == "identity":
            await conn.execute(text("update public.identities set status = 'failed', error = :m where id = :id"),
                               {"id": job["payload"]["identity_id"], "m": message})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _series(conn, series_id):
    return (await conn.execute(text("select * from public.series where id = :s"), {"s": series_id})).mappings().one()


def _brief(series, stored: dict | None) -> Brief:
    facts = _facts(_json(series["research"]))
    brand = (_json(series["design"]) or {}).get("brand") or {}
    voice = f"«{brand['name']}»: {brand['voice']}" if brand.get("voice") else None
    if stored:
        return Brief(request=stored["request"], audience=stored["audience"], language=stored.get("language", "es"),
                     section_count=stored.get("section_count"), extra_instructions=stored.get("extra_instructions"),
                     page_count=stored.get("page_count"), facts=facts,
                     program=_program(_json(series["research"])), voice=voice)
    brief = Brief(request=series["topic"], audience=(_json(series["audience"]) or {}).get("label", ""),
                 language=series["language"], section_count=series["lesson_count"],
                 extra_instructions=series["extra_instructions"], page_count=series["page_target"], facts=facts,
                 voice=voice)
    brief.program = _program(_json(series["research"]))
    return brief


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
