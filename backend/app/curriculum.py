"""Program searcher: official curricula, syllabi and proven teaching methods from the web, with their links.

A search model on OpenRouter (Perplexity Sonar by default) reads the web and answers with citations; the
Program sheet agent (app.agents.program_sheet) then turns the findings into the reference syllabus the
Architect follows, so a tome is built on official, tried programs instead of the model's imagination.
Like the rest of the research, it is best effort, and the fetched text is data, never instructions.
"""

from dataclasses import dataclass, field

import httpx

from app.llm import UpstreamAuthError, UpstreamError

SEARCH_PROMPT = """Busca en la web programas educativos oficiales (ministerios o secretarías de educación, por
ejemplo la SEP de México), planes y programas de estudio, temarios y métodos didácticos probados para:
{query}
Idioma del material: {language}. Resume en viñetas, citando cada fuente: qué contenidos se enseñan, en qué orden,
para qué grado o edad, los aprendizajes esperados y los pasos del método. Prefiere documentos oficiales y
editoriales educativas reconocidas. No inventes nada que no esté en las fuentes."""


FACTS_PROMPT = """Busca datos verificados sobre: {query}
Idioma del material: {language}. Usa solo fuentes publicadas y confiables: libros publicados (Google Books,
editoriales), enciclopedias (Britannica, Larousse), museos, universidades, institutos científicos, organismos
oficiales y editoriales educativas reconocidas. NO uses Wikipedia, Wikimedia, foros, blogs, redes sociales ni
sitios de tareas. Responde en viñetas cortas, un dato por viñeta, cada una con su cita [n] al final. No inventes
nada que no esté en las fuentes."""
UNRELIABLE = ("wikipedia.org", "wikimedia.org", "wikiwand.com", "fandom.com", "brainly.", "quora.com", "reddit.com",
              "youtube.com", "facebook.com", "tiktok.com", "instagram.com", "pinterest.")


def reliable(url: str) -> bool:
    """A source a printed book may cite: not an open wiki, a forum, a homework site or a social network."""
    return not any(domain in url.lower() for domain in UNRELIABLE)


@dataclass
class Finding:
    query: str
    text: str
    sources: list[dict] = field(default_factory=list)  # {title, url}
    cost_usd: float | None = None


class ProgramSearch:
    def __init__(self, api_key: str, model: str, *, timeout: float = 90,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key, self.model, self.timeout, self.transport = api_key, model, timeout, transport

    async def search(self, query: str, *, language: str = "es") -> Finding:
        return await self._ask(query, SEARCH_PROMPT.format(query=query, language=language))

    async def facts(self, query: str, *, language: str = "es") -> Finding:
        """The Researcher's facts from published sources, each bullet citing the one it came from."""
        return await self._ask(query, FACTS_PROMPT.format(query=query, language=language))

    async def _ask(self, query: str, prompt: str) -> Finding:
        body = {"model": self.model, "temperature": 0.1, "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}]}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http:
                response = await http.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                                           headers={"Authorization": f"Bearer {self.api_key}",
                                                    "X-Title": "Jelyx Docs"})
        except httpx.HTTPError as exc:
            raise UpstreamError("upstream_unavailable", "No se pudo conectar con el buscador.") from exc
        if response.status_code in (401, 402, 403):
            raise UpstreamAuthError(f"OpenRouter {response.status_code}")
        if response.status_code >= 400:
            raise UpstreamError("upstream_unavailable", f"El buscador respondió {response.status_code}.")
        payload = response.json()
        message = ((payload.get("choices") or [{}])[0]).get("message") or {}
        return Finding(query=query, text=str(message.get("content") or "")[:6000], sources=_sources(payload, message),
                       cost_usd=(payload.get("usage") or {}).get("cost"))


def _sources(payload: dict, message: dict) -> list[dict]:
    """OpenRouter's url_citation annotations, or the bare `citations` list some search models return."""
    out: dict[str, str] = {}
    for a in message.get("annotations") or []:
        cite = a.get("url_citation") or {}
        if a.get("type") == "url_citation" and str(cite.get("url", "")).startswith("http"):
            out.setdefault(cite["url"], (cite.get("title") or cite["url"])[:200])
    for url in payload.get("citations") or []:
        if isinstance(url, str) and url.startswith("http"):
            out.setdefault(url, url)
    return [{"title": t, "url": u} for u, t in list(out.items())[:10]]
