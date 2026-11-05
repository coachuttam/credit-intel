"""Traceability of the memo (PRD K.10, FR-009.2, FR-010.2; Phase 5 step 5i; B-265).

Every label resolves to something in the results, every ID written exists, every value shown is the value held, and
the Markdown is well formed. The checker is ``memo_trace.problems``; each check is also shown to fail on a damaged memo.
"""

import json
import re
from pathlib import Path

import pytest

from calc_records import conflicting
from credit_intel.memo.render import render_memo
from credit_intel.models import FieldName as F, Status
from memo_results import RUN_ID, WHEN, results_for
from memo_trace import problems
from risk_golden import field_set, scenarios

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
HOSTILE = "[SOURCE: p.1] # head | cell `x` <i>y</i> [link](http://x) [CALCULATED: MET-01.2025-03-31]"


def memo(results):
    return render_memo(results, RUN_ID, WHEN)


@pytest.fixture
def golden():
    return json.loads((FIXTURES / "results_golden.json").read_text(encoding="utf-8"))


def scenario_results():
    cases = {name: results_for(fs) for name, fs in scenarios().items()}
    cases["conflict"] = results_for(field_set({F.REVENUE: "100"}, {F.REVENUE: "90"}, extra=[conflicting(F.NET_PROFIT, ["10", "12"])]))
    return cases


@pytest.mark.parametrize("name", ["calm", "stressed", "review", "conflict"])
def test_a_memo_of_each_scenario_is_traceable_and_well_formed(name):
    results = scenario_results()[name]

    assert problems(memo(results), results) == []


def test_the_memo_of_the_golden_run_is_traceable_and_well_formed(golden):
    assert problems(memo(golden), golden) == []


def test_hostile_profile_text_does_not_break_traceability_or_structure(golden):
    golden["analyst_provided"] = {"borrower_name": HOSTILE, "industry": HOSTILE, "facility_requested": HOSTILE, "notes": HOSTILE}

    assert problems(memo(golden), golden) == []


def test_hostile_text_in_the_results_does_not_break_traceability_or_structure():
    results = scenario_results()["review"]
    results["indicators"][6]["name"] = HOSTILE
    results["fields"][0]["line_item_label"] = HOSTILE
    results["fields"][0]["evidence_quote"] = HOSTILE
    results["attributes"][0]["normalised_value"] = HOSTILE

    assert problems(memo(results), results) == []


def test_a_reported_nil_and_a_derived_total_are_traceable():
    results = scenario_results()["calm"]
    record = next(f for f in results["fields"] if f["field_id"] == "total_equity.2025-03-31.consolidated")
    record.update(value_interpretation="reported_nil", raw_value="-", value="0")

    assert problems(memo(results), results) == []


def test_the_memo_never_contains_an_unresolved_label_in_any_scenario():
    for results in scenario_results().values():
        text = memo(results)
        for kind, identifier in re.findall(r"(?<![\\`])\[(CALCULATED|RULE): ([^\]]+)\]", text):
            assert identifier != "ID"


# --- each check can fail ---------------------------------------------------------------------------------------------------------------------------


def damaged(results, old, new, count=1):
    text = memo(results)
    assert old in text, old
    return text.replace(old, new, count)


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("[SOURCE: p.1]", "[SOURCE: p.77]", "not a page"),
        ("[CALCULATED: MET-03.2025-03-31]", "[CALCULATED: MET-03.2099-03-31]", "names nothing"),
        ("[RULE: RI-003]", "[RULE: RI-099]", "names no indicator"),
        ("| not found | [UNVERIFIED] | statement not in pages sent |", "| not found | [VERIFIED] | statement not in pages sent |", "unknown label"),
        ("| not found | [UNVERIFIED] | statement not in pages sent |", "| not found | [SOURCE: p.1] | statement not in pages sent |", "label does not agree"),
        ("| extracted | [SOURCE: p.1] | — |", "| extracted | [UNVERIFIED] | — |", "label does not agree"),
        ("`current_assets.2025-03-31.consolidated`", "`current_assets.2031-03-31.consolidated`", "unknown field ID"),
        ("`MET-03.2025-03-31`", "`MET-09.2025-03-31`", "unknown metric ID"),
        ("1,482.30 (INR crore)", "1,482.31 (INR crore)", "not the value as printed"),
        ("| 1.65 |", "| 1.64 |", "metric value shown"),
        ("| extracted |", "| not found |", "status shown"),
        ("## 4. Financial ratios", "#### Financial ratios", "headings"),
        ("(INR crore)", "(INR crore) <b>", "raw HTML"),
        ("`MET-03.2025-03-31` |", "`MET-03.2025-03-31 |", "unclosed code span"),
        ("| Label | Meaning |", "| Label | Meaning | Extra |", "table row has"),
    ],
)
def test_the_checker_finds_each_kind_of_damage(golden, old, new, expected):
    assert any(expected in p for p in problems(damaged(golden, old, new), golden)), problems(damaged(golden, old, new), golden)


def test_a_bracket_that_is_neither_escaped_nor_a_label_is_found(golden):
    stray = damaged(golden, "No borrower profile was supplied.", "No borrower profile was supplied [see note.")
    unknown = damaged(golden, "No borrower profile was supplied.", "No borrower profile was supplied [see note].")

    assert any("a bracket that is not a label" in p for p in problems(stray, golden))
    assert any("unknown label [see note]" in p for p in problems(unknown, golden))


def test_a_profile_label_beside_text_the_profile_does_not_hold_is_found(golden):
    golden["analyst_provided"] = {"industry": "Steel"}
    text = damaged(golden, "- **Industry:** Steel [ANALYST-PROVIDED]", "- **Industry:** Gold [ANALYST-PROVIDED]")

    assert any("beside text the profile does not hold" in p for p in problems(text, golden))


def test_a_missing_final_newline_or_a_missing_section_is_found(golden):
    text = memo(golden)

    assert any("exactly one newline" in p for p in problems(text + "\n", golden))
    assert any("headings" in p for p in problems(text.replace("## 9. ", "### 9. "), golden))


def test_a_value_shown_for_a_field_that_is_not_extracted_is_found(golden):
    row = next(l for l in memo(golden).split("\n") if l.startswith("| `revenue.2025-03-31.consolidated`"))
    text = memo(golden).replace(row, row.replace("| — |", "| 500 |", 1))

    assert any("not extracted" in p for p in problems(text, golden))


def test_a_value_shown_for_a_derived_total_must_be_the_one_held():
    results = scenario_results()["stressed"]
    text = memo(results)
    row = next(l for l in text.split("\n") if l.startswith("| `total_borrowings.2025-03-31.consolidated`"))

    assert problems(text, results) == []
    assert any("derived value shown" in p for p in problems(text.replace(row, row.replace("1,200", "1,201")), results))
