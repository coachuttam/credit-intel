"""Reconciling duplicate occurrences (PRD FR-006.2, H.4.1, H.4.2, H.4.6; step 8c; B-219).

Appendix B.6 rows 7 and 8, and the boundary cases of the rounding rule. Synthetic records.
"""

import json
import random
from datetime import date
from decimal import Decimal

from credit_intel.extraction.missing import H3_FIELDS
from credit_intel.extraction.normalise import apply_scale, parse_value
from credit_intel.extraction.reconcile import primary_page, reconcile
from credit_intel.ingestion.models import CandidatePage, LocatorResult
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

CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE
D25, D24 = date(2025, 3, 31), date(2024, 3, 31)
DOC = SourceDocument(file_name="report.pdf", sha256="a" * 64)
CHECKS = {
    k: True
    for k in (
        "evidence_verified", "value_in_evidence", "label_verified", "period_end_verified",
        "period_column_verified", "sign_verified", "scale_verified", "currency_verified",
    )
}  # fmt: skip
REV = FieldName.REVENUE


def occ(raw, page, scale=Scale.CRORE, name=REV, role=CUR, status=Status.EXTRACTED, basis=Basis.CONSOLIDATED,
        quote=None, reason=StatusReason.SIGN_MISMATCH):  # fmt: skip
    day = D25 if role is CUR else D24
    parsed = parse_value(raw)
    extracted = status is Status.EXTRACTED
    return ExtractedField(
        field_id=make_field_id(name, day, basis), field_name=name, origin=Origin.SOURCE, period_end=day,
        period_length_months=12, period_role=role, statement_basis=basis, status=status,
        status_reason=None if extracted else reason,
        value=apply_scale(parsed.value, scale) if extracted else None, currency="INR" if extracted else None,
        raw_value=raw, value_interpretation=parsed.interpretation, scale=scale, source_document=DOC,
        page_number=page, page_label=f"p{page}", evidence_quote=quote or f"Revenue {raw}",
        line_item_label="Revenue", validation={**CHECKS, "details": {}},
    )  # fmt: skip


def pages(*specs):
    """specs: (page, score) of balance-sheet and income-statement candidates."""
    return LocatorResult(
        "keywords", tuple(CandidatePage(n, ("income_statement",), score, ()) for n, score in specs)
    )


LOCATED = pages((3, 9), (4, 5), (5, 5))  # page 3 is the primary statement page


def one(*records, located=LOCATED):
    (result,) = reconcile(records, located)
    return result


# --- a single occurrence ------------------------------------------------------------------------


def test_a_field_with_one_occurrence_is_returned_unchanged():
    record = occ("1,234.56", 3)

    assert one(record) == record


def test_fields_are_returned_in_field_order_current_period_first():
    records = [occ("5.00", 3, name=FieldName.TOTAL_EQUITY), occ("1.00", 3, role=COMP), occ("2.00", 3), occ("4.00", 3, name=FieldName.NET_PROFIT)]

    result = reconcile(records, LOCATED)

    assert [(r.field_name, r.period_role) for r in result] == [
        (REV, CUR), (REV, COMP), (FieldName.NET_PROFIT, CUR), (FieldName.TOTAL_EQUITY, CUR),
    ]  # fmt: skip


def test_occurrences_of_different_fields_periods_or_bases_are_not_merged():
    records = [occ("1.00", 3), occ("1.00", 4, role=COMP), occ("1.00", 5, basis=Basis.STANDALONE)]

    assert len(reconcile(records, LOCATED)) == 3


def test_nothing_in_nothing_out():
    assert reconcile([], LOCATED) == ()


# --- agreement: exact and within the rounding tolerance (B.6 row 7) ----------------------------------------


def test_equal_values_on_two_pages_are_one_field_with_corroborating_evidence():
    result = one(occ("1,234.56", 3), occ("1,234.56", 4))

    assert result.status is Status.EXTRACTED and result.page_number == 3
    assert [(e.page_number, e.raw_value) for e in result.corroborating_evidence] == [(4, "1,234.56")]
    assert result.corroborating_evidence[0].evidence_quote == "Revenue 1,234.56"


def test_b6_row_7_the_rounded_highlights_value_is_corroborating_and_the_precise_one_is_used():
    result = one(occ("1,235", 4), occ("1,234.56", 3))

    assert result.status is Status.EXTRACTED
    assert result.value == Decimal("12345600000.00") and result.raw_value == "1,234.56"
    assert [e.page_number for e in result.corroborating_evidence] == [4]


def test_the_more_precise_value_is_used_even_if_it_is_not_on_the_primary_page():
    result = one(occ("1,234.56", 4), occ("1,235", 3))  # page 3 is primary

    assert result.raw_value == "1,234.56" and result.page_number == 4
    assert [e.page_number for e in result.corroborating_evidence] == [3]


def test_exactly_half_a_unit_of_the_coarser_last_digit_is_consistent():
    for coarse, fine in (("1,235", "1,234.50"), ("1,234", "1,234.50"), ("1,235", "1,235.50"), ("1,235", "1,234.5")):
        assert one(occ(coarse, 4), occ(fine, 3)).status is Status.EXTRACTED, (coarse, fine)


def test_just_over_half_a_unit_is_a_conflict():
    for coarse, fine in (("1,235", "1,234.49"), ("1,235", "1,235.51"), ("1,234", "1,234.51")):
        assert one(occ(coarse, 4), occ(fine, 3)).status is Status.CONFLICTING, (coarse, fine)


def test_the_tolerance_scales_with_the_coarser_values_unit():
    # 12.3 crore (one decimal) against 12.34: half of 0.1 crore is 0.05 crore.
    assert one(occ("12.3", 4), occ("12.34", 3)).status is Status.EXTRACTED
    assert one(occ("12.3", 4), occ("12.35", 3)).status is Status.EXTRACTED  # exactly 0.05
    assert one(occ("12.3", 4), occ("12.36", 3)).status is Status.CONFLICTING


def test_precision_is_read_from_the_printed_digits_so_trailing_zeros_count():
    # "1,234.50" has two places: against "1,234.5" (one place) the values are equal.
    result = one(occ("1,234.5", 4), occ("1,234.50", 3))

    assert result.raw_value == "1,234.50" and result.status is Status.EXTRACTED


# --- equal precision needs exact equality ---------------------------------------------------------------------


def test_the_same_precision_needs_exactly_equal_values():
    assert one(occ("1,234.56", 3), occ("1,234.57", 4)).status is Status.CONFLICTING
    assert one(occ("1,235", 3), occ("1,236", 4)).status is Status.CONFLICTING


def test_different_scales_of_the_same_unit_size_are_compared_in_base_units():
    # 1,234.56 crore (step 100,000) and 1,23,456 lakh (step 100,000) are equal and agree ...
    assert one(occ("1,234.56", 3), occ("1,23,456", 4, scale=Scale.LAKH)).status is Status.EXTRACTED
    # ... and one lakh apart they are not: equal steps need exact equality.
    assert one(occ("1,234.56", 3), occ("1,23,457", 4, scale=Scale.LAKH)).status is Status.CONFLICTING


def test_a_coarser_scale_can_corroborate_a_finer_one():
    # 12,345.6 lakh and 123.5 crore: the crore value has step 1e6... base units differ by 1e5.
    result = one(occ("12,345.6", 3, scale=Scale.LAKH), occ("123.5", 4))

    assert result.status is Status.EXTRACTED and result.raw_value == "12,345.6"


# --- conflict (B.6 row 8) ----------------------------------------------------------------------------------------


def test_b6_row_8_values_that_disagree_are_conflicting_with_every_candidate():
    result = one(occ("1,234.56", 3), occ("1,198.20", 4))

    assert result.status is Status.CONFLICTING and result.status_reason is None
    assert result.value is None and result.currency is None
    assert [(c.page_number, c.raw_value, c.value) for c in result.candidates] == [
        (3, "1,234.56", Decimal("12345600000.00")),
        (4, "1,198.20", Decimal("11982000000.00")),
    ]  # fmt: skip
    assert result.candidates[0].evidence_quote == "Revenue 1,234.56"
    assert result.corroborating_evidence == ()


def test_a_conflict_records_the_rule_the_values_and_the_primary_page():
    result = one(occ("1,234.56", 4), occ("1,198.20", 3))

    conflict = result.validation.details["conflict"]
    assert conflict == {"rule": "H.4.2", "values": ["11982000000", "12345600000"], "primary_page": 3}
    assert result.page_number == 3  # the record's own evidence is the primary page's


def test_three_occurrences_one_outside_the_tolerance_make_a_conflict_of_all_three():
    result = one(occ("1,234.56", 3), occ("1,235", 4), occ("1,234", 5))

    assert result.status is Status.CONFLICTING and len(result.candidates) == 3


def test_three_consistent_occurrences_are_one_field_with_two_corroborating():
    result = one(occ("1,234.56", 3), occ("1,235", 4), occ("1,235", 5, quote="Highlights 1,235"))

    assert result.status is Status.EXTRACTED and len(result.corroborating_evidence) == 2


def test_negative_and_positive_figures_do_not_agree():
    assert one(occ("(245.10)", 3), occ("245.10", 4)).status is Status.CONFLICTING
    assert one(occ("(245.10)", 3), occ("(245.10)", 4)).status is Status.EXTRACTED


def test_a_reported_nil_agrees_with_a_zero_but_not_with_a_figure():
    assert one(occ("-", 3), occ("0.00", 4)).status is Status.EXTRACTED
    assert one(occ("-", 3), occ("5.00", 4)).status is Status.CONFLICTING


# --- identical evidence is not duplicated ----------------------------------------------------------------------------


def test_the_same_figure_proposed_twice_for_one_row_is_one_occurrence():
    result = one(occ("1,234.56", 3), occ("1,234.56", 3))

    assert result.corroborating_evidence == () and result.status is Status.EXTRACTED


def test_conflicting_candidates_are_not_duplicated_either():
    result = one(occ("1,234.56", 3), occ("1,234.56", 3), occ("1,198.20", 4))

    assert len(result.candidates) == 2


# --- occurrences that failed verification (default 3) ----------------------------------------------------------------


def test_a_failed_occurrence_beside_a_verified_one_is_listed_not_merged():
    failed = occ("9,999.00", 4, status=Status.REQUIRES_REVIEW)
    result = one(occ("1,234.56", 3), failed)

    assert result.status is Status.EXTRACTED and result.raw_value == "1,234.56"
    assert result.validation.details["unverified_occurrences"] == [
        {"page_number": 4, "raw_value": "9,999.00", "evidence_quote": "Revenue 9,999.00",
         "status": "requires_review", "status_reason": "sign_mismatch"}
    ]  # fmt: skip


def test_a_conflict_also_lists_the_failed_occurrences():
    result = one(occ("1,234.56", 3), occ("1,198.20", 4), occ("5.00", 5, status=Status.REQUIRES_REVIEW))

    assert result.status is Status.CONFLICTING
    assert [o["page_number"] for o in result.validation.details["unverified_occurrences"]] == [5]


def test_with_no_verified_occurrence_the_best_ranked_failed_one_is_the_record():
    result = one(occ("5.00", 5, status=Status.REQUIRES_REVIEW), occ("6.00", 3, status=Status.REQUIRES_REVIEW), occ("7.00", 4, status=Status.REQUIRES_REVIEW))

    assert result.status is Status.REQUIRES_REVIEW and result.page_number == 3
    assert [o["page_number"] for o in result.validation.details["other_occurrences"]] == [4, 5]


def test_a_single_failed_occurrence_is_unchanged():
    record = occ("5.00", 5, status=Status.REQUIRES_REVIEW)

    assert one(record) == record


def test_failed_occurrences_never_make_a_conflict():
    result = one(occ("5.00", 3, status=Status.REQUIRES_REVIEW), occ("6.00", 4, status=Status.REQUIRES_REVIEW))

    assert result.status is Status.REQUIRES_REVIEW and result.candidates == ()


# --- the primary statement page ----------------------------------------------------------------------------------------


def test_the_primary_page_is_the_highest_scoring_candidate_of_the_fields_statement_type():
    assert primary_page(LOCATED, REV) == 3
    assert primary_page(pages((7, 5), (6, 5)), REV) == 6  # the lowest page number on a tie
    assert primary_page(pages(), REV) is None
    balance_only = LocatorResult("keywords", (CandidatePage(2, ("balance_sheet",), 9, ()),))
    assert primary_page(balance_only, REV) is None
    assert primary_page(balance_only, FieldName.TOTAL_EQUITY) == 2


def test_the_primary_page_wins_an_exact_tie_even_if_another_page_has_a_lower_number():
    located = pages((4, 5), (5, 9))  # page 5 is primary

    result = one(occ("1,234.56", 4), occ("1,234.56", 5), located=located)

    assert result.page_number == 5 and result.corroborating_evidence[0].page_number == 4


def test_an_exact_tie_goes_to_the_primary_page_then_the_lowest_page():
    on_primary = one(occ("1,234.56", 4), occ("1,234.56", 3, quote="Revenue 1,234.56 (primary)"))
    no_primary = one(occ("1,234.56", 9), occ("1,234.56", 8), located=pages())

    assert on_primary.page_number == 3 and on_primary.corroborating_evidence[0].page_number == 4
    assert no_primary.page_number == 8


# --- determinism and validity ---------------------------------------------------------------------------------------------


def test_the_result_does_not_depend_on_the_order_of_the_occurrences():
    records = [occ("1,234.56", 3), occ("1,235", 4), occ("1,235", 5, quote="Highlights 1,235"), occ("9.00", 6, status=Status.REQUIRES_REVIEW)]
    expected = reconcile(records, LOCATED)
    rng = random.Random(6)
    for _ in range(10):
        shuffled = records[:]
        rng.shuffle(shuffled)
        assert reconcile(shuffled, LOCATED) == expected


def test_the_results_are_json_serialisable_and_valid_records():
    result = reconcile([occ("1,234.56", 3), occ("1,198.20", 4), occ("1.00", 3, role=COMP)], LOCATED)

    json.dumps([r.model_dump(mode="json") for r in result])
    assert all(isinstance(r, ExtractedField) for r in result)


def test_the_inputs_are_not_changed():
    records = [occ("1,234.56", 3), occ("1,198.20", 4)]
    before = [r.model_dump() for r in records]

    reconcile(records, LOCATED)

    assert [r.model_dump() for r in records] == before


def test_properties_over_generated_occurrences():
    rng = random.Random(20261019)
    raws = ["1,234.56", "1,234.5", "1,235", "1,234", "1,198.20", "(245.10)", "-", "0.00", "5.00"]
    for _ in range(300):
        records = [
            occ(rng.choice(raws), page, scale=rng.choice([Scale.CRORE, Scale.LAKH]),
                status=Status.EXTRACTED if rng.random() < 0.8 else Status.REQUIRES_REVIEW,
                quote=f"row {rng.randint(0, 3)}")
            for page in rng.sample([3, 4, 5, 6, 7], rng.randint(1, 4))
        ]  # fmt: skip
        result = one(*records)
        verified = [r for r in records if r.status is Status.EXTRACTED]
        if not verified:
            assert result.status is Status.REQUIRES_REVIEW
        elif result.status is Status.EXTRACTED:
            assert result in verified or result.raw_value in {r.raw_value for r in verified}
            assert result.value is not None
        else:
            assert result.status is Status.CONFLICTING and len(result.candidates) >= 2
            assert result.value is None
        assert reconcile(list(reversed(records)), LOCATED) == (result,)
        assert set(H3_FIELDS) >= {result.field_name}
