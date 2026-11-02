"""The style lab (admins): one subject painted in every house style, side by side, so the team keeps the samples
that look made by an illustrator; kept samples become each style's reference images."""

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.admin import _staff
from app.api.deps import current_user_id
from app.errors import ApiError
from app.house_styles import BY_KEY, STYLES, finish, style_prompt
from app.illustrator import reference_image

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
_running: set[asyncio.Task] = set()  # keeps the paint tasks alive until they finish


class NewRun(BaseModel):
    subject: str | None = Field(default=None, max_length=700)
    series_id: uuid.UUID | None = None  # its first plate and cast, when no subject is given
    styles: list[str] = Field(default_factory=lambda: [s.key for s in STYLES], min_length=1, max_length=len(STYLES))


@router.post("/api/admin/style-lab", status_code=202)
async def paint_samples(body: NewRun, request: Request, user_id: UserId):
    images, storage = getattr(request.app.state, "images", None), request.app.state.storage
    if images is None or storage is None:
        raise ApiError(503, "not_configured", "Falta OPENROUTER_API_KEY para pintar.")
    styles = [BY_KEY[k] for k in dict.fromkeys(body.styles) if k in BY_KEY]
    if not styles:
        raise ApiError(422, "invalid_request", "Elige al menos un estilo.")
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        subject, sheet_keys = body.subject, []
        if body.series_id:
            plate, sheet_keys = await _tome(conn, body.series_id)
            subject = subject or plate
        if not subject:
            raise ApiError(422, "invalid_request", "Escribe qué pintar o elige un tomo con láminas.")
        run = uuid.uuid4()
        ids = {}
        for style in styles:
            ids[style.key] = (await conn.execute(text(
                """insert into public.style_samples (run, style, subject, series_id, created_by)
                   values (:r, :st, :su, :se, :u) returning id"""),
                {"r": run, "st": style.key, "su": subject, "se": body.series_id, "u": user_id})).scalar_one()
    _start(request.app, run, subject, sheet_keys, [(ids[st.key], st) for st in styles])
    return {"run": str(run), "subject": subject}


@router.post("/api/admin/style-lab/{run}/retry", status_code=202)
async def retry_failed(run: uuid.UUID, request: Request, user_id: UserId):
    """Paint again only the styles of a run that failed (an exhausted key, a timeout); the others are kept."""
    if getattr(request.app.state, "images", None) is None or request.app.state.storage is None:
        raise ApiError(503, "not_configured", "Falta OPENROUTER_API_KEY para pintar.")
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        rows = (await conn.execute(text(
            """update public.style_samples set status = 'painting', error = null
                where run = :r and status = 'failed' returning id, style, subject, series_id"""),
            {"r": run})).mappings().all()
        rows = [r for r in rows if r["style"] in BY_KEY]
        if not rows:
            raise ApiError(404, "not_found", "No hay estilos fallidos en esa ronda.")
        sheet_keys = (await _tome(conn, rows[0]["series_id"]))[1] if rows[0]["series_id"] else []
    _start(request.app, run, rows[0]["subject"], sheet_keys, [(r["id"], BY_KEY[r["style"]]) for r in rows])
    return {"run": str(run), "styles": [r["style"] for r in rows]}


async def _tome(conn, series_id) -> tuple[str | None, list[str]]:
    """A tome's first plate and the model sheets of its first two cast members."""
    row = (await conn.execute(text(
        """select s."cast",
                  (select b->>'subject' from public.lessons l, jsonb_array_elements(l.content_json->'blocks') b
                    where l.series_id = s.id and b->>'type' = 'image' and b->>'kind' = 'illustration'
                    order by l.position limit 1) as subject
             from public.series s where s.id = :s"""), {"s": series_id})).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", "No existe ese tomo.")
    return row["subject"], [c["sheet_key"] for c in (row["cast"] or []) if c.get("sheet_key")][:2]


def _start(app, run, subject: str, sheet_keys: list[str], samples: list) -> None:
    """Paint each (sample id, style) in the background; every sample ends done or failed with its error."""
    images, storage, engine = app.state.images, app.state.storage, app.state.engine

    async def paint(sample, style, sheets):
        try:
            image = await images.generate(style_prompt(style, subject, sheets=len(sheets)), references=sheets,
                                          aspect_ratio="3:4", resolution="2K")
            raw_key, key = f"style-lab/{run}/{style.key}-raw.jpg", f"style-lab/{run}/{style.key}.jpg"
            await storage.upload(raw_key, reference_image(image.data, 2048), "image/jpeg", bucket="images")
            await storage.upload(key, finish(image.data, style), "image/jpeg", bucket="images")
            values = {"status": "done", "raw": raw_key, "key": key, "cost": image.cost_usd, "error": None}
        except Exception as exc:  # one style failing must not stop the others
            values = {"status": "failed", "raw": None, "key": None, "cost": None, "error": str(exc)[:300]}
        async with engine.begin() as conn:
            await conn.execute(text(
                """update public.style_samples set status = :status, raw_key = :raw, key = :key, cost_usd = :cost,
                          error = :error where id = :id"""), {**values, "id": sample})

    async def paint_all():
        try:
            sheets = [reference_image(await storage.download(k, bucket="images")) for k in sheet_keys]
        except Exception:
            sheets = []
        await asyncio.gather(*(paint(sample, style, sheets) for sample, style in samples))

    task = asyncio.create_task(paint_all())
    _running.add(task)
    task.add_done_callback(_running.discard)


@router.get("/api/admin/style-lab")
async def list_samples(request: Request, user_id: UserId):
    """The house styles and the last runs, newest first, each sample with its finished and raw picture."""
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        rows = (await conn.execute(text(
            """select id::text, run::text, style, subject, status, raw_key, key, error, cost_usd, chosen, created_at,
                      (select slug from public.library_plates p where p.sample_id = style_samples.id and p.published
                        limit 1) as plate
                 from public.style_samples
                where run in (select run from public.style_samples group by run order by max(created_at) desc limit 8)
                   or chosen
                order by created_at desc"""))).mappings().all()
    storage = request.app.state.storage
    url = (lambda k: storage.public_url(k, bucket="images") if k and storage else None)
    runs: dict[str, dict] = {}
    for r in rows:
        run = runs.setdefault(r["run"], {"run": r["run"], "subject": r["subject"], "created_at": r["created_at"],
                                         "samples": []})
        run["samples"].append({"id": r["id"], "style": r["style"], "status": r["status"], "error": r["error"],
                               "cost_usd": float(r["cost_usd"]) if r["cost_usd"] is not None else None,
                               "chosen": r["chosen"], "url": url(r["key"]), "raw_url": url(r["raw_key"]),
                               "plate": r["plate"]})
    order = {s.key: i for i, s in enumerate(STYLES)}
    for run in runs.values():
        run["samples"].sort(key=lambda s: order.get(s["style"], 99))
    return {"styles": [{"key": s.key, "name": s.name, "inspired_by": s.inspired_by} for s in STYLES],
            "runs": sorted(runs.values(), key=lambda r: r["created_at"], reverse=True)}


class Choice(BaseModel):
    chosen: bool


@router.patch("/api/admin/style-lab/{sample_id}")
async def choose_sample(sample_id: uuid.UUID, body: Choice, request: Request, user_id: UserId):
    """Keep (or drop) a sample as a reference image of its style."""
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        found = (await conn.execute(text(
            "update public.style_samples set chosen = :c where id = :id and status = 'done' returning id"),
            {"c": body.chosen, "id": sample_id})).first()
    if found is None:
        raise ApiError(404, "not_found", "No existe esa muestra.")
    return {"id": str(sample_id), "chosen": body.chosen}
