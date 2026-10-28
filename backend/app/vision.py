"""The image Reviewer: a cheap vision model on OpenRouter checks each generated picture."""

import base64
import json
from dataclasses import dataclass

import httpx

from app.images import _sniff
from app.llm import UpstreamAuthError, UpstreamError

REVIEW_PROMPT = """Revisa esta imagen para un libro educativo impreso.
Tipo pedido: {kind}. Tema pedido: {subject}.
Responde solo con json: {{"ok": true|false, "has_text": true|false, "matches_subject": true|false,
"issues": "problemas concretos en una frase, o vacío"}}
ok es false si aparece texto o letras, si no muestra el tema pedido, si es inapropiada para niños, o si
{extra}"""
EXTRA = {
    "line_art": "no es un dibujo de líneas negras sobre blanco apto para colorear (sin relleno ni sombras).",
    "icon": "no es un dibujo simple de líneas negras sobre blanco de un solo objeto reconocible.",
    "illustration": "está deformada o es confusa.",
    "diagram": "no se entiende qué muestra.",
    "photo": "parece falsa o está deformada.",
}


SHEET_PROMPT = """Esta imagen es una hoja con {n} ilustraciones para un libro educativo impreso, en orden de
lectura (izquierda a derecha, arriba a abajo). Tipo: {kind}. Lo que debe mostrar cada una:
{subjects}
Responde solo con json: {{"panels": [{{"ok": true|false, "has_text": true|false, "issues": "una frase o vacío"}}]}}
con un elemento por ilustración, en el mismo orden. ok es false solo si tiene texto o letras, si no muestra lo
pedido, si es inapropiada para niños, o si {extra}"""


STYLE_PROMPT = """Eres directora de arte de una editorial de material educativo impreso. La imagen tiene {n} páginas
de referencia numeradas (portadas y páginas interiores de cuadernillos o libros). Lee su ESTILO, no su contenido:
1. Elige hasta 3 páginas con el diseño más profesional y vendible (best_pages, por su número).
2. Describe el estilo común de esas páginas para reproducirlo en libros nuevos, sin copiar dibujos, textos,
   personajes ni marcas.
Responde solo con json:
{{"best_pages": [1, 3], "score": 1-10 (qué tan profesional es el diseño),
 "palette": ["#fondo de página muy claro", "#tinta del texto", "#color de acento principal"],
 "heading_look": "rounded|handwritten|serif|geometric|script|bubbly" (cómo son los títulos),
 "frame": "none|line|rounded|dashed|double" (marco alrededor de cada página),
 "ornament": "estrellas|notas|hojas|puntos|formas|ninguno",
 "density": "airy|balanced|dense", "color_use": "bw|accents|full" (interior en blanco y negro, con acentos o a color),
 "illustration_style": "en inglés, una frase: técnica y trazo de las ilustraciones (p. ej. thick black outline clip-art, flat vector, watercolor)",
 "traits": ["hasta 8 rasgos de maquetación en español, breves (p. ej. pestaña 'Ficha N' arriba a la izquierda, casillas de autoevaluación)"],
 "suits": "para qué tomos sirve este estilo, en una frase en español"}}"""


@dataclass
class Review:
    ok: bool
    has_text: bool = False
    matches_subject: bool = True
    issues: str = ""
    cost_usd: float | None = None


class OpenRouterVision:
    def __init__(self, api_key: str, model: str, *, timeout: float = 60,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key, self.model, self.timeout, self.transport = api_key, model, timeout, transport

    async def review(self, image: bytes, *, kind: str, subject: str) -> Review:
        verdict, cost = await self._ask(image, REVIEW_PROMPT.format(kind=kind, subject=subject, extra=EXTRA[kind]))
        return _review(verdict, cost)

    async def review_sheet(self, image: bytes, subjects: list[str], *, kind: str) -> list[Review]:
        """One call for a whole sheet; panels the model forgot to judge count as accepted."""
        listing = "\n".join(f"{i}. {s}" for i, s in enumerate(subjects, 1))
        verdict, cost = await self._ask(image, SHEET_PROMPT.format(n=len(subjects), kind=kind, subjects=listing,
                                                                   extra=EXTRA[kind]))
        panels = verdict.get("panels") if isinstance(verdict.get("panels"), list) else []
        return [_review(panels[i] if i < len(panels) and isinstance(panels[i], dict) else {"ok": True},
                        cost if i == 0 else None) for i in range(len(subjects))]

    async def analyze_style(self, sheet: bytes, pages: int) -> tuple[dict, float | None]:
        """Curator and Style analyst in one call over a numbered contact sheet of reference pages."""
        return await self._ask(sheet, STYLE_PROMPT.format(n=pages), max_tokens=1200)

    async def _ask(self, image: bytes, prompt: str, max_tokens: int = 800) -> tuple[dict, float | None]:
        url = f"data:{_sniff(image)};base64,{base64.b64encode(image).decode()}"
        body = {"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                "reasoning": {"exclude": True}, "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": url}}]}]}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http:
                response = await http.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                                           headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError as exc:
            raise UpstreamError("upstream_unavailable", "No se pudo conectar con el revisor.") from exc
        if response.status_code in (401, 402, 403):
            raise UpstreamAuthError(f"OpenRouter {response.status_code}")
        if response.status_code >= 400:
            raise UpstreamError("upstream_unavailable", f"El revisor respondió {response.status_code}.")
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"] or ""
            # Some vision models wrap the json in prose or a ```json fence despite response_format.
            verdict = json.loads(content[content.index("{"):content.rindex("}") + 1])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raw = str((payload.get("choices") or [{}])[0].get("message", {}).get("content"))[:200]
            raise UpstreamError("invalid_output", f"El revisor no devolvió un veredicto: {raw!r}") from exc
        return verdict, (payload.get("usage") or {}).get("cost")


def _review(verdict: dict, cost: float | None) -> Review:
    return Review(ok=bool(verdict.get("ok")), has_text=bool(verdict.get("has_text")),
                  matches_subject=bool(verdict.get("matches_subject", True)),
                  issues=str(verdict.get("issues") or "")[:500], cost_usd=cost)
