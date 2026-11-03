"""The value gate. Two values of the same field that are written differently are a conflict unless this gate says they name
the same thing. It covers the mailing address, the client name and the employer. Dates, passport numbers and other
identifiers are compared exactly and never go through the gate.

Code decides first. A pair whose numbers or name parts cannot agree is stored as different without asking the model, and only a
pair that passes that check is asked. A spelling difference in a name, Dawan and Dhawan, is therefore always a conflict. Any
doubt, failed call or injection flag leaves the values different.

The answer is stored once per pair in value_matches. Reads only look the stored answers up, so a read never calls the model.
A change that brings a new spelling asks once, from the rebuild or from the document check."""

import json
import logging
import re
import unicodedata
from collections.abc import Callable, Sequence
from itertools import combinations
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.client import STATUS_OK, ClaudeCall, run_prompt
from app.ai.envelope import build_envelope
from app.ai.reader import _db_get_version
from app.core.config import get_settings
from app.facts.normalize import compare_key, normalize

log = logging.getLogger(__name__)

PROMPT_KEY = "facts.value_match"
ADDRESS, PERSON_NAME, ORGANIZATION = "ADDRESS", "PERSON_NAME", "ORGANIZATION"
FIELD_KIND = {"mailing_address": ADDRESS, "full_name": PERSON_NAME, "employer_name": ORGANIZATION}
MAX_PAIRS = 12
_NUMBER = re.compile(r"\d+")
_WORD = re.compile(r"[^\W_]+")
_TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof"}
_ORG_ENDINGS = {"llc", "inc", "ltd", "corp", "co", "company", "corporation", "incorporated", "limited", "the"}


def _tokens(value: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return [w.casefold() for w in _WORD.findall(plain)]


def numbers_agree(a: str, b: str) -> bool:
    """Every number in the shorter address, street number, unit and postal code, is also in the other."""
    one, two = set(_NUMBER.findall(a)), set(_NUMBER.findall(b))
    small, large = (one, two) if len(one) <= len(two) else (two, one)
    return small <= large


def _covered(small: list[str], large: list[str]) -> bool:
    """Every token of the shorter name is in the longer one. An initial stands for a token that starts with it."""

    def fits(t: str, u: str) -> bool:
        return t == u or (len(t) == 1 and u.startswith(t)) or (len(u) == 1 and t.startswith(u))

    return all(any(fits(t, u) for u in large) for t in small)


def names_agree(a: str, b: str) -> bool:
    """Same name parts in any order, an initial for a given name allowed. A different spelling of a part never agrees.
    A name of one part is not enough."""
    one, two = [t for t in _tokens(a) if t not in _TITLES], [t for t in _tokens(b) if t not in _TITLES]
    small, large = (one, two) if len(one) <= len(two) else (two, one)
    return len(small) >= 2 and _covered(small, large)


def organizations_agree(a: str, b: str) -> bool:
    """The same words once a legal ending such as LLC is dropped. A different word or number never agrees."""
    one, two = [t for t in _tokens(a) if t not in _ORG_ENDINGS], [t for t in _tokens(b) if t not in _ORG_ENDINGS]
    small, large = (one, two) if len(one) <= len(two) else (two, one)
    return bool(small) and set(small) <= set(large)


_GUARD: dict[str, Callable[[str, str], bool]] = {ADDRESS: numbers_agree, PERSON_NAME: names_agree, ORGANIZATION: organizations_agree}


def key_of(field: str, value: str) -> str:
    """The key a pair is stored under. It matches the comparison key the facts use."""
    return compare_key(normalize(field, value))


def _spellings(items: Sequence[Any]) -> dict[str, dict[str, str]]:
    """For each gated field, each distinct way it is written, by comparison key, with the first spelling."""
    found: dict[str, dict[str, str]] = {f: {} for f in FIELD_KIND}
    for a in items:
        if a.field in found:
            found[a.field].setdefault(compare_key(a.normalized_value), a.normalized_value)
    return found


def _stored(db: Session, field: str, keys: list[str]) -> dict[tuple[str, str], bool]:
    rows = db.execute(
        text("SELECT key_a, key_b, same FROM value_matches WHERE field = :f AND key_a = ANY(:k) AND key_b = ANY(:k)"),
        {"f": field, "k": keys},
    ).all()
    return {(r.key_a, r.key_b): r.same for r in rows}


def apply(db: Session, items: Sequence[Any]) -> None:
    """Give assertions that the gate calls the same value one group key, so they count as one value. Read only."""
    for field, keys in _spellings(items).items():
        if len(keys) < 2:
            continue
        same = _stored(db, field, list(keys))
        parent = {k: k for k in keys}

        def find(k: str, parent: dict[str, str] = parent) -> str:
            while parent[k] != k:
                k = parent[k]
            return k

        for (a, b), is_same in same.items():
            if is_same:
                parent[find(b)] = find(a)
        # A cluster that holds a pair the gate called different is not trusted, so nothing in it is merged.
        broken = {find(a) for (a, b), is_same in same.items() if not is_same and find(a) == find(b)}
        for item in items:
            if item.field == field:
                key = compare_key(item.normalized_value)
                root = find(key)
                item.group_key = key if root in broken else root


def _ask(db: Session, wanted: list[tuple[str, str, str, str, str]], case_id: str | None, call: ClaudeCall | None) -> int:
    """wanted rows are (field, key_a, key_b, text_a, text_b). Decide each in code or ask the model. Returns the rows stored."""
    stored = 0

    def store(field: str, a: str, b: str, same: bool, reason: str, run_id: int | None) -> None:
        nonlocal stored
        db.execute(
            text("INSERT INTO value_matches (field, key_a, key_b, same, reason, prompt_run_id) VALUES (:f, :a, :b, :s, :r, :p) ON CONFLICT DO NOTHING"),
            {"f": field, "a": a, "b": b, "s": same, "r": reason[:500], "p": run_id},
        )
        stored += 1

    to_ask = []
    for field, a, b, ta, tb in wanted:
        if _GUARD[FIELD_KIND[field]](ta, tb):
            to_ask.append((field, a, b, ta, tb))
        else:
            store(field, a, b, False, "Decided in code: the numbers or name parts cannot agree.", None)
    settings = get_settings()
    asking = to_ask and (call is not None or (settings.auto_read and settings.anthropic_api_key))
    version = _db_get_version(PROMPT_KEY) if asking else None
    if version is None:
        return stored
    named = {f"p{i}": row for i, row in enumerate(to_ask, 1)}
    block = json.dumps([{"id": i, "kind": FIELD_KIND[r[0]], "a": r[3], "b": r[4]} for i, r in named.items()], ensure_ascii=False)
    try:
        variables = {"pairs": build_envelope([(1, block)])}
        result = call(version, variables) if call else run_prompt(PROMPT_KEY, version, variables, input_text=block, case_id=case_id)
    except Exception:
        log.exception("The value gate failed for %s", case_id)
        return stored
    if result.status != STATUS_OK or result.data is None or result.data.get("injection_flag"):
        return stored
    for entry in result.data.get("matches") or []:
        row = named.get(str(entry.get("id"))) if isinstance(entry, dict) else None
        if row is None or not isinstance(entry.get("same"), bool):
            continue
        store(row[0], row[1], row[2], entry["same"], str(entry.get("reason") or ""), result.run_id)
    return stored


def settle(db: Session, items: Sequence[Any], case_id: str | None = None, call: ClaudeCall | None = None) -> bool:
    """Decide every pair of spellings of a gated field that has no stored answer yet. True when any was stored.
    Never raises. A failed call stores nothing for the pairs it was asked, so they stay different."""
    wanted: list[tuple[str, str, str, str, str]] = []
    for field, keys in _spellings(items).items():
        if len(keys) < 2:
            continue
        known = _stored(db, field, list(keys))
        wanted += [(field, a, b, keys[a], keys[b]) for a, b in combinations(sorted(keys), 2) if (a, b) not in known]
    if not wanted:
        return False
    try:
        return _ask(db, wanted[:MAX_PAIRS], case_id, call) > 0
    except Exception:
        log.exception("The value gate failed for %s", case_id)
        return False


def settle_names(db: Session, names: Sequence[str], case_id: str | None = None, call: ClaudeCall | None = None) -> bool:
    """The same for person names that are about to be compared outside the facts, such as a document against the case client."""
    keys = {key_of("full_name", n): normalize("full_name", n) for n in names if n and n.strip()}
    if len(keys) < 2:
        return False
    known = _stored(db, "full_name", list(keys))
    wanted = [("full_name", a, b, keys[a], keys[b]) for a, b in combinations(sorted(keys), 2) if (a, b) not in known]
    if not wanted:
        return False
    try:
        return _ask(db, wanted[:MAX_PAIRS], case_id, call) > 0
    except Exception:
        log.exception("The name gate failed for %s", case_id)
        return False


def name_matcher(db: Session, names: Sequence[str]) -> Callable[[str, str], bool]:
    """A function that says whether two names are the same person written differently, from the stored answers only."""
    keys = list({key_of("full_name", n) for n in names if n and n.strip()})
    stored = _stored(db, "full_name", keys) if len(keys) > 1 else {}

    def same(a: str, b: str) -> bool:
        ka, kb = key_of("full_name", a), key_of("full_name", b)
        return ka == kb or stored.get((min(ka, kb), max(ka, kb)), False)

    return same
