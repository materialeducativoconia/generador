"""DeepSeek client: OpenAI-compatible API, a global rate limiter and streaming timeouts (ARCHITECTURE.md §5.2)."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Protocol

import openai
from aiolimiter import AsyncLimiter


@dataclass
class Completion:
    text: str
    finish_reason: str | None
    model: str
    usage: dict = field(default_factory=dict)
    latency_ms: int | None = None
    time_to_first_token_ms: int | None = None


# deepseek-chat list prices, USD per million tokens: prompt served from the prefix cache, prompt not cached, output.
USD_PER_M = {"hit": 0.028, "miss": 0.28, "out": 0.42}


class LLM(Protocol):
    async def complete(
        self, messages: list[dict], *, temperature: float, max_tokens: int, json_mode: bool = True
    ) -> Completion: ...


class UpstreamError(Exception):
    """A failure worth retrying later (429, 5xx, timeouts)."""

    def __init__(self, code: str, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class UpstreamAuthError(Exception):
    """401/402: retrying only burns attempts; the queue needs an operator."""


class DeepSeek:
    def __init__(self, api_key: str, model: str, rpm: int, max_inflight: int,
                 base_url: str = "https://api.deepseek.com", idle_timeout: float = 90, total_timeout: float = 600):
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        self.model = model
        self.limiter = AsyncLimiter(rpm, 60)
        self.inflight = asyncio.Semaphore(max_inflight)
        self.idle_timeout = idle_timeout
        self.total_timeout = total_timeout

    async def complete(self, messages, *, temperature, max_tokens, json_mode=True) -> Completion:
        async with self.inflight:
            await self.limiter.acquire()
            started = time.monotonic()
            try:
                async with asyncio.timeout(self.total_timeout):
                    return await self._stream(messages, temperature, max_tokens, json_mode, started)
            except TimeoutError as exc:
                raise UpstreamError("timeout", "DeepSeek no respondió a tiempo.") from exc
            except openai.RateLimitError as exc:
                raise UpstreamError("rate_limited", "DeepSeek limitó las peticiones.", _retry_after(exc)) from exc
            except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
                raise UpstreamAuthError(str(exc)) from exc
            except openai.APIStatusError as exc:
                if exc.status_code == 402:
                    raise UpstreamAuthError("Saldo de DeepSeek insuficiente.") from exc
                raise UpstreamError("upstream_unavailable", f"DeepSeek respondió {exc.status_code}.") from exc
            except openai.APIConnectionError as exc:
                raise UpstreamError("upstream_unavailable", "No se pudo conectar con DeepSeek.") from exc

    async def _stream(self, messages, temperature, max_tokens, json_mode, started) -> Completion:
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"} if json_mode else openai.NOT_GIVEN,
            stream=True,
            stream_options={"include_usage": True},
        )
        parts, finish, usage, ttft = [], None, {}, None
        iterator = stream.__aiter__()
        while True:
            try:
                # "Slow but alive" vs "hung": each chunk must arrive within the idle timeout.
                chunk = await asyncio.wait_for(iterator.__anext__(), self.idle_timeout)
            except StopAsyncIteration:
                break
            if chunk.usage:
                usage = chunk.usage.model_dump()
            for choice in chunk.choices:
                if choice.delta.content:
                    ttft = ttft or int((time.monotonic() - started) * 1000)
                    parts.append(choice.delta.content)
                finish = choice.finish_reason or finish
        return Completion(
            text="".join(parts), finish_reason=finish, model=self.model, usage=usage,
            latency_ms=int((time.monotonic() - started) * 1000), time_to_first_token_ms=ttft,
        )


def _retry_after(exc: openai.APIStatusError) -> float | None:
    try:
        return float(exc.response.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None
