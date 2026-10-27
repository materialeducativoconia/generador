"""Illustrator helpers: print-ready post-processing and the Curator's matching key (prompts live in app.artwork).

The model paints; everything that decides print quality (pure black lines for colouring pages,
sane file sizes) is deterministic code here.
"""

import io
import re
import unicodedata

from PIL import Image


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
    """Colouring pages become 1-bit black on white (crisp in print, tiny files); colour art a ≤1800 px JPEG."""
    im = Image.open(io.BytesIO(data))
    im.load()
    out = io.BytesIO()
    if kind == "line_art":
        grey = im.convert("L")
        grey.thumbnail((2000, 2000))
        grey.point(lambda v: 255 if v > 170 else 0).convert("1").save(out, "PNG", optimize=True)
        return out.getvalue(), "image/png"
    rgb = im.convert("RGB")
    rgb.thumbnail((1800, 1800))
    rgb.save(out, "JPEG", quality=86, optimize=True)
    return out.getvalue(), "image/jpeg"


def line_art_coverage(data: bytes) -> float:
    """Share of black pixels: ~0 is a blank page, very high means filled shapes, not colourable lines."""
    grey = Image.open(io.BytesIO(data)).convert("L")
    grey.thumbnail((400, 400))
    pixels = list(grey.get_flattened_data())
    return sum(1 for v in pixels if v < 128) / len(pixels)
