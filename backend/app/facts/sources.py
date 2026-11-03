"""Everything that says something about the nine form fields of one case, each value with its citation.

Documents and the verified profile can be evidence. Notes, messages and claims are never evidence."""

import hashlib
import json
import logging
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import reader
from app.cases.communications import intake_call_id
from app.core.config import get_settings
from app.core.contracts import ReadStatus
from app.facts import match_gate
from app.facts.normalize import DATE_FIELDS, normalize
from app.ingest import comm

log = logging.getLogger(__name__)

EVIDENCE, CLAIM = "EVIDENCE", "CLAIM"
PROFILE_PREFIX = "07_case_profiles."
DOC_KEY = re.compile(r"^[A-Z][A-Z0-9_]*\.")
# The form target of each field. The targets come from 08_form_field_map.json.
TARGET_FIELD = {
    "applicant.legal_name": "full_name",
    "applicant.date_of_birth": "date_of_birth",
    "applicant.passport_number": "passport_number",
    "applicant.passport_expiration": "passport_expiration",
    "travel.last_entry": "last_entry_date",
    "employment.organization": "employer_name",
    "employment.start_date": "employment_start_date",
    "case.prior_receipt_reference": "prior_receipt_number",
    "applicant.mailing_address": "mailing_address",
}
FIELDS = tuple(TARGET_FIELD.values())
# The communication prompts name some fields differently from the form.
CLAIM_ALIASES = {"employer": "employer_name", "employment_start": "employment_start_date", "last_entry": "last_entry_date"}
READABLE = ("USABLE", "NEEDS_HUMAN_REVIEW")
COMM_CATEGORY = {"ZOOM": "ZOOM_NOTES", "EMAIL": "EMAIL_MESSAGE", "WHATSAPP": "WHATSAPP_CHAT"}


class Assertion(BaseModel):
    field: str
    value: str
    normalized_value: str
    source_kind: str
    source_id: str
    quote: str | None = None
    page: int | None = None
    verified: bool = False
    trust: str = CLAIM
    from_image: bool = False
    phase: str = "UPDATE"
    group_key: str | None = None  # set when the address gate calls two spellings the same place


def make(field: str, value: str, kind: str, source_id: str, *, quote: str | None = None, page: int | None = None,
         verified: bool = False, trust: str = CLAIM, from_image: bool = False, phase: str | None = None,
         date_fields: tuple[str, ...] = DATE_FIELDS) -> Assertion:  # fmt: skip
    """A claim kind can never be evidence, whatever the caller asks for."""
    if kind not in ("DOCUMENT", "PROFILE"):
        trust, verified = CLAIM, False
    phase = {"DOCUMENT": "DOCUMENT", "PROFILE": "PROFILE"}.get(kind, phase or "UPDATE")
    return Assertion(field=field, value=" ".join(value.split()), normalized_value=normalize(field, value, date_fields), source_kind=kind,
                     source_id=source_id, quote=quote, page=page, verified=verified, trust=trust, from_image=from_image, phase=phase)  # fmt: skip


def claim_kind(source_id: str) -> str:
    return "INTAKE" if source_id.startswith("Z-") else "MESSAGE" if source_id.startswith("MSG-") else "CLAIM"


class ExtraField(BaseModel):
    """A form input a user added from the AI tab. Its fact field is the target, such as additional.aadhaar_number."""

    target: str
    label: str
    value_type: str


ADDITIONAL_SECTION = "Additional client fields"


def additional_fields(db: Session) -> list[ExtraField]:
    """The enabled additional client fields, oldest first."""
    rows = db.execute(text("SELECT target, label, value_type FROM additional_form_fields WHERE enabled ORDER BY id")).all()
    return [ExtraField(target=r.target, label=r.label, value_type=r.value_type) for r in rows]


def field_names(db: Session) -> tuple[str, ...]:
    """Every field that gets a state: the nine form fields, then the additional client fields."""
    return FIELDS + tuple(f.target for f in additional_fields(db))


def date_fields(db: Session) -> tuple[str, ...]:
    return DATE_FIELDS + tuple(f.target for f in additional_fields(db) if f.value_type == "date")


_EXTRA = json.loads((Path(__file__).parent / "field_sources_extra.json").read_text(encoding="utf-8"))["source_candidates"]


def _declared(db: Session) -> dict[str, list[str]]:
    """Document sources the prompt registry declares: each extracted field of an active read prompt that names a form target.
    This is what the AI dashboard edits. A target this app does not know is ignored."""
    known = set(TARGET_FIELD) | {f.target for f in additional_fields(db)}
    rows = db.execute(
        text(
            "SELECT v.field_definitions FROM prompts p JOIN prompt_versions v ON v.id = p.active_version_id "
            "WHERE p.step = 'read' AND p.enabled ORDER BY p.key"
        )
    ).scalars()
    declared: dict[str, list[str]] = defaultdict(list)
    for definitions in rows:
        for item in definitions or []:
            target = item.get("form_target")
            if target in known and item["key"] not in declared[target]:
                declared[target].append(item["key"])
    return declared


def _candidates(db: Session, requestable: bool = False) -> dict[str, list[str]]:
    """The source candidates of the kit's field map, plus the document sources this app adds: the targets declared in the prompt
    registry and the older field_sources_extra.json.
    requestable is for the words that ask a client for a document. There an added source counts only for a field the kit names
    no document for, so a name or a birth date is still asked for on the passport and not on an address proof."""
    body = db.execute(text("SELECT body FROM rule_sets WHERE key = 'form_field_map' ORDER BY version DESC LIMIT 1")).scalar() or {}
    found = {TARGET_FIELD[f["target"]]: list(f.get("source_candidates", [])) for f in body.get("fields", []) if f["target"] in TARGET_FIELD}
    added = {target: list(names) for target, names in _EXTRA.items()}
    declared = _declared(db)
    for target, names in declared.items():
        added[target] = added.get(target, []) + [n for n in names if n not in added.get(target, [])]
    for target, names in added.items():
        field = TARGET_FIELD.get(target)
        if field in found and not (requestable and any(DOC_KEY.match(n) for n in found[field])):
            found[field] += [n for n in names if n not in found[field]]
    for extra in additional_fields(db):
        found[extra.target] = list(declared.get(extra.target, []))
    return found


def no_document_fields(db: Session) -> frozenset[str]:
    """Fields whose source candidates in the form field map name no document type, so no document can ever back them."""
    return frozenset(field for field, names in _candidates(db).items() if not any(DOC_KEY.match(n) for n in names))


def required_document_labels(db: Session) -> dict[str, str]:
    """For each field that one of the required documents can give, the name of that document, such as Passport."""
    body = db.execute(text("SELECT body FROM rule_sets WHERE key = 'document_rules' ORDER BY version DESC LIMIT 1")).scalar() or {}
    required = {item["category"] for item in body.get("required_document_categories", [])}
    labels: dict[str, str] = {}
    for field, names in _candidates(db).items():
        categories = [n.split(".")[0] for n in names if DOC_KEY.match(n) and n.split(".")[0] in required]
        if categories:
            labels[field] = " or ".join(dict.fromkeys(c.replace("_", " ").capitalize() for c in categories))
    return labels


def document_required_fields(db: Session) -> frozenset[str]:
    """Fields that one of the required documents can give. For these the profile and the claims are not enough on their own,
    the document has to be there. A field whose only documents are optional, such as the mailing address with an address proof,
    rests on the profile."""
    return frozenset(required_document_labels(db))


def _document_rows(db: Session, case_id: str) -> list[Any]:
    return db.execute(
        text(
            "SELECT DISTINCT ON (r.upload_id, r.category) r.upload_id, r.extracted, u.outcome FROM document_reads r "
            "JOIN uploads u ON u.upload_id = r.upload_id WHERE u.case_id = :c AND u.deleted_at IS NULL AND u.outcome = ANY(:o) "
            "AND r.status = 'READ' AND r.extracted IS NOT NULL ORDER BY r.upload_id, r.category, r.read_at DESC, r.id DESC"
        ),
        {"c": case_id, "o": list(READABLE)},
    ).all()


def document_assertions(db: Session, case_id: str, candidates: dict[str, list[str]],
                        dates: tuple[str, ...] = DATE_FIELDS) -> list[Assertion]:  # fmt: skip
    """Values read from usable documents. A value read from a scanned page is never verified, so it is a claim."""
    found: list[Assertion] = []
    for row in _document_rows(db, case_id):
        read = {k.lower(): v for k, v in (row.extracted.get("fields") or {}).items() if isinstance(v, dict)}
        for field, names in candidates.items():
            for name in (n for n in names if DOC_KEY.match(n)):
                item = read.get(name.lower())
                if not item or not (item.get("value") or "").strip():
                    continue
                image = bool(item.get("from_image"))
                verified = bool(item.get("verified")) and not image
                trust = EVIDENCE if verified and row.outcome == "USABLE" else CLAIM
                found.append(make(field, item["value"], "DOCUMENT", row.upload_id, quote=item.get("quote"),
                                  page=item.get("page") or None, verified=verified, trust=trust, from_image=image, date_fields=dates))  # fmt: skip
    return found


def profile_assertions(db: Session, case_id: str, candidates: dict[str, list[str]]) -> list[Assertion]:
    """The profile. A person checked it earlier, so it is evidence, but it can be out of date. It counts as verified only
    once a person confirmed it in the app. An imported kit value shows as not confirmed."""
    rows = db.execute(
        text("SELECT source_id, field_name, verified_value, verification_state FROM profile_fields WHERE case_id = :c "
             "AND verification_state <> 'DRAFT_PLACEHOLDER' AND verified_value IS NOT NULL"),
        {"c": case_id},
    ).all()  # fmt: skip
    return [
        make(r.field_name, r.verified_value, "PROFILE", r.source_id, verified=r.verification_state == "HUMAN_VERIFIED", trust=EVIDENCE)
        for r in rows
        if r.field_name in FIELDS and PROFILE_PREFIX + r.field_name in candidates.get(r.field_name, [])
        and r.verified_value.strip()
    ]  # fmt: skip


def claim_assertions(db: Session, case_id: str) -> list[Assertion]:
    rows = db.execute(
        text("SELECT source_id, field_name, value, quote, page FROM claims WHERE case_id = :c ORDER BY id"), {"c": case_id}
    ).all()
    found = []
    baseline = intake_call_id(db, case_id)
    for r in rows:
        field = CLAIM_ALIASES.get(r.field_name, r.field_name)
        if field in FIELDS:
            found.append(make(field, r.value, claim_kind(r.source_id), r.source_id, quote=r.quote, page=r.page,
                              phase="BASELINE" if r.source_id == baseline else "UPDATE"))
    return found


def collect(db: Session, case_id: str) -> list[Assertion]:
    """All assertions for the case, documents first, then the profile, then claims."""
    candidates = _candidates(db)
    items = document_assertions(db, case_id, candidates, date_fields(db)) + profile_assertions(db, case_id, candidates) + claim_assertions(db, case_id)
    match_gate.apply(db, items)
    return items


# ---------------------------------------------------------------- claims from the notes and messages of the starter kit

_ATTEMPTED: set[tuple[str, str, int]] = set()
# Pages ask for the facts at the same time. The second request waits, so it sees the claims the first one stored.
_LOCKS: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def _unread(db: Session, case_id: str) -> list[tuple[str, str, str]]:
    """Notes and inbound messages with no claim yet, as (source id, category, text)."""
    notes = db.execute(
        text("SELECT intake_id, summary FROM intake_notes WHERE case_id = :c AND NOT EXISTS "
             "(SELECT 1 FROM claims k WHERE k.case_id = :c AND k.source_id = intake_notes.intake_id)"),
        {"c": case_id},
    ).all()  # fmt: skip
    messages = db.execute(
        text("SELECT message_id, channel, subject, body FROM messages WHERE case_id = :c AND direction = 'INBOUND' "
             "AND NOT EXISTS (SELECT 1 FROM claims k WHERE k.case_id = :c AND k.source_id = messages.message_id)"),
        {"c": case_id},
    ).all()  # fmt: skip
    todo = [(n.intake_id, "ZOOM_NOTES", n.summary) for n in notes]
    todo += [(m.message_id, COMM_CATEGORY[m.channel], f"{m.subject}\n{m.body}" if m.subject else m.body)
             for m in messages if m.channel in COMM_CATEGORY]  # fmt: skip
    return todo


def _read_claims(category: str, body: str) -> Any:
    """The same reader and prompts as an uploaded call or message. The category is known, so no classify call."""
    sha = hashlib.sha256(body.encode()).hexdigest()
    loaded = reader.LoadedUpload(sha, [(1, body)])
    group, deps = loaded.pages, reader.default_deps(lambda _id: loaded)
    _, _, result = reader._read_group(deps, category, group, sha)
    return reader._build_read(category, group, result, None, {})


def ensure_claims(db: Session, case_id: str) -> int:
    """Read the notes and messages that have no claims yet. Safe to call often and it never raises.

    It does nothing when auto read is off or there is no API key. The reader caches every result."""
    settings = get_settings()
    if not settings.auto_read or not settings.anthropic_api_key:
        return 0
    try:
        with _LOCKS[case_id]:
            return _read_unread(db, case_id)
    except Exception:
        log.exception("Could not read the claims for %s", case_id)
        db.rollback()
        return 0


def _read_unread(db: Session, case_id: str) -> int:
    todo = [t for t in _unread(db, case_id) if (case_id, t[0], hash(t[2])) not in _ATTEMPTED]
    _ATTEMPTED.update((case_id, t[0], hash(t[2])) for t in todo)
    if not todo:
        return 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        reads = list(pool.map(lambda t: _safe_read(t[1], t[2]), todo))
    stored = 0
    for (source_id, _, body), read in zip(todo, reads, strict=True):
        if read is None or read.status != ReadStatus.READ:
            _ATTEMPTED.discard((case_id, source_id, hash(body)))  # try again on a later visit
            continue
        stored += comm.store_claims(db, case_id, source_id, [read])
    db.commit()
    return stored


def _safe_read(category: str, body: str) -> Any:
    try:
        return _read_claims(category, body)
    except Exception:
        log.exception("Could not read a %s text", category)
        return None
