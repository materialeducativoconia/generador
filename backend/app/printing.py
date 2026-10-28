"""Print geometry and preflight (code, no AI): trim sizes, margins, spine width, and whether pictures are sharp enough.

Sizes are millimetres. KDP figures: 0.125 in bleed, 24-page minimum, spine text from 79 pages,
0.002252 in per page on white paper (black ink) and 0.0025 in per page on colour paper.
"""

import io
import re
from dataclasses import dataclass

from PIL import Image

PAPERS = {"A4": (210.0, 297.0), "Letter": (215.9, 279.4), "8x10": (203.2, 254.0), "6x9": (152.4, 228.6)}
BLEED_MM = 3.175
MIN_PAGES = 24
SPINE_TEXT_PAGES = 79
SHARP_DPI, SOFT_DPI = 300, 200


@dataclass(frozen=True)
class PageGeometry:
    w: float
    h: float
    top: float
    bottom: float
    inner: float  # binding side; equal to outer in the digital edition
    outer: float

    @property
    def content_w(self) -> float:
        return self.w - self.inner - self.outer

    @property
    def content_h(self) -> float:
        return self.h - self.top - self.bottom

    # Picture heights by block size, leaving room for the section header and a caption.
    @property
    def full(self) -> float:
        return round(self.content_h - 78, 1)  # still fits under a section header and a paragraph

    @property
    def half(self) -> float:
        return round(self.content_h * 0.345, 1)

    @property
    def small(self) -> float:
        return round(self.content_h * 0.196, 1)


def page_geometry(paper: str, *, print_edition: bool) -> PageGeometry:
    w, h = PAPERS[paper]
    top, bottom, side = (16, 18, 14) if w < 180 else (20, 22, 18)
    gutter = 4 if print_edition else 0  # bound books lose a few millimetres into the spine
    return PageGeometry(w, h, top, bottom, side + gutter, side)


def spine_mm(pages: int, *, color: bool) -> float:
    return round(pages * (0.0025 if color else 0.002252) * 25.4, 2)


def is_color(tome) -> bool:
    """Colour paper if anything prints in colour; colouring books and text stay on cheaper white paper."""
    kinds = {b.kind for s in tome.sections for b in s.content.blocks if b.type == "image" and b.asset_id}
    return bool(kinds - {"line_art"})


def _pixels(data: bytes, media_type: str) -> tuple[int, int] | None:
    if media_type == "image/svg+xml":
        return None
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def _dpi(px: tuple[int, int], box_w: float, box_h: float, *, fill: bool = False) -> int:
    """Printed resolution of a picture fitted (or, for covers, cropped to fill) into a box in mm."""
    scale = (max if fill else min)(box_w / px[0], box_h / px[1])  # mm per pixel
    return round(25.4 / scale)


def preflight(tome, *, paper: str, print_edition: bool, pages: int, layout: dict | None = None) -> dict:
    geo = page_geometry(paper, print_edition=print_edition)
    issues, dpis, vector = [], [], 0

    def check(what: str, dpi: int):
        dpis.append(dpi)
        if dpi < SHARP_DPI:
            issues.append(f"{what}: {dpi} dpi (se recomiendan {SHARP_DPI})")

    if tome.cover_image:
        px = _pixels(tome.cover_image, tome.cover_media_type)
        bleed = BLEED_MM if print_edition else 0
        if px:
            check("Portada", _dpi(px, geo.w + bleed, geo.h + 2 * bleed, fill=True))
    seen = set()
    for section in tome.sections:
        for b in section.content.blocks:
            if b.type != "image" or b.asset_id not in tome.images or b.asset_id in seen:
                continue
            seen.add(b.asset_id)
            px = _pixels(*tome.images[b.asset_id])
            if px is None:
                vector += 1
                continue
            box_w = geo.content_w if b.size != "small" else geo.content_w * 0.6
            check(_short(b.subject), _dpi(px, box_w, getattr(geo, b.size)))
    if print_edition and pages < MIN_PAGES:
        issues.append(f"KDP pide al menos {MIN_PAGES} páginas; este tomo tiene {pages}")
    layout = layout or {"fixed": [], "issues": []}
    issues += layout["issues"]
    low = min(dpis, default=None)
    rating = "baja" if low is not None and low < SOFT_DPI else ("aceptable" if issues else "lista")
    report = {"rating": rating, "min_dpi": low, "issues": issues, "vector": vector}
    if layout["fixed"] or layout["issues"]:
        report["layout"] = layout
    return report


def _short(subject: str) -> str:
    subject = re.sub(r"\s+", " ", subject).strip()
    return subject[:57] + "…" if len(subject) > 60 else subject
