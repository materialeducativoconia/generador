"""Another version of a tome (paid plans): the same book in another illustration style, the story or content changed,
or the next tome of its series. The original is never touched; the new tome remembers where it came from."""

import json
import math
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from uuid6 import uuid7

from app import credits
from app.api.deps import current_user_id
from app.api.series import NewTome, _created, _new_tome, _own_series, _parse, _require_active
from app.content import PLATE_GENRES, Design, SectionContent
from app.errors import ApiError
from app.house_styles import apply
from app.jobs import enqueue_cover, only_cited
from app.layout import lay_out
from app.plans import COVER, PAID

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
HouseKey = Literal["enciclopedia", "acuarela", "gouache", "collage", "crayon", "didactico"]
FORMATS = ("picture_book", "story_book", "coloring_book", "worksheets", "tutorial", "lesson_series")


class NewVersion(BaseModel):
    mode: Literal["style", "story", "next"]
    request: str | None = Field(default=None, min_length=3, max_length=2000)  # the request, edited
    changes: str | None = Field(default=None, max_length=2000)  # what to change, for the Architect and the Narrator
    house_style: HouseKey | None = None
    keep_cast: bool = True


@router.post("/api/series/{series_id}/versions", status_code=202)
async def new_version(series_id: uuid.UUID, body: NewVersion, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _require_active(conn, user_id)
        src = await _own_series(conn, series_id, user_id)
        acc = await credits.account(conn, user_id)
        if acc.plan_key not in PAID:
            raise ApiError(402, "plan_required", "Hacer otra versión de un tomo está incluido en los planes de pago.",
                           {"feature": "versions", "plan": acc.plan_key})
        if src["status"] in ("outlining", "outline_failed"):
            raise ApiError(409, "not_ready", "Espera a que el tomo tenga su plan antes de hacer otra versión.")
        house = body.house_style or src["house_style"]
        design = _design(src, house)
        cast = _cast(src, house) if body.keep_cast or body.mode == "style" else None
        if body.mode == "style":
            return await _restyle(conn, src, user_id, house, design, cast)
        return await _rewrite(conn, request, src, user_id, body, house, design, cast)


def _design(src, house: str | None) -> dict | None:
    """The tome's look, kept, wearing the version's illustration style."""
    if not src["design"]:
        return None
    design = Design.model_validate(_parse(src["design"]))
    if house and house != design.house_style:
        design = apply(design, house)
    return design.model_dump(mode="json")


def _cast(src, house: str | None) -> list[dict] | None:
    """The same characters; in another style each one is redrawn in it before the cover is painted."""
    cast = _parse(src["cast"])
    if not cast:
        return None
    restyle = bool(house) and house != src["house_style"]
    return [{**c, "restyle": True} if restyle and c.get("character_id") else c for c in cast]


async def _restyle(conn, src, user_id, house: str | None, design: dict | None, cast: list[dict] | None):
    """The same text, painted again: a new tome with the written sections copied and every illustration cleared,
    then a new cover (which restyles the cast) and the plates after it."""
    if src["status"] != "ready":
        raise ApiError(409, "not_ready", "Termina de generar este tomo antes de pintarlo en otro estilo.")
    if not house or house == src["house_style"]:
        raise ApiError(422, "invalid_request", "Elige un estilo de ilustración distinto al de este tomo.")
    lessons = (await conn.execute(text(
        """select position, title, objectives, key_points, letters, pages, content_json, review
             from public.lessons where series_id = :s order by position"""), {"s": src["id"]})).mappings().all()
    plates = 0
    copies = []
    for lesson in lessons:
        content = _parse(lesson["content_json"]) or {"blocks": []}
        for b in content.get("blocks", []):
            if b.get("type") == "image" and b.get("kind") == "illustration":
                plates += 1
                b.pop("asset_id", None)
        if src["genre"] in PLATE_GENRES and any(b.get("size") == "plate" and not b.get("layout")
                                                for b in content.get("blocks", [])):
            # A tome from before the Layout designer: its plates get their compositions now, before painting.
            laid = SectionContent.model_validate(content)
            lay_out(laid, position=lesson["position"], pages=lesson["pages"], house_style=house,
                    story=src["genre"] == "story_book")
            content = laid.model_dump(mode="json", exclude_none=True)
        copies.append({**lesson, "content_json": content})
    research = _parse(src["research"])
    if research and research.get("facts") and research.get("sources"):  # sources no fact came from are dropped
        research["facts"], research["sources"] = only_cited(research["facts"], research["sources"])
    new_id = uuid7()
    await conn.execute(text(
        """insert into public.series (id, user_id, title, topic, audience, language, lesson_count, extra_instructions,
                                      status, page_target, genre, plan, research, design, "cast", house_style,
                                      guide_id, identity_id, style_id, outline_approved_at, source_id, variant)
           select :id, user_id, title, topic, audience, language, lesson_count, extra_instructions, 'generating',
                  page_target, genre, plan, cast(:research as jsonb), cast(:design as jsonb), cast(:cast as jsonb), :house, guide_id,
                  identity_id, style_id, now(), id, 'style'
             from public.series where id = :src"""),
        {"id": new_id, "src": src["id"], "house": house, "design": json.dumps(design) if design else None,
         "research": json.dumps(research) if research else None,
         "cast": json.dumps(cast) if cast is not None else None})
    for lesson in copies:
        await conn.execute(text(
            """insert into public.lessons (series_id, position, title, objectives, key_points, letters, pages,
                                           content_json, review, status)
               values (:s, :p, :t, cast(:o as jsonb), cast(:k as jsonb), cast(:lt as jsonb), :pg, cast(:c as jsonb),
                       cast(:r as jsonb), 'generated')"""),
            {"s": new_id, "p": lesson["position"], "t": lesson["title"], "o": json.dumps(_parse(lesson["objectives"])),
             "k": json.dumps(_parse(lesson["key_points"])), "lt": json.dumps(_parse(lesson["letters"]) or []),
             "pg": lesson["pages"], "c": json.dumps(lesson["content_json"]),
             "r": json.dumps(_parse(lesson["review"])) if lesson["review"] else None})
    await conn.execute(text("select public.refresh_series_status(:s)"), {"s": new_id})
    job_id = await enqueue_cover(conn, user_id, new_id, illustrate=True)
    await credits.charge(conn, user_id, COVER, "Portada en otro estilo", job_id)
    if plates:  # repainting a plate costs half a written and painted page
        await credits.charge(conn, user_id, math.ceil(plates / 2), "Ilustraciones en otro estilo", job_id)
    return await _created(conn, new_id, job_id)


async def _rewrite(conn, request: Request, src, user_id, body: NewVersion, house: str | None, design: dict | None,
                   cast: list[dict] | None):
    """A new tome from the edited request: the story or content changed, or the next tome of the series. It keeps
    the look, the style and (unless asked otherwise) the characters; its outline opens for review as any tome's."""
    title = src["title"] or src["topic"]
    sections = (await conn.execute(text(
        "select title from public.lessons where series_id = :s order by position"), {"s": src["id"]})).scalars().all()
    changes = (body.changes or "").strip()
    if body.mode == "story":
        if not changes and not body.request:
            raise ApiError(422, "invalid_request", "Cuéntanos qué quieres cambiar en esta versión.")
        extra = f"Esta es una nueva versión de «{title}»." + (f" Cambios que pide el usuario: {changes}" if changes else "")
        collection_id = None
    else:
        plan = _parse(src["plan"]) or {}
        story = plan.get("story") or {}
        told = f" La historia anterior: {story['protagonist']}." if story.get("protagonist") else ""
        extra = (f"Este tomo es el siguiente de la serie, después de «{title}», con los mismos personajes y el mismo "
                 f"estilo. Lo que ya cubrió: {'; '.join(sections)}.{told} No repitas esos temas: continúa desde ahí, "
                 "un paso más allá." + (f" Lo que pide el usuario para este tomo: {changes}" if changes else ""))
        collection_id = src["collection_id"] or await _start_collection(conn, src, user_id, title)
    if cast:  # the Architect titles the acts: it must know who the drawn characters are, not guess from a name
        extra += " Personajes ya dibujados (siguen siendo lo que son): " + "; ".join(
            f"{c['name']} ({c.get('archetype') or 'personaje'})" for c in cast if c.get("name")) + "."
    extra = "\n".join(filter(None, [src["extra_instructions"], extra]))[:2000]
    audience = (_parse(src["audience"]) or {}).get("label", "")
    pages = src["page_target"] or max(len(sections), 1)
    new = NewTome(request=body.request or src["topic"], audience=audience, section_count=min(src["lesson_count"] or 1, pages),
                  page_count=pages, extra_instructions=extra, collection_id=collection_id, place="end",
                  format=src["genre"] if src["genre"] in FORMATS else "auto", house_style=house)
    return await _new_tome(conn, new, request, user_id, version={
        "source_id": src["id"], "variant": body.mode, "cast": cast, "design": design})


async def _start_collection(conn, src, user_id, name: str):
    """A tome without a series starts one, named after itself and first in it, so its next tome joins it."""
    collection_id = uuid7()
    await conn.execute(text("insert into public.collections (id, user_id, name) values (:id, :u, :n)"),
                       {"id": collection_id, "u": user_id, "n": name[:120]})
    await conn.execute(text("update public.series set collection_id = :c, collection_position = 0 where id = :s"),
                       {"c": collection_id, "s": src["id"]})
    return collection_id
