"""Plans (monthly, USD) and what each action costs in credits. One credit is about one generated page.

Worst case a credit costs us ~$0.026 (a page written plus a colour picture, app.pricing), so the margins hold
even when every page is illustrated. Prices and grants live here and in Stripe (scripts/stripe_setup.py).
"""

from dataclasses import dataclass

APP = "generador"


@dataclass(frozen=True)
class Plan:
    label: str
    price_usd: int
    credits: int  # per month; they do not roll over
    watermark: bool  # "Hecho con…" at the foot of the PDF: classroom use only
    commercial: bool  # the user may sell what they make
    word: bool  # editable Word download
    print_edition: bool  # KDP-ready interior and cover wrap
    styles: int  # library styles
    identities: int
    logo: bool
    premium: bool  # better AI models, at twice the credits
    max_pages: int  # per tome
    concurrent: int  # tomes generating at once
    seats: int


PLANS: dict[str, Plan] = {
    "prueba": Plan("Prueba", 0, 0, True, False, False, False, 0, 0, False, False, 24, 1, 1),
    "docente": Plan("Docente", 9, 150, True, False, False, False, 0, 0, False, False, 24, 1, 1),
    "creador": Plan("Creador", 24, 500, False, True, True, True, 5, 1, True, False, 100, 3, 1),
    "editorial": Plan("Editorial", 69, 1500, False, True, True, True, 30, 20, True, True, 200, 10, 3),
}
PAID = ("docente", "creador", "editorial")
TRIAL_CREDITS = 40
# Extra credits, one-off: pricier per credit than a plan, so moving up a plan is the better deal. Valid 12 months.
PACKS: dict[str, tuple[int, int]] = {"pack_100": (100, 8), "pack_300": (300, 21), "pack_1000": (1000, 60)}
PACK_MONTHS = 12

# Credits per action
OUTLINE = 1  # research + the Architect + the Designer
COVER = 4
IDENTITY = 3
STYLE = 2


def lookup_key(plan: str) -> str:
    """The Stripe price of a plan, found by lookup key so no price ids live in config."""
    return f"{plan}_monthly"


def plan_for_key(key: str | None) -> str | None:
    plan = (key or "").removesuffix("_monthly")
    return plan if plan in PAID else None


def tome_credits(pages: int) -> int:
    """Outline, cover and one credit per page: what the cost window shows before a tome is created."""
    return OUTLINE + COVER + pages
