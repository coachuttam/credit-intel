"""The memo and the traceability check for fields read by OCR (PRD v0.4.44, FR-005 criterion 11, K.0, K.10; B-320).

Step 1e of the OCR build. The results are the reviewed golden results with one field changed to what the verifier writes for a
field read by OCR, so the memo code and the checker run on the real shapes. No engine runs.
"""

import copy
import dataclasses
import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "integration"))

import pipeline_fixture as fx  # noqa: E402
from memo_results import GOLDEN, RUN_ID, WHEN  # noqa: E402
from memo_trace import problems  # noqa: E402

from credit_intel.export.results import build_results  # noqa: E402
from credit_intel.extraction.ocr_evidence import OcrRunRecord  # noqa: E402
from credit_intel.llm.provider import FakeProvider  # noqa: E402
from credit_intel.memo.limitations import OCR_SCOPE, SCOPE  # noqa: E402
from credit_intel.memo.questions import OCR_QUESTION, questions  # noqa: E402
from credit_intel.memo.render import render_memo  # noqa: E402
from credit_intel.memo.text import ocr_label  # noqa: E402
from credit_intel.run import run_pipeline  # noqa: E402
from credit_intel.states import Recorder  # noqa: E402

TARGET = "total_equity.2025-03-31.consolidated"
EVIDENCE = {
    "engine": "fake-ocr", "engine_version": "1.0", "dpi": 300,
    "min_word_confidence": "62.5", "mean_word_confidence": "82.2", "page_mean_confidence": "89.3",
}  # fmt: skip
BLOCK = {
    "engine": "fake-ocr", "engine_version": "1.0", "dpi": 300, "language": "eng",
    "pages_ocr": [{"page": 1, "mean_word_confidence": "89.3"}], "pages_text_layer": [2, 3],
}  # fmt: skip


def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def with_ocr(results=None, *, block=BLOCK, evidence=EVIDENCE, reason="ocr_unconfirmed", field_id=TARGET):
    """The golden results with ``field_id`` turned into a field read by OCR, and the run's OCR block."""
    data = copy.deepcopy(results or golden())
    record = next(r for r in data["fields"] if r["field_id"] == field_id)
    record.update(
        status="requires_review", status_reason=reason, value=None, currency=None,
        evidence_source="ocr", ocr_evidence=dict(evidence) if evidence else None,
    )  # fmt: skip
    if block is not None:
        data["extraction"]["ocr"] = copy.deepcopy(block)
    return data, record


def memo_of(data):
    return render_memo(data, RUN_ID, WHEN)


def section(memo, number):
    head = f"## {number}. "
    start = memo.index(head)
    nxt = memo.find("\n## ", start + 1)
    return memo[start : nxt if nxt != -1 else len(memo)]


# --- a run without OCR is unchanged -------------------------------------------------------------------------


def test_a_memo_without_ocr_has_no_ocr_label_line_or_legend_row():
    memo = memo_of(golden())

    assert "[OCR" not in memo and "Text read by OCR" not in memo and "OCR p.N" not in memo
    assert SCOPE[0] in memo and OCR_SCOPE not in memo and problems(memo, golden()) == []


# --- with OCR -------------------------------------------------------------------------------------------------


def test_the_memo_of_a_run_with_ocr_passes_the_traceability_check():
    data, _ = with_ocr()

    assert problems(memo_of(data), data) == []


def test_the_legend_gains_a_row_for_the_ocr_label():
    data, _ = with_ocr()
    head = memo_of(data).split("## 1. ")[0]

    assert "| `[OCR p.N, confidence …]` |" in head and "not a text layer" in head


def test_section_2_says_which_pages_were_read_by_ocr_with_the_engine_and_settings_and_which_from_the_text_layer():
    data, _ = with_ocr()
    two = section(memo_of(data), 2)

    assert "- **Text read by OCR:** page 1 (engine fake-ocr 1.0, 300 dpi, language eng) [CALCULATED: extraction]" in two
    assert "- **Text read from the text layer:** pages 2–3 [CALCULATED: extraction]" in two


def test_a_run_whose_pages_were_all_read_by_ocr_has_no_text_layer_line():
    data, _ = with_ocr(block={**BLOCK, "pages_text_layer": []})

    assert "Text read from the text layer" not in memo_of(data)


def test_the_field_appears_in_section_7_with_its_page_quote_and_the_ocr_label_not_the_source_label():
    data, record = with_ocr()
    seven = section(memo_of(data), 7)
    expected = ocr_label(record["page_number"], "82.2")

    assert expected in seven and f"[SOURCE: p.{record['page_number']}]" not in seven.split("**Requires review**")[1]
    assert f"> {record['evidence_quote'].split(' ')[0]}" in seven
    assert "ocr unconfirmed" in seven


def test_section_7_shows_the_three_confidences_and_says_they_are_not_a_measure_of_correctness():
    data, _ = with_ocr()
    seven = section(memo_of(data), 7)

    assert "lowest word 62.5, mean of the quote's words 82.2, page mean 89.3" in seven
    assert "not a measure of correctness" in seven


def test_a_missing_word_confidence_shows_n_a_in_the_label_and_not_available_in_the_text():
    data, _ = with_ocr(evidence={**EVIDENCE, "min_word_confidence": None, "mean_word_confidence": None})
    memo = memo_of(data)

    assert "[OCR p.1, confidence n/a]" in memo and "lowest word not available" in memo and problems(memo, data) == []


def test_the_table_row_of_an_ocr_field_is_unverified_and_shows_no_value():
    data, record = with_ocr()
    row = next(line for line in section(memo_of(data), 3).split("\n") if f"`{TARGET}`" in line)

    assert "requires review" in row and "[UNVERIFIED]" in row and "ocr unconfirmed" in row and "[SOURCE" not in row


def test_the_analyst_is_asked_to_check_the_value_against_the_page_image():
    data, record = with_ocr()
    asked = [q for q in questions(data) if "Total equity" in q]

    assert len(asked) == 1 and OCR_QUESTION == "Check this value against the page image."
    assert asked[0].endswith(f"{OCR_QUESTION} [UNVERIFIED]") and "read by OCR" in asked[0]
    assert "Confirm the figure from the audited statements" not in asked[0]


def test_an_ocr_field_that_failed_an_earlier_check_is_asked_the_same_question_and_its_reason_is_shown():
    data, _ = with_ocr(reason="scale_not_verified")
    asked = next(q for q in questions(data) if "Total equity" in q)

    assert "scale not verified" in asked and asked.endswith(f"{OCR_QUESTION} [UNVERIFIED]")


def test_a_text_layer_review_field_keeps_the_existing_question():
    data = golden()
    record = next(r for r in data["fields"] if r["field_id"] == TARGET)
    record.update(status="requires_review", status_reason="scale_not_verified", value=None, currency=None)

    asked = next(q for q in questions(data) if "Total equity" in q)

    assert "Confirm the figure from the audited statements" in asked and OCR_QUESTION not in asked


def test_section_9_states_the_ocr_limitation_in_place_of_no_ocr():
    data, _ = with_ocr()
    nine = section(memo_of(data), 9)

    assert OCR_SCOPE in nine and SCOPE[0] not in nine and "There is no OCR" not in nine
    assert "never accepted as extracted" in nine and "page image" in nine and "English only" in nine
    assert all(text in nine for text in SCOPE[1:]) and nine.count(OCR_SCOPE) == 1  # only the first scope line is replaced


def test_the_ocr_limitation_needs_no_escaping():
    from credit_intel.memo.text import esc

    assert esc(OCR_SCOPE) == OCR_SCOPE


def test_text_from_the_engine_name_is_escaped():
    data, _ = with_ocr(block={**BLOCK, "engine": "tess[1]*", "engine_version": "<b>"})
    memo = memo_of(data)

    assert "tess\\[1\\]\\*" in memo and "<b>" not in memo.replace("\\<b\\>", "")
    assert problems(memo, data) == []


# --- the checker catches what it should ----------------------------------------------------------------------


def test_the_checker_rejects_an_ocr_label_with_the_wrong_page():
    data, record = with_ocr()
    memo = memo_of(data).replace(ocr_label(record["page_number"], "82.2"), ocr_label(record["page_number"] + 1, "82.2"))

    assert any("is not the page and confidence of the field read by OCR" in p for p in problems(memo, data))


def test_the_checker_rejects_an_ocr_label_with_the_wrong_confidence():
    data, record = with_ocr()
    memo = memo_of(data).replace(ocr_label(record["page_number"], "82.2"), ocr_label(record["page_number"], "99.9"))

    assert any("is not the page and confidence" in p for p in problems(memo, data))


def test_the_checker_rejects_a_source_label_given_to_a_field_read_by_ocr():
    data, record = with_ocr()
    memo = memo_of(data).replace(ocr_label(record["page_number"], "82.2"), f"[SOURCE: p.{record['page_number']}]")

    assert any("given to a field read by OCR" in p for p in problems(memo, data))


def test_the_checker_rejects_an_ocr_label_beside_a_text_layer_field():
    data = golden()
    data["extraction"]["ocr"] = BLOCK  # OCR was used elsewhere, so the disclosure agrees
    record = next(r for r in data["fields"] if r["field_id"] == TARGET)
    assert record["evidence_source"] == "text_layer" and record["status"] == "extracted"
    memo = memo_of(data).replace("- **Page count:**", "- **Text read by OCR:** page 1\n- **Page count:**", 1)
    lines = memo.split("\n")
    row = next(n for n, line in enumerate(lines) if line.startswith(f"| `{TARGET}`"))
    assert f"[SOURCE: p.{record['page_number']}]" in lines[row]
    lines[row] = lines[row].replace(f"[SOURCE: p.{record['page_number']}]", ocr_label(record["page_number"], "82.2"))

    assert any("is not the page and confidence of the field read by OCR beside it" in p for p in problems("\n".join(lines), data))


def test_the_checker_rejects_an_ocr_field_in_results_that_record_no_use_of_ocr():
    data, _ = with_ocr(block=None)

    assert any("record no use of OCR" in p for p in problems(memo_of(data), data))


def test_the_checker_rejects_a_memo_that_does_not_disclose_the_ocr_the_results_record():
    data, _ = with_ocr()
    memo = memo_of(data)
    hidden = memo.replace("- **Text read by OCR:**", "- **Something else:**")

    assert any("does not agree with the results" in p for p in problems(hidden, data))


def test_the_checker_rejects_a_memo_that_claims_ocr_the_results_do_not_record():
    data, _ = with_ocr()
    memo = memo_of(data)
    plain = golden()

    assert any("does not agree with the results" in p for p in problems(memo, plain))


# --- results.json carries the OCR block only when OCR was used ------------------------------------------------


def run_result(tmp_path, ocr):
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")
    start = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
    ticks = iter(start + timedelta(milliseconds=7 * n) for n in range(1000))
    result = run_pipeline(pdf, FakeProvider(script=[fx.good_response(pdf)]), fx.LLM, recorder=Recorder(lambda: next(ticks)), cache_dir=tmp_path / "cache")
    extraction = dataclasses.replace(result.extraction, ocr=ocr)
    return build_results(extraction, result.metrics, result.rules)


def test_results_have_an_ocr_block_only_when_ocr_was_used(tmp_path):
    record = OcrRunRecord("fake-ocr", "1.0", 300, "eng", {1: Decimal("89.3")}, (2,))
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    assert run_result(tmp_path / "a", record)["extraction"]["ocr"] == record.to_manifest()
    assert "ocr" not in run_result(tmp_path / "b", None)["extraction"]
