"""The OCR boundary: models, the engine interface and the offline fake (PRD v0.4.44, FR-001A, D-15; step 1b; B-317).

Nothing here reads a scan. The fake engine follows the ``OcrExtractor`` contract so later steps can be tested without an engine.
"""

from pathlib import Path

import pytest

from credit_intel.ingestion.errors import CATALOGUE, EXIT_INPUT, ErrorCode, IngestionError, exit_code
from credit_intel.ingestion.fake_ocr import FakeOcrExtractor
from credit_intel.ingestion.models import OcrPage, OcrWord, PageText, PageWords, Word

PDF = Path("scan.pdf")


def word(text, x0=10.0, top=100.0, confidence=90.0):
    return OcrWord(text, x0, x0 + 30.0, top, top + 10.0, confidence)


def page(number, words=(), text=None, width=595.0, height=842.0):
    return OcrPage(number, width, height, text if text is not None else " ".join(w.text for w in words), tuple(words))


# --- the models ---------------------------------------------------------------------------------------------------


def test_mean_confidence_is_the_mean_of_the_word_confidences():
    assert page(1, [word("a", confidence=80.0), word("b", confidence=60.0), word("c", confidence=70.0)]).mean_confidence == 70.0


def test_a_page_with_no_words_has_no_mean_confidence_not_zero():
    assert page(1).mean_confidence is None


def test_the_page_converts_to_the_text_and_word_forms_the_checks_read():
    ocr = page(7, [word("Total", x0=10.0), word("14", x0=80.0)], width=595.0, height=842.0)
    assert ocr.page_text() == PageText(page_number=7, text="Total 14")
    assert ocr.page_text().page_label is None
    assert ocr.page_words() == PageWords(7, 595.0, 842.0, 0, (Word("Total", 10.0, 40.0, 100.0, 110.0), Word("14", 80.0, 110.0, 100.0, 110.0)))


def test_a_page_with_only_whitespace_text_has_no_text():
    assert not page(1, text="  \n ").page_text().has_text and page(1, [word("x")]).page_text().has_text


# --- the two new codes ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("code", [ErrorCode.OCR_UNAVAILABLE, ErrorCode.OCR_FAILED])
def test_each_ocr_code_is_catalogued_as_an_input_failure_with_fixed_text(code):
    entry = CATALOGUE[code]
    assert entry.exit_code == EXIT_INPUT == exit_code(IngestionError(code)) and entry.retried == "No"
    assert entry.stage == "text_extracted" and "--" in entry.message
    assert str(IngestionError(code, "x")).startswith(f"{code}:")


def test_the_ocr_codes_use_the_names_of_the_prd():
    assert (ErrorCode.OCR_UNAVAILABLE.value, ErrorCode.OCR_FAILED.value) == ("E-INPUT-OCR-UNAVAILABLE", "E-INPUT-OCR-FAILED")


# --- the fake engine follows the contract ----------------------------------------------------------------------------


def fake(**kwargs):
    return FakeOcrExtractor({1: page(1, [word("one")]), 2: page(2, [word("two")]), 3: page(3, [word("three")])}, page_count=5, **kwargs)


def read(engine, numbers, dpi=300, timeout=60.0):
    return engine.ocr_pages(PDF, numbers, dpi={n: dpi for n in numbers}, timeout_seconds=timeout)


def test_it_returns_one_page_per_request_ascending_whatever_the_order_asked():
    assert [p.page_number for p in read(fake(), [3, 1, 2])] == [1, 2, 3]


def test_a_page_it_was_not_given_comes_back_empty_not_missing():
    got = read(fake(), [4])
    assert got == [OcrPage(4, 612.0, 792.0, "", (), 300)] and got[0].mean_confidence is None


def test_it_records_what_it_was_asked():
    engine = fake()
    read(engine, [2, 1], dpi=200, timeout=9.0)
    assert engine.calls == [((2, 1), {2: 200, 1: 200}, 9.0)] and (engine.name, engine.version) == ("fake-ocr", "0")


@pytest.mark.parametrize("numbers", [[], [1, 1], [0], [6], [-1]])
def test_the_page_numbers_must_be_non_empty_unique_and_in_the_document(numbers):
    with pytest.raises(IngestionError) as excinfo:
        read(fake(), numbers)
    assert excinfo.value.code is ErrorCode.PAGE_RANGE


def test_the_last_page_of_the_document_is_accepted():
    assert read(fake(), [5])[0].page_number == 5


def test_an_unavailable_engine_raises_ocr_unavailable():
    with pytest.raises(IngestionError) as excinfo:
        read(fake(unavailable=True), [1])
    assert excinfo.value.code is ErrorCode.OCR_UNAVAILABLE


def test_a_failing_engine_raises_ocr_failed():
    with pytest.raises(IngestionError) as excinfo:
        read(fake(fail=True), [1])
    assert excinfo.value.code is ErrorCode.OCR_FAILED


def test_a_read_longer_than_the_time_limit_raises_ocr_failed_and_one_within_it_does_not():
    slow = fake(seconds_per_page=10.0)
    assert read(slow, [1, 2], timeout=20.0)  # exactly at the limit is accepted
    with pytest.raises(IngestionError) as excinfo:
        read(slow, [1, 2], timeout=19.9)
    assert excinfo.value.code is ErrorCode.OCR_FAILED


def test_unavailable_is_reported_before_a_bad_page_range():
    with pytest.raises(IngestionError) as excinfo:
        read(fake(unavailable=True), [])
    assert excinfo.value.code is ErrorCode.OCR_UNAVAILABLE


def test_no_error_message_carries_document_text():
    engine = FakeOcrExtractor({1: page(1, [word("SECRET-FIGURE")])}, page_count=1, fail=True)
    with pytest.raises(IngestionError) as excinfo:
        read(engine, [1])
    assert "SECRET-FIGURE" not in str(excinfo.value)
