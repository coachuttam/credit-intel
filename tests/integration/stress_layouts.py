"""Synthetic statements that vary one layout factor at a time, with the reply a perfect model would give (Phase 7c). Not a test module.

The model is replaced by a scripted reply that is right by construction, so what a variant measures is the deterministic part of the
pipeline alone (locator, basis gate, declarations, period columns, row labels, number reading) on that layout. Every value is synthetic.
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from reportlab.pdfgen import canvas

import pipeline_fixture as fx
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import load_prompt
from credit_intel.ingestion.errors import IngestionError
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import StatementBasis

# field name, label as printed in the base layout, current, comparative (the same synthetic figures in every variant)
BASE_ROWS = (
    ("current_assets", "Total current assets", "1,482.30", "1,356.75"),
    ("total_equity", "Total equity", "600.00", "500.00"),
    ("current_liabilities", "Total current liabilities", "900.00", "850.00"),
)
EXPECTED = len(BASE_ROWS) * 2


@dataclass(frozen=True)
class Layout:
    """One statement page. Every default is the base layout, which a perfect model reads in full."""

    title: str = "Consolidated Balance Sheet"
    scale_line: str | None = "(Rs. in crore)"
    date_line: str | None = None
    headers: tuple[str, str] = ("31 March 2025", "31 March 2024")
    period_current: str = "2025-03-31"
    period_comparative: str = "2024-03-31"
    labels: tuple[str, str, str] = ("Total current assets", "Total equity", "Total current liabilities")
    figures: tuple[tuple[str, str], ...] = (("1,482.30", "1,356.75"), ("600.00", "500.00"), ("900.00", "850.00"))
    values: tuple[tuple[str, str], ...] = (("1,482.30", "1,356.75"), ("600.00", "500.00"), ("900.00", "850.00"))  # what the model reports as the raw value
    note_header: bool = True
    comparative_first: bool = False
    scale_token: str = "crore"  # the model's reading of the scale
    currency_code: str = "INR"
    scale_quote_needle: str = "in crore"  # the part of the declaration line the model quotes as the scale
    currency_quote_needle: str = "Rs."
    currency_raw: str = "Rs."
    scale_raw: str = "in crore"
    basis_raw: str = "Consolidated"
    basis_value: str = "consolidated"
    wrap_labels: bool = False  # the label breaks over two lines and the figures sit on the second
    second_page_from: int | None = None  # the statement continues on a second page that repeats the title, from this row on
    second_page_headers: tuple[str, str] | None = None  # the column headings of the second page, if they differ (a year-only heading, say)
    filler: tuple[tuple[str, str, str], ...] = ()  # rows the model is not asked about, printed first (so that a page holds enough statement lines to be found)
    page_range: str | None = None  # the pages the run is given (the analyst's range, which replaces the locator)
    wrap_figures_first: bool = False  # the label breaks over two lines and the figures sit on the first
    asserted: bool = False  # the run gives the page and asserts the basis (a title that names none)
    extra: dict = field(default_factory=dict)


def build(path: Path, layout: Layout) -> Path:
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.setFont("Helvetica", 10)
    y = 780
    for text in ("Acme Industries Limited", layout.title, layout.scale_line, layout.date_line):
        if text:
            pdf.drawString(72, y, text)
            y -= 15
    first, second = (layout.headers[1], layout.headers[0]) if layout.comparative_first else layout.headers
    if layout.note_header:
        pdf.drawString(300, y, "Note")
    pdf.drawCentredString(400, y, first)
    pdf.drawCentredString(480, y, second)
    y -= 15
    for label, current, comparative in layout.filler:
        pdf.drawString(72, y, label)
        pdf.drawRightString(430, y, current)
        pdf.drawRightString(510, y, comparative)
        y -= 14
    for index, (label, (current, comparative)) in enumerate(zip(layout.labels, layout.figures, strict=True)):
        if layout.second_page_from is not None and index == layout.second_page_from:
            pdf.showPage()  # the second page repeats the title and the column headings, and carries no scale declaration of its own
            pdf.setFont("Helvetica", 10)
            y = 780
            pdf.drawString(72, y, layout.title)
            y -= 15
            if layout.note_header:
                pdf.drawString(300, y, "Note")
            heads = layout.second_page_headers or (first, second)
            pdf.drawCentredString(400, y, heads[0])
            pdf.drawCentredString(480, y, heads[1])
            y -= 15
        cur, cmp_ = (comparative, current) if layout.comparative_first else (current, comparative)
        if layout.wrap_labels and " " in label:
            head, _, tail = label.rpartition(" ")
            pdf.drawString(72, y, head)
            y -= 12
            pdf.drawString(72, y, tail)
            pdf.drawRightString(430, y, cur)
            pdf.drawRightString(510, y, cmp_)
        elif layout.wrap_figures_first and " " in label:
            head, _, tail = label.rpartition(" ")
            pdf.drawString(72, y, head)
            pdf.drawRightString(430, y, cur)
            pdf.drawRightString(510, y, cmp_)
            y -= 12
            pdf.drawString(72, y, tail)
        else:
            pdf.drawString(72, y, label)
            pdf.drawRightString(430, y, cur)
            pdf.drawRightString(510, y, cmp_)
        y -= 14
    pdf.showPage()
    pdf.save()
    return path


def ideal_reply(pdf: Path, layout: Layout) -> str:
    """What a careful model would answer for the page."""
    header_line = fx.line_of(pdf, layout.headers[0] if not layout.comparative_first else layout.headers[1])
    scale_line = layout.scale_line or ""
    attributes = [
        fx.attribute(pdf, "entity_name", "Acme Industries Limited", "Acme Industries Limited", "Acme Industries Limited"),
        fx.attribute(pdf, "period_end", layout.headers[0], layout.period_current, header_line, "current"),
        fx.attribute(pdf, "period_end", layout.headers[1], layout.period_comparative, header_line, "comparative"),
        fx.attribute(pdf, "statement_basis", layout.basis_raw, layout.basis_value, layout.title),
    ]
    if layout.scale_line:
        attributes += [
            fx.attribute(pdf, "reporting_currency", layout.currency_raw, layout.currency_code, scale_line),
            fx.attribute(pdf, "scale", layout.scale_raw, layout.scale_token, scale_line),
        ]
    fields = []
    for index, ((name, _, _, _), label, (cur_value, cmp_value)) in enumerate(zip(BASE_ROWS, layout.labels, layout.values, strict=True)):
        needle = label.rpartition(" ")[2] if layout.wrap_labels and " " in label else (label.rpartition(" ")[0] if layout.wrap_figures_first and " " in label else label)
        page = 2 if layout.second_page_from is not None and index >= layout.second_page_from else 1
        for role, value in (("current", cur_value), ("comparative", cmp_value)):
            fields.append(fx.field(pdf, name, role, value, needle, label=label, scale=layout.scale_token, currency=layout.currency_code, page=page))
    return json.dumps({"attributes": attributes, "fields": fields})


def run_layout(tmp_path: Path, layout: Layout, name: str = "stress.pdf") -> dict:
    """Run the pipeline offline on one layout with the ideal reply. Returns counts and enum words only."""
    pdf = build(tmp_path / name, layout)
    kwargs = {"page_range": "1", "assert_basis": StatementBasis(layout.basis_value)} if layout.asserted else {}
    if layout.page_range is not None:
        kwargs["page_range"] = layout.page_range
    cache = tmp_path / f".cache_{name}"
    try:
        result = run_extraction(pdf, FakeProvider(script=[ideal_reply(pdf, layout)]), fx.LLM, cache_dir=cache, prompt=load_prompt(), **kwargs)
    except IngestionError as error:
        return {"stopped": error.code.value, "extracted": 0, "of": EXPECTED, "reasons": {}}
    records = result.field_set.fields
    reasons: dict[str, int] = {}
    for record in records:
        if record.status_reason and record.status.value != "not_found":  # the reasons of a field that was proposed and failed a check
            reasons[record.status_reason.value] = reasons.get(record.status_reason.value, 0) + 1
    right = sum(
        1
        for record in records
        if record.status.value == "extracted"
        and any(
            record.field_name.value == name_ and str(record.value) == _scaled(layout, printed)
            for (name_, _, _, _), (cv, mv) in zip(BASE_ROWS, layout.figures, strict=True)  # the truth is what the page prints
            for printed in (cv if record.period_role.value == "current" else mv,)
        )
    )
    return {"stopped": None, "extracted": sum(r.status.value == "extracted" for r in records), "right": right, "of": EXPECTED, "reasons": dict(sorted(reasons.items()))}


def _scaled(layout: Layout, printed: str) -> str:
    from decimal import Decimal

    from credit_intel.extraction.normalise import apply_scale, parse_value
    from credit_intel.models import Scale

    parsed = parse_value(printed)
    assert parsed is not None
    return str(apply_scale(parsed.value, Scale(layout.scale_token)))


def variant(**changes) -> Layout:
    return replace(Layout(), **changes)


NEG = (("1,482.30", "1,356.75"), ("(600.00)", "500.00"), ("900.00", "850.00"))
FILLER = (("Total assets", "2,282.30", "2,056.75"),)
LAKH = (("14,82,300.50", "13,56,750.25"), ("6,00,000.00", "5,00,000.00"), ("9,00,000.00", "8,50,000.00"))

# name -> (layout, what the matrix is for). The base layout is read in full by a perfect model; each other one changes a single factor.
VARIANTS: dict[str, Layout] = {
    "base": variant(),
    "labels with item markers": variant(labels=("(a) Total current assets", "(b) Total equity", "(c) Total current liabilities")),
    "labels in capitals": variant(labels=("TOTAL CURRENT ASSETS", "TOTAL EQUITY", "TOTAL CURRENT LIABILITIES")),
    "labels without the word total": variant(labels=("Current assets", "Equity", "Current liabilities")),
    "one label a synonym": variant(labels=("Total current assets", "Shareholders' funds", "Total current liabilities")),
    "labels wrapped, figures on the second line": variant(wrap_labels=True),
    "labels wrapped, figures on the first line": variant(wrap_figures_first=True),
    "title names no basis, basis asserted": variant(title="Balance Sheet", asserted=True),
    "title names no basis, not asserted": variant(title="Balance Sheet"),
    "title is statement of financial position": variant(title="Consolidated Statement of Financial Position"),
    "title is statement of assets and liabilities": variant(title="Consolidated Statement of Assets and Liabilities"),
    "header March 31, 2025": variant(headers=("March 31, 2025", "March 31, 2024")),
    "header 31.03.2025": variant(headers=("31.03.2025", "31.03.2024")),
    "header years under As at": variant(headers=("2025", "2024"), date_line="As at March 31,", note_header=False),
    "header Dec 31, 2025": variant(headers=("Dec 31, 2025", "Dec 31, 2024"), period_current="2025-12-31", period_comparative="2024-12-31"),
    "header FY 2024-25": variant(headers=("FY 2024-25", "FY 2023-24")),
    "comparative column first": variant(comparative_first=True),
    "no notes column": variant(note_header=False),
    "scale in lakhs": variant(scale_line="(Rs. in lakhs)", scale_token="lakh", scale_raw="in lakhs"),
    "US dollars in millions, written out": variant(scale_line="(Amounts in millions of U.S. dollars)", scale_token="millions", currency_code="USD", currency_raw="U.S. dollars", scale_raw="millions"),
    "dollar sign in millions": variant(scale_line="($ in millions)", scale_token="millions", currency_code="USD", currency_raw="$", scale_raw="in millions"),
    "no scale or currency declared": variant(scale_line=None),
    "lakh digit grouping": variant(figures=LAKH, values=LAKH),
    "a negative figure in brackets": variant(figures=NEG, values=NEG),
    "statement on two pages, run by the locator": variant(second_page_from=1, filler=FILLER),
    "statement on two pages, pages given": variant(second_page_from=1, filler=FILLER, page_range="1-2"),
    "second page headed by years only, pages given": variant(second_page_from=1, filler=FILLER, page_range="1-2", second_page_headers=("2025", "2024")),
}


def matrix(tmp_path: Path) -> dict[str, dict]:
    results = {}
    for number, (name, layout) in enumerate(VARIANTS.items()):
        results[name] = run_layout(tmp_path, layout, name=f"v{number}.pdf")
    return results


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        for name, result in matrix(Path(directory)).items():
            shown = result["stopped"] or (f"{result['right']}/{result['of']}" + (f" {result['reasons']}" if result["reasons"] else ""))
            print(f"{name:48s} {shown}")
