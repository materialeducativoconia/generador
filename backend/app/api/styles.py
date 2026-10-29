"""The user's style library: upload reference files, let the style job read them, use them in tomes."""

import json
import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from uuid6 import uuid7

from app import credits
from app.api.deps import current_user_id
from app.errors import ApiError
from app.plans import STYLE

router = APIRouter()
log = logging.getLogger("api")
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
EXTENSION = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_BYTES = 50 * 1024 * 1024
MAX_STYLES = 30


class NewStyle(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    content_type: Literal["application/pdf", "image/png", "image/jpeg", "image/webp"]
    size: int = Field(gt=0)


@router.post("/api/styles", status_code=201)
async def create_style(body: NewStyle, request: Request, user_id: UserId):
    """Step 1 of an upload: a style row and a one-off URL the browser PUTs the file to."""
    if body.size > MAX_BYTES:
        raise ApiError(422, "too_large", "El archivo pesa más de 50 MB.")
    style_id = uuid7()
    key = f"{user_id}/{style_id}/source.{EXTENSION[body.content_type]}"
    async with request.app.state.engine.begin() as conn:
        acc = await credits.require(conn, user_id, "styles", "La biblioteca de estilos")
        limit = min(acc.plan.styles, MAX_STYLES)
        count = (await conn.execute(text("select count(*) from public.styles where user_id = :u"),
                                    {"u": user_id})).scalar_one()
        if count >= limit:
            raise ApiError(409, "too_many", f"Tu plan admite {limit} estilos; borra alguno o sube de plan.")
        storage = _storage(request)
        await conn.execute(text(
            """insert into public.styles (id, user_id, name, source_key, source_type)
               values (:id, :u, :n, :k, :t)"""), {"id": style_id, "u": user_id, "n": body.name.strip(), "k": key,
                                                  "t": body.content_type})
    return {"style": {"id": str(style_id), "name": body.name.strip(), "status": "uploading"},
            "upload_url": await storage.upload_url(key, bucket="references")}


@router.post("/api/styles/{style_id}/analyze", status_code=202)
async def analyze_style(style_id: uuid.UUID, request: Request, user_id: UserId):
    """Step 2: the file is in storage; queue the Curator and Style analyst."""
    async with request.app.state.engine.begin() as conn:
        style = await _own(conn, style_id, user_id, lock=True)
        if style["status"] == "analyzing":
            raise ApiError(409, "invalid_state", "Este estilo ya se está analizando.")
        await conn.execute(text("update public.styles set status = 'analyzing', error = null where id = :id"),
                           {"id": style_id})
        job_id = uuid7()
        await conn.execute(text(
            """insert into public.generation_jobs (id, user_id, kind, status, payload, max_attempts)
               values (:j, :u, 'style', 'queued', cast(:p as jsonb), 3)"""),
            {"j": job_id, "u": user_id, "p": json.dumps({"style_id": str(style_id)})})
        await credits.charge(conn, user_id, STYLE, "Analizar estilo", job_id)
    return {"style": {"id": str(style_id), "status": "analyzing"}}


@router.get("/api/styles")
async def list_styles(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            """select id, name, status, pages, spec, design, error, created_at from public.styles
                where user_id = :u order by created_at desc"""), {"u": user_id})).mappings().all()
    storage = request.app.state.storage
    keys = [k for r in rows for k in (_json(r["pages"]) or [])[:3]]
    urls = await storage.signed_urls(keys, bucket="references") if storage is not None else {}
    out = []
    for r in rows:
        spec, design, pages = _json(r["spec"]) or {}, _json(r["design"]), _json(r["pages"]) or []
        previews = [urls[k] for k in pages[:3] if k in urls]
        out.append({"id": str(r["id"]), "name": r["name"], "status": r["status"], "error": r["error"],
                    "created_at": r["created_at"].isoformat(), "previews": previews, "design": design,
                    "score": spec.get("score"), "traits": spec.get("traits", []), "suits": spec.get("suits")})
    return {"styles": out, "poll_after_ms": 4000 if any(s["status"] == "analyzing" for s in out) else None}


@router.delete("/api/styles/{style_id}", status_code=204)
async def delete_style(style_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        style = await _own(conn, style_id, user_id, lock=True)
        await conn.execute(text("delete from public.styles where id = :id"), {"id": style_id})
    storage = request.app.state.storage
    if storage is not None:  # tomes keep their copy of the design; only the files go
        for key in [style["source_key"], *(_json(style["pages"]) or [])]:
            try:
                await storage.delete(key, bucket="references")
            except Exception:  # an orphaned file costs cents; the user asked for the style to go
                log.warning("could not delete %s", key)


async def _own(conn, style_id, user_id, lock=False):
    row = (await conn.execute(text(
        "select * from public.styles where id = :id and user_id = :u" + (" for update" if lock else "")),
        {"id": style_id, "u": user_id})).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "not_found", "Este estilo no existe.")
    return row


def _storage(request: Request):
    storage = request.app.state.storage
    if storage is None:
        raise ApiError(503, "not_configured", "El almacenamiento no está configurado.")
    return storage


def _json(value):
    return json.loads(value) if isinstance(value, str) else value
