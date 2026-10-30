"""Plans and credits: what each plan may do, charges and refunds, and Stripe's webhook granting credits."""

import json
import time
import uuid

from tests.db.conftest import subscribe
from tests.db.test_jobs import OUTLINE, engine, run_next  # noqa: F401  (engine is a fixture)
from tests.db.test_me import bearer
from tests.db.test_series_api import NEW_TOME, create_tome, outline_ready
from tests.fakes import ScriptedLLM


async def credits_of(client, key, user):
    return (await client.get("/api/billing", headers=bearer(key, user))).json()["credits"]["total"]


async def test_credits_pay_a_tome_and_come_back_when_it_fails(raw_db, google_user, client, key, engine):
    user = await google_user(plan="docente", credits=40)
    assert await credits_of(client, key, user) == 40

    sid = (await create_tome(client, key, user))["series"]["id"]
    assert await credits_of(client, key, user) == 35  # outline 1 + cover 4

    await run_next(engine, ScriptedLLM("no", "tampoco"))  # the Architect fails twice: the job fails

    assert await raw_db.fetchval("select status from public.series where id = $1", sid) == "outline_failed"
    assert await credits_of(client, key, user) == 40
    kinds = await raw_db.fetch("select kind from public.credit_ledger l join public.memberships m using (org_id)"
                               " where m.user_id = $1 order by l.created_at", user)
    assert [k["kind"] for k in kinds] == ["spend", "spend", "refund", "refund"]


async def test_sections_cost_their_pages_and_the_cover_follows_its_job(raw_db, google_user, client, key, engine):
    user = await google_user(plan="docente", credits=40)
    h = bearer(key, user)
    sid = (await create_tome(client, key, user))["series"]["id"]
    await run_next(engine, ScriptedLLM(json.dumps(OUTLINE)))
    cover_job = await raw_db.fetchval("select id from public.generation_jobs where series_id = $1 and kind = 'cover'",
                                      sid)
    assert await raw_db.fetchval("select -delta from public.credit_ledger where job_id = $1", cover_job) == 4

    await raw_db.execute("update public.lessons set pages = 3 where series_id = $1", sid)
    assert (await client.post(f"/api/series/{sid}/lessons/generate", json={}, headers=h)).status_code == 202
    sections = await raw_db.fetchval("select count(*) from public.lessons where series_id = $1", sid)
    assert await credits_of(client, key, user) == 35 - 3 * sections


async def test_without_credits_nothing_is_queued(raw_db, google_user, client, key):
    user = await google_user(plan="docente", credits=2)

    response = await client.post("/api/series", json=NEW_TOME, headers=bearer(key, user))

    assert response.status_code == 402 and response.json()["error"]["code"] == "insufficient_credits"
    assert await raw_db.fetchval("select count(*) from public.series where user_id = $1", user) == 0


async def test_each_plan_unlocks_its_features(raw_db, google_user, client, key):
    user = await google_user(plan=None)
    h = bearer(key, user)

    big = await client.post("/api/series", json={**NEW_TOME, "page_count": 48}, headers=h)
    assert big.status_code == 403 and big.json()["error"]["code"] == "plan_required"
    style = await client.post("/api/styles", json={"name": "x", "content_type": "image/png", "size": 10}, headers=h)
    assert style.status_code == 403 and "Creador" in style.json()["error"]["message"]
    assert (await client.post("/api/identities", json={"about": "Fichas"}, headers=h)).status_code == 403
    sid = (await create_tome(client, key, user, page_count=4))["series"]["id"]  # the free preview (4 pages at most)
    await outline_ready(raw_db, sid)
    await raw_db.execute("update public.series set status = 'ready' where id = $1", sid)
    pdf = await client.post(f"/api/series/{sid}/exports", json={}, headers=h)
    assert pdf.status_code == 403 and pdf.json()["error"]["details"]["feature"] == "download"

    await subscribe(raw_db, user, "docente")
    word = await client.post(f"/api/series/{sid}/exports", json={"format": "docx"}, headers=h)
    assert word.status_code == 403
    pdf = await client.post(f"/api/series/{sid}/exports", json={}, headers=h)
    job = await raw_db.fetchval("select payload->>'watermark' from public.generation_jobs where id = "
                                "(select job_id from public.exports where id = $1)", pdf.json()["export"]["id"])
    assert job == "true"

    await subscribe(raw_db, user, "creador")
    assert (await client.post(f"/api/series/{sid}/exports", json={"format": "docx"}, headers=h)).status_code == 202
    me = (await client.get("/api/me", headers=h)).json()
    assert me["plan"]["key"] == "creador" and me["plan"]["watermark"] is False


class FakeStripe:
    def __init__(self, subscriptions=None):
        self.subscriptions = subscriptions or {}
        self.sessions = []

    def event(self, payload, signature):
        if signature != "ok":
            raise ValueError("bad signature")
        return json.loads(payload)

    async def subscription(self, sub_id):
        return self.subscriptions[sub_id]

    async def checkout_plan(self, **kw):
        self.sessions.append(("plan", kw))
        return "https://checkout.stripe.test/plan"

    async def checkout_pack(self, **kw):
        self.sessions.append(("pack", kw))
        return "https://checkout.stripe.test/pack"

    async def portal(self, customer):
        return f"https://billing.stripe.test/{customer}"


def sub(sub_id, org, plan, status="active"):
    return {"id": sub_id, "customer": "cus_1", "status": status, "metadata": {"org_id": str(org)},
            "items": {"data": [{"price": {"lookup_key": f"{plan}_monthly"},
                                "current_period_end": int(time.time()) + 30 * 86400}]}}


RUN = uuid.uuid4().hex[:8]  # Stripe ids are global: stripe_events and stripe_ref outlive a test run


async def send(client, event_id, kind, obj, signature="ok"):
    return await client.post("/api/stripe/webhook", content=json.dumps(
        {"id": f"{event_id}_{RUN}", "type": kind, "data": {"object": obj}}), headers={"stripe-signature": signature})


async def test_stripe_grants_packs_and_monthly_credits_once(raw_db, google_user, client, key):
    user = await google_user(plan=None)
    org = await raw_db.fetchval("select org_id from public.memberships where user_id = $1", user)
    stripe = FakeStripe({"sub_1": sub("sub_1", org, "docente")})
    client._transport.app.state.stripe = stripe
    h = bearer(key, user)

    assert (await client.post("/api/billing/checkout", json={"plan": "docente"}, headers=h)).json()["url"] \
        == "https://checkout.stripe.test/plan"
    assert stripe.sessions[0][1]["org_id"] == str(org)
    assert (await send(client, "evt_x", "invoice.paid", {}, signature="forged")).status_code == 400

    pack = {"id": f"cs_{RUN}", "mode": "payment", "payment_status": "paid", "client_reference_id": str(org),
            "customer": "cus_1", "metadata": {"pack": "pack_100"}}
    await send(client, "evt_1", "checkout.session.completed", pack)
    await send(client, "evt_1", "checkout.session.completed", pack)  # Stripe retries: granted once
    assert await credits_of(client, key, user) == 100

    await send(client, "evt_2", "invoice.paid", {"id": f"in_1_{RUN}", "subscription": "sub_1"})
    assert await credits_of(client, key, user) == 250
    billing = (await client.get("/api/billing", headers=h)).json()
    assert billing["plan"] == "docente" and billing["can_manage"]

    # Next month: last month's plan credits go, this month's arrive (new API shape for the subscription id)
    await raw_db.execute("update public.credit_buckets set remaining = 100 where source = 'plan' and org_id = $1", org)
    await send(client, "evt_3", "invoice.paid", {"id": f"in_2_{RUN}", "parent": {"subscription_details":
                                                                         {"subscription": "sub_1"}}})
    assert await credits_of(client, key, user) == 250

    stripe.subscriptions["sub_1"] = sub("sub_1", org, "creador")  # upgrade in the portal: the difference now
    await send(client, "evt_4", "customer.subscription.updated", stripe.subscriptions["sub_1"])
    assert await credits_of(client, key, user) == 250 + 350
    assert (await client.post("/api/billing/checkout", json={"plan": "editorial"}, headers=h)).json()["url"] \
        == "https://billing.stripe.test/cus_1"

    await send(client, "evt_5", "customer.subscription.deleted", stripe.subscriptions["sub_1"])
    assert (await client.get("/api/me", headers=h)).json()["plan"]["key"] == "prueba"
