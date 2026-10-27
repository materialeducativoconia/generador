"""The pdf_export job: load the finished tome, lay it out, upload it to Storage."""

import asyncio
import json
import logging

from sqlalchemy import text

from app.content import Design, SectionContent
from app.render import Tome, TomeSection, render_pdf

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

    options = _json(export["options"])
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
    )
    # WeasyPrint is CPU-bound; keep the event loop free for the other jobs in flight.
    pdf, pages = await asyncio.wait_for(
        asyncio.to_thread(render_pdf, tome, paper=options.get("paper", "A4"),
                          include_answer_key=options.get("include_answer_key", True)),
        timeout=120,
    )
    storage_key = f"{job['user_id']}/{job['series_id']}/{export_id}.pdf"
    await deps.storage.upload(storage_key, pdf)

    async with deps.engine.begin() as conn:
        await conn.execute(text(
            """update public.exports set status = 'succeeded', storage_key = :k, page_count = :p, size_bytes = :b,
                      finished_at = now() where id = :e"""
        ), {"e": export_id, "k": storage_key, "p": pages, "b": len(pdf)})
        await conn.execute(text(
            "update public.generation_jobs set status = 'succeeded', finished_at = now(), locked_at = null,"
            " locked_by = null where id = :j"), {"j": job["id"]})


def _json(value):
    return json.loads(value) if isinstance(value, str) else value
