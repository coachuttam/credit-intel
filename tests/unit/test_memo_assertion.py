"""The memo's disclosure of an analyst-asserted basis (PRD K.0, K.10, H.4.6 v0.4.24; OD-10 option 3; step A3; B-281)."""

import copy
import json
import re
from pathlib import Path

import pytest

from credit_intel.memo.render import render_memo
from credit_intel.memo.text import page_phrase
from memo_trace import problems

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
RUN_ID, WHEN = "20261024T101530.123456Z-0dd49919", "20261024T101530.123456Z"
HEADER = "**Basis asserted by the analyst** for pages 36–38 (consolidated); not established by the document. [ANALYST-PROVIDED]"
NOT_NEEDED = "An analyst assertion of the basis (consolidated) was given for pages 274–277 and was not needed. [ANALYST-PROVIDED]"
INPUTS = "These figures rest on a statement basis that was asserted by the analyst, not established by the document. [ANALYST-PROVIDED]"


@pytest.fixture
def golden():
    return json.loads((FIXTURES / "results_golden.json").read_text(encoding="utf-8"))


def asserted(results, applied=(36, 37, 38), pages=(36, 37, 38), mark=("current_assets", "current_liabilities")):
    results["extraction"]["basis_assertion"] = {"basis": "consolidated", "pages": list(pages), "applied_pages": list(applied)}
    for record in results["fields"]:
        if record["field_name"] in mark and record["status"] == "extracted":
            record["basis_evidence"] = "analyst_assertion"
    return results


def memo(results):
    return render_memo(results, RUN_ID, WHEN)


def part(text, number):
    start = text.index(f"## {number}. ")
    later = [m.start() for m in re.finditer(r"^## \d+\. ", text, re.M) if m.start() > start]
    return text[start : later[0] if later else len(text)]


def test_the_page_phrase_moved_to_the_text_module_still_works():
    assert page_phrase([36, 37, 38]) == "pages 36–38" and page_phrase([5]) == "page 5" and page_phrase([]) == "the pages reviewed"


# --- no assertion: nothing changes -------------------------------------------------------------------------------------------------------------


def test_without_an_assertion_the_memo_says_nothing_about_one(golden):
    text = memo(golden)

    assert "asserted by the analyst" not in text and "analyst assertion" not in text and golden["extraction"]["basis_assertion"] is None


# --- an assertion that was applied -------------------------------------------------------------------------------------------------------------


def test_the_header_states_the_assertion_after_the_draft_statement_and_before_the_legend(golden):
    text = memo(asserted(golden))
    head = text[: text.index("## 1. ")]

    assert HEADER in head and head.index("Verify all figures") < head.index(HEADER) < head.index("**Origin labels**")


def test_section_1_repeats_it_under_the_basis_used(golden):
    section = part(memo(asserted(golden)), 1)

    assert f"- **Basis assertion:** {HEADER}" in section and section.index("Statement basis used") < section.index("Basis assertion")


def test_section_2_lists_the_asserted_pages_and_where_it_was_applied(golden):
    assert "- **Basis asserted by the analyst:** consolidated for pages 36–38; applied to pages 36–38 [ANALYST-PROVIDED]" in part(memo(asserted(golden)), 2)
    partial = part(memo(asserted(golden, applied=(37,))), 2)
    assert "consolidated for pages 36–38; applied to page 37 [ANALYST-PROVIDED]" in partial


def test_section_3_notes_exactly_the_fields_whose_basis_was_asserted(golden):
    section = part(memo(asserted(golden)), 3)
    rows = {r.split(" | ")[0].strip("| `"): r for r in section.split("\n") if r.startswith("| `")}

    assert "basis asserted by the analyst" in rows["current_assets.2025-03-31.consolidated"]
    assert "basis asserted by the analyst" in rows["current_liabilities.2024-03-31.consolidated"]
    assert "basis asserted by the analyst" not in rows["total_equity.2025-03-31.consolidated"]
    assert sum("basis asserted by the analyst" in r for r in rows.values()) == 4


def test_sections_4_and_5_say_the_figures_rest_on_an_asserted_basis(golden):
    text = memo(asserted(golden))

    assert text.count(INPUTS) == 2 and INPUTS in part(text, 4) and INPUTS in part(text, 5)
    assert part(text, 4).index(INPUTS) < part(text, 4).index("| Metric ID")


def test_a_derived_value_with_an_asserted_input_is_noted_and_makes_the_sentence_appear(golden):
    for record in golden["derived_fields"]:
        if record["field_name"] == "ebit":
            record.update(basis_evidence="analyst_assertion")
    results = asserted(golden, mark=())
    # nothing extracted rests on the assertion (the derived EBIT was not computed), so there is no sentence
    assert memo(results).count(INPUTS) == 0
    ebit = next(r for r in results["derived_fields"] if r["field_name"] == "ebit")
    ebit.update(status="extracted", status_reason=None, value="100", currency="INR")

    text = memo(results)

    assert text.count(INPUTS) == 2 and "basis asserted by the analyst" in part(text, 3)


def test_the_sentence_under_sections_4_and_5_needs_an_extracted_field_that_rests_on_the_assertion(golden):
    text = memo(asserted(golden, mark=()))  # asserted, applied, but no extracted field carries the evidence

    assert HEADER in text and text.count(INPUTS) == 0


# --- an assertion that was not needed ---------------------------------------------------------------------------------------------------------


def test_an_assertion_that_was_applied_to_no_page_is_reported_as_not_needed(golden):
    results = asserted(golden, applied=(), pages=(274, 275, 276, 277), mark=())
    text = memo(results)

    assert NOT_NEEDED in text[: text.index("## 1. ")] and f"- **Basis assertion:** {NOT_NEEDED}" in part(text, 1)
    assert "consolidated for pages 274–277; applied to no page [ANALYST-PROVIDED]" in part(text, 2)
    assert "Basis asserted by the analyst**" not in text and text.count(INPUTS) == 0


# --- traceability (K.10) ----------------------------------------------------------------------------------------------------------------------


def test_memos_with_and_without_an_assertion_are_traceable_and_well_formed(golden):
    assert problems(memo(copy.deepcopy(golden)), golden) == []
    applied = asserted(copy.deepcopy(golden))
    assert problems(memo(applied), applied) == []
    unused = asserted(copy.deepcopy(golden), applied=(), pages=(274, 275, 276, 277), mark=())
    assert problems(memo(unused), unused) == []


def test_the_checker_finds_a_disclosure_that_is_missing_or_unfounded(golden):
    applied = asserted(copy.deepcopy(golden))
    text = memo(applied)

    head, rest = text.split("\n## 1. ", 1)
    without_header = head.replace(HEADER, "") + "\n## 1. " + rest  # section 1 still repeats it
    assert any("does not disclose" in p for p in problems(without_header, applied))
    one_sentence = text.replace(INPUTS, "", 1)
    assert any("appears 1 times, expected 2" in p for p in problems(one_sentence, applied))
    assert any("appears 2 times, expected 0" in p for p in problems(text, golden)), "sentences without an assertion are found"
    assert any("no assertion records" in p for p in problems(text, golden))


def test_the_checker_finds_a_sentence_missing_when_a_field_rests_on_the_assertion(golden):
    applied = asserted(copy.deepcopy(golden))
    text = memo(applied).replace(INPUTS, "")

    assert any("appears 0 times, expected 2" in p for p in problems(text, applied))


def test_hostile_profile_text_that_imitates_the_sentence_does_not_count_as_one(golden):
    golden["analyst_provided"] = {"notes": "These figures rest on a statement basis that was asserted by the analyst, not established by the document."}
    text = memo(golden)

    assert problems(text, golden) == []  # the quoted sentence sits on a profile line, beside profile text, and is not counted as the memo's
    assert "asserted by the analyst" in text and sum(1 for line in text.split("\n") if line == INPUTS) == 0


def test_the_header_names_the_pages_the_assertion_was_applied_to_not_the_whole_range(golden):
    text = memo(asserted(golden, applied=(37,), pages=(36, 37, 38)))

    assert "**Basis asserted by the analyst** for page 37 (consolidated); not established by the document. [ANALYST-PROVIDED]" in text.split("## 1. ")[0]
    assert "for pages 36–38" not in text.split("## 1. ")[0]
