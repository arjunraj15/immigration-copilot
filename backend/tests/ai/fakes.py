"""Fake model, fake Claude API objects and reader dependencies. No network."""

import itertools
import threading
import time
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from app.ai.client import STATUS_OK, CallResult
from app.ai.reader import LoadedUpload, ReaderDeps

CLASSIFY = "doc.classify"
GENERIC = "doc.read.generic"


def page_entry(page: int, category: str, language: str = "en", legible: bool = True,
               injection: bool = False) -> dict[str, Any]:
    return {"page": page, "category": category, "language": language, "legible": legible,
            "injection_flag": injection, "owner_names": []}


def field(value: str | None, quote: str, page: int = 1) -> dict[str, Any]:
    return {"value": value, "quote": quote, "page": page}


def read_data(fields: dict[str, Any], category: str = "PASSPORT", language: str = "en",
              legible: bool = True, injection: bool = False) -> dict[str, Any]:
    return {"category": category, "language": language, "legible": legible,
            "injection_flag": injection, "fields": fields}


class FakeModel:
    """Dispatches on prompt key. Read results are chosen by the category variable."""

    def __init__(self, classify: Any, reads: Mapping[str, Any] | None = None,
                 delays: Mapping[str, float] | None = None) -> None:
        self.classify = classify
        self.reads = dict(reads or {})
        self.delays = dict(delays or {})
        self.calls: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def _wrap(self, item: Any) -> CallResult:
        if isinstance(item, CallResult):
            return item
        return CallResult(STATUS_OK, item, next(self._ids), "end_turn")

    def __call__(self, version: Mapping[str, Any], variables: Mapping[str, Any]) -> CallResult:
        key = version["prompt_key"]
        with self._lock:
            self.calls.append((key, version, variables))
        if key == CLASSIFY:
            return self._wrap(self.classify)
        category = variables["category"]
        time.sleep(self.delays.get(category, 0))
        return self._wrap(self.reads[category])

    def keys(self) -> list[str]:
        return [c[0] for c in self.calls]


def make_deps(model: FakeModel, pages: list[tuple[int, str]], sha: str = "sha-1",
              read_keys: tuple[str, ...] = (), version: int = 1, cache: dict | None = None) -> ReaderDeps:
    """read_keys are the read prompts that exist. Classify and generic always exist."""
    available = {CLASSIFY, GENERIC, *read_keys}
    holder = {"version": version}

    def get_version(key: str) -> Mapping[str, Any] | None:
        if key not in available:
            return None
        return {"prompt_key": key, "version": holder["version"], "field_definitions": [
            {"key": "X.a", "label": "A", "type": "string", "required": True, "hint": None}]}

    deps = ReaderDeps(lambda _id: LoadedUpload(sha, pages), get_version, lambda: "- PASSPORT: id",
                      call=model, cache={} if cache is None else cache)
    deps.holder = holder  # type: ignore[attr-defined]
    return deps


def message(text: str | None = "{}", stop_reason: str = "end_turn", content: list | None = None,
            tokens: tuple[int, int] = (11, 7)) -> SimpleNamespace:
    blocks = content if content is not None else [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks,
                           usage=SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1]))


class FakeApi:
    """Stands in for anthropic.Anthropic. Each outcome is a message or an exception to raise."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
