"""OCR helpers for scanned pages. All OCR runs in the docling-serve container so this image stays light."""

from pathlib import Path
from typing import Literal

import httpx

from app.core.config import get_settings

Engine = Literal["tesseract", "docling"]

# "docling" uses docling-serve's default OCR engine. Tesseract names English "eng", the others "en".
OCR_ENGINES = {"tesseract": ("tesseract", "eng"), "docling": (None, "en")}


def ocr_version() -> str:
    response = httpx.get(f"{get_settings().ocr_url}/version", timeout=10)
    response.raise_for_status()
    return str(response.json())


def ocr_image(source: str | Path | bytes, engine: Engine = "tesseract") -> str:
    """Return the text found in an image file path or raw image bytes."""
    if engine not in OCR_ENGINES:
        raise ValueError(f"Unknown OCR engine: {engine}")
    if isinstance(source, bytes):
        return convert_file("page.png", source, engine)
    return docling_file_text(source, engine)


def docling_file_text(path: str | Path, engine: Engine = "docling") -> str:
    """Convert a PDF or image file to plain text with docling-serve."""
    path = Path(path)
    return convert_file(path.name, path.read_bytes(), engine)


def convert_file(name: str, data: bytes, engine: Engine) -> str:
    ocr_engine, ocr_lang = OCR_ENGINES[engine]
    form = {"to_formats": "text", "do_ocr": "true", "do_table_structure": "false", "ocr_lang": ocr_lang}
    if ocr_engine:
        form["ocr_engine"] = ocr_engine
    response = httpx.post(
        f"{get_settings().ocr_url}/v1/convert/file",
        files={"files": (name, data)},
        data=form,
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["document"]["text_content"].strip()
