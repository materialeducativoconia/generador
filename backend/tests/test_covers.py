import base64
import io
import json

import httpx
import pytest
from pypdf import PdfReader

from app.agents import Brief, cover_director
from app.images import OpenRouterImages
from app.llm import UpstreamAuthError, UpstreamError
from app.references import find_covers
from app.render import Tome, render_html, render_pdf
from tests.fakes import ScriptedLLM

# Smallest valid PNG (1x1 transparent) so WeasyPrint and the pipeline see a real image.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

PLAN = {"concept": "Un niño feliz frente a un piano de juguete", "search_queries": ["piano for kids", "método piano"],
        "illustration_prompt": "A cheerful child at a toy piano, flat vector style", "palette": ["#FFF4E0", "#1E3A5F", "#F2994A"]}


async def test_cover_director_returns_a_validated_plan():
    llm = ScriptedLLM(json.dumps(PLAN))

    result = await cover_director(llm, Brief(request="piano para niños", audience="Preescolar"), "Mi primer piano",
                                  "tutorial", ["Postura", "El Do central"])

    assert result.value.palette == ["#FFF4E0", "#1E3A5F", "#F2994A"]
    assert "Mi primer piano" in llm.calls[0][1]["content"]


async def test_cover_director_rejects_a_bad_palette_then_repairs():
    bad = {**PLAN, "palette": ["naranja"]}
    llm = ScriptedLLM(json.dumps(bad), json.dumps(PLAN))

    result = await cover_director(llm, Brief(request="x", audience="y"), "T", "tutorial", [])

    assert result.attempts[0].outcome == "invalid_output" and result.value.concept == PLAN["concept"]


async def test_find_covers_keeps_books_with_covers_and_downloads_them():
    seen = []

    def handler(request: httpx.Request):
        seen.append(str(request.url))
        if request.url.host == "openlibrary.org":
            return httpx.Response(200, json={"docs": [
                {"title": "Piano for Kids", "cover_i": 11, "key": "/works/OL1W"},
                {"title": "Sin portada", "key": "/works/OL2W"},
                {"title": "Piano Adventures", "cover_i": 22, "key": "/works/OL3W"},
            ]})
        if "/b/id/22-" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/jpeg"})

    refs = await find_covers(["piano for kids"], limit=3, transport=httpx.MockTransport(handler))

    assert [r.title for r in refs] == ["Piano for Kids"]
    assert refs[0].data == PNG and refs[0].source_url == "https://openlibrary.org/works/OL1W"


async def test_find_covers_skips_unrelated_books_and_cover_words():
    asked = []

    def handler(request: httpx.Request):
        if request.url.host == "openlibrary.org":
            asked.append(request.url.params["q"])
            return httpx.Response(200, json={"docs": [
                {"title": "American Film", "cover_i": 1, "key": "/works/A"},
                {"title": "My First Piano Adventure", "cover_i": 2, "key": "/works/B"},
            ]})
        return httpx.Response(200, content=PNG)

    refs = await find_covers(["preschool piano method book cover"], transport=httpx.MockTransport(handler))

    assert [r.title for r in refs] == ["My First Piano Adventure"]
    assert asked == ["preschool piano method"]


async def test_find_covers_retries_a_flaky_connection():
    calls = []

    def handler(request: httpx.Request):
        if request.url.host == "openlibrary.org":
            calls.append(1)
            if len(calls) == 1:
                raise httpx.ConnectError("reset")
            return httpx.Response(200, json={"docs": [{"title": "Piano for Kids", "cover_i": 1, "key": "/works/A"}]})
        return httpx.Response(200, content=PNG)

    refs = await find_covers(["piano for kids"], transport=httpx.MockTransport(handler))

    assert [r.title for r in refs] == ["Piano for Kids"] and len(calls) == 2


async def test_find_covers_is_best_effort_when_the_site_is_down():
    refs = await find_covers(["x"], transport=httpx.MockTransport(lambda r: httpx.Response(503)))

    assert refs == []


async def test_image_client_sends_references_and_decodes_the_image():
    sent = {}

    def handler(request: httpx.Request):
        sent.update(json.loads(request.content))
        sent["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode(), "media_type": "image/png"}],
                                         "usage": {"cost": 0.04}})

    images = OpenRouterImages("sk-or-test", "google/gemini-nano-banana-2.1", transport=httpx.MockTransport(handler))
    result = await images.generate("a cover", references=[PNG], aspect_ratio="3:4")

    assert result.data == PNG and result.media_type == "image/png" and result.cost_usd == 0.04
    assert sent["aspect_ratio"] == "3:4" and sent["model"] == "google/gemini-nano-banana-2.1"
    assert sent["input_references"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert sent["auth"] == "Bearer sk-or-test"


@pytest.mark.parametrize(("status", "error"), [(429, UpstreamError), (502, UpstreamError), (402, UpstreamAuthError),
                                               (401, UpstreamAuthError)])
async def test_image_client_maps_http_errors(status, error):
    images = OpenRouterImages("k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(status, json={})))

    with pytest.raises(error):
        await images.generate("a cover")


def test_cover_image_and_palette_go_on_the_pdf_cover():
    t = Tome(title="Mi primer piano", genre="tutorial", audience="Preescolar", author=None, sections=[],
             cover_image=PNG, cover_media_type="image/png", palette=["#FFF4E0", "#1E3A5F", "#F2994A"])

    html = render_html(t, paper="A4", include_answer_key=False)
    pdf, pages = render_pdf(t, paper="A4", include_answer_key=False)

    assert 'class="cover-art"' in html and "data:image/png;base64," in html and "#1E3A5F" in html
    assert pages == 1
    assert PdfReader(io.BytesIO(pdf)).pages[0].images
