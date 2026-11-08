"""Editor de páginas: an illustrated book's page, seen exactly as the PDF prints it, its words and composition
edited in place, and its picture painted again from an instruction."""

import asyncio
import base64
import hashlib
import io
import json
import uuid
from collections import OrderedDict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app import credits
from app.api.deps import current_user_id
from app.api.series import _own_lesson, _parse
from app.content import PLATE_GENRES, Design, Image, SectionContent, Spot
from app.errors import ApiError
from app.jobs import _queue_artwork
from app.render import note_spots, question_low

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
EDITABLE = ("generated", "edited", "approved")
REPAINT = 1  # credits: one picture, painted again
SCREEN_PX = 1400  # the longest side of a picture in the preview: sharp at 110 dpi on a spread
RENDERED = 64  # pages kept rendered in memory, about 200 KB each
_rendered: OrderedDict[str, tuple[str, dict]] = OrderedDict()
PAPERS = Literal["17x21", "8x10", "A4", "Letter", "6x9"]


class PageEdit(BaseModel):
    narration: str | None = Field(default=None, max_length=700)
    question: str | None = Field(default=None, max_length=300)
    answer: str | None = Field(default=None, max_length=500)
    notes: list[Annotated[str, Field(max_length=140)]] | None = Field(default=None, max_length=4)
    find: str | None = Field(default=None, max_length=300)
    layout: Literal["bleed", "band", "vignette", "spread"] | None = None
    place: dict[Literal["q", "f", "n0", "n1", "n2", "n3"], Spot] | None = None  # {} back to the automatic layout
    inset: None = None  # null removes the plate's diagram; one is never written here


class Repaint(BaseModel):
    instructions: str = Field(min_length=3, max_length=400)


async def _plate(conn, lesson_id, block_id: str, user_id, lock=False):
    lesson = await _own_lesson(conn, lesson_id, user_id, lock=lock)
    series = (await conn.execute(text("select * from public.series where id = :s"),
                                 {"s": lesson["series_id"]})).mappings().one()
    if series["genre"] not in PLATE_GENRES:
        raise ApiError(422, "invalid_request", "El editor de páginas es para libros ilustrados y cuentos.")
    content = _parse(lesson["content_json"]) or {"blocks": []}
    block = next((b for b in content.get("blocks", []) if b.get("id") == block_id and b.get("size") == "plate"), None)
    if block is None:
        raise ApiError(404, "not_found", "Esta página no existe.")
    return lesson, series, content, block


@router.get("/api/lessons/{lesson_id}/pages/{block_id}/preview")
async def page_preview(lesson_id: uuid.UUID, block_id: str, request: Request, user_id: UserId,
                       paper: PAPERS = "17x21"):
    """The page rendered by the PDF's own layout, as a picture (a spread: both pages side by side)."""
    async with request.app.state.engine.connect() as conn:
        lesson, series, _, block = await _plate(conn, lesson_id, block_id, user_id)
        asset = (await conn.execute(text(
            "select storage_key, review->'busy' as busy from public.assets where id = cast(:a as uuid)"),
            {"a": block["asset_id"]})).mappings().one_or_none() if block.get("asset_id") else None
    # Everything the printed page depends on: the same page asked again (going back and forth) is not rendered again.
    key = hashlib.sha256(json.dumps([block, paper, lesson["position"], lesson["title"], str(asset and asset["busy"])] +
                                    [str(series[c]) for c in ("title", "topic", "genre", "audience", "cover", "design")],
                                    sort_keys=True, default=str).encode()).hexdigest()
    # Where each fact sits on the printed page, so the editor lays its draggable copy out the same way.
    plate, cells = Image.model_validate(block), _parse(asset["busy"]) if asset and asset["busy"] else None
    layout = {"spots": note_spots(plate, cells), "low": question_low(plate, cells)}
    if key in _rendered:
        _rendered.move_to_end(key)
        image, looks = _rendered[key]
        return {"image": image, "looks": looks, **layout}
    images, busy = {}, {}
    if asset:
        try:
            images[block["asset_id"]] = (await request.app.state.storage.download(asset["storage_key"], bucket="images"),
                                         "image/jpeg" if asset["storage_key"].endswith(".jpg") else "image/png")
        except Exception:  # prints as its placeholder
            pass
        if asset["busy"]:
            busy[block["asset_id"]] = _parse(asset["busy"])
    jpeg, looks = await asyncio.wait_for(asyncio.to_thread(_render_page, series, lesson, block, images, busy, paper), 60)
    _rendered[key] = ("data:image/jpeg;base64," + base64.b64encode(jpeg).decode(), looks)
    while len(_rendered) > RENDERED:
        _rendered.popitem(last=False)
    return {"image": _rendered[key][0], "looks": looks, **layout}


def _render_page(series, lesson, block: dict, images: dict, busy: dict, paper: str) -> tuple[bytes, dict[str, str]]:
    """The page as a JPEG, and how each text of a bleed plate lies on the picture (for the editor's draggable copy)."""
    import pypdfium2
    from PIL import Image as Picture

    from app.printing import page_geometry
    from app.render import Tome, TomeSection, _document, _pages, render_html, text_looks, theme_colors

    # The screen needs a fraction of a 4K painting: shrunk first, the page renders in a second or two, not thirty.
    images = {k: _screen_size(data) for k, (data, _) in images.items()}
    design = Design.model_validate(_parse(series["design"])) if series["design"] else None
    tome = Tome(title=series["title"] or series["topic"], genre=series["genre"],
                audience=(_parse(series["audience"]) or {}).get("label", ""), author=None,
                sections=[TomeSection(position=lesson["position"], title=lesson["title"],
                                      content=SectionContent.model_validate({"blocks": [block]}))],
                palette=(_parse(series["cover"]) or {}).get("palette"), design=design, images=images, busy=busy)
    document = _document(render_html(tome, paper=paper, include_answer_key=False))
    key = f"{lesson['position']}:{block['id']}"
    first = next((i for i, p in enumerate(_pages(document)) if p["first"] == key), 1)
    pdf = pypdfium2.PdfDocument(document.write_pdf())
    count = 2 if block.get("layout") == "spread" and first + 1 < len(pdf) else 1
    pages = [pdf[i].render(scale=110 / 72).to_pil() for i in range(first, first + count)]
    out = pages[0]
    if count == 2:
        out = Picture.new("RGB", (pages[0].width + pages[1].width, pages[0].height), "white")
        out.paste(pages[0], (0, 0))
        out.paste(pages[1], (pages[0].width, 0))
    buffer = io.BytesIO()
    out.convert("RGB").save(buffer, "JPEG", quality=85)
    plate = tome.sections[0].content.blocks[0]
    geo = page_geometry(paper, print_edition=False)
    looks = text_looks(plate, tome, (geo.w, geo.h), theme_colors(design, tome.palette)[1]["ink"]) \
        if (plate.layout or "bleed") == "bleed" else {}
    return buffer.getvalue(), looks


def _screen_size(data: bytes) -> tuple[bytes, str]:
    from PIL import Image as Picture

    picture = Picture.open(io.BytesIO(data))
    picture.draft("RGB", (SCREEN_PX, SCREEN_PX))  # a JPEG decodes straight at a smaller scale
    picture = picture.convert("RGB")
    picture.thumbnail((SCREEN_PX, SCREEN_PX))
    buffer = io.BytesIO()
    picture.save(buffer, "JPEG", quality=85)
    return buffer.getvalue(), "image/jpeg"


@router.patch("/api/lessons/{lesson_id}/pages/{block_id}")
async def edit_page(lesson_id: uuid.UUID, block_id: str, body: PageEdit, request: Request, user_id: UserId):
    """The page's words and composition, as the user writes them: no AI, no credits."""
    async with request.app.state.engine.begin() as conn:
        lesson, _, content, block = await _plate(conn, lesson_id, block_id, user_id, lock=True)
        if lesson["status"] not in EDITABLE:
            raise ApiError(409, "invalid_state", "Espera a que la sección termine de generarse.")
        for field, value in body.model_dump(exclude_unset=True).items():
            if isinstance(value, str):
                value = value.strip() or None
            if field == "notes":
                value = [n.strip() for n in value or [] if n.strip()]
            if value in (None, [], {}):
                block.pop(field, None)
            else:
                block[field] = value
        try:
            Image.model_validate(block)
        except ValidationError as exc:
            raise ApiError(422, "validation_error", "Revisa el texto de la página.", {"errors": exc.errors()}) from exc
        await conn.execute(text(
            """update public.lessons set content_json = cast(:c as jsonb), content_version = content_version + 1,
                      status = 'edited' where id = :l"""), {"c": json.dumps(content), "l": lesson_id})
    return {"block": block}


@router.post("/api/lessons/{lesson_id}/pages/{block_id}/repaint", status_code=202)
async def repaint_page(lesson_id: uuid.UUID, block_id: str, body: Repaint, request: Request, user_id: UserId):
    """Only this page's picture, painted again with the user's instruction; the rest of the book stays."""
    async with request.app.state.engine.begin() as conn:
        lesson, series, content, block = await _plate(conn, lesson_id, block_id, user_id, lock=True)
        if series["status"] != "ready" or lesson["status"] not in EDITABLE:
            raise ApiError(409, "invalid_state", "Espera a que el libro termine de ilustrarse.")
        ask = f" (Cambio pedido por el usuario: {body.instructions.strip()})"
        block["subject"] = block["subject"].split(" (Cambio pedido por el usuario:")[0][:700 - len(ask)] + ask
        block.pop("asset_id", None)
        await conn.execute(text(
            """update public.lessons set content_json = cast(:c as jsonb), content_version = content_version + 1,
                      status = 'edited' where id = :l"""), {"c": json.dumps(content), "l": lesson_id})
        # The Art director's prompt for this page would repaint the old picture: it falls back to the new subject.
        await conn.execute(text("update public.series set art = art #- cast(:path as text[]) where id = :s"),
                           {"s": series["id"], "path": ["prompts", f"{lesson['position']}:{block_id}"]})
        await _queue_artwork(conn, {"user_id": user_id, "series_id": series["id"]})
        job_id = (await conn.execute(text(
            """select id from public.generation_jobs where series_id = :s and kind = 'illustration'
                and status in ('queued', 'running') order by created_at desc limit 1"""),
            {"s": series["id"]})).scalar_one_or_none()
        await credits.charge(conn, user_id, REPAINT, "Repintar una ilustración", job_id)
    return {"job": {"id": str(job_id) if job_id else None, "kind": "illustration"}}


@router.get("/api/series/{series_id}/cover/preview")
async def cover_preview(series_id: uuid.UUID, request: Request, user_id: UserId, paper: PAPERS = "17x21"):
    """The cover as the next PDF prints it (its options, the owner's signature and plan), as a picture."""
    from app.api.exports import signature_of
    from app.api.series import _own_series

    async with request.app.state.engine.connect() as conn:
        series = await _own_series(conn, series_id, user_id, staff=True)
        acc, signature = await signature_of(conn, series["user_id"])
    key = hashlib.sha256(json.dumps(["cover", str(series_id), paper, signature, acc.plan.watermark] +
                                    [str(series[c]) for c in ("title", "topic", "genre", "audience", "cover",
                                                              "cover_key", "cover_options", "design")],
                                    sort_keys=True, default=str).encode()).hexdigest()
    if key in _rendered:
        _rendered.move_to_end(key)
        return {"image": _rendered[key][0]}
    storage = request.app.state.storage
    cover = logo = None
    if series["cover_key"]:
        try:
            cover = _screen_size(await storage.download(series["cover_key"]))[0]
        except Exception:  # prints as the plain cover
            pass
    if signature.get("logo"):
        try:
            logo = (await storage.download(signature["logo"]), "image/png")
        except Exception:
            pass
    jpeg = await asyncio.wait_for(asyncio.to_thread(_render_cover, series, cover, signature, logo,
                                                    acc.plan.watermark, paper), 60)
    _rendered[key] = ("data:image/jpeg;base64," + base64.b64encode(jpeg).decode(), {})
    while len(_rendered) > RENDERED:
        _rendered.popitem(last=False)
    return {"image": _rendered[key][0]}


def _render_cover(series, cover: bytes | None, signature: dict, logo, watermark: bool, paper: str) -> bytes:
    import pypdfium2

    from app.render import Tome, _document, render_html

    design = Design.model_validate(_parse(series["design"])) if series["design"] else None
    meta = _parse(series["cover"]) or {}
    title = series["title"] or series["topic"]
    tome = Tome(title=title, genre=series["genre"], audience=(_parse(series["audience"]) or {}).get("label", ""),
                author=signature.get("author"), school=signature.get("school"), logo=logo, sections=[],
                cover_image=cover, cover_media_type="image/jpeg", cover_lettered=bool(cover) and meta.get("lettered") == title,
                palette=meta.get("palette"), design=design, watermark=watermark,
                cover_options=_parse(series["cover_options"]) or {})
    pdf = pypdfium2.PdfDocument(_document(render_html(tome, paper=paper, include_answer_key=False)).write_pdf())
    buffer = io.BytesIO()
    pdf[0].render(scale=110 / 72).to_pil().convert("RGB").save(buffer, "JPEG", quality=85)
    return buffer.getvalue()
