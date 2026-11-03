"""Three layer duplicate upload detection.

A new file is only compared with earlier files of the same case. It must pass
three layers in order:

1. Raw file sha256 match is an exact duplicate. Category does not matter, since
   identical bytes are the same file whatever it was classified as.
2. Canonical content hash match (sorted, symbol-free JSON of extracted fields)
   is an exact content duplicate. Only same category files are compared.
3. A rapidfuzz token_sort_ratio at or above the review threshold escalates to a
   human. Only same category files are compared. Categories listed in
   `duplicate_similarity_excluded_categories` (pay statements) skip this layer,
   because monthly statements of one person look alike by design.

A file that triggers none of them is distinct. Nothing is merged automatically.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from rapidfuzz import fuzz

from app.core.config import get_settings
from app.ingest.content_hash import canonical_content_hash, normalize_text


class DuplicateVerdict(StrEnum):
    EXACT_FILE = "EXACT_FILE"
    EXACT_CONTENT = "EXACT_CONTENT"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    DISTINCT = "DISTINCT"


@dataclass(frozen=True)
class DocumentFingerprint:
    doc_id: str
    case_id: str
    category: str
    sha256: str
    fields: Mapping[str, Any]
    text: str


@dataclass(frozen=True)
class DuplicateResult:
    verdict: DuplicateVerdict
    score: float
    reason: str
    matched_doc_id: str | None = None


def similarity_score(text_a: str, text_b: str) -> float:
    """Token sort ratio from 0 to 100 on symbol-free, casefolded text."""
    return fuzz.token_sort_ratio(
        normalize_text(text_a).casefold(), normalize_text(text_b).casefold()
    )


def _best_fuzzy_match(new: DocumentFingerprint, candidates: list[DocumentFingerprint]) -> tuple[float, str | None]:
    best_score, best_id = 0.0, None
    for old in candidates:
        score = similarity_score(new.text, old.text)
        if score > best_score:
            best_score, best_id = score, old.doc_id
    return best_score, best_id


def check_duplicate(
    new: DocumentFingerprint,
    existing: Iterable[DocumentFingerprint],
    review_threshold: float | None = None,
) -> DuplicateResult:
    """Run the three layers for `new` against earlier documents."""
    in_case = [old for old in existing if old.case_id == new.case_id and old.doc_id != new.doc_id]
    for old in in_case:
        if old.sha256 == new.sha256:
            return DuplicateResult(DuplicateVerdict.EXACT_FILE, 100.0, "File sha256 matches.", old.doc_id)
    candidates = [old for old in in_case if old.category == new.category]
    new_hash = canonical_content_hash(new.fields)
    for old in candidates:
        if canonical_content_hash(old.fields) == new_hash:
            return DuplicateResult(
                DuplicateVerdict.EXACT_CONTENT, 100.0, "Canonical content hash matches.", old.doc_id
            )
    settings = get_settings()
    if new.category.casefold() in {c.casefold() for c in settings.duplicate_similarity_excluded_categories}:
        reason = "Passed layers 1 and 2. Similarity is skipped for this category."
        return DuplicateResult(DuplicateVerdict.DISTINCT, 0.0, reason)
    threshold = review_threshold if review_threshold is not None else settings.duplicate_review_threshold
    score, matched_id = _best_fuzzy_match(new, candidates)
    if score >= threshold:
        return DuplicateResult(
            DuplicateVerdict.NEEDS_HUMAN_REVIEW,
            score,
            f"Text similarity {score:.1f} is at or above {threshold:.1f}. A person must decide.",
            matched_id,
        )
    return DuplicateResult(DuplicateVerdict.DISTINCT, score, "Passed all three layers.")
