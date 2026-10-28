"""Illustrator helpers: print-ready post-processing and the Curator's matching key (prompts live in app.artwork).

The model paints; everything that decides print quality (pure black lines for colouring pages,
sane file sizes) is deterministic code here.
"""

import io
import re
import shutil
import subprocess
import unicodedata

from PIL import Image, ImageFilter


ASPECT = {"full": "3:4", "half": "4:3", "small": "1:1"}
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
    if kind == "line_art":
        grey = im.convert("L")
        grey.thumbnail((2000, 2000))
        grey.point(lambda v: 255 if v > 170 else 0).convert("1").save(out, "PNG", optimize=True)
        return out.getvalue(), "image/png"
    rgb = im.convert("RGB")
    rgb.thumbnail((3200, 3200))  # 4K sheets give ~1500x2000 panels: 300 dpi at half a page
    rgb.save(out, "JPEG", quality=86, optimize=True)
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
