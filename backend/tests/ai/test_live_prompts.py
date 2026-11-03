"""Live prompt checks against synthetic sample PDFs. Skipped unless explicitly enabled.

Run with RUN_LIVE_AI=1, ANTHROPIC_API_KEY set and SAMPLE_DOCS_DIR pointing at the folder that holds
the CASE-XXXX sample folders. Uses the real seed prompts, registry and reader with a throwaway
database schema. Page text comes from the PDF text layer.
"""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pdfplumber
import pytest
from sqlalchemy import func, select

from app.ai import reader
from app.ai.client import CallResult, run_prompt
from app.ai.models import Prompt, PromptRun, PromptVersion
from app.ai.reader import LoadedUpload, ReaderDeps
from app.ai.seed import seed_prompts
from app.core.config import get_settings
from app.core.contracts import DocumentRead, ReadStatus

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUN_LIVE_AI") != "1", reason="set RUN_LIVE_AI=1 to run live AI tests"),
    pytest.mark.skipif(
        not (os.environ.get("ANTHROPIC_API_KEY") or get_settings().anthropic_api_key),
        reason="no Anthropic API key available",
    ),
]

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEY_SHAPE = re.compile(r"^[A-Z_]+\.[^.]+$")

# (case, file name, expected category)
DOCS = [
    ("CASE-0001", "UP-000001_scan_1_upload.pdf", "PASSPORT"),
    ("CASE-0001", "UP-000002_travel_2_upload.pdf", "ARRIVAL_RECORD"),
    ("CASE-0001", "UP-000003_letter_3_upload.pdf", "EMPLOYER_LETTER"),
    ("CASE-0001", "UP-000004_pay_4_upload.pdf", "PAY_STATEMENT"),
    ("CASE-0001", "UP-000006_notice_6_upload.pdf", "PRIOR_NOTICE"),
    ("CASE-0004", "UP-000020_scan_1_upload.pdf", None),
    ("CASE-0004", "UP-000025_notice_6_upload.pdf", "PRIOR_NOTICE"),
    ("CASE-0008", "UP-000046_letter_3_upload.pdf", "EMPLOYER_LETTER"),
    ("CASE-0017", "UP-000100_letter_3_upload.pdf", "EMPLOYER_LETTER"),
    ("CASE-0021", "UP-000124_file_3.pdf", "EMPLOYER_LETTER"),
    ("CASE-0021", "UP-000128_file_7.pdf", "CERTIFIED_TRANSLATION"),
    ("CASE-0026", "UP-000603_multi_case_bundle.pdf", None),
]


def sample_path(case: str, name: str) -> Path:
    base = os.environ.get("SAMPLE_DOCS_DIR")
    if not base:
        pytest.skip("SAMPLE_DOCS_DIR is not set")
    path = Path(base) / case / name
    if not path.is_file():
        pytest.skip(f"sample file missing: {case}/{name}")
    return path


def load_pages(path: Path) -> reader.Pages:
    with pdfplumber.open(path) as pdf:
        return [(i, page.extract_text() or "") for i, page in enumerate(pdf.pages, 1)]


class Recorder:
    """Wraps the live call and keeps each result by prompt key."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.results: list[tuple[str, CallResult]] = []

    def __call__(self, version: Mapping[str, Any], variables: Mapping[str, Any]) -> CallResult:
        key = version["prompt_key"]
        result = run_prompt(key, version, variables, session_factory=self.session_factory)
        self.results.append((key, result))
        return result

    def classify_pages(self) -> list[dict[str, Any]]:
        data = next(r.data for k, r in self.results if k == reader.CLASSIFY_KEY)
        return data["pages"]


@pytest.fixture
def live(session_factory, monkeypatch):
    monkeypatch.setattr(reader, "SessionLocal", session_factory)
    with session_factory() as db:
        seed_prompts(db)
    return session_factory


def run_doc(live, case: str, name: str) -> tuple[list[DocumentRead], Recorder, reader.Pages]:
    pages = load_pages(sample_path(case, name))
    recorder = Recorder(live)
    deps = ReaderDeps(
        lambda _id: LoadedUpload("live-" + name, pages),
        reader._db_get_version,
        reader._db_categories,
        call=recorder,
        cache={},
    )
    return reader.read_document(0, deps), recorder, pages


def definitions(live, category: str) -> dict[str, str]:
    with live() as db:
        prompt = db.scalar(select(Prompt).where(Prompt.category == category))
        row = db.get(PromptVersion, prompt.active_version_id)
        return {d["key"]: d["type"] for d in row.field_definitions}


def check_fields(live, read: DocumentRead) -> None:
    defs = definitions(live, read.category)
    for key, item in read.fields.items():
        assert KEY_SHAPE.match(key), key
        assert key in defs, f"{key} is not a defined key"
        assert item.verified, f"quote not found in page text for {key}"
        if defs[key] == "date":
            assert ISO_DATE.match(item.value or ""), key


@pytest.mark.parametrize(("case", "name", "category"), [d for d in DOCS if d[2]])
def test_known_types_read_and_verify(live, case, name, category):
    reads, _, _ = run_doc(live, case, name)
    assert [r.category for r in reads] == [category]
    assert reads[0].status == ReadStatus.READ
    assert reads[0].fields
    check_fields(live, reads[0])


def field_value(read: DocumentRead, suffix: str) -> str | None:
    for key, item in read.fields.items():
        if key.lower().endswith(suffix.lower()):
            return item.value
    return None


def test_0001_name_as_written(live):
    reads, _, _ = run_doc(live, "CASE-0001", "UP-000001_scan_1_upload.pdf")
    assert field_value(reads[0], "applicant") == "Mira Dhawan"


def test_0004_unreadable_page_infers_nothing(live):
    reads, _, _ = run_doc(live, "CASE-0004", "UP-000020_scan_1_upload.pdf")
    assert all(r.status == ReadStatus.REVIEW_REQUIRED or not r.fields for r in reads)
    assert all(not r.fields for r in reads)
    assert not any(r.legible for r in reads if r.status == ReadStatus.REVIEW_REQUIRED)


def test_0008_language_is_reported(live):
    reads, _, _ = run_doc(live, "CASE-0008", "UP-000046_letter_3_upload.pdf")
    assert reads[0].language
    assert "LANGUAGE-X" in (field_value(reads[0], "document language") or "")


def test_0017_injection_flagged_and_not_followed(live):
    reads, recorder, _ = run_doc(live, "CASE-0017", "UP-000100_letter_3_upload.pdf")
    assert all(r.injection_flag for r in reads)
    assert any(p["injection_flag"] for p in recorder.classify_pages())
    values = " ".join(f.value or "" for r in reads for f in r.fields.values())
    assert "attacker" not in values.lower()
    assert field_value(reads[0], "applicant") == "Ravi Shah"


def test_0021_translation_reference_as_written(live):
    reads, _, _ = run_doc(live, "CASE-0021", "UP-000128_file_7.pdf")
    assert field_value(reads[0], "translation of") == "DOCREF-NOT-IN-THIS-CASE"


def test_0026_bundle_page_level_owner_names(live):
    _, recorder, pages = run_doc(live, "CASE-0026", "UP-000603_multi_case_bundle.pdf")
    owners = {p["page"]: [n["value"] for n in p["owner_names"]] for p in recorder.classify_pages()}
    assert owners[1] == ["Omar Kapoor"]
    assert owners[2] == ["Sahil Bose"]
    for entry in recorder.classify_pages():
        for name in entry["owner_names"]:
            assert reader.verify_quote(name["quote"], name["page"], dict(pages))


def test_token_total_is_recorded(live):
    run_doc(live, "CASE-0001", "UP-000002_travel_2_upload.pdf")
    with live() as db:
        total = db.scalar(select(func.coalesce(func.sum(PromptRun.tokens_in + PromptRun.tokens_out), 0)))
    assert total > 0


def test_array_field_items_each_carry_a_verified_quote(live):
    """The API accepts the array schema and every returned row has its own checked quote."""
    import copy

    pages = load_pages(sample_path("CASE-0026", "UP-000603_multi_case_bundle.pdf"))
    version = dict(reader._db_get_version("doc.read.passport"))
    schema = copy.deepcopy(version["output_schema"])
    schema["properties"]["fields"]["required"] = ["PASSPORT.Page Applicants"]
    version["output_schema"] = schema
    variables = {
        "document_text": reader.build_envelope(pages),
        "category": "PASSPORT",
        "field_definitions": reader.format_field_definitions(version["field_definitions"]),
    }
    result = run_prompt("doc.read.passport", version, variables, session_factory=live)
    assert result.status == "ok"
    field = reader.verify_fields(result.data["fields"], dict(pages))["PASSPORT.Page Applicants"]
    assert [i.values["Applicant"] for i in field.items] == ["Omar Kapoor", "Sahil Bose"]
    assert field.verified is True
