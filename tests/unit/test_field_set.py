"""The run's field set (PRD FR-006, H.2, H.4, D-06; step 8d; B-221). Synthetic records."""

import json
import random
from datetime import date

import pytest

from credit_intel.extraction.attributes import VerifiedAttributes
from credit_intel.extraction.field_set import build_field_set
from credit_intel.extraction.missing import H3_FIELDS
from credit_intel.extraction.normalise import apply_scale, parse_value
from credit_intel.extraction.verify import FieldVerification
from credit_intel.ingestion.models import CandidatePage, LocatorResult
from credit_intel.models import (
    DocumentAttribute,
    DocumentAttributeName as Name,
    ExtractableFieldName,
    ExtractedField,
    FieldName,
    Origin,
    PeriodRole,
    ProposedField,
    Scale,
    SourceDocument,
    StatementBasis as Basis,
    Status,
    StatusReason,
    make_field_id,
)

CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE
D25, D24 = date(2025, 3, 31), date(2024, 3, 31)
DOC = SourceDocument(file_name="report.pdf", sha256="a" * 64)
LOCATED = LocatorResult("keywords", (CandidatePage(3, ("income_statement", "balance_sheet"), 9, ()),
                                     CandidatePage(4, ("income_statement", "balance_sheet"), 5, ())))  # fmt: skip
CHECKS = {
    k: True
    for k in (
        "evidence_verified", "value_in_evidence", "label_verified", "period_end_verified",
        "period_column_verified", "sign_verified", "scale_verified", "currency_verified",
    )
}  # fmt: skip


def attribute(role, day):
    return DocumentAttribute(
        attribute=Name.PERIOD_END, period_role=role, raw_text=day.isoformat(), normalised_value=day.isoformat(),
        page_number=3, evidence_quote=day.isoformat(), status=Status.EXTRACTED,
    )  # fmt: skip


def attributes(comparative=True):
    absent = lambda name: DocumentAttribute(attribute=name, status=Status.NOT_FOUND)  # noqa: E731
    return VerifiedAttributes(
        entity_name=absent(Name.ENTITY_NAME), current_period_end=attribute(CUR, D25),
        comparative_period_end=attribute(COMP, D24) if comparative else DocumentAttribute(
            attribute=Name.PERIOD_END, period_role=COMP, status=Status.NOT_FOUND),
        statement_basis=absent(Name.STATEMENT_BASIS), reporting_currency=absent(Name.REPORTING_CURRENCY),
        scale=absent(Name.SCALE),
    )  # fmt: skip


def rec(name, raw="1,234.56", page=3, role=CUR, basis=Basis.CONSOLIDATED, status=Status.EXTRACTED,
        reason=StatusReason.SIGN_MISMATCH):  # fmt: skip
    day = D25 if role is CUR else D24
    parsed = parse_value(raw)
    extracted = status is Status.EXTRACTED
    return ExtractedField(
        field_id=make_field_id(name, day, basis), field_name=name, origin=Origin.SOURCE, period_end=day,
        period_length_months=12, period_role=role, statement_basis=basis, status=status,
        status_reason=None if extracted else reason,
        value=apply_scale(parsed.value, Scale.CRORE) if extracted else None, currency="INR" if extracted else None,
        raw_value=raw, value_interpretation=parsed.interpretation, scale=Scale.CRORE, source_document=DOC,
        page_number=page, evidence_quote=f"row {raw}", line_item_label="row", validation={**CHECKS, "details": {}},
    )  # fmt: skip


def verification(record):
    proposed = ProposedField(
        field_name=ExtractableFieldName(record.field_name.value), period_role=record.period_role,
        raw_value=record.raw_value, scale=Scale.CRORE, currency="INR", page_number=record.page_number,
        evidence_quote=record.evidence_quote, line_item_label="row",
    )  # fmt: skip
    return FieldVerification(proposed, record, () if record.status is Status.EXTRACTED else (record.status_reason,))


def build(records, basis=Basis.CONSOLIDATED, attrs=None):
    return build_field_set([verification(r) for r in records], attrs or attributes(), LOCATED, basis, DOC)


# --- the pipeline ------------------------------------------------------------------------------


def test_an_empty_run_has_every_field_not_found_in_both_periods():
    result = build([])

    assert len(result.fields) == 24 and result.counts == {
        "extracted": 0, "not_found": 24, "conflicting": 0, "requires_review": 0
    }  # fmt: skip
    assert result.ignored == () and result.unplaced == () and result.bases_present == ()


def test_found_fields_are_kept_and_the_rest_are_not_found():
    result = build([rec(FieldName.REVENUE), rec(FieldName.REVENUE, "1.00", role=COMP)])

    assert result.get(FieldName.REVENUE, CUR).status is Status.EXTRACTED
    assert result.get(FieldName.REVENUE, COMP).status is Status.EXTRACTED
    assert result.get(FieldName.TOTAL_EQUITY, CUR).status is Status.NOT_FOUND
    assert result.counts["extracted"] == 2 and result.counts["not_found"] == 22


def test_b6_row_14_a_period_with_nothing_proposed_is_not_found_never_zero():
    result = build([rec(FieldName.REVENUE, role=COMP)])

    current = result.get(FieldName.REVENUE, CUR)
    assert current.status is Status.NOT_FOUND and current.value is None


def test_duplicates_are_reconciled_into_one_field():
    result = build([rec(FieldName.REVENUE, "1,235", page=4), rec(FieldName.REVENUE, "1,234.56", page=3)])

    revenue = result.get(FieldName.REVENUE, CUR)
    assert revenue.raw_value == "1,234.56" and len(revenue.corroborating_evidence) == 1
    assert len([r for r in result.fields if r.field_id == revenue.field_id]) == 1


def test_b6_row_8_a_conflict_stays_a_conflict_and_is_not_filled_in_as_missing():
    result = build([rec(FieldName.REVENUE, "1,234.56", page=3), rec(FieldName.REVENUE, "1,198.20", page=4)])

    revenue = result.get(FieldName.REVENUE, CUR)
    assert revenue.status is Status.CONFLICTING and len(revenue.candidates) == 2
    assert result.counts["conflicting"] == 1


def test_an_implausible_value_is_marked_after_reconciliation():
    result = build([rec(FieldName.REVENUE, "(5.00)"), rec(FieldName.TOTAL_EQUITY, "(5.00)")])

    revenue = result.get(FieldName.REVENUE, CUR)
    assert revenue.status is Status.REQUIRES_REVIEW and revenue.status_reason is StatusReason.IMPLAUSIBLE_VALUE
    assert result.get(FieldName.TOTAL_EQUITY, CUR).status is Status.EXTRACTED
    assert result.get(FieldName.TOTAL_EQUITY, CUR).value < 0


def test_a_negative_that_was_reconciled_with_a_positive_is_a_conflict_not_an_implausible_value():
    result = build([rec(FieldName.REVENUE, "(5.00)", page=3), rec(FieldName.REVENUE, "5.00", page=4)])

    assert result.get(FieldName.REVENUE, CUR).status is Status.CONFLICTING


def test_a_field_that_failed_verification_is_not_also_reported_as_not_found():
    failed = rec(FieldName.REVENUE, "9.00", status=Status.REQUIRES_REVIEW)
    result = build([failed])

    assert result.get(FieldName.REVENUE, CUR).status is Status.REQUIRES_REVIEW
    assert [r.status for r in result.fields if r.field_name is FieldName.REVENUE and r.period_role is CUR] == [Status.REQUIRES_REVIEW]


# --- the configured basis (D-06, B.6 rows 9 and 10) -----------------------------------------------------------


def test_fields_of_another_basis_are_set_aside_never_mixed_in():
    result = build([rec(FieldName.REVENUE), rec(FieldName.TOTAL_EQUITY, basis=Basis.STANDALONE)])

    assert result.get(FieldName.REVENUE, CUR).status is Status.EXTRACTED
    assert result.get(FieldName.TOTAL_EQUITY, CUR).status is Status.NOT_FOUND
    assert [r.field_name for r in result.ignored] == [FieldName.TOTAL_EQUITY]
    assert result.bases_present == ("consolidated", "standalone")
    assert all(r.statement_basis is Basis.CONSOLIDATED for r in result.fields)


def test_b6_row_10_the_same_document_with_the_standalone_basis_uses_the_standalone_fields():
    records = [rec(FieldName.REVENUE, "1.00"), rec(FieldName.REVENUE, "2.00", basis=Basis.STANDALONE)]

    consolidated = build(records, Basis.CONSOLIDATED)
    standalone = build(records, Basis.STANDALONE)

    assert consolidated.get(FieldName.REVENUE, CUR).raw_value == "1.00"
    assert standalone.get(FieldName.REVENUE, CUR).raw_value == "2.00"
    assert standalone.get(FieldName.REVENUE, CUR).field_id == "revenue.2025-03-31.standalone"


def test_the_two_bases_are_never_reconciled_into_one_field():
    result = build([rec(FieldName.REVENUE, "1.00"), rec(FieldName.REVENUE, "99.00", basis=Basis.STANDALONE)])

    assert result.get(FieldName.REVENUE, CUR).status is Status.EXTRACTED  # not conflicting


def test_a_field_of_unknown_basis_is_kept_so_the_analyst_sees_it_and_no_not_found_hides_it():
    unknown = rec(FieldName.REVENUE, "1.00", basis=Basis.UNKNOWN, status=Status.REQUIRES_REVIEW, reason=StatusReason.BASIS_UNKNOWN)

    result = build([unknown])

    assert [r.statement_basis for r in result.fields if r.field_name is FieldName.REVENUE and r.period_role is CUR] == [Basis.UNKNOWN]


def test_get_gives_only_the_configured_basis_not_a_record_of_unknown_basis():
    unknown = rec(FieldName.REVENUE, "1.00", basis=Basis.UNKNOWN, status=Status.REQUIRES_REVIEW, reason=StatusReason.BASIS_UNKNOWN)

    result = build([unknown])

    assert result.get(FieldName.REVENUE, CUR) is None
    assert any(r.statement_basis is Basis.UNKNOWN for r in result.fields)


def test_the_configured_basis_must_be_a_real_one():
    with pytest.raises(ValueError):
        build([], Basis.UNKNOWN)


# --- fields without a period-end, and periods that were not validated -------------------------------------------------


def test_a_verification_with_no_field_is_reported_as_unplaced():
    placed = verification(rec(FieldName.REVENUE))
    unplaced = FieldVerification(placed.proposed, None, (StatusReason.PERIOD_MISMATCH,))

    result = build_field_set([placed, unplaced], attributes(), LOCATED, Basis.CONSOLIDATED, DOC)

    assert result.unplaced == (unplaced,) and len(result.fields) == 24


def test_a_period_that_was_not_validated_has_no_not_found_records():
    result = build([rec(FieldName.REVENUE)], attrs=attributes(comparative=False))

    assert {r.period_role for r in result.fields} == {CUR} and len(result.fields) == 12


# --- invariants -----------------------------------------------------------------------------------------------------------


def test_every_field_id_appears_once_and_the_order_is_by_field_then_period():
    result = build([rec(FieldName.TOTAL_EQUITY), rec(FieldName.REVENUE, role=COMP), rec(FieldName.REVENUE)])

    ids = [r.field_id for r in result.fields]
    assert len(ids) == len(set(ids))
    names = [(list(H3_FIELDS).index(r.field_name), 0 if r.period_role is CUR else 1) for r in result.fields]
    assert names == sorted(names)


def test_the_counts_always_add_up_to_the_records():
    result = build([rec(FieldName.REVENUE), rec(FieldName.NET_PROFIT, "9.00", status=Status.REQUIRES_REVIEW)])

    assert sum(result.counts.values()) == len(result.fields)
    assert set(result.counts) == {"extracted", "not_found", "conflicting", "requires_review"}


def test_the_field_set_is_json_serialisable():
    result = build([rec(FieldName.REVENUE, "1,234.56", page=3), rec(FieldName.REVENUE, "1,198.20", page=4)])

    json.dumps([r.model_dump(mode="json") for r in result.fields])


def test_the_result_does_not_depend_on_the_order_of_the_verifications():
    records = [rec(FieldName.REVENUE, "1,234.56", page=3), rec(FieldName.REVENUE, "1,235", page=4),
               rec(FieldName.TOTAL_EQUITY), rec(FieldName.NET_PROFIT, "(9.00)", role=COMP)]  # fmt: skip
    expected = build(records)
    rng = random.Random(2)
    for _ in range(10):
        shuffled = records[:]
        rng.shuffle(shuffled)
        assert build(shuffled) == expected


def test_get_returns_none_for_a_period_with_no_records():
    assert build([], attrs=attributes(comparative=False)).get(FieldName.REVENUE, COMP) is None


def test_properties_over_generated_runs():
    rng = random.Random(20261019)
    raws = ["1,234.56", "1,235", "(5.00)", "-", "0.00", "9,999.00", "7"]
    names = list(H3_FIELDS)
    for _ in range(300):
        records = [
            rec(
                rng.choice(names), rng.choice(raws), page=rng.choice([3, 4]), role=rng.choice([CUR, COMP]),
                basis=rng.choice([Basis.CONSOLIDATED, Basis.CONSOLIDATED, Basis.STANDALONE, Basis.UNKNOWN]),
                status=Status.EXTRACTED if rng.random() < 0.75 else Status.REQUIRES_REVIEW,
            )
            for _ in range(rng.randint(0, 14))
        ]  # fmt: skip
        configured = rng.choice([Basis.CONSOLIDATED, Basis.STANDALONE])
        result = build(records, configured)

        ids = [r.field_id for r in result.fields]
        assert len(ids) == len(set(ids))
        assert sum(result.counts.values()) == len(result.fields)
        assert all(r.statement_basis in (configured, Basis.UNKNOWN) for r in result.fields)
        for name in H3_FIELDS:
            for role in (CUR, COMP):  # every field and period is accounted for exactly once
                matching = [r for r in result.fields if r.field_name is name and r.period_role is role]
                assert len(matching) >= 1
        for r in result.fields:
            if r.status is Status.EXTRACTED:
                assert r.value is not None and r.status_reason is None
                assert not (r.value < 0 and r.field_name.value in {"revenue", "current_assets", "current_liabilities",
                    "total_borrowings", "borrowings_non_current", "borrowings_current", "interest_expense"})  # fmt: skip
            else:
                assert r.value is None
        assert {i.statement_basis for i in result.ignored} <= {Basis.CONSOLIDATED, Basis.STANDALONE} - {configured}
