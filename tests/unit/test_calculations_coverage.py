"""Every acceptance test and edge case of PRD Section I, as one table; and the purity of the calculation code (PRD FR-007, I.1, I.5; Phase 3 step 3f; B-245)."""

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from calc_records import D24, D25, conflicting, rec
from credit_intel.calculations import calculate, metrics
from credit_intel.calculations.metrics import (
    MetricReason as M,
    current_ratio,
    debt_to_equity,
    interest_coverage,
    net_profit_margin,
    revenue_growth,
)
from credit_intel.models import FieldName as F, PeriodRole, Status

COMP = PeriodRole.COMPARATIVE
OK = Status.EXTRACTED


def r(name, value, **kw):
    return rec(name, value, **kw)


def missing(name, **kw):
    return rec(name, status=Status.NOT_FOUND, **kw)


# (metric, label, call, expected value or MetricReason) -- the PRD's acceptance tests first, then each edge case of I.1 and I.2.
CASES = [
    # MET-01
    ("MET-01", "100 to 110", lambda: revenue_growth(r(F.REVENUE, "110"), r(F.REVENUE, "100", role=COMP, end=D24)), Decimal("10")),
    ("MET-01", "100 to 90", lambda: revenue_growth(r(F.REVENUE, "90"), r(F.REVENUE, "100", role=COMP, end=D24)), Decimal("-10")),
    ("MET-01", "comparative 0", lambda: revenue_growth(r(F.REVENUE, "50"), r(F.REVENUE, "0", role=COMP, end=D24)), M.ZERO_DENOMINATOR),
    ("MET-01", "missing comparative", lambda: revenue_growth(r(F.REVENUE, "110"), missing(F.REVENUE, role=COMP, end=D24)), M.MISSING_INPUT),
    ("MET-01", "comparative below 0", lambda: revenue_growth(r(F.REVENUE, "10"), r(F.REVENUE, "-5", role=COMP, end=D24)), M.NON_POSITIVE_BASE),
    ("MET-01", "current below 0", lambda: revenue_growth(r(F.REVENUE, "-10"), r(F.REVENUE, "100", role=COMP, end=D24)), M.INPUT_REQUIRES_REVIEW),
    ("MET-01", "conflicting input", lambda: revenue_growth(conflicting(F.REVENUE, ["1", "2"]), r(F.REVENUE, "100", role=COMP, end=D24)), M.INPUT_CONFLICTING),
    ("MET-01", "review input", lambda: revenue_growth(rec(F.REVENUE, status=Status.REQUIRES_REVIEW), r(F.REVENUE, "100", role=COMP, end=D24)), M.INPUT_REQUIRES_REVIEW),
    ("MET-01", "two currencies", lambda: revenue_growth(r(F.REVENUE, "110"), r(F.REVENUE, "100", role=COMP, end=D24, currency="USD")), M.CURRENCY_MISMATCH),
    ("MET-01", "periods not consecutive", lambda: revenue_growth(r(F.REVENUE, "110"), r(F.REVENUE, "100", role=COMP, end=date(2023, 3, 31))), M.PERIOD_MISMATCH),
    # MET-02
    ("MET-02", "10 over 200", lambda: net_profit_margin(r(F.NET_PROFIT, "10"), r(F.REVENUE, "200")), Decimal("5")),
    ("MET-02", "loss", lambda: net_profit_margin(r(F.NET_PROFIT, "-10"), r(F.REVENUE, "200")), Decimal("-5")),
    ("MET-02", "revenue 0", lambda: net_profit_margin(r(F.NET_PROFIT, "10"), r(F.REVENUE, "0")), M.ZERO_DENOMINATOR),
    ("MET-02", "revenue below 0", lambda: net_profit_margin(r(F.NET_PROFIT, "10"), r(F.REVENUE, "-200")), M.NON_POSITIVE_BASE),
    ("MET-02", "missing revenue", lambda: net_profit_margin(r(F.NET_PROFIT, "10"), None), M.MISSING_INPUT),
    ("MET-02", "two currencies", lambda: net_profit_margin(r(F.NET_PROFIT, "10", currency="USD"), r(F.REVENUE, "200")), M.CURRENCY_MISMATCH),
    ("MET-02", "two period ends", lambda: net_profit_margin(r(F.NET_PROFIT, "10", end=date(2025, 4, 1)), r(F.REVENUE, "200")), M.PERIOD_MISMATCH),
    # MET-03
    ("MET-03", "150 over 100", lambda: current_ratio(r(F.CURRENT_ASSETS, "150"), r(F.CURRENT_LIABILITIES, "100")), Decimal("1.5")),
    ("MET-03", "80 over 100", lambda: current_ratio(r(F.CURRENT_ASSETS, "80"), r(F.CURRENT_LIABILITIES, "100")), Decimal("0.8")),
    ("MET-03", "liabilities 0", lambda: current_ratio(r(F.CURRENT_ASSETS, "100"), r(F.CURRENT_LIABILITIES, "0")), M.ZERO_DENOMINATOR),
    ("MET-03", "negative input", lambda: current_ratio(r(F.CURRENT_ASSETS, "-1"), r(F.CURRENT_LIABILITIES, "100")), M.INPUT_REQUIRES_REVIEW),
    ("MET-03", "missing assets", lambda: current_ratio(None, r(F.CURRENT_LIABILITIES, "100")), M.MISSING_INPUT),
    # MET-04
    ("MET-04", "200 over 100", lambda: debt_to_equity(r(F.TOTAL_BORROWINGS, "200"), r(F.TOTAL_EQUITY, "100")), Decimal("2")),
    ("MET-04", "no borrowings", lambda: debt_to_equity(r(F.TOTAL_BORROWINGS, "0"), r(F.TOTAL_EQUITY, "100")), Decimal("0")),
    ("MET-04", "negative equity", lambda: debt_to_equity(r(F.TOTAL_BORROWINGS, "50"), r(F.TOTAL_EQUITY, "-10")), M.NOT_MEANINGFUL_NEGATIVE_EQUITY),
    ("MET-04", "equity 0", lambda: debt_to_equity(r(F.TOTAL_BORROWINGS, "50"), r(F.TOTAL_EQUITY, "0")), M.ZERO_DENOMINATOR),
    ("MET-04", "borrowings not found", lambda: debt_to_equity(missing(F.TOTAL_BORROWINGS), r(F.TOTAL_EQUITY, "100")), M.MISSING_INPUT),
    # MET-05
    ("MET-05", "300 over 100", lambda: interest_coverage(r(F.EBIT, "300"), r(F.INTEREST_EXPENSE, "100")), Decimal("3")),
    ("MET-05", "negative EBIT", lambda: interest_coverage(r(F.EBIT, "-50"), r(F.INTEREST_EXPENSE, "100")), Decimal("-0.5")),
    ("MET-05", "no interest", lambda: interest_coverage(r(F.EBIT, "300"), r(F.INTEREST_EXPENSE, "0")), M.NOT_APPLICABLE_NO_INTEREST),
    ("MET-05", "negative interest", lambda: interest_coverage(r(F.EBIT, "300"), r(F.INTEREST_EXPENSE, "-1")), M.INPUT_REQUIRES_REVIEW),
]


@pytest.mark.parametrize(("metric", "label", "call", "expected"), CASES, ids=[f"{c[0]} {c[1]}" for c in CASES])
def test_the_prd_case(metric, label, call, expected):
    result = call()

    assert result.metric_id == metric
    if isinstance(expected, Decimal):
        assert result.value == expected and result.undefined_reason is None
    else:
        assert result.value is None and result.undefined_reason is expected


def test_every_undefined_reason_of_the_prds_list_is_exercised_by_the_table():
    expected_reasons = {case[3] for case in CASES if isinstance(case[3], M)}

    assert expected_reasons == set(M)


def test_every_metric_has_its_prd_acceptance_tests_in_the_table():
    counts = {}
    for case in CASES:
        counts[case[0]] = counts.get(case[0], 0) + 1

    assert set(counts) == {"MET-01", "MET-02", "MET-03", "MET-04", "MET-05"} and min(counts.values()) >= 4  # the PRD gives 3 or 4 acceptance tests per metric, plus edge cases


# --- the calculation code is pure and uses Decimal throughout (FR-007.1, I.1) --------------------------------------------------------

PACKAGE = Path(metrics.__file__).parent
BANNED_IMPORTS = {"random", "os", "sys", "socket", "subprocess", "requests", "httpx", "httpx2", "openai", "urllib", "shutil", "tempfile", "time", "logging", "pathlib", "secrets", "uuid"}


def _modules():
    return sorted(PACKAGE.glob("*.py"))


def test_the_package_has_the_expected_modules():
    assert {p.name for p in _modules()} >= {"__init__.py", "derived.py", "borrowings.py", "metrics.py", "calculate.py"}


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_module_imports_anything_that_does_io_or_randomness_or_a_model(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert not imported & BANNED_IMPORTS, imported & BANNED_IMPORTS
    assert "llm" not in {part for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module for part in node.module.split(".")}


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_module_calls_open_print_or_float_and_none_has_a_float_literal(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "float", "input", "eval", "exec"}, node.func.id
        if isinstance(node, ast.Constant):
            assert not isinstance(node.value, float), node.value


def test_the_metric_set_module_is_pure_in_the_same_sense():
    assert calculate.__file__.startswith(str(PACKAGE))
