"""A stand-in for the Anthropic client. Code under test must build its client through
anthropic.Anthropic(...) so the conftest fixture can swap it in."""

import json
from types import SimpleNamespace
from typing import Any


class FakeMessages:
    def __init__(self) -> None:
        self.replies: list[SimpleNamespace | Exception] = []
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if not self.replies:
            raise AssertionError("FakeAnthropic got a call with no scripted reply")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeAnthropic:
    def __init__(self) -> None:
        self.messages = FakeMessages()

    def reply(self, payload: Any, stop_reason: str = "end_turn", model: str = "fake-model") -> None:
        """Queue one response. A dict or list becomes JSON text, a string is sent as is."""
        body = payload if isinstance(payload, str) else json.dumps(payload)
        self.messages.replies.append(
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text=body)],
                stop_reason=stop_reason,
                model=model,
                usage=SimpleNamespace(input_tokens=10, output_tokens=10),
            )
        )

    def fail(self, error: Exception) -> None:
        """Queue an exception to be raised by the next call."""
        self.messages.replies.append(error)
