"""The free book library on the landing: whole tomes the team publishes from the admin. Anyone browses them as page
thumbnails; downloading the PDF needs a Google account, so every download is a sign-up."""

import asyncio
import io
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.api.admin import _staff
from app.api.deps import current_user_id
from app.api.library import _slug
from app.errors import ApiError
from app.render import GENRE_LABEL

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
FIELDS = "id::text, slug, title, topic, audience, genre, page_count, pages, downloads, created_at"
THUMBS = 6  # the cover and the first pages, enough to judge the book
THUMB_PX = 480


def _public(row, request: Request) -> dict:
    book = dict(row)
    storage = request.app.state.storage
    pages = book.pop("pages")
    pages = json.loads(pages) if isinstance(pages, str) else pages
    book["pages"] = [storage.public_url(k, bucket="images") for k in pages] if storage else []
    book["genre_label"] = GENRE_LABEL.get(book["genre"] or "", "Libro")
    return book


@router.get("/api/books")
async def list_books(request: Request):
    async with request.app.state.engine.connect() as conn:
        rows = (await conn.execute(text(
            f"select {FIELDS} from public.library_books where published order by created_at desc limit 120"
        ))).mappings().all()
    return {"books": [_public(r, request) for r in rows]}


@router.get("/api/books/{slug}")
async def get_book(slug: str, request: Request):
    async with request.app.state.engine.connect() as conn:
        row = (await conn.execute(text(f"select {FIELDS} from public.library_books where slug = :s and published"),
                                  {"s": slug})).mappings().first()
        if row is None:
            raise ApiError(404, "not_found", "Ese libro no existe.")
        related = (await conn.execute(text(
            f"""select {FIELDS} from public.library_books where published and slug <> :s
                 order by (topic = :t) desc, created_at desc limit 4"""), {"s": slug, "t": row["topic"]})).mappings().all()
    return {"book": _public(row, request), "related": [_public(r, request) for r in related]}


@router.post("/api/books/{slug}/download")
async def download_book(slug: str, request: Request, user_id: UserId):
    """The PDF, for signed-in users only: a visitor signs in with Google first."""
    async with request.app.state.engine.begin() as conn:
        email = (await conn.execute(text("select email from public.profiles where id = :u"),
                                    {"u": user_id})).scalar_one_or_none()
        if not email:
            raise ApiError(401, "login_required", "Entra con Google para descargar el libro gratis.")
        book = (await conn.execute(text(
            "update public.library_books set downloads = downloads + 1 where slug = :s and published "
            "returning slug, pdf_key"), {"s": slug})).mappings().first()
        if book is None:
            raise ApiError(404, "not_found", "Ese libro no existe.")
    return {"url": await request.app.state.storage.signed_url(book["pdf_key"], expires_in=300,
                                                              download_name=f"{book['slug']}.pdf")}


def thumbnails(pdf: bytes, n: int = THUMBS) -> tuple[list[bytes], int]:
    """The first pages as small JPEGs, and the page count."""
    import pypdfium2

    document = pypdfium2.PdfDocument(pdf)
    out = []
    for i in range(min(n, len(document))):
        page = document[i]
        image = page.render(scale=THUMB_PX / page.get_width()).to_pil().convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=82, optimize=True)
        out.append(buffer.getvalue())
    return out, len(document)


class NewBook(BaseModel):
    series_id: uuid.UUID


@router.post("/api/admin/books", status_code=201)
async def publish_book(body: NewBook, request: Request, user_id: UserId):
    """A finished tome published in the free library: its last PDF is copied (later edits do not leak in) and its
    first pages become the thumbnails visitors see."""
    storage = request.app.state.storage
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        series = (await conn.execute(text(
            """select s.id, coalesce(s.title, s.topic) as title, s.topic, s.genre::text as genre,
                      coalesce(s.audience->>'label', '') as audience,
                      (select e.storage_key from public.exports e
                        where e.series_id = s.id and e.status = 'succeeded' and e.storage_key like '%.pdf'
                        order by e.created_at desc limit 1) as pdf
                 from public.series s where s.id = :s"""), {"s": body.series_id})).mappings().first()
        if series is None:
            raise ApiError(404, "not_found", "Ese tomo no existe.")
        if not series["pdf"]:
            raise ApiError(409, "invalid_state", "Exporta el PDF del tomo antes de publicarlo.")
        old = (await conn.execute(text("select slug from public.library_books where series_id = :s"),
                                  {"s": body.series_id})).scalar_one_or_none()
        slug = old
        if slug is None:
            base = slug = _slug(series["title"])
            n = 2
            while (await conn.execute(text("select 1 from public.library_books where slug = :s"), {"s": slug})).first():
                slug, n = f"{base}-{n}", n + 1
    pdf = await storage.download_private(series["pdf"], "exports")
    pages, count = await asyncio.to_thread(thumbnails, pdf)
    keys = []
    for i, data in enumerate(pages):
        key = f"library/books/{slug}/{i}.jpg"
        await storage.upload(key, data, "image/jpeg", bucket="images")
        keys.append(key)
    pdf_key = f"library/books/{slug}.pdf"
    await storage.upload(pdf_key, pdf, "application/pdf")
    async with request.app.state.engine.begin() as conn:
        row = (await conn.execute(text(
            f"""insert into public.library_books (slug, series_id, title, topic, audience, genre, page_count, pages,
                                                  pdf_key, created_by)
                values (:slug, :s, :title, :topic, :aud, :genre, :n, cast(:pages as jsonb), :pdf, :u)
                on conflict (series_id) do update set title = excluded.title, topic = excluded.topic,
                    audience = excluded.audience, page_count = excluded.page_count, pages = excluded.pages,
                    pdf_key = excluded.pdf_key, published = true
                returning {FIELDS}"""),
            {"slug": slug, "s": body.series_id, "title": series["title"], "topic": series["topic"],
             "aud": series["audience"], "genre": series["genre"], "n": count, "pages": json.dumps(keys),
             "pdf": pdf_key, "u": user_id})).mappings().one()
    return {"book": _public(row, request)}


@router.delete("/api/admin/books/{series_id}", status_code=204)
async def unpublish_book(series_id: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        await conn.execute(text("update public.library_books set published = false where series_id = :s"),
                           {"s": series_id})
