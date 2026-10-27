"""OpenRouter image generation (POST /api/v1/images). Used by the cover agent."""

import base64
from dataclasses import dataclass

import httpx

from app.llm import UpstreamAuthError, UpstreamError


@dataclass
class GeneratedImage:
    data: bytes
    media_type: str
    model: str
    cost_usd: float | None


class OpenRouterImages:
    def __init__(self, api_key: str, model: str, *, timeout: float = 180,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key, self.model, self.timeout, self.transport = api_key, model, timeout, transport

    async def generate(self, prompt: str, *, references: list[bytes] = (), aspect_ratio: str = "3:4") -> GeneratedImage:
        body = {"model": self.model, "prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": "1K"}
        if references:
            body["input_references"] = [
                {"type": "image_url", "image_url": {"url": f"data:{_sniff(r)};base64,{base64.b64encode(r).decode()}"}}
                for r in references
            ]
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http:
                response = await http.post("https://openrouter.ai/api/v1/images", json=body, headers={
                    "Authorization": f"Bearer {self.api_key}", "X-Title": "Material Educativo IA"})
        except httpx.TimeoutException as exc:
            raise UpstreamError("timeout", "OpenRouter no respondió a tiempo.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("upstream_unavailable", "No se pudo conectar con OpenRouter.") from exc
        if response.status_code in (401, 402, 403):
            raise UpstreamAuthError(f"OpenRouter {response.status_code}: {response.text[:300]}")
        if response.status_code == 429:
            raise UpstreamError("rate_limited", "OpenRouter limitó las peticiones.",
                                float(response.headers.get("retry-after", 0)) or None)
        if response.status_code >= 400:
            raise UpstreamError("upstream_unavailable", f"OpenRouter respondió {response.status_code}.")
        payload = response.json()
        images = payload.get("data") or []
        if not images or not images[0].get("b64_json"):
            raise UpstreamError("upstream_unavailable", "OpenRouter no devolvió ninguna imagen.")
        data = base64.b64decode(images[0]["b64_json"])
        return GeneratedImage(data=data, media_type=images[0].get("media_type") or _sniff(data), model=self.model,
                              cost_usd=(payload.get("usage") or {}).get("cost"))


def _sniff(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"
