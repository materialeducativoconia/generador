from app.llm import Completion, UpstreamError


class ScriptedLLM:
    """Stands in for DeepSeek: returns the scripted replies in order and records the prompts it got. Past the
    script it behaves like DeepSeek being down, so best-effort agents (the Designer in the outline job) skip."""

    def __init__(self, *replies: str | Completion):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    async def complete(self, messages, *, temperature, max_tokens, json_mode=True):
        self.calls.append(messages)
        if not self.replies:
            raise UpstreamError("upstream_unavailable", "script ended")
        reply = self.replies.pop(0)
        return reply if isinstance(reply, Completion) else Completion(text=reply, finish_reason="stop", model="fake")
