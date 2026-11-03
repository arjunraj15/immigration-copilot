"""Health checks used by the /status page to prove each container dependency works."""

import io

from fastapi import APIRouter, Depends
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services import embeddings, ocr

router = APIRouter(prefix="/api/health", tags=["health"])

SAMPLE_TEXT = "CASE DESK 12345"


@router.get("")
def health() -> dict:
    return {"status": "ok"}


@router.get("/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    row = db.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).first()
    return {"status": "ok" if row else "missing_vector", "pgvector": row[0] if row else None}


def sample_image() -> bytes:
    image = Image.new("RGB", (900, 160), "white")
    font = ImageFont.load_default(size=72)
    ImageDraw.Draw(image).text((20, 30), SAMPLE_TEXT, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@router.get("/ocr")
def health_ocr() -> dict:
    data = sample_image()
    tesseract = ocr.ocr_image(data, "tesseract")
    docling = ocr.ocr_image(data, "docling")
    return {
        "status": "ok" if SAMPLE_TEXT in tesseract and SAMPLE_TEXT in docling else "mismatch",
        "expected": SAMPLE_TEXT,
        "tesseract": {"version": ocr.ocr_version(), "text": tesseract},
        "docling": {"text": docling},
    }


@router.get("/embeddings")
def health_embeddings() -> dict:
    a, b, c = embeddings.embed(
        ["The passport expires in 2031.", "Passport expiry date is March 2031.", "Pay statement for August."]
    )
    related, unrelated = embeddings.cosine(a, b), embeddings.cosine(a, c)
    return {
        "status": "ok" if related > unrelated else "bad_ranking",
        "dimensions": len(a),
        "related": round(related, 3),
        "unrelated": round(unrelated, 3),
    }


@router.get("/ai")
def health_ai() -> dict:
    settings = get_settings()
    return {
        "status": "ok" if settings.anthropic_api_key else "no_key",
        "key_set": bool(settings.anthropic_api_key),
        "reading_model": settings.reading_model,
        "analysis_model": settings.analysis_model,
    }
