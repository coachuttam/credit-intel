"""Word positions (PRD FR-005.7, OD-1 step 6a; B-206).

``WordExtractor`` is a separate interface; ``TextExtractor`` is unchanged. PDFs are
generated at test time with reportlab in pytest's temporary directories.
"""

import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from credit_intel.config import ColumnSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.extractor import TextExtractor, WordExtractor
from credit_intel.ingestion.models import PageWords, Word
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "word_extraction_golden.json"
A4 = (595.2756, 841.8898)

# One page of placed words: (x, y_from_bottom, text), Helvetica 10.
PAGE_ONE = [
    (72, 700, "Balance"),
    (150, 700, "Sheet"),
    (72, 680, "Total"),
    (300, 680, "1,740.00"),
    (400, 680, "(600.00)"),
]
PAGE_TWO: list[tuple[float, float, str]] = []  # blank page
PAGE_THREE = [(100, 500, "Third"), (200, 500, "page")]


def build(path: Path, pages, rotations=None) -> Path:
    pdf = canvas.Canvas(str(path), invariant=1)
    for index, words in enumerate(pages):
        if rotations:
            pdf.setPageRotation(rotations[index])
        pdf.setFont("Helvetica", 10)
        for x, y, text in words:
            pdf.drawString(x, y, text)
        pdf.showPage()
    pdf.save()
    return path


@pytest.fixture
def pdf(tmp_path):
    return build(tmp_path / "w.pdf", [PAGE_ONE, PAGE_TWO, PAGE_THREE])


def extract(path, numbers):
    return PdfplumberExtractor().extract_words(path, numbers)


# --- the interface -----------------------------------------------------------------


def test_pdfplumber_extractor_satisfies_both_interfaces():
    extractor = PdfplumberExtractor()

    text_extractor: TextExtractor = extractor
    word_extractor: WordExtractor = extractor

    assert text_extractor is word_extractor


def test_text_extractor_protocol_is_unchanged():
    assert {n for n in vars(TextExtractor) if not n.startswith("_")} == {"inspect", "extract_pages"}
    assert {n for n in vars(WordExtractor) if not n.startswith("_")} == {"extract_words"}


def test_models_are_frozen_value_objects():
    word = Word("a", 1.0, 2.0, 3.0, 4.0)
    page = PageWords(1, 595.0, 842.0, 0, (word,))

    with pytest.raises(dataclasses.FrozenInstanceError):
        word.x0 = 5.0  # type: ignore[misc]
    assert page.words == (word,)


# --- content ------------------------------------------------------------------------


def test_words_carry_text_and_positions(pdf):
    (page,) = extract(pdf, [1])

    assert [w.text for w in page.words] == ["Balance", "Sheet", "Total", "1,740.00", "(600.00)"]
    by_text = {w.text: w for w in page.words}
    assert by_text["Balance"].x0 == pytest.approx(72, abs=0.01)
    assert by_text["1,740.00"].x0 == pytest.approx(300, abs=0.01)
    assert by_text["1,740.00"].x1 > by_text["1,740.00"].x0
    assert by_text["Balance"].bottom > by_text["Balance"].top
    # Top-left origin: the first line (y=700) is nearer the top than the second (y=680).
    assert by_text["Balance"].top < by_text["Total"].top
    assert by_text["Balance"].top == pytest.approx(A4[1] - 700 - 10 * 0.9, abs=5)


def test_words_are_ordered_by_top_then_x0_then_text(pdf):
    (page,) = extract(pdf, [1])

    keys = [(w.top, w.x0, w.text) for w in page.words]
    assert keys == sorted(keys)


def test_blank_page_has_no_words(pdf):
    (page,) = extract(pdf, [2])

    assert page.words == () and page.page_number == 2


def test_only_requested_pages_are_returned_in_ascending_order(pdf):
    pages = extract(pdf, [3, 1])

    assert [p.page_number for p in pages] == [1, 3]
    assert [w.text for w in pages[1].words] == ["Third", "page"]


def test_numbering_agrees_with_extract_pages(pdf):
    text_pages = PdfplumberExtractor().extract_pages(pdf)
    word_pages = extract(pdf, [p.page_number for p in text_pages])

    assert [p.page_number for p in word_pages] == [p.page_number for p in text_pages]


# --- page size and rotation ------------------------------------------------------------


def test_width_and_height_are_the_page_size(pdf):
    (page,) = extract(pdf, [1])

    assert (page.width, page.height) == pytest.approx(A4, abs=0.01)
    assert page.rotation == 0


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotation_is_reported_and_size_stays_unrotated(tmp_path, rotation):
    path = build(tmp_path / "r.pdf", [PAGE_ONE], rotations=[rotation])

    (page,) = extract(path, [1])

    assert page.rotation == rotation
    assert (page.width, page.height) == pytest.approx(A4, abs=0.01)


# --- page lists ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "numbers",
    [[], [1, 1], [0], [4], [-1], [1, 4], [True], ["1"]],
    ids=["empty", "duplicate", "zero", "past end", "negative", "one past end", "bool", "string"],
)
def test_bad_page_lists_are_rejected_with_the_page_range_code(pdf, numbers):
    with pytest.raises(IngestionError) as excinfo:
        extract(pdf, numbers)

    assert excinfo.value.code is ErrorCode.PAGE_RANGE


def test_accepts_any_sequence_type(pdf):
    assert [p.page_number for p in extract(pdf, (2, 1))] == [1, 2]
    assert [p.page_number for p in extract(pdf, range(1, 4))] == [1, 2, 3]


# --- unreadable files ------------------------------------------------------------------


def test_missing_file_and_garbage_map_to_ingestion_errors(tmp_path):
    garbage = tmp_path / "g.pdf"
    garbage.write_bytes(b"%PDF-1.4 not really")

    for path in (tmp_path / "absent.pdf", garbage):
        with pytest.raises(IngestionError) as excinfo:
            extract(path, [1])
        assert excinfo.value.code is ErrorCode.CORRUPT


def test_extraction_does_not_modify_the_input(pdf):
    before = hashlib.sha256(pdf.read_bytes()).hexdigest()

    extract(pdf, [1, 2, 3])

    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == before


# --- tolerances are pinned -----------------------------------------------------------------


def gap_pdf(tmp_path, gap, name):
    # Two single-letter pieces whose edges are `gap` points apart.
    pdf_path = tmp_path / name
    pdf = canvas.Canvas(str(pdf_path), invariant=1)
    pdf.setFont("Helvetica", 10)
    width = pdf.stringWidth("A", "Helvetica", 10)
    pdf.drawString(100, 700, "A")
    pdf.drawString(100 + width + gap, 700, "B")
    pdf.showPage()
    pdf.save()
    return pdf_path


def test_pieces_two_points_apart_join_into_one_word(tmp_path):
    (page,) = extract(gap_pdf(tmp_path, 2, "g2.pdf"), [1])

    assert [w.text for w in page.words] == ["AB"]


def test_pieces_four_points_apart_stay_separate_words(tmp_path):
    (page,) = extract(gap_pdf(tmp_path, 4, "g4.pdf"), [1])

    assert [w.text for w in page.words] == ["A", "B"]


def test_vertical_tolerance_joins_pieces_within_three_points(tmp_path):
    path = tmp_path / "v.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.setFont("Helvetica", 10)
    width = pdf.stringWidth("A", "Helvetica", 10)
    pdf.drawString(100, 700, "A")
    pdf.drawString(100 + width, 698, "B")  # 2 pt lower, touching horizontally
    pdf.showPage()
    pdf.save()

    (page,) = extract(path, [1])

    assert [w.text for w in page.words] == ["AB"]


def test_spaces_split_words(tmp_path):
    path = build(tmp_path / "s.pdf", [[(72, 700, "Year Ended June 30,")]])

    (page,) = extract(path, [1])

    assert [w.text for w in page.words] == ["Year", "Ended", "June", "30,"]


# --- determinism (AC-OD1-24, words part) ---------------------------------------------------


def test_repeated_extraction_is_identical(pdf):
    assert extract(pdf, [1, 2, 3]) == extract(pdf, [1, 2, 3])


CHILD_SCRIPT = (
    "import dataclasses, json, sys\n"
    "from pathlib import Path\n"
    "from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor\n"
    "pages = PdfplumberExtractor().extract_words(Path(sys.argv[1]), [1, 2, 3])\n"
    "rows = [dataclasses.asdict(p) for p in pages]\n"
    "sys.stdout.buffer.write((json.dumps(rows, indent=2, ensure_ascii=True) + '\\n').encode('ascii'))\n"
)


def test_fresh_process_extraction_matches_the_golden_output(pdf):
    result = subprocess.run(
        [sys.executable, "-I", "-c", CHILD_SCRIPT, str(pdf)],
        capture_output=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout == GOLDEN.read_bytes()


def test_golden_output_covers_a_blank_page_and_all_fields():
    rows = json.loads(GOLDEN.read_bytes())

    assert [row["page_number"] for row in rows] == [1, 2, 3]
    assert rows[1]["words"] == []
    assert set(rows[0]) == {"page_number", "width", "height", "rotation", "words"}
    assert set(rows[0]["words"][0]) == {"text", "x0", "x1", "top", "bottom"}


# --- settings -------------------------------------------------------------------------------


def test_column_settings_defaults_are_the_provisional_values():
    settings = ColumnSettings()

    assert (settings.column_margin_pt, settings.line_tolerance_pt) == (3, 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.column_margin_pt = 4  # type: ignore[misc]
