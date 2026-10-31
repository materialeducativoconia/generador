"""The landing's carousel of example covers: painted once by the worker (which holds the premium Illustrator's
key) with the same cover template the tomes print with, kept in the public `covers` bucket under showcase/.
Each start of the worker paints only the ones missing: about 8 × $0.09 the first time, nothing after."""

import asyncio
import io
import logging

import httpx
import pypdfium2
from PIL import Image

from app.content import Design
from app.render import Tome, render_pdf
from app.themes import ART_STYLES, COVER_LAYOUTS

log = logging.getLogger("showcase")

# slug, kicker, title, audience, theme, palette, illustration, layout, picture
COVERS = [
    ("colorear-dinosaurios", "Libro para colorear", "Dinosaurios para colorear", "Preescolar (3–5 años)", "juego",
     ["#FFF7E8", "#1E2B3A", "#2FA35A"], "crayon", "plate",
     "a friendly baby triceratops and a smiling long-neck dinosaur among ferns and a volcano, bright jungle colors"),
    ("escritura-letras", "Cuaderno de escritura", "Mis primeras letras", "Primaria baja (6–8)", "cuaderno",
     ["#F3F8FF", "#1D2A4D", "#2F6FE4"], "recorte", "band",
     "a happy child pencil character riding giant colorful alphabet letters A, M, S like a playground"),
    ("matematicas-sumas", "Matemáticas", "Sumo y cuento hasta 20", "Primaria baja (6–8)", "juego",
     ["#FFF5F0", "#2A1E3A", "#E8553D"], "gouache", "framed",
     "cute ladybugs and bees counting flowers and apples in a sunny garden, numbers drawn as hidden shapes"),
    ("ciencias-espacio", "Ciencias", "Viaje al sistema solar", "Primaria alta (9–12)", "metodo",
     ["#F2F0FF", "#16163A", "#5B3FD9"], "gouache", "plate",
     "a kid astronaut floating near colorful planets, Saturn's rings and a friendly rocket, starry deep blue sky"),
    ("colorear-oceano", "Libro para colorear", "Animales del océano", "Preescolar (3–5 años)", "juego",
     ["#EEFAFB", "#13324A", "#0E9AA7"], "acuarela", "band",
     "a smiling whale, a turtle, an octopus and little fish among coral and bubbles, turquoise sea"),
    ("lectura-cuentos", "Comprensión lectora", "Leo y comprendo", "Primaria alta (9–12)", "cuaderno",
     ["#FFF9EC", "#2B2118", "#D9822B"], "acuarela", "framed",
     "two kids reading inside a giant open book that becomes a forest with a fox, an owl and a winding path"),
    ("musica-ritmo", "Método paso a paso", "Mi primer piano", "Primaria baja (6–8)", "metodo",
     ["#FFF4F8", "#2A1830", "#D23C7A"], "plastilina", "plate",
     "a cheerful clay piano with dancing music notes, a cat and a bird singing, playful studio lighting"),
    ("granja-vocales", "Lectoescritura", "Las vocales de la granja", "Preescolar (3–5 años)", "juego",
     ["#F6FBEF", "#1F2D17", "#5FA82E"], "recorte", "framed",
     "farm animals (cow, hen, pig, sheep) peeking from a red barn decorated with big letters A E I O U"),
]


RETRY_SECONDS = 1800  # a refused or rate-limited cover is tried again half an hour later
PAUSE_SECONDS = 75  # between covers and between tries: the image API refuses requests that come too close


async def keep_painted(images, storage) -> None:
    """The worker's background task: paints what is missing, again every half hour until nothing is."""
    while await paint_missing(images, storage) is not None:
        await asyncio.sleep(RETRY_SECONDS)


async def paint_missing(images, storage, pause: float = PAUSE_SECONDS) -> int | None:
    """Paints the covers not yet in storage; returns how many it painted, or None when none is missing."""
    painted, missing = 0, 0
    for slug, kicker, title, audience, theme, palette, art, layout, picture in COVERS:
        key = f"showcase/{slug}.webp"
        if await _exists(storage.public_url(key)):
            continue
        if missing:
            await asyncio.sleep(pause)
        missing += 1
        prompt = (f"Premium children's book cover illustration, award-winning picture book quality (Kalandraka, "
                  f"Flamboyant, SM). {picture}. Style: {ART_STYLES[art][1]}. Vibrant, joyful, rich detail, "
                  f"no text, no letters except those described. {COVER_LAYOUTS[layout][1]}")
        try:
            art_image = await _generate(images, prompt, pause)
            design = Design(theme=theme, palette=palette, ornament="ninguno", illustration=art, cover_layout=layout)
            tome = Tome(title=title, genre="worksheets", audience=audience, author=None, sections=[], design=design,
                        cover_image=art_image.data, cover_media_type=art_image.media_type, collection=kicker)
            await storage.upload(key, await asyncio.to_thread(_webp, tome), "image/webp", bucket="covers")
        except Exception:  # noqa: BLE001  the carousel waits for the next start
            log.exception("showcase cover %s failed", slug)
            continue
        painted += 1
        log.info("showcase cover %s painted ($%.3f)", slug, art_image.cost_usd)
    return painted if missing else None


async def _generate(images, prompt: str, pause: float, tries: int = 3):
    for attempt in range(tries):
        try:
            return await images.generate(prompt, aspect_ratio="3:4", resolution="2K")
        except Exception as exc:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            log.warning("showcase cover try %s failed: %s", attempt + 1, exc)
            await asyncio.sleep(pause * (attempt + 1))


def _webp(tome: Tome) -> bytes:
    pdf, _ = render_pdf(tome, paper="A4", include_answer_key=False)
    page = pypdfium2.PdfDocument(pdf)[0].render(scale=1.6).to_pil()
    page.thumbnail((720, 1020), Image.LANCZOS)
    buf = io.BytesIO()
    page.save(buf, "WEBP", quality=82)
    return buf.getvalue()


async def _exists(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            return (await http.head(url)).status_code == 200
    except httpx.HTTPError:
        return True  # storage unreachable: don't pay for a cover we may already have
