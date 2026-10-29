"""Plan and credits: what the user has, Stripe Checkout to subscribe or buy a pack, and Stripe's webhook."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text

from app import credits
from app.api.deps import current_user_id
from app.errors import ApiError
from app.plans import APP, PACK_MONTHS, PACKS, PAID, PLANS, TRIAL_CREDITS, plan_for_key

router = APIRouter()
log = logging.getLogger("billing")
UserId = Annotated[uuid.UUID, Depends(current_user_id)]


class PlanCheckout(BaseModel):
    plan: Literal["docente", "creador", "editorial"]


class PackCheckout(BaseModel):
    pack: Literal["pack_100", "pack_300", "pack_1000"]


@router.get("/api/billing")
async def billing(request: Request, user_id: UserId):
    async with request.app.state.engine.connect() as conn:
        acc = await credits.account(conn, user_id)
        wallet = await credits.balance(conn, acc.org_id)
        history = (await conn.execute(text(
            """select delta, kind, reason, created_at from public.credit_ledger where org_id = :o and delta <> 0
                order by created_at desc limit 30"""), {"o": acc.org_id})).mappings().all()
        customer = (await conn.execute(text("select stripe_customer_id from public.organizations where id = :o"),
                                       {"o": acc.org_id})).scalar_one()
    return {
        "plan": acc.plan_key, "status": acc.status,
        "period_end": acc.period_end.isoformat() if acc.period_end else None,
        "credits": wallet, "can_manage": customer is not None,
        "plans": [{"key": k, **vars(p)} for k, p in PLANS.items() if k in PAID],
        "packs": [{"key": k, "credits": c, "price_usd": usd} for k, (c, usd) in PACKS.items()],
        "trial_credits": TRIAL_CREDITS,
        "history": [{**h, "created_at": h["created_at"].isoformat()} for h in history],
        "enabled": request.app.state.stripe is not None,
    }


@router.post("/api/billing/checkout")
async def checkout_plan(body: PlanCheckout, request: Request, user_id: UserId):
    gateway = _gateway(request)
    async with request.app.state.engine.connect() as conn:
        acc, email, customer = await _payer(conn, user_id)
    if acc.plan_key in PAID:  # changing plans (with proration) happens in Stripe's portal
        if not customer:
            raise ApiError(409, "invalid_state", "Tu suscripción no tiene cliente en Stripe.")
        return {"url": await gateway.portal(customer)}
    return {"url": await gateway.checkout_plan(org_id=str(acc.org_id), plan=body.plan, email=email,
                                               customer=customer)}


@router.post("/api/billing/packs")
async def checkout_pack(body: PackCheckout, request: Request, user_id: UserId):
    gateway = _gateway(request)
    async with request.app.state.engine.connect() as conn:
        acc, email, customer = await _payer(conn, user_id)
    return {"url": await gateway.checkout_pack(org_id=str(acc.org_id), pack=body.pack, email=email,
                                               customer=customer)}


@router.post("/api/billing/portal")
async def portal(request: Request, user_id: UserId):
    gateway = _gateway(request)
    async with request.app.state.engine.connect() as conn:
        _, _, customer = await _payer(conn, user_id)
    if not customer:
        raise ApiError(409, "invalid_state", "Aún no tienes pagos en Stripe.")
    return {"url": await gateway.portal(customer)}


@router.post("/api/stripe/webhook")
async def webhook(request: Request):
    """Stripe tells us what was paid. Each event is handled once; credits are granted only for paid invoices."""
    gateway = _gateway(request)
    try:
        event = gateway.event(await request.body(), request.headers.get("stripe-signature", ""))
    except Exception:
        raise ApiError(400, "bad_signature", "Firma de Stripe inválida.")
    obj = event["data"]["object"]
    async with request.app.state.engine.begin() as conn:
        fresh = (await conn.execute(text(
            "insert into public.stripe_events (id, type) values (:i, :t) on conflict do nothing returning id"),
            {"i": event["id"], "t": event["type"]})).scalar_one_or_none()
        if fresh is None:
            return {"received": True, "duplicate": True}
        kind = event["type"]
        if kind == "checkout.session.completed":
            await _checkout_completed(conn, obj)
        elif kind == "invoice.paid":
            sub_id = obj.get("subscription") or (((obj.get("parent") or {}).get("subscription_details") or {})
                                                 .get("subscription"))
            if sub_id:
                await _month_paid(conn, await gateway.subscription(sub_id), obj["id"])
        elif kind in ("customer.subscription.updated", "customer.subscription.deleted"):
            await _subscription_changed(conn, obj, event["id"], deleted=kind.endswith("deleted"))
    return {"received": True}


async def _checkout_completed(conn, session: dict) -> None:
    org_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("org_id")
    if not org_id:
        return
    if session.get("customer"):
        await conn.execute(text("update public.organizations set stripe_customer_id = :c where id = :o"),
                           {"c": session["customer"], "o": org_id})
    pack = (session.get("metadata") or {}).get("pack")
    if session.get("mode") == "payment" and pack in PACKS and session.get("payment_status") == "paid":
        await credits.grant(conn, org_id, PACKS[pack][0], "pack", f"Paquete de {PACKS[pack][0]} créditos",
                            expires_at=datetime.now(timezone.utc) + timedelta(days=30 * PACK_MONTHS),
                            stripe_ref=session["id"])


async def _month_paid(conn, sub: dict, invoice_id: str) -> None:
    """A paid month: last month's plan credits go, this month's arrive and last until the period ends."""
    org_id, plan, period_end = await _save_subscription(conn, sub)
    if not org_id or not plan:
        return
    exists = (await conn.execute(text("select 1 from public.credit_buckets where stripe_ref = :r"),
                                 {"r": invoice_id})).first()
    if exists:
        return
    await credits.expire_plan_credits(conn, org_id)
    await credits.grant(conn, org_id, PLANS[plan].credits, "plan", f"Plan {PLANS[plan].label}: créditos del mes",
                        expires_at=period_end + timedelta(days=1) if period_end else None, stripe_ref=invoice_id)


async def _subscription_changed(conn, sub: dict, event_id: str, *, deleted: bool) -> None:
    """An upgrade in the portal gives the difference in credits now; a downgrade or cancel waits for the
    next invoice (the credits already paid for stay until they expire)."""
    org_id = await _org_of(conn, sub)
    before = (await conn.execute(text("select plan, status from public.subscriptions where org_id = :o and app = :a"),
                                 {"o": org_id, "a": APP})).mappings().one_or_none() if org_id else None
    org_id, plan, period_end = await _save_subscription(conn, sub, status="canceled" if deleted else None)
    if not org_id or deleted or not plan or not before or before["plan"] == plan:
        return
    extra = PLANS[plan].credits - PLANS[before["plan"]].credits
    if extra > 0 and sub.get("status") in ("active", "trialing"):
        await credits.grant(conn, org_id, extra, "plan", f"Cambio al plan {PLANS[plan].label}",
                            expires_at=period_end + timedelta(days=1) if period_end else None, stripe_ref=event_id)


async def _save_subscription(conn, sub: dict, status: str | None = None):
    org_id = await _org_of(conn, sub)
    items = (sub.get("items") or {}).get("data") or [{}]
    plan = plan_for_key((items[0].get("price") or {}).get("lookup_key"))
    end = items[0].get("current_period_end") or sub.get("current_period_end")  # moved to items in 2025 APIs
    period_end = datetime.fromtimestamp(end, timezone.utc) if end else None
    if not org_id or not plan:
        log.warning("subscription %s without organization or known plan", sub.get("id"))
        return org_id, None, period_end
    await conn.execute(text(
        """insert into public.subscriptions (org_id, app, plan, status, stripe_subscription_id, current_period_end)
           values (:o, :a, :p, :s, :i, :e)
           on conflict (org_id, app) do update set plan = :p, status = :s, stripe_subscription_id = :i,
                                                   current_period_end = :e, updated_at = now()"""),
        {"o": org_id, "a": APP, "p": plan, "s": status or sub.get("status") or "active", "i": sub["id"],
         "e": period_end})
    if sub.get("customer"):
        await conn.execute(text(
            "update public.organizations set stripe_customer_id = :c where id = :o and stripe_customer_id is null"),
            {"c": sub["customer"], "o": org_id})
    return org_id, plan, period_end


async def _org_of(conn, sub: dict):
    org_id = (sub.get("metadata") or {}).get("org_id")
    if org_id:
        return org_id
    return (await conn.execute(text("select id from public.organizations where stripe_customer_id = :c"),
                               {"c": sub.get("customer")})).scalar_one_or_none()


async def _payer(conn, user_id):
    acc = await credits.account(conn, user_id)
    email, customer = (await conn.execute(text(
        """select p.email, o.stripe_customer_id from public.profiles p, public.organizations o
            where p.id = :u and o.id = :o"""), {"u": user_id, "o": acc.org_id})).one()
    return acc, email, customer


def _gateway(request: Request):
    gateway = request.app.state.stripe
    if gateway is None:
        raise ApiError(503, "not_configured", "Los pagos aún no están configurados.")
    return gateway
