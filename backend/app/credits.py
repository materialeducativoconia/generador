"""The credit ledger: plans and packs grant buckets, jobs spend from them when queued, failures refund.

Every function takes the caller's connection, so a charge commits or rolls back with the job it pays for.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from app.errors import ApiError
from app.plans import APP, PAID, PLANS, Plan


@dataclass
class Account:
    org_id: object
    plan_key: str
    status: str | None
    period_end: datetime | None

    @property
    def plan(self) -> Plan:
        return PLANS[self.plan_key]


async def account(conn, user_id) -> Account:
    """The user's organization and its plan; no active subscription means the free trial's limits."""
    row = (await conn.execute(text(
        """select m.org_id, s.plan, s.status, s.current_period_end
             from public.memberships m
             left join public.subscriptions s on s.org_id = m.org_id and s.app = :app
            where m.user_id = :u order by (m.role = 'owner') desc, m.created_at limit 1"""),
        {"u": user_id, "app": APP})).mappings().one_or_none()
    if row is None:
        raise ApiError(403, "forbidden", "Tu cuenta no tiene organización.")
    active = row["plan"] and row["status"] in ("active", "trialing", "past_due")
    return Account(row["org_id"], row["plan"] if active else "prueba", row["status"], row["current_period_end"])


async def require(conn, user_id, feature: str, label: str) -> Account:
    """403 plan_required unless the user's plan includes `feature` (a Plan field that is true or > 0)."""
    acc = await account(conn, user_id)
    if not getattr(acc.plan, feature):
        need = next(p.label for p in PLANS.values() if getattr(p, feature))
        raise ApiError(403, "plan_required", f"{label} está disponible desde el plan {need}.",
                       {"feature": feature, "plan": acc.plan_key})
    return acc


async def require_download(conn, user_id) -> Account:
    """Downloads need a plan. Organizations from the 40-credit trial days keep downloading what they made."""
    acc = await account(conn, user_id)
    if acc.plan_key not in PAID and not (await conn.execute(text(
            "select 1 from public.credit_buckets where org_id = :o and source = 'trial' and granted > 0"),
            {"o": acc.org_id})).first():
        raise ApiError(403, "plan_required", "Descargar tu material está disponible desde el plan Docente.",
                       {"feature": "download", "plan": acc.plan_key})
    return acc


async def balance(conn, org_id) -> dict:
    rows = (await conn.execute(text(
        """select source, sum(remaining) as n, min(expires_at) as first_expiry from public.credit_buckets
            where org_id = :o and remaining > 0 and (expires_at is null or expires_at > now()) group by source"""),
        {"o": org_id})).mappings().all()
    by = {r["source"]: int(r["n"]) for r in rows}
    plan_expiry = next((r["first_expiry"] for r in rows if r["source"] == "plan"), None)
    return {"total": sum(by.values()), "by_source": by,
            "plan_expires_at": plan_expiry.isoformat() if plan_expiry else None}


async def charge(conn, user_id, amount: int, reason: str, job_id=None) -> None:
    """Spends `amount` credits or raises 402 with nothing spent."""
    if amount <= 0:
        return
    acc = await account(conn, user_id)
    buckets = (await conn.execute(text(
        """select id, remaining from public.credit_buckets
            where org_id = :o and remaining > 0 and (expires_at is null or expires_at > now())
            order by (source = 'plan') desc, expires_at nulls last, created_at for update"""),
        {"o": acc.org_id})).all()
    available = sum(r.remaining for r in buckets)
    if available < amount:
        raise ApiError(402, "insufficient_credits",
                       f"Necesitas {amount} créditos y tienes {available}. Compra más o sube de plan.",
                       {"needed": amount, "available": available})
    left = amount
    for bucket_id, remaining in buckets:
        take = min(left, remaining)
        await conn.execute(text("update public.credit_buckets set remaining = remaining - :n where id = :b"),
                           {"n": take, "b": bucket_id})
        await _log(conn, acc.org_id, user_id, bucket_id, -take, "spend", reason, job_id)
        left -= take
        if not left:
            break


async def move_charge(conn, from_job, to_job, reason: str) -> None:
    """A prepaid part of one job (the cover paid with the outline) follows the job that does the work."""
    await conn.execute(text("update public.credit_ledger set job_id = :t where job_id = :f and reason = :r"),
                       {"f": from_job, "t": to_job, "r": reason})


async def refund_job(conn, job_id) -> int:
    """Gives back what a failed job spent, to the buckets it came from (if they have not expired)."""
    spent = (await conn.execute(text(
        """select org_id, user_id, bucket_id, -delta as n, reason from public.credit_ledger
            where job_id = :j and kind = 'spend' and not exists (
                  select 1 from public.credit_ledger r where r.job_id = :j and r.kind = 'refund')"""),
        {"j": job_id})).mappings().all()
    for s in spent:
        await conn.execute(text("update public.credit_buckets set remaining = remaining + :n where id = :b"),
                           {"n": s["n"], "b": s["bucket_id"]})
        await _log(conn, s["org_id"], s["user_id"], s["bucket_id"], s["n"], "refund", f"Reembolso: {s['reason']}",
                   job_id)
    return sum(s["n"] for s in spent)


async def grant(conn, org_id, amount: int, source: str, reason: str, *, expires_at=None,
                stripe_ref: str | None = None) -> bool:
    """Adds a bucket; a repeated Stripe reference (a webhook delivered twice) grants nothing."""
    bucket_id = (await conn.execute(text(
        """insert into public.credit_buckets (org_id, source, granted, remaining, expires_at, stripe_ref)
           values (:o, :s, :n, :n, :e, :r) on conflict (stripe_ref) do nothing returning id"""),
        {"o": org_id, "s": source, "n": amount, "e": expires_at, "r": stripe_ref})).scalar_one_or_none()
    if bucket_id is not None:
        await _log(conn, org_id, None, bucket_id, amount, "grant", reason, None)
    return bucket_id is not None


async def expire_plan_credits(conn, org_id) -> None:
    """A new month replaces the last one's plan credits: they do not roll over."""
    rows = (await conn.execute(text(
        """select id, remaining from public.credit_buckets where org_id = :o and source = 'plan' and remaining > 0
           for update"""), {"o": org_id})).all()
    for bucket_id, remaining in rows:
        await conn.execute(text("update public.credit_buckets set remaining = 0 where id = :b"), {"b": bucket_id})
        await _log(conn, org_id, None, bucket_id, -remaining, "expire", "Créditos del mes anterior", None)


async def _log(conn, org_id, user_id, bucket_id, delta, kind, reason, job_id) -> None:
    await conn.execute(text(
        """insert into public.credit_ledger (org_id, user_id, bucket_id, delta, kind, reason, job_id)
           values (:o, :u, :b, :d, :k, :r, :j)"""),
        {"o": org_id, "u": user_id, "b": bucket_id, "d": delta, "k": kind, "r": reason, "j": job_id})
