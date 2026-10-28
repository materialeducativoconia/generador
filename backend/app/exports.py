"""The pdf_export job: load the finished tome, lay it out, upload it to Storage."""

import asyncio
import json
import logging

from sqlalchemy import text

from app.content import Design, SectionContent, block_assets
from app.illustrator import vectorize
from app.printing import preflight
from app.render import Tome, TomeSection, render_checked, render_cover_wrap

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
        await conn.execute(text("update public.exports set status = 'running' where id = :e"), {"e": export_id})
        asset_ids = list({i for lesson in lessons for b in (_json(lesson["content_json"]) or {}).get("blocks", [])
                          for i in block_assets(b)})
        assets = (await conn.execute(text(
            "select id::text, storage_key, media_type, attribution, kind from public.assets where id = any(cast(:ids as uuid[]))"
        ), {"ids": asset_ids})).all() if asset_ids else []

    options = _json(export["options"])
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
        images[asset_id] = (data, media_type)

    await asyncio.gather(*(fetch(*row) for row in assets))
    cover_image, media_type = None, "image/png"
    if series["cover_key"]:
        try:
            cover_image = await deps.storage.download(series["cover_key"])
            media_type = "image/webp" if series["cover_key"].endswith(".webp") else (
                "image/png" if series["cover_key"].endswith(".png") else "image/jpeg")
        except Exception:  # a missing cover must not cost the user their PDF
            log.exception("cover %s unavailable, exporting with the plain cover", series["cover_key"])
    audience = (_json(series["audience"]) or {}).get("label", "")
    tome = Tome(
        title=series["title"] or series["topic"], genre=series["genre"] or "lesson_series", audience=audience,
        author=series["display_name"],
        sections=[TomeSection(position=lesson["position"], title=lesson["title"],
                              content=SectionContent.model_validate(_json(lesson["content_json"])))
                  for lesson in lessons if lesson["content_json"]],
        cover_image=cover_image, cover_media_type=media_type,
        palette=(_json(series["cover"]) or {}).get("palette"),
        design=Design.model_validate(_json(series["design"])) if series["design"] else None,
        images=images, credits=credits,
        sources=(_json(series["research"]) or {}).get("sources") or [],
    )
    paper, print_edition = options.get("paper", "A4"), options.get("edition") == "print"
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


def _json(value):
    return json.loads(value) if isinstance(value, str) else value
