"""The pdf_export job: load the finished tome, lay it out (PDF or Word), upload it to Storage."""

import asyncio
import json
import logging

from sqlalchemy import text

from app.curriculum import reliable
from app.content import Design, SectionContent, block_assets
from app.illustrator import ink_saver, vectorize
from app.printing import preflight
from app.render import Tome, TomeSection, render_checked, render_cover_wrap
from app.word import render_docx

MONO = ["#FFFFFF", "#262626", "#737373"]  # paper, ink, accent for the black-and-white edition
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

log = logging.getLogger("worker")


async def run_export(deps, job: dict) -> None:
    export_id = job["payload"]["export_id"]
    async with deps.engine.begin() as conn:
        export = (await conn.execute(text("select * from public.exports where id = :e"),
                                     {"e": export_id})).mappings().one()
        series = (await conn.execute(text(
            """select s.*, p.display_name from public.series s join public.profiles p on p.id = s.user_id
                where s.id = :s"""), {"s": job["series_id"]})).mappings().one()
        lessons = (await conn.execute(text(
            "select position, title, content_json from public.lessons where series_id = :s order by position"
        ), {"s": job["series_id"]})).mappings().all()
        shelf = (await conn.execute(text(  # its collection and level, as the library shelf numbers them
            """select c.name, (select count(*) from public.series o where o.collection_id = c.id and
                      (o.collection_position, o.created_at) <= (s.collection_position, s.created_at)) as level
                 from public.series s join public.collections c on c.id = s.collection_id where s.id = :s"""),
            {"s": job["series_id"]})).one_or_none()
        await conn.execute(text("update public.exports set status = 'running' where id = :e"), {"e": export_id})
        asset_ids = list({i for lesson in lessons for b in (_json(lesson["content_json"]) or {}).get("blocks", [])
                          for i in block_assets(b)})
        assets = (await conn.execute(text(
            "select id::text, storage_key, media_type, attribution, kind from public.assets where id = any(cast(:ids as uuid[]))"
        ), {"ids": asset_ids})).all() if asset_ids else []
        noted = {b.get("asset_id") for lesson in lessons for b in (_json(lesson["content_json"]) or {}).get("blocks", [])
                 if b.get("type") == "image" and b.get("size") == "plate" and b.get("notes") and b.get("asset_id")}
        busy = {r.id: r.busy for r in (await conn.execute(text(
            """select id::text, review->'busy' as busy from public.assets
                where id = any(cast(:ids as uuid[])) and review ? 'busy'"""), {"ids": list(noted)})).all()} if noted else {}

    options = _json(export["options"])
    saver = options.get("ink") == "saver"  # the black-and-white edition: same tome, no AI, little ink
    images, credits = {}, {}
    slots = asyncio.Semaphore(8)  # a worksheet tome can point at a hundred small pictures

    async def fetch(asset_id, key, media_type, attribution, kind):
        if attribution:
            credits[asset_id] = _json(attribution)["credit"]
        try:
            async with slots:
                data = await deps.storage.download(key, bucket="images")
        except Exception:  # a missing picture prints as its placeholder
            log.exception("image %s unavailable", key)
            return
        if kind == "line_art" and media_type == "image/png":  # painted before colouring pages were traced
            svg = await asyncio.to_thread(vectorize, data)
            data, media_type = (svg, "image/svg+xml") if svg else (data, media_type)
        if saver and media_type != "image/svg+xml":
            data, media_type = await asyncio.to_thread(ink_saver, data)
        images[asset_id] = (data, media_type)

    await asyncio.gather(*(fetch(*row) for row in assets))
    busy = {k: _json(v) for k, v in busy.items()}
    await _inspect(deps, [a for a in noted if a not in busy and a in images], images, busy)
    cover_image, media_type = None, "image/png"
    if series["cover_key"]:
        try:
            cover_image = await deps.storage.download(series["cover_key"])
            media_type = "image/webp" if series["cover_key"].endswith(".webp") else (
                "image/png" if series["cover_key"].endswith(".png") else "image/jpeg")
        except Exception:  # a missing cover must not cost the user their PDF
            log.exception("cover %s unavailable, exporting with the plain cover", series["cover_key"])
    if saver and cover_image:
        cover_image, media_type = await asyncio.to_thread(ink_saver, cover_image)
    signature = job["payload"].get("signature") or {"author": series["display_name"]}
    logo = None
    if signature.get("logo"):
        try:
            key = signature["logo"]
            logo = (await deps.storage.download(key), "image/png" if key.endswith(".png") else
                    "image/webp" if key.endswith(".webp") else "image/jpeg")
        except Exception:  # the signature prints without the logo
            log.exception("logo %s unavailable", signature["logo"])
    if saver and logo:
        logo = await asyncio.to_thread(ink_saver, logo[0])
    audience = (_json(series["audience"]) or {}).get("label", "")
    design = Design.model_validate(_json(series["design"])) if series["design"] else None
    palette = (_json(series["cover"]) or {}).get("palette")
    if saver:  # every theme colour from greys: tints, frames and openers print light
        palette = MONO
        design = design.model_copy(update={"palette": MONO}) if design else None
    tome = Tome(
        title=series["title"] or series["topic"], genre=series["genre"] or "lesson_series", audience=audience,
        author=signature.get("author"), school=signature.get("school"), logo=logo,
        sections=[TomeSection(position=lesson["position"], title=lesson["title"],
                              content=SectionContent.model_validate(_json(lesson["content_json"])))
                  for lesson in lessons if lesson["content_json"]],
        cover_image=cover_image, cover_media_type=media_type,
        cover_lettered=bool(cover_image) and (_json(series["cover"]) or {}).get("lettered") == (series["title"] or series["topic"]),
        palette=palette, design=design,
        images=images, credits=credits,
        sources=[src for src in (_json(series["research"]) or {}).get("sources") or [] if reliable(src.get("url", ""))],
        collection=shelf.name if shelf else None, level=shelf.level if shelf else None,
        watermark=job["payload"].get("watermark", False), mono=saver, busy=busy,
    )
    paper, print_edition = options.get("paper", "A4"), options.get("edition") == "print"
    if options.get("format") == "docx":
        await _finish_docx(deps, job, export_id, tome, paper, options.get("include_answer_key", True))
        return
    # WeasyPrint is CPU-bound; keep the event loop free for the other jobs in flight.
    pdf, pages, layout = await asyncio.wait_for(
        asyncio.to_thread(render_checked, tome, paper=paper, include_answer_key=options.get("include_answer_key", True),
                          print_edition=print_edition),
        timeout=240,  # up to three layout passes on a slow CPU
    )
    base = f"{job['user_id']}/{job['series_id']}/{export_id}"
    storage_key, cover_key = f"{base}.pdf", None
    await deps.storage.upload(storage_key, pdf)
    if print_edition:  # the printer takes the cover as its own file, sized by the page count
        wrap, _ = await asyncio.wait_for(asyncio.to_thread(render_cover_wrap, tome, paper=paper, pages=pages),
                                         timeout=60)
        cover_key = f"{base}-cover.pdf"
        await deps.storage.upload(cover_key, wrap)
    report = preflight(tome, paper=paper, print_edition=print_edition, pages=pages, layout=layout)

    async with deps.engine.begin() as conn:
        await conn.execute(text(
            """update public.exports set status = 'succeeded', storage_key = :k, page_count = :p, size_bytes = :b,
                      cover_storage_key = :ck, preflight = cast(:pf as jsonb), finished_at = now() where id = :e"""
        ), {"e": export_id, "k": storage_key, "p": pages, "b": len(pdf), "ck": cover_key, "pf": json.dumps(report)})
        await conn.execute(text(
            "update public.generation_jobs set status = 'succeeded', finished_at = now(), locked_at = null,"
            " locked_by = null where id = :j"), {"j": job["id"]})


async def _inspect(deps, asset_ids: list[str], images: dict, busy: dict) -> None:
    """The Design inspector looks at each plate once (kept on the asset): where its faces, characters and subject
    are, so the fact cards are laid on calm parts of the picture. Without it the cards keep their spots."""
    if not asset_ids or getattr(deps, "vision", None) is None:
        return

    async def one(asset_id):
        try:
            cells, _ = await deps.vision.busy_cells(images[asset_id][0])
        except Exception as exc:  # a quality step: the plate still prints
            log.warning("design inspector skipped %s: %s", asset_id, exc)
            return
        busy[asset_id] = cells
        async with deps.engine.begin() as conn:
            await conn.execute(text(
                """update public.assets set review = coalesce(review, '{}'::jsonb) || jsonb_build_object('busy', cast(:b as jsonb))
                    where id = cast(:id as uuid)"""), {"id": asset_id, "b": json.dumps(cells)})

    await asyncio.gather(*(one(a) for a in asset_ids))


async def _finish_docx(deps, job, export_id, tome, paper, include_answer_key) -> None:
    """An editable Word file: no page count or print preflight, Word lays the pages out itself."""
    data = await asyncio.wait_for(asyncio.to_thread(render_docx, tome, paper=paper,
                                                    include_answer_key=include_answer_key), timeout=240)
    storage_key = f"{job['user_id']}/{job['series_id']}/{export_id}.docx"
    await deps.storage.upload(storage_key, data, DOCX)
    async with deps.engine.begin() as conn:
        await conn.execute(text(
            """update public.exports set status = 'succeeded', storage_key = :k, size_bytes = :b, finished_at = now()
                where id = :e"""), {"e": export_id, "k": storage_key, "b": len(data)})
        await conn.execute(text(
            "update public.generation_jobs set status = 'succeeded', finished_at = now(), locked_at = null,"
            " locked_by = null where id = :j"), {"j": job["id"]})


def _json(value):
    return json.loads(value) if isinstance(value, str) else value
