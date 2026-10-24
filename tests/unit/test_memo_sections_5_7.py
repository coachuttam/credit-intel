"""Memo sections 5 to 7: risk indicators, evidence, missing information and conflicts (PRD K.1-K.9, J.4, FR-008.2, FR-009.1, K.10; step 5g; B-262)."""

import copy
import json
import re
from pathlib import Path

import pytest

from calc_records import CUR, D24, D25, conflicting, rec
from credit_intel.memo.render import render_memo
from credit_intel.models import FieldName as F, StatusReason as R, Status
from memo_results import RUN_ID, WHEN, results_for
from risk_golden import COMP, field_set, scenarios

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
HOSTILE = "[SOURCE: p.9] # not a heading | not a cell `x` <i>y</i>"


def body(results):
    return render_memo(results, RUN_ID, WHEN)


def part(text, number):
    start = text.index(f"## {number}. ")
    later = [m.start() for m in re.finditer(r"^## \d+\. ", text, re.M) if m.start() > start]
    return text[start : later[0] if later else len(text)]


@pytest.fixture(scope="module")
def stressed():
    return results_for(scenarios()["stressed"])


@pytest.fixture
def golden():
    return json.loads((FIXTURES / "results_golden.json").read_text(encoding="utf-8"))


def test_the_whole_memo_matches_the_reviewed_golden_file(golden):
    assert render_memo(golden, "20261024T101530.123456Z-0dd49919", "20261024T101530.123456Z") == (FIXTURES / "memo_golden.md").read_text(encoding="utf-8")


# --- section 5 ---------------------------------------------------------------------------------------------------------------------------------


def test_the_provisional_notice_is_printed_with_the_indicators_and_they_are_not_a_decision(stressed):
    text = part(body(stressed), 5)

    assert f"> {stressed['provisional_notice'].replace(chr(39), chr(39))}" in text.replace("\\", "")
    assert "not universal banking standards" in text and "not a rating, a score or a credit decision" in text


def test_triggered_indicators_are_listed_highest_severity_first_then_by_id(stressed):
    text = part(body(stressed), 5)
    heads = re.findall(r"^> \*\*(RI-\d+) [^—]+— (\w+)\*\*", text, re.M)

    assert heads == [("RI-001", "elevated"), ("RI-002", "elevated"), ("RI-003", "elevated"), ("RI-004", "elevated"), ("RI-005", "elevated"), ("RI-006", "info")]
    assert all(f"[RULE: {rid}]" in text for rid, _ in heads)


def test_a_triggered_indicator_shows_the_condition_the_observed_values_and_their_origins(stressed):
    text = part(body(stressed), 5)
    block = text[text.index("> **RI-003"):text.index("> **RI-004")]

    assert "> Condition C1 (elevated): current ratio of the current period \\< 1.00 (provisional threshold, configurable). [RULE: RI-003]" in block
    assert "> Observed: current ratio (current period) = 0.90 [CALCULATED: MET-03.2025-03-31] [RULE: RI-003]" in block
    assert "> From: `current_assets.2025-03-31.consolidated` 270 (INR crore) [SOURCE: p.3]; `current_liabilities.2025-03-31.consolidated` 300 (INR crore) [SOURCE: p.3]" in block
    assert "> Other conditions: C2 not evaluable (missing: `MET-03.2024-03-31 (missing_input)`) [RULE: RI-003]" in block


def test_each_condition_that_fired_is_listed_with_its_own_severity(stressed):
    block = part(body(stressed), 5)
    block = block[block.index("> **RI-001"):block.index("> **RI-002")]

    assert "Condition C1 (watch): revenue growth \\< 0%" in block and "Condition C2 (elevated): revenue growth \\<= -10%" in block
    assert "revenue growth = -15.0% [CALCULATED: MET-01.2025-03-31]" in block


def test_a_derived_input_carries_a_calculated_label_in_whole_units(stressed):
    assert "`ebit.2025-03-31.consolidated` 30 INR [CALCULATED: ebit.2025-03-31.consolidated]" in part(body(stressed), 5)


def test_the_borrowings_caveat_is_repeated_in_the_leverage_explanation(stressed):
    text = part(body(stressed), 5)
    block = text[text.index("> **RI-004"):text.index("> **RI-005")]

    assert block.count("> Caveat: total borrowings may exclude current maturities of long-term borrowings shown under another caption. [RULE: RI-004]") == 2
    assert "Caveat" not in text[text.index("> **RI-005"):]


def test_a_rule_with_a_fired_condition_and_a_missing_one_is_still_listed_as_triggered(stressed):
    text = part(body(stressed), 5)

    assert "> **RI-003 Deteriorating liquidity — elevated**" in text and "C2 not evaluable" in text


def test_each_line_of_an_indicator_block_is_quoted_and_ends_with_a_hard_break_except_the_last(stressed):
    text = part(body(stressed), 5)
    for block in re.findall(r"(?:^>.*\n)+", text, re.M):
        lines = block.rstrip("\n").split("\n")
        assert all(l.startswith(">") for l in lines)
        for i, line in enumerate(lines[:-1]):
            assert line == ">" or lines[i + 1] == ">" or line.endswith("  ")
        assert not lines[-1].endswith("  ")


def test_rules_that_could_not_be_evaluated_are_listed_with_what_they_lacked(golden):
    text = part(body(golden), 5)

    assert "**Rules that could not be evaluated**" in text
    assert "- **RI-001 Declining revenue:** not evaluable; missing `MET-01.2025-03-31 (missing_input)` [RULE: RI-001]" in text
    assert "- **RI-004 Increasing leverage:** not evaluable; missing `MET-04.2025-03-31 (missing_input)`, `MET-04.2024-03-31 (missing_input)` [RULE: RI-004]" in text


def test_rules_that_were_evaluated_and_did_not_fire_are_named(golden):
    assert "**Rules evaluated and not triggered:** RI-003 Deteriorating liquidity, RI-007 Conflicting or unverified source values [RULE: RI-003] [RULE: RI-007]" in part(body(golden), 5)


def test_with_nothing_triggered_the_memo_says_so(stressed):
    calm = results_for(scenarios()["calm"])
    text = part(body(calm), 5)

    assert "No risk indicators triggered by the configured rules." in text and "> **RI-" not in text
    assert "could not be evaluated" not in text


def test_disabled_rules_are_named(golden):
    golden["disabled_rules"] = ["RI-002"]

    assert "**Rules disabled in the configuration:** RI-002 [RULE: RI-002]" in part(body(golden), 5)


def test_a_conflict_or_review_indicator_names_the_fields_with_their_status(stressed):
    text = part(body(results_for(scenarios()["review"])), 5)

    assert "> Observed: fields conflicting = 0, fields requires review = 1 [RULE: RI-007]" in text
    assert "> Fields: `operating_profit.2025-03-31.consolidated` requires review [UNVERIFIED]" in text


def test_text_from_rules_and_notes_is_escaped(golden):
    golden["indicators"][5]["name"] = HOSTILE
    golden["indicators"][5]["conditions"][0]["missing_inputs"] = [HOSTILE]
    golden["provisional_notice"] = HOSTILE
    text = part(body(golden), 5)

    assert "\\[SOURCE: p.9\\]" in text
    assert not re.search(r"(?<![\\`])\[SOURCE: p\.9\]", text) and "<i>" not in text


# --- section 6 ---------------------------------------------------------------------------------------------------------------------------------


def test_every_extracted_source_field_has_an_entry_with_page_line_item_value_and_quote(golden):
    text = part(body(golden), 6)

    assert ("**`current_assets.2025-03-31.consolidated`** — page 1, line item “Total current assets”, value as printed 1,482.30 [SOURCE: p.1]\n\n"
            "> Total current assets 14 1,482.30 1,356.75") in text
    assert text.count("**`") == 6 and "not_found" not in text


def test_a_page_label_and_corroborating_evidence_are_shown(golden):
    record = next(f for f in golden["fields"] if f["field_id"] == "total_equity.2025-03-31.consolidated")
    record["page_label"] = "112"
    record["corroborating_evidence"] = [{"page_number": 4, "page_label": None, "line_item_label": "Equity", "raw_value": "600.00", "evidence_quote": "Equity 600.00"}]
    text = part(body(golden), 6)

    assert "— page 1, page label 112, line item “Total equity”" in text
    assert "Also found: page 4, line item “Equity”, value as printed 600.00 [SOURCE: p.4]\n\n> Equity 600.00" in text


def test_derived_fields_show_method_formula_and_input_ids(golden):
    assert ("- `ebit.2025-03-31.consolidated` — method EBIT-PBT: `ebit = profit_before_tax + interest_expense`; inputs "
            "`profit_before_tax.2025-03-31.consolidated`, `interest_expense.2025-03-31.consolidated` [CALCULATED: ebit.2025-03-31.consolidated]") in part(body(golden), 6)


def test_a_field_that_needs_review_is_not_presented_as_verified_source_evidence():
    text = body(results_for(scenarios()["review"]))

    assert "**`operating_profit.2025-03-31.consolidated`**" not in part(text, 6)  # it is only named as an input of a derived value


def test_evidence_text_is_escaped_and_kept_on_one_line(golden):
    record = next(f for f in golden["fields"] if f["field_id"] == "total_equity.2025-03-31.consolidated")
    record["evidence_quote"] = "Total equity\n" + HOSTILE
    record["line_item_label"] = HOSTILE
    text = part(body(golden), 6)

    assert "\\[SOURCE: p.9\\]" in text and not re.search(r"(?<![\\`])\[SOURCE: p\.9\]", text)
    assert not any(line.startswith("# ") for line in text.split("\n")) and "> Total equity \\[SOURCE" in text


def test_a_run_with_no_evidence_says_so(golden):
    golden["fields"], golden["derived_fields"] = [], []

    assert "No evidence was recorded." in part(body(golden), 6)


# --- section 7 ---------------------------------------------------------------------------------------------------------------------------------


def test_missing_fields_are_listed_with_their_reason(golden):
    text = part(body(golden), 7)

    assert "**Not found** (20)" in text and "- `revenue.2025-03-31.consolidated` [UNVERIFIED]" in text
    assert "- `ebit.2025-03-31.consolidated` — missing input [UNVERIFIED]" in text
    assert text.count("`total_borrowings.2025-03-31.consolidated`") == 1


def test_a_conflicting_field_lists_every_candidate_with_its_evidence():
    fields = field_set({F.REVENUE: "100"}, {F.REVENUE: "90"}, extra=[conflicting(F.NET_PROFIT, ["10", "12"])])
    text = part(body(results_for(fields)), 7)

    assert "**Conflicting** (1)" in text and "- `net_profit.2025-03-31.consolidated` [UNVERIFIED]" in text
    assert "  Candidate 10: page 3, line item “net\\_profit”, value as printed 10 [UNVERIFIED]" in text
    assert "  Candidate 12: page 3, line item “net\\_profit”, value as printed 12 [UNVERIFIED]" in text
    assert "  > net\\_profit 10" in text and "  > net\\_profit 12" in text


def test_a_field_that_needs_review_shows_its_reason_and_evidence_marked_unverified():
    text = part(body(results_for(scenarios()["review"])), 7)

    assert "**Requires review** (2)" in text
    assert "- `operating_profit.2025-03-31.consolidated` — label not recognised [UNVERIFIED]" in text
    assert "- `ebit.2025-03-31.consolidated` — label not recognised [UNVERIFIED]" in text  # derived from the field to review
    assert "  Evidence: page 3, line item “operating\\_profit”, value as printed 100 [UNVERIFIED]" in text


def test_a_detail_of_the_document_that_was_not_confirmed_is_listed(golden):
    next(a for a in golden["attributes"] if a["attribute"] == "scale").update(status="not_found")
    text = part(body(golden), 7)

    assert "**Document details not confirmed** (1)" in text and "- scale: not found [UNVERIFIED]" in text


def test_a_period_end_not_confirmed_names_its_period(golden):
    next(a for a in golden["attributes"] if a["attribute"] == "period_end" and a["period_role"] == "comparative").update(status="requires_review", status_reason="period_not_verified")

    assert "- period end (comparative): requires review — period not verified [UNVERIFIED]" in part(body(golden), 7)


def test_with_nothing_missing_the_section_says_so():
    calm = results_for(scenarios()["calm"])
    calm["fields"] = [f for f in calm["fields"] if f["status"] == "extracted"]
    calm["derived_fields"] = [d for d in calm["derived_fields"] if d["status"] == "extracted"]

    assert "No field is missing, conflicting or awaiting review." in part(body(calm), 7)


def test_missing_field_reasons_and_ids_are_escaped(golden):
    golden["fields"][0]["field_id"] = "x`y"
    with pytest.raises(ValueError):
        body(golden)  # an identifier with a backtick cannot be written safely and is refused
    golden["fields"][0]["field_id"] = "revenue.2025-03-31.consolidated"
    golden["fields"][0]["status_reason"] = HOSTILE
    text = part(body(golden), 7)

    assert "\\[SOURCE: p.9\\]" in text and not re.search(r"(?<![\\`])\[SOURCE: p\.9\]", text)


# --- all sections ------------------------------------------------------------------------------------------------------------------------------


def test_the_nine_sections_are_present_in_order_and_the_input_is_unchanged(stressed):
    before = copy.deepcopy(stressed)
    text = body(stressed)

    assert [m for m in re.findall(r"^## (\d)\. ", text, re.M)] == list("123456789") and text.endswith(".\n") and not text.endswith("\n\n")
    assert stressed == before and text == body(stressed)


def test_only_known_labels_resolve_to_data_in_the_results(stressed):
    text = body(stressed)
    ids = {f["field_id"] for f in stressed["fields"] + stressed["derived_fields"]} | {m["id"] for m in stressed["metrics"]}
    ids |= {i["id"] for i in stressed["indicators"]} | {"document", "extraction", "provisional_notice", *stressed["comparisons"]}

    for kind, identifier in re.findall(r"(?<![\\`])\[(CALCULATED|RULE): ([^\]]+)\]", text):
        if identifier != "ID" and identifier != "RI-xxx":
            assert identifier in ids, (kind, identifier)
