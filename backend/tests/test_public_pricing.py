import re
from pathlib import Path

from app.plans import FREE_PREVIEW_PAGES, PAID, PLANS, PRICE_MXN, TRIAL_CREDITS

PRICING = Path(__file__).parents[2] / "frontend" / "src" / "lib" / "pricing.ts"


def test_landing_prices_match_the_plans():
    """The public pages state prices and credits; they must say what Stripe charges and the ledger grants."""
    source = PRICING.read_text()
    shown = {k: (int(p), int(m), int(c)) for k, p, m, c in
             re.findall(r"key: '(\w+)', label: '[^']+', price: (\d+), price_mxn: (\d+), credits: (\d+)", source)}
    assert shown == {k: (PLANS[k].price_usd, PRICE_MXN[k], PLANS[k].credits) for k in PAID}
    assert f"TRIAL_CREDITS = {TRIAL_CREDITS}" in source
    assert f"FREE_PREVIEW_PAGES = {FREE_PREVIEW_PAGES}" in source
