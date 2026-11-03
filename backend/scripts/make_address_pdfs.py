"""Writes the synthetic address proof PDFs used to try the address flow. They are not part of the starter kit.

    python scripts/make_address_pdfs.py /data/extra-documents

Each file follows the layout of the kit's PDFs and says it is synthetic.
"""

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

DOCS = [
    ("CASE-0001", "ADDR-0001_utility_bill.pdf", "Utility bill",
     [("Applicant:", "Mira Dhawan"), ("Synthetic Matter:", "CASE-0001"), ("Reference:", "DOCREF-000008"),
      ("Service Address:", "101 Invented Way, Unit 2, Example City, EX 00010"), ("Bill Date:", "2026-09-20"),
      ("Account:", "SYN-UTIL-00001")]),
    ("CASE-0013", "ADDR-0013_change_of_address.pdf", "Change of address confirmation",
     [("Applicant:", "Naveen Batra"), ("Synthetic Matter:", "CASE-0013"), ("Reference:", "DOCREF-000008"),
      ("New Address:", "901 Newly Claimed Rd, Example City, EX 00000"), ("Effective Date:", "2026-10-21"),
      ("Confirmation ID:", "SYN-COA-00013")]),
]


def write(path: Path, title: str, rows: list[tuple[str, str]]) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    pdf.setFillColor(colors.HexColor("#16345e"))
    pdf.rect(0, height - 54, width, 54, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(36, height - 33, "FICTIONAL IMMIGRATION FIRM  |  HACKATHON TEST DATA")
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(40, height - 110, title)
    y = height - 160
    for label, value in rows:
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(44, y, label)
        pdf.setFont("Helvetica", 11)
        pdf.drawString(220, y, value)
        y -= 34
    pdf.setFont("Helvetica", 8)
    pdf.drawString(36, 40, "SYNTHETIC | NOT A REAL IMMIGRATION DOCUMENT | NOT VALID FOR ANY PURPOSE")
    pdf.drawString(36, 29, "All people, records, employers, dates, rules and identifiers are fabricated.")
    pdf.save()


def main(out: Path) -> None:
    for case_id, name, title, rows in DOCS:
        folder = out / case_id
        folder.mkdir(parents=True, exist_ok=True)
        write(folder / name, title, rows)
        print(folder / name)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("extra-documents"))
