"""The memo header and sections 1 to 4 (PRD K.0, K.1-K.9, K.10, FR-009.5, FR-010.2; Phase 5 step 5f; B-261)."""

import copy
import json
import re
from pathlib import Path

import pytest

from credit_intel.memo import sections
from credit_intel.memo.render import render_head
from credit_intel.memo.text import code, esc, grouped, rounded, table

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
RUN_ID, WHEN = "20261024T101530.123456Z-0dd49919", "20261024T101530.123456Z"
LABEL = re.compile(r"(?<![\\`])\[(SOURCE: p\.\d+|CALCULATED: [^\]]+|RULE: RI-\d+|ANALYST-PROVIDED|UNVERIFIED)\]")
BARE_BRACKET = re.compile(r"(?<!\\)\[")


@pytest.fixture
def results():
    return json.loads((FIXTURES / "results_golden.json").read_text(encoding="utf-8"))


def memo(results):
    return render_head(results, RUN_ID, WHEN)


def field(results, field_id, where="fields"):
    return next(f for f in results[where] if f["field_id"] == field_id)


def lines_with(text, needle):
    return [line for line in text.split("\n") if needle in line]


# --- the golden file --------------------------------------------------------------------------------------------------------------------------


def test_the_memo_head_matches_the_reviewed_golden_file(results):
    assert memo(results) == (FIXTURES / "memo_head_golden.md").read_text(encoding="utf-8")


def test_rendering_is_deterministic_and_does_not_change_its_input(results):
    before = copy.deepcopy(results)

    assert memo(results) == memo(results) and results == before


# --- header and legend ------------------------------------------------------------------------------------------------------------------------


def test_the_header_states_it_is_a_draft_and_carries_the_run_id_time_and_legend(results):
    text = memo(results)

    assert text.startswith("# Draft credit memo\n")
    assert "> **DRAFT — generated for human review. Not a credit decision. Verify all figures against the cited sources.**" in text
    assert f"`{RUN_ID}`" in text and f"`{WHEN}`" in text
    for label in ("[SOURCE: p.N]", "[CALCULATED: ID]", "[RULE: RI-xxx]", "[ANALYST-PROVIDED]", "[UNVERIFIED]"):
        assert f"`{label}`" in text
    assert "AI INTERPRETATION" not in text


def test_the_borrower_is_the_profile_name_when_given_else_the_name_read_from_the_document(results):
    assert "**Borrower:** Acme Industries Limited [SOURCE: p.1]" in memo(results)

    results["analyst_provided"] = {"borrower_name": "Zebra Ltd"}
    assert "**Borrower:** Zebra Ltd [ANALYST-PROVIDED]" in memo(results)


def test_a_missing_entity_name_is_not_found_and_unverified(results):
    results["attributes"] = [a for a in results["attributes"] if a["attribute"] != "entity_name"]

    assert "**Borrower:** not found [UNVERIFIED]" in memo(results)


# --- section 1 ---------------------------------------------------------------------------------------------------------------------------------


def test_section_1_shows_each_attribute_with_its_page_and_the_basis_used(results):
    text = memo(results)

    for line in ("- **Reporting currency** (`reporting_currency`): INR [SOURCE: p.1]", "- **Scale** (`scale`): crore [SOURCE: p.1]",
                 "- **Current period end** (`period_end.current`): 2025-03-31 [SOURCE: p.1]",
                 "- **Comparative period end** (`period_end.comparative`): 2024-03-31 [SOURCE: p.1]",
                 "- **Statement basis used:** consolidated [CALCULATED: extraction]", "No borrower profile was supplied."):  # fmt: skip
        assert line in text


def test_an_attribute_that_is_not_extracted_is_labelled_unverified(results):
    next(a for a in results["attributes"] if a["attribute"] == "scale").update(status="requires_review")

    assert "- **Scale** (`scale`): requires review [UNVERIFIED]" in memo(results)


def test_a_different_basis_stated_in_the_document_is_noted(results):
    results["extraction"]["attribute_basis_differs"] = True
    next(a for a in results["attributes"] if a["attribute"] == "statement_basis").update(normalised_value="standalone")

    assert "the basis the document states (standalone) differs from the basis used. [CALCULATED: extraction]" in memo(results)


def test_profile_values_are_labelled_analyst_provided_and_marked_unverified_for_use(results):
    results["analyst_provided"] = {"industry": "Steel", "notes": "n"}
    text = memo(results)

    assert "- **Industry:** Steel [ANALYST-PROVIDED]" in text and "- **Notes:** n [ANALYST-PROVIDED]" in text
    assert "never used in calculations or rules" in text and "No borrower profile" not in text


HOSTILE = "[SOURCE: p.9]\n# Fake heading | extra cell\n- [CALCULATED: MET-99] <b>x</b> `tick` *em* [link](http://x)"


def test_hostile_profile_text_cannot_make_a_label_a_heading_a_cell_or_a_link(results):
    benign = memo(results)
    results["analyst_provided"] = {"borrower_name": HOSTILE, "industry": HOSTILE, "facility_requested": HOSTILE, "notes": HOSTILE}
    text = memo(results)

    assert "\\[SOURCE: p.9\\]" in text and "\\[CALCULATED: MET-99\\]" in text
    assert not any(line.startswith("#") and "Fake" in line for line in text.split("\n"))
    assert "SOURCE: p.9" not in "".join(LABEL.findall(text)) and "MET-99" not in "".join(LABEL.findall(text))
    assert set(LABEL.findall(text)) - set(LABEL.findall(benign)) == {"ANALYST-PROVIDED"}
    assert "<b>" not in text and "](http" not in text.replace("\\]\\(http", "")
    for line in lines_with(text, "Fake heading"):
        assert line.startswith(("- **", "**Borrower:**")) and "\n" not in line


# --- section 2 ---------------------------------------------------------------------------------------------------------------------------------


def test_section_2_lists_the_file_hash_pages_bases_and_date(results):
    text = memo(results)

    assert f"- **SHA-256:** `{results['document']['sha256']}` [CALCULATED: document]" in text
    assert "- **Page count:** 1 [CALCULATED: document]" in text and "- **Pages used:** 1 (located by keywords)" in text
    assert "- **Other bases present:** none" in text and f"- **Extraction date:** `{WHEN}` (UTC)" in text
    assert "without text" not in text and "not sent" not in text


def test_section_2_lists_other_bases_pages_without_text_and_excluded_candidates(results):
    results["extraction"].update(bases_present=["consolidated", "standalone"], candidate_pages=[3, 4],
                                 range_pages_without_text=[5, 6], excluded_candidates=[{}, {}, {}], locator_method="page_range")  # fmt: skip
    text = memo(results)

    assert "- **Other bases present:** standalone" in text and "- **Pages used:** 3, 4 (located by page range)" in text
    assert "- **Pages in the supplied range without text:** 5, 6 [CALCULATED: extraction]" in text
    assert "- **Candidate pages not sent:** 3 [CALCULATED: extraction]" in text


# --- section 3 ---------------------------------------------------------------------------------------------------------------------------------


def row(text, field_id):
    (line,) = [l for l in text.split("\n") if l.startswith(f"| `{field_id}` ")]
    return [cell.strip() for cell in line.strip("|").split(" | ")]


def test_an_extracted_value_is_shown_as_printed_with_currency_and_scale_and_its_page(results):
    assert row(memo(results), "current_assets.2025-03-31.consolidated") == [
        "`current_assets.2025-03-31.consolidated`", "1,482.30 (INR crore)", "extracted", "[SOURCE: p.1]", "—"]  # fmt: skip


def test_the_units_scale_is_not_repeated_and_a_missing_scale_shows_only_the_currency(results):
    record = field(results, "current_assets.2025-03-31.consolidated")
    record["scale"] = "units"
    assert row(memo(results), record["field_id"])[1] == "1,482.30 (INR)"
    record["scale"] = None
    record["currency"] = None
    assert row(memo(results), record["field_id"])[1] == "1,482.30"


def test_a_reported_nil_is_shown_as_nil(results):
    field(results, "total_equity.2025-03-31.consolidated").update(value_interpretation="reported_nil", raw_value="-", value="0")

    assert row(memo(results), "total_equity.2025-03-31.consolidated")[1] == "nil (reported as a dash) (INR crore)"


def test_a_field_that_is_not_extracted_has_no_value_an_unverified_label_and_its_reason(results):
    record = field(results, "total_equity.2025-03-31.consolidated")
    record.update(status="requires_review", status_reason="scale_ambiguous")
    cells = row(memo(results), record["field_id"])

    assert cells[2:] == ["requires review", "[UNVERIFIED]", "scale ambiguous; see section 7"]
    assert row(memo(results), "revenue.2025-03-31.consolidated")[1:4] == ["—", "not found", "[UNVERIFIED]"]


def test_a_derived_value_is_in_whole_units_with_the_currency_its_formula_and_a_calculated_label(results):
    ebit = field(results, "ebit.2025-03-31.consolidated", "derived_fields")
    ebit.update(status="extracted", status_reason=None, value="14823000000", currency="INR")
    cells = row(memo(results), ebit["field_id"])

    assert cells[1:4] == ["14,823,000,000 INR", "extracted", "[CALCULATED: ebit.2025-03-31.consolidated]"]
    assert "`ebit = profit_before_tax + interest_expense` (EBIT-PBT)" in cells[4]
    ebit["currency"] = None
    assert row(memo(results), ebit["field_id"])[1] == "14,823,000,000 INR"  # the reporting currency from section 1


def test_a_derived_total_replaces_the_missing_reported_total_with_the_same_id(results):
    for period in ("2025-03-31", "2024-03-31"):
        assert sum(1 for l in memo(results).split("\n") if l.startswith(f"| `total_borrowings.{period}.consolidated`")) == 1
    assert "no total is reported, so it is derived" in row(memo(results), "total_borrowings.2025-03-31.consolidated")[4]


def test_a_reported_total_stays_when_nothing_is_derived(results):
    results["derived_fields"] = [d for d in results["derived_fields"] if d["field_name"] != "total_borrowings"]

    cells = row(memo(results), "total_borrowings.2025-03-31.consolidated")
    assert cells[1:4] == ["—", "not found", "[UNVERIFIED]"] and "derived" not in cells[4]


def test_a_run_with_no_fields_says_so(results):
    results["fields"], results["derived_fields"] = [], []

    assert "No fields were extracted." in memo(results)


# --- section 4 ---------------------------------------------------------------------------------------------------------------------------------


def metric(results, metric_id):
    return next(m for m in results["metrics"] if m["id"] == metric_id)


def test_a_ratio_is_rounded_to_two_places_and_a_percentage_to_one_and_the_stored_value_is_unchanged(results):
    results_before = copy.deepcopy(results)
    cells = row(memo(results), "MET-03.2025-03-31")

    assert cells[2] == "1.65" and cells[5] == "[CALCULATED: MET-03.2025-03-31]"
    assert cells[3] == "`current_assets / current_liabilities`" and "`current_assets.2025-03-31.consolidated`" in cells[4]
    metric(results, "MET-02.2025-03-31").update(value="12.25", undefined_reason=None)
    assert row(memo(results), "MET-02.2025-03-31")[2] == "12.2%"  # half to even
    assert metric(results_before, "MET-03.2025-03-31")["value"] == "1.647"


@pytest.mark.parametrize(("value", "places", "shown"), [("0.125", 2, "0.12"), ("0.135", 2, "0.14"), ("2.5", 0, "2"), ("-1.25", 1, "-1.2"),
                                                       ("1.647", 2, "1.65"), ("10", 1, "10.0"), ("0", 2, "0.00")])  # fmt: skip
def test_display_rounding_is_half_even(value, places, shown):
    assert rounded(value, places) == shown


def test_an_undefined_metric_shows_its_reason(results):
    cells = row(memo(results), "MET-04.2025-03-31")

    assert cells[2] == "not defined: missing input"


def test_a_metric_caveat_is_printed_in_words_below_the_table(results):
    metric(results, "MET-04.2025-03-31")["caveats"] = ["borrowings_not_presented_assumption"]
    text = memo(results)

    assert ("- **Caveat for `MET-04.2025-03-31`:** total borrowings may exclude current maturities of long-term borrowings shown "
            "under another caption. [CALCULATED: MET-04.2025-03-31]") in text


def test_an_unknown_caveat_is_printed_as_its_name(results):
    metric(results, "MET-03.2025-03-31")["caveats"] = ["some_new_caveat"]

    assert "- **Caveat for `MET-03.2025-03-31`:** some new caveat [CALCULATED: MET-03.2025-03-31]" in memo(results)


def test_the_period_change_is_shown_with_its_caveats(results):
    results["comparisons"]["MET-04"].update(relative_change_percent="25.55", undefined_reason=None, caveats=["borrowings_not_presented_assumption"])
    text = memo(results)

    assert "| `MET-04` | 25.6% | [CALCULATED: MET-04] |" in text and "| `MET-03` | 3.2% | [CALCULATED: MET-03] |" in text
    assert "- **Caveat for the change in `MET-04`:**" in text


def test_a_run_with_no_metrics_says_so(results):
    results["metrics"], results["comparisons"] = [], {}

    assert "No metrics were computed." in memo(results)


# --- every table is well formed and nothing but this module writes a label --------------------------------------------------------------------


def test_every_table_row_has_as_many_cells_as_its_header(results):
    results["analyst_provided"] = {"notes": HOSTILE}
    lines, tables, current = memo(results).split("\n"), [], []
    for line in [*lines, ""]:
        if line.startswith("|"):
            current.append(line)
        elif current:
            tables.append(current)
            current = []

    assert len(tables) == 4  # legend, fields, metrics, changes
    for rows in tables:
        widths = {len(re.split(r"(?<!\\)\|", r.strip())[1:-1]) for r in rows}
        assert len(widths) == 1 and "---" in rows[1]


def test_the_only_unescaped_brackets_are_labels_and_the_legend(results):
    results["analyst_provided"] = {"notes": HOSTILE, "industry": "[UNVERIFIED]"}
    text = "\n".join(l for l in memo(results).split("\n") if not l.startswith("| `[") )
    stripped = re.sub(r"`[^`]*`", "", text)

    assert len(BARE_BRACKET.findall(stripped)) == len(LABEL.findall(stripped))


# --- the text helpers --------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "safe"), [("a|b", "a\\|b"), ("[x]", "\\[x\\]"), ("l1\nl2", "l1 l2"), ("tab\tcr\r", "tab cr"),
                                           ("# h", "\\# h"), ("a b", "a b"), ("`c` *e* _u_", "\\`c\\` \\*e\\* \\_u\\_"), (7, "7")])  # fmt: skip
def test_escaping_keeps_text_on_one_line_and_inert(raw, safe):
    assert esc(raw) == safe


@pytest.mark.parametrize("bad", ["a`b", "a\nb"])
def test_an_identifier_with_a_backtick_or_a_newline_is_refused(bad):
    with pytest.raises(ValueError):
        code(bad)


def test_a_table_row_of_the_wrong_width_is_refused_and_an_empty_cell_shows_a_dash():
    with pytest.raises(ValueError):
        table(["a", "b"], [["x"]])
    assert table(["a", "b"], [["x", ""]])[2] == "| x | — |"


def test_grouping_changes_no_digit():
    assert grouped("14823000000") == "14,823,000,000" and grouped("1234.50") == "1,234.50" and grouped("-1000") == "-1,000"
