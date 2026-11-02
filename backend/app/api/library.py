"""The free plate library: plates the team painted in the style lab, published with a question and an answer.
Anyone browses them; downloading the printable PDF needs a Google account, so every download is a sign-up."""

import asyncio
import html
import re
import unicodedata
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.admin import _staff
from app.api.deps import current_user_id
from app.errors import ApiError
from app.house_styles import BY_KEY
from app.render import ASSETS, _write_pdf

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
FIELDS = "id::text, slug, title, answer, topic, audience, style, image_key, downloads, created_at"


def _slug(title: str) -> str:
    plain = unicodedata.normalize("NFKD", title.lower()).encode("ascii", "ignore").decode()
    return "-".join(re.findall(r"[a-z0-9]+", plain))[:70] or "lamina"


def _public(row, request: Request) -> dict:
    plate = dict(row)
    key = plate.pop("image_key")
    storage = request.app.state.storage
    plate["image_url"] = storage.public_url(key, bucket="images") if storage else None
    style = BY_KEY.get(plate["style"])
    plate["style_name"] = style.name if style else plate["style"]
    return plate


@router.get("/api/library")
async def list_plates(request: Request, topic: str = Query("", max_length=120), style: str = Query("", max_length=40)):
    async with request.app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            f"""select {FIELDS} from public.library_plates
                 where published and (:t = '' or topic = :t) and (:st = '' or style = :st)
                 order by created_at desc limit 200"""), {"t": topic, "st": style})).mappings().all()
        topics = (await conn.execute(text(
            "select topic, count(*) as n from public.library_plates where published group by topic order by n desc"
        ))).mappings().all()
    return {"plates": [_public(r, request) for r in rows], "topics": [dict(t) for t in topics]}


@router.get("/api/library/{slug}")
async def get_plate(slug: str, request: Request):
    async with request.app.state.engine.connect() as conn:
        row = (await conn.execute(text(f"select {FIELDS} from public.library_plates where slug = :s and published"),
                                  {"s": slug})).mappings().first()
        if row is None:
            raise ApiError(404, "not_found", "Esa lámina no existe.")
        related = (await conn.execute(text(
            f"""select {FIELDS} from public.library_plates where published and slug <> :s
                 order by (topic = :t) desc, created_at desc limit 6"""),
            {"s": slug, "t": row["topic"]})).mappings().all()
    return {"plate": _public(row, request), "related": [_public(r, request) for r in related]}


@router.post("/api/library/{slug}/download")
async def download_plate(slug: str, request: Request, user_id: UserId):
    """The printable PDF (made once, then kept), for signed-in users only: a visitor signs in with Google first."""
    storage = request.app.state.storage
    async with request.app.state.engine.begin() as conn:
        email = (await conn.execute(text("select email from public.profiles where id = :u"),
                                    {"u": user_id})).scalar_one_or_none()
        if not email:
            raise ApiError(401, "login_required", "Entra con Google para descargar la lámina gratis.")
        plate = (await conn.execute(text(
            "select id, slug, title, answer, topic, image_key, pdf_key from public.library_plates "
            "where slug = :s and published for update"), {"s": slug})).mappings().first()
        if plate is None:
            raise ApiError(404, "not_found", "Esa lámina no existe.")
        pdf_key = plate["pdf_key"]
        if pdf_key is None:
            image = await storage.download(plate["image_key"], bucket="images")
            pdf, _ = await asyncio.to_thread(plate_pdf, plate["title"], plate["answer"], plate["topic"], image)
            pdf_key = f"library/{plate['slug']}.pdf"
            await storage.upload(pdf_key, pdf, "application/pdf")
        await conn.execute(text(
            "update public.library_plates set pdf_key = :k, downloads = downloads + 1 where id = :id"),
            {"k": pdf_key, "id": plate["id"]})
    return {"url": await storage.signed_url(pdf_key, expires_in=300, download_name=f"{plate['slug']}.pdf")}


def plate_pdf(title: str, answer: str, topic: str, image: bytes) -> tuple[bytes, int]:
    """A letter page: the question, the plate, the answer and our signature."""
    import base64

    fonts = (ASSETS / "fonts").as_uri()
    src = f"data:image/jpeg;base64,{base64.b64encode(image).decode()}"
    esc = html.escape
    doc = f"""<html><head><style>
@font-face {{ font-family: "Fredoka"; font-weight: 300 700; src: url("{fonts}/Fredoka-Variable.ttf"); }}
@font-face {{ font-family: "Nunito"; font-weight: 200 1000; src: url("{fonts}/Nunito-Variable.ttf"); }}
@page {{ size: letter; margin: 14mm; }}
body {{ font-family: Nunito; color: #1c1917; margin: 0; }}
.topic {{ font-size: 10pt; letter-spacing: .12em; text-transform: uppercase; color: #78716c; }}
h1 {{ font-family: Fredoka; font-weight: 600; font-size: 24pt; line-height: 1.1; margin: 2mm 0 5mm; }}
img {{ display: block; height: 178mm; width: auto; margin: 0 auto; border-radius: 4mm; }}
.answer {{ font-size: 13pt; line-height: 1.45; margin: 6mm 0 0; }}
.foot {{ position: fixed; bottom: 0; left: 0; right: 0; font-size: 8.5pt; color: #a8a29e; display: flex;
         justify-content: space-between; }}
</style></head><body>
<div class="topic">{esc(topic)}</div><h1>{esc(title)}</h1><img src="{src}">
{f'<p class="answer">{esc(answer)}</p>' if answer else ''}
<div class="foot"><span>Lámina gratis de Jelyx Docs</span><span>Crea el libro completo en docs.jelyx.app</span></div>
</body></html>"""
    return _write_pdf(doc)


class NewPlate(BaseModel):
    sample_id: uuid.UUID
    title: str = Field(min_length=3, max_length=160)
    answer: str = Field(default="", max_length=600)
    topic: str = Field(min_length=2, max_length=120)
    audience: str = Field(default="", max_length=80)


@router.post("/api/admin/library", status_code=201)
async def publish_plate(body: NewPlate, request: Request, user_id: UserId):
    """A style lab sample published as a free plate."""
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        sample = (await conn.execute(text(
            "select style, key from public.style_samples where id = :id and status = 'done'"),
            {"id": body.sample_id})).mappings().first()
        if sample is None:
            raise ApiError(404, "not_found", "No existe esa muestra.")
        base = slug = _slug(body.title)
        n = 2
        while (await conn.execute(text("select 1 from public.library_plates where slug = :s"), {"s": slug})).first():
            slug, n = f"{base}-{n}", n + 1
        row = (await conn.execute(text(
            f"""insert into public.library_plates (slug, title, answer, topic, audience, style, image_key, sample_id,
                                                   created_by)
                values (:slug, :title, :answer, :topic, :aud, :style, :key, :sample, :u) returning {FIELDS}"""),
            {"slug": slug, "title": body.title.strip(), "answer": body.answer.strip(), "topic": body.topic.strip(),
             "aud": body.audience.strip(), "style": sample["style"], "key": sample["key"], "sample": body.sample_id,
             "u": user_id})).mappings().one()
    return {"plate": _public(row, request)}


@router.delete("/api/admin/library/{plate_id}", status_code=204)
async def unpublish_plate(plate_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        await conn.execute(text("update public.library_plates set published = false where id = :id"),
                           {"id": plate_id})
