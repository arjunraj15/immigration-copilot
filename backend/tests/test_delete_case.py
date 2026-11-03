"""Deleting a case: it disappears everywhere and its ledger lines stay."""

from sqlalchemy import text

from app.db.session import SessionLocal
from tests.test_facts import LEGAL, OPS, add_claim, call, new_case


def test_a_deleted_case_is_gone_from_every_view_but_the_audit_trail_keeps_it():
    case_id = new_case("Delete Me")
    add_claim(case_id, "Z-9400", "mailing_address", "5 Invented Way")
    assert call("GET", f"/api/cases/{case_id}").status_code == 200
    done = call("DELETE", f"/api/cases/{case_id}")
    assert done.status_code == 200 and done.json() == {"case_id": case_id, "status": "DELETED"}
    assert call("GET", f"/api/cases/{case_id}").status_code == 404
    assert call("GET", f"/api/cases/{case_id}/facts").status_code == 404
    assert call("DELETE", f"/api/cases/{case_id}").status_code == 404  # already gone
    queue = call("GET", "/api/cases").json()
    assert case_id not in {i["case_id"] for g in queue["groups"] for i in g["items"]}
    with SessionLocal() as db:
        assert db.scalar(text("SELECT status FROM case_workflows WHERE case_id = :c"), {"c": case_id}) == "DELETED"
        assert db.scalar(text("SELECT count(*) FROM audit_log WHERE case_id = :c AND action = 'CASE_DELETED'"), {"c": case_id}) == 1


def test_only_the_assigned_users_can_delete_a_case():
    case_id = new_case("Keep Me")
    assert call("DELETE", f"/api/cases/{case_id}", "OPS-92").status_code == 403
    assert call("GET", f"/api/cases/{case_id}").status_code == 200
    assert call("DELETE", f"/api/cases/{case_id}", LEGAL).status_code == 200  # the assigned legal reviewer may too
