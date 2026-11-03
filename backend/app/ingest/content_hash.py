"""Canonical content hash for reupload detection.

The file sha256 only catches byte-identical PDFs. This hash is computed from the
extracted key-value fields, so a regenerated PDF with reordered fields, extra
whitespace or changed metadata still matches. A match is a duplicate candidate
for a human, never an automatic merge.
"""
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

_SYMBOLS = re.compile(r"[^\w\s]|_")
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Drop symbols and collapse whitespace. Letters and digits of any script stay."""
    return _WHITESPACE.sub(" ", _SYMBOLS.sub("", text)).strip()


def _normalize_key(key: Any) -> str:
    return normalize_text(str(key)).casefold()


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, Mapping):
        return _normalize_fields(value)
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    return value


def _normalize_fields(fields: Mapping[str, Any], exclude_keys: Iterable[str] = ()) -> dict[str, Any]:
    excluded = {_normalize_key(key) for key in exclude_keys}
    normalized = {_normalize_key(key): _normalize_value(value) for key, value in fields.items()}
    return {key: value for key, value in normalized.items() if key not in excluded}


def canonical_content_hash(fields: Mapping[str, Any], exclude_keys: Iterable[str] = ()) -> str:
    """SHA-256 of sorted, normalized JSON built from extracted fields.

    Keys are casefolded. Keys and string values have symbols removed and
    whitespace collapsed. Pass `exclude_keys` for fields that are not part of
    document identity, such as filename or upload time. Do not exclude reference
    numbers, dates or amounts, or different documents will merge.
    """
    canonical = json.dumps(
        _normalize_fields(fields, exclude_keys),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
