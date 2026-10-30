"""The report check (PRD FR-015 criterion 5, v0.4.56; step 3 of its build; B-328).

A PDF is built from a memo, or from a tampered copy of it, and checked against the real memo. The messages must never quote the memo.
"""

import io
import json
import sys
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "integration"))

from memo_results import GOLDEN, RUN_ID, WHEN  # noqa: E402
from test_memo_ocr import with_ocr  # noqa: E402

from credit_intel.memo.render import render_memo  # noqa: E402
from credit_intel.memo.sections import DRAFT_STATEMENT  # noqa: E402
from credit_intel.report import build_pdf, check, typeset  # noqa: E402


def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def memo_of(data):
    return render_memo(data, RUN_ID, WHEN)


@pytest.fixture(scope="module")
def memo():
    return memo_of(golden())


@pytest.fixture(scope="module")
def pdf(memo):
    return build_pdf(memo)


def small(extra="", section_9=True):
    tail = "\n## 9. Limitations and human-review requirements\n\n- A limit.\n" if section_9 else ""
    return f"# Draft credit memo\n\n**Run ID:** `{RUN_ID}`  \n\n> **{DRAFT_STATEMENT}**\n\n## 1. Borrower overview\n\n{extra}\n{tail}"


# --- a sound report -------------------------------------------------------------------------------------------


def test_the_report_of_the_golden_memo_has_no_problems(memo, pdf):
    assert check.problems(pdf, memo) == []


def test_the_report_of_a_run_with_ocr_has_no_problems():
    data, _ = with_ocr()
    memo = memo_of(data)
    assert check.problems(build_pdf(memo), memo) == []


def test_a_long_table_whose_header_repeats_on_each_page_is_sound():
    rows = "\n".join(f"| row-{n:03d} | value {n} | [UNVERIFIED] |" for n in range(150))
    memo = small("| Field | Value | Origin |\n|---|---|---|\n" + rows)
    assert check.problems(build_pdf(memo), memo) == []


def test_a_header_word_added_to_a_one_page_report_is_not_excused_as_a_repeated_header():
    memo = small("| Field | Value |\n|---|---|\n| a | b |")
    pdf = build_pdf(small("| Field | Value |\n|---|---|\n| a | b |\n\nField Value Field Value"))  # one page: a header cannot repeat
    assert any("text differs" in p and "added" in p for p in check.problems(pdf, memo))


def test_the_check_is_deterministic(memo, pdf):
    assert check.problems(pdf, memo) == check.problems(pdf, memo)


# --- a report that is not the memo ---------------------------------------------------------------------------------


def tampered(memo, old, new, count=1):
    assert memo.count(old) >= 1, old
    return build_pdf(memo.replace(old, new, count))


def test_a_swapped_digit_is_a_changed_word(memo):
    found = check.problems(tampered(memo, "1.65", "1.56"), memo)
    assert any("text differs" in p and "1 words missing, 1 added" in p for p in found)


def test_an_invented_value_is_found(memo):
    found = check.problems(tampered(memo, "## 2. Documents reviewed", "Invented 9,999.99 figure.\n\n## 2. Documents reviewed"), memo)
    assert any("added" in p and "text differs" in p for p in found)


def test_a_dropped_limitation_is_named_as_section_9_and_as_the_text(memo):
    line = next(l for l in memo.splitlines() if l.startswith("- ") and "Lease liabilities" in l)
    found = check.problems(build_pdf(memo.replace(line + "\n", "", 1)), memo)
    assert any(p.startswith("section 9 differs") for p in found) and any(p.startswith("the text differs") for p in found)


def test_a_label_that_is_missing_is_found(memo):
    found = check.problems(tampered(memo, " [SOURCE: p.1]", "", 1), memo)
    assert any(p.startswith("origin labels differ") and "1 missing" in p for p in found)


def test_a_label_that_was_added_is_found(memo):
    found = check.problems(tampered(memo, "## 2. Documents reviewed", "Extra [SOURCE: p.9] text.\n\n## 2. Documents reviewed"), memo)
    assert any(p.startswith("origin labels differ") and "1 added" in p for p in found)


def test_one_label_changed_to_another_is_both_missing_and_added(memo):
    found = check.problems(tampered(memo, "[SOURCE: p.1]", "[CALCULATED: extraction]"), memo)
    assert any(p.startswith("origin labels differ") and "1 missing, 1 added" in p for p in found)


def test_an_ocr_run_without_its_ocr_lines_and_labels_is_found():
    data, _ = with_ocr()
    memo = memo_of(data)
    line = next(l for l in memo.splitlines() if "Text read by OCR" in l)
    stripped = memo.replace(line + "\n", "", 1)
    found = check.problems(build_pdf(stripped), memo)
    assert any("OCR" in p for p in found)


def test_the_messages_never_quote_the_memo(memo):
    secret = "SECRETWORD7"
    found = check.problems(build_pdf(memo.replace("## 2. Documents reviewed", f"{secret} invented.\n\n## 2. Documents reviewed", 1)), memo)
    assert found and all(secret not in p and "Acme" not in p for p in found)


# --- the draft statement and the footers --------------------------------------------------------------------------------------


def with_footer(monkeypatch, draw):
    """A canvas class whose footer is drawn by ``draw(canvas, total)`` instead of the real one."""
    real = typeset._canvas_class

    def make(banner, run_id):
        base = real(banner, run_id)

        class Changed(base):
            def _footer(self, total):
                draw(self, total, banner, run_id)

        return Changed

    monkeypatch.setattr(typeset, "_canvas_class", make)


def test_a_first_page_without_the_draft_statement_box_is_found_even_if_the_footer_has_it(memo, monkeypatch):
    real = typeset._Typesetter._paragraph_open

    def without_banner(self, tokens, i, ctx):
        flows, nxt = real(self, tokens, i, ctx)
        return ([] if ctx == "banner" else flows), nxt

    monkeypatch.setattr(typeset._Typesetter, "_paragraph_open", without_banner)
    found = check.problems(build_pdf(memo), memo)
    assert "the draft statement is not on the first page" in found


def test_a_footer_missing_on_later_pages_is_found(memo, monkeypatch):
    real = typeset._canvas_class
    monkeypatch.setattr(typeset, "_canvas_class", lambda b, r: type("First", (real(b, r),), {"_footer": lambda self, total: real(b, r)._footer(self, total) if self._pageNumber == 1 else None}))
    found = check.problems(build_pdf(memo), memo)
    assert any("not in the footer of page 2" in p for p in found)


def test_a_footer_with_other_words_is_found(memo, monkeypatch):
    def draw(canvas, total, banner, run_id):
        canvas.drawString(50, 40, f"Run ID {run_id} Page {canvas._pageNumber} of {total}")
        canvas.drawString(50, 30, "Looks fine.")

    with_footer(monkeypatch, draw)
    found = check.problems(build_pdf(memo), memo)
    assert any("not in the footer of page 1" in p for p in found)


def test_wrong_page_numbers_are_found(memo, monkeypatch):
    def draw(canvas, total, banner, run_id):
        canvas.drawString(50, 40, banner)
        canvas.drawString(50, 30, f"Run ID {run_id} Page {canvas._pageNumber} of {total + 1}")

    with_footer(monkeypatch, draw)
    found = check.problems(build_pdf(memo), memo)
    assert any("lacks the run ID or the page numbers" in p for p in found)


def test_a_missing_run_id_in_the_footer_is_found(memo, monkeypatch):
    def draw(canvas, total, banner, run_id):
        canvas.drawString(50, 40, banner)
        canvas.drawString(50, 30, f"Page {canvas._pageNumber} of {total}")

    with_footer(monkeypatch, draw)
    assert any("lacks the run ID" in p for p in check.problems(build_pdf(memo), memo))


# --- nothing loaded or linked, and a PDF that cannot be read -----------------------------------------------------------------------------


def one_page(draw):
    buffer = io.BytesIO()
    canvas = Canvas(buffer, invariant=1)
    draw(canvas)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_a_link_annotation_is_found(memo):
    pdf = one_page(lambda c: c.linkURL("http://example.invalid/", (10, 10, 100, 40)))
    assert any("loads or links" in p for p in check.problems(pdf, memo))


def test_an_image_is_found(memo, tmp_path):
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    pdf = one_page(lambda c: c.drawImage(ImageReader(Image.new("RGB", (4, 4), "white")), 10, 10, 20, 20))
    assert any("loads or links" in p for p in check.problems(pdf, memo))


@pytest.mark.parametrize("name", [b"/JavaScript", b"/Launch", b"/OpenAction", b"/EmbeddedFile", b"/GoTo", b"/XFA"])
def test_a_script_or_action_name_in_the_pdf_is_found(memo, pdf, name):
    assert any("loads or links" in p for p in check.problems(pdf + b"\n<< " + name + b" >>\n", memo))


def test_bytes_that_are_not_a_pdf_cannot_be_read_back(memo):
    assert check.problems(b"this is not a pdf", memo) == ["the PDF cannot be read back"]


def test_a_pdf_with_no_pages_is_found(memo):
    from reportlab.pdfgen.canvas import Canvas as C

    buffer = io.BytesIO()
    C(buffer, invariant=1).save()
    found = check.problems(buffer.getvalue(), memo)
    assert found and found[-1] in ("the PDF has no pages", "the PDF cannot be read back")


def test_a_memo_without_section_9_is_reported_as_such():
    memo = small(section_9=False)
    found = check.problems(build_pdf(memo), memo)
    assert "section 9 is not in the report" in found


# --- the word comparison itself ---------------------------------------------------------------------------------------------------------


def test_words_ignore_bullets_dashes_edge_punctuation_and_layout():
    assert check._bag("• one — two, (three) 1,482.30. [UNVERIFIED]") == check._bag("one two (three) 1,482.30 [UNVERIFIED]")


def test_a_code_span_joined_to_its_neighbours_is_one_word():
    assert check._bag(check._memo_text("Name (`entity_name`): x")) == check._bag("Name (entity_name): x")


def test_an_ordered_lists_numbers_are_part_of_the_expected_text():
    assert check._bag(check._memo_text("3. third\n4. fourth\n")) == check._bag("3 third 4 fourth")
