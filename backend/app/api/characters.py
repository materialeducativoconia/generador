"""The character library: the guides every picture book can borrow, with their model sheets, and the character
maker (plans that sell): describe a character, the worker designs it and paints its sheet."""

import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from uuid6 import uuid7

from app import credits
from app.api.deps import current_user_id
from app.errors import ApiError
from app.plans import CHARACTER

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
MAX_OWN = 60


@router.get("/api/characters")
async def list_characters(request: Request, user_id: UserId):
    """The shared library and the user's own characters (also those still painting), most used first."""
    async with request.app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            """select id::text, name, role, archetype, personality, signature, palette, topics, sheet_key, use_count,
                      based_on::text, (user_id = :u) is true as mine, shared, status, error, description,
                      (select coalesce(array_agg(style), '{}') from public.character_sheets s
                        where s.character_id = c.id) as styles
                 from public.characters c
                where (sheet_key is not null and status = 'ready' and shared) or user_id = :u
                order by (user_id = :u) is true desc, use_count desc, created_at desc limit 200"""),
            {"u": user_id})).mappings().all()
    return {"characters": [sheet_url(dict(r), request) for r in rows]}


class NewCharacter(BaseModel):
    description: str = Field(min_length=5, max_length=600)
    based_on: uuid.UUID | None = None  # a library character to derive from (same body and face)
    style: Literal["enciclopedia", "acuarela", "gouache", "collage", "crayon", "didactico"] | None = None


@router.post("/api/characters", status_code=202)
async def create_character(body: NewCharacter, request: Request, user_id: UserId):
    """A private character for the user's tomes: queued for the designer and the Illustrator."""
    async with request.app.state.engine.begin() as conn:
        await credits.require(conn, user_id, "commercial", "Crear tus propios personajes")
        own = (await conn.execute(text("select count(*) from public.characters where user_id = :u"),
                                  {"u": user_id})).scalar_one()
        if own >= MAX_OWN:
            raise ApiError(409, "too_many", f"Tienes {MAX_OWN} personajes; borra alguno para crear otro.")
        if body.based_on and not (await conn.execute(text(
                "select 1 from public.characters where id = :id and status = 'ready' and (shared or user_id = :u)"),
                {"id": body.based_on, "u": user_id})).first():
            raise ApiError(404, "not_found", "No existe ese personaje base.")
        char_id, job_id = uuid.uuid4(), uuid7()
        await conn.execute(text(
            """insert into public.characters (id, name, description, based_on, user_id, shared, status, use_count)
               values (:id, 'Nuevo personaje', :d, :b, :u, false, 'painting', 0)"""),
            {"id": char_id, "d": body.description.strip(), "b": body.based_on, "u": user_id})
        await conn.execute(text(
            """insert into public.generation_jobs (id, user_id, kind, status, payload, max_attempts)
               values (:j, :u, 'character', 'queued', cast(:p as jsonb), 2)"""),
            {"j": job_id, "u": user_id, "p": json.dumps({"character_id": str(char_id), "style": body.style})})
        await credits.charge(conn, user_id, CHARACTER, "Crear personaje", job_id)
    return {"character": {"id": str(char_id), "status": "painting"}}


@router.delete("/api/characters/{character_id}", status_code=204)
async def delete_character(character_id: uuid.UUID, request: Request, user_id: UserId):
    """Only the user's own characters; tomes that used one keep their pictures."""
    async with request.app.state.engine.begin() as conn:
        gone = (await conn.execute(text(
            "delete from public.characters where id = :id and user_id = :u and not seed returning id"),
            {"id": character_id, "u": user_id})).first()
    if gone is None:
        raise ApiError(404, "not_found", "No existe ese personaje.")


def sheet_url(c: dict, request: Request) -> dict:
    key = c.pop("sheet_key", None)
    storage = request.app.state.storage
    c["sheet_url"] = storage.public_url(key, bucket="images") if key and storage else None
    return c
