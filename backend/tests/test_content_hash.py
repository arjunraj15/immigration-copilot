from app.ingest.content_hash import canonical_content_hash

DOC = {
    "Applicant": "Rohan Anand-3",
    "Reference": "DOCREF-000599",
    "Pay Period": "2026-08",
    "Net Pay": "USD 3,250.00",
}


def test_field_order_does_not_matter() -> None:
    reordered = dict(reversed(list(DOC.items())))
    assert canonical_content_hash(DOC) == canonical_content_hash(reordered)


def test_key_case_and_whitespace_are_normalized() -> None:
    messy = {"  applicant ": "Rohan   Anand-3 ", "REFERENCE": "DOCREF-000599",
             "pay  period": "2026-08", "net pay": "USD  3,250.00"}
    assert canonical_content_hash(DOC) == canonical_content_hash(messy)


def test_changed_amount_or_reference_changes_hash() -> None:
    assert canonical_content_hash(DOC) != canonical_content_hash({**DOC, "Net Pay": "USD 3,500.00"})
    assert canonical_content_hash(DOC) != canonical_content_hash({**DOC, "Reference": "DOCREF-000600"})


def test_excluded_keys_are_ignored() -> None:
    a = {**DOC, "Filename": "a.pdf"}
    b = {**DOC, "Filename": "b.pdf"}
    assert canonical_content_hash(a) != canonical_content_hash(b)
    assert canonical_content_hash(a, exclude_keys=["filename"]) == canonical_content_hash(b, exclude_keys=["FILENAME"])


def test_nested_values_are_normalized() -> None:
    a = {"items": [{"B": "x  y", "a": 1}]}
    b = {"items": [{"a": 1, "b": "x y"}]}
    assert canonical_content_hash(a) == canonical_content_hash(b)
