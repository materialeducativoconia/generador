"""Illustrator helpers: print-ready post-processing and the Curator's matching key (prompts live in app.artwork).

The model paints; everything that decides print quality (pure black lines for colouring pages,
sane file sizes) is deterministic code here.
"""

import io
import re
import shutil
import subprocess
import unicodedata

from PIL import Image, ImageFilter, ImageOps


ASPECT = {"plate": "3:4", "full": "3:4", "half": "4:3", "small": "1:1", "icon": "1:1"}
STOPWORDS = {"un", "una", "unos", "unas", "el", "la", "los", "las", "lo", "de", "del", "al", "a", "y", "e", "o",
             "en", "con", "para", "por", "su", "sus"}
THEME_STYLE = {
    "juego": "rounded, friendly flat vector shapes, bold and cheerful",
    "cuaderno": "hand-drawn crayon and colored pencil texture, like a school notebook doodle",
    "editorial": "elegant gouache painting, soft textures, refined",
    "metodo": "clean flat vector, clear and instructive",
    "ciencia": "clean flat vector, precise, infographic feel",
    "clasico": "clean flat vector",
}
NO_TEXT = "No text, no letters, no numbers, no labels, no watermark, no signature."


def normalize_subject(subject: str) -> str:
    plain = unicodedata.normalize("NFKD", subject.lower()).encode("ascii", "ignore").decode()
    return " ".join(w for w in re.findall(r"[a-z0-9]+", plain) if w not in STOPWORDS)


def prepare_image(data: bytes, kind: str) -> tuple[bytes, str]:
    """Colouring pages become 1-bit black on white (crisp in print, tiny files); colour art a ≤3200 px JPEG."""
    im = Image.open(io.BytesIO(data))
    im.load()
    out = io.BytesIO()
    if kind in ("line_art", "icon"):
        grey = im.convert("L")
        grey.thumbnail((2000, 2000))
        # A low threshold keeps light greys and shading white: they are not lines to colour inside.
        grey.point(lambda v: 255 if v > 110 else 0).convert("1").save(out, "PNG", optimize=True)
        return out.getvalue(), "image/png"
    rgb = im.convert("RGB")
    rgb.thumbnail((3200, 3200))  # 4K sheets give ~1500x2000 panels: 300 dpi at half a page
    rgb.save(out, "JPEG", quality=86, optimize=True)
    return out.getvalue(), "image/jpeg"


def upscale(data: bytes, long_side: int = 3000) -> tuple[bytes, str]:
    """A preview's 1K picture brought to print size when the tome is bought: Lanczos and a light unsharp mask, free
    and local (a picture already that big is only re-encoded)."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    scale = long_side / max(im.size)
    if scale > 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue(), "image/jpeg"


INK_SAVER = 0.55  # share of the original ink kept: shadows print as dark grey, never as solid black


def ink_saver(data: bytes) -> tuple[bytes, str]:
    """A picture for the black-and-white edition, made locally (no AI): grey, its contrast stretched, then every tone
    lifted toward white so a home printer spends about half the toner; transparency becomes paper white."""
    im = Image.open(io.BytesIO(data))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        paper = Image.new("RGBA", im.size, "white")
        im = Image.alpha_composite(paper, im)
    grey = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    grey = grey.point(lambda v: 255 - round((255 - v) * INK_SAVER))
    out = io.BytesIO()
    grey.save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue(), "image/jpeg"


def line_art_coverage(data: bytes) -> float:
    """Share of black pixels: ~0 is a blank page, very high means filled shapes, not colourable lines."""
    grey = Image.open(io.BytesIO(data)).convert("L")
    grey.thumbnail((400, 400))
    pixels = list(grey.get_flattened_data())
    return sum(1 for v in pixels if v < 128) / len(pixels)


def vectorize(png: bytes) -> bytes | None:
    """A colouring page traced into vector outlines: sharp at any print size, a few KB. None without potrace."""
    exe = shutil.which("potrace")
    if exe is None:
        return None
    grey = Image.open(io.BytesIO(png)).convert("L")
    w, h = grey.size
    # Doubling and a slight blur before the threshold turn the staircase of a 1-bit panel into smooth curves.
    big = grey.resize((w * 2, h * 2), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(1.6))
    bitmap = big.point(lambda v: 255 if v > 128 else 0).convert("1")
    pbm = io.BytesIO()
    bitmap.save(pbm, "PPM")
    try:
        run = subprocess.run([exe, "--svg", "--flat", "--turdsize", "8", "--alphamax", "1.2", "--opttolerance", "0.4", "--output", "-", "-"], input=pbm.getvalue(),
                             capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None
    if run.returncode != 0 or b"<svg" not in run.stdout:
        return None
    # potrace sizes the drawing in points; WeasyPrint wants pixels, the size of the original panel.
    return re.sub(rb'width="[\d.]+pt" height="[\d.]+pt"', f'width="{w}px" height="{h}px"'.encode(), run.stdout,
                  count=1)


def reference_image(data: bytes, side: int = 1024) -> bytes:
    """A small JPEG of the cover to anchor the style: a 4K upload would only slow the request down."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((side, side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


def cover_jpeg(data: bytes) -> bytes:
    """Covers are painted at 4K; a high-quality JPEG keeps them sharp and well under the bucket's size limit."""
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue()
