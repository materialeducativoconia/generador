"""PDF exports: queue one, poll it, download through a short-lived signed URL (ARCHITECTURE.md §3.8–3.9)."""

import hashlib
import json
import re
import unicodedata
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from uuid6 import uuid7

from app.api.deps import current_user_id
from app.api.series import _jsonable, _own_series
from app.errors import ApiError

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]


class ExportOptions(BaseModel):
    paper: Literal["A4", "Letter", "8x10", "6x9"] = "A4"
    include_answer_key: bool = True
    edition: Literal["digital", "print"] = "digital"  # print: KDP-ready interior plus a separate cover wrap


@router.post("/api/series/{series_id}/exports", status_code=202)
async def create_export(series_id: uuid.UUID, body: ExportOptions, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        series = await _own_series(conn, series_id, user_id, lock=True)
        if series["status"] != "ready":
            raise ApiError(409, "invalid_state", "Todas las secciones deben estar generadas para exportar.")
        versions = (await conn.execute(text(
            "select id, content_version from public.lessons where series_id = :s order by position"
        ), {"s": series_id})).all()
        content_hash = hashlib.sha256(json.dumps({
            "title": series["title"], "lessons": [[str(i), v] for i, v in versions], "options": body.model_dump(),
            "cover": series["cover_key"], "design": _jsonable_design(series["design"]),
        }, sort_keys=True).encode()).hexdigest()
        existing = (await conn.execute(text(
            """select * from public.exports where series_id = :s and content_hash = :h and status <> 'failed'
                order by created_at desc limit 1"""), {"s": series_id, "h": content_hash})).mappings().one_or_none()
        if existing:
            code = 200 if existing["status"] == "succeeded" else 202
            return JSONResponse({"export": _export(existing)}, status_code=code)
        export_id, job_id = uuid7(), uuid7()
        await conn.execute(text(
            """insert into public.generation_jobs (id, user_id, series_id, kind, status, payload)
               values (:j, :u, :s, 'pdf_export', 'queued', cast(:p as jsonb))"""
        ), {"j": job_id, "u": user_id, "s": series_id, "p": json.dumps({"export_id": str(export_id)})})
        row = (await conn.execute(text(
            """insert into public.exports (id, series_id, user_id, job_id, status, options, content_hash)
               values (:e, :s, :u, :j, 'queued', cast(:o as jsonb), :h) returning *"""
        ), {"e": export_id, "s": series_id, "u": user_id, "j": job_id, "o": body.model_dump_json(),
            "h": content_hash})).mappings().one()
    return JSONResponse({"export": _export(row)}, status_code=202)


@router.get("/api/exports/{export_id}")
async def get_export(export_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        return _export(await _own_export(conn, export_id, user_id))


@router.get("/api/exports/{export_id}/file")
async def download_export(export_id: uuid.UUID, request: Request, user_id: UserId,
                          part: Literal["interior", "cover"] = "interior"):
    async with request.app.state.engine.connect() as conn:
        export = await _own_export(conn, export_id, user_id)
        title = (await conn.execute(text("select coalesce(title, topic) from public.series where id = :s"),
                                    {"s": export["series_id"]})).scalar_one()
    storage_key = export["cover_storage_key"] if part == "cover" else export["storage_key"]
    if export["status"] != "succeeded" or not storage_key:
        raise ApiError(404, "not_found", "Este PDF no está disponible.")
    # Signed at click time, so a link in the UI never expires. JSON rather than a 302: the browser
    # fetches this with a Bearer token, which a plain <a href> navigation could not send.
    name = f"{_slug(title)}-portada.pdf" if part == "cover" else f"{_slug(title)}.pdf"
    url = await request.app.state.storage.signed_url(storage_key, 60, name)
    return {"url": url}


async def _own_export(conn, export_id, user_id):
    row = (await conn.execute(text("select * from public.exports where id = :e and user_id = :u"),
                              {"e": export_id, "u": user_id})).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "not_found", "Este PDF no existe.")
    return row


def _export(row) -> dict:
    out = _jsonable(row)
    out.pop("user_id", None)
    done = out["status"] == "succeeded"
    out["download_url"] = f"/api/exports/{out['id']}/file" if done else None
    out["cover_download_url"] = f"/api/exports/{out['id']}/file?part=cover" if done and out.get("cover_storage_key") else None
    return out


def _slug(title: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:80] or "tomo"


def _jsonable_design(value):
    return json.loads(value) if isinstance(value, str) else value
