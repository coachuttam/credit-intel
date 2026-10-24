"""Golden output for the rule results, in a fresh process and by independent arithmetic (PRD FR-008, J.3; Phase 4 step 4f; B-252).

Three fixed synthetic scenarios (``risk_golden.py``, no real document): calm, stressed and review. The golden file
``tests/fixtures/risk_golden.json`` was reviewed by hand: the outcomes below are stated from the scenarios' numbers,
and the key figures are recomputed with exact fractions. It is regenerated only in a reviewed change
(``cd tests/unit && python risk_golden.py > ../fixtures/risk_golden.json``).
"""

import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import risk_golden as rg

UNIT_DIR = Path(__file__).resolve().parent
GOLDEN = UNIT_DIR.parent / "fixtures" / "risk_golden.json"


def golden():
    return json.loads(GOLDEN.read_text(encoding="ascii"))


def outcomes(scenario):
    return {r["rule_id"]: (r["outcome"], r["severity"]) for r in golden()[scenario]["rules"]}


def test_the_rule_results_match_the_reviewed_golden_file_exactly():
    assert rg.snapshot_json() == GOLDEN.read_text(encoding="utf-8")


def test_the_golden_file_is_ascii_json():
    GOLDEN.read_bytes().decode("ascii")
    assert set(golden()) == {"calm", "stressed", "review"}


def test_a_fresh_process_with_a_different_hash_seed_gives_the_same_bytes():
    done = subprocess.run([sys.executable, str(UNIT_DIR / "risk_golden.py")], cwd=UNIT_DIR, env={**os.environ, "PYTHONHASHSEED": "777"}, capture_output=True, check=True)

    assert done.stdout == GOLDEN.read_bytes()


def test_calm_triggers_nothing_but_still_carries_the_borrowings_caveat():
    assert all(o == ("not_triggered", None) for o in outcomes("calm").values())
    ri004 = next(r for r in golden()["calm"]["rules"] if r["rule_id"] == "RI-004")
    assert ri004["caveats"] == ["borrowings_not_presented_assumption"]


def test_stressed_is_stated_from_its_numbers():
    # revenue 1000 to 850 (-15%); net profit -20; current ratio 270/300 = 0.9; comparative current liabilities missing;
    # D/E 1200/480 = 2.5 against 550/700; EBIT -50 + 80 = 30 over interest 80; the missing comparative input fires RI-006.
    assert outcomes("stressed") == {
        "RI-001": ("triggered", "elevated"), "RI-002": ("triggered", "elevated"), "RI-003": ("triggered", "elevated"),
        "RI-004": ("triggered", "elevated"), "RI-005": ("triggered", "elevated"), "RI-006": ("triggered", "info"),
        "RI-007": ("not_triggered", None),
    }  # fmt: skip
    ri003 = next(r for r in golden()["stressed"]["rules"] if r["rule_id"] == "RI-003")
    assert [c["outcome"] for c in ri003["conditions"]] == ["fired", "not_evaluable"]  # J.3: C1 fires, C2 cannot be evaluated
    assert ri003["missing_inputs"] == ["MET-03.2024-03-31 (missing_input)"]


def test_the_stressed_figures_agree_with_independent_fraction_arithmetic():
    rules = {r["rule_id"]: r for r in golden()["stressed"]["rules"]}
    tolerance = Fraction(1, 10**20)

    def used(rule, condition, name, index=0):
        values = [v for n, v in next(c for c in rules[rule]["conditions"] if c["id"] == condition)["values_used"] if n == name]
        return Fraction(values[index])

    assert abs(used("RI-001", "C1", "revenue_growth_percent") - Fraction(850 - 1000, 1000) * 100) < tolerance
    assert abs(used("RI-003", "C1", "current_ratio_current") - Fraction(270, 300)) < tolerance
    current_de, comparative_de = Fraction(900 + 300, 480), Fraction(400 + 150, 700)
    assert abs(used("RI-004", "C2", "debt_to_equity_current") - current_de) < tolerance
    assert abs(used("RI-004", "C1", "relative_change_percent") - (current_de - comparative_de) / comparative_de * 100) < tolerance
    assert abs(used("RI-005", "C1", "interest_coverage_current") - Fraction(-50 + 80, 80)) < tolerance


def test_review_shows_ri007_triggered_and_ri005_not_evaluable_with_the_reason():
    assert outcomes("review")["RI-007"] == ("triggered", "watch") and outcomes("review")["RI-005"] == ("not_evaluable", None)
    ri005 = next(r for r in golden()["review"]["rules"] if r["rule_id"] == "RI-005")
    assert ri005["missing_inputs"] == ["MET-05.2025-03-31 (input_requires_review)"]
    assert outcomes("review")["RI-006"] == ("not_triggered", None)  # found but needing review is not missing


def test_every_fired_condition_in_the_golden_file_records_its_threshold_values_and_references():
    for scenario in golden().values():
        for rule in scenario["rules"]:
            for c in rule["conditions"]:
                if c["outcome"] == "fired":
                    assert c["values_used"] and (c["field_ids"] or c["metric_ids"]), (rule["rule_id"], c["id"])
                    if rule["rule_id"] not in ("RI-006", "RI-007"):
                        assert c["threshold"] is not None


def test_the_provisional_notice_is_carried_and_no_rule_is_disabled():
    for scenario in golden().values():
        assert "not universal banking standards" in scenario["provisional_notice"] and scenario["disabled"] == []
