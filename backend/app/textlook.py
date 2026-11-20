"""How a text sits on a bleed plate: on the art itself or on a card.

Picture books from the big publishers (Usborne, DK, Kingfisher, SM, Combel) set their words straight on the
painting wherever the illustrator left a quiet, even patch (sky, a wall, the floor) and the ink reads at a glance;
a card or a tinted panel appears only where the picture is busy or mid-toned. This module makes that call the
same way for every text, by measuring the patch under it: the worst-case contrast against the ink (WCAG: 4.5:1
for body text, 3:1 for a big heading) and how much detail lies behind the letters. No AI, the same answer on
every render.

Between the two lies the veil, as Larousse and DK do over a moderately busy sky or meadow: the words stay on the
art over a soft wash of paper (or of shade, under white words) that fades into the picture with no edge. It is a
feathered PNG made to the text's size, since WeasyPrint draws neither text-shadow, box-shadow nor blur.
"""

import base64
import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

CARD, OPEN, LIGHT = "", "open", "open light"  # css classes: the white card, dark ink on the art, white ink on it
VEIL, DARK_VEIL = "veil", "veil dark"  # dark ink over a paper wash, white ink over a shade wash
WHITE = "#ffffff"
DETAIL = 9.0  # mean edge strength (0-255) above which a patch is too busy to read letters over it
SPREAD = 34.0  # standard deviation of the patch's luminance (0-255) above which its tone is too uneven
BUSY = 30.0  # mean edge strength above which even a veil loses the words in the drawing: the card
DIM = 105  # the patch's mean grey below which the veil is a shade under white words
FEATHER = 6.0  # mm: how far a veil reaches past its text's box, fading out


def _channel(v: float) -> float:
    v /= 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


@lru_cache(maxsize=32)
def _picture(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data)).convert("L")
    im.thumbnail((600, 600))
    return im


def patch_look(data: bytes, box: tuple[float, float, float, float], page: tuple[float, float], ink: str,
               large: bool = False) -> str:
    """box: the text's area as fractions of the page (left, top, right, bottom); page: its width and height. The
    picture fills the page like `object-fit: cover`, so the box is mapped onto the visible, centred crop."""
    im = _picture(data)
    w, h = im.size
    page_ratio, ratio = page[0] / page[1], w / h
    vis_w, vis_h = (h * page_ratio, h) if ratio > page_ratio else (w, w / page_ratio)
    x0, y0 = (w - vis_w) / 2, (h - vis_h) / 2
    left, top, right, bottom = (max(0.0, min(1.0, v)) for v in box)
    crop = im.crop((round(x0 + left * vis_w), round(y0 + top * vis_h),
                    round(x0 + right * vis_w), round(y0 + bottom * vis_h)))
    if crop.width < 4 or crop.height < 4:
        return CARD
    pixels = sorted(crop.get_flattened_data())
    n = len(pixels)
    mean = sum(pixels) / n
    spread = (sum((p - mean) ** 2 for p in pixels) / n) ** 0.5
    edges = crop.filter(ImageFilter.FIND_EDGES).crop((1, 1, crop.width - 1, crop.height - 1))
    detail = sum(edges.get_flattened_data()) / max(1, (crop.width - 2) * (crop.height - 2))
    if detail <= DETAIL and spread <= SPREAD:
        need = 3.0 if large else 4.5
        grey = lambda v: luminance(f"#{v:02x}{v:02x}{v:02x}")  # noqa: E731
        darkest, lightest = grey(pixels[n // 20]), grey(pixels[n - 1 - n // 20])  # the worst 5 % of the patch
        if contrast(luminance(ink), darkest) >= need:
            return OPEN
        if contrast(luminance(WHITE), lightest) >= need:
            return LIGHT
    if detail > BUSY:
        return CARD
    return DARK_VEIL if mean < DIM else VEIL


@lru_cache(maxsize=256)
def veil_uri(w_mm: int, h_mm: int, dark: bool, px: float = 3.0) -> str:
    """A wash the size of a text's box plus FEATHER on every side, opaque enough behind the words (a 4.5:1 ink on
    any picture) and fading to nothing at its edge; stretched over that area by the template."""
    f = FEATHER * px
    w, h = round(w_mm * px + 2 * f), round(h_mm * px + 2 * f)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((f * .7, f * .7, w - f * .7, h - f * .7), radius=2 * f,
                                           fill=round(255 * (.6 if dark else .82)))
    mask = mask.filter(ImageFilter.GaussianBlur(f * .4))
    wash = Image.new("RGBA", (w, h), (24, 20, 16, 0) if dark else (255, 252, 246, 0))
    wash.putalpha(mask)
    out = io.BytesIO()
    wash.save(out, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def plate_looks(block, data: bytes | None, page: tuple[float, float], ink: str, low: bool,
                spots: dict[str, tuple[float, float, float, float]]) -> dict[str, str]:
    """The look of each text of a bleed plate: "q" the question (or story) card, "f" the find strip, "n0".."n3" the
    facts laid over the picture (spots: fact index key -> its box). Without a picture, or over an inset diagram,
    everything keeps its card."""
    if not data or getattr(block, "inset", None):
        return {}
    w, h = page
    place = getattr(block, "place", None) or {}
    words = len((block.narration or "").split()) + len((block.answer or "").split())
    q_h = min(0.42, (24 + words * 0.9 + (12 if block.narration else 0)) / h)  # its height grows with its words
    if "q" in place:
        q_top = place["q"].y / 100
    elif low:
        q_top = 1 - (27 if block.find else 9) / h - q_h
    else:
        q_top = 9 / h
    side = 9 / w
    boxes = {"q": (side, q_top, 1 - side, q_top + q_h)}
    looks = {"q": patch_look(data, boxes["q"], page, ink, large=not words)}
    if block.find:
        f_top = place["f"].y / 100 if "f" in place else 1 - 21 / h
        boxes["f"] = (side, f_top, 1 - side, f_top + 12 / h)
        looks["f"] = patch_look(data, boxes["f"], page, ink)
    for key, box in spots.items():
        boxes[key] = box
        looks[key] = patch_look(data, box, page, ink)
    for key, look in list(looks.items()):  # "qv", "fv", "n0v"..: the wash each veiled text lies on
        if look in (VEIL, DARK_VEIL):
            left, top, right, bottom = boxes[key]
            looks[key + "v"] = veil_uri(round((right - left) * w), round((bottom - top) * h), look == DARK_VEIL)
    return looks
