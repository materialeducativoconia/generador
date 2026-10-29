import json
import logging
import secrets
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from uuid6 import uuid7

from app import credits
from app.api.deps import current_user_id
from app.errors import ApiError

router = APIRouter()
log = logging.getLogger("api")
UserId = Annotated[uuid.UUID, Depends(current_user_id)]
CLAIMED_TABLES = ("series", "generation_jobs", "generation_logs", "exports", "collections", "styles", "identities")
LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
LOGO_MAX_BYTES = 2 * 1024 * 1024

PROFILE_WITH_USAGE = text(
    """
    select p.id, p.email, p.display_name, p.avatar_url, p.daily_lesson_quota, p.is_active, p.platform_role,
           p.author_name, p.school, p.onboarding, p.onboarded_at,
           (select count(*) from public.generation_jobs j
             where j.user_id = p.id
               and j.kind in ('lesson', 'lesson_block')
               and j.created_at >= date_trunc('day', now() at time zone 'utc') at time zone 'utc') as used_today
      from public.profiles p
     where p.id = :user_id
    """
)


@router.get("/api/me")
async def get_me(request: Request, user_id: UserId) -> dict:
    async with request.app.state.engine.connect() as conn:
        row = (await conn.execute(PROFILE_WITH_USAGE, {"user_id": user_id})).mappings().one_or_none()
    if row is None or not row["is_active"]:
        raise ApiError(403, "forbidden", "Esta cuenta no está activa.")
    used = row["used_today"]
    async with request.app.state.engine.connect() as conn:
        acc = await credits.account(conn, user_id)
        wallet = await credits.balance(conn, acc.org_id)
        org = (await conn.execute(text(
            """select o.name, o.logo_key, m.role from public.organizations o
                 join public.memberships m on m.org_id = o.id and m.user_id = :u where o.id = :o"""),
            {"u": user_id, "o": acc.org_id})).mappings().one()
    plan = acc.plan
    storage = request.app.state.storage
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "anonymous": row["email"] is None,  # a landing-page visitor with a free preview, before Google
        "display_name": row["display_name"],
        "avatar_url": row["avatar_url"],
        "platform_role": row["platform_role"],
        "author_name": row["author_name"],
        "school": row["school"],
        "onboarded": row["onboarded_at"] is not None,
        "onboarding": json.loads(row["onboarding"]) if isinstance(row["onboarding"], str) else row["onboarding"],
        "organization": {"name": org["name"], "role": org["role"],
                         "logo_url": storage.public_url(org["logo_key"]) if org["logo_key"] and storage else None},
        "plan": {"key": acc.plan_key, "label": plan.label, "status": acc.status, "word": plan.word, "logo": plan.logo,
                 "print_edition": plan.print_edition, "styles": plan.styles, "identities": plan.identities,
                 "max_pages": plan.max_pages, "watermark": plan.watermark, "commercial": plan.commercial},
        "credits": wallet["total"],
        "quota": {
            "daily_lessons": row["daily_lesson_quota"],
            "used_today": used,
            "remaining_today": max(row["daily_lesson_quota"] - used, 0),
        },
    }


class ProfileEdit(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    author_name: str | None = Field(default=None, max_length=80)  # "" goes back to the Google name
    school: str | None = Field(default=None, max_length=120)


class Onboarding(BaseModel):
    use: Literal["aula", "venta", "escuela", "casa"] | None = None  # classroom, selling, school/publisher, home
    levels: list[str] = Field(default=[], max_length=6)
    subjects: list[str] = Field(default=[], max_length=10)
    author_name: str | None = Field(default=None, max_length=80)
    school: str | None = Field(default=None, max_length=120)


class NewLogo(BaseModel):
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    size: int = Field(gt=0)


class LogoDone(BaseModel):
    key: str = Field(max_length=200)


@router.patch("/api/me")
async def edit_profile(body: ProfileEdit, request: Request, user_id: UserId):
    """The name the app greets and the signature the material prints ("Elaborado por …")."""
    changes = {k: (v.strip() or None) if isinstance(v, str) else v
               for k, v in body.model_dump(exclude_unset=True).items() if k != "display_name" or v}
    if changes:
        sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys come from the model, never from the request
        async with request.app.state.engine.begin() as conn:
            await conn.execute(text(f"update public.profiles set {sets} where id = :u"), {**changes, "u": user_id})
    return await get_me(request, user_id)


@router.post("/api/me/onboarding")
async def finish_onboarding(body: Onboarding, request: Request, user_id: UserId):
    """The welcome flow ends (answered or skipped): keep the answers, and the signature if given."""
    answers = {"use": body.use, "levels": [v.strip()[:60] for v in body.levels if v.strip()],
               "subjects": [v.strip()[:60] for v in body.subjects if v.strip()]}
    async with request.app.state.engine.begin() as conn:
        await conn.execute(text(
            """update public.profiles set onboarding = cast(:a as jsonb), onboarded_at = coalesce(onboarded_at, now()),
                      author_name = coalesce(:n, author_name), school = coalesce(:s, school) where id = :u"""),
            {"a": json.dumps(answers), "n": (body.author_name or "").strip() or None,
             "s": (body.school or "").strip() or None, "u": user_id})
    return await get_me(request, user_id)


@router.post("/api/claims", status_code=201)
async def new_claim(request: Request, user_id: UserId):
    """An anonymous visitor is about to sign in with Google: a code that will carry their preview over."""
    async with request.app.state.engine.begin() as conn:
        email = (await conn.execute(text("select email from public.profiles where id = :u"),
                                    {"u": user_id})).scalar_one()
        if email is not None:
            raise ApiError(409, "invalid_state", "Tu cuenta ya está creada.")
        code = secrets.token_urlsafe(24)
        await conn.execute(text("insert into public.claims (code, user_id) values (:c, :u)"), {"c": code, "u": user_id})
    return {"code": code}


@router.post("/api/claims/{code}")
async def redeem_claim(code: str, request: Request, user_id: UserId):
    """Signed in with Google: the anonymous visitor's tomes become this account's (new or existing)."""
    async with request.app.state.engine.begin() as conn:
        anon = (await conn.execute(text(
            """delete from public.claims where code = :c and created_at > now() - interval '2 days'
               returning user_id"""), {"c": code})).scalar_one_or_none()
        if anon is None or anon == user_id:
            return {"moved": 0}
        if (await conn.execute(text("select email from public.profiles where id = :u"),
                               {"u": user_id})).scalar_one() is None:
            raise ApiError(409, "invalid_state", "Entra con Google para guardar tu vista previa.")
        moved = 0
        for table in CLAIMED_TABLES:  # fixed names, never from the request
            result = await conn.execute(text(f"update public.{table} set user_id = :to where user_id = :anon"),
                                        {"to": user_id, "anon": anon})
            moved += result.rowcount if table == "series" else 0
        await conn.execute(text(  # the free preview counts for the real account too
            """update public.organizations o set free_preview_at = coalesce(o.free_preview_at, now())
                 from public.memberships m where m.org_id = o.id and m.user_id = :u"""), {"u": user_id})
        await conn.execute(text("update public.profiles set is_active = false where id = :anon"), {"anon": anon})
    return {"moved": moved}


@router.post("/api/me/logo", status_code=201)
async def logo_upload(body: NewLogo, request: Request, user_id: UserId):
    """Step 1: a one-off URL the browser PUTs the logo to. Step 2 (PUT /api/me/logo) makes it the organization's."""
    if body.size > LOGO_MAX_BYTES:
        raise ApiError(422, "too_large", "El logo pesa más de 2 MB.")
    async with request.app.state.engine.connect() as conn:
        acc = await credits.require(conn, user_id, "logo", "Cargar tu logo")
    storage = _storage(request)
    key = f"logos/{acc.org_id}/{uuid7()}.{LOGO_TYPES[body.content_type]}"
    return {"key": key, "upload_url": await storage.upload_url(key, bucket="covers")}


@router.put("/api/me/logo")
async def logo_set(body: LogoDone, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        acc = await credits.require(conn, user_id, "logo", "Cargar tu logo")
        if not body.key.startswith(f"logos/{acc.org_id}/") or ".." in body.key:
            raise ApiError(422, "invalid_key", "Ese archivo no es tuyo.")
        old = await _swap_logo(conn, acc.org_id, body.key)
    await _drop(request, old)
    return await get_me(request, user_id)


@router.delete("/api/me/logo")
async def logo_delete(request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        old = await _swap_logo(conn, (await credits.account(conn, user_id)).org_id, None)
    await _drop(request, old)
    return await get_me(request, user_id)


async def _swap_logo(conn, org_id, key):
    old = (await conn.execute(text("select logo_key from public.organizations where id = :o for update"),
                              {"o": org_id})).scalar_one()
    await conn.execute(text("update public.organizations set logo_key = :k where id = :o"), {"k": key, "o": org_id})
    return old


async def _drop(request: Request, key: str | None) -> None:
    storage = request.app.state.storage
    if key and storage is not None:
        try:
            await storage.delete(key, bucket="covers")
        except Exception:  # an orphaned logo costs nothing worth failing the request for
            log.warning("could not delete %s", key)


def _storage(request: Request):
    storage = request.app.state.storage
    if storage is None:
        raise ApiError(503, "not_configured", "El almacenamiento no está configurado.")
    return storage
