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
    "illustration": "está deformada o es confusa.",
    "diagram": "no se entiende qué muestra.",
    "photo": "parece falsa o está deformada.",
}


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
        url = f"data:{_sniff(image)};base64,{base64.b64encode(image).decode()}"
        body = {"model": self.model, "temperature": 0, "max_tokens": 800,
                "reasoning": {"exclude": True}, "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": REVIEW_PROMPT.format(kind=kind, subject=subject, extra=EXTRA[kind])},
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
        return Review(ok=bool(verdict.get("ok")), has_text=bool(verdict.get("has_text")),
                      matches_subject=bool(verdict.get("matches_subject", True)),
                      issues=str(verdict.get("issues") or "")[:500], cost_usd=(payload.get("usage") or {}).get("cost"))
