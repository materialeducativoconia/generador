"""Sheets: the Illustrator paints up to four pictures per call in a 2x2 grid, then they are cut apart.

One call per sheet is the cost win (one image price for four pictures) and the consistency win
(the four share one generation, one style, one set of characters).
"""

import io
import re
from dataclasses import dataclass, field

from PIL import Image

from app.content import ArtPlan, Design
from app.illustrator import ASPECT, NO_TEXT, THEME_STYLE
from app.printing import PAPERS, page_geometry

# Pixels the image model returns at "1K" per aspect; "2K" and "4K" double and quadruple them.
PIXELS_1K = {"1:1": (1024, 1024), "3:4": (896, 1200), "4:3": (1200, 896)}
RESOLUTIONS = {"1K": 1, "2K": 2, "4K": 4}
# Colour art must print at 300 dpi on its own; colouring pages are traced to vectors and only need the shapes.
TARGET_DPI = {"colour": 300, "line": 150, "icon": 150}
ICON_MM = 30  # the largest a worksheet prints a word's picture
ICONS_PER_SHEET = 16


@dataclass
class ImageRequest:
    ref: str  # "<lesson position>:<block id>", unique in the tome
    lesson_id: str
    block_id: str
    kind: str
    size: str
    subject: str
    word: str | None = None  # a worksheet word's picture (kind "icon"), stored in the block's `pictures`
    layout: str | None = None  # a plate's composition (app.layout): its own aspect and page area
    compose: str = ""  # room the page layout needs (kept after the Art director's rewrite of the scene)
    check: str | None = None  # what the Reviewer verifies: the plate's question and facts, else the subject


@dataclass
class Sheet:
    family: str  # "line" (colouring pages), "colour" or "icon" (worksheet pictures); never mixed in one sheet
    aspect: str  # of each panel; a 2x2 grid of them has the same aspect
    requests: list[ImageRequest] = field(default_factory=list)

    @property
    def cols(self) -> int:
        n = len(self.requests)
        return next(k for k in (1, 2, 3, 4) if k * k >= n)

    rows = cols

    @property
    def resolution(self) -> str:
        """The cheapest resolution at which every panel reaches its target dpi on the largest page size."""
        for name, scale in RESOLUTIONS.items():
            w, h = (v * scale / self.cols for v in PIXELS_1K[self.aspect])
            if all(_dpi(w, h, r.size, r.layout) >= TARGET_DPI[self.family] for r in self.requests):
                return name
        return "4K"


def _dpi(w: float, h: float, size: str, layout: str | None = None) -> float:
    def on(paper: str) -> float:
        geo = page_geometry(paper, print_edition=False)
        if size == "icon":
            return 25.4 / min(ICON_MM / w, ICON_MM / h)
        if size == "plate" and layout in PLATE_BOX:
            box_w, box_h = PLATE_BOX[layout](geo)
            return 25.4 / min(box_w / w, box_h / h)
        box_w = geo.w if size == "plate" else geo.content_w * (0.6 if size == "small" else 1)
        return 25.4 / min(box_w / w, getattr(geo, size) / h)

    return min(on(paper) for paper in PAPERS)


# The page area each plate composition fills (mm), for the resolution; the full bleed is the whole page.
PLATE_BOX = {"spread": lambda g: (2 * g.w, g.h), "band": lambda g: (g.w, g.h * 0.62),
             "vignette": lambda g: (g.content_w, g.h * 0.5)}
LAYOUT_ASPECT = {"spread": "3:2", "band": "4:3", "vignette": "1:1"}


def _family(kind: str) -> str:
    return {"line_art": "line", "icon": "icon"}.get(kind, "colour")


def plan_sheets(requests: list[ImageRequest], per_sheet: int = 4) -> list[Sheet]:
    groups: dict[tuple[str, str], list[ImageRequest]] = {}
    for r in requests:
        aspect = LAYOUT_ASPECT.get(r.layout or "") or ASPECT.get(r.size, "3:4")
        groups.setdefault((_family(r.kind), aspect), []).append(r)
    return [Sheet(family, aspect, items[i:i + n])
            for (family, aspect), items in groups.items()
            for n in [ICONS_PER_SHEET if family == "icon" else per_sheet] for i in range(0, len(items), n)]


def _slots(n: int) -> list[str]:
    if n == 1:
        return ["the only panel"]
    if n == 2:
        return ["top-left", "top-right", "bottom-left", "bottom-right"]
    return [f"row {r + 1}, column {c + 1}" for r in range(n) for c in range(n)]


def icon_sheet_prompt(sheet: Sheet, feedback: str | None = None) -> str:
    """Worksheet pictures: one plain object per cell, the same clip-art style in every tome (they are shared)."""
    n = sheet.cols
    cells = [f"{slot}: {r.subject}" for slot, r in zip(_slots(n), sheet.requests)]
    cells += [f"{slot}: empty, pure white" for slot in _slots(n)[len(sheet.requests):]]
    layout = ("A single" if n == 1 else f"A {n}x{n} grid of separate") + (
        " simple black-and-white line drawing" + ("" if n == 1 else "s, one per cell,") +
        " for a children's reading workbook: clip-art style, one recognisable object or animal per cell, centred, "
        "drawn as a young child would name the Spanish word given, thick clean continuous black outlines, closed "
        "shapes, no shading, no gray, no color, pure white background")
    gutters = "" if n == 1 else ", wide pure white gutters between cells, no borders or frames"
    prompt = f"{layout}{gutters}. Each cell names the Spanish word to draw. {' '.join(c + '.' for c in cells)} {NO_TEXT}"
    if feedback:
        prompt += f" Fix these problems from the previous attempt: {feedback}"
    return prompt


QUOTED = re.compile(r"«[^»]{1,200}»|“[^”]{1,200}”|\"[^\"]{1,200}\"")


def unquote(scene: str) -> str:
    """Words quoted in a scene (a line said aloud, a sign, a to-do list) come out painted, in English and misspelt:
    the painter gets a picture instead, and the printed page keeps the words."""
    return QUOTED.sub("a simple picture, no words", scene)


def sheet_prompt(sheet: Sheet, plan: ArtPlan, design: Design | None, feedback: str | None = None,
                 sheets: int = 0) -> str:
    if sheet.family == "icon":
        return icon_sheet_prompt(sheet, feedback)
    slots = _slots(sheet.cols)
    panels = [f"{slot}: {unquote(plan.prompts.get(r.ref, r.subject))}{r.compose}" for slot, r in zip(slots, sheet.requests)]
    panels += [f"{slot}: leave this panel completely empty and white" for slot in slots[len(sheet.requests):]]
    cast = "; ".join(f"{c.name} is {c.look}" for c in plan.characters)
    if sheet.family == "line":
        medium = ("Black and white coloring book line art: thick, clean, continuous black outlines, closed shapes, "
                  "large areas to color, no shading, no gray, no color, no filled black areas or silhouettes, "
                  "pure white background.")
    else:
        palette = ", ".join(design.palette) if design else "soft, friendly colors"
        look = (design.art_style if design and design.art_style else THEME_STYLE[design.theme if design else "clasico"])
        medium = f"Full color illustration, {look}, palette {palette}, white background."
    layout = ("A single illustration." if sheet.cols == 1 else
              "A 2x2 grid of four separate illustrations for the same children's book, separated by wide pure white "
              "gutters, no borders or frames around panels. Every panel uses exactly the same art style and the "
              "same characters.")
    prompt = (f"{layout} Art style: {plan.style}. {medium} "
              f"{('Recurring characters, drawn identically everywhere: ' + cast + '.') if cast else ''} "
              f"The first attached image is this book's cover: match its style. "
              f"{'The other attached images are the model sheets of the recurring characters: draw each exactly as on its sheet (face, hair, outfit, colours, proportions, signature detail), in this book art style. ' if sheets > 0 else 'Match the cover characters. '}"
              f"{' '.join(p + '.' for p in panels)} {NO_TEXT}")
    if feedback:
        prompt += f" Fix these problems from the previous attempt: {feedback}"
    return prompt


def slice_sheet(data: bytes, cols: int, rows: int) -> list[bytes]:
    """Cuts at the whitest column/row near the middle (the model rarely centres gutters exactly)."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    grey = im.convert("L")
    xs = [0, *(_gutter(grey, axis=0, at=k / cols) for k in range(1, cols)), im.width]
    ys = [0, *(_gutter(grey, axis=1, at=k / rows) for k in range(1, rows)), im.height]
    panels = []
    for r in range(rows):
        for c in range(cols):
            panels.append(_png(_trim(im.crop((xs[c], ys[r], xs[c + 1], ys[r + 1])))))
    return panels


def _gutter(grey: Image.Image, axis: int, at: float = 0.5) -> int:
    """axis=0: x of the whitest column near `at` (a fraction of the width); axis=1: y of the whitest row.
    The band is ±10 % around the middle (±7 % on denser grids): wider, a pale sky or a calm strip left for the text
    (lighter than the painted gutter) cut a scene through its characters."""
    small = grey.copy()
    small.thumbnail((400, 400))
    w, h = small.size
    length = w if axis == 0 else h
    px = small.load()

    def darkness(i: int) -> int:
        return sum(255 - (px[i, j] if axis == 0 else px[j, i]) for j in range(h if axis == 0 else w))

    band = 0.1 if at == 0.5 else 0.07
    lo, hi = int(length * (at - band)), int(length * (at + band))
    best = min(range(lo, hi), key=lambda i: (darkness(i), abs(i - length * at)))
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
