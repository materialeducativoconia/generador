"""Mis identidades: the user's editorial lines. The identity job proposes three, the user keeps one and applies
it to a collection, so all its tomes share the look, the seal, the voice and the mascot."""

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from uuid6 import uuid7

from app.api.collections import own_collection
from app.api.deps import current_user_id
from app.api.series import _parse, apply_design
from app.content import Design
from app.errors import ApiError
from app.identity import mark_svg
from app.themes import theme_for

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
MAX_IDENTITIES = 20


class NewIdentity(BaseModel):
    about: str = Field(min_length=3, max_length=600)  # what the user publishes
    audience: str | None = Field(default=None, max_length=200)
    personality: str | None = Field(default=None, max_length=200)  # a few words: «cálida, divertida, clara»
    language: str = Field(default="es", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    style_id: uuid.UUID | None = None  # a ready library style to draw inspiration from


class Choice(BaseModel):
    index: int = Field(ge=0, le=2)


class BrandEdit(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=40)
    tagline: str | None = Field(default=None, max_length=90)
    voice: str | None = Field(default=None, max_length=400)


class IdentityPick(BaseModel):
    identity_id: uuid.UUID | None  # None: the collection's tomes keep their looks but no longer follow a line


@router.post("/api/identities", status_code=202)
async def create_identity(body: NewIdentity, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        count = (await conn.execute(text("select count(*) from public.identities where user_id = :u"),
                                    {"u": user_id})).scalar_one()
        if count >= MAX_IDENTITIES:
            raise ApiError(409, "too_many", f"Admites {MAX_IDENTITIES} identidades; borra alguna.")
        identity_id = uuid7()
        brief = body.model_dump(mode="json")
        await conn.execute(text(
            "insert into public.identities (id, user_id, brief) values (:id, :u, cast(:b as jsonb))"),
            {"id": identity_id, "u": user_id, "b": json.dumps(brief)})
        await _enqueue(conn, user_id, identity_id)
    return {"identity": {"id": str(identity_id), "status": "generating"}}


@router.post("/api/identities/{identity_id}/propose", status_code=202)
async def propose_again(identity_id: uuid.UUID, request: Request, user_id: UserId):
    """Three new candidates for the same brief (the chosen look, if any, stays until the user picks again)."""
    async with request.app.state.engine.begin() as conn:
        row = await _own(conn, identity_id, user_id, lock=True)
        if row["status"] == "generating":
            raise ApiError(409, "invalid_state", "Ya estamos proponiendo identidades.")
        await conn.execute(text("update public.identities set status = 'generating', error = null where id = :id"),
                           {"id": identity_id})
        await _enqueue(conn, user_id, identity_id)
    return {"identity": {"id": str(identity_id), "status": "generating"}}


@router.get("/api/identities")
async def list_identities(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            """select i.id, i.status, i.brief, i.candidates, i.design, i.error, i.created_at,
                      coalesce(array_agg(c.id) filter (where c.id is not null), '{}') as collection_ids
                 from public.identities i left join public.collections c on c.identity_id = i.id
                where i.user_id = :u group by i.id order by i.created_at desc"""), {"u": user_id})).mappings().all()
    out = [{"id": str(r["id"]), "status": r["status"], "brief": _parse(r["brief"]), "error": r["error"],
            "created_at": r["created_at"].isoformat(), "collection_ids": [str(c) for c in r["collection_ids"]],
            "design": _show(_parse(r["design"])), "candidates": [_show(c) for c in _parse(r["candidates"]) or []]}
           for r in rows]
    return {"identities": out, "poll_after_ms": 4000 if any(i["status"] == "generating" for i in out) else None}


@router.post("/api/identities/{identity_id}/choose")
async def choose(identity_id: uuid.UUID, body: Choice, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        row = await _own(conn, identity_id, user_id, lock=True)
        candidates = _parse(row["candidates"]) or []
        if row["status"] == "generating" or body.index >= len(candidates):
            raise ApiError(409, "invalid_state", "Aún no hay propuestas para elegir.")
        design = Design.model_validate(candidates[body.index])
        await conn.execute(text(
            "update public.identities set status = 'ready', design = cast(:d as jsonb) where id = :id"),
            {"id": identity_id, "d": design.model_dump_json()})
        await _reapply(conn, user_id, identity_id, design)
    return {"identity": {"id": str(identity_id), "status": "ready", "design": _show(design.model_dump())}}


@router.patch("/api/identities/{identity_id}")
async def edit_brand(identity_id: uuid.UUID, body: BrandEdit, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        row = await _own(conn, identity_id, user_id, lock=True)
        if row["status"] != "ready" and not row["design"]:
            raise ApiError(409, "invalid_state", "Elige primero una de las propuestas.")
        design = Design.model_validate(_parse(row["design"]))
        design.brand = design.brand.model_copy(update=body.model_dump(exclude_unset=True, exclude_none=True))
        await conn.execute(text("update public.identities set design = cast(:d as jsonb) where id = :id"),
                           {"id": identity_id, "d": design.model_dump_json()})
        await _reapply(conn, user_id, identity_id, design)
    return {"design": _show(design.model_dump())}


@router.delete("/api/identities/{identity_id}", status_code=204)
async def delete_identity(identity_id: uuid.UUID, request: Request, user_id: UserId):
    """Its tomes keep their copy of the look; collections stop following it."""
    async with request.app.state.engine.begin() as conn:
        await _own(conn, identity_id, user_id, lock=True)
        await conn.execute(text("delete from public.identities where id = :id"), {"id": identity_id})


@router.put("/api/collections/{collection_id}/identity")
async def set_collection_identity(collection_id: uuid.UUID, body: IdentityPick, request: Request, user_id: UserId):
    """One identity per collection: every tome in it, and every level added later, takes the line's look."""
    async with request.app.state.engine.begin() as conn:
        await own_collection(conn, collection_id, user_id)
        design = None
        if body.identity_id:
            row = await _own(conn, body.identity_id, user_id)
            if row["status"] != "ready" and not row["design"]:
                raise ApiError(409, "invalid_state", "Esa identidad aún no está lista.")
            design = Design.model_validate(_parse(row["design"]))
        await conn.execute(text("update public.collections set identity_id = :i where id = :c"),
                           {"c": collection_id, "i": body.identity_id})
        if design:
            await apply_to_collection(conn, user_id, collection_id, design)
    return {"identity_id": str(body.identity_id) if body.identity_id else None}


async def apply_to_collection(conn, user_id, collection_id, design: Design) -> None:
    rows = (await conn.execute(text(
        "select id, design from public.series where collection_id = :c for update"), {"c": collection_id})).all()
    for series_id, current in rows:
        await apply_design(conn, user_id, series_id, Design.model_validate(_parse(current)) if current else None,
                           design)


async def _reapply(conn, user_id, identity_id, design: Design) -> None:
    """A new pick or a renamed imprint reaches every tome that follows the identity."""
    rows = (await conn.execute(text(
        "select id, design from public.series where identity_id = :i for update"), {"i": identity_id})).all()
    for series_id, current in rows:
        await apply_design(conn, user_id, series_id, Design.model_validate(_parse(current)) if current else None,
                           design)


def _show(design: dict | None) -> dict | None:
    """The design plus its seal, so the web shows exactly what the PDF prints."""
    if not design or not design.get("brand"):
        return design
    d = Design.model_validate(design)
    return {**design, "mark_svg": mark_svg(d.brand, d.palette[2], theme_for(d).head)}


async def _enqueue(conn, user_id, identity_id) -> None:
    await conn.execute(text(
        """insert into public.generation_jobs (user_id, kind, status, payload, max_attempts)
           values (:u, 'identity', 'queued', cast(:p as jsonb), 3)"""),
        {"u": user_id, "p": json.dumps({"identity_id": str(identity_id)})})


async def _own(conn, identity_id, user_id, lock=False):
    row = (await conn.execute(text(
        "select * from public.identities where id = :id and user_id = :u" + (" for update" if lock else "")),
        {"id": identity_id, "u": user_id})).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "not_found", "Esta identidad no existe.")
    return row
