"""Claims from call and message documents. They are read by the same pipeline as every other document.

A claim is never a fact. It is stored with the upload id as its source, it is never verified and it never
reaches profile_fields. Only a value whose quote the reader found in the page text is kept.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.contracts import DocumentRead
from app.ingest import rules


def claim_name(key: str) -> str:
    """CATEGORY.Full Name becomes full_name."""
    return key.split(".", 1)[-1].strip().lower().replace(" ", "_")


def store_claims(db: Session, case_id: str, upload_id: str, reads: list[DocumentRead]) -> int:
    """Replace the claims of this upload with the verified values of its call or message reads."""
    db.execute(text("DELETE FROM claims WHERE case_id = :c AND source_id = :s"), {"c": case_id, "s": upload_id})
    stored = 0
    for read in (r for r in reads if r.category in rules.COMM_CATEGORIES):
        for key, item in read.fields.items():
            if not item.verified or not (item.value or "").strip():
                continue
            db.execute(
                text("INSERT INTO claims (case_id, source_id, field_name, value, quote, page) VALUES (:c, :s, :f, :v, :q, :p)"),
                {"c": case_id, "s": upload_id, "f": claim_name(key), "v": item.value.strip(), "q": item.quote, "p": item.page},
            )
            stored += 1
    return stored
