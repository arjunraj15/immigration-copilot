"""The answer shape, the citation checks and the answer built without a model.

Code decides what is kept. A reason is dropped when it cites a result that does not exist in this run, when a date or
name verdict has no compare result behind it, or when it reads like advice or a prediction.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel

from app.core.dates import us_text
from app.investigate.tools import Toolbox, ToolResult

DATE_VERDICT, NAME_VERDICT = "DATE_VERDICT", "NAME_VERDICT"
DATE_TOOLS = ("compare_dates", "add_days", "is_expired", "compare_values")
NAME_TOOLS = ("compare_names", "compare_values")
# Words that give a date or name verdict. Such a reason must cite a compare result even when the model did not mark it.
_VERDICT = re.compile(
    r"\b(expired|earlier than|later than|(before|after) the review date|same (name|person)|different name|similar name)\b", re.I
)
_ADVICE = re.compile(
    r"\b(will be (approved|denied|rejected)|likely to be|chances? of|you should|should (file|apply|sign)|eligible|eligibility|legal advice|guarantee\w*)\b",
    re.I,
)
MIN_CHARS = 20
NOTHING = "No blocking item was found in the case records."
REFUSED = "This tool explains what blocks the case records only. It does not give legal advice or predict outcomes."


class ReasonOut(BaseModel):
    text: str
    cited: list[str]
    source_ids: list[str]


class TraceStep(BaseModel):
    tool: str
    args: dict[str, Any]
    result_id: str


class InvestigationOut(BaseModel):
    question: str
    answer: str
    reasons: list[ReasonOut]
    trace: list[TraceStep]
    origin: Literal["MODEL", "FALLBACK", "REFUSED"]
    dropped: int = 0
    injection_flagged: bool = False
    note: str = "An explanation only. It is not a draft to send and it is not legal advice."


def trace_of(box: Toolbox) -> list[TraceStep]:
    return [TraceStep(tool=r.tool, args=r.args, result_id=r.id) for r in box.results.values()]


def _sources(cited: list[str], results: dict[str, ToolResult]) -> list[str]:
    return list(dict.fromkeys(s for rid in cited for s in results[rid].source_ids))


def _backed(kind: str, text: str, cited: list[ToolResult]) -> bool:
    """A date or name verdict needs a compare result of the right kind behind it."""
    tools = {r.tool for r in cited if r.is_compare}
    if kind == NAME_VERDICT:
        return bool(tools & set(NAME_TOOLS))
    if kind == DATE_VERDICT:
        return bool(tools & set(DATE_TOOLS))
    return not _VERDICT.search(text) or bool(tools)


def _keep(item: Any, results: dict[str, ToolResult]) -> ReasonOut | None:
    if not isinstance(item, dict):
        return None
    text, ids = str(item.get("text") or "").strip(), item.get("cited_result_ids") or []
    if len(text) < MIN_CHARS or not ids or _ADVICE.search(text) or any(i not in results for i in ids):
        return None
    cited = list(dict.fromkeys(ids))
    if not _backed(str(item.get("kind")), text, [results[i] for i in cited]):
        return None
    return ReasonOut(text=us_text(text), cited=cited, source_ids=_sources(cited, results))  # dates shown US style after the checks


def verify(data: dict[str, Any], results: dict[str, ToolResult]) -> tuple[str, list[ReasonOut], int] | None:
    """The kept reasons and the count dropped, or None when nothing is left to show."""
    items = data.get("reasons") or []
    kept = [r for r in (_keep(i, results) for i in items) if r is not None]
    summary = str(data.get("summary") or "").strip()
    if not kept or len(summary) < MIN_CHARS or _ADVICE.search(summary):
        return None
    return us_text(summary), kept, len(items) - len(kept)


def _checklist_reasons(result: ToolResult) -> list[ReasonOut]:
    out = []
    for c in result.data:
        if c["status"] == "SATISFIED":
            continue
        why = "No file has been uploaded." if c["status"] == "MISSING" else "Files exist but none is usable. " + " ".join(
            (r["reason"] or r["outcome"]).rstrip(".") + "." for r in c["reasons"])
        out.append(ReasonOut(text=f"{c['label']}: {why}", cited=[result.id], source_ids=[r["upload_id"] for r in c["reasons"]]))
    return out


def _conflict_reasons(result: ToolResult) -> list[ReasonOut]:
    out = []
    for f in result.data:
        if f["state"] != "CONFLICT":
            continue
        said = ", ".join(f'{s["source_id"]} says "{s["value"]}"' for s in f["sources"])
        out.append(ReasonOut(text=f"Sources disagree on {f['label'].lower()}: {said}.", cited=[result.id],
                             source_ids=[s["source_id"] for s in f["sources"]]))
    return out


COVERED = ("DUPLICATE", "FACT_CONFLICT", "MISSING_DOCUMENT")


def _exception_reasons(result: ToolResult) -> list[ReasonOut]:
    return [ReasonOut(text=f"{i['title']}. {i['reason']}", cited=[result.id], source_ids=i["source_ids"])
            for i in result.data if i["type"] not in COVERED]  # fmt: skip


def fallback(box: Toolbox, question: str) -> InvestigationOut:
    """The answer from the checklist, the conflicts and the exceptions alone. No model is called."""
    checklist = box.call("get_checklist", {})
    facts = box.call("list_facts_and_conflicts", {})
    found = box.call("get_exceptions", {})
    reasons = _checklist_reasons(checklist) + _conflict_reasons(facts) + _exception_reasons(found)
    summary = f"{len(reasons)} item{'s' if len(reasons) != 1 else ''} block or hold up this case." if reasons else NOTHING
    return InvestigationOut(question=question, answer=summary, reasons=reasons, trace=trace_of(box), origin="FALLBACK")
