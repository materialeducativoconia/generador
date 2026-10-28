"""The Program searcher reads official programs on the web and keeps the links it used."""

import json

import httpx

from app.curriculum import ProgramSearch


def search_transport(payload):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler), seen


async def test_findings_keep_the_cited_links():
    transport, seen = search_transport({
        "choices": [{"message": {"content": "- Fase 3: lectura y escritura inicial [1]", "annotations": [
            {"type": "url_citation", "url_citation": {"url": "https://www.gob.mx/sep/programa-fase-3.pdf",
                                                     "title": "Programa sintético Fase 3"}}]}}],
        "citations": ["https://www.gob.mx/sep/programa-fase-3.pdf", "https://example.org/metodo-20-dias"],
        "usage": {"cost": 0.006}})

    found = await ProgramSearch("k", "perplexity/sonar", transport=transport).search("lectoescritura primer grado")

    assert seen[0]["model"] == "perplexity/sonar" and "lectoescritura primer grado" in seen[0]["messages"][0]["content"]
    assert found.sources == [{"title": "Programa sintético Fase 3", "url": "https://www.gob.mx/sep/programa-fase-3.pdf"},
                             {"title": "https://example.org/metodo-20-dias", "url": "https://example.org/metodo-20-dias"}]
    assert "Fase 3" in found.text and found.cost_usd == 0.006
