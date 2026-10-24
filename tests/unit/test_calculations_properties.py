"""Cross-module properties of the calculation code on random field sets (PRD I.1, FR-007; Phase 3 step 3f; B-246). Fixed seeds."""

import random
from decimal import Decimal

from calc_records import CUR, D24, D25, rec
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status, StatusReason as R

COMP = PeriodRole.COMPARATIVE
NAMES = [n for n in F if n is not F.EBIT]
STATUSES = [Status.EXTRACTED] * 6 + [Status.NOT_FOUND, Status.REQUIRES_REVIEW]  # mostly usable, sometimes not


def random_field_set(rng, absent=0.1):
    """Random statuses and amounts (zero, negative and large included); some records absent altogether."""
    records = []
    for role, end in ((CUR, D25), (COMP, D24)):
        for name in NAMES:
            if rng.random() < absent:
                continue
            status = rng.choice(STATUSES)
            if status is Status.EXTRACTED:
                value = rng.choice(["0", "1", "-1", "7.5", "100", "-250.25", str(rng.randint(-10**6, 10**6) / 100)])
                records.append(rec(name, value, role=role, end=end, currency=rng.choice(["INR"] * 9 + ["USD"])))
            elif status is Status.NOT_FOUND:
                records.append(rec(name, status=status, role=role, end=end))
            else:
                records.append(rec(name, status=status, reason=R.SCALE_AMBIGUOUS, role=role, end=end))
    return FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ())


def test_property_no_random_field_set_raises_and_every_result_has_a_value_or_a_reason():
    rng = random.Random(80)
    for _ in range(400):
        metrics = calculate_metrics(random_field_set(rng))

        for result in metrics.results.values():
            assert (result.value is None) != (result.undefined_reason is None)
        for comparison in metrics.comparisons.values():
            assert (comparison.relative_change is None) != (comparison.undefined_reason is None)


def test_property_a_defined_result_has_every_input_value_and_no_float_anywhere():
    rng = random.Random(81)
    for _ in range(400):
        metrics = calculate_metrics(random_field_set(rng))

        for result in metrics.results.values():
            for value in result.input_values:
                assert value is None or isinstance(value, Decimal)
            if result.value is not None:
                assert isinstance(result.value, Decimal) and all(v is not None for v in result.input_values)
        for comparison in metrics.comparisons.values():
            assert comparison.relative_change is None or isinstance(comparison.relative_change, Decimal)


def test_property_scaling_every_amount_changes_no_ratio_and_no_comparison():
    rng = random.Random(82)
    for _ in range(150):
        seed = rng.randint(0, 10**9)
        base = random_field_set(random.Random(seed))
        k = Decimal(rng.randint(2, 400))
        scaled = FieldSet(
            base.configured_basis,
            tuple(r.model_copy(update={"value": None if r.value is None else r.value * k}) for r in base.fields),
            (), (), (),
        )  # fmt: skip
        a, b = calculate_metrics(base), calculate_metrics(scaled)
        for key, result in a.results.items():
            assert result.value == b.results[key].value and result.undefined_reason == b.results[key].undefined_reason, key
        for metric, comparison in a.comparisons.items():
            assert comparison.relative_change == b.comparisons[metric].relative_change


def test_property_the_same_field_set_always_gives_the_same_answer_and_is_not_changed():
    rng = random.Random(83)
    for _ in range(150):
        field_set = random_field_set(rng)
        before = [r.model_dump() for r in field_set.fields]

        first, second = calculate_metrics(field_set), calculate_metrics(field_set)

        assert first.results == second.results and first.comparisons == second.comparisons and first.derived == second.derived
        assert [r.model_dump() for r in field_set.fields] == before


def test_property_a_change_to_a_field_a_metric_does_not_read_leaves_that_metric_alone():
    rng = random.Random(84)
    reads = {"MET-02": {F.NET_PROFIT, F.REVENUE}, "MET-03": {F.CURRENT_ASSETS, F.CURRENT_LIABILITIES}}
    for _ in range(200):
        fs = random_field_set(rng, absent=0.0)
        victim = rng.choice([n for n in NAMES if n not in reads["MET-03"]])  # not an input of the current ratio
        changed = FieldSet(
            fs.configured_basis,
            tuple(rec(r.field_name, "999", role=r.period_role, end=r.period_end) if r.field_name is victim else r for r in fs.fields),
            (), (), (),
        )  # fmt: skip
        assert calculate_metrics(fs).results[("MET-03", CUR)] == calculate_metrics(changed).results[("MET-03", CUR)]
        assert calculate_metrics(fs).results[("MET-03", COMP)] == calculate_metrics(changed).results[("MET-03", COMP)]


def test_property_the_current_period_never_reads_the_comparative_one_except_growth_and_comparisons():
    rng = random.Random(85)
    for _ in range(200):
        fs = random_field_set(rng)
        without = FieldSet(fs.configured_basis, tuple(r for r in fs.fields if r.period_role is CUR), (), (), ())

        a, b = calculate_metrics(fs), calculate_metrics(without)

        for metric in ("MET-02", "MET-03", "MET-04", "MET-05"):
            assert a.results[(metric, CUR)] == b.results[(metric, CUR)], metric
