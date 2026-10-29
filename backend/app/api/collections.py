"""Collections: the user's tomes on one topic, grouped and ordered by level. Plus deleting a tome."""

import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from uuid6 import uuid7

from app.api.deps import current_user_id
from app.api.series import _own_series
from app.errors import ApiError

log = logging.getLogger("api")
router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]


class NewCollection(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    series_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)  # tomes to put in it, in order


class CollectionEdit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class Placement(BaseModel):
    collection_id: uuid.UUID | None  # None takes the tome out of its collection
    place: Literal["start", "end"] = "end"  # a lower level goes first, a higher one last


@router.get("/api/collections")
async def list_collections(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            """select c.id, c.name, c.description, c.created_at,
                      coalesce(array_agg(s.id order by s.collection_position, s.created_at)
                               filter (where s.id is not null), '{}') as series_ids
                 from public.collections c left join public.series s on s.collection_id = c.id
                where c.user_id = :u group by c.id order by c.created_at desc"""), {"u": user_id})).mappings().all()
    return {"collections": [{**r, "id": str(r["id"]), "created_at": r["created_at"].isoformat(),
                             "series_ids": [str(i) for i in r["series_ids"]]} for r in rows]}


@router.post("/api/collections", status_code=201)
async def create_collection(body: NewCollection, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        collection_id = uuid7()
        await conn.execute(text(
            "insert into public.collections (id, user_id, name, description) values (:id, :u, :n, :d)"),
            {"id": collection_id, "u": user_id, "n": body.name.strip(), "d": body.description})
        for position, series_id in enumerate(body.series_ids):
            await _own_series(conn, series_id, user_id)
            await _place(conn, series_id, collection_id, position)
    return {"collection": {"id": str(collection_id), "name": body.name.strip(), "description": body.description,
                           "series_ids": [str(i) for i in body.series_ids]}}


@router.patch("/api/collections/{collection_id}")
async def edit_collection(collection_id: uuid.UUID, body: CollectionEdit, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await own_collection(conn, collection_id, user_id)
        changes = body.model_dump(exclude_unset=True)
        if changes:
            await conn.execute(text(
                f"update public.collections set {', '.join(f'{k} = :{k}' for k in changes)} where id = :id"),
                {**changes, "id": collection_id})
    return {"ok": True}


@router.delete("/api/collections/{collection_id}", status_code=204)
async def delete_collection(collection_id: uuid.UUID, request: Request, user_id: UserId):
    """Only the grouping goes: its tomes stay in the library, loose."""
    async with request.app.state.engine.begin() as conn:
        await own_collection(conn, collection_id, user_id)
        await conn.execute(text("delete from public.collections where id = :id"), {"id": collection_id})


@router.put("/api/series/{series_id}/collection")
async def place_tome(series_id: uuid.UUID, body: Placement, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _own_series(conn, series_id, user_id, lock=True)
        if body.collection_id is None:
            await conn.execute(text(
                "update public.series set collection_id = null, collection_position = null where id = :s"),
                {"s": series_id})
            return {"collection_id": None}
        await own_collection(conn, body.collection_id, user_id)
        await place_in(conn, series_id, body.collection_id, body.place)
    return {"collection_id": str(body.collection_id)}


@router.delete("/api/series/{series_id}", status_code=204)
async def delete_tome(series_id: uuid.UUID, request: Request, user_id: UserId):
    """The tome, its sections, jobs and exports go (the database cascades); its files are removed from Storage.
    Pictures stay in the shared library: other tomes may use them. Cost logs stay for the accounts."""
    async with request.app.state.engine.begin() as conn:
        series = await _own_series(conn, series_id, user_id, lock=True)
        exports = (await conn.execute(text(
            "select storage_key, cover_storage_key from public.exports where series_id = :s"),
            {"s": series_id})).all()
        await conn.execute(text("delete from public.series where id = :s"), {"s": series_id})
    storage = request.app.state.storage
    if storage is None:
        return
    files = [(k, "exports") for row in exports for k in row if k]
    if series["cover_key"]:
        files.append((series["cover_key"], "covers"))
    for key, bucket in files:
        try:
            await storage.delete(key, bucket=bucket)
        except Exception:  # an orphaned file costs cents; the user asked for the tome to go
            log.warning("could not delete %s/%s", bucket, key)


async def own_collection(conn, collection_id, user_id):
    row = (await conn.execute(text("select * from public.collections where id = :id and user_id = :u"),
                              {"id": collection_id, "u": user_id})).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "not_found", "Esta colección no existe.")
    return row


async def place_in(conn, series_id, collection_id, place: str = "end") -> None:
    """Puts the tome first (a lower level) or last (a higher one) in the collection."""
    edge = (await conn.execute(text(
        f"select {'min' if place == 'start' else 'max'}(collection_position) from public.series "
        "where collection_id = :c and id <> :s"), {"c": collection_id, "s": series_id})).scalar()
    await _place(conn, series_id, collection_id,
                 0 if edge is None else edge - 1 if place == "start" else edge + 1)


async def _place(conn, series_id, collection_id, position: int) -> None:
    await conn.execute(text(
        "update public.series set collection_id = :c, collection_position = :p where id = :s"),
        {"c": collection_id, "p": position, "s": series_id})
