"""Fields that were not found (PRD FR-006.1, FR-004.3, H.4.7; step 8b; B-218). Appendix B.6 row 14."""

import json
import random
from datetime import date

from credit_intel.extraction.attributes import VerifiedAttributes
from credit_intel.extraction.missing import H3_FIELDS, missing_fields
from credit_intel.models import (
    DocumentAttribute,
    DocumentAttributeName as Name,
    ExtractedField,
    FieldName,
    Origin,
    PeriodRole,
    SourceDocument,
    StatementBasis as Basis,
    Status,
    StatusReason,
    make_field_id,
)

CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE
D25, D24 = date(2025, 3, 31), date(2024, 3, 31)
DOC = SourceDocument(file_name="report.pdf", sha256="a" * 64)
VALIDATION = {
    k: True
    for k in (
        "evidence_verified", "value_in_evidence", "label_verified", "period_end_verified",
        "period_column_verified", "sign_verified", "scale_verified", "currency_verified",
    )
}  # fmt: skip


def period_attribute(role, day, status=Status.EXTRACTED):
    if day is None:
        return DocumentAttribute(attribute=Name.PERIOD_END, period_role=role, status=Status.NOT_FOUND)
    extracted = status is Status.EXTRACTED
    return DocumentAttribute(
        attribute=Name.PERIOD_END, period_role=role, raw_text=day.isoformat(), normalised_value=day.isoformat(),
        page_number=1, evidence_quote=day.isoformat(), status=status,
        status_reason=None if extracted else StatusReason.PERIOD_MISMATCH,
    )  # fmt: skip


def attributes(current=D25, comparative=D24, comparative_status=Status.EXTRACTED):
    other = DocumentAttribute(attribute=Name.ENTITY_NAME, status=Status.NOT_FOUND)
    return VerifiedAttributes(
        entity_name=other,
        current_period_end=period_attribute(CUR, current),
        comparative_period_end=period_attribute(COMP, comparative, comparative_status),
        statement_basis=DocumentAttribute(attribute=Name.STATEMENT_BASIS, status=Status.NOT_FOUND),
        reporting_currency=DocumentAttribute(attribute=Name.REPORTING_CURRENCY, status=Status.NOT_FOUND),
        scale=DocumentAttribute(attribute=Name.SCALE, status=Status.NOT_FOUND),
    )


def record(name, role, status=Status.EXTRACTED, basis=Basis.CONSOLIDATED, day=None):
    day = day or (D25 if role is CUR else D24)
    extracted = status is Status.EXTRACTED
    return ExtractedField(
        field_id=make_field_id(name, day, basis), field_name=name, origin=Origin.SOURCE, period_end=day,
        period_length_months=12, period_role=role, statement_basis=basis, status=status,
        status_reason=None if extracted else StatusReason.SIGN_MISMATCH,
        value=1 if extracted else None, currency="INR" if extracted else None,
        raw_value="1", value_interpretation="number", scale="units", source_document=DOC, page_number=1,
        evidence_quote="x 1", line_item_label="x", validation=VALIDATION,
    )  # fmt: skip


def missing(present=(), attrs=None, basis=Basis.CONSOLIDATED):
    return missing_fields(present, attrs or attributes(), basis, DOC)


# --- nothing was found ---------------------------------------------------------------------


def test_with_no_records_every_h3_field_is_missing_in_both_periods():
    result = missing()

    assert len(result) == 24
    assert {r.field_name for r in result} == set(H3_FIELDS) and FieldName.EBIT not in {r.field_name for r in result}
    assert all(r.status is Status.NOT_FOUND for r in result)


def test_a_missing_record_is_complete_and_never_zero():
    first = missing()[0]

    assert first.field_id == "revenue.2025-03-31.consolidated"
    assert first.origin is Origin.SOURCE and first.period_length_months == 12
    assert first.period_role is CUR and first.period_end == D25
    assert first.statement_basis is Basis.CONSOLIDATED
    assert first.value is None and first.currency is None and first.status_reason is None
    assert first.raw_value is None and first.evidence_quote is None and first.validation is None
    assert first.source_document == DOC


def test_records_are_in_field_order_with_the_current_period_first():
    result = missing()

    assert [(r.field_name, r.period_role) for r in result] == [(n, role) for n in H3_FIELDS for role in (CUR, COMP)]
    assert [r.period_end for r in result[:2]] == [D25, D24]


def test_the_runs_basis_is_used_in_the_ids():
    result = missing(basis=Basis.STANDALONE)

    assert all(r.field_id.endswith(".standalone") and r.statement_basis is Basis.STANDALONE for r in result)


def test_the_records_are_json_serialisable():
    json.dumps([r.model_dump(mode="json") for r in missing()])


# --- a field that has a record is not missing ----------------------------------------------------


def test_b6_row_14_a_blank_cell_with_nothing_proposed_is_missing_for_that_period_only():
    present = [record(FieldName.REVENUE, COMP)]

    result = missing(present)

    revenue = [r for r in result if r.field_name is FieldName.REVENUE]
    assert [(r.period_role, r.status) for r in revenue] == [(CUR, Status.NOT_FOUND)]
    assert len(result) == 23


def test_a_field_with_any_status_is_present_not_missing():
    for status in (Status.EXTRACTED, Status.REQUIRES_REVIEW):
        present = [record(FieldName.TOTAL_EQUITY, CUR, status), record(FieldName.TOTAL_EQUITY, COMP, status)]
        assert not [r for r in missing(present) if r.field_name is FieldName.TOTAL_EQUITY]


def test_a_conflicting_field_is_present_not_missing():
    candidate = {"page_number": 3, "evidence_quote": "x 1", "line_item_label": "x", "raw_value": "1", "value": "1"}
    conflicted = record(FieldName.REVENUE, CUR).model_copy(
        update={"status": Status.CONFLICTING, "value": None, "currency": None, "status_reason": None,
                "candidates": (candidate, candidate | {"page_number": 4})}
    )  # fmt: skip

    assert not [r for r in missing([conflicted]) if (r.field_name, r.period_role) == (FieldName.REVENUE, CUR)]


def test_a_field_whose_basis_could_not_be_read_is_present_not_missing():
    unplaced = record(FieldName.REVENUE, CUR, Status.REQUIRES_REVIEW, Basis.UNKNOWN)

    assert not [r for r in missing([unplaced]) if (r.field_name, r.period_role) == (FieldName.REVENUE, CUR)]


def test_a_complete_set_has_nothing_missing():
    present = [record(n, role) for n in H3_FIELDS for role in (CUR, COMP)]

    assert missing(present) == ()


def test_a_record_of_another_field_does_not_hide_a_missing_one():
    result = missing([record(FieldName.REVENUE, CUR)])

    assert FieldName.NET_PROFIT in {r.field_name for r in result}
    assert (FieldName.REVENUE, CUR) not in {(r.field_name, r.period_role) for r in result}


# --- periods without a validated end date ----------------------------------------------------------


def test_an_unvalidated_period_gets_no_records():
    result = missing(attrs=attributes(comparative_status=Status.REQUIRES_REVIEW))

    assert {r.period_role for r in result} == {CUR} and len(result) == 12


def test_a_period_that_was_not_proposed_gets_no_records():
    assert {r.period_role for r in missing(attrs=attributes(comparative=None))} == {CUR}
    assert missing(attrs=attributes(current=None, comparative=None)) == ()


def test_the_dates_are_the_validated_ones():
    result = missing(attrs=attributes(date(2026, 6, 30), date(2025, 6, 30)))

    assert {r.period_end for r in result} == {date(2026, 6, 30), date(2025, 6, 30)}


# --- determinism ----------------------------------------------------------------------------------------


def test_the_order_of_the_present_records_does_not_matter():
    present = [record(n, role) for n in list(H3_FIELDS)[:5] for role in (CUR, COMP)]
    expected = missing(present)
    rng = random.Random(8)
    for _ in range(10):
        shuffled = present[:]
        rng.shuffle(shuffled)
        assert missing(shuffled) == expected


def test_the_function_is_repeatable_and_does_not_change_its_input():
    present = [record(FieldName.REVENUE, CUR)]
    before = list(present)

    assert missing(present) == missing(present) and present == before
