"""The full trace of one model run: every call, the tool rounds and the answer. Stored as zlib compressed JSON."""

import json
import zlib
from typing import Any


def pack(trace: dict[str, Any]) -> bytes:
    return zlib.compress(json.dumps(trace, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"), 6)


def unpack(blob: bytes) -> dict[str, Any]:
    return json.loads(zlib.decompress(blob).decode("utf-8"))
