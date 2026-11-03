"""Read only tools for the investigation agent.

The case id is fixed when the Toolbox is built. No tool takes a case id and no tool writes. Every call gets a result id
such as T1 that an answer can cite. A file that belongs to another client is described only as belonging to someone else.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.cases import communications, documents, exceptions, repository
from app.core import audit
from app.core.security import Actor
from app.facts import engine
from app.ingest import service as ingest
from app.investigate import compare

TEXT_CAP = 300
LIST_CAP = 40
AUDIT_CAP = 20
FOREIGN_CODES = ("WRONG_CLIENT", "MIXED_CLIENTS", "OWNER_MISMATCH")
COMPARE_TOOLS = ("compare_dates", "add_days", "is_expired", "compare_names", "compare_values")

_STR = {"type": "string"}


def _spec(name: str, description: str, **props: dict[str, Any]) -> dict[str, Any]:
    schema = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    return {"name": name, "description": description, "input_schema": schema}


TOOL_SPECS: list[dict[str, Any]] = [
    _spec("list_documents", "Uploaded files of this case with outcome and reason. Files of another client are hidden."),
    _spec("get_checklist", "Required document categories of this case and whether each is satisfied, not usable or missing."),
    _spec("list_facts_and_conflicts", "Fact fields of this case with their sources, and which fields have conflicting sources."),
    _spec("list_events", "Portal and calendar events of this case."),
    _spec("list_communications", "Calls and messages of this case. These are claims and never facts."),
    _spec("get_audit_tail", "The newest audit lines of this case. Ids and states only.", limit={"type": "integer", "minimum": 1, "maximum": AUDIT_CAP}),
    _spec("get_exceptions", "The open exceptions of this case, the same list as the Exceptions page."),
    _spec("compare_dates", "Compare two dates written as YYYY-MM-DD or MM/DD/YYYY.", a=_STR, b=_STR),
    _spec("add_days", "Add calendar days to a date written as YYYY-MM-DD or MM/DD/YYYY.", start=_STR, days={"type": "integer"}),
    _spec("is_expired", "Whether a date is before the fixed review date.", date=_STR),
    _spec("compare_names", "Similarity label for two names. It informs a person and resolves nothing.", a=_STR, b=_STR),
    _spec("compare_values", "Whether two values are equal, as dates when both are dates.", a=_STR, b=_STR),
]
ARGS = {s["name"]: set(s["input_schema"]["properties"]) for s in TOOL_SPECS}


@dataclass
class ToolResult:
    id: str
    tool: str
    args: dict[str, Any]
    data: Any
    source_ids: list[str] = field(default_factory=list)
    error: bool = False

    @property
    def is_compare(self) -> bool:
        return self.tool in COMPARE_TOOLS and not self.error


def _cut(value: str | None) -> str | None:
    return value if value is None or len(value) <= TEXT_CAP else value[:TEXT_CAP] + "..."


def _hide(row: documents.DocumentRow) -> bool:
    return row.outcome == "QUARANTINED" or row.reason_code in FOREIGN_CODES


class Toolbox:
    def __init__(self, db: Session, case_id: str, actor: Actor, as_of: date) -> None:
        self._db, self._case_id, self._actor, self._as_of = db, case_id, actor, as_of
        self.results: dict[str, ToolResult] = {}
        self._hidden: set[str] = set()

    def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        for earlier in self.results.values():
            if earlier.tool == name and earlier.args == args and not earlier.error:
                return earlier  # the same call gives the same result, so it keeps its id
        rid = f"T{len(self.results) + 1}"
        allowed = ARGS.get(name)
        if allowed is None or set(args) - allowed:
            result = ToolResult(rid, name, {}, {"error": "Unknown tool or argument. No tool takes a case id."}, error=True)
        else:
            try:
                data, ids = getattr(self, f"_{name}")(**args)
                result = ToolResult(rid, name, args, data, ids)
            except (TypeError, ValueError) as exc:
                result = ToolResult(rid, name, args, {"error": f"Bad arguments: {exc}"}, error=True)
        self.results[rid] = result
        return result

    def _rows(self) -> list[documents.DocumentRow]:
        page = documents.list_documents(
            self._db, actor=self._actor.label, role=self._actor.role, case=None, client=None, outcome=None,
            page=1, page_size=documents.MAX_PAGE_SIZE, exact_case=self._case_id,
        )  # fmt: skip
        self._hidden = {r.upload_id for r in page.items if _hide(r)}
        return page.items

    def _list_documents(self) -> tuple[Any, list[str]]:
        rows = self._rows()
        items = []
        for r in rows[:LIST_CAP]:
            if r.upload_id in self._hidden:
                items.append({"upload_id": r.upload_id, "outcome": r.outcome, "reason": f"This file belongs {exceptions.HIDDEN}"})
                continue
            items.append({"upload_id": r.upload_id, "filename": r.original_filename, "category": r.category_label, "outcome": r.outcome,
                          "reason": r.outcome_reason, "reason_code": r.reason_code, "duplicate_of": r.duplicate_of,
                          "injection_flagged": r.injection})  # fmt: skip
        return items, [r.upload_id for r in rows[:LIST_CAP]]

    def _get_checklist(self) -> tuple[Any, list[str]]:
        self._rows()
        items, ids = [], []
        for c in ingest.checklist(self._db, self._case_id):
            reasons = [{"upload_id": r.upload_id, "outcome": r.outcome,
                        "reason": f"This file belongs {exceptions.HIDDEN}" if r.upload_id in self._hidden else r.reason} for r in c.reasons]  # fmt: skip
            items.append({"category": c.category, "label": c.label, "status": c.status, "reasons": reasons})
            ids += [r.upload_id for r in c.reasons]
        return items, ids

    def _list_facts_and_conflicts(self) -> tuple[Any, list[str]]:
        states = engine.compute_states(self._db, self._case_id)
        items = [{"field": s.field, "label": s.label, "state": s.state, "value": s.value, "decided_by": s.decided_by.reviewer_id if s.decided_by else None,
                  "sources": [{"source_id": x.source_id, "kind": x.source_kind, "trust": x.trust, "value": x.value, "quote": _cut(x.quote), "verified": x.verified}
                              for x in s.sources]} for s in states if s.sources]  # fmt: skip
        return items, [x.source_id for s in states for x in s.sources]

    def _list_events(self) -> tuple[Any, list[str]]:
        events = repository.list_events(self._db, self._case_id)[:LIST_CAP]
        items = [{"event_id": e["event_id"], "date": e["event_date"].isoformat(), "type": e["event_type"], "source": e["event_source"],
                  "verified": bool(e["source_verified"]), "details": _cut(e["details"])} for e in events]  # fmt: skip
        return items, [e["event_id"] for e in events]

    def _list_communications(self) -> tuple[Any, list[str]]:
        rows = communications.list_communications(self._db, self._case_id)[-LIST_CAP:]
        items = [{"source_id": c.source_id, "kind": c.kind, "direction": c.direction, "when": c.occurred_at, "subject": _cut(c.subject), "body": _cut(c.body),
                  "is_draft_not_sent": c.is_draft, "client_question": c.client_question} for c in rows]  # fmt: skip
        return items, [c.source_id for c in rows]

    def _get_audit_tail(self, limit: int = 10) -> tuple[Any, list[str]]:
        _, entries = audit.list_entries(self._db, self._case_id, limit=max(1, min(int(limit), AUDIT_CAP)))
        items = [{"seq": e.seq, "action": e.action.value, "outcome": e.outcome.value, "actor": e.actor, "target": f"{e.target_type or ''} {e.target_id or ''}".strip()}
                 for e in entries]  # fmt: skip
        return items, []

    def _get_exceptions(self) -> tuple[Any, list[str]]:
        found = [i for i in exceptions.build_items(self._db, self._actor) if i.case_id == self._case_id]
        items = [{"type": i.type, "severity": i.severity, "title": i.title, "reason": i.reason, "source_ids": i.source_ids,
                  "next_action": i.next_action, "owner_role": i.owner_role.value} for i in found]  # fmt: skip
        return items, [s for i in found for s in i.source_ids]

    def _compare_dates(self, a: str, b: str) -> tuple[Any, list[str]]:
        return compare.compare_dates(a, b), []

    def _add_days(self, start: str, days: int) -> tuple[Any, list[str]]:
        return compare.add_days(start, int(days)), []

    def _is_expired(self, date: str) -> tuple[Any, list[str]]:
        return compare.is_expired(date, self._as_of), []

    def _compare_names(self, a: str, b: str) -> tuple[Any, list[str]]:
        return compare.compare_names(a, b), []

    def _compare_values(self, a: str, b: str) -> tuple[Any, list[str]]:
        return compare.compare_values(a, b), []

