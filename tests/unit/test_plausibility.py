"""Plausibility (PRD FR-006.5; step 8d; B-220). Synthetic records."""

from datetime import date
from decimal import Decimal

import pytest

from credit_intel.extraction.plausibility import MUST_NOT_BE_NEGATIVE, apply_plausibility, is_implausible
from credit_intel.extraction.missing import H3_FIELDS
from credit_intel.extraction.normalise import apply_scale, parse_value
from credit_intel.models import (
    ExtractedField,
    FieldName,
    Origin,
    PeriodRole,
    Scale,
    SourceDocument,
    StatementBasis as Basis,
    Status,
    StatusReason,
    make_field_id,
)

DOC = SourceDocument(file_name="report.pdf", sha256="a" * 64)
D25 = date(2025, 3, 31)
CHECKS = {
    k: True
    for k in (
        "evidence_verified", "value_in_evidence", "label_verified", "period_end_verified",
        "period_column_verified", "sign_verified", "scale_verified", "currency_verified",
    )
}  # fmt: skip

INVALID_IF_NEGATIVE = {
    FieldName.REVENUE, FieldName.CURRENT_ASSETS, FieldName.CURRENT_LIABILITIES, FieldName.TOTAL_BORROWINGS,
    FieldName.BORROWINGS_NON_CURRENT, FieldName.BORROWINGS_CURRENT, FieldName.INTEREST_EXPENSE,
}  # fmt: skip
VALID_IF_NEGATIVE = {
    FieldName.NET_PROFIT, FieldName.PROFIT_BEFORE_TAX, FieldName.OPERATING_PROFIT, FieldName.TOTAL_EQUITY,
}  # fmt: skip


def rec(name, raw="(245.10)", status=Status.EXTRACTED, reason=StatusReason.SIGN_MISMATCH):
    parsed = parse_value(raw)
    extracted = status is Status.EXTRACTED
    return ExtractedField(
        field_id=make_field_id(name, D25, Basis.CONSOLIDATED), field_name=name, origin=Origin.SOURCE,
        period_end=D25, period_length_months=12, period_role=PeriodRole.CURRENT, statement_basis=Basis.CONSOLIDATED,
        status=status, status_reason=None if extracted else reason,
        value=apply_scale(parsed.value, Scale.CRORE) if extracted else None, currency="INR" if extracted else None,
        raw_value=raw, value_interpretation=parsed.interpretation, scale=Scale.CRORE, source_document=DOC,
        page_number=3, evidence_quote=f"row {raw}", line_item_label="row", validation={**CHECKS, "details": {}},
    )  # fmt: skip


def test_the_prds_two_lists_cover_exactly_the_fields_that_have_a_rule():
    assert MUST_NOT_BE_NEGATIVE == INVALID_IF_NEGATIVE
    assert INVALID_IF_NEGATIVE | VALID_IF_NEGATIVE | {FieldName.CURRENT_MATURITIES_LONG_TERM_BORROWINGS} == set(H3_FIELDS)


@pytest.mark.parametrize("name", sorted(INVALID_IF_NEGATIVE))
def test_a_negative_value_in_a_field_that_cannot_be_negative_needs_review(name):
    (result,) = apply_plausibility([rec(name)])

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason is StatusReason.IMPLAUSIBLE_VALUE
    assert result.value is None and result.currency is None


@pytest.mark.parametrize("name", sorted(VALID_IF_NEGATIVE))
def test_a_negative_value_in_a_field_that_may_be_negative_is_untouched(name):
    record = rec(name)

    assert apply_plausibility([record]) == (record,)
    assert record.value < 0


def test_the_evidence_is_kept_and_the_reason_recorded_in_the_details():
    record = rec(FieldName.REVENUE)

    (result,) = apply_plausibility([record])

    assert result.raw_value == record.raw_value and result.evidence_quote == record.evidence_quote
    assert result.page_number == record.page_number and result.scale is Scale.CRORE
    assert result.validation.all_passed()  # the verification itself passed
    assert result.validation.details["plausibility"] == {"rule": "FR-006.5", "value": str(record.value)}
    assert result.field_id == record.field_id


@pytest.mark.parametrize("raw", ["245.10", "0.00", "-", "nil", "1"])
@pytest.mark.parametrize("name", sorted(INVALID_IF_NEGATIVE))
def test_zero_a_reported_nil_and_positive_values_are_plausible(name, raw):
    record = rec(name, raw)

    assert not is_implausible(record) and apply_plausibility([record]) == (record,)


def test_the_current_maturities_field_is_never_judged():
    record = rec(FieldName.CURRENT_MATURITIES_LONG_TERM_BORROWINGS)

    assert apply_plausibility([record]) == (record,)


@pytest.mark.parametrize("status", [Status.REQUIRES_REVIEW, Status.NOT_FOUND])
def test_a_field_that_is_not_extracted_is_left_alone(status):
    record = rec(FieldName.REVENUE, "(245.10)", status)

    assert apply_plausibility([record]) == (record,)


def test_a_conflicting_field_is_left_alone():
    candidate = {"page_number": 3, "evidence_quote": "q 1", "line_item_label": "q", "raw_value": "1", "value": "-1"}
    base = rec(FieldName.REVENUE, "(1.00)")
    conflicting = ExtractedField.model_validate(
        base.model_dump() | {"status": "conflicting", "value": None, "currency": None, "status_reason": None,
                             "candidates": [candidate, candidate | {"page_number": 4}]}
    )  # fmt: skip

    assert apply_plausibility([conflicting]) == (conflicting,)


def test_a_mixed_list_changes_only_the_implausible_fields_and_keeps_the_order():
    records = [rec(FieldName.TOTAL_EQUITY), rec(FieldName.REVENUE), rec(FieldName.NET_PROFIT, "5.00")]

    result = apply_plausibility(records)

    assert [r.field_name for r in result] == [r.field_name for r in records]
    assert [r.status for r in result] == [Status.EXTRACTED, Status.REQUIRES_REVIEW, Status.EXTRACTED]


def test_the_result_is_a_valid_record_and_the_input_is_not_changed():
    record = rec(FieldName.REVENUE)
    before = record.model_dump()

    (result,) = apply_plausibility([record])

    assert isinstance(result, ExtractedField) and record.model_dump() == before
    assert result.model_dump(mode="json")["value"] is None


def test_a_value_of_exactly_minus_one_unit_is_implausible_and_the_smallest_positive_is_not():
    assert is_implausible(rec(FieldName.REVENUE, "(0.01)"))
    assert not is_implausible(rec(FieldName.REVENUE, "0.01"))
    assert Decimal("0") == rec(FieldName.REVENUE, "0.00").value
