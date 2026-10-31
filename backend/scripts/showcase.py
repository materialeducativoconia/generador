"""Paints (once) the landing's carousel of example covers: premium Illustrator art, laid out by the same cover
template the tomes print with, saved as WebP under frontend/public/showcase/.

    OPENROUTER_API_KEY=sk-or-… uv run python scripts/showcase.py

About 8 × $0.09. Existing files are kept: delete one to paint it again.
"""

import asyncio
import io
import os
import sys
from pathlib import Path

import pypdfium2
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.content import Design  # noqa: E402
from app.images import OpenRouterImages  # noqa: E402
from app.render import Tome, render_pdf  # noqa: E402
from app.themes import ART_STYLES, COVER_LAYOUTS  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "frontend/public/showcase"

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


async def main() -> None:
    images = OpenRouterImages(os.environ["OPENROUTER_API_KEY"], os.environ.get("OPENROUTER_IMAGE_MODEL",
                                                                               "google/gemini-nano-banana-2.1"))
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, kicker, title, audience, theme, palette, art, layout, picture in COVERS:
        path = OUT / f"{slug}.webp"
        if path.exists():
            print(f"= {slug}")
            continue
        prompt = (f"Premium children's book cover illustration, award-winning picture book quality (Kalandraka, "
                  f"Flamboyant, SM). {picture}. Style: {ART_STYLES[art][1]}. Vibrant, joyful, rich detail, "
                  f"no text, no letters except those described. {COVER_LAYOUTS[layout][1]}")
        art_image = await images.generate(prompt, aspect_ratio="3:4", resolution="2K")
        design = Design(theme=theme, palette=palette, ornament="ninguno", illustration=art, cover_layout=layout)
        tome = Tome(title=title, genre="worksheets", audience=audience, author=None, sections=[], design=design,
                    cover_image=art_image.data, cover_media_type=art_image.media_type, collection=kicker)
        pdf, _ = render_pdf(tome, paper="A4", include_answer_key=False)
        page = pypdfium2.PdfDocument(pdf)[0].render(scale=1.6).to_pil()
        page.thumbnail((720, 1020), Image.LANCZOS)
        buf = io.BytesIO()
        page.save(buf, "WEBP", quality=82)
        path.write_bytes(buf.getvalue())
        print(f"+ {slug} (${art_image.cost_usd:.3f})")


if __name__ == "__main__":
    asyncio.run(main())
