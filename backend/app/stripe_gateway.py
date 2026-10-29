"""Our only door to Stripe: Checkout for plans and packs, the customer portal, and webhook verification.

Prices are found by lookup key (app.plans), so no price ids live in config. The SDK is synchronous; calls
run in a thread. Tests swap this class for a fake (app.state.stripe).
"""

import asyncio
import json

import stripe

from app.plans import PACKS, lookup_key


class StripeGateway:
    def __init__(self, secret_key: str, webhook_secret: str, app_url: str):
        self.client = stripe.StripeClient(secret_key)
        self.webhook_secret = webhook_secret
        self.app_url = app_url.rstrip("/")
        self._prices: dict[str, str] = {}

    async def _price(self, key: str) -> str:
        if key not in self._prices:
            found = await asyncio.to_thread(self.client.v1.prices.list,
                                            {"lookup_keys": [key], "active": True, "limit": 1})
            if not found.data:
                raise RuntimeError(f"Stripe price {key} missing; run scripts/stripe_setup.py")
            self._prices[key] = found.data[0].id
        return self._prices[key]

    async def checkout_plan(self, *, org_id: str, plan: str, email: str, customer: str | None) -> str:
        params = {
            "mode": "subscription", "client_reference_id": org_id,
            "line_items": [{"price": await self._price(lookup_key(plan)), "quantity": 1}],
            "metadata": {"org_id": org_id, "plan": plan},
            "subscription_data": {"metadata": {"org_id": org_id}},
            "success_url": f"{self.app_url}/app/plan?pago=ok", "cancel_url": f"{self.app_url}/app/plan",
            "allow_promotion_codes": True,
            **({"customer": customer} if customer else {"customer_email": email}),
        }
        session = await asyncio.to_thread(self.client.v1.checkout.sessions.create, params)
        return session.url

    async def checkout_pack(self, *, org_id: str, pack: str, email: str, customer: str | None) -> str:
        params = {
            "mode": "payment", "client_reference_id": org_id,
            "line_items": [{"price": await self._price(pack), "quantity": 1}],
            "metadata": {"org_id": org_id, "pack": pack, "credits": str(PACKS[pack][0])},
            "success_url": f"{self.app_url}/app/plan?pago=ok", "cancel_url": f"{self.app_url}/app/plan",
            **({"customer": customer} if customer else {"customer_email": email, "customer_creation": "always"}),
        }
        session = await asyncio.to_thread(self.client.v1.checkout.sessions.create, params)
        return session.url

    async def portal(self, customer: str) -> str:
        session = await asyncio.to_thread(self.client.v1.billing_portal.sessions.create,
                                          {"customer": customer, "return_url": f"{self.app_url}/app/plan"})
        return session.url

    async def subscription(self, subscription_id: str) -> dict:
        sub = await asyncio.to_thread(self.client.v1.subscriptions.retrieve, subscription_id)
        return json.loads(str(sub))

    def event(self, payload: bytes, signature: str) -> dict:
        """Raises unless Stripe signed this payload with our webhook secret."""
        stripe.WebhookSignature.verify_header(payload.decode(), signature, self.webhook_secret, 300)
        return json.loads(payload)
