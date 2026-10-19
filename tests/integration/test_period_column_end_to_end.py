"""The period-column chain on real PDFs: ingest, words, structure, assignment (B-209).

Synthetic PDFs are generated with reportlab at test time. Header years are centred
over right-aligned figures, as in a typical statement. The fresh-process golden
(AC-OD1-24) covers the whole chain; it is regenerated only in a reviewed change.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from credit_intel.extraction.assignment import ColumnClaim, Failure, Outcome, check_column
from credit_intel.extraction.columns import StructureProblem, analyse_structure
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "column_check_golden.json"
PERIODS = {"2025": date(2025, 3, 31), "2024": date(2024, 3, 31)}

CHAIN_SCRIPT = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, sys.argv[2])\n"
    "import chain\n"
    "sys.stdout.buffer.write((json.dumps(chain.run(Path(sys.argv[1])), indent=2) + '\\n').encode('ascii'))\n"
)


def resolve(anchor):
    return PERIODS.get(anchor.text)


def statement_pdf(path: Path, rotation: int = 0, header: bool = True) -> Path:
    pdf = canvas.Canvas(str(path), invariant=1)
    if rotation:
        pdf.setPageRotation(rotation)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 760, "Consolidated Balance Sheet")
    if header:
        pdf.drawString(300, 740, "Note")
        pdf.drawCentredString(400, 740, "2025")
        pdf.drawCentredString(480, 740, "2024")
    rows = [
        ("Total assets", "14", "1,740.00", "1,600.00"),
        ("Total equity", "", "600.00", "(500.00)"),
        ("Finance costs", "", "-", "250.00"),
        ("Common stock and paid-in capital outstanding 7,434 and 7,434", "", "109,095", "100,923"),
    ]
    y = 720
    for label, note, current, comparative in rows:
        pdf.drawString(72, y, label if len(label) < 30 else label[:30])
        if len(label) >= 30:
            y -= 14
            pdf.drawString(72, y, label[30:])
        if note:
            pdf.drawString(305, y, note)
        pdf.drawRightString(412, y, current)
        pdf.drawRightString(492, y, comparative)
        y -= 14
    pdf.showPage()
    pdf.save()
    return path


def structure_of(path):
    (page,) = PdfplumberExtractor().extract_words(path, [1])
    return analyse_structure(page, resolve), page


def line_text(path, needle):
    text = PdfplumberExtractor().extract_pages(path)[0].text
    return next(line for line in text.split("\n") if needle in line)


@pytest.fixture
def pdf(tmp_path):
    return statement_pdf(tmp_path / "s.pdf")


def test_the_real_page_has_two_valid_columns_and_a_note_span(pdf):
    structure, _ = structure_of(pdf)

    assert structure.valid
    assert [c.period_end for c in structure.columns] == [date(2025, 3, 31), date(2024, 3, 31)]
    assert structure.note_span is not None
    assert structure.label_limit == structure.note_span.x0 < 300


@pytest.mark.parametrize(
    ("needle", "period", "raw"),
    [
        ("Total assets", date(2025, 3, 31), "1,740.00"),
        ("Total assets", date(2024, 3, 31), "1,600.00"),
        ("Total equity", date(2025, 3, 31), "600.00"),
        ("Total equity", date(2024, 3, 31), "(500.00)"),
        ("Finance costs", date(2025, 3, 31), "-"),
        ("Finance costs", date(2024, 3, 31), "250.00"),
    ],
)
def test_right_aligned_figures_are_assigned_to_their_centred_headers(pdf, needle, period, raw):
    structure, _ = structure_of(pdf)

    result = check_column(structure, ColumnClaim(period, raw, line_text(pdf, needle), True))

    assert result.outcome is Outcome.PASS and result.token.text == raw


def test_the_note_reference_is_never_the_value(pdf):
    structure, _ = structure_of(pdf)

    result = check_column(structure, ColumnClaim(date(2025, 3, 31), "14", line_text(pdf, "Total assets"), True))

    assert result.outcome is Outcome.FAIL and result.failure is Failure.VALUE_DIFFERS


def test_the_comparative_figure_for_the_current_period_is_rejected(pdf):
    structure, _ = structure_of(pdf)

    result = check_column(structure, ColumnClaim(date(2025, 3, 31), "1,600.00", line_text(pdf, "Total assets"), True))

    assert result.failure is Failure.VALUE_DIFFERS


def test_the_wrapped_label_numbers_are_never_values_and_the_figures_are_found(pdf):
    structure, _ = structure_of(pdf)
    quote = line_text(pdf, "109,095")

    current = check_column(structure, ColumnClaim(date(2025, 3, 31), "109,095", quote, True))
    label_number = check_column(structure, ColumnClaim(date(2025, 3, 31), "7,434", quote, True))

    assert current.token.text == "109,095"
    assert label_number.outcome is Outcome.FAIL


def test_a_rotated_page_is_unverifiable(tmp_path):
    structure, _ = structure_of(statement_pdf(tmp_path / "r.pdf", rotation=90))

    assert structure.problems == (StructureProblem.ROTATED,)


def test_a_page_without_a_header_has_no_usable_anchor(tmp_path):
    path = statement_pdf(tmp_path / "h.pdf", header=False)
    structure, _ = structure_of(path)

    assert structure.problems == (StructureProblem.NO_USABLE_ANCHOR,)
    result = check_column(structure, ColumnClaim(date(2025, 3, 31), "1,740.00", line_text(path, "Total assets"), True))
    assert result.failure is Failure.STRUCTURE_INVALID


# --- AC-OD1-24: the whole chain in a fresh process matches the golden output -------------------------------


def chain_source() -> str:
    return '''
from datetime import date

from credit_intel.extraction.assignment import ColumnClaim, check_column
from credit_intel.extraction.columns import analyse_structure
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

PERIODS = {"2025": date(2025, 3, 31), "2024": date(2024, 3, 31)}
CLAIMS = [
    ("Total assets", "2025", "1,740.00"), ("Total assets", "2024", "1,600.00"),
    ("Total assets", "2025", "14"), ("Total equity", "2024", "(500.00)"),
    ("Finance costs", "2025", "-"), ("Finance costs", "2024", "250.00"),
    ("109,095", "2025", "7,434"), ("109,095", "2025", "109,095"),
]


def run(path):
    extractor = PdfplumberExtractor()
    (page,) = extractor.extract_words(path, [1])
    structure = analyse_structure(page, lambda a: PERIODS.get(a.text))
    lines = extractor.extract_pages(path)[0].text.split("\\n")
    out = {
        "problems": [str(p) for p in structure.problems],
        "label_limit": structure.label_limit,
        "columns": [[str(c.period_end), c.x0, c.x1] for c in structure.columns],
        "note_span": [structure.note_span.x0, structure.note_span.x1],
        "checks": [],
    }
    for needle, year, raw in CLAIMS:
        quote = next(line for line in lines if needle in line)
        r = check_column(structure, ColumnClaim(PERIODS[year], raw, quote, True))
        out["checks"].append([
            needle, year, raw, str(r.outcome), str(r.failure),
            [str(x) for x in r.reasons], r.token.text if r.token else None,
        ])
    return out
'''


def test_the_whole_chain_in_a_fresh_process_matches_the_golden_output(pdf, tmp_path):
    (tmp_path / "chain.py").write_text(chain_source(), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-I", "-c", CHAIN_SCRIPT, str(pdf), str(tmp_path)],
        capture_output=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout == GOLDEN.read_bytes()


def test_the_golden_output_records_passes_and_failures():
    data = json.loads(GOLDEN.read_bytes())

    assert data["problems"] == [] and len(data["columns"]) == 2
    outcomes = [row[3] for row in data["checks"]]
    assert "pass" in outcomes and "fail" in outcomes
