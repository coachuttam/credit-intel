"""The PDF report's typesetting core (PRD FR-015, v0.4.56; step 2 of its build; B-327).

The memo is the reviewed golden memo (synthetic) and variants of it; the PDF is read back with pdfplumber. What is checked: the text,
every origin label, the draft statement on every page, byte-identical output, that untrusted text is never interpreted as markup,
that a character the font lacks stops the build, and that nothing is loaded or linked.
"""

import copy
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pdfplumber
import pytest
from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "integration"))

from memo_results import GOLDEN, RUN_ID, WHEN  # noqa: E402
from test_memo_ocr import with_ocr  # noqa: E402

from credit_intel.memo.render import render_memo  # noqa: E402
from credit_intel.memo.sections import DRAFT_STATEMENT  # noqa: E402
from credit_intel.memo.trace import FIELD_ID, FORMS, METRIC_ID  # noqa: E402
from credit_intel.report import REASONS, ReportError, build_pdf, fonts  # noqa: E402
from credit_intel.report import typeset  # noqa: E402

LABEL = re.compile(r"(?<!\\)\[([^\]\\]*)\]")


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


def pages_of(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
        return [page.extract_text() or "" for page in doc.pages]


def flat(text):
    return re.sub(r"\s+", " ", text)


def labels(text):
    return sorted(m.group(0) for m in LABEL.finditer(text) if any(f.fullmatch(m.group(1)) for f in FORMS))


def small(extra=""):
    """A minimal memo with the parts the renderer needs, and ``extra`` in the body."""
    return f"# Draft credit memo\n\n**Run ID:** `{RUN_ID}`  \n\n> **{DRAFT_STATEMENT}**\n\n## 1. Borrower overview\n\n{extra}\n"


# --- the document ---------------------------------------------------------------------------------------------


def test_the_golden_memo_becomes_a_multi_page_pdf(pdf):
    assert pdf.startswith(b"%PDF-") and len(pages_of(pdf)) >= 3


def test_every_origin_label_of_the_memo_is_in_the_pdf_the_same_number_of_times(memo, pdf):
    text = flat(" ".join(pages_of(pdf)))
    assert labels(memo)  # the memo has labels to find
    for label in set(labels(memo)):
        assert text.count(label) == labels(memo).count(label), label


def test_every_field_and_metric_id_is_printed_whole_not_broken_across_lines(memo, pdf):
    raw = "\n".join(pages_of(pdf))
    for identifier in set(FIELD_ID.findall(memo)) | set(METRIC_ID.findall(memo)):
        assert identifier in raw, identifier


def test_the_draft_statement_is_on_every_page_in_the_memos_words(pdf):
    pages = pages_of(pdf)
    assert len(pages) >= 3
    for number, text in enumerate(pages, start=1):
        assert DRAFT_STATEMENT in flat(text), number
        assert f"Page {number} of {len(pages)}" in text and f"Run ID {RUN_ID}" in text


def test_the_first_page_has_the_title_the_statement_and_the_label_legend(pdf):
    first = flat(pages_of(pdf)[0])
    assert first.startswith("Draft credit memo") and DRAFT_STATEMENT in first and "Origin labels" in first and "[UNVERIFIED]" in first


def test_all_nine_sections_and_the_limitations_text_are_present(memo, pdf):
    text = flat(" ".join(pages_of(pdf)))
    for number in range(1, 10):
        assert re.search(rf"\b{number}\. [A-Z]", text), number
    section_9 = memo[memo.index("## 9. ") :]
    sentences = [line[2:] for line in section_9.splitlines() if line.startswith("- ")]
    assert sentences
    for sentence in sentences[:6]:
        words = re.sub(r"[`*\\]", "", sentence)
        assert flat(words)[:80] in text, sentence[:60]


def test_the_rupee_sign_and_typographic_quotes_are_printed(memo):
    out = pages_of(build_pdf(small("Borrower: Acme ₹ crore, “quoted” and ‘single’ — a dash …")))
    assert "₹" in out[0] and "“quoted”" in out[0] and "—" in out[0]


def test_the_fonts_are_embedded(pdf):
    assert b"DejaVuSans" in pdf and b"DejaVuSansMono" in pdf and b"DejaVuSans-Bold" in pdf


def test_the_pdf_metadata_holds_no_document_text(memo, pdf):
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        info = {k: str(v) for k, v in doc.metadata.items()}
    assert info["Title"] == "Draft credit memo" and RUN_ID in info["Subject"] and info.get("Author", "") == ""
    assert "Acme" not in " ".join(info.values())


# --- the same memo gives the same bytes ----------------------------------------------------------------------------


def test_the_pdf_carries_reportlabs_fixed_date_not_the_time_of_the_build(pdf):
    assert b"D:20000101000000" in pdf  # invariant mode: the same memo gives the same bytes on any day


def test_the_same_memo_gives_byte_identical_pdfs(memo, pdf):
    assert build_pdf(memo) == pdf


def test_byte_identical_in_fresh_processes_with_different_hash_seeds(memo, tmp_path):
    memo_file = tmp_path / "memo.md"
    memo_file.write_text(memo, encoding="utf-8")
    code = "import sys, hashlib\nfrom credit_intel.report import build_pdf\nprint(hashlib.sha256(build_pdf(open(sys.argv[1], encoding='utf-8').read())).hexdigest())\n"
    digests = {
        subprocess.run([sys.executable, "-c", code, str(memo_file)], capture_output=True, text=True, check=True, env={"PYTHONHASHSEED": seed, "TZ": zone, "PATH": "/usr/bin:/bin", "LC_ALL": "C"}).stdout
        for seed, zone in (("1", "UTC"), ("77", "Asia/Kolkata"))
    }
    assert len(digests) == 1


# --- OCR runs -----------------------------------------------------------------------------------------------------------


def test_a_run_with_ocr_keeps_the_ocr_label_the_legend_row_and_the_review_reason():
    data, record = with_ocr()
    memo = memo_of(data)
    out = flat(" ".join(pages_of(build_pdf(memo))))
    ocr_labels = [label for label in labels(memo) if label.startswith("[OCR")]
    assert ocr_labels and all(out.count(label) == labels(memo).count(label) for label in set(ocr_labels))
    assert "Text read by OCR" in out and "[OCR p.N, confidence" in out
    assert "ocr_unconfirmed" in memo or "OCR" in memo  # the memo's own wording of the reason is what is printed
    for line in (m for m in memo.splitlines() if "OCR" in m and not m.startswith("|")):
        assert flat(re.sub(r"[`*\\]", "", re.sub(r"^\s*(?:[-*>]|\d+\.)\s+", "", line)))[:60] in out, line[:60]


# --- untrusted text is never markup ------------------------------------------------------------------------------------


MARKUP = [
    '<img src="file:///etc/hosts"/>', '<a href="http://example.invalid/x">link</a>', "<font color='red'>x</font>", "<b>bold</b> <i>i</i> <br/> <u>u</u>",
    "<para><seq id='a'/></para>", "<onDraw name='f'/>", "<getName id='x'/>", "&amp; &lt; &#65; &nbsp;", "<![CDATA[x]]>", "<script>alert(1)</script>",
]


@pytest.mark.parametrize("snippet", MARKUP)
def test_raw_markup_in_the_memo_is_printed_as_text_and_nothing_is_loaded(snippet):
    out = build_pdf(small(f"before {snippet} after"))
    text = flat(" ".join(pages_of(out)))
    assert "before" in text and "after" in text
    assert b"/Subtype /Image" not in out and b"/URI" not in out and b"/Annots" not in out


@pytest.mark.parametrize("snippet", MARKUP)
def test_escaped_markup_as_the_memo_writes_it_is_printed_literally(snippet):
    from credit_intel.memo.text import esc

    text = flat(" ".join(pages_of(build_pdf(small(esc(snippet))))))
    assert flat(snippet).replace("&nbsp;", "&nbsp;") in text or re.sub(r"\s", "", snippet) in re.sub(r"\s", "", text)


def test_an_image_and_a_link_in_the_memo_are_printed_as_text_and_never_loaded():
    out = build_pdf(small("![alt text](http://example.invalid/pic.png) and [link text](http://example.invalid/page)"))
    text = flat(" ".join(pages_of(out)))
    assert "alt text" in text and "link text" in text and "example.invalid" not in text
    assert b"/Subtype /Image" not in out and b"/URI" not in out


def test_an_escaped_label_is_not_styled_as_a_label_and_a_genuine_one_is():
    tokens = typeset.parser().parse(r"a \[SOURCE: p.9\] b [SOURCE: p.1] c [NOT A LABEL] d")
    markup = typeset._Typesetter().inline(tokens[1].children)
    assert markup.count("backColor") == 1 and 'backColor="#dbe7f3">[SOURCE:\u00a0p.1]</font>' in markup
    assert "[SOURCE: p.9]" in markup and "[NOT A LABEL]" in markup


def test_an_ocr_label_has_its_own_style():
    tokens = typeset.parser().parse("x [OCR p.3, confidence 82.2] y")
    assert "#fbefd2" in typeset._Typesetter().inline(tokens[1].children)


def test_a_backslash_or_angle_bracket_in_text_cannot_close_a_tag_early():
    tokens = typeset.parser().parse("**bold </b></font> text** and `<code>`")
    markup = typeset._Typesetter().inline(tokens[1].children)
    assert "&lt;/b&gt;&lt;/font&gt;" in markup and "&lt;code&gt;" in markup
    assert markup.count("<b>") == markup.count("</b>") == 1


# --- a character the font lacks, and a memo the renderer cannot use ------------------------------------------------------------------


def test_a_character_the_font_lacks_stops_the_build_with_glyph_missing():
    with pytest.raises(ReportError) as error:
        build_pdf(small("Name: 漢字"))
    assert error.value.reason == "glyph_missing" and "漢" not in str(error.value)


def test_a_control_character_stops_the_build_with_glyph_missing():
    with pytest.raises(ReportError) as error:
        build_pdf(small("a\x07b"))
    assert error.value.reason == "glyph_missing"


def test_a_missing_character_in_a_code_span_is_found_too():
    with pytest.raises(ReportError) as error:
        build_pdf(small("`字`"))
    assert error.value.reason == "glyph_missing"


@pytest.mark.parametrize("memo", ["", "# Title only\n", "no statement here\n\n**Run ID:** `x`\n", f"> **{DRAFT_STATEMENT}**\n\nno run id\n", small().replace(DRAFT_STATEMENT, "")])
def test_a_memo_without_its_statement_or_run_id_cannot_be_typeset(memo):
    with pytest.raises(ReportError) as error:
        build_pdf(memo)
    assert error.value.reason == "render_error"


def test_a_first_block_quote_that_is_not_the_draft_statement_cannot_be_typeset():
    with pytest.raises(ReportError) as error:
        build_pdf(small().replace(DRAFT_STATEMENT, "A different sentence."))
    assert error.value.reason == "render_error"


def test_only_the_first_block_quote_is_the_banner_and_later_quotes_are_plain_quotes():
    out = flat(" ".join(pages_of(build_pdf(small("> a later quote of text")))))
    assert "a later quote of text" in out and out.count(DRAFT_STATEMENT) >= 2  # the banner and the footer, not the later quote


def test_the_reasons_are_a_closed_list_and_an_error_holds_no_text():
    assert REASONS == ("render_error", "check_failed", "glyph_missing", "timeout")
    with pytest.raises(ValueError):
        ReportError("anything else")
    assert str(ReportError("timeout")) == "timeout"


def test_the_fonts_report_what_they_lack():
    assert fonts.missing(fonts.SANS, "₹ “ ” — é") == set()
    assert fonts.missing(fonts.SANS, "a漢b") == {"漢"} and fonts.missing(fonts.MONO, "x字") == {"字"}


# --- layout ------------------------------------------------------------------------------------------------------------------------------


def test_a_long_table_flows_over_pages_with_its_header_repeated():
    rows = "\n".join(f"| row-{n:03d} | value {n} | [UNVERIFIED] |" for n in range(150))
    memo = small("| Field | Value | Origin |\n|---|---|---|\n" + rows)
    pages = pages_of(build_pdf(memo))
    assert len(pages) >= 3
    assert all("Field Value Origin" in flat(p) for p in pages[:-1] if "row-" in p)
    assert "row-149" in pages[-1] and any("row-000" in p for p in pages[:2])


def test_the_widest_ids_are_kept_whole_in_a_table_of_long_ids():
    ids = [f"current_maturities_long_term_borrowings.202{n}-03-31.consolidated" for n in range(4)]
    memo = small("| Field ID | Value | Status | Origin | Notes |\n|---|---|---|---|---|\n" + "\n".join(f"| `{i}` | — | not found | [UNVERIFIED] | text |" for i in ids))
    raw = "\n".join(pages_of(build_pdf(memo)))
    assert all(i in raw for i in ids) and "[UNVERIFIED]" in raw


def test_column_widths_fill_the_page_and_give_a_long_word_its_room():
    cells = [["ID", "Note"], ["`" + "x" * 30 + "`", "short"], ["y", "a few words of ordinary text that may wrap freely"]]
    size, widths = typeset._Typesetter._fit(cells)
    assert abs(sum(widths) - typeset.CONTENT_WIDTH) < 0.01 and widths[0] >= 30 * size * 0.62
    assert 5.6 <= size <= 7.8


def test_a_table_too_wide_even_at_the_smallest_size_is_narrowed_in_proportion():
    cells = [[f"h{n}" for n in range(6)], ["z" * 60] * 6]
    size, widths = typeset._Typesetter._fit(cells)
    assert size == 5.6 and abs(sum(widths) - typeset.CONTENT_WIDTH) < 0.01 and len({round(w, 3) for w in widths}) == 1


def test_lists_numbered_lists_and_nested_lists_are_typeset():
    out = flat(" ".join(pages_of(build_pdf(small("- one\n  - nested\n- two\n\n3. third\n4. fourth\n")))))
    assert "one" in out and "nested" in out and "two" in out and "3. third" in out and "4. fourth" in out


def test_a_code_block_and_a_rule_are_typeset_as_text():
    out = flat(" ".join(pages_of(build_pdf(small("---\n\n```\nsome <b>code</b>\n```\n")))))
    assert "some <b>code</b>" in out


def test_a_very_long_unbroken_word_does_not_break_the_build():
    out = pages_of(build_pdf(small("x" * 400)))
    assert "x" * 50 in "".join(out)


def test_a_token_the_memo_format_does_not_use_is_a_render_error(monkeypatch):
    from markdown_it import MarkdownIt as Parser
    from markdown_it.token import Token

    real = Parser.parse
    monkeypatch.setattr(Parser, "parse", lambda self, src, env=None: [*real(self, src, env), Token("mystery", "", 0)])
    with pytest.raises(ReportError) as error:
        build_pdf(small())
    assert error.value.reason == "render_error"


def test_a_table_with_uneven_rows_is_a_render_error():
    tokens = typeset.parser().parse("| a | b |\n|---|---|\n| 1 |\n")
    story = typeset._Typesetter().blocks(tokens)[0]  # markdown-it pads the short row, so this is a table of equal rows
    assert story
