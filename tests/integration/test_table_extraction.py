"""How statement tables survive page-text extraction (PRD D-01; input to OD-1).

Synthetic statement pages are drawn with right-aligned figure columns, as in
annual reports, and passed through the real pdfplumber extractor. Tests named
``..._known_limitation`` pin down layouts that default extraction does not
handle; they guard against silent changes in library behaviour and are not
behaviour the product relies on.
"""

from pathlib import Path

from reportlab.pdfgen import canvas

from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

X_LABEL, X_NOTE, X_CURRENT, X_COMPARATIVE = 60, 300, 440, 540
FONT, SIZE = "Helvetica", 9


def statement_page(path: Path, lines: list[tuple], *, current_offsets: dict[int, float] | None = None) -> str:
    """Draw ``(label, note, current, comparative)`` lines; return extracted text.

    Figures are right-aligned on the column edges. ``current_offsets`` raises
    the current-period figure of line ``i`` by that many points.
    """
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.setFont(FONT, SIZE)
    y = 760
    for i, (label, note, current, comparative) in enumerate(lines):
        if label:
            pdf.drawString(X_LABEL, y, label)
        if note:
            pdf.drawString(X_NOTE, y, note)
        if current:
            pdf.drawRightString(X_CURRENT, y + (current_offsets or {}).get(i, 0.0), current)
        if comparative:
            pdf.drawRightString(X_COMPARATIVE, y, comparative)
        y -= 16
    pdf.showPage()
    pdf.save()
    return PdfplumberExtractor().extract_pages(path)[0].text


HEADER = ("Particulars", "Note", "As at 31 March 2025", "As at 31 March 2024")


# --- Layouts that extract faithfully ----------------------------------------


def test_aligned_rows_keep_label_note_and_period_columns_in_order(tmp_path):
    text = statement_page(
        tmp_path / "bs.pdf",
        [HEADER, ("Borrowings", "14", "1,23,456.70", "98,765.40")],
    )

    assert text.splitlines() == [
        "Particulars Note As at 31 March 2025 As at 31 March 2024",
        "Borrowings 14 1,23,456.70 98,765.40",
    ]


def test_signs_nil_dashes_and_indian_grouping_are_kept_verbatim(tmp_path):
    text = statement_page(
        tmp_path / "pl.pdf",
        [
            ("Profit/(loss) for the year", None, "(245.10)", "312.40"),
            ("Borrowings", "15", "-", "120.00"),
            ("Current maturities of long-term borrowings", "15", "–", "45.00"),
            ("Exceptional items", "31", "(1,02,345.00)", "-12.00"),
        ],
    )

    assert text.splitlines() == [
        "Profit/(loss) for the year (245.10) 312.40",
        "Borrowings 15 - 120.00",
        "Current maturities of long-term borrowings 15 – 45.00",
        "Exceptional items 31 (1,02,345.00) -12.00",
    ]


def test_two_line_column_header_keeps_dates_in_column_order(tmp_path):
    text = statement_page(
        tmp_path / "hdr.pdf",
        [("", "", "As at", "As at"), ("Particulars", "Note", "31 March 2025", "31 March 2024")],
    )

    assert text.splitlines() == ["As at As at", "Particulars Note 31 March 2025 31 March 2024"]


def test_section_heading_stays_on_its_own_line_above_its_rows(tmp_path):
    text = statement_page(
        tmp_path / "sections.pdf",
        [
            ("Non-current liabilities", None, None, None),
            ("Borrowings", "14", "900.00", "850.00"),
            ("Current liabilities", None, None, None),
            ("Borrowings", "15", "300.00", "120.00"),
        ],
    )

    assert text.splitlines() == [
        "Non-current liabilities",
        "Borrowings 14 900.00 850.00",
        "Current liabilities",
        "Borrowings 15 300.00 120.00",
    ]


def test_value_offset_up_to_3pt_stays_on_its_row(tmp_path):
    text = statement_page(
        tmp_path / "offset3.pdf",
        [("Borrowings", "14", "1,23,456.70", "98,765.40")],
        current_offsets={0: 3.0},
    )

    assert text.splitlines() == ["Borrowings 14 1,23,456.70 98,765.40"]


# --- Known limitations of default text extraction -----------------------------


def test_blank_cell_leaves_no_placeholder_known_limitation(tmp_path):
    # The row has one fewer figure than there are period columns; text order
    # alone cannot tell which column is blank (OD-1).
    text = statement_page(tmp_path / "blank.pdf", [("Exceptional items", "31", "(1,02,345.00)", None)])

    assert text == "Exceptional items 31 (1,02,345.00)"


def test_value_offset_over_3pt_leaves_its_row_known_limitation(tmp_path):
    # The current figure moves to its own line; the row then shows the note
    # and the comparative figure only, so text order alone could attribute
    # the comparative figure to the current period (OD-1).
    text = statement_page(
        tmp_path / "offset4.pdf",
        [("Borrowings", "14", "1,23,456.70", "98,765.40")],
        current_offsets={0: 4.0},
    )

    assert text.splitlines() == ["1,23,456.70", "Borrowings 14 98,765.40"]


def test_figures_3pt_apart_merge_known_limitation(tmp_path):
    path = tmp_path / "tight.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.setFont(FONT, SIZE)
    pdf.drawString(X_LABEL, 700, "Borrowings")
    pdf.drawRightString(X_CURRENT, 700, "1,23,456.70")
    width = pdf.stringWidth("98,765.40", FONT, SIZE)
    pdf.drawRightString(X_CURRENT + 3 + width, 700, "98,765.40")
    pdf.showPage()
    pdf.save()

    assert PdfplumberExtractor().extract_pages(path)[0].text == "Borrowings 1,23,456.7098,765.40"


def test_letter_spacing_over_3pt_splits_a_figure_known_limitation(tmp_path):
    path = tmp_path / "spaced.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    text_object = pdf.beginText()
    text_object.setFont(FONT, SIZE)
    text_object.setTextOrigin(X_LABEL, 700)
    text_object.textOut("Borrowings ")
    text_object.setCharSpace(4)
    text_object.textOut("1,23,456.70")
    pdf.drawText(text_object)
    pdf.showPage()
    pdf.save()

    assert PdfplumberExtractor().extract_pages(path)[0].text == "Borrowings 1 , 2 3 , 4 5 6 . 7 0"
