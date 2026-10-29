"""Creates (once) the Stripe products and USD prices the app finds by lookup key, and the webhook endpoint.

    STRIPE_SECRET_KEY=sk_test_… uv run python scripts/stripe_setup.py https://<api-host>

Run it again safely: existing lookup keys are kept. Prints the webhook secret (whsec_…) the first time; put it
in STRIPE_WEBHOOK_SECRET on Render.
"""

import os
import sys

import stripe

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.plans import PACKS, PAID, PLANS, lookup_key  # noqa: E402

EVENTS = ["checkout.session.completed", "invoice.paid", "customer.subscription.updated",
          "customer.subscription.deleted"]


def price(client, key: str, name: str, cents: int, recurring: bool) -> None:
    if client.v1.prices.list({"lookup_keys": [key], "limit": 1}).data:
        print(f"= {key}")
        return
    product = client.v1.products.create({"name": name})
    client.v1.prices.create({"product": product.id, "currency": "usd", "unit_amount": cents, "lookup_key": key,
                             **({"recurring": {"interval": "month"}} if recurring else {})})
    print(f"+ {key}")


def main() -> None:
    client = stripe.StripeClient(os.environ["STRIPE_SECRET_KEY"])
    for plan in PAID:
        p = PLANS[plan]
        price(client, lookup_key(plan), f"Plan {p.label} · {p.credits} créditos al mes", p.price_usd * 100, True)
    for key, (n, usd) in PACKS.items():
        price(client, key, f"Paquete de {n} créditos", usd * 100, False)
    if len(sys.argv) > 1:
        url = sys.argv[1].rstrip("/") + "/api/stripe/webhook"
        if any(e.url == url for e in client.v1.webhook_endpoints.list({"limit": 100}).data):
            print(f"= webhook {url}")
        else:
            endpoint = client.v1.webhook_endpoints.create({"url": url, "enabled_events": EVENTS})
            print(f"+ webhook {url}\nSTRIPE_WEBHOOK_SECRET={endpoint.secret}")


if __name__ == "__main__":
    main()
