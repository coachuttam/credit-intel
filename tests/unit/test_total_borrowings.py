"""Total borrowings by BORR-SUM, its four classifications and the not-presented caveat (PRD H.5 rules 4 and 5, D-12, OD-9, MET-04; Phase 3 step 3b; B-243)."""

import random
from decimal import Decimal

import pytest

from calc_records import CUR, D24, D25, conflicting, rec
from credit_intel.calculations.borrowings import (
    BORR_SUM,
    CAVEAT_NOT_PRESENTED,
    INCLUDED_IN_CURRENT,
    NOT_PRESENTED,
    SEPARATE_COMPONENT,
    UNRESOLVED,
    caveats_of,
    classify_current_maturities,
    derive_total_borrowings,
    total_borrowings_for,
)
from credit_intel.calculations.calculate import calculate_metrics, compare
from credit_intel.calculations.metrics import MetricReason as M, debt_to_equity
from credit_intel.config import BorrowingSettings
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status, StatusReason as R

COMP = PeriodRole.COMPARATIVE
NC, CURB, CM, TOT = F.BORROWINGS_NON_CURRENT, F.BORROWINGS_CURRENT, F.CURRENT_MATURITIES_LONG_TERM_BORROWINGS, F.TOTAL_BORROWINGS


def parts(nc="700", cur="300", cm=None, cur_label=None, cm_label=None, **kw):
    maturities = None if cm is None else rec(CM, cm, label=cm_label, **kw) if cm != "absent" else rec(CM, status=Status.NOT_FOUND, **kw)
    return rec(NC, nc, **kw), rec(CURB, cur, label=cur_label, **kw), maturities


# --- the four cases (H.5 rule 5) -----------------------------------------------------------------------------------------------


def test_no_current_maturities_row_is_not_presented():
    nc, cur, _ = parts()

    assert classify_current_maturities(cur, None) == NOT_PRESENTED
    assert classify_current_maturities(cur, rec(CM, status=Status.NOT_FOUND)) == NOT_PRESENTED


def test_an_inclusion_phrase_in_the_current_borrowings_label_means_included_in_current():
    _, cur, cm = parts(cm="50", cur_label="Current borrowings (including current maturities)")

    assert classify_current_maturities(cur, cm) == INCLUDED_IN_CURRENT


def test_an_inclusion_phrase_counts_even_with_no_current_maturities_row():
    _, cur, _ = parts(cur_label="Borrowings including current maturities")

    assert classify_current_maturities(cur, None) == INCLUDED_IN_CURRENT


def test_an_exclusion_phrase_in_either_label_means_a_separate_component():
    _, cur, cm = parts(cm="50", cur_label="Current borrowings excluding current maturities")
    assert classify_current_maturities(cur, cm) == SEPARATE_COMPONENT
    _, cur, cm = parts(cm="50", cm_label="Current maturities of long-term borrowings (excluding current maturities of leases)")
    assert classify_current_maturities(cur, cm) == SEPARATE_COMPONENT  # the PRD's phrase appears in the row label


def test_its_own_row_with_no_phrase_is_unresolved():
    _, cur, cm = parts(cm="50")

    assert classify_current_maturities(cur, cm) == UNRESOLVED


def test_matching_ignores_case_and_needs_whole_words():
    _, cur, cm = parts(cm="50", cur_label="CURRENT BORROWINGS INCLUDING CURRENT MATURITIES")
    assert classify_current_maturities(cur, cm) == INCLUDED_IN_CURRENT
    _, cur, cm = parts(cm="50", cur_label="Current borrowings reincluding current maturitiesx")
    assert classify_current_maturities(cur, cm) == UNRESOLVED


def test_inclusion_is_checked_before_exclusion_so_a_double_count_cannot_happen():
    _, cur, cm = parts(cm="50", cur_label="Current borrowings including current maturities, excluding current maturities of leases")

    assert classify_current_maturities(cur, cm) == INCLUDED_IN_CURRENT


def test_the_phrase_lists_are_configurable():
    settings = BorrowingSettings(inclusion_phrases=("with current portion",), exclusion_phrases=("without current portion",))
    _, cur, cm = parts(cm="50", cur_label="Debt with current portion")

    assert classify_current_maturities(cur, cm, settings) == INCLUDED_IN_CURRENT
    assert classify_current_maturities(*parts(cm="50", cur_label="Debt including current maturities")[1:], settings) == UNRESOLVED


# --- the derived total: Appendix B.6 examples 40 to 44 ----------------------------------------------------------------------------


def test_b6_row_40_the_two_presented_lines_are_summed_with_the_not_presented_classification():
    result = derive_total_borrowings(*parts())

    assert result.status is Status.EXTRACTED and result.value == Decimal("1000") and result.currency == "INR"
    assert result.derivation.method_id == BORR_SUM and result.derivation.component_classification == NOT_PRESENTED
    assert result.derivation.formula == "total_borrowings = borrowings_non_current + borrowings_current"
    assert result.derivation.input_field_ids == ("borrowings_non_current.2025-03-31.consolidated", "borrowings_current.2025-03-31.consolidated")
    assert caveats_of(result) == (CAVEAT_NOT_PRESENTED,)


def test_b6_row_40_debt_to_equity_carries_the_caveat():
    total = derive_total_borrowings(*parts())

    result = debt_to_equity(total, rec(F.TOTAL_EQUITY, "500"))

    assert result.value == Decimal("2") and result.caveats == (CAVEAT_NOT_PRESENTED,)


def test_b6_row_41_a_reported_total_is_used_as_reported_with_no_caveat():
    reported = rec(TOT, "1200")
    fs = FieldSet(Basis.CONSOLIDATED, (reported, *[r for r in parts() if r is not None]), (), (), ())

    chosen = total_borrowings_for(fs, CUR)

    assert chosen is reported and caveats_of(chosen) == () and debt_to_equity(chosen, rec(F.TOTAL_EQUITY, "600")).caveats == ()


def test_b6_row_42_a_missing_current_borrowings_gives_not_found_and_no_caveat():
    nc, _, _ = parts()
    result = derive_total_borrowings(nc, rec(CURB, status=Status.NOT_FOUND), None)

    assert result.status is Status.NOT_FOUND and result.status_reason is R.MISSING_INPUT and result.value is None
    assert caveats_of(result) == ()


def test_b6_row_43_a_reported_nil_component_is_zero_not_missing():
    result = derive_total_borrowings(rec(NC, "0"), rec(CURB, "300"), None)

    assert result.status is Status.EXTRACTED and result.value == Decimal("300") and caveats_of(result) == (CAVEAT_NOT_PRESENTED,)


def test_b6_row_44_a_separate_component_is_added_and_has_no_not_presented_caveat():
    result = derive_total_borrowings(*parts(cm="50", cur_label="Current borrowings excluding current maturities"))

    assert result.value == Decimal("1050") and result.derivation.component_classification == SEPARATE_COMPONENT
    assert result.derivation.formula.endswith("+ current_maturities_long_term_borrowings")
    assert len(result.derivation.input_field_ids) == 3 and caveats_of(result) == ()


def test_an_included_row_is_not_added_so_nothing_is_counted_twice():
    result = derive_total_borrowings(*parts(cm="50", cur_label="Current borrowings including current maturities"))

    assert result.value == Decimal("1000") and result.derivation.component_classification == INCLUDED_IN_CURRENT and caveats_of(result) == ()


def test_an_unresolved_row_needs_review_and_records_all_three_inputs():
    result = derive_total_borrowings(*parts(cm="50"))

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason is R.BORROWINGS_CLASSIFICATION_UNRESOLVED
    assert result.value is None and result.derivation.component_classification == UNRESOLVED
    assert result.derivation.input_field_ids[-1] == "current_maturities_long_term_borrowings.2025-03-31.consolidated"
    assert caveats_of(result) == ()


def test_a_missing_component_outranks_an_unresolved_row():
    result = derive_total_borrowings(rec(NC, status=Status.NOT_FOUND), rec(CURB, "300"), rec(CM, "50"))

    assert result.status is Status.NOT_FOUND and result.status_reason is R.MISSING_INPUT


# --- statuses of the inputs, currency and period (rules 1, 2 and 4) -----------------------------------------------------------


def test_a_component_that_needs_review_gives_a_total_that_needs_review_with_its_reason():
    result = derive_total_borrowings(rec(NC, status=Status.REQUIRES_REVIEW, reason=R.SCALE_AMBIGUOUS), rec(CURB, "300"), None)

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason is R.SCALE_AMBIGUOUS and caveats_of(result) == ()


def test_a_conflicting_component_gives_the_combined_candidate_totals():
    result = derive_total_borrowings(conflicting(NC, ["700", "710"]), rec(CURB, "300"), None)

    assert result.status is Status.CONFLICTING and sorted(c.value for c in result.candidates) == [Decimal("1000"), Decimal("1010")]


def test_components_in_two_currencies_need_review():
    result = derive_total_borrowings(rec(NC, "700", currency="USD"), rec(CURB, "300"), None)

    assert result.status_reason is R.CURRENCY_MISMATCH and result.status is Status.REQUIRES_REVIEW


def test_without_any_record_there_is_no_total():
    assert derive_total_borrowings(None, None, None) is None


def test_the_comparative_period_has_its_own_total_and_id():
    kw = dict(role=COMP, end=D24)
    result = derive_total_borrowings(*parts("600", "200", **kw))

    assert result.value == Decimal("800") and result.field_id == "total_borrowings.2024-03-31.consolidated" and result.period_role is COMP


# --- choosing between a reported and a derived total -------------------------------------------------------------------------------


def field_set(records):
    return FieldSet(Basis.CONSOLIDATED, tuple(r for r in records if r is not None), (), (), ())


def test_a_reported_total_that_needs_review_is_still_the_reported_total():
    reported = rec(TOT, status=Status.REQUIRES_REVIEW)

    assert total_borrowings_for(field_set([reported, *parts()]), CUR) is reported  # like operating profit: reported means reported


def test_a_total_that_was_not_found_is_derived_from_the_components():
    fs = field_set([rec(TOT, status=Status.NOT_FOUND), *parts()])

    chosen = total_borrowings_for(fs, CUR)

    assert chosen.origin.value == "derived" and chosen.value == Decimal("1000")


def test_with_neither_a_total_nor_components_the_total_is_just_not_found():
    not_found = rec(TOT, status=Status.NOT_FOUND)

    assert total_borrowings_for(field_set([not_found]), CUR).status is Status.NOT_FOUND
    assert total_borrowings_for(field_set([]), CUR) is None


# --- caveats reach the metric, the comparison and the metric set ----------------------------------------------------------------


def test_the_caveat_stays_on_a_zero_figure():
    zero = derive_total_borrowings(rec(NC, "0"), rec(CURB, "0"), None)

    result = debt_to_equity(zero, rec(F.TOTAL_EQUITY, "100"))

    assert result.value == Decimal("0") and result.caveats == (CAVEAT_NOT_PRESENTED,)


def test_a_missing_total_has_no_caveat_to_carry():
    assert debt_to_equity(None, rec(F.TOTAL_EQUITY, "100")).caveats == ()


def test_a_comparison_carries_the_caveats_of_either_side():
    caveated = debt_to_equity(derive_total_borrowings(*parts()), rec(F.TOTAL_EQUITY, "500"))
    plain = debt_to_equity(rec(TOT, "400", role=COMP, end=D24), rec(F.TOTAL_EQUITY, "500", role=COMP, end=D24))

    assert compare(caveated, plain).caveats == (CAVEAT_NOT_PRESENTED,)
    assert compare(plain, caveated).caveats == (CAVEAT_NOT_PRESENTED,)
    assert compare(caveated, caveated).caveats == (CAVEAT_NOT_PRESENTED,)  # once, not twice
    assert compare(plain, plain).caveats == ()


def test_the_metric_set_derives_the_total_when_none_is_reported_and_labels_it():
    values = {F.TOTAL_EQUITY: "500", F.REVENUE: "1000", F.NET_PROFIT: "50", F.CURRENT_ASSETS: "300", F.CURRENT_LIABILITIES: "200"}
    records = []
    for role, end, nc, cur in ((CUR, D25, "700", "300"), (COMP, D24, "400", "200")):
        records += [rec(n, v, role=role, end=end) for n, v in values.items()]
        records += [rec(NC, nc, role=role, end=end), rec(CURB, cur, role=role, end=end)]

    metrics = calculate_metrics(FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ()))

    assert metrics.get("MET-04", CUR).value == Decimal("2") and metrics.get("MET-04", COMP).value == Decimal("1.2")
    assert metrics.get("MET-04", CUR).caveats == (CAVEAT_NOT_PRESENTED,)
    assert metrics.comparison("MET-04").caveats == (CAVEAT_NOT_PRESENTED,) and metrics.get("MET-03", CUR).caveats == ()
    assert metrics.get("MET-04", CUR).undefined_reason is None and M.MISSING_INPUT not in {metrics.get("MET-04", CUR).undefined_reason}


# --- property ----------------------------------------------------------------------------------------------------------------------


def test_property_the_total_is_the_exact_sum_of_its_components_and_the_caveat_follows_the_classification():
    rng = random.Random(70)
    for _ in range(300):
        nc, cur, cm = (Decimal(rng.randint(0, 10**6)) / 100 for _ in range(3))
        label = rng.choice([None, "Current borrowings including current maturities", "Current borrowings excluding current maturities"])
        with_row = rng.choice([True, False])
        maturities = rec(CM, str(cm)) if with_row else None
        if with_row and label == "Current borrowings excluding current maturities":
            maturities = rec(CM, str(cm), label="Current maturities (excluding current maturities of leases)")

        result = derive_total_borrowings(rec(NC, str(nc)), rec(CURB, str(cur), label=label), maturities)

        case = classify_current_maturities(rec(CURB, "1", label=label), maturities)
        if case == UNRESOLVED:
            assert result.status is Status.REQUIRES_REVIEW
            continue
        expected = nc + cur + (cm if case == SEPARATE_COMPONENT else 0)
        assert result.value == expected and (caveats_of(result) == (CAVEAT_NOT_PRESENTED,)) == (case == NOT_PRESENTED)
