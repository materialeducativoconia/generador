"""The style library (Phase 9): reference pages in, a layout theme out.

Searcher: the user's own reference files (PDF or images) are sampled into page images.
Curator + Style analyst: one vision call over a numbered contact sheet picks the best-designed pages and
reads their style (app.vision.OpenRouterVision.analyze_style).
Theme maker and style maker: code turns that reading into a Design the template can print — a curated
theme, a heading font, a page frame, a palette fixed for print contrast, and an illustration style.
Only the style is kept; the references' artwork, text and branding never reach a tome.
"""

import io

from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from app.content import Design, StyleSpec
from app.themes import DEFAULT_PALETTE, mix

MAX_PAGES = 8
PAGE_PX = 900  # long side of a sampled page: enough to read layout and type, cheap for the vision model
# heading look -> (curated theme it builds on, heading font)
LOOKS = {"rounded": ("juego", "Fredoka"), "handwritten": ("cuaderno", "Patrick Hand"),
         "serif": ("editorial", "Fraunces"), "geometric": ("ciencia", "Lexend"),
         "script": ("cuaderno", "Pacifico"), "bubbly": ("juego", "Sniglet")}


def sample_pages(data: bytes, media_type: str) -> list[bytes]:
    """Up to eight evenly spread pages (always the first, usually the cover) as JPEGs."""
    if media_type != "application/pdf":
        return [_jpeg(Image.open(io.BytesIO(data)))]
    import pypdfium2 as pdfium  # only the style job needs it

    pdf = pdfium.PdfDocument(data)
    try:
        n = len(pdf)
        picks = sorted({round(i * (n - 1) / (MAX_PAGES - 1)) for i in range(MAX_PAGES)}) if n > 1 else [0]
        pages = []
        for i in picks:
            page = pdf[i]
            scale = PAGE_PX / max(page.get_size())
            pages.append(_jpeg(page.render(scale=scale).to_pil()))
        return pages
    finally:
        pdf.close()


def _jpeg(im: Image.Image) -> bytes:
    im = im.convert("RGB")
    im.thumbnail((PAGE_PX, PAGE_PX))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82)
    return out.getvalue()


def contact_sheet(pages: list[bytes]) -> bytes:
    """All pages on one image, numbered 1..n, so a single vision call can compare and rank them."""
    cols = 4 if len(pages) > 4 else len(pages)
    rows = -(-len(pages) // cols)
    cell_w, cell_h = 460, 600
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=40)
    for i, data in enumerate(pages):
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im.thumbnail((cell_w - 20, cell_h - 20))
        x, y = (i % cols) * cell_w + 10, (i // cols) * cell_h + 10
        sheet.paste(im, (x, y))
        draw.rectangle((x, y, x + 64, y + 54), fill="#111111")
        draw.text((x + 16, y + 4), str(i + 1), fill="white", font=font)
    out = io.BytesIO()
    sheet.save(out, "JPEG", quality=80)
    return out.getvalue()


def _luminance(hex_: str) -> float:
    def ch(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def print_palette(palette: list[str]) -> list[str]:
    """References come in any colours; print needs a near-white page, readable ink and a visible accent."""
    bg, ink, accent = (p.upper() for p in palette)
    while _luminance(bg) < 0.8:
        bg = mix(bg, "#FFFFFF", 0.5)
    while contrast(ink, "#FFFFFF") < 7:
        ink = mix(ink, "#000000", 0.35)
    while contrast(accent, bg) < 2.2:
        accent = mix(accent, "#000000", 0.25)
    return [bg, ink, accent]


def read_spec(raw: dict, pages: int) -> StyleSpec:
    """Vision models get a field wrong now and then; drop only what is invalid instead of the whole reading."""
    data = {k: v for k, v in raw.items() if k in StyleSpec.model_fields}
    data.setdefault("palette", DEFAULT_PALETTE)
    data["best_pages"] = [p for p in data.get("best_pages") or [] if isinstance(p, int) and 1 <= p <= pages][:4]
    for _ in range(len(StyleSpec.model_fields)):
        try:
            return StyleSpec.model_validate(data)
        except ValidationError as exc:
            for err in exc.errors():
                field = err["loc"][0]
                data.pop(field, None)
                if field == "palette":
                    data["palette"] = DEFAULT_PALETTE
    return StyleSpec(palette=DEFAULT_PALETTE)


def theme_from_spec(spec: StyleSpec, *, name: str, style_id: str) -> Design:
    """Theme maker + style maker: the analyst's reading becomes a printable Design."""
    theme, font = LOOKS[spec.heading_look]
    colour = {"bw": "black and white line art with very little colour", "accents": "mostly line art with a few "
              "flat colour accents", "full": "full colour"}[spec.color_use]
    art = ", ".join(filter(None, [spec.illustration_style.strip().rstrip("."), colour]))
    return Design(theme=theme, palette=print_palette(spec.palette), ornament=spec.ornament, head_font=font,
                  frame=spec.frame, art_style=art[:500] or None, style_id=style_id,
                  rationale=f"Estilo de tu biblioteca: «{name}»")
