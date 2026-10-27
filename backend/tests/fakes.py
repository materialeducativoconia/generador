from app.llm import Completion


class ScriptedLLM:
    """Stands in for DeepSeek: returns the scripted replies in order and records the prompts it got."""

    def __init__(self, *replies: str | Completion):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    async def complete(self, messages, *, temperature, max_tokens, json_mode=True):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        return reply if isinstance(reply, Completion) else Completion(text=reply, finish_reason="stop", model="fake")
