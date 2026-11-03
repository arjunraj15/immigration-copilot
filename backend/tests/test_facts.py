import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.cases import form_draft
from app.cases.form_pdf import render_form_pdf
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.facts import engine, explain, normalize, sources
from app.main import app
from tests.conftest import make_case

client = TestClient(app)
OPS, LEGAL = "OPS-91", "LEGAL-91"


def call(method: str, path: str, actor: str = OPS, **kwargs):
    return client.request(method, path, headers={"X-Actor": actor}, **kwargs)


def new_case(name: str = "Mira Dhawan") -> str:
    case_id = f"CASE-T{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        make_case(db, case_id, name=name)
    return case_id


def changed(case_id: str) -> None:
    """The event hook a real change runs after it is saved. Reads never rebuild the facts."""
    with SessionLocal() as db:
        engine.recompute(db, case_id)


def add_profile(case_id: str, field: str, value: str) -> str:
    source_id = f"PROFILE-{case_id}-{field}"
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO profile_fields (source_id, case_id, field_name, verified_value, verification_state, verified_at, "
                 "verified_by) VALUES (:s, :c, :f, :v, 'HUMAN_VERIFIED', now(), 'OPS-91') "
                 "ON CONFLICT (source_id) DO UPDATE SET verified_value = :v"),
            {"s": source_id, "c": case_id, "f": field, "v": value},
        )  # fmt: skip
        db.commit()
    changed(case_id)
    return source_id


def add_claim(case_id: str, source_id: str, field: str, value: str) -> None:
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO claims (case_id, source_id, field_name, value, quote, page) VALUES (:c, :s, :f, :v, :v, 1)"),
            {"c": case_id, "s": source_id, "f": field, "v": value},
        )
        db.commit()
    changed(case_id)


def add_doc(case_id: str, key: str, value: str, *, outcome: str = "USABLE", verified: bool = True, image: bool = False) -> str:
    upload_id = f"UP-T{uuid.uuid4().hex[:8].upper()}"
    fields = {key: {"value": value, "quote": value, "page": 1, "verified": verified, "from_image": image}}
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, file_size_bytes, "
                 "sha256, uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label, outcome) VALUES "
                 "(:u, :c, 'APP_STORAGE', :u, 'a.pdf', 'application/pdf', 1, :h, now(), 'CLIENT', 'TEST', 'UNSPECIFIED', 'v1', :o)"),
            {"u": upload_id, "c": case_id, "h": uuid.uuid4().hex + uuid.uuid4().hex, "o": outcome},
        )  # fmt: skip
        db.execute(
            text("INSERT INTO document_reads (upload_id, category, status, extracted) VALUES (:u, 'PASSPORT', 'READ', CAST(:x AS jsonb))"),
            {"u": upload_id, "x": json.dumps({"fields": fields, "image_pages": [1] if image else []})},
        )  # fmt: skip
        db.commit()
    changed(case_id)
    return upload_id


def facts(case_id: str, actor: str = OPS) -> dict:
    body = call("GET", f"/api/cases/{case_id}/facts", actor).json()
    return {f["field"]: f for f in body["fields"]}


def audit_actions(case_id: str) -> list[tuple[str, str]]:
    with SessionLocal() as db:
        rows = db.execute(text("SELECT action, outcome FROM audit_log WHERE case_id = :c ORDER BY seq"), {"c": case_id}).all()
    return [(r.action, r.outcome) for r in rows]


def name_conflict() -> tuple[str, str, str]:
    """The CASE-0001 pattern. The call note says Dawan, the passport and the profile say Dhawan."""
    case_id = new_case("Mira Dhawan")
    passport = add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    add_claim(case_id, "Z-9001", "full_name", "Mira Dawan")
    return case_id, passport, "Z-9001"


# ---------------------------------------------------------------- states


def test_agree_when_every_source_has_the_same_value():
    case_id = new_case("Mira Dhawan")
    add_doc(case_id, "PASSPORT.Applicant", "Mira  Dhawan")
    state = facts(case_id)["full_name"]
    assert state["state"] == "AGREE" and state["severity"] == "high"
    assert state["value"] == "Mira Dhawan" and len(state["sources"]) == 2


def test_name_conflict_lists_three_sources_and_no_value():
    case_id, passport, note = name_conflict()
    state = facts(case_id)["full_name"]
    assert state["state"] == "CONFLICT" and state["value"] is None
    ids = {s["source_id"] for s in state["sources"]}
    assert ids == {passport, note, f"PROFILE-{case_id}-full_name"}
    odd = [s["source_id"] for s in state["sources"] if s["odd"]]
    assert odd == [note]
    assert {s["trust"] for s in state["sources"] if s["source_id"] == note} == {"CLAIM"}
    assert state["trust"] == {"evidence": 2, "claim": 1}


def test_claims_only_is_unverified_and_never_evidence():
    case_id = new_case()
    add_claim(case_id, "Z-9002", "mailing_address", "5 Invented Way")
    add_claim(case_id, "MSG-9002-1", "mailing_address", "5 Invented Way")
    state = facts(case_id)["mailing_address"]
    assert state["state"] == "UNVERIFIED" and state["value"] is None and state["note"] == "Needs a document"
    assert {s["trust"] for s in state["sources"]} == {"CLAIM"}
    assert {s["source_kind"] for s in state["sources"]} == {"INTAKE", "MESSAGE"}
    assert sources.make("full_name", "A B", "INTAKE", "Z-1", trust="EVIDENCE", verified=True).trust == "CLAIM"


def test_the_fact_table_refuses_a_claim_as_evidence():
    case_id = new_case()
    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                text("INSERT INTO facts (case_id, field, value, normalized_value, source_kind, source_id, trust) "
                     "VALUES (:c, 'full_name', 'x', 'x', 'MESSAGE', 'MSG-1', 'EVIDENCE')"),
                {"c": case_id},
            )  # fmt: skip
        db.rollback()


def test_a_scanned_page_read_is_a_claim_and_is_not_verified():
    case_id = new_case()
    add_doc(case_id, "PASSPORT.Document Identifier", "P1234567", outcome="NEEDS_HUMAN_REVIEW", verified=False, image=True)
    state = facts(case_id)["passport_number"]
    assert state["state"] == "UNVERIFIED"
    assert state["sources"][0]["trust"] == "CLAIM" and state["sources"][0]["from_image"] is True


def test_single_document_source_and_no_source():
    case_id = new_case()
    add_doc(case_id, "PASSPORT.Expires", "2030-01-31")
    found = facts(case_id)
    assert found["passport_expiration"]["state"] == "SINGLE_SOURCE_EVIDENCE" and found["passport_expiration"]["value"] == "2030-01-31"
    assert found["employer_name"]["state"] == "NO_SOURCE"


def test_an_unusable_or_foreign_upload_adds_nothing():
    case_id = new_case()
    add_doc(case_id, "PASSPORT.Expires", "2030-01-31", outcome="QUARANTINED")
    assert facts(case_id)["passport_expiration"]["state"] == "NO_SOURCE"


def test_normalization_of_dates_and_text():
    assert normalize.normalize("date_of_birth", "April 8, 1982") == "1982-04-08"
    assert normalize.normalize("date_of_birth", "8 Apr 1982") == "1982-04-08"
    assert normalize.normalize("date_of_birth", "04/13/1982") == "1982-04-13"
    assert normalize.normalize("date_of_birth", "13/04/1982") == "1982-04-13"
    assert normalize.normalize("date_of_birth", "04/05/1982") == "04/05/1982"
    assert normalize.normalize("date_of_birth", "1982-02-30") == "1982-02-30"
    assert normalize.normalize("full_name", "  Mira   Dhawan ") == "Mira Dhawan"
    assert normalize.normalize("passport_number", "P 1234 5678") == "P 1234 5678"
    assert normalize.normalize("mailing_address", "May 5, 2020") == "May 5, 2020"
    assert normalize.compare_key("Mira  DHAWAN") == normalize.compare_key("mira dhawan")


def test_a_date_written_two_ways_still_agrees():
    case_id = new_case()
    add_profile(case_id, "date_of_birth", "1982-04-08")
    add_doc(case_id, "PASSPORT.Date of Birth", "1982-04-08")
    add_claim(case_id, "Z-9003", "date_of_birth", "April 8, 1982")
    assert facts(case_id)["date_of_birth"]["state"] == "AGREE"


# ---------------------------------------------------------------- audit and review requests


def test_conflict_is_opened_once_and_a_review_request_is_open():
    case_id, _, _ = name_conflict()
    for _ in range(3):
        facts(case_id)
    actions = [a for a, _ in audit_actions(case_id)]
    assert actions.count("CONFLICT_OPENED") == 1 and actions.count("REVIEW_REQUESTED") == 1
    with SessionLocal() as db:
        row = db.execute(text("SELECT status FROM review_requests WHERE case_id = :c AND field = 'full_name'"), {"c": case_id}).one()
        count = db.scalar(text("SELECT count(*) FROM facts WHERE case_id = :c AND field = 'full_name'"), {"c": case_id})
    assert row.status == "OPEN" and count == 3


def test_changing_a_profile_value_opens_a_new_conflict():
    case_id = new_case()
    add_claim(case_id, "Z-9004", "employer_name", "Fictional Employer 01 LLC")
    add_profile(case_id, "employer_name", "Fictional Employer 01 LLC")
    add_doc(case_id, "EMPLOYER_LETTER.Employer", "Fictional Employer 01 LLC")
    assert facts(case_id)["employer_name"]["state"] == "AGREE"
    add_profile(case_id, "employer_name", "Another Employer Inc")
    assert facts(case_id)["employer_name"]["state"] == "CONFLICT"


# ---------------------------------------------------------------- suggest


def test_suggest_only_from_source_values():
    case_id, _, _ = name_conflict()
    path = f"/api/cases/{case_id}/conflicts/full_name/suggest"
    bad = call("POST", path, json={"value": "Someone Else", "reason": "Looks right"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "VALUE_NOT_A_SOURCE"
    ok = call("POST", path, json={"value": "mira dhawan", "reason": "Passport shows it"})
    assert ok.status_code == 200 and ok.json()["suggested_value"] == "Mira Dhawan"
    held = call("POST", path, json={"leave_to_attorney": True, "reason": "Not sure"})
    assert held.json()["suggested_value"] is None and held.json()["leave_to_attorney"] is True
    assert call("POST", path, json={"value": "Mira Dhawan", "reason": " "}).status_code == 400
    assert facts(case_id)["full_name"]["state"] == "CONFLICT"
    newest = call("GET", f"/api/cases/{case_id}/conflicts").json()["conflicts"][0]["suggestion"]
    assert newest["leave_to_attorney"] is True
    assert ("CONFLICT_SUGGESTED", "ALLOWED") in audit_actions(case_id)


def test_only_the_assigned_ops_user_suggests():
    case_id, _, _ = name_conflict()
    path = f"/api/cases/{case_id}/conflicts/full_name/suggest"
    body = {"value": "Mira Dhawan", "reason": "x"}
    assert call("POST", path, LEGAL, json=body).status_code == 403
    assert call("POST", path, "OPS-92", json=body).status_code == 403
    assert ("CONFLICT_SUGGESTED", "DENIED") in audit_actions(case_id)


# ---------------------------------------------------------------- resolve


def test_resolve_permissions_and_decision():
    case_id, passport, note = name_conflict()
    path = f"/api/cases/{case_id}/conflicts/full_name/resolve"
    body = {"value": "Mira Dhawan"}
    assert call("POST", path, OPS, json=body).status_code == 403
    assert call("POST", path, "LEGAL-92", json=body).status_code == 403
    assert facts(case_id)["full_name"]["state"] == "CONFLICT"
    denied = [a for a in audit_actions(case_id) if a[1] == "DENIED"]
    assert ("CONFLICT_RESOLVED", "DENIED") in denied and ("CASE_ACCESS", "DENIED") in denied
    done = call("POST", path, LEGAL, json=body)
    assert done.status_code == 200
    state = done.json()
    assert state["state"] == "HUMAN_DECIDED" and state["value"] == "Mira Dhawan"
    assert state["decided_by"]["reviewer_id"] == LEGAL and state["decided_by"]["source_ref"] in {passport, f"PROFILE-{case_id}-full_name"}
    assert ("CONFLICT_RESOLVED", "ALLOWED") in audit_actions(case_id)
    with SessionLocal() as db:
        request = db.scalar(text("SELECT status FROM review_requests WHERE case_id = :c AND field = 'full_name'"), {"c": case_id})
    assert request == "RESOLVED"


def test_resolve_is_idempotent_and_survives_a_rebuild_with_new_sources():
    case_id, _, _ = name_conflict()
    path = f"/api/cases/{case_id}/conflicts/full_name/resolve"
    call("POST", path, LEGAL, json={"value": "Mira Dhawan"})
    again = call("POST", path, LEGAL, json={"value": "Mira Dhawan"})
    assert again.status_code == 200
    with SessionLocal() as db:
        rows = db.scalar(text("SELECT count(*) FROM review_decisions WHERE case_id = :c AND field_name = 'full_name'"), {"c": case_id})
    assert rows == 1
    add_claim(case_id, "MSG-9005-1", "full_name", "Mira Dawan Jr")
    state = facts(case_id)["full_name"]
    assert state["state"] == "HUMAN_DECIDED" and state["value"] == "Mira Dhawan"
    with SessionLocal() as db:
        engine.rebuild_facts(db, case_id)
        db.commit()
    assert facts(case_id)["full_name"]["value"] == "Mira Dhawan"
    assert not [e for e in call("GET", f"/api/cases/{case_id}/conflicts").json()["conflicts"] if e["field"] == "full_name"]


def test_a_seeded_human_correction_wins_over_extraction():
    """The CASE-0012 pattern. The reviewer corrected the name and a reimport never changes it."""
    case_id = new_case("Ayan Sury")
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO review_decisions (decision_id, case_id, field_name, rejected_value, corrected_value, decision, "
                 "reviewer_role, reviewer_id, reason, source_ref, recorded_at) VALUES (:d, :c, 'full_name', 'Ayan Sury', "
                 "'Meera Batra', 'REJECTED_EXTRACTION', 'LEGAL_REVIEWER', 'LEGAL-01', 'Keep it', 'PROFILE-X', now())"),
            {"d": f"REV-T{uuid.uuid4().hex[:8]}", "c": case_id},
        )  # fmt: skip
        db.commit()
    for _ in range(2):
        state = facts(case_id)["full_name"]
        assert state["state"] == "HUMAN_DECIDED" and state["value"] == "Meera Batra"


def test_a_typed_correction_needs_a_reason_and_a_real_date():
    case_id = new_case()
    add_profile(case_id, "date_of_birth", "1982-04-08")
    add_claim(case_id, "Z-9006", "date_of_birth", "1982-04-09")
    path = f"/api/cases/{case_id}/conflicts/date_of_birth/resolve"
    assert call("POST", path, LEGAL, json={"value": "1982-04-10"}).json()["error"]["code"] == "REASON_REQUIRED"
    assert call("POST", path, LEGAL, json={"value": "soon", "reason": "typed"}).json()["error"]["code"] == "INVALID_DATE"
    ok = call("POST", path, LEGAL, json={"value": "1982-04-10", "reason": "Birth certificate seen"})
    assert ok.json()["state"] == "HUMAN_DECIDED" and ok.json()["value"] == "1982-04-10"
    assert ok.json()["decided_by"]["source_ref"] is None


def test_nothing_to_resolve_when_sources_agree():
    case_id = new_case("Test Client")
    add_doc(case_id, "PASSPORT.Applicant", "Test Client")  # the passport and the profile agree
    r = call("POST", f"/api/cases/{case_id}/conflicts/full_name/resolve", LEGAL, json={"value": "Test Client"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOTHING_TO_RESOLVE"
    assert call("POST", f"/api/cases/{case_id}/conflicts/nope/resolve", LEGAL, json={"value": "x"}).status_code == 404


def test_scoping_other_users_get_403_and_a_denied_line():
    case_id, _, _ = name_conflict()
    for path in ("facts", "conflicts"):
        assert call("GET", f"/api/cases/{case_id}/{path}", "OPS-92").status_code == 403
        assert call("GET", f"/api/cases/{case_id}/{path}", "LEGAL-92").status_code == 403
    assert ("CASE_ACCESS", "DENIED") in audit_actions(case_id)


# ---------------------------------------------------------------- explanation


def seed_prompts_again() -> None:
    """The AI tests empty the prompt tables, so the seeds are loaded again."""
    from app.ai.seed import seed_prompts

    with SessionLocal() as db:
        seed_prompts(db)


@pytest.fixture
def model_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "auto_read", True)
    seed_prompts_again()
    explain._CACHE.clear()


def conflict_state(case_id: str):
    with SessionLocal() as db:
        return next(s for s in engine.compute_states(db, case_id) if s.field == "full_name")


def answer(ids: list[str], text_: str) -> dict:
    return {"injection_flag": False, "explanations": [{"field": "full_name", "explanation": text_, "cited_source_ids": ids}]}


def test_explanation_cites_only_conflict_sources_and_is_cached(model_on, fake_claude):
    case_id, passport, note = name_conflict()
    state = conflict_state(case_id)
    fake_claude.reply(answer([note, passport, "UP-999999"], f"{note} says Mira Dawan but {passport} says Mira Dhawan."))
    first = explain.explain(case_id, [state])["full_name"]
    assert first.origin == "MODEL" and set(first.cited_source_ids) == {note, passport}
    second = explain.explain(case_id, [state])["full_name"]
    assert second.text == first.text and len(fake_claude.messages.calls) == 1


def test_explanation_that_names_a_foreign_id_or_picks_a_winner_is_replaced(model_on, fake_claude):
    case_id, passport, note = name_conflict()
    state = conflict_state(case_id)
    fake_claude.reply(answer([note], f"{note} differs from UP-999999."))
    assert explain.explain(case_id, [state])["full_name"].origin == "FALLBACK"
    explain._CACHE.clear()
    fake_claude.reply(answer([note, passport], f"{passport} is correct and {note} is wrong."))
    assert explain.explain(case_id, [state])["full_name"].origin == "FALLBACK"


def test_explanation_falls_back_when_the_model_fails_or_is_off(model_on, fake_claude, monkeypatch: pytest.MonkeyPatch):
    case_id, passport, note = name_conflict()
    state = conflict_state(case_id)
    fake_claude.fail(RuntimeError("boom"))
    failed = explain.explain(case_id, [state])["full_name"]
    assert failed.origin == "FALLBACK" and note in failed.text and "Mira Dawan" in failed.text and "disagree" in failed.text
    fake_claude.reply("not json")
    assert explain.explain(case_id, [state])["full_name"].origin == "FALLBACK"
    monkeypatch.setattr(get_settings(), "auto_read", False)
    calls = len(fake_claude.messages.calls)
    assert explain.explain(case_id, [state])["full_name"].origin == "FALLBACK"
    assert len(fake_claude.messages.calls) == calls
    assert ";" not in failed.text and chr(0x2014) not in failed.text


def test_conflicts_route_returns_the_explanation_and_the_suggestion():
    case_id, _, note = name_conflict()
    call("POST", f"/api/cases/{case_id}/conflicts/full_name/suggest", json={"leave_to_attorney": True, "reason": "Ask the client"})
    body = call("GET", f"/api/cases/{case_id}/conflicts").json()
    item = next(c for c in body["conflicts"] if c["field"] == "full_name")
    assert item["explanation_origin"] == "FALLBACK" and note in item["explanation"]
    assert item["suggestion"]["reason"] == "Ask the client"
    assert all(c["state"] in ("CONFLICT", "UNVERIFIED") for c in body["conflicts"])


# ---------------------------------------------------------------- claims from notes and messages


def test_ensure_claims_reads_a_note_once(monkeypatch: pytest.MonkeyPatch, fake_claude):
    case_id = new_case()
    note_id = f"Z-T{uuid.uuid4().hex[:6]}"
    summary = f"Automated notes: person introduced themselves as Mira Dawan {uuid.uuid4().hex}."
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO intake_notes (intake_id, case_id, recorded_at, platform, speaker, summary, raw_note_excerpt, "
                 "ai_generated, approved_as_fact) VALUES (:i, :c, now(), 'ZOOM', 'Intake Coordinator', :s, '', true, false)"),
            {"i": note_id, "c": case_id, "s": summary},
        )  # fmt: skip
        db.commit()
    with SessionLocal() as db:
        assert sources.ensure_claims(db, case_id) == 0
    assert not fake_claude.messages.calls
    monkeypatch.setattr(get_settings(), "auto_read", True)
    seed_prompts_again()
    reply = {"category": "ZOOM_NOTES", "language": "en", "legible": True, "injection_flag": False,
             "fields": {"ZOOM_NOTES.Full Name": {"value": "Mira Dawan", "quote": "Mira Dawan", "page": 1}}}  # fmt: skip
    fake_claude.reply(reply)
    with SessionLocal() as db:
        assert sources.ensure_claims(db, case_id) == 1
        assert sources.ensure_claims(db, case_id) == 0
    assert len(fake_claude.messages.calls) == 1
    state = facts(case_id)["full_name"]
    assert state["state"] == "CONFLICT" and note_id in {s["source_id"] for s in state["sources"]}


def test_ensure_claims_never_raises_when_the_model_fails(monkeypatch: pytest.MonkeyPatch, fake_claude):
    case_id = new_case()
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO intake_notes (intake_id, case_id, recorded_at, platform, speaker, summary, raw_note_excerpt, "
                 "ai_generated, approved_as_fact) VALUES (:i, :c, now(), 'ZOOM', 'x', :s, '', true, false)"),
            {"i": f"Z-T{uuid.uuid4().hex[:6]}", "c": case_id, "s": f"note {uuid.uuid4().hex}"},
        )  # fmt: skip
        db.commit()
    monkeypatch.setattr(get_settings(), "auto_read", True)
    fake_claude.fail(RuntimeError("down"))
    with SessionLocal() as db:
        assert sources.ensure_claims(db, case_id) == 0


# ---------------------------------------------------------------- form draft


def draft(case_id: str, actor: str = OPS) -> dict[str, dict]:
    body = call("GET", f"/api/cases/{case_id}/form-draft", actor).json()
    return {f["target"]: f for f in body["fields"]}


def test_form_draft_holds_a_conflict_and_fills_a_claim_for_legal_review():
    case_id, passport, note = name_conflict()
    add_claim(case_id, "Z-9007", "mailing_address", "5 Invented Way")
    add_doc(case_id, "PASSPORT.Expires", "2030-01-31")
    rows = draft(case_id)
    name = rows["applicant.legal_name"]
    assert name["status"] == "HELD_FOR_REVIEW" and name["value"] is None and name["needs_legal_review"] is True
    assert set(name["evidence_refs"]) == {passport, note, f"PROFILE-{case_id}-full_name"}
    assert name["review_notes"] == "Sources disagree, an attorney must decide"
    address = rows["applicant.mailing_address"]
    assert address["status"] == "PROPOSED" and address["value"] == "5 Invented Way" and address["needs_legal_review"] is True
    assert address["evidence_refs"] == ["Z-9007"] and address["review_notes"].startswith("Claim from Z-9007")
    assert rows["applicant.passport_expiration"]["status"] == "PROPOSED" and rows["applicant.passport_expiration"]["value"] == "2030-01-31"
    assert set(rows["applicant.legal_name"]) == {"target", "value", "status", "evidence_refs", "confidence", "needs_legal_review", "review_notes"}


def test_form_draft_profile_only_case_proposes_nothing_a_required_document_gives():
    case_id = new_case("Test Client")
    add_profile(case_id, "date_of_birth", "1990-01-02")
    add_profile(case_id, "mailing_address", "5 Invented Way")
    rows = draft(case_id)
    for target in ("applicant.legal_name", "applicant.date_of_birth", "applicant.passport_number"):
        assert rows[target]["status"] == "NOT_AVAILABLE" and rows[target]["value"] is None  # the passport is a required document
    assert rows["applicant.legal_name"]["evidence_refs"] == [f"PROFILE-{case_id}-full_name"]
    assert "not enough on its own" in rows["applicant.date_of_birth"]["review_notes"]
    assert rows["applicant.mailing_address"]["status"] == "PROPOSED" and rows["applicant.mailing_address"]["value"] == "5 Invented Way"
    add_doc(case_id, "PASSPORT.Date of Birth", "1990-01-02")
    assert draft(case_id)["applicant.date_of_birth"]["status"] == "PROPOSED"  # the passport is there now
    assert call("GET", f"/api/cases/{case_id}/form-draft").json()["release_status"] == "PENDING_LEGAL_REVIEW_ONLY"


def test_form_draft_uses_the_human_decision_and_a_held_row_prints_in_the_pdf():
    case_id, passport, _ = name_conflict()
    held = call("GET", f"/api/cases/{case_id}/form-draft").json()
    pdf = render_form_pdf(case_id=case_id, client_name="Test", form_id=held["form_id"], sections=held["sections"], fields=held["fields"],
                          proposal_id="ACT-000001", approved_by=LEGAL, approved_at=datetime(2026, 10, 23, tzinfo=timezone.utc))  # fmt: skip
    assert b"HELD" in pdf and b"Not available" in pdf
    proposal = call("POST", f"/api/cases/{case_id}/proposals", json={"kind": "FORM_EXPORT", "idempotency_key": uuid.uuid4().hex})
    assert proposal.status_code == 409 and proposal.json()["error"]["code"] == "OPEN_EXCEPTIONS"  # an open conflict stops the send
    call("POST", f"/api/cases/{case_id}/conflicts/full_name/resolve", LEGAL, json={"value": "Mira Dhawan"})
    row = draft(case_id)["applicant.legal_name"]
    assert row["status"] == "PROPOSED" and row["value"] == "Mira Dhawan"
    assert passport in row["evidence_refs"] and "Decided by LEGAL-91" in row["review_notes"]


def state_of(kind: str, *kinds: str, image: bool = False) -> engine.FieldState:
    items = [engine.SourceOut(source_id=f"S-{i}", source_kind=k, trust="CLAIM", value="v", quote=None, page=None, verified=False, from_image=image)
             for i, k in enumerate(kinds)]  # fmt: skip
    return engine.FieldState(field="full_name", label="Name", state=kind, severity="LOW", value="v", trust={}, sources=items, decided_by=None, note=None)


@pytest.mark.parametrize(
    ("state", "kinds", "image", "score"),
    [
        (engine.HUMAN_DECIDED, ("DOCUMENT",), False, 1.0),
        (engine.AGREE, ("DOCUMENT", "PROFILE"), False, 0.95),
        (engine.SINGLE, ("DOCUMENT",), False, 0.8),
        (engine.SINGLE, ("PROFILE",), False, 0.5),
        (engine.UNVERIFIED, ("INTAKE",), False, 0.3),
        (engine.AGREE, ("DOCUMENT", "PROFILE"), True, 0.8),
        (engine.SINGLE, ("DOCUMENT",), True, 0.65),
    ],
)
def test_form_confidence_comes_from_what_backs_the_value(state, kinds, image, score):
    assert form_draft.confidence_of(state_of(state, *kinds, image=image)) == score


def test_form_draft_rows_carry_confidence_only_when_they_have_a_value():
    case_id, _, _ = name_conflict()
    add_claim(case_id, "Z-9008", "mailing_address", "5 Invented Way")
    add_doc(case_id, "PASSPORT.Expires", "2030-01-31")
    rows = draft(case_id)
    assert rows["applicant.legal_name"]["confidence"] is None  # held, no value
    assert rows["applicant.mailing_address"]["confidence"] == 0.3  # a claim alone
    assert rows["applicant.passport_expiration"]["confidence"] == 0.8  # one document
    assert all(r["confidence"] is not None for r in rows.values() if r["value"] is not None)
    call("POST", f"/api/cases/{case_id}/conflicts/full_name/resolve", LEGAL, json={"value": "Mira Dhawan"})
    assert draft(case_id)["applicant.legal_name"]["confidence"] == 1.0  # an attorney decided


# ---------------------------------------------------------------- home


def home_row(case_id: str, actor: str):
    return call("GET", f"/api/home?case_id={case_id}", actor).json()["rows"][0]


def test_home_reason_for_an_identity_mismatch_and_a_facts_conflict():
    case_id, _, _ = name_conflict()
    ops = home_row(case_id, OPS)
    assert ops["reason"]["label"] == "Identity mismatch" and ops["next_action"] == "Review conflict" and ops["attention"] is True
    assert home_row(case_id, LEGAL)["next_action"] == "Resolve conflict"
    call("POST", f"/api/cases/{case_id}/conflicts/full_name/resolve", LEGAL, json={"value": "Mira Dhawan"})
    assert home_row(case_id, OPS)["reason"]["key"] not in ("identity_mismatch", "facts_conflict")
    other = new_case()
    add_profile(other, "employer_name", "Acme LLC")
    add_claim(other, "Z-9008", "employer_name", "Other Corp")
    row = home_row(other, OPS)
    assert row["reason"]["label"] == "Facts conflict" and "employer name" in row["reason"]["text"]


def _comm_case():
    case_id = new_case("Mira Dhawan")
    n = case_id[5:]
    with SessionLocal() as db:
        db.execute(text("INSERT INTO intake_notes (intake_id, case_id, recorded_at, platform, speaker, summary, raw_note_excerpt, "
                        "ai_generated, approved_as_fact) VALUES (:i, :c, '2026-10-04', 'ZOOM', 'Intake Coordinator', 's', 'x', true, false)"),
                   {"i": f"Z-{n}", "c": case_id})  # fmt: skip
        db.execute(text("INSERT INTO messages (message_id, case_id, thread_id, created_at_source, channel, direction, sender_role, subject, "
                        "body, attachment_refs, delivery_state) VALUES (:i, :c, 'T', '2026-10-08', 'WHATSAPP', 'INBOUND', 'CLIENT', 's', "
                        "'b', '{}', 'RECORDED_MOCK')"), {"i": f"MSG-{n}-1", "c": case_id})  # fmt: skip
        db.commit()
    return case_id, n


def test_sources_carry_a_phase_and_a_later_message_sets_change():
    case_id, n = _comm_case()
    add_profile(case_id, "mailing_address", "1 Old Road")
    add_claim(case_id, f"Z-{n}", "mailing_address", "1 Old Road")
    add_claim(case_id, f"MSG-{n}-1", "mailing_address", "9 New Street")
    state = facts(case_id)["mailing_address"]
    phases = {s["source_id"]: s["phase"] for s in state["sources"]}
    assert phases == {f"PROFILE-{case_id}-mailing_address": "PROFILE", f"Z-{n}": "BASELINE", f"MSG-{n}-1": "UPDATE"}
    assert state["state"] == "CONFLICT" and state["change"] is True
    passport = add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    assert {s["source_id"]: s["phase"] for s in facts(case_id)["full_name"]["sources"]}[passport] == "DOCUMENT"


def test_change_is_false_when_the_update_repeats_the_call_or_the_call_differs_from_a_document():
    case_id, n = _comm_case()
    add_claim(case_id, f"Z-{n}", "employer_name", "Acme")
    add_claim(case_id, f"MSG-{n}-1", "employer_name", "acme")
    assert facts(case_id)["employer_name"]["change"] is False
    add_claim(case_id, f"Z-{n}", "full_name", "Mira Dawan")
    add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    state = facts(case_id)["full_name"]
    assert state["state"] == "CONFLICT" and state["change"] is False


def test_a_shorter_repeat_of_the_call_value_is_not_a_change():
    case_id, n = _comm_case()
    add_claim(case_id, f"Z-{n}", "mailing_address", "901 Newly Claimed Rd, Example City, EX 00000")
    add_claim(case_id, f"MSG-{n}-1", "mailing_address", "901 Newly Claimed Rd")
    assert facts(case_id)["mailing_address"]["change"] is False


# ---------------------------------------------------------------- operations resolves a medium conflict


def medium_conflict() -> str:
    case_id = new_case()
    add_profile(case_id, "employer_name", "Acme LLC")
    add_claim(case_id, f"Z-{uuid.uuid4().hex[:6]}", "employer_name", "Other Corp")
    return case_id


def conflict_row(case_id: str, field: str, actor: str = OPS) -> dict:
    return next(c for c in call("GET", f"/api/cases/{case_id}/conflicts", actor).json()["conflicts"] if c["field"] == field)


def test_ops_resolves_a_medium_conflict_with_a_reason_and_the_role_is_recorded():
    case_id = medium_conflict()
    path = f"/api/cases/{case_id}/conflicts/employer_name/resolve"
    assert call("POST", path, OPS, json={"value": "Acme LLC"}).json()["error"]["code"] == "REASON_REQUIRED"
    done = call("POST", path, OPS, json={"value": "Acme LLC", "reason": "The letter names Acme"})
    assert done.status_code == 200
    state = done.json()
    assert state["state"] == "HUMAN_DECIDED" and state["value"] == "Acme LLC"
    assert state["decided_by"]["reviewer_id"] == OPS and state["decided_by"]["reviewer_role"] == "OPS"
    with SessionLocal() as db:
        role = db.scalar(text("SELECT actor_role FROM audit_log WHERE case_id = :c AND action = 'CONFLICT_RESOLVED'"), {"c": case_id})
        count = db.scalar(text("SELECT count(*) FROM review_decisions WHERE case_id = :c"), {"c": case_id})
    assert role == "OPS" and count == 1
    again = call("POST", path, OPS, json={"value": "Acme LLC", "reason": "again"})
    assert again.status_code == 200
    add_claim(case_id, "MSG-9100-1", "employer_name", "Third Co")
    assert facts(case_id)["employer_name"]["state"] == "HUMAN_DECIDED"


def test_ops_is_blocked_on_a_high_conflict_and_others_are_blocked():
    case_id, _, _ = name_conflict()
    path = f"/api/cases/{case_id}/conflicts/full_name/resolve"
    blocked = call("POST", path, OPS, json={"value": "Mira Dhawan", "reason": "x"})
    assert blocked.status_code == 403 and blocked.json()["error"]["message"] == "Identity conflicts need the legal reviewer"
    assert ("CONFLICT_RESOLVED", "DENIED") in audit_actions(case_id)
    medium = medium_conflict()
    mpath = f"/api/cases/{medium}/conflicts/employer_name/resolve"
    body = {"value": "Acme LLC", "reason": "x"}
    assert call("POST", mpath, "OPS-92", json=body).status_code == 403
    assert call("POST", mpath, "LEGAL-92", json=body).status_code == 403
    assert call("POST", path, LEGAL, json={"value": "Mira Dhawan"}).status_code == 200
    assert call("POST", mpath, LEGAL, json={"value": "Acme LLC"}).status_code == 200


def test_can_resolve_is_set_per_acting_user():
    high, _, _ = name_conflict()
    medium = medium_conflict()
    assert conflict_row(high, "full_name", OPS)["can_resolve"] is False
    assert conflict_row(high, "full_name", LEGAL)["can_resolve"] is True
    assert conflict_row(medium, "employer_name", OPS)["can_resolve"] is True
    assert conflict_row(medium, "employer_name", LEGAL)["can_resolve"] is True


def test_a_medium_conflict_is_not_a_legal_review_item_and_a_high_one_is():
    high, _, _ = name_conflict()
    medium = medium_conflict()
    ops_medium, legal_medium = home_row(medium, OPS), home_row(medium, LEGAL)
    assert ops_medium["next_action"] == "Resolve conflict" and ops_medium["legal_review"] is False and legal_medium["legal_review"] is False
    assert home_row(high, OPS)["next_action"] == "Review conflict" and home_row(high, LEGAL)["legal_review"] is True
    owners = {i["case_id"]: i["owner_role"] for i in call("GET", "/api/exceptions", OPS).json()["items"] if i["type"] == "FACT_CONFLICT"}
    assert owners[high] == "LEGAL" and owners[medium] == "OPS"


def test_a_read_loads_the_stored_states_and_does_not_rebuild(monkeypatch: pytest.MonkeyPatch):
    case_id = new_case("Mira Dhawan")
    add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    assert facts(case_id)["full_name"]["state"] == "AGREE"

    def refuse(*_args, **_kwargs):
        raise AssertionError("a read rebuilt the facts")

    monkeypatch.setattr(engine, "refresh", refuse)
    monkeypatch.setattr(engine, "rebuild_facts", refuse)
    assert facts(case_id)["full_name"]["state"] == "AGREE"
    assert call("GET", f"/api/cases/{case_id}/conflicts").status_code == 200
    assert call("GET", f"/api/cases/{case_id}/form-draft").status_code == 200


def test_a_change_rebuilds_the_stored_states_once():
    case_id = new_case("Mira Dhawan")
    add_doc(case_id, "PASSPORT.Applicant", "Mira Dhawan")
    assert facts(case_id)["full_name"]["state"] == "AGREE"
    add_claim(case_id, "Z-9100", "full_name", "Mira Dawan")
    assert facts(case_id)["full_name"]["state"] == "CONFLICT"
    with SessionLocal() as db:
        assert db.execute(text("SELECT count(*) FROM fact_states WHERE case_id = :c"), {"c": case_id}).scalar() == len(sources.FIELDS)


# ---------------------------------------------------------------- confirming an imported profile value


def import_profile(case_id: str, field: str, value: str) -> None:
    add_profile(case_id, field, value)
    with SessionLocal() as db:
        db.execute(text("UPDATE profile_fields SET verification_state = 'IMPORTED' WHERE case_id = :c AND field_name = :f"), {"c": case_id, "f": field})
        db.commit()
    changed(case_id)


def test_a_profile_value_is_accepted_evidence_and_is_not_held_back_for_review():
    case_id = new_case("Test Client")
    add_profile(case_id, "mailing_address", "5 Invented Way")  # no required document gives the address, so the profile is enough
    state = facts(case_id)["mailing_address"]
    assert state["state"] == "SINGLE_SOURCE_EVIDENCE" and state["sources"][0]["source_kind"] == "PROFILE" and state["sources"][0]["verified"] is True
    row = draft(case_id)["applicant.mailing_address"]
    assert row["status"] == "PROPOSED" and row["needs_legal_review"] is False and "possibly out of date" in row["review_notes"]


def test_a_profile_value_alone_is_not_enough_where_a_required_document_gives_the_field():
    case_id = new_case("Test Client")
    add_profile(case_id, "date_of_birth", "1990-01-02")
    state = facts(case_id)["date_of_birth"]
    assert state["state"] == "UNVERIFIED" and state["requires_document"] is True and state["value"] is None
    assert state["note"] == "Needs a document, the profile alone is not enough"
    row = draft(case_id)["applicant.date_of_birth"]
    assert row["status"] == "NOT_AVAILABLE" and row["value"] is None and row["evidence_refs"] == [f"PROFILE-{case_id}-date_of_birth"]
    add_doc(case_id, "PASSPORT.Date of Birth", "1990-01-02")
    assert facts(case_id)["date_of_birth"]["state"] == "AGREE"


def test_a_person_can_still_confirm_a_profile_row_that_is_not_yet_verified():
    case_id = new_case("Test Client")
    import_profile(case_id, "date_of_birth", "1990-01-02")
    source = facts(case_id)["date_of_birth"]["sources"][0]
    assert source["source_kind"] == "PROFILE" and source["verified"] is False
    assert draft(case_id)["applicant.date_of_birth"]["needs_legal_review"] is False  # evidence either way
    done = call("POST", f"/api/cases/{case_id}/profile/date_of_birth/confirm")
    assert done.status_code == 200 and done.json()["sources"][0]["verified"] is True
    with SessionLocal() as db:
        row = db.execute(text("SELECT verification_state, verified_by, note FROM profile_fields WHERE case_id = :c AND field_name = 'date_of_birth'"), {"c": case_id}).one()
    assert row.verification_state == "HUMAN_VERIFIED" and row.verified_by == OPS and row.note.startswith("Confirmed in app")


def test_only_the_assigned_users_can_confirm_a_profile_value():
    case_id = new_case("Test Client")
    import_profile(case_id, "date_of_birth", "1990-01-02")
    assert call("POST", f"/api/cases/{case_id}/profile/date_of_birth/confirm", "OPS-92").status_code == 403
    assert call("POST", f"/api/cases/{case_id}/profile/passport_number/confirm").status_code == 404


def test_a_field_no_document_can_supply_needs_a_person_to_confirm_it(monkeypatch):
    monkeypatch.setattr(sources, "_EXTRA", {})  # the kit alone names no document for the mailing address
    monkeypatch.setattr(sources, "_declared", lambda db: {})  # and the prompt registry declares none either
    case_id = new_case("Test Client")
    add_claim(case_id, "Z-9100", "mailing_address", "5 Invented Way")
    add_claim(case_id, "Z-9100", "last_entry_date", "2025-06-10")
    states = facts(case_id)
    assert states["mailing_address"]["document_source"] is False and states["mailing_address"]["note"] == "Needs a person to confirm it"
    assert states["last_entry_date"]["document_source"] is True and states["last_entry_date"]["note"] == "Needs a document"
    rows = draft(case_id)
    assert rows["applicant.mailing_address"]["review_notes"] == "Claim from Z-9100. A person must confirm it."
    assert rows["travel.last_entry"]["status"] == "NOT_AVAILABLE" and "A claim (Z-9100) says 2025-06-10" in rows["travel.last_entry"]["review_notes"]
    add_profile(case_id, "mailing_address", "5 Invented Way")
    assert draft(case_id)["applicant.mailing_address"]["needs_legal_review"] is False  # the profile is accepted evidence for it


def test_a_form_target_declared_in_the_registry_adds_a_document_source(monkeypatch):
    monkeypatch.setattr(sources, "_EXTRA", {})
    monkeypatch.setattr(sources, "_declared", lambda db: {"applicant.mailing_address": ["UTILITY_BILL.Service Address"]})
    with SessionLocal() as db:
        assert "UTILITY_BILL.Service Address" in sources._candidates(db)["mailing_address"]
        # the kit names no document for the mailing address, so the added source is also the one to ask the client for
        assert "UTILITY_BILL.Service Address" in sources._candidates(db, requestable=True)["mailing_address"]
        assert "UTILITY_BILL.Service Address" not in sources._candidates(db)["full_name"]


def test_a_registry_target_this_app_does_not_know_is_ignored():
    with SessionLocal() as db:
        assert set(sources._declared(db)) <= set(sources.TARGET_FIELD)


def test_an_address_proof_document_is_evidence_for_the_mailing_address():
    case_id = new_case("Test Client")
    add_claim(case_id, "Z-9101", "mailing_address", "5 Invented Way")
    add_doc(case_id, "ADDRESS_PROOF.Address", "5 Invented Way")
    state = facts(case_id)["mailing_address"]
    assert state["document_source"] is True and state["state"] == "AGREE"
    assert {s["source_kind"] for s in state["sources"]} == {"DOCUMENT", "INTAKE"}


def test_dates_in_other_styles_normalize_to_one_value_so_sources_agree():
    for text in ("April 8, 1982", "8 April 1982", "1982/04/08", "08-Apr-1982", "8th April 1982", "1982-04-08"):
        assert normalize.normalize("date_of_birth", text) == "1982-04-08", text
    assert normalize.normalize("date_of_birth", "13/04/1982") == "1982-04-13"  # only one way to read it
    assert normalize.normalize("date_of_birth", "03/04/2025") == "03/04/2025"  # day or month first, left alone


def test_deciding_the_name_checks_held_back_files_again_and_no_other_field_does(monkeypatch):
    from app.api import facts as facts_api

    started = []
    monkeypatch.setattr(facts_api.ingest, "start_case_job", lambda db, tasks, actor, case_id, claimable, kind="ANALYSE": started.append((case_id, claimable, kind)))
    case_id, passport, note = name_conflict()
    done = call("POST", f"/api/cases/{case_id}/conflicts/full_name/resolve", LEGAL, json={"value": "Mira Dhawan", "reason": "Passport"})
    assert done.status_code == 200 and started == [(case_id, ("NEEDS_HUMAN_REVIEW",), "ANALYSE")]


def test_an_address_proof_held_for_review_is_named_as_held_and_not_as_missing():
    case_id = new_case("Test Client")
    add_claim(case_id, "Z-9200", "mailing_address", "5 Invented Way")
    held = add_doc(case_id, "ADDRESS_PROOF.Address", "5 Invented Way", outcome="NEEDS_HUMAN_REVIEW")
    state = facts(case_id)["mailing_address"]
    assert state["state"] == "UNVERIFIED" and state["note"] == "A document is held for review, so it does not count yet"
    row = draft(case_id)["applicant.mailing_address"]
    assert row["needs_legal_review"] is True and row["value"] == "5 Invented Way"
    assert row["review_notes"] == f"{held} is held for review, so it does not count as evidence yet. Claim from Z-9200."


# ---------------------------------------------------------------- the profile against the Zoom intake


@pytest.mark.parametrize(
    ("field", "target", "profile", "zoom"),
    [
        ("full_name", "applicant.legal_name", "Mira Dhawan", "Mira Dawan"),
        ("employer_name", "employment.organization", "Fictional Employer 01 LLC", "Fictional Employer 10 LLC"),
        ("employment_start_date", "employment.start_date", "2024-05-07", "2024-06-07"),
        ("last_entry_date", "travel.last_entry", "2025-06-10", "2025-07-10"),
        ("mailing_address", "applicant.mailing_address", "101 Invented Way, Unit 2, Example City", "901 Newly Claimed Rd, Example City"),
    ],
)
def test_a_profile_value_that_differs_from_the_zoom_intake_is_held_for_legal_review(field, target, profile, zoom):
    case_id = new_case("Test Client")
    add_profile(case_id, field, profile)
    add_claim(case_id, "Z-9500", field, zoom)
    state = facts(case_id)[field]
    assert state["state"] == "CONFLICT" and state["review_open"] is True
    assert {s["source_kind"] for s in state["sources"]} == {"PROFILE", "INTAKE"}
    row = draft(case_id)[target]
    assert row["status"] == "HELD_FOR_REVIEW" and row["value"] is None and row["needs_legal_review"] is True
    assert field in {c["field"] for c in call("GET", f"/api/cases/{case_id}/conflicts").json()["conflicts"]}


def test_a_profile_value_that_matches_the_zoom_intake_needs_no_review():
    case_id = new_case("Test Client")
    add_profile(case_id, "last_entry_date", "2025-06-10")
    add_doc(case_id, "ARRIVAL_RECORD.Last Recorded Entry", "2025-06-10")
    add_claim(case_id, "Z-9501", "last_entry_date", "2025-06-10")
    state = facts(case_id)["last_entry_date"]
    assert state["state"] == "AGREE" and state["review_open"] is False
    assert draft(case_id)["travel.last_entry"]["status"] == "PROPOSED"


def test_a_hedged_date_is_the_same_date_so_a_matching_claim_is_not_a_conflict():
    for text in ("about 2024-05-07", "around 2024-05-07", "approx. 2024-05-07", "maybe 2024-05-07", "~ 2024-05-07"):
        assert normalize.normalize("employment_start_date", text) == "2024-05-07", text
    case_id = new_case("Test Client")
    add_profile(case_id, "employment_start_date", "2024-05-07")
    add_doc(case_id, "EMPLOYER_LETTER.Employment start", "2024-05-07")
    add_claim(case_id, "Z-9600", "employment_start", "about 2024-05-07")
    assert facts(case_id)["employment_start_date"]["state"] == "AGREE"
    other = new_case("Test Client")
    add_profile(other, "employment_start_date", "2023-05-07")
    add_claim(other, "Z-9601", "employment_start", "about 2025-05-07")
    assert facts(other)["employment_start_date"]["state"] == "CONFLICT"  # a different date is still a conflict


def test_a_row_waiting_for_a_required_document_says_so_and_an_optional_one_does_not():
    case_id = new_case("Test Client")
    add_profile(case_id, "full_name", "Test Client")
    add_doc(case_id, "PASSPORT.Applicant", "Test Client", outcome="NEEDS_HUMAN_REVIEW")  # a passport that was held back
    rows = draft(case_id)
    assert rows["applicant.passport_number"]["review_notes"].startswith("Needs a document")  # the passport is required and missing
    assert rows["applicant.legal_name"]["status"] == "NOT_AVAILABLE" and rows["applicant.legal_name"]["review_notes"].startswith("Needs a document")
    assert "is held for review" in rows["applicant.legal_name"]["review_notes"]
    assert not rows["applicant.mailing_address"]["review_notes"].startswith("Needs a document")  # an address proof is optional
