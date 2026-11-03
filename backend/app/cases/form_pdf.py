"""Watermarked PDF of an approved form draft. It prints only what is passed in and never adds a value."""

import io
import re
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

WATERMARK = "DRAFT - NOT FOR FILING"
FOOTER = "Review-only worksheet. Not a government form."
ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
RED = colors.HexColor("#b3261e")
GRAY = colors.HexColor("#5c6884")

_base = getSampleStyleSheet()["BodyText"]
CELL = ParagraphStyle("cell", parent=_base, fontSize=9, leading=11)
SMALL = ParagraphStyle("small", parent=CELL, fontSize=7.5, leading=9, textColor=GRAY)
MONO = ParagraphStyle("mono", parent=CELL, fontName="Courier", fontSize=8)
MUTED = ParagraphStyle("muted", parent=CELL, fontName="Helvetica-Oblique", textColor=GRAY)
HEAD = ParagraphStyle("head", parent=_base, fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, spaceAfter=4)


def _us_date(value: str) -> str:
    match = ISO_DATE.match(value)
    return f"{match.group(2)}/{match.group(3)}/{match.group(1)}" if match else value


def _value_cell(field: dict[str, Any], is_date: bool) -> list[Paragraph]:
    value = field.get("value")
    shown = Paragraph("Not available", MUTED) if value is None else Paragraph(escape(_us_date(value) if is_date else value), CELL)
    note = field.get("review_notes")
    return [shown, Paragraph(escape(note), SMALL)] if note else [shown]


def _status_cell(field: dict[str, Any]) -> list[Paragraph]:
    status = str(field.get("status", "")).replace("_", " ")
    style = ParagraphStyle("status", parent=CELL, textColor=RED) if status.startswith("HELD") else CELL
    cells = [Paragraph(escape(status), style)]
    if field.get("needs_legal_review"):
        cells.append(Paragraph("Needs legal review", SMALL))
    return cells


def _sources_cell(field: dict[str, Any]) -> list[Paragraph]:
    refs = field.get("evidence_refs") or []
    return [Paragraph(escape(ref), MONO) for ref in refs] or [Paragraph("-", CELL)]


def _section_table(title: str, rows: list[tuple[str, bool, dict[str, Any]]]) -> list[Any]:
    data = [[Paragraph(h, SMALL) for h in ("Field", "Value", "Status", "Sources")]]
    for label, is_date, field in rows:
        data.append([Paragraph(escape(label), CELL), _value_cell(field, is_date), _status_cell(field), _sources_cell(field)])
    table = Table(data, colWidths=[1.3 * inch, 2.6 * inch, 1.2 * inch, 1.9 * inch], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0f8")),
            ]
        )
    )
    return [Paragraph(escape(title), HEAD), table]


def _page(form_id: str, case_id: str):
    def draw(canvas, doc) -> None:  # reportlab callback, runs once per page
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 54)
        canvas.setFillColor(colors.Color(0.85, 0.85, 0.85, alpha=0.5))
        canvas.translate(letter[0] / 2, letter[1] / 2)
        canvas.rotate(35)
        canvas.drawCentredString(0, 0, WATERMARK)
        canvas.restoreState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRAY)
        canvas.drawString(0.75 * inch, letter[1] - 0.5 * inch, f"{form_id}  |  {case_id}")
        canvas.drawString(0.75 * inch, 0.5 * inch, FOOTER)
        canvas.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")

    return draw


def _group(sections: list[dict[str, Any]], fields: list[dict[str, Any]]) -> list[tuple[str, list[tuple[str, bool, dict[str, Any]]]]]:
    by_target = {f["target"]: f for f in fields}
    listed: set[str] = set()
    groups = []
    for section in sections:
        rows = [(f["label"], bool(f.get("date")), by_target[f["target"]]) for f in section["fields"] if f["target"] in by_target]
        listed.update(f["target"] for f in section["fields"])
        groups.append((section["title"], rows))
    extra = [(t, False, f) for t, f in by_target.items() if t not in listed]
    return groups + ([("Other fields", extra)] if extra else [])


def render_form_pdf(
    *, case_id: str, client_name: str, form_id: str, sections: list[dict[str, Any]], fields: list[dict[str, Any]],
    proposal_id: str, approved_by: str, approved_at: datetime,
) -> bytes:  # fmt: skip
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.9 * inch,
        bottomMargin=0.9 * inch, pageCompression=0, invariant=1,
    )  # fmt: skip
    day = f"{approved_at:%b} {approved_at.day}, {approved_at.year}"
    story: list[Any] = [
        Paragraph(f"Form draft: {escape(client_name)}", getSampleStyleSheet()["Title"]),
        Paragraph(f"Case {escape(case_id)}  |  Form {escape(form_id)}", CELL),
        Spacer(1, 8),
        Paragraph(f"Approved for export by {escape(approved_by)} on {day}", CELL),
        Paragraph(f"Proposal {escape(proposal_id)}", CELL),
        Paragraph("Release status: approved for review-only export. Not for filing.", CELL),
    ]
    for title, rows in _group(sections, fields):
        story.extend(_section_table(title, rows))
    draw = _page(form_id, case_id)
    doc.build(story, onFirstPage=draw, onLaterPages=draw)
    return buffer.getvalue()
