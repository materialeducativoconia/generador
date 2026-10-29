"""Platform analytics for our own staff (profiles.platform_role staff/admin): growth, activation, revenue, AI cost."""

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from app.api.deps import current_user_id
from app.errors import ApiError
from app.plans import PACKS, PAID, PLANS

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


async def _staff(conn, user_id) -> None:
    role = (await conn.execute(text("select platform_role from public.profiles where id = :u"),
                               {"u": user_id})).scalar_one_or_none()
    if role not in ("staff", "admin"):
        raise ApiError(403, "forbidden", "Solo el equipo de la plataforma puede ver esto.")


@router.get("/api/admin/analytics")
async def analytics(request: Request, user_id: UserId, days: int = Query(30, ge=7, le=365)):
    since = date.today() - timedelta(days=days - 1)
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
