from types import SimpleNamespace

from app.cases.exceptions import reference_items


def row(upload_id: str, serials: list[str], outcome: str = "USABLE"):
    return SimpleNamespace(upload_id=upload_id, outcome=outcome, flags={"ref_serials": serials} if serials else {})


def test_reference_numbers_of_one_set_raise_nothing():
    rows = [row("UP-1", ["00001"]), row("UP-2", ["00001"]), row("UP-3", [])]
    assert reference_items(rows, "CASE-0001", "Mira Dhawan") == []


def test_two_sets_in_one_case_are_flagged_for_a_person_to_look():
    items = reference_items([row("UP-1", ["00001"]), row("UP-2", ["00007"])], "CASE-0001", "Mira Dhawan")
    assert len(items) == 1 and items[0].source_ids == ["UP-1", "UP-2"] and items[0].severity == "MEDIUM"
    assert "00001" in items[0].reason and "00007" in items[0].reason


def test_an_unusable_file_does_not_count():
    assert reference_items([row("UP-1", ["00001"]), row("UP-2", ["00007"], outcome="QUARANTINED")], "CASE-0001", "Mira Dhawan") == []
