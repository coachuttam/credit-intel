"""Golden output for the metrics, checked in a fresh process and by independent arithmetic (PRD FR-007, I.5; Phase 3 step 3f; B-244).

The fixed synthetic field set is in ``calc_golden.py`` (no real document). The golden file
``tests/fixtures/metrics_golden.json`` was reviewed by hand: every number in it was recomputed from the
inputs with exact fractions (``test_the_golden_numbers_agree_with_independent_fraction_arithmetic``), and
it is regenerated only in a reviewed change (``cd tests/unit && python calc_golden.py > ../fixtures/metrics_golden.json``).
"""

import json
import os
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import calc_golden as cg
from credit_intel.calculations.calculate import calculate_metrics

UNIT_DIR = Path(__file__).resolve().parent
GOLDEN = UNIT_DIR.parent / "fixtures" / "metrics_golden.json"


def test_the_metrics_match_the_reviewed_golden_file_exactly():
    assert cg.snapshot_json() == GOLDEN.read_text(encoding="utf-8")


def test_the_golden_file_is_ascii_json():
    GOLDEN.read_bytes().decode("ascii")
    json.loads(GOLDEN.read_text(encoding="ascii"))


def test_a_fresh_process_with_a_different_hash_seed_gives_the_same_bytes():
    env = {**os.environ, "PYTHONHASHSEED": "12345"}

    done = subprocess.run([sys.executable, str(UNIT_DIR / "calc_golden.py")], cwd=UNIT_DIR, env=env, capture_output=True, check=True)

    assert done.stdout == GOLDEN.read_bytes()


def test_the_golden_numbers_agree_with_independent_fraction_arithmetic():
    frac = lambda text: Fraction(text)  # noqa: E731
    cur = {k.value: frac(v) for k, v in cg.CURRENT.items()}
    com = {k.value: frac(v) for k, v in cg.COMPARATIVE.items()}
    golden = json.loads(GOLDEN.read_text(encoding="ascii"))["results"]

    def number(key):
        return Fraction(golden[key]["value"])

    ebit_cur = cur["profit_before_tax"] + cur["interest_expense"]
    expected = {
        "MET-01/-": (cur["revenue"] - com["revenue"]) / com["revenue"] * 100,
        "MET-02/current": cur["net_profit"] / cur["revenue"] * 100,
        "MET-02/comparative": com["net_profit"] / com["revenue"] * 100,
        "MET-03/current": cur["current_assets"] / cur["current_liabilities"],
        "MET-03/comparative": com["current_assets"] / com["current_liabilities"],
        "MET-04/current": (cur["borrowings_non_current"] + cur["borrowings_current"]) / cur["total_equity"],
        "MET-04/comparative": (com["borrowings_non_current"] + com["borrowings_current"]) / com["total_equity"],
        "MET-05/current": ebit_cur / cur["interest_expense"],
    }
    tolerance = Fraction(1, 10**20)
    for key, value in expected.items():
        assert abs(number(key) - value) < tolerance, key
    assert golden["MET-05/comparative"]["value"] is None and golden["MET-05/comparative"]["undefined_reason"] == "not_applicable_no_interest"

    comparisons = json.loads(GOLDEN.read_text(encoding="ascii"))["comparisons"]
    for metric in ("MET-02", "MET-03", "MET-04"):
        change = (expected[f"{metric}/current"] - expected[f"{metric}/comparative"]) / expected[f"{metric}/comparative"] * 100
        assert abs(Fraction(comparisons[metric]["relative_change"]) - change) < tolerance, metric


def test_the_golden_run_exercises_a_derived_ebit_a_derived_total_a_caveat_and_an_undefined_result():
    golden = json.loads(GOLDEN.read_text(encoding="ascii"))

    assert [d["method"] for d in golden["derived"]] == ["EBIT-PBT", "EBIT-PBT"]
    assert golden["results"]["MET-04/current"]["caveats"] == ["borrowings_not_presented_assumption"]
    assert golden["comparisons"]["MET-04"]["caveats"] == ["borrowings_not_presented_assumption"]
    assert golden["comparisons"]["MET-05"]["undefined_reason"] == "not_applicable_no_interest"


def test_every_value_in_the_golden_run_is_a_decimal():
    metrics = calculate_metrics(cg.golden_field_set())

    for result in metrics.results.values():
        assert result.value is None or isinstance(result.value, Decimal)
    for comparison in metrics.comparisons.values():
        assert comparison.relative_change is None or isinstance(comparison.relative_change, Decimal)
