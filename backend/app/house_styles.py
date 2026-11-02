"""House styles: illustration styles inspired by premium educational publishers, so a tome looks made by an
illustrator, not by a model's default glossy look.

Each style is a bible (medium, line, palette, texture, composition, what to avoid) written as traits, never as a
publisher's, artist's or brand's name. The lab paints one subject in every style; the samples the team keeps become
the style's reference images. `finish` adds what a printed page has and a render lacks (paper grain, a limited
palette), locally and free.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageFilter

from app.illustrator import NO_TEXT

NOT_AI = ("Hand-made look: visible brush or pencil marks, slightly irregular edges, flat lighting, no glossy 3D "
          "render, no airbrushed gradients, no lens blur or bokeh, no glow, no plastic skin, no hyper-detail, "
          "no perfect symmetry.")


@dataclass(frozen=True)
class HouseStyle:
    key: str
    name: str
    inspired_by: str  # for the team only, never sent to the image model
    prompt: str
    grain: float  # paper grain strength, 0..1
    colors: int  # palette size after finishing; 0 keeps the painting's colours


STYLES = [
    HouseStyle("enciclopedia", "Enciclopedia", "Larousse, DK",
               "Naturalist watercolour illustration for a children's encyclopedia: accurate anatomy and proportions, "
               "delicate pencil underdrawing, transparent washes, subjects as vignettes on a clean white page with "
               "soft cast shadows, no background scenery, plenty of white space around each subject.",
               grain=0.25, colors=0),
    HouseStyle("acuarela", "Acuarela y tinta", "Usborne, Combel",
               "Loose ink line and watercolour wash children's book illustration: lively uneven pen lines, washes "
               "that bleed past the lines, warm paper white showing through, simple light background, airy "
               "composition with calm empty areas.",
               grain=0.35, colors=0),
    HouseStyle("gouache", "Gouache moderno", "Flying Eye, Nobrow, Big Picture Press",
               "Mid-century modern gouache illustration: bold flat shapes, a limited palette of five inks, "
               "risograph print texture with slight misregistration, stylised geometric forms, strong graphic "
               "silhouettes, large flat colour fields.",
               grain=0.5, colors=8),
    HouseStyle("collage", "Collage de papel", "classic preschool picture books",
               "Cut-paper collage illustration: shapes cut from hand-painted tissue paper with visible brush "
               "streaks and torn edges, layered paper pieces, bold simple forms, white background.",
               grain=0.3, colors=0),
    HouseStyle("crayon", "Lápiz y crayón", "school notebook picture books",
               "Coloured pencil and wax crayon illustration on textured paper: visible strokes and paper tooth, "
               "warm childlike charm with confident drawing, soft hatching for shading, light background.",
               grain=0.45, colors=0),
    HouseStyle("didactico", "Didáctico claro", "SM, Santillana textbooks",
               "Clean educational textbook illustration: clear dark outlines of even weight, flat colours with "
               "one soft shadow tone, friendly rounded characters, uncluttered simple background, every element "
               "easy to identify.",
               grain=0.12, colors=0),
]
BY_KEY = {s.key: s for s in STYLES}
FREE_STYLES = ("didactico", "acuarela")  # the ones a visitor's preview can use; plans get them all


def apply(design, key: str):
    """The tome's Design wearing a house style: its prompt replaces the Designer's illustration style."""
    style = BY_KEY[key]
    return design.model_copy(update={"house_style": key, "art_style": f"{style.prompt} {NOT_AI}",
                                     "illustration": None})


async def style_references(engine, storage, key: str | None) -> list[bytes]:
    """The sample the team kept for this style (or its latest one), small, to anchor technique and texture."""
    if not key or storage is None:
        return []
    from sqlalchemy import text

    from app.illustrator import reference_image

    async with engine.connect() as conn:
        found = (await conn.execute(text(
            """select key from public.style_samples where style = :st and status = 'done' and key is not null
                order by chosen desc, created_at desc limit 1"""), {"st": key})).scalar_one_or_none()
    if not found:
        return []
    try:
        return [reference_image(await storage.download(found, bucket="images"))]
    except Exception:  # a reference helps; painting goes on without it
        return []


STYLE_NOTE = ("The attached style reference shows the art style to match exactly: its technique, line, texture and "
              "colour treatment, never its subject or composition.")


def style_prompt(style: HouseStyle, subject: str, *, sheets: int = 0) -> str:
    cast = ("The attached images are model sheets of the recurring characters: keep each one's face, hair, outfit, "
            "colours and signature detail, redrawn in this art style. " if sheets else "")
    return (f"A full-page illustration for a premium children's knowledge book. Art style: {style.prompt} {NOT_AI} "
            f"{cast}Leave the top quarter calm and simple for a title. Scene: {subject}. {NO_TEXT}")


def finish(data: bytes, style: HouseStyle, quality: int = 88) -> bytes:
    """Paper grain and, for print-styled looks, a reduced palette: a local, free step after the painting."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if style.colors:
        im = im.quantize(colors=style.colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    if style.grain:
        small = Image.effect_noise((max(1, im.width // 2), max(1, im.height // 2)), 64)
        noise = small.resize(im.size, Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(0.6))
        # Grain only darkens, like ink sitting in the paper's tooth: 255 is no change, lower values add texture.
        depth = round(60 * style.grain)
        noise = noise.point(lambda v: 255 - round(v * depth / 255))
        im = ImageChops.multiply(im, Image.merge("RGB", (noise, noise, noise)))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True)
    return out.getvalue()
