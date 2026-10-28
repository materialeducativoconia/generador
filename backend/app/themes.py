"""Curated layout themes. The Designer agent picks one per tome and a palette; it never writes CSS.

Every font here is bundled (OFL) under assets/fonts for WeasyPrint and is also on Google Fonts,
so the web preview (frontend/src/lib/themes.ts) matches the PDF.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Theme:
    label: str
    use_for: str  # shown to the Designer
    head: str  # font family
    head_file: str
    head_weight: int
    body: str
    body_file: str
    body_size_pt: float
    opener: str  # section opener style, see the template
    radius_mm: float
    title_case: str = "none"  # text-transform for section titles


THEMES: dict[str, Theme] = {
    "juego": Theme("Juego", "preescolar y primeros grados: formas redondas, grande y alegre",
                   "Fredoka", "Fredoka-Variable.ttf", 600, "Andika", "Andika-Regular.ttf", 13.5, "blob", 6),
    "cuaderno": Theme("Cuaderno", "fichas y cuadernillos de práctica: escrito a mano, cercano, como un cuaderno escolar",
                      "Patrick Hand", "PatrickHand-Regular.ttf", 400, "Andika", "Andika-Regular.ttf", 12.5, "tape", 2),
    "editorial": Theme("Editorial", "adultos, secundaria o temas serios: tipografía con serifa, elegante y sobria",
                       "Fraunces", "Fraunces-Variable.ttf", 700, "Nunito", "Nunito-Variable.ttf", 11, "numeral", 1.5),
    "metodo": Theme("Método", "métodos paso a paso (música, deportes, manualidades): lecciones con insignia",
                    "Baloo 2", "Baloo2-Variable.ttf", 800, "Nunito", "Nunito-Variable.ttf", 11.5, "badge", 4),
    "ciencia": Theme("Ciencia", "ciencias, matemáticas, tecnología: limpio, moderno, muy legible",
                     "Lexend", "Lexend-Variable.ttf", 700, "Lexend", "Lexend-Variable.ttf", 10.5, "bar", 3),
    "clasico": Theme("Clásico", "cuando ninguno encaja: neutro y claro",
                     "Nunito", "Nunito-Variable.ttf", 900, "Andika", "Andika-Regular.ttf", 11.5, "plain", 4),
}

# Heading fonts a library style may pick (all bundled under assets/fonts and on Google Fonts): file, weight.
FONTS: dict[str, tuple[str, int]] = {
    "Fredoka": ("Fredoka-Variable.ttf", 600), "Patrick Hand": ("PatrickHand-Regular.ttf", 400),
    "Fraunces": ("Fraunces-Variable.ttf", 700), "Baloo 2": ("Baloo2-Variable.ttf", 800),
    "Lexend": ("Lexend-Variable.ttf", 700), "Nunito": ("Nunito-Variable.ttf", 900),
    "Pacifico": ("Pacifico-Regular.ttf", 400), "Sniglet": ("Sniglet-ExtraBold.ttf", 800),
}
# Page frames drawn by @page (inside the margin, so the text area stays the same): CSS border, radius in mm.
FRAMES: dict[str, tuple[str, float]] = {
    "none": ("none", 0), "line": ("1.2pt solid", 0), "rounded": ("1.6pt solid", 6),
    "dashed": ("1.4pt dashed", 4), "double": ("3pt double", 3),
}


def theme_for(design) -> Theme:
    """The curated theme, with a library style's heading font when it has one."""
    th = THEMES[design.theme if design else "clasico"]
    if design and design.head_font:
        file, weight = FONTS[design.head_font]
        th = replace(th, head=design.head_font, head_file=file, head_weight=weight)
    return th


DEFAULT_PALETTE = ["#F5F3FF", "#1C1917", "#4F46E5"]  # background tint, ink, accent

# Decorative marks for section openers, filled with the accent. WeasyPrint clips an <svg> that has an
# opacity attribute, so the template never sets one.
ORNAMENTS: dict[str, str] = {
    "estrellas": '<path stroke-width="0" d="M12 2l2.9 6.1 6.6.8-4.9 4.6 1.3 6.5L12 16.8 6.1 20l1.3-6.5L2.5 8.9l6.6-.8z"/>',
    "notas": '<path stroke-width="0" d="M9 18a3 3 0 1 1-2-2.8V5l12-2v11a3 3 0 1 1-2-2.8V6.3L9 7.6z"/>',
    "hojas": '<path stroke-width="0" d="M5 19c0-8 5-14 15-15-1 10-7 15-15 15z"/>'
             '<path fill="none" stroke="#fff" stroke-width="1.4" stroke-linecap="round" d="M7 17l8-8"/>',
    "puntos": '<g stroke-width="0"><circle cx="5" cy="12" r="2.6"/><circle cx="12" cy="12" r="2.6"/>'
              '<circle cx="19" cy="12" r="2.6"/></g>',
    "formas": '<g stroke-width="0"><circle cx="6" cy="7" r="4"/><rect x="13" y="3" width="8" height="8" rx="1.5"/>'
              '<path d="M3 21l5-8 5 8z"/><path d="M17 13l4 4-4 4-4-4z"/></g>',
    "ninguno": "",
}


def mix(hex_a: str, hex_b: str, t: float) -> str:
    """t=0 gives a, t=1 gives b. WeasyPrint has no color-mix(), so tints are computed here."""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))
