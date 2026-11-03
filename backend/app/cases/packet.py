"""Evidence packet index: each required category with the usable documents filed under it.

Built by code from the checklist and the upload outcomes, never typed in or written by the model."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ingest import service as ingest


def build_packet_index(db: Session, case_id: str) -> dict[str, Any]:
    items = ingest.checklist(db, case_id)
    rows = db.execute(
        text(
            "SELECT upload_id, original_filename, category, flags->>'pay_period' AS period FROM uploads "
            "WHERE case_id = :c AND deleted_at IS NULL AND category IS NOT NULL AND outcome = 'USABLE' ORDER BY uploaded_at, upload_id"
        ),
        {"c": case_id},
    ).all()
    doc_rules = ingest.load_rules(db)
    entries = []
    for item in items:
        period = doc_rules.pay_periods.get(item.category)
        own = [r for r in rows if (r.category == "PAY_STATEMENT" and r.period == period if period else r.category == item.category)]
        entries.append(
            {
                "category": item.category,
                "label": item.label,
                "status": item.status,
                "documents": [{"upload_id": r.upload_id, "filename": r.original_filename} for r in own],
                "not_usable": [reason.model_dump() for reason in item.reasons],
            }
        )
    usable = [doc["upload_id"] for entry in entries for doc in entry["documents"]]
    return {
        "case_id": case_id,
        "packet_id": f"PKT-{case_id}",
        "items": entries,
        "usable_count": len(usable),
        "missing": [e["label"] for e in entries if e["status"] == "MISSING"],
        "not_usable_labels": [e["label"] for e in entries if e["status"] == "NOT_USABLE"],
        "complete": all(e["status"] == "SATISFIED" for e in entries),
        "usable_ids": usable,
        "release_status": "pending legal review only",
    }
