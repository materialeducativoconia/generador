"""Identities (Mis identidades): the user's editorial lines, one per collection.

Brand strategist (LLM): three clearly different lines for what the user publishes — name, tagline, voice, mascot.
Identity designer (LLM): a visual system for each, from the curated catalogs in app.themes.
Brand guard (code, here): print-safe palettes, the illustration prompt, and no candidate that repeats another,
one of the user's identities or a look many other users already have. Code also draws the seal.
"""

import html
import re

from app.content import Brand, Design
from app.styles import print_palette
from app.themes import ART_STYLES, COVER_LAYOUTS, THEMES

STOP = {"de", "del", "la", "las", "el", "los", "y", "ediciones", "editorial", "edición", "libros"}
# 48x48 seals, filled with the accent; the initials sit in the middle in white.
MARKS = {
    "circle": '<circle cx="24" cy="24" r="22"/>',
    "shield": '<path d="M24 2l19 7v13c0 12-8 20-19 24C13 42 5 34 5 22V9z"/>',
    "leaf": '<path d="M24 2C38 8 45 20 42 33 39 43 30 46 24 46S9 43 6 33C3 20 10 8 24 2z"/>',
    "star": '<path d="M24 1l5.6 7.2 8.9-2 .9 9.1 8.1 4.2-4.5 7.9 4.5 7.9-8.1 4.2-.9 9.1-8.9-2L24 47l-5.6-7.2-8.9 2'
            '-.9-9.1L.5 28.5 5 20.6.5 12.7l8.1-4.2.9-9.1 8.9 2z"/>',
    "badge": '<rect x="2" y="6" width="44" height="36" rx="10"/>',
    "book": '<path d="M2 8c8-3 15-2 22 3 7-5 14-6 22-3v34c-8-3-15-2-22 3-7-5-14-6-22-3z"/>',
}


def initials(name: str) -> str:
    words = [w for w in re.findall(r"[^\W\d_]+", name) if w.lower() not in STOP] or name.split()
    return "".join(w[0] for w in words[:2]).upper() or "M"


def mark_svg(brand: Brand, accent: str, font: str = "Nunito", size_mm: float | None = None) -> str:
    """The imprint's seal as inline SVG: the same markup goes in the PDF and the web preview."""
    letters = html.escape((brand.initials or initials(brand.name))[:3])
    fs = 19 if len(letters) < 3 else 14
    dims = f' width="{size_mm}mm" height="{size_mm}mm"' if size_mm else ""
    return (f'<svg class="seal" viewBox="0 0 48 48"{dims} xmlns="http://www.w3.org/2000/svg">'
            f'<g fill="{accent}">{MARKS[brand.mark]}</g>'
            f'<text x="24" y="{24 + fs * 0.36:.1f}" text-anchor="middle" font-family="{html.escape(font)}" '
            f'font-weight="800" font-size="{fs}" fill="#FFFFFF">{letters}</text></svg>')


def look_key(d: Design) -> tuple:
    """Two identities with the same key would look like the same line on a shelf."""
    return d.theme, d.illustration, d.cover_layout, d.head_font


def guard(looks: list[Design], taken: set[tuple]) -> list[Design]:
    """Fix each look for print and nudge it until it is unlike the others and unlike `taken`."""
    seen = set(taken)
    out = []
    styles, layouts = list(ART_STYLES), list(COVER_LAYOUTS)
    for i, d in enumerate(looks):
        d = d.model_copy(update={"palette": print_palette(d.palette), "style_id": None})
        if d.illustration is None:
            d.illustration = styles[i % len(styles)]
        for n in range(len(styles) * len(layouts)):
            if look_key(d) not in seen:
                break
            d.illustration = styles[(styles.index(d.illustration) + 1) % len(styles)]
            if n % len(styles) == len(styles) - 1:
                d.cover_layout = layouts[(layouts.index(d.cover_layout) + 1) % len(layouts)]
        d.art_style = ART_STYLES[d.illustration][1]
        seen.add(look_key(d))
        out.append(d)
    return out


def describe(d: Design) -> str:
    """A short Spanish summary, for the strategist and designer prompts."""
    brand = d.brand.name if d.brand else "—"
    return (f"{brand}: tema {THEMES[d.theme].label}, ilustración {d.illustration or '—'}, portada {d.cover_layout}, "
            f"letra {d.head_font or 'del tema'}, acento {d.palette[2]}")
