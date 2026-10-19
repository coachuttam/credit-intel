"""A synthetic balance sheet PDF and a scripted model response for the pipeline tests.

Not a test module. Years are centred over right-aligned figures, with a Note column, a
scale and currency declaration, and the model's reply written as the JSON the prompt asks for.
"""

import json
from pathlib import Path

from reportlab.pdfgen import canvas

from credit_intel.config import LLMSettings
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

LLM = LLMSettings(provider="fake", model_id="m", token_ceiling=1_000_000, max_output_tokens=2000)

ROWS = [
    # label, note, current, comparative
    ("Total non-current assets", "", "800.00", "700.00"),
    ("Total current assets", "14", "1,482.30", "1,356.75"),
    ("Total assets", "", "2,282.30", "2,056.75"),
    ("Total equity", "", "600.00", "500.00"),
    ("Total current liabilities", "15", "900.00", "850.00"),
]


def balance_sheet_pdf(path: Path, rows=ROWS, title="Consolidated Balance Sheet", scale="(Rs. in crore)",
                      narrative_page=None) -> Path:  # fmt: skip
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.setFont("Helvetica", 10)
    y = 780
    for text in ("Acme Industries Limited", title, scale):
        if text:
            pdf.drawString(72, y, text)
            y -= 15
    pdf.drawString(300, y, "Note")
    pdf.drawCentredString(400, y, "31 March 2025")
    pdf.drawCentredString(480, y, "31 March 2024")
    y -= 15
    for label, note, current, comparative in rows:
        pdf.drawString(72, y, label)
        if note:
            pdf.drawString(305, y, note)
        if current:
            pdf.drawRightString(430, y, current)
        if comparative:
            pdf.drawRightString(510, y, comparative)
        y -= 14
    pdf.showPage()
    if narrative_page:  # a second page that is not a statement
        pdf.drawString(72, 700, narrative_page)
        pdf.showPage()
    pdf.save()
    return path


def blank_text_pdf(path: Path) -> Path:
    """A PDF with text that is not a financial statement."""
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.drawString(72, 700, "Directors' report")
    pdf.drawString(72, 686, "The company had a good year.")
    pdf.showPage()
    pdf.save()
    return path


def line_of(pdf: Path, needle: str) -> str:
    text = PdfplumberExtractor().extract_pages(pdf)[0].text
    return next(line for line in text.split("\n") if needle in line)


def attribute(pdf, name, raw, normalised, quote, role=None):
    return {"attribute": name, "period_role": role, "raw_text": raw, "normalised_value": normalised,
            "page_number": 1, "evidence_quote": quote}  # fmt: skip


def field(pdf, name, role, raw, needle, label=None, scale="crore", currency="INR"):
    return {"field_name": name, "period_role": role, "raw_value": raw, "scale": scale, "currency": currency,
            "page_number": 1, "evidence_quote": line_of(pdf, needle), "line_item_label": label or needle}  # fmt: skip


def good_response(pdf: Path, field_changes=None, drop_attributes=()) -> str:
    """The reply a careful model would give for ``balance_sheet_pdf``."""
    header = line_of(pdf, "31 March 2025")
    attributes = [
        attribute(pdf, "entity_name", "Acme Industries Limited", "Acme Industries Limited", "Acme Industries Limited"),
        attribute(pdf, "period_end", "31 March 2025", "2025-03-31", header, "current"),
        attribute(pdf, "period_end", "31 March 2024", "2024-03-31", header, "comparative"),
        attribute(pdf, "statement_basis", "Consolidated", "consolidated", "Consolidated Balance Sheet"),
        attribute(pdf, "reporting_currency", "Rs.", "INR", "(Rs. in crore)"),
        attribute(pdf, "scale", "in crore", "crore", "(Rs. in crore)"),
    ]
    attributes = [a for a in attributes if a["attribute"] not in drop_attributes]
    fields = [
        field(pdf, "current_assets", "current", "1,482.30", "Total current assets"),
        field(pdf, "current_assets", "comparative", "1,356.75", "Total current assets"),
        field(pdf, "current_liabilities", "current", "900.00", "Total current liabilities"),
        field(pdf, "current_liabilities", "comparative", "850.00", "Total current liabilities"),
        field(pdf, "total_equity", "current", "600.00", "Total equity"),
        field(pdf, "total_equity", "comparative", "500.00", "Total equity"),
    ]
    for index, changes in (field_changes or {}).items():
        fields[index] = {**fields[index], **changes}
    return json.dumps({"attributes": attributes, "fields": fields})
