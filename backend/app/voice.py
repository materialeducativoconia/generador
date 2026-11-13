"""OpenRouter text-to-speech (POST /api/v1/audio/speech) with Gemini TTS: the marketing videos' voiceover.
Gemini answers raw PCM (24 kHz, 16-bit, mono); it is wrapped in a WAV the browser renderer decodes."""

import io
import wave

import httpx

from app.llm import UpstreamAuthError, UpstreamError

RATE = 24_000
# Gemini reads `input` word for word: how it is said goes apart, in `instructions`.
STYLE = ("Locutora latinoamericana de anuncios de TikTok: cálida, segura y con energía, ritmo ágil y natural, "
         "sonrisa en la voz; sin acento de España.")


def wav(pcm: bytes, rate: int = RATE) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def seconds(audio: bytes) -> float:
    with wave.open(io.BytesIO(audio)) as w:
        return w.getnframes() / w.getframerate()


class OpenRouterVoice:
    def __init__(self, api_key: str, model: str, voice: str, *, timeout: float = 90,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key, self.model, self.voice, self.timeout, self.transport = api_key, model, voice, timeout, transport

    async def speak(self, text: str, *, instructions: str = STYLE) -> bytes:
        """The words read aloud, as a WAV."""
        body = {"model": self.model, "input": text, "voice": self.voice, "instructions": instructions,
                "response_format": "pcm"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as http:
                response = await http.post("https://openrouter.ai/api/v1/audio/speech", json=body, headers={
                    "Authorization": f"Bearer {self.api_key}", "X-Title": "Jelyx Docs"})
        except httpx.TimeoutException as exc:
            raise UpstreamError("timeout", "OpenRouter no respondió a tiempo.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("upstream_unavailable", "No se pudo conectar con OpenRouter.") from exc
        if response.status_code in (401, 402, 403):
            raise UpstreamAuthError(f"OpenRouter {response.status_code}: {response.text[:300]}")
        if response.status_code == 429:
            raise UpstreamError("rate_limited", "OpenRouter limitó las peticiones.",
                                float(response.headers.get("retry-after", 0)) or None)
        if response.status_code >= 400 or not response.content:
            raise UpstreamError("upstream_unavailable", f"OpenRouter respondió {response.status_code}.")
        data = response.content
        if data[:4] == b"RIFF":  # a provider that already wraps it
            return data
        return wav(data[: len(data) // 2 * 2])
