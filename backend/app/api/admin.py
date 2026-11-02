"""The admin panel for our own staff (profiles.platform_role staff/admin): users and their plans, and platform
analytics. Staff can look; only admins change plans, credits or roles."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import current_user_id
from app import credits
from app.errors import ApiError
from app.plans import APP, PACKS, PAID, PLANS

router = APIRouter()
UserId = Annotated[uuid.UUID, Depends(current_user_id)]

SUMMARY = text("""
select
  (select count(*) from public.profiles where email is not null) as users,
  (select count(*) from public.profiles where email is not null and created_at >= :since) as new_users,
  (select count(*) from public.series where preview and created_at >= :since) as previews,
  (select count(*) from public.series s join public.profiles p on p.id = s.user_id
    where s.preview and s.created_at >= :since and p.email is not null) as previews_saved,
  (select count(*) from public.series s join public.memberships m on m.user_id = s.user_id
     join public.subscriptions sub on sub.org_id = m.org_id and sub.status in ('active', 'trialing', 'past_due')
    where s.preview and s.created_at >= :since) as previews_paid,
  (select count(*) from public.profiles where created_at >= :since and onboarded_at is not null) as onboarded,
  (select count(distinct user_id) from public.series where created_at >= :since) as creators,
  (select count(distinct s.user_id) from public.series s join public.profiles p on p.id = s.user_id
    where p.created_at >= :since) as activated,
  (select count(*) from public.series where created_at >= :since) as tomes,
  (select count(*) from public.exports where created_at >= :since and status = 'succeeded') as exports,
  (select count(*) from public.generation_jobs where created_at >= :since) as jobs,
  (select count(*) from public.generation_jobs where created_at >= :since and status = 'failed') as failed_jobs,
  (select coalesce(-sum(delta), 0) from public.credit_ledger where created_at >= :since and kind in ('spend', 'refund'))
    as credits_spent,
  (select coalesce(sum(cost_usd_micros), 0) / 1e6 from public.generation_logs where created_at >= :since) as llm_usd,
  (select coalesce(sum(cost_usd), 0) from public.assets where created_at >= :since) as images_usd,
  (select coalesce(sum(coalesce((cover->>'spent_usd')::numeric, (cover->>'cost_usd')::numeric, 0)), 0)
     from public.series where created_at >= :since) as covers_usd
""")


async def _staff(conn, user_id, *, admin: bool = False) -> None:
    role = (await conn.execute(text("select platform_role from public.profiles where id = :u"),
                               {"u": user_id})).scalar_one_or_none()
    if role not in (("admin",) if admin else ("staff", "admin")):
        raise ApiError(403, "forbidden", "Solo los administradores pueden hacer esto." if admin
                       else "Solo el equipo de la plataforma puede ver esto.")


# A user's organization (their own, as owner), its subscription for this app and its live credits.
USER_ROW = """
select p.id, p.email, p.display_name, p.avatar_url, p.platform_role, p.created_at, u.last_sign_in_at,
       m.org_id, s.plan, s.status, s.current_period_end, s.stripe_subscription_id is not null as stripe,
       (select coalesce(sum(b.remaining), 0) from public.credit_buckets b
         where b.org_id = m.org_id and b.remaining > 0 and (b.expires_at is null or b.expires_at > now())) as credits,
       (select count(*) from public.series x where x.user_id = p.id) as tomes
  from public.profiles p
  join auth.users u on u.id = p.id
  left join lateral (select org_id from public.memberships where user_id = p.id
                      order by (role = 'owner') desc, created_at limit 1) m on true
  left join public.subscriptions s on s.org_id = m.org_id and s.app = :app
"""


def _user(r) -> dict:
    lapsed = not r["stripe"] and r["current_period_end"] and r["current_period_end"] < datetime.now(UTC)
    active = r["plan"] and r["status"] in ("active", "trialing", "past_due") and not lapsed
    return {"id": str(r["id"]), "email": r["email"], "name": r["display_name"], "avatar_url": r["avatar_url"],
            "role": r["platform_role"], "created_at": r["created_at"].isoformat(),
            "last_sign_in_at": r["last_sign_in_at"].isoformat() if r["last_sign_in_at"] else None,
            "plan": r["plan"] if active else "prueba", "plan_status": r["status"],
            "period_end": r["current_period_end"].isoformat() if r["current_period_end"] else None,
            "stripe": r["stripe"], "credits": int(r["credits"]), "tomes": r["tomes"]}


@router.get("/api/admin/users")
async def users(request: Request, user_id: UserId, q: str = Query("", max_length=200),
                plan: str = Query("", pattern="^(|prueba|docente|creador|editorial)$"),
                offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    """Registered users (landing visitors without Google are not users yet), newest first."""
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        where = """ where p.email is not null and not u.is_anonymous
                      and (:q = '' or p.email ilike '%' || :q || '%' or p.display_name ilike '%' || :q || '%')"""
        rows = (await conn.execute(text(f"select * from ({USER_ROW}{where}) x"
                                        " where :plan = '' or (case when x.plan is not null and x.status in"
                                        " ('active', 'trialing', 'past_due') then x.plan else 'prueba' end) = :plan"
                                        " order by created_at desc limit :lim offset :off"),
                                   {"app": APP, "q": q.strip(), "plan": plan, "lim": limit + 1, "off": offset})
                ).mappings().all()
    return {"users": [_user(r) for r in rows[:limit]], "more": len(rows) > limit}


@router.get("/api/admin/series")
async def all_series(request: Request, user_id: UserId, q: str = Query("", max_length=200),
                     status: str = Query("", pattern="^(|outlining|outline_ready|outline_failed|generating|needs_attention|ready)$"),
                     genre: str = Query("", max_length=40), preview: str = Query("", pattern="^(|yes|no)$"),
                     offset: int = Query(0, ge=0), limit: int = Query(48, ge=1, le=200)):
    """Every tome on the platform, newest first, to review what the agents make: cover, owner, Editor score,
    pictures and the last file (opened and downloaded with the tome's own page, read-only for the team)."""
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        rows = (await conn.execute(text(
            """select s.id, coalesce(s.title, s.topic) as title, s.title is null as untitled, s.genre, s.status,
                      s.preview, s.created_at, s.page_target, s.cover_key, s.cover->'palette' as palette,
                      p.email, p.display_name,
                      (select count(*) from public.lessons l where l.series_id = s.id) as sections,
                      (select round(avg((l.review->>'score')::numeric), 1) from public.lessons l
                        where l.series_id = s.id and l.review ? 'score') as score,
                      (select json_build_object('id', e.id, 'status', e.status, 'format', coalesce(e.options->>'format', 'pdf'),
                                                'pages', e.page_count)
                         from public.exports e where e.series_id = s.id order by e.created_at desc limit 1) as export
                 from public.series s left join public.profiles p on p.id = s.user_id
                where (:q = '' or s.title ilike '%' || :q || '%' or s.topic ilike '%' || :q || '%' or p.email ilike '%' || :q || '%')
                  and (:status = '' or s.status::text = :status) and (:genre = '' or s.genre::text = :genre)
                  and (:preview = '' or s.preview = (:preview = 'yes'))
                order by s.created_at desc limit :lim offset :off"""),
            {"q": q.strip(), "status": status, "genre": genre, "preview": preview, "lim": limit + 1, "off": offset})
        ).mappings().all()
    storage = request.app.state.storage
    out = []
    for r in rows[:limit]:
        d = dict(r)
        key = d.pop("cover_key")
        d["cover_url"] = storage.public_url(key) if key and storage else None
        d["id"], d["created_at"] = str(d["id"]), d["created_at"].isoformat()
        d["score"] = float(d["score"]) if d["score"] is not None else None
        for k in ("palette", "export"):
            d[k] = json.loads(d[k]) if isinstance(d[k], str) else d[k]
        out.append(d)
    return {"series": out, "more": len(rows) > limit}


@router.get("/api/admin/users/{target}")
async def user_detail(target: uuid.UUID, request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        row = (await conn.execute(text(f"{USER_ROW} where p.id = :t"), {"app": APP, "t": target})).mappings().one_or_none()
        if row is None:
            raise ApiError(404, "not_found", "Ese usuario no existe.")
        ledger = (await conn.execute(text(
            """select delta, kind, reason, created_at from public.credit_ledger where org_id = :o
                order by created_at desc limit 30"""), {"o": row["org_id"]})).mappings().all()
        tomes = (await conn.execute(text(
            """select id, coalesce(title, topic) as title, genre, status, preview, created_at from public.series
                where user_id = :t order by created_at desc limit 20"""), {"t": target})).mappings().all()
    return {**_user(row),
            "ledger": [{**r, "created_at": r["created_at"].isoformat()} for r in ledger],
            "series": [{**r, "id": str(r["id"]), "created_at": r["created_at"].isoformat()} for r in tomes]}


class PlanGrant(BaseModel):
    plan: str | None = Field(default=None, pattern="^(docente|creador|editorial)$")  # None: back to the free trial
    months: int = Field(default=1, ge=1, le=24)


@router.post("/api/admin/users/{target}/plan")
async def set_plan(target: uuid.UUID, body: PlanGrant, request: Request, user_id: UserId):
    """A plan given by hand (courtesy, a school's invoice, a partner): active for N months with that many months of
    credits, no Stripe involved. A plan paid through Stripe is changed or cancelled in Stripe, not here."""
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        acc = await credits.account(conn, target)
        sub = (await conn.execute(text(
            "select stripe_subscription_id, status from public.subscriptions where org_id = :o and app = :app"),
            {"o": acc.org_id, "app": APP})).mappings().one_or_none()
        if sub and sub["stripe_subscription_id"] and sub["status"] in ("active", "trialing", "past_due"):
            raise ApiError(409, "stripe_managed", "Este plan se paga con Stripe: cámbialo o cancélalo desde Stripe.")
        await credits.expire_plan_credits(conn, acc.org_id)
        if body.plan is None:
            await conn.execute(text("delete from public.subscriptions where org_id = :o and app = :app"),
                               {"o": acc.org_id, "app": APP})
        else:
            end = datetime.now(UTC) + timedelta(days=30 * body.months)
            await conn.execute(text(
                """insert into public.subscriptions (org_id, app, plan, status, stripe_subscription_id,
                                                     current_period_end, updated_at)
                   values (:o, :app, :p, 'active', null, :e, now())
                   on conflict (org_id, app) do update set plan = :p, status = 'active', stripe_subscription_id = null,
                                                           current_period_end = :e, updated_at = now()"""),
                {"o": acc.org_id, "app": APP, "p": body.plan, "e": end})
            await credits.grant(conn, acc.org_id, PLANS[body.plan].credits * body.months, "plan",
                                f"Plan {PLANS[body.plan].label} asignado por el equipo", expires_at=end)
        row = (await conn.execute(text(f"{USER_ROW} where p.id = :t"), {"app": APP, "t": target})).mappings().one()
    return _user(row)


class CreditGrant(BaseModel):
    amount: int = Field(ge=1, le=100000)
    reason: str = Field(default="Créditos de cortesía", min_length=3, max_length=200)


@router.post("/api/admin/users/{target}/credits")
async def give_credits(target: uuid.UUID, body: CreditGrant, request: Request, user_id: UserId):
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        acc = await credits.account(conn, target)
        await credits.grant(conn, acc.org_id, body.amount, "adjust", body.reason,
                            expires_at=datetime.now(UTC) + timedelta(days=365))
        row = (await conn.execute(text(f"{USER_ROW} where p.id = :t"), {"app": APP, "t": target})).mappings().one()
    return _user(row)


class RoleChange(BaseModel):
    role: str = Field(pattern="^(user|staff|admin)$")


@router.post("/api/admin/users/{target}/role")
async def set_role(target: uuid.UUID, body: RoleChange, request: Request, user_id: UserId):
    """staff sees the panel; admin also changes plans, credits and roles."""
    if target == user_id and body.role != "admin":
        raise ApiError(409, "own_role", "No puedes quitarte tu propio acceso de administrador.")
    async with request.app.state.engine.begin() as conn:
        await _staff(conn, user_id, admin=True)
        await conn.execute(text("update public.profiles set platform_role = :r where id = :t"),
                           {"r": body.role, "t": target})
        row = (await conn.execute(text(f"{USER_ROW} where p.id = :t"), {"app": APP, "t": target})).mappings().one()
    return _user(row)


@router.get("/api/admin/analytics")
async def analytics(request: Request, user_id: UserId, days: int = Query(30, ge=7, le=365)):
    since = datetime.now(UTC).date() - timedelta(days=days - 1)  # the database counts days in UTC
    async with request.app.state.engine.connect() as conn:
        await _staff(conn, user_id)
        s = (await conn.execute(SUMMARY, {"since": since})).mappings().one()
        daily = (await conn.execute(text(
            """select d::date as day,
                      (select count(*) from public.profiles where created_at::date = d::date) as signups,
                      (select count(*) from public.series where created_at::date = d::date) as tomes
                 from generate_series(cast(:since as date), current_date, interval '1 day') d order by d"""),
            {"since": since})).mappings().all()
        subs = (await conn.execute(text(
            "select plan, status, count(*) as n from public.subscriptions group by plan, status"))).mappings().all()
        packs = (await conn.execute(text(
            """select granted, count(*) as n from public.credit_buckets
                where source = 'pack' and created_at >= :since group by granted"""), {"since": since})).all()
        uses = (await conn.execute(text(
            """select coalesce(onboarding->>'use', 'sin respuesta') as k, count(*) as n from public.profiles
                where onboarded_at is not null group by 1 order by n desc"""))).all()
        subjects = (await conn.execute(text(
            """select v as k, count(*) as n from public.profiles, jsonb_array_elements_text(onboarding->'subjects') v
                group by v order by n desc limit 10"""))).all()
        genres = (await conn.execute(text(
            """select coalesce(genre, 'sin género') as k, count(*) as n from public.series where created_at >= :since
                group by 1 order by n desc"""), {"since": since})).all()
        top = (await conn.execute(text(
            """select p.email, coalesce(sub.plan, 'prueba') as plan, -sum(l.delta) as spent, count(distinct l.job_id) as jobs
                 from public.credit_ledger l join public.profiles p on p.id = l.user_id
                 left join public.subscriptions sub on sub.org_id = l.org_id and sub.status in ('active', 'trialing', 'past_due')
                where l.created_at >= :since and l.kind in ('spend', 'refund')
                group by p.email, sub.plan having sum(l.delta) < 0 order by spent desc limit 10"""),
            {"since": since})).mappings().all()

    active = {}
    for r in subs:
        if r["status"] in ("active", "trialing", "past_due"):
            active[r["plan"]] = active.get(r["plan"], 0) + r["n"]
    churned = sum(r["n"] for r in subs if r["status"] == "canceled")
    mrr = sum(PLANS[p].price_usd * n for p, n in active.items())
    price_of = {c: usd for c, usd in PACKS.values()}
    packs_usd = sum(price_of.get(g, 0) * n for g, n in packs)
    ai_usd = float(s["llm_usd"]) + float(s["images_usd"]) + float(s["covers_usd"])
    paying = sum(active.values())
    return {
        "days": days,
        "users": {"total": s["users"], "new": s["new_users"], "onboarded": s["onboarded"], "activated": s["activated"],
                  "creators": s["creators"], "paying": paying, "churned": churned,
                  "conversion": round(paying / s["users"], 4) if s["users"] else 0},
        "previews": {"total": s["previews"], "saved": s["previews_saved"], "paid": s["previews_paid"]},
        "revenue": {"mrr_usd": mrr, "packs_usd": packs_usd, "packs_sold": sum(n for _, n in packs),
                    "by_plan": [{"plan": p, "label": PLANS[p].label, "count": active.get(p, 0),
                                 "mrr_usd": PLANS[p].price_usd * active.get(p, 0)} for p in PAID]},
        "usage": {"tomes": s["tomes"], "exports": s["exports"], "jobs": s["jobs"], "failed_jobs": s["failed_jobs"],
                  "credits_spent": int(s["credits_spent"])},
        "cost": {"ai_usd": round(ai_usd, 2), "llm_usd": round(float(s["llm_usd"]), 2),
                 "images_usd": round(float(s["images_usd"]) + float(s["covers_usd"]), 2),
                 "per_credit_usd": round(ai_usd / int(s["credits_spent"]), 4) if s["credits_spent"] else None},
        "daily": [{"day": r["day"].isoformat(), "signups": r["signups"], "tomes": r["tomes"]} for r in daily],
        "uses": [{"key": k, "count": n} for k, n in uses],
        "subjects": [{"key": k, "count": n} for k, n in subjects],
        "genres": [{"key": k, "count": n} for k, n in genres],
        "top_users": [{**r, "spent": int(r["spent"])} for r in top],
    }
