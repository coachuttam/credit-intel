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


STANDALONE_ROWS = [
    ("Total non-current assets", "", "500.00", "450.00"),
    ("Total current assets", "14", "1,000.00", "900.00"),
    ("Total assets", "", "1,500.00", "1,350.00"),
    ("Total equity", "", "400.00", "350.00"),
    ("Total current liabilities", "15", "500.00", "450.00"),
]


def _statement_page(pdf, rows, title, scale):
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


def balance_sheet_pdf(path: Path, rows=ROWS, title="Consolidated Balance Sheet", scale="(Rs. in crore)",
                      narrative_page=None) -> Path:  # fmt: skip
    pdf = canvas.Canvas(str(path), invariant=1)
    _statement_page(pdf, rows, title, scale)
    if narrative_page:  # a second page that is not a statement
        pdf.setFont("Helvetica", 10)
        pdf.drawString(72, 700, narrative_page)
        pdf.showPage()
    pdf.save()
    return path


def two_basis_pdf(path: Path) -> Path:
    """A consolidated balance sheet on page 1 and a standalone one on page 2."""
    pdf = canvas.Canvas(str(path), invariant=1)
    _statement_page(pdf, ROWS, "Consolidated Balance Sheet", "(Rs. in crore)")
    _statement_page(pdf, STANDALONE_ROWS, "Standalone Balance Sheet", "(Rs. in crore)")
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


def line_of(pdf: Path, needle: str, page: int = 1) -> str:
    text = PdfplumberExtractor().extract_pages(pdf)[page - 1].text
    return next(line for line in text.split("\n") if needle in line)


def attribute(pdf, name, raw, normalised, quote, role=None):
    return {"attribute": name, "period_role": role, "raw_text": raw, "normalised_value": normalised,
            "page_number": 1, "evidence_quote": quote}  # fmt: skip


def field(pdf, name, role, raw, needle, label=None, scale="crore", currency="INR", page=1):
    return {"field_name": name, "period_role": role, "raw_value": raw, "scale": scale, "currency": currency,
            "page_number": page, "evidence_quote": line_of(pdf, needle, page), "line_item_label": label or needle}  # fmt: skip


def good_attributes(pdf: Path, drop=()) -> list[dict]:
    header = line_of(pdf, "31 March 2025")
    attributes = [
        attribute(pdf, "entity_name", "Acme Industries Limited", "Acme Industries Limited", "Acme Industries Limited"),
        attribute(pdf, "period_end", "31 March 2025", "2025-03-31", header, "current"),
        attribute(pdf, "period_end", "31 March 2024", "2024-03-31", header, "comparative"),
        attribute(pdf, "statement_basis", "Consolidated", "consolidated", "Consolidated Balance Sheet"),
        attribute(pdf, "reporting_currency", "Rs.", "INR", "(Rs. in crore)"),
        attribute(pdf, "scale", "in crore", "crore", "(Rs. in crore)"),
    ]
    return [a for a in attributes if a["attribute"] not in drop]


def standalone_fields(pdf: Path) -> list[dict]:
    """The same three fields read from the standalone statement on page 2."""
    return [
        field(pdf, "current_assets", "current", "1,000.00", "Total current assets", page=2),
        field(pdf, "current_assets", "comparative", "900.00", "Total current assets", page=2),
        field(pdf, "total_equity", "current", "400.00", "Total equity", page=2),
        field(pdf, "total_equity", "comparative", "350.00", "Total equity", page=2),
    ]


def reply(attributes, fields) -> str:
    return json.dumps({"attributes": attributes, "fields": fields})


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
