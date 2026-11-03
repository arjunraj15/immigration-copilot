from app.ingest.content_hash import canonical_content_hash
from app.ingest.duplicate_check import (
    DocumentFingerprint,
    DuplicateVerdict,
    check_duplicate,
    similarity_score,
)

DOC = {"Applicant": "Rohan Anand-3", "Reference": "DOCREF-000599", "Net Pay": "USD 3,250.00"}
TEXT = "Pay slip Rohan Anand-3 reference DOCREF-000599 net pay USD 3,250.00 for August 2026"


def fp(doc_id="new", case_id="C1", category="letter", sha="a", fields=None, text=TEXT) -> DocumentFingerprint:
    return DocumentFingerprint(doc_id, case_id, category, sha, fields if fields is not None else DOC, text)


OLD = fp("old", sha="b")


def test_symbols_do_not_change_hash() -> None:
    other = {"applicant": "Rohan  Anand3!", "REFERENCE": "DOCREF000599", "net pay": "USD 325000"}
    assert canonical_content_hash(DOC) == canonical_content_hash(other)


def test_same_sha_is_exact_file() -> None:
    result = check_duplicate(fp(sha="b", fields={"x": "1"}, text="zzz"), [OLD])
    assert result.verdict == DuplicateVerdict.EXACT_FILE
    assert result.matched_doc_id == "old"


def test_same_fields_different_bytes_is_exact_content() -> None:
    reordered = dict(reversed(list(DOC.items())))
    result = check_duplicate(fp(fields=reordered, text="zzz"), [OLD])
    assert result.verdict == DuplicateVerdict.EXACT_CONTENT


def test_similar_text_escalates_to_human() -> None:
    new = fp(fields={**DOC, "Net Pay": "USD 3,251.00"}, text=TEXT.replace("3,250", "3,251"))
    result = check_duplicate(new, [OLD])
    assert result.verdict == DuplicateVerdict.NEEDS_HUMAN_REVIEW
    assert result.score >= 90
    assert result.matched_doc_id == "old"


def test_different_document_passes_all_layers() -> None:
    new = fp(fields={"Applicant": "Someone Else"}, text="Passport issued to Someone Else expires 2031")
    assert check_duplicate(new, [OLD]).verdict == DuplicateVerdict.DISTINCT


def test_other_case_is_never_compared() -> None:
    other_case = fp("old", case_id="C2", sha="a")
    assert check_duplicate(fp(), [other_case]).verdict == DuplicateVerdict.DISTINCT


def test_other_category_skips_content_layers() -> None:
    other_category = fp("old", category="passport", sha="b")
    assert check_duplicate(fp(), [other_category]).verdict == DuplicateVerdict.DISTINCT


def test_token_order_does_not_matter() -> None:
    assert similarity_score("alpha beta gamma", "gamma alpha beta") == 100.0


def test_threshold_is_overridable() -> None:
    new = fp(fields={**DOC, "Net Pay": "USD 9"}, text=TEXT.replace("3,250", "9"))
    assert check_duplicate(new, [OLD], review_threshold=99.9).verdict == DuplicateVerdict.DISTINCT


def test_same_sha_matches_across_categories() -> None:
    other_category = fp("old", category="passport", sha="a")
    result = check_duplicate(fp(), [other_category])
    assert result.verdict == DuplicateVerdict.EXACT_FILE


def test_same_sha_in_another_case_is_ignored() -> None:
    other_case = fp("old", case_id="C2", category="passport", sha="a")
    assert check_duplicate(fp(), [other_case]).verdict == DuplicateVerdict.DISTINCT


def test_pay_statement_skips_similarity() -> None:
    old = fp("old", category="PAY_STATEMENT", sha="b")
    new = fp(category="PAY_STATEMENT", fields={**DOC, "Net Pay": "USD 3,251.00"}, text=TEXT.replace("3,250", "3,251"))
    assert check_duplicate(new, [old]).verdict == DuplicateVerdict.DISTINCT


def test_pay_statement_still_caught_by_layers_1_and_2() -> None:
    old = fp("old", category="PAY_STATEMENT", sha="b")
    assert check_duplicate(fp(category="PAY_STATEMENT", sha="b"), [old]).verdict == DuplicateVerdict.EXACT_FILE
    assert check_duplicate(fp(category="PAY_STATEMENT"), [old]).verdict == DuplicateVerdict.EXACT_CONTENT
