"""The character library: the guides every picture book can borrow, with their model sheets."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from app.api.deps import current_user_id

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]


@router.get("/api/characters")
async def list_characters(request: Request, user_id: UserId):
    """The shared library and the user's own characters, most used first."""
    async with request.app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            """select id::text, name, role, archetype, personality, signature, palette, topics, sheet_key, use_count,
                      based_on::text, user_id = :u as mine, shared
                 from public.characters where sheet_key is not null and (shared or user_id = :u)
                order by use_count desc, created_at limit 200"""), {"u": user_id})).mappings().all()
    return {"characters": [sheet_url(dict(r), request) for r in rows]}


def sheet_url(c: dict, request: Request) -> dict:
    key = c.pop("sheet_key", None)
    storage = request.app.state.storage
    c["sheet_url"] = storage.public_url(key, bucket="images") if key and storage else None
    return c
