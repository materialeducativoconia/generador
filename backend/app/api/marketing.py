"""/admin/marketing: promotional videos. DeepSeek writes a template's script from a real tome; the admin edits it,
previews the video and renders the MP4 in the browser."""

import json
import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.agents import AgentFailed
from app.api.admin import _staff
from app.api.deps import current_user_id
from app.errors import ApiError
from app.marketing import VideoScript, video_script
from app.render import GENRE_LABEL

log = logging.getLogger("api")
router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
FIELDS = "id::text, template, series_id::text, format, script, created_at, updated_at, mp4_key, rendered_at"
BUCKET = "marketing"
Format = Literal["9:16", "1:1", "16:9"]


def _out(row) -> dict:
    video = dict(row)
    if isinstance(video["script"], str):
        video["script"] = json.loads(video["script"])
    video["has_mp4"] = bool(video.pop("mp4_key"))
    return video


@router.get("/api/admin/marketing/videos")
async def list_videos(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        rows = (await conn.execute(text(
            f"select {FIELDS} from public.marketing_videos order by created_at desc limit 100"))).mappings().all()
    return {"videos": [_out(r) for r in rows]}


class NewVideo(BaseModel):
    series_id: uuid.UUID
    format: Format = "9:16"
    angle: str | None = Field(default=None, max_length=300)  # what the team wants the video to stress


@router.post("/api/admin/marketing/videos", status_code=201)
async def new_video(body: NewVideo, request: Request, user_id: UserId):
    """A new video of a tome: DeepSeek writes its script (a few seconds)."""
    llm = request.app.state.llm
    if llm is None:
        raise ApiError(503, "unavailable", "El guionista no está configurado.")
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        series = (await conn.execute(text(
            """select coalesce(title, topic) as title, topic, genre::text as genre,
                      coalesce(audience->>'label', '') as audience,
                      array(select l.title from public.lessons l where l.series_id = s.id order by l.position) as sections
                 from public.series s where id = :s"""), {"s": body.series_id})).mappings().first()
    if series is None:
        raise ApiError(404, "not_found", "Ese tomo no existe.")
    try:
        result = await video_script(llm, title=series["title"], topic=series["topic"],
                                    kind=GENRE_LABEL.get(series["genre"] or "", "Libro"), audience=series["audience"],
                                    sections=list(series["sections"]), angle=body.angle)
    except AgentFailed as exc:
        log.warning("video script failed: %s", [(a.outcome, (a.error or "")[:300]) for a in exc.attempts])
        raise ApiError(502, "upstream_error", "DeepSeek no pudo escribir el guion; inténtalo de nuevo.") from exc
    async with request.app.state.engine.begin() as conn:
        row = (await conn.execute(text(
            f"""insert into public.marketing_videos (series_id, format, script, created_by)
                values (:s, :f, cast(:sc as jsonb), :u) returning {FIELDS}"""),
            {"s": body.series_id, "f": body.format, "sc": result.value.model_dump_json(), "u": user_id})).mappings().one()
    return {"video": _out(row)}


class VideoEdit(BaseModel):
    format: Format | None = None
    script: VideoScript | None = None


@router.patch("/api/admin/marketing/videos/{video_id}")
async def edit_video(video_id: uuid.UUID, body: VideoEdit, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        row = (await conn.execute(text(
            f"""update public.marketing_videos set format = coalesce(:f, format),
                       script = coalesce(cast(:sc as jsonb), script), updated_at = now(),
                       -- the kept MP4 shows the old words or size: it is made again
                       mp4_key = case when coalesce(:f, format) = format and (cast(:sc as jsonb) is null
                                       or cast(:sc as jsonb) = script) then mp4_key end
                 where id = :id returning {FIELDS}"""),
            {"id": video_id, "f": body.format, "sc": body.script.model_dump_json() if body.script else None}
        )).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Ese video no existe.")
    return {"video": _out(row)}


@router.delete("/api/admin/marketing/videos/{video_id}", status_code=204)
async def delete_video(video_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        await conn.execute(text("delete from public.marketing_videos where id = :id"), {"id": video_id})


async def _video(conn, video_id) -> dict:
    row = (await conn.execute(text(f"select {FIELDS} from public.marketing_videos where id = :id"),
                              {"id": video_id})).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Ese video no existe.")
    return dict(row)


@router.post("/api/admin/marketing/videos/{video_id}/upload")
async def mp4_upload(video_id: uuid.UUID, request: Request, user_id: UserId):
    """Where the browser puts the MP4 it just rendered (straight to storage, never through this server)."""
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        await _video(conn, video_id)
    key = f"{video_id}/{uuid.uuid4().hex[:8]}.mp4"
    return {"key": key, "upload_url": await request.app.state.storage.upload_url(key, bucket=BUCKET)}


class Rendered(BaseModel):
    key: str = Field(pattern=r"^[0-9a-f-]{36}/[0-9a-f]{8}\.mp4$")


@router.post("/api/admin/marketing/videos/{video_id}/rendered")
async def mp4_rendered(video_id: uuid.UUID, body: Rendered, request: Request, user_id: UserId):
    """The MP4 is up: the video keeps it until its script or format changes."""
    if not body.key.startswith(f"{video_id}/"):
        raise ApiError(422, "invalid_request", "Ese archivo no es de este video.")
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id)
        row = (await conn.execute(text(
            f"""update public.marketing_videos set mp4_key = :k, rendered_at = now() where id = :id
                returning {FIELDS}"""), {"id": video_id, "k": body.key})).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "Ese video no existe.")
    return {"video": _out(row)}


@router.get("/api/admin/marketing/videos/{video_id}/mp4")
async def mp4_download(video_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        video = await _video(conn, video_id)
    if not video["mp4_key"]:
        raise ApiError(404, "not_found", "Este video aún no tiene MP4: créalo con «Crear MP4».")
    name = f"jelyx-{video['format'].replace(':', 'x')}-{str(video_id)[:6]}.mp4"
    return {"url": await request.app.state.storage.signed_url(video["mp4_key"], expires_in=300, download_name=name,
                                                              bucket=BUCKET)}
