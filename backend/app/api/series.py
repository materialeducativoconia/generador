"""Tomes (the `series` table): create, read, edit the outline and approve it (ARCHITECTURE.md §3)."""

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from uuid6 import uuid7

from app.api.deps import current_user_id
from app.content import OutlineSection
from app.errors import ApiError
from app.jobs import enqueue_cover

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]

ACTIVE = ("pending", "queued", "generating")
COVERS_PER_DAY = 10
COVER_STATUS_SQL = """(select j.status::text from public.generation_jobs j where j.series_id = s.id and j.kind = 'cover'
                         order by j.created_at desc limit 1) as cover_status"""


class NewTome(BaseModel):
    request: str = Field(min_length=3, max_length=2000)
    audience: str = Field(min_length=1, max_length=200)
    language: str = Field(default="es", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    section_count: int | None = Field(default=None, ge=1, le=20)
    extra_instructions: str | None = Field(default=None, max_length=2000)


class OutlineLesson(OutlineSection):
    id: uuid.UUID | None = None


class OutlineEdit(BaseModel):
    version: int
    title: str | None = Field(default=None, max_length=300)
    lessons: list[OutlineLesson] = Field(max_length=20)


class Regenerate(BaseModel):
    instructions: str | None = Field(default=None, max_length=2000)


class Generate(BaseModel):
    lesson_ids: list[uuid.UUID] | None = None


@router.post("/api/series", status_code=202)
async def create_series(body: NewTome, request: Request, user_id: UserId,
                        idempotency_key: Annotated[str | None, Header(max_length=100)] = None):
    async with request.app.state.engine.begin() as conn:
        if idempotency_key:
            existing = (await conn.execute(text(
                "select series_id, id from public.generation_jobs where user_id = :u and idempotency_key = :k"
            ), {"u": user_id, "k": idempotency_key})).one_or_none()
            if existing:
                return await _created(conn, existing.series_id, existing.id)
        await _require_active(conn, user_id)
        series_id, job_id = uuid7(), uuid7()
        await conn.execute(text(
            """insert into public.series (id, user_id, topic, audience, language, lesson_count,
                                          extra_instructions, status)
               values (:id, :u, :topic, cast(:audience as jsonb), :lang, :n, :extra, 'outlining')"""
        ), {"id": series_id, "u": user_id, "topic": body.request, "audience": json.dumps({"label": body.audience}),
            "lang": body.language, "n": body.section_count or 10, "extra": body.extra_instructions})
        await conn.execute(text(
            """insert into public.generation_jobs (id, user_id, series_id, kind, status, payload, idempotency_key)
               values (:id, :u, :s, 'outline', 'queued', cast(:payload as jsonb), :k)"""
        ), {"id": job_id, "u": user_id, "s": series_id, "k": idempotency_key,
            "payload": json.dumps({"brief": body.model_dump()})})
        return await _created(conn, series_id, job_id)


@router.get("/api/series")
async def list_series(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            f"""select s.id, s.title, s.topic, s.genre, s.status, s.lesson_count, s.created_at, s.updated_at,
                       s.cover_key, s.cover, s.design, {COVER_STATUS_SQL},
                       count(l.id) filter (where l.status in ('generated','edited','approved')) as done
                  from public.series s left join public.lessons l on l.series_id = s.id
                 where s.user_id = :u
                 group by s.id order by s.created_at desc limit 100"""
        ), {"u": user_id})).mappings().all()
    return {"series": [_with_cover(_jsonable(r), request) for r in rows]}


@router.get("/api/series/{series_id}")
async def get_series(series_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        return await _series_detail(conn, series_id, user_id, request)


@router.get("/api/series/{series_id}/progress")
async def get_progress(series_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        series = await _own_series(conn, series_id, user_id)
        lessons = (await conn.execute(text(
            "select id, position, title, status, last_error as error, updated_at from public.lessons"
            " where series_id = :s order by position"), {"s": series_id})).mappings().all()
        export = (await conn.execute(text(
            """select e.id, e.status, e.created_at < (select max(l.updated_at) from public.lessons l
                                                        where l.series_id = e.series_id) as stale
                 from public.exports e where e.series_id = :s order by e.created_at desc limit 1"""
        ), {"s": series_id})).mappings().one_or_none()
        images = await _image_progress(conn, series_id)
    counts = {k: 0 for k in ("pending", "queued", "generating", "generated", "failed", "edited", "approved")}
    for lesson in lessons:
        counts[lesson["status"]] += 1
    active = (series["status"] in ("outlining", "generating") or counts["queued"] + counts["generating"] > 0
              or images["active"] > 0)
    return {
        "series_id": str(series_id),
        "status": series["status"],
        "version": series["version"],
        "counts": {"total": len(lessons), **counts},
        "lessons": [_jsonable(lesson) for lesson in lessons],
        "latest_export": _jsonable(export) if export else None,
        "images": images,
        "poll_after_ms": 15000 if active else None,
    }


@router.patch("/api/series/{series_id}/outline")
async def edit_outline(series_id: uuid.UUID, body: OutlineEdit, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        series = await _own_series(conn, series_id, user_id, lock=True)
        if series["status"] != "outline_ready":
            raise ApiError(409, "invalid_state", "El esquema solo se puede editar antes de aprobarlo.")
        if series["version"] != body.version:
            raise ApiError(409, "version_conflict", "El esquema cambió en otra pestaña.",
                           {"current_version": series["version"]})
        if not body.lessons:
            raise ApiError(422, "validation_error", "El tomo necesita al menos una sección.")
        kept = [lesson.id for lesson in body.lessons if lesson.id]
        await conn.execute(text("set constraints public.lessons_series_position_key deferred"))
        await conn.execute(text(
            "delete from public.lessons where series_id = :s and not (id = any(:kept))"
        ), {"s": series_id, "kept": kept})
        for position, lesson in enumerate(body.lessons, 1):
            params = {"s": series_id, "p": position, "t": lesson.title, "o": json.dumps(lesson.objectives),
                      "k": json.dumps(lesson.key_points)}
            if lesson.id:
                updated = await conn.execute(text(
                    """update public.lessons set position = :p, title = :t, objectives = cast(:o as jsonb),
                              key_points = cast(:k as jsonb) where id = :id and series_id = :s"""
                ), {**params, "id": lesson.id})
                if updated.rowcount == 0:
                    raise ApiError(422, "validation_error", "Una sección no pertenece a este tomo.")
            else:
                await conn.execute(text(
                    """insert into public.lessons (id, series_id, position, title, objectives, key_points, status)
                       values (:id, :s, :p, :t, cast(:o as jsonb), cast(:k as jsonb), 'pending')"""
                ), {**params, "id": uuid7()})
        await conn.execute(text(
            """update public.series set version = version + 1, lesson_count = :n,
                      title = coalesce(:title, title) where id = :s"""
        ), {"s": series_id, "n": len(body.lessons), "title": body.title})
        return await _series_detail(conn, series_id, user_id, request)


@router.post("/api/series/{series_id}/outline/regenerate", status_code=202)
async def regenerate_outline(series_id: uuid.UUID, body: Regenerate, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        series = await _own_series(conn, series_id, user_id, lock=True)
        if series["status"] not in ("outline_ready", "outline_failed"):
            raise ApiError(409, "invalid_state", "El esquema ya se está generando o fue aprobado.")
        job_id = uuid7()
        await conn.execute(text("update public.series set status = 'outlining' where id = :s"), {"s": series_id})
        await conn.execute(text(
            """insert into public.generation_jobs (id, user_id, series_id, kind, status, payload)
               values (:id, :u, :s, 'outline', 'queued', cast(:payload as jsonb))"""
        ), {"id": job_id, "u": user_id, "s": series_id, "payload": json.dumps({"instructions": body.instructions})})
        return await _created(conn, series_id, job_id)


@router.post("/api/series/{series_id}/cover", status_code=202)
async def request_cover(series_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        series = await _own_series(conn, series_id, user_id, lock=True)
        if not series["title"]:
            raise ApiError(409, "invalid_state", "La portada se crea cuando el esquema está listo.")
        busy = (await conn.execute(text(
            "select 1 from public.generation_jobs where series_id = :s and kind = 'cover'"
            " and status in ('queued', 'running')"), {"s": series_id})).first()
        if busy:
            raise ApiError(409, "cover_in_progress", "Ya estamos creando una portada para este tomo.")
        today = (await conn.execute(text(
            "select count(*) from public.generation_jobs where user_id = :u and kind = 'cover'"
            " and created_at > now() - interval '1 day'"), {"u": user_id})).scalar_one()
        if today >= COVERS_PER_DAY:
            raise ApiError(429, "quota_exceeded", f"Puedes crear hasta {COVERS_PER_DAY} portadas al día.")
        await enqueue_cover(conn, user_id, series_id)
    return {"cover_status": "queued"}


@router.post("/api/series/{series_id}/lessons/generate", status_code=202)
async def generate_lessons(series_id: uuid.UUID, body: Generate, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        series = await _own_series(conn, series_id, user_id, lock=True)
        if series["status"] not in ("outline_ready", "needs_attention", "ready"):
            raise ApiError(409, "invalid_state", "El esquema todavía no está listo para aprobarse.")
        if body.lesson_ids:
            targets = (await conn.execute(text(
                "select id from public.lessons where series_id = :s and id = any(:ids) and status not in"
                " ('queued','generating')"), {"s": series_id, "ids": body.lesson_ids})).scalars().all()
        else:
            targets = (await conn.execute(text(
                "select id from public.lessons where series_id = :s and status in ('pending','failed')"
                " order by position"), {"s": series_id})).scalars().all()
        if not targets:
            raise ApiError(409, "invalid_state", "No hay secciones pendientes de generar.")
        await _check_quota(conn, user_id, len(targets))
        jobs = []
        for lesson_id in targets:
            job_id = uuid7()
            await conn.execute(text(
                """insert into public.generation_jobs (id, user_id, series_id, lesson_id, kind, status, payload)
                   values (:id, :u, :s, :l, 'lesson', 'queued', '{}')"""
            ), {"id": job_id, "u": user_id, "s": series_id, "l": lesson_id})
            jobs.append({"id": str(job_id), "kind": "lesson", "lesson_id": str(lesson_id), "status": "queued"})
        await conn.execute(text(
            "update public.lessons set status = 'queued', last_error = null where id = any(:ids)"
        ), {"ids": list(targets)})
        await conn.execute(text(
            """update public.series set status = 'generating', version = version + 1,
                      outline_approved_at = coalesce(outline_approved_at, now()) where id = :s"""
        ), {"s": series_id})
        return {"series": {"id": str(series_id), "status": "generating"}, "jobs": jobs}


# ---------------------------------------------------------------------------


async def _require_active(conn, user_id):
    active = (await conn.execute(text("select is_active from public.profiles where id = :u"),
                                 {"u": user_id})).scalar_one_or_none()
    if not active:
        raise ApiError(403, "forbidden", "Esta cuenta no está activa.")


async def _check_quota(conn, user_id, wanted: int):
    row = (await conn.execute(text(
        """select p.daily_lesson_quota as quota,
                  (select count(*) from public.generation_jobs j where j.user_id = p.id
                     and j.kind in ('lesson','lesson_block')
                     and j.created_at >= date_trunc('day', now() at time zone 'utc') at time zone 'utc') as used
             from public.profiles p where p.id = :u and p.is_active"""
    ), {"u": user_id})).mappings().one_or_none()
    if row is None:
        raise ApiError(403, "forbidden", "Esta cuenta no está activa.")
    if row["used"] + wanted > row["quota"]:
        remaining = max(row["quota"] - row["used"], 0)
        raise ApiError(429, "quota_exceeded", f"Hoy solo puedes generar {remaining} secciones más.",
                       {"remaining_today": remaining})


async def _image_progress(conn, series_id) -> dict:
    blocks = (await conn.execute(text(
        """select l.id::text as lesson_id, b->>'id' as block_id, b->>'asset_id' as asset_id
             from public.lessons l, jsonb_array_elements(l.content_json->'blocks') b
            where l.series_id = :s and b->>'type' = 'image'"""), {"s": series_id})).mappings().all()
    jobs = (await conn.execute(text(
        """select distinct on (lesson_id, payload->>'block_id') lesson_id::text, payload->>'block_id' as block_id,
                  status::text from public.generation_jobs
            where series_id = :s and kind = 'illustration'
            order by lesson_id, payload->>'block_id', created_at desc"""), {"s": series_id})).all()
    latest = {(lesson, block): status for lesson, block, status in jobs}
    out = {"total": len(blocks), "done": 0, "active": 0, "failed": 0}
    for b in blocks:
        status = latest.get((b["lesson_id"], b["block_id"]))
        if b["asset_id"]:
            out["done"] += 1
        elif status in ("queued", "running"):
            out["active"] += 1
        elif status == "failed":
            out["failed"] += 1
    return out


async def _own_series(conn, series_id, user_id, lock=False):
    sql = "select * from public.series where id = :s and user_id = :u" + (" for update" if lock else "")
    row = (await conn.execute(text(sql), {"s": series_id, "u": user_id})).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "not_found", "Este tomo no existe.")
    return row


def _with_cover(out: dict, request: Request) -> dict:
    """Swaps the storage key for a public URL and exposes the palette the UI uses for placeholders."""
    key, cover = out.pop("cover_key", None), out.pop("cover", None) or {}
    storage = request.app.state.storage
    out["cover_url"] = storage.public_url(key) if key and storage else None
    out["cover_palette"] = cover.get("palette")
    return out


async def _series_detail(conn, series_id, user_id, request: Request):
    series = await _own_series(conn, series_id, user_id)
    lessons = (await conn.execute(text(
        """select id, position, title, objectives, key_points, status, last_error, content_version, content_json,
                  updated_at
             from public.lessons where series_id = :s order by position"""), {"s": series_id})).mappings().all()
    outline_error = None
    if series["status"] == "outline_failed":
        outline_error = (await conn.execute(text(
            "select error from public.generation_jobs where series_id = :s and kind = 'outline'"
            " order by created_at desc limit 1"), {"s": series_id})).scalar_one_or_none()
    out = _jsonable(series)
    out.pop("user_id", None)
    out["cover_status"] = (await conn.execute(text(
        "select status::text from public.generation_jobs where series_id = :s and kind = 'cover'"
        " order by created_at desc limit 1"), {"s": series_id})).scalar_one_or_none()
    out["lessons"] = [_jsonable(lesson) for lesson in lessons]
    out["assets"] = await _asset_urls(conn, request, out["lessons"])
    out["outline_error"] = outline_error
    return _with_cover(out, request)


async def _created(conn, series_id, job_id):
    series = (await conn.execute(text(
        "select id, title, status, lesson_count, version, created_at from public.series where id = :s"
    ), {"s": series_id})).mappings().one()
    job = (await conn.execute(text("select id, kind, status from public.generation_jobs where id = :j"),
                              {"j": job_id})).mappings().one()
    return JSONResponse({"series": _jsonable(series), "job": _jsonable(job)}, status_code=202)


def _jsonable(row) -> dict:
    out = {}
    for k, v in dict(row).items():
        if isinstance(v, uuid.UUID):
            v = str(v)
        elif hasattr(v, "isoformat"):
            v = v.isoformat()
        elif isinstance(v, str) and k in ("objectives", "key_points", "audience", "plan", "last_error", "error", "cover",
                                          "options", "content_json", "pending_content_json", "design"):
            v = json.loads(v)
        out[k] = v
    return out


@router.get("/api/lessons/{lesson_id}")
async def get_lesson(lesson_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        out = _jsonable(await _own_lesson(conn, lesson_id, user_id))
        out["assets"] = await _asset_urls(conn, request, [out])
    return out


def _image_blocks(lessons) -> list[dict]:
    return [b for lesson in lessons for b in ((lesson.get("content_json") or {}).get("blocks") or [])
            if b.get("type") == "image"]


async def _asset_urls(conn, request: Request, lessons) -> dict[str, str]:
    """Image blocks carry an asset id; the page needs a URL for each (public `images` bucket)."""
    ids = list({b["asset_id"] for b in _image_blocks(lessons) if b.get("asset_id")})
    storage = request.app.state.storage
    if not ids or storage is None:
        return {}
    rows = (await conn.execute(text("select id::text, storage_key from public.assets where id = any(cast(:ids as uuid[]))"),
                               {"ids": ids})).all()
    return {i: storage.public_url(k, bucket="images") for i, k in rows}


@router.post("/api/lessons/{lesson_id}/regenerate", status_code=202)
async def regenerate_lesson(lesson_id: uuid.UUID, body: Regenerate, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        lesson = await _own_lesson(conn, lesson_id, user_id, lock=True)
        if lesson["status"] in ACTIVE:
            raise ApiError(409, "invalid_state", "Esta sección ya se está generando.")
        await _check_quota(conn, user_id, 1)
        job_id = uuid7()
        await conn.execute(text(
            """insert into public.generation_jobs (id, user_id, series_id, lesson_id, kind, status, payload)
               values (:id, :u, :s, :l, 'lesson', 'queued', cast(:p as jsonb))"""
        ), {"id": job_id, "u": user_id, "s": lesson["series_id"], "l": lesson_id,
            "p": json.dumps({"instructions": body.instructions})})
        await conn.execute(text("update public.lessons set status = 'queued', last_error = null where id = :l"),
                           {"l": lesson_id})
        await conn.execute(text("update public.series set status = 'generating' where id = :s"),
                           {"s": lesson["series_id"]})
    return {"job": {"id": str(job_id), "kind": "lesson", "lesson_id": str(lesson_id), "status": "queued"}}


async def _own_lesson(conn, lesson_id, user_id, lock=False):
    row = (await conn.execute(text(
        """select l.* from public.lessons l join public.series s on s.id = l.series_id
            where l.id = :l and s.user_id = :u""" + (" for update of l" if lock else "")
    ), {"l": lesson_id, "u": user_id})).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "not_found", "Esta sección no existe.")
    return row
