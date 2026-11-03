"""Three layer duplicate check against real PDFs from 06_synthetic_documents.

Skipped when the starter kit or pdftotext is not available. The kit is read only.
"""
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.ingest.duplicate_check import DocumentFingerprint, DuplicateVerdict, check_duplicate

_REPO_KIT = Path(__file__).resolve().parents[2] / "project_requirmnt" / "Galaxy_Immigration_starter-kit"
_FIELD = re.compile(r"^([A-Za-z][A-Za-z /]+?):\s{2,}(.+)$")


def _kit_dir() -> Path:
    configured = Path(get_settings().starter_kit_dir)
    return configured if configured.is_dir() else _REPO_KIT


DOCS = _kit_dir() / "06_synthetic_documents"

pytestmark = pytest.mark.skipif(
    not DOCS.is_dir() or shutil.which("pdftotext") is None,
    reason="starter kit or pdftotext not available",
)


def _category(title: str) -> str:
    return "PAY_STATEMENT" if title.startswith("Pay statement") else title.split(",")[0]


def _fingerprint(case_id: str, name: str) -> DocumentFingerprint:
    path = DOCS / case_id / name
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fields = {m.group(1): m.group(2) for m in map(_FIELD.match, lines) if m}
    return DocumentFingerprint(
        doc_id=name.split("_")[0],
        case_id=case_id,
        category=_category(lines[1]),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        fields=fields,
        text=text,
    )


PASSPORT_A = "UP-000001_scan_1_upload.pdf"
PASSPORT_B = "UP-000007_scan_7_upload.pdf"
PAY_AUG = "UP-000004_pay_4_upload.pdf"
PAY_SEP = "UP-000005_pay_5_upload.pdf"


def test_kit_has_one_exact_file_duplicate_pair() -> None:
    a, b = _fingerprint("CASE-0001", PASSPORT_A), _fingerprint("CASE-0001", PASSPORT_B)
    assert a.sha256 == b.sha256
    assert a.category == b.category


def test_layer1_same_bytes_in_same_case() -> None:
    new, old = _fingerprint("CASE-0001", PASSPORT_B), _fingerprint("CASE-0001", PASSPORT_A)
    result = check_duplicate(new, [old])
    assert result.verdict == DuplicateVerdict.EXACT_FILE
    assert result.matched_doc_id == old.doc_id


def test_layer2_regenerated_file_with_same_content() -> None:
    old = _fingerprint("CASE-0001", PASSPORT_A)
    noisy_fields = {f"  {k.upper()} ": f"{v}!!" for k, v in reversed(list(old.fields.items()))}
    regenerated = DocumentFingerprint(
        "UP-NEW", old.case_id, old.category, "different-bytes", noisy_fields, "other text"
    )
    result = check_duplicate(regenerated, [old])
    assert result.verdict == DuplicateVerdict.EXACT_CONTENT


def test_layer3_near_copy_of_passport_escalates_to_human() -> None:
    old = _fingerprint("CASE-0001", PASSPORT_A)
    near = DocumentFingerprint(
        "UP-NEW", old.case_id, old.category, "different-bytes",
        {**old.fields, "Document Identifier": "SYN-P-00002"}, old.text.replace("SYN-P-00001", "SYN-P-00002"),
    )
    result = check_duplicate(near, [old])
    assert result.verdict == DuplicateVerdict.NEEDS_HUMAN_REVIEW
    assert result.score >= get_settings().duplicate_review_threshold
    assert result.matched_doc_id == old.doc_id


def test_sibling_pay_statements_skip_similarity() -> None:
    aug, sep = _fingerprint("CASE-0001", PAY_AUG), _fingerprint("CASE-0001", PAY_SEP)
    assert aug.sha256 != sep.sha256
    assert check_duplicate(sep, [aug]).verdict == DuplicateVerdict.DISTINCT


def test_different_category_passes_all_layers() -> None:
    passport, pay = _fingerprint("CASE-0001", PASSPORT_A), _fingerprint("CASE-0001", PAY_AUG)
    assert passport.category != pay.category
    assert check_duplicate(pay, [passport]).verdict == DuplicateVerdict.DISTINCT


def test_same_category_in_another_case_is_ignored() -> None:
    pay_case1 = _fingerprint("CASE-0001", PAY_AUG)
    pay_case2 = _fingerprint("CASE-0002", "UP-000011_pay_4_upload.pdf")
    assert pay_case1.category == pay_case2.category
    assert check_duplicate(pay_case2, [pay_case1]).verdict == DuplicateVerdict.DISTINCT
