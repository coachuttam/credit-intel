"""OCR evidence on a field: the source, the confidences, the reason and the manifest block (PRD v0.4.44, FR-005 criterion 11; B-319).

Step 1d of the OCR build. The OCR reading is synthetic: a generated PDF's own text and word boxes, given invented
confidences. No engine runs. What the tests establish is the rule: a field cited on an OCR page is never extracted, however
well the other checks pass, and nothing it holds reaches a metric.
"""

import dataclasses
import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from pydantic import ValidationError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # the verification fixtures live beside this file
sys.path.insert(0, str(HERE.parent / "unit"))  # and the pipeline fixture with the unit tests

import pipeline_fixture as fx  # noqa: E402
from test_field_verification import CUR, build, proposal  # noqa: E402

from credit_intel.calculations.calculate import calculate_metrics  # noqa: E402
from credit_intel.export.manifest import CodeVersion  # noqa: E402
from credit_intel.export.results import to_jsonable  # noqa: E402
from credit_intel.export.run_export import export_run  # noqa: E402
from credit_intel.extraction.field_set import build_field_set  # noqa: E402
from credit_intel.extraction.ocr_evidence import OcrReading, OcrRunRecord, confidence, mean_confidence  # noqa: E402
from credit_intel.extraction.verify import _ORDER, FieldVerifier  # noqa: E402
from credit_intel.ingestion.models import OcrPage, OcrWord  # noqa: E402
from credit_intel.llm.provider import FakeProvider  # noqa: E402
from credit_intel.models import (  # noqa: E402
    EvidenceSource,
    ExtractableFieldName as F,
    ExtractedField,
    OcrEvidence,
    Origin,
    Scale,
    StatementBasis,
    Status,
    StatusReason as R,
)
from credit_intel.run import run_pipeline  # noqa: E402
from credit_intel.states import Recorder  # noqa: E402

FIGURE_CONFIDENCE = {"1,482.30": 62.5, "1,356.75": 71.0}
OTHER_CONFIDENCE = 90.0
BASIS = StatementBasis.CONSOLIDATED


def ocr_page(verifier, page_number=1):
    """The page the verifier holds, as an OCR page: the same text and boxes, with invented confidences."""
    ctx = verifier._ctx
    words = ctx.page_words[page_number]
    return OcrPage(
        page_number=page_number,
        width=words.width,
        height=words.height,
        text=ctx.pages[page_number].text,
        words=tuple(
            OcrWord(w.text, w.x0, w.x1, w.top, w.bottom, FIGURE_CONFIDENCE.get(w.text, OTHER_CONFIDENCE)) for w in words.words
        ),
    )


def as_ocr(env, pages=(1,)):
    """The same verifier, with ``pages`` read by OCR."""
    verifier, line, attributes = env
    reading = OcrReading("fake-ocr", "1.0", 300, {n: ocr_page(verifier, n) for n in pages})
    return FieldVerifier(dataclasses.replace(verifier._ctx, ocr=reading)), line, attributes


@pytest.fixture
def env(tmp_path):
    return build(tmp_path / "s.pdf")


def verify(env, field, role, raw, needle, **kw):
    verifier, line, _ = env
    return verifier.verify(proposal(line, field, role, raw, needle, **kw))


# --- the rule: never extracted -------------------------------------------------------------------------------


def test_the_same_field_is_extracted_from_the_text_layer_and_a_review_from_ocr(env):
    text = verify(env, F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets").field
    ocr = verify(as_ocr(env), F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets")

    assert text.status is Status.EXTRACTED and text.evidence_source is EvidenceSource.TEXT_LAYER and text.ocr_evidence is None
    assert ocr.field.status is Status.REQUIRES_REVIEW and ocr.field.status_reason is R.OCR_UNCONFIRMED
    assert ocr.field.evidence_source is EvidenceSource.OCR and ocr.reasons == (R.OCR_UNCONFIRMED,)


def test_an_ocr_field_has_no_value_or_currency_but_keeps_its_evidence_exactly(env):
    verifier, line, _ = as_ocr(env)
    given = proposal(line, F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets", label="Total Current Assets ")

    record = verifier.verify(given).field

    assert record.value is None and record.currency is None
    assert record.raw_value == "1,482.30" and record.evidence_quote == line("Total current assets")
    assert record.line_item_label == "Total Current Assets " and record.page_number == 1


def test_every_other_check_still_runs_and_is_recorded_on_an_ocr_field(env):
    validation = verify(as_ocr(env), F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field.validation

    assert validation.all_passed()
    assert validation.details["column"]["token"]["text"] == "600.00"


def test_a_field_that_fails_an_earlier_check_keeps_that_reason_and_ocr_unconfirmed_is_last(env):
    result = verify(as_ocr(env), F.TOTAL_EQUITY, CUR, "600.00", "Total equity", scale=Scale.MILLIONS)

    assert result.field.status is Status.REQUIRES_REVIEW and result.field.status_reason is not R.OCR_UNCONFIRMED
    assert result.reasons[-1] is R.OCR_UNCONFIRMED and len(result.reasons) >= 2
    assert result.field.status_reason is result.reasons[0]


def test_a_value_not_in_the_evidence_keeps_its_own_reason_on_an_ocr_page(env):
    result = verify(as_ocr(env), F.TOTAL_EQUITY, CUR, "601.00", "Total equity")

    assert result.field.status_reason is R.VALUE_NOT_IN_EVIDENCE and result.reasons[-1] is R.OCR_UNCONFIRMED


def test_ocr_unconfirmed_is_the_last_reason_in_the_order():
    assert _ORDER[-1] is R.OCR_UNCONFIRMED and _ORDER.count(R.OCR_UNCONFIRMED) == 1


def test_a_page_not_read_by_ocr_is_unchanged_in_a_run_that_used_it_elsewhere(tmp_path):
    env = build(tmp_path / "two.pdf", pages=2, candidates=(1, 2))
    verifier, line, _ = as_ocr(env, pages=(2,))

    on_text_page = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=1)).field
    on_ocr_page = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=2, quote=line("Total equity", 2))).field

    assert on_text_page.status is Status.EXTRACTED and on_text_page.evidence_source is EvidenceSource.TEXT_LAYER
    assert on_ocr_page.evidence_source is EvidenceSource.OCR and on_ocr_page.status is Status.REQUIRES_REVIEW


def test_a_run_with_no_ocr_reading_is_exactly_as_before(env):
    assert env[0]._ctx.ocr is None
    assert verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field.status is Status.EXTRACTED


# --- the confidences -----------------------------------------------------------------------------------------


def test_the_quote_confidences_are_over_the_words_of_the_figure_line(env):
    evidence = verify(as_ocr(env), F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets").field.ocr_evidence

    # the line is: Total current assets 14 1,482.30 1,356.75 -> 90, 90, 90, 90, 62.5, 71
    assert evidence.min_word_confidence == Decimal("62.5")
    assert evidence.mean_word_confidence == Decimal("82.2")  # 493.5 / 6 = 82.25, half to even
    assert (evidence.engine, evidence.engine_version, evidence.dpi) == ("fake-ocr", "1.0", 300)


def test_the_page_mean_is_over_every_word_of_the_page(env):
    ocr_env = as_ocr(env)
    page = ocr_env[0]._ctx.ocr.pages[1]
    exact = sum(Fraction(str(w.confidence)) for w in page.words) / len(page.words)

    evidence = verify(ocr_env, F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets").field.ocr_evidence

    assert abs(Fraction(evidence.page_mean_confidence) - exact) <= Fraction(1, 20)
    assert evidence.page_mean_confidence != evidence.mean_word_confidence  # not the quote's mean


def test_confidences_are_one_place_decimals_not_floats(env):
    evidence = verify(as_ocr(env), F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets").field.ocr_evidence

    for value in (evidence.min_word_confidence, evidence.mean_word_confidence, evidence.page_mean_confidence):
        assert isinstance(value, Decimal) and value.as_tuple().exponent == -1


def test_a_quote_not_found_on_a_figure_line_uses_the_words_of_the_quote(env):
    verifier, line, _ = as_ocr(env)
    given = proposal(line, F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets", quote="current assets")

    field = verifier.verify(given).field

    assert field.status_reason is not R.OCR_UNCONFIRMED  # the quote does not hold the figure, so it is not linked to a line
    assert field.ocr_evidence.min_word_confidence == field.ocr_evidence.mean_word_confidence == Decimal("90.0")


def test_a_quote_with_no_word_on_the_page_has_no_word_confidences_but_keeps_the_page_mean(env):
    verifier, line, _ = as_ocr(env)
    given = proposal(line, F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets", quote="nothing here matches 9,999.99")

    field = verifier.verify(given).field

    assert field.ocr_evidence.min_word_confidence is None and field.ocr_evidence.mean_word_confidence is None
    assert field.ocr_evidence.page_mean_confidence is not None


def test_confidence_rounding_is_half_to_even_from_the_shortest_text_of_the_float():
    assert confidence(82.25) == Decimal("82.2") and confidence(82.35) == Decimal("82.4") and confidence(0.1 + 0.2) == Decimal("0.3")
    assert mean_confidence([90.0, 91.0]) == Decimal("90.5") and mean_confidence([]) is None
    assert mean_confidence([0.1, 0.2]) == Decimal("0.2")  # 0.15 exactly, half to even


def test_a_float_confidence_cannot_be_put_in_the_record():
    with pytest.raises(ValidationError):
        OcrEvidence(engine="e", engine_version="1", dpi=300, min_word_confidence=90.5)


# --- the field model ------------------------------------------------------------------------------------------


def good_ocr_field(env, **changes):
    record = verify(as_ocr(env), F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field
    return record.model_copy(update=changes)


def revalidate(record):
    return ExtractedField.model_validate(record.model_dump(mode="python"))


def test_an_ocr_field_round_trips_through_validation(env):
    record = good_ocr_field(env)
    assert revalidate(record) == record


def test_a_field_read_by_ocr_cannot_be_extracted(env):
    extracted = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field
    changed = extracted.model_copy(update={"evidence_source": EvidenceSource.OCR, "ocr_evidence": good_ocr_field(env).ocr_evidence})

    with pytest.raises(ValidationError, match="never extracted"):
        revalidate(changed)


def test_a_field_read_by_ocr_must_record_its_ocr_evidence(env):
    with pytest.raises(ValidationError, match="ocr_evidence"):
        revalidate(good_ocr_field(env, ocr_evidence=None))


def test_only_a_field_read_by_ocr_has_ocr_evidence(env):
    text = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field

    with pytest.raises(ValidationError, match="only a field read by OCR"):
        revalidate(text.model_copy(update={"ocr_evidence": good_ocr_field(env).ocr_evidence}))


def test_a_derived_or_not_found_field_cannot_be_ocr(env):
    with pytest.raises(ValidationError, match="found source field"):
        revalidate(good_ocr_field(env, status=Status.NOT_FOUND, status_reason=None))
    with pytest.raises(ValidationError):
        revalidate(good_ocr_field(env, origin=Origin.DERIVED))


def test_the_default_source_is_the_text_layer(env):
    assert verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field.evidence_source is EvidenceSource.TEXT_LAYER


# --- what results.json shows ---------------------------------------------------------------------------------


def test_a_text_layer_field_is_written_with_its_source_and_no_ocr_key(env):
    data = to_jsonable(verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field)

    assert data["evidence_source"] == "text_layer" and "ocr_evidence" not in data


def test_an_ocr_field_is_written_with_exact_decimal_strings(env):
    data = to_jsonable(verify(as_ocr(env), F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets").field)

    assert data["evidence_source"] == "ocr" and data["status"] == "requires_review" and data["status_reason"] == "ocr_unconfirmed"
    assert data["ocr_evidence"]["min_word_confidence"] == "62.5" and data["ocr_evidence"]["mean_word_confidence"] == "82.2"
    assert data["ocr_evidence"]["engine"] == "fake-ocr" and data["ocr_evidence"]["dpi"] == 300


# --- no OCR field reaches a metric ---------------------------------------------------------------------------


CURRENT_RATIO = [(F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets"), (F.CURRENT_LIABILITIES, CUR, "900.00", "Total current liabilities")]


def current_ratio_of(env, ocr_inputs):
    """Metrics from the two current-ratio inputs, those named in ``ocr_inputs`` (indexes) read by OCR."""
    verifier, line, attributes = env
    ocr_verifier = as_ocr(env)[0]
    verifications = [(ocr_verifier if i in ocr_inputs else verifier).verify(proposal(line, *p)) for i, p in enumerate(CURRENT_RATIO)]
    fields = build_field_set(verifications, attributes, verifier._ctx.located, BASIS, verifier._ctx.source_document)
    return fields, calculate_metrics(fields)


def test_control_the_current_ratio_is_defined_from_text_layer_fields(env):
    assert current_ratio_of(env, set())[1].results[("MET-03", CUR)].value is not None


@pytest.mark.parametrize("ocr_inputs", [{0}, {1}, {0, 1}])
def test_a_metric_with_an_ocr_input_is_undefined_and_carries_no_ocr_value(env, ocr_inputs):
    fields, metrics = current_ratio_of(env, ocr_inputs)

    result = metrics.results[("MET-03", CUR)]
    ocr_ids = {r.field_id for r in fields.fields if r.evidence_source is EvidenceSource.OCR}
    assert len(ocr_ids) == len(ocr_inputs)
    assert result.value is None and result.undefined_reason is not None
    assert all(value is None for field_id, value in zip(result.input_field_ids, result.input_values) if field_id in ocr_ids)
    assert all(r.value is None for r in fields.fields if r.field_id in ocr_ids)


def test_no_metric_or_derived_value_takes_an_ocr_field_id_as_a_usable_input(env):
    fields, metrics = current_ratio_of(env, {0, 1})
    ocr_ids = {r.field_id for r in fields.fields if r.evidence_source is EvidenceSource.OCR}

    for result in metrics.results.values():
        assert not [v for i, v in zip(result.input_field_ids, result.input_values) if i in ocr_ids and v is not None]
    for derived in (*metrics.derived, *metrics.derived_borrowings):
        assert not set(derived.derivation.input_field_ids) & ocr_ids


# --- the manifest block --------------------------------------------------------------------------------------


def record(**kw):
    base = dict(engine="fake-ocr", engine_version="1.0", dpi=300, language="eng", ocr_pages={5: Decimal("91.3"), 2: None}, text_layer_pages=(7, 3))
    return OcrRunRecord(**{**base, **kw})


def test_the_manifest_block_names_the_engine_settings_and_the_source_of_each_page():
    assert record().to_manifest() == {
        "engine": "fake-ocr", "engine_version": "1.0", "dpi": 300, "language": "eng",
        "pages_ocr": [{"page": 2, "mean_word_confidence": None}, {"page": 5, "mean_word_confidence": "91.3"}],
        "pages_text_layer": [3, 7],
    }  # fmt: skip


def exported_manifest(tmp_path, ocr):
    tmp_path.mkdir(parents=True, exist_ok=True)
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")
    start = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
    ticks = iter(start + timedelta(milliseconds=7 * n) for n in range(1000))
    recorder = Recorder(lambda: next(ticks))
    result = run_pipeline(pdf, FakeProvider(script=[fx.good_response(pdf)]), fx.LLM, recorder=recorder, cache_dir=tmp_path / "cache")
    result = dataclasses.replace(result, extraction=dataclasses.replace(result.extraction, ocr=ocr))
    packages = {"openai": "1.0", "pdfplumber": "2.0", "pydantic": "3.0", "python": "3.12.0"}
    folder = export_run(tmp_path / "runs", result, recorder, fx.LLM, requested_basis=BASIS, version=CodeVersion("a" * 40, False), packages=packages)
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


def test_the_manifest_has_an_ocr_block_only_when_ocr_was_used(tmp_path):
    with_ocr = exported_manifest(tmp_path / "a", record())
    without = exported_manifest(tmp_path / "b", None)

    assert with_ocr["ocr"] == record().to_manifest() and "ocr" not in without


def test_the_ocr_block_holds_no_document_text_or_value(tmp_path):
    block = json.dumps(exported_manifest(tmp_path / "a", record())["ocr"])

    assert "Total" not in block and "1,482" not in block
