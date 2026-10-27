import io
import json

import httpx
import pytest
from PIL import Image, ImageDraw

from app.content import Design
from app.illustrator import (ASPECT, illustration_prompt, line_art_coverage, normalize_subject, prepare_image,
                             style_key)
from app.llm import UpstreamError
from app.vision import OpenRouterVision

DESIGN = Design(theme="juego", palette=["#FFF8EC", "#2D2A5A", "#E8762C"], ornament="notas")


def png(draw=None, size=(400, 400), color="white"):
    im = Image.new("RGB", size, color)
    if draw:
        draw(ImageDraw.Draw(im))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def test_subjects_are_normalized_for_matching():
    assert normalize_subject("Una ardilla comiendo bellotas.") == "ardilla comiendo bellotas"
    assert normalize_subject("  El  Árbol de la vida ") == "arbol vida"


def test_line_art_is_style_free_but_colour_art_depends_on_the_design():
    assert style_key("line_art", DESIGN) == style_key("line_art", None) == "line"
    assert style_key("illustration", DESIGN) == "juego:#E8762C"
    assert style_key("illustration", None) == "clasico"


def test_prompts_fit_the_kind_and_forbid_text():
    line = illustration_prompt("line_art", "una ardilla", DESIGN)
    colour = illustration_prompt("illustration", "una ardilla", DESIGN)

    assert "coloring" in line.lower() and "no color" in line.lower() and "una ardilla" in line
    assert "#E8762C" in colour and "rounded" in colour.lower()
    assert all("no text" in p.lower() for p in (line, colour))
    assert ASPECT["full"] == "3:4" and ASPECT["small"] == "1:1"


def test_line_art_becomes_pure_black_and_white():
    grey_sketch = png(lambda d: d.ellipse((100, 100, 300, 300), outline=(90, 90, 90), width=8, fill=(235, 240, 250)))

    data, media_type = prepare_image(grey_sketch, "line_art")

    im = Image.open(io.BytesIO(data))
    assert media_type == "image/png" and set(im.convert("L").get_flattened_data()) <= {0, 255}
    assert 0.01 < line_art_coverage(data) < 0.3


def test_an_empty_page_has_no_line_coverage():
    data, _ = prepare_image(png(), "line_art")

    assert line_art_coverage(data) == 0


def test_colour_art_is_shrunk_to_a_printable_jpeg():
    data, media_type = prepare_image(png(size=(3000, 4000), color=(200, 120, 40)), "illustration")

    im = Image.open(io.BytesIO(data))
    assert media_type == "image/jpeg" and max(im.size) <= 1800


async def test_vision_review_parses_the_verdict():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        verdict = {"ok": False, "has_text": True, "matches_subject": True, "issues": "hay letras"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(verdict)}}],
                                         "usage": {"cost": 0.0001}})

    vision = OpenRouterVision("k", "qwen/qwen3.7-flash", transport=httpx.MockTransport(handler))
    review = await vision.review(png(), kind="line_art", subject="una ardilla")

    assert review.ok is False and review.has_text and review.issues == "hay letras"
    content = seen["messages"][-1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_vision_review_maps_errors():
    vision = OpenRouterVision("k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(503)))

    with pytest.raises(UpstreamError):
        await vision.review(png(), kind="line_art", subject="x")


async def test_vision_review_reads_a_verdict_wrapped_in_prose_or_fences():
    reply = 'Claro:\n```json\n{"ok": true, "has_text": false, "matches_subject": true, "issues": ""}\n```'
    vision = OpenRouterVision("k", "m", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})))

    review = await vision.review(png(), kind="illustration", subject="x")

    assert review.ok is True
