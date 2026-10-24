"""RI-006 missing financial information and RI-007 conflicting or unverified source values (PRD J.3, FR-008; Phase 4 step 4e; B-251)."""

import random
from decimal import Decimal

import pytest

from calc_records import CUR, D24, D25, conflicting, rec
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status, StatusReason as Reason
from credit_intel.risk.config import load_risk_rules
from credit_intel.risk.results import ConditionOutcome as C, RuleOutcome as R
from credit_intel.risk.rules import RULE_FUNCTIONS, missing_financial_information, unverified_source_values
from credit_intel.risk.spec import Severity

COMP = PeriodRole.COMPARATIVE
CONFIG = load_risk_rules()
FULL = {F.REVENUE: "1000", F.NET_PROFIT: "100", F.CURRENT_ASSETS: "300", F.CURRENT_LIABILITIES: "200",
        F.TOTAL_BORROWINGS: "400", F.TOTAL_EQUITY: "500", F.PROFIT_BEFORE_TAX: "150", F.INTEREST_EXPENSE: "30"}  # fmt: skip


def build(current=None, comparative=None, extra=(), ignored=()):
    cur = FULL if current is None else current
    com = FULL if comparative is None else comparative
    records = [rec(n, v, role=CUR, end=D25) for n, v in cur.items() if v is not None]
    records += [rec(n, v, role=COMP, end=D24) for n, v in com.items() if v is not None]
    records += list(extra)
    field_set = FieldSet(Basis.CONSOLIDATED, tuple(records), tuple(ignored), (), ())
    return field_set, calculate_metrics(field_set)


def ri006(**kw):
    field_set, metrics = build(**kw)
    return missing_financial_information(CONFIG.rule("RI-006"), field_set, metrics)


def ri007(**kw):
    field_set, metrics = build(**kw)
    return unverified_source_values(CONFIG.rule("RI-007"), field_set, metrics)


def without(*names):
    return {n: v for n, v in FULL.items() if n not in names}


# --- RI-006: an input the five metrics need was not found (info) --------------------------------------------------------------------------


def test_ri006_with_every_input_present_does_not_fire():
    result = ri006()

    assert result.outcome is R.NOT_TRIGGERED and result.severity is None
    assert result.conditions[0].outcome is C.NOT_FIRED and result.conditions[0].values_used == (("inputs_not_found", Decimal(0)),)


@pytest.mark.parametrize("name", [F.REVENUE, F.NET_PROFIT, F.CURRENT_ASSETS, F.CURRENT_LIABILITIES, F.TOTAL_BORROWINGS, F.TOTAL_EQUITY, F.INTEREST_EXPENSE])
def test_ri006_fires_when_any_input_is_missing_in_the_current_period(name):
    result = ri006(current=without(name))

    assert result.outcome is R.TRIGGERED and result.severity is Severity.INFO
    if name is F.INTEREST_EXPENSE:  # EBIT from profit before tax needs interest, so EBIT goes missing with it
        assert result.conditions[0].values_used == (("inputs_not_found", Decimal(2)),)
        assert result.conditions[0].field_ids == ("ebit.2025-03-31.consolidated", "interest_expense.current")
    else:
        assert result.conditions[0].values_used == (("inputs_not_found", Decimal(1)),)
        assert result.conditions[0].field_ids == (f"{name.value}.current",)


def test_ri006_fires_when_an_input_is_missing_in_the_comparative_period_only():
    result = ri006(comparative=without(F.REVENUE))

    assert result.outcome is R.TRIGGERED and result.conditions[0].field_ids == ("revenue.comparative",)


def test_ri006_names_a_not_found_record_by_its_field_id():
    result = ri006(current=without(F.REVENUE), extra=[rec(F.REVENUE, status=Status.NOT_FOUND, role=CUR, end=D25)])

    assert result.conditions[0].field_ids == ("revenue.2025-03-31.consolidated",)
    assert result.conditions[0].note == "not found: revenue.2025-03-31.consolidated"


def test_ri006_counts_every_missing_input_in_both_periods():
    result = ri006(current=without(F.REVENUE, F.NET_PROFIT), comparative=without(F.TOTAL_EQUITY))

    assert result.conditions[0].values_used == (("inputs_not_found", Decimal(3)),)
    assert len(result.conditions[0].field_ids) == 3


def test_ri006_an_absent_operating_profit_does_not_count_when_ebit_can_be_derived():
    # FULL has profit before tax and interest but no operating profit: EBIT-PBT is available
    assert ri006().outcome is R.NOT_TRIGGERED


def test_ri006_an_absent_ebit_counts_when_neither_method_can_run():
    result = ri006(current=without(F.PROFIT_BEFORE_TAX))

    assert result.outcome is R.TRIGGERED
    assert result.conditions[0].field_ids == ("ebit.2025-03-31.consolidated",)


def test_ri006_a_reported_operating_profit_alone_supplies_ebit_but_interest_is_still_needed():
    current = without(F.PROFIT_BEFORE_TAX, F.INTEREST_EXPENSE)
    current[F.OPERATING_PROFIT] = "200"

    result = ri006(current=current)

    assert result.conditions[0].field_ids == ("interest_expense.current",)  # EBIT is there, interest is not


def test_ri006_a_total_derived_from_components_counts_as_present():
    components = without(F.TOTAL_BORROWINGS)
    components[F.BORROWINGS_NON_CURRENT], components[F.BORROWINGS_CURRENT] = "300", "100"

    assert ri006(current=components, comparative=components).outcome is R.NOT_TRIGGERED


def test_ri006_borrowings_with_only_one_component_are_missing():
    one = without(F.TOTAL_BORROWINGS)
    one[F.BORROWINGS_NON_CURRENT] = "300"

    result = ri006(current=one)

    assert result.outcome is R.TRIGGERED and result.conditions[0].field_ids[0].startswith("total_borrowings.2025-03-31")


def test_ri006_a_field_that_needs_review_is_not_missing_it_is_ri007s_business():
    review = rec(F.REVENUE, status=Status.REQUIRES_REVIEW, role=CUR, end=D25)

    assert ri006(current=without(F.REVENUE), extra=[review]).outcome is R.NOT_TRIGGERED


def test_ri006_with_no_comparative_period_at_all_lists_the_comparative_inputs():
    field_set, metrics = build(comparative={})

    result = missing_financial_information(CONFIG.rule("RI-006"), field_set, metrics)

    assert result.outcome is R.TRIGGERED
    assert all(ref.endswith(".comparative") for ref in result.conditions[0].field_ids) and len(result.conditions[0].field_ids) == 8  # all eight inputs, EBIT included


def test_ri006_is_always_evaluable_even_with_nothing_at_all():
    field_set, metrics = build(current={}, comparative={})

    result = missing_financial_information(CONFIG.rule("RI-006"), field_set, metrics)

    assert result.outcome is R.TRIGGERED and result.conditions[0].outcome is C.FIRED and result.missing_inputs == ()


# --- RI-007: a source field is conflicting or needs review (watch) -------------------------------------------------------------------------


def test_ri007_with_every_field_verified_does_not_fire():
    result = ri007()

    assert result.outcome is R.NOT_TRIGGERED and result.severity is None
    assert result.conditions[0].values_used == (("fields_conflicting", Decimal(0)), ("fields_requires_review", Decimal(0)))


def test_ri007_fires_on_a_field_that_needs_review():
    review = rec(F.REVENUE, status=Status.REQUIRES_REVIEW, reason=Reason.PERIOD_NOT_VERIFIED, role=CUR, end=D25)

    result = ri007(current=without(F.REVENUE), extra=[review])

    assert result.outcome is R.TRIGGERED and result.severity is Severity.WATCH
    assert result.conditions[0].field_ids == ("revenue.2025-03-31.consolidated",)
    assert result.conditions[0].note == "revenue.2025-03-31.consolidated (requires_review: period_not_verified)"


def test_ri007_fires_on_a_conflicting_field_and_counts_each_kind():
    review = rec(F.REVENUE, status=Status.REQUIRES_REVIEW, role=CUR, end=D25)
    clash = conflicting(F.NET_PROFIT, ["1", "2"])

    result = ri007(current=without(F.REVENUE, F.NET_PROFIT), extra=[review, clash])

    assert result.conditions[0].values_used == (("fields_conflicting", Decimal(1)), ("fields_requires_review", Decimal(1)))
    assert "(conflicting)" in result.conditions[0].note and len(result.conditions[0].field_ids) == 2


def test_ri007_counts_fields_no_metric_reads():
    # an operating profit held for review (as the model's mislabelled profit before tax was) still triggers it
    review = rec(F.OPERATING_PROFIT, status=Status.REQUIRES_REVIEW, reason=Reason.LABEL_NOT_RECOGNISED, role=CUR, end=D25)

    result = ri007(extra=[review])

    assert result.outcome is R.TRIGGERED and result.conditions[0].field_ids == ("operating_profit.2025-03-31.consolidated",)


def test_ri007_does_not_count_a_field_that_was_not_found():
    assert ri007(extra=[rec(F.OPERATING_PROFIT, status=Status.NOT_FOUND, role=CUR, end=D25)]).outcome is R.NOT_TRIGGERED


def test_ri007_does_not_count_fields_of_another_basis_set_aside_by_the_run():
    other = rec(F.REVENUE, status=Status.REQUIRES_REVIEW, role=CUR, end=D25, basis=Basis.STANDALONE)

    assert ri007(ignored=[other]).outcome is R.NOT_TRIGGERED


def test_ri007_does_not_count_derived_values_only_the_source_fields_behind_them():
    review = rec(F.PROFIT_BEFORE_TAX, status=Status.REQUIRES_REVIEW, role=CUR, end=D25)

    result = ri007(current=without(F.PROFIT_BEFORE_TAX), extra=[review])

    assert result.conditions[0].field_ids == ("profit_before_tax.2025-03-31.consolidated",)  # EBIT is derived requires_review too, uncounted


def test_ri007_ignores_a_derived_record_even_if_one_is_present_in_the_field_set():
    from credit_intel.calculations.derived import derive_ebit

    derived = derive_ebit(rec(F.OPERATING_PROFIT, status=Status.REQUIRES_REVIEW, role=CUR, end=D25), None, None)

    assert derived.origin.value == "derived" and derived.status is Status.REQUIRES_REVIEW
    assert ri007(extra=[derived]).outcome is R.NOT_TRIGGERED  # only source fields are reported


def test_ri007_counts_both_periods():
    review = rec(F.REVENUE, status=Status.REQUIRES_REVIEW, role=COMP, end=D24)

    result = ri007(comparative=without(F.REVENUE), extra=[review])

    assert result.outcome is R.TRIGGERED and result.conditions[0].field_ids == ("revenue.2024-03-31.consolidated",)


def test_ri007_is_always_evaluable():
    field_set, metrics = build(current={}, comparative={})

    assert unverified_source_values(CONFIG.rule("RI-007"), field_set, metrics).outcome is R.NOT_TRIGGERED


# --- both: registration, repeatability and properties --------------------------------------------------------------------------------------


def test_the_seven_rules_are_all_registered():
    assert set(RULE_FUNCTIONS) == {f"RI-00{n}" for n in range(1, 8)}


NAMES = [n for n in F if n is not F.EBIT]
STATUSES = [Status.EXTRACTED] * 5 + [Status.NOT_FOUND, Status.REQUIRES_REVIEW]


def random_field_set(rng):
    records = []
    for role, end in ((CUR, D25), (COMP, D24)):
        for name in NAMES:
            if rng.random() < 0.08:
                continue
            status = rng.choice(STATUSES)
            if status is Status.EXTRACTED:
                records.append(rec(name, rng.choice(["1", "0", "-3", "250"]), role=role, end=end))
            elif status is Status.NOT_FOUND:
                records.append(rec(name, status=status, role=role, end=end))
            else:
                records.append(rec(name, status=status, role=role, end=end))
    return FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ())


def test_property_ri007_fires_exactly_when_a_source_field_is_flagged_and_ri006_is_never_not_evaluable():
    rng = random.Random(100)
    for _ in range(300):
        field_set = random_field_set(rng)
        metrics = calculate_metrics(field_set)

        seven = unverified_source_values(CONFIG.rule("RI-007"), field_set, metrics)
        six = missing_financial_information(CONFIG.rule("RI-006"), field_set, metrics)

        flagged = any(r.status in (Status.CONFLICTING, Status.REQUIRES_REVIEW) for r in field_set.fields)
        assert (seven.outcome is R.TRIGGERED) == flagged and seven.outcome is not R.NOT_EVALUABLE
        assert six.outcome in (R.TRIGGERED, R.NOT_TRIGGERED) and six.missing_inputs == ()


def test_property_the_evaluation_is_repeatable_and_leaves_the_field_set_unchanged():
    rng = random.Random(101)
    for _ in range(100):
        field_set = random_field_set(rng)
        metrics = calculate_metrics(field_set)
        before = [r.model_dump() for r in field_set.fields]

        first = [f(CONFIG.rule(i), field_set, metrics) for i, f in RULE_FUNCTIONS.items()]
        second = [f(CONFIG.rule(i), field_set, metrics) for i, f in RULE_FUNCTIONS.items()]

        assert first == second and [r.model_dump() for r in field_set.fields] == before
