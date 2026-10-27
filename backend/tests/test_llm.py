"""The DeepSeek client against a local server speaking the OpenAI-compatible streaming protocol."""

import contextlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.llm import DeepSeek, UpstreamAuthError, UpstreamError


@contextlib.contextmanager
def fake_deepseek(status=200, chunks=("{\"a\":", " 1}"), headers=None):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            if status != 200:
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": {"message": "nope"}}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            base = {"id": "1", "object": "chat.completion.chunk", "created": 0, "model": "deepseek-chat"}
            for i, text in enumerate(chunks):
                last = i == len(chunks) - 1
                event = {**base, "choices": [{"index": 0, "delta": {"content": text},
                                              "finish_reason": "stop" if last else None}]}
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            usage = {**base, "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14,
                                                      "prompt_cache_hit_tokens": 8, "prompt_cache_miss_tokens": 2}}
            self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        server.server_close()


def client(url):
    return DeepSeek("key", "deepseek-chat", rpm=600, max_inflight=2, base_url=url)


async def test_streams_text_usage_and_finish_reason():
    with fake_deepseek() as (url, seen):
        result = await client(url).complete([{"role": "user", "content": "json"}], temperature=0.7, max_tokens=100)

    assert result.text == '{"a": 1}'
    assert result.finish_reason == "stop"
    assert result.usage["prompt_cache_hit_tokens"] == 8
    assert seen[0]["response_format"] == {"type": "json_object"} and seen[0]["stream"] is True


async def test_429_is_retryable_and_carries_retry_after():
    with fake_deepseek(status=429, headers={"Retry-After": "7"}) as (url, _):
        with pytest.raises(UpstreamError) as exc:
            await client(url).complete([{"role": "user", "content": "x"}], temperature=1, max_tokens=10)

    assert exc.value.code == "rate_limited" and exc.value.retry_after == 7


@pytest.mark.parametrize("status", [401, 402])
async def test_bad_key_or_no_balance_is_not_retryable(status):
    with fake_deepseek(status=status) as (url, _):
        with pytest.raises(UpstreamAuthError):
            await client(url).complete([{"role": "user", "content": "x"}], temperature=1, max_tokens=10)


async def test_503_is_retryable():
    with fake_deepseek(status=503) as (url, _):
        with pytest.raises(UpstreamError) as exc:
            await client(url).complete([{"role": "user", "content": "x"}], temperature=1, max_tokens=10)

    assert exc.value.code == "upstream_unavailable"
