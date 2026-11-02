"""The Layout designer: how each plate of a picture book is composed, decided before it is painted.

A publisher never prints the same template on every page: some pictures bleed to the edges with the text on top,
some sit above a calm text band, some are cut-out vignettes on white with the facts around them, and some run
across a double page. Code picks the composition (deterministic, free): it follows the house style's taste, never
repeats the previous plate's composition, and spends a section's spare page on one double-page spread.
"""

from app.content import SectionContent

LAYOUTS = ("bleed", "band", "vignette", "spread")
# The order each house style prefers; others use the default.
TASTE = {
    "enciclopedia": ["vignette", "bleed", "band"],
    "didactico": ["band", "vignette", "bleed"],
    "gouache": ["bleed", "band", "vignette"],
    "collage": ["vignette", "bleed", "band"],
}
DEFAULT = ["bleed", "band", "vignette"]
STORY = ["band", "bleed"]  # a story reads best with its text beside the picture, never a cut-out encyclopedia page
# What the painting must leave room for, by composition (the plate's subject is extended with it).
COMPOSE = {
    "bleed": "",
    "band": " (composition for the upper part of a page: characters and subject in the middle, nothing important "
            "touching the bottom edge)",
    "vignette": " (a cut-out vignette: the subject and characters isolated on a pure white background, no scenery, "
                "no frame, no border, only a soft shadow on the ground, like an encyclopedia illustration)",
    "spread": " (a wide panoramic double-page scene: keep the vertical strip in the very centre, the book's fold, "
              "free of faces and important details; calm sky or ground in the top-left for a title)",
}


def lay_out(content: SectionContent, *, position: int, pages: int | None, house_style: str | None,
            story: bool = False) -> None:
    """Gives each plate without one its composition. A plate with an exact diagram keeps the full bleed (its card
    sits over the calm lower third); a section with a page more than plates gets one spread."""
    plates = [b for b in content.blocks if b.type == "image" and b.size == "plate"]
    spare = 1 if pages and pages > len(plates) else 0
    taste = STORY if story else TASTE.get(house_style or "", DEFAULT)
    last = None
    for i, b in enumerate(plates):
        if b.layout:
            last = b.layout
            continue
        if b.inset:
            b.layout = "bleed"
        elif spare and i == (0 if len(plates) == 1 else 1):
            b.layout, spare = "spread", 0
        else:
            pick = taste[(position - 1 + i) % len(taste)]
            b.layout = pick if pick != last else taste[(position + i) % len(taste)]
        last = b.layout
