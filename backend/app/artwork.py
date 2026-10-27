"""Sheets: the Illustrator paints up to four pictures per call in a 2x2 grid, then they are cut apart.

One call per sheet is the cost win (one image price for four pictures) and the consistency win
(the four share one generation, one style, one set of characters).
"""

import io
from dataclasses import dataclass, field

from PIL import Image

from app.content import ArtPlan, Design
from app.illustrator import ASPECT, NO_TEXT, THEME_STYLE

SLOTS = {(1, 1): ["the only panel"], (2, 2): ["top-left", "top-right", "bottom-left", "bottom-right"]}


@dataclass
class ImageRequest:
    ref: str  # "<lesson position>:<block id>", unique in the tome
    lesson_id: str
    block_id: str
    kind: str
    size: str
    subject: str


@dataclass
class Sheet:
    family: str  # "line" (colouring pages) or "colour"; never mixed in one sheet
    aspect: str  # of each panel; a 2x2 grid of them has the same aspect
    requests: list[ImageRequest] = field(default_factory=list)

    @property
    def cols(self) -> int:
        return 1 if len(self.requests) == 1 else 2

    rows = cols


def plan_sheets(requests: list[ImageRequest], per_sheet: int = 4) -> list[Sheet]:
    groups: dict[tuple[str, str], list[ImageRequest]] = {}
    for r in requests:
        groups.setdefault(("line" if r.kind == "line_art" else "colour", ASPECT.get(r.size, "3:4")), []).append(r)
    return [Sheet(family, aspect, items[i:i + per_sheet])
            for (family, aspect), items in groups.items() for i in range(0, len(items), per_sheet)]


def sheet_prompt(sheet: Sheet, plan: ArtPlan, design: Design | None, feedback: str | None = None) -> str:
    slots = SLOTS[(sheet.cols, sheet.rows)]
    panels = [f"{slot}: {plan.prompts.get(r.ref, r.subject)}" for slot, r in zip(slots, sheet.requests)]
    panels += [f"{slot}: leave this panel completely empty and white" for slot in slots[len(sheet.requests):]]
    cast = "; ".join(f"{c.name} is {c.look}" for c in plan.characters)
    if sheet.family == "line":
        medium = ("Black and white coloring book line art: thick, clean, continuous black outlines, closed shapes, "
                  "large areas to color, no shading, no gray, no color, pure white background.")
    else:
        palette = ", ".join(design.palette) if design else "soft, friendly colors"
        medium = f"Full color illustration, {THEME_STYLE[design.theme if design else 'clasico']}, palette {palette}, white background."
    layout = ("A single illustration." if sheet.cols == 1 else
              "A 2x2 grid of four separate illustrations for the same children's book, separated by wide pure white "
              "gutters, no borders or frames around panels. Every panel uses exactly the same art style and the "
              "same characters.")
    prompt = (f"{layout} Art style: {plan.style}. {medium} "
              f"{('Recurring characters, drawn identically everywhere: ' + cast + '.') if cast else ''} "
              f"The attached image is this book's cover: match its style and characters. "
              f"{' '.join(p + '.' for p in panels)} {NO_TEXT}")
    if feedback:
        prompt += f" Fix these problems from the previous attempt: {feedback}"
    return prompt


def slice_sheet(data: bytes, cols: int, rows: int) -> list[bytes]:
    """Cuts at the whitest column/row near the middle (the model rarely centres gutters exactly)."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    grey = im.convert("L")
    xs = [0, _gutter(grey, axis=0), im.width] if cols == 2 else [0, im.width]
    ys = [0, _gutter(grey, axis=1), im.height] if rows == 2 else [0, im.height]
    panels = []
    for r in range(rows):
        for c in range(cols):
            panels.append(_png(_trim(im.crop((xs[c], ys[r], xs[c + 1], ys[r + 1])))))
    return panels


def _gutter(grey: Image.Image, axis: int) -> int:
    """axis=0: x of the whitest column in the central 30–70 % band; axis=1: y of the whitest row."""
    small = grey.copy()
    small.thumbnail((400, 400))
    w, h = small.size
    length = w if axis == 0 else h
    px = small.load()

    def darkness(i: int) -> int:
        return sum(255 - (px[i, j] if axis == 0 else px[j, i]) for j in range(h if axis == 0 else w))

    lo, hi = int(length * 0.3), int(length * 0.7)
    best = min(range(lo, hi), key=lambda i: (darkness(i), abs(i - length / 2)))
    return round(best * (grey.width if axis == 0 else grey.height) / length)


def _trim(panel: Image.Image) -> Image.Image:
    """Crops to the drawing plus a small margin, so gutters don't become blank space on the page."""
    mask = panel.convert("L").point(lambda v: 255 if v < 235 else 0)
    box = mask.getbbox()
    if not box:
        return panel
    m = round(max(panel.size) * 0.03)
    return panel.crop((max(box[0] - m, 0), max(box[1] - m, 0), min(box[2] + m, panel.width),
                       min(box[3] + m, panel.height)))


def _png(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()
