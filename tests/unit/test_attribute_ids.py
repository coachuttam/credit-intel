"""Stable IDs for the document-level attributes, in the results, the memo and the traceability check (PRD H.1.2, K.0, K.10; PRD v0.4.27; step S1; B-287)."""

import copy
import json
from pathlib import Path

import pytest

from credit_intel.memo.render import render_memo
from credit_intel.models import DocumentAttribute, DocumentAttributeName as N, PeriodRole, Status, attribute_id
from memo_trace import problems

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
IDS = ["entity_name", "period_end.current", "period_end.comparative", "statement_basis", "reporting_currency", "scale"]
RUN_ID, WHEN = "20261024T101530.123456Z-0dd49919", "20261024T101530.123456Z"


@pytest.fixture
def golden():
    return json.loads((FIXTURES / "results_golden.json").read_text(encoding="utf-8"))


def memo(results):
    return render_memo(results, RUN_ID, WHEN)


# --- the model ---------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "role", "expected"),
    [(N.ENTITY_NAME, None, "entity_name"), (N.PERIOD_END, PeriodRole.CURRENT, "period_end.current"), (N.PERIOD_END, PeriodRole.COMPARATIVE, "period_end.comparative"),
     (N.STATEMENT_BASIS, None, "statement_basis"), (N.REPORTING_CURRENCY, None, "reporting_currency"), (N.SCALE, None, "scale")],
)  # fmt: skip
def test_each_attribute_has_the_id_the_prd_names(name, role, expected):
    record = DocumentAttribute(attribute=name, period_role=role, status=Status.NOT_FOUND)

    assert attribute_id(name, role) == expected == record.id


def test_the_id_is_part_of_the_record_when_it_is_written_out_and_does_not_depend_on_its_status():
    found = DocumentAttribute(attribute=N.SCALE, raw_text="in crore", normalised_value="crore", page_number=1, evidence_quote="(Rs. in crore)", status=Status.EXTRACTED)
    missing = DocumentAttribute(attribute=N.SCALE, status=Status.NOT_FOUND)

    assert found.model_dump(mode="python")["id"] == missing.model_dump(mode="python")["id"] == "scale"


# --- results.json ------------------------------------------------------------------------------------------------------------------------------


def test_the_results_list_the_six_attributes_with_their_ids_once_each(golden):
    ids = [a["id"] for a in golden["attributes"]]

    assert ids == IDS and len(set(ids)) == 6


def test_an_attribute_id_is_never_the_id_of_a_field_a_metric_or_a_rule(golden):
    others = {f["field_id"] for f in golden["fields"] + golden["derived_fields"]} | {m["id"] for m in golden["metrics"]} | {i["id"] for i in golden["indicators"]}

    assert not set(IDS) & others


# --- the memo -----------------------------------------------------------------------------------------------------------------------------------


def test_section_1_prints_the_id_beside_each_attribute_it_shows(golden):
    text = memo(golden)

    for line in ("- **Entity name** (`entity_name`): Acme Industries Limited [SOURCE: p.1]", "- **Reporting currency** (`reporting_currency`): INR [SOURCE: p.1]",
                 "- **Scale** (`scale`): crore [SOURCE: p.1]", "- **Current period end** (`period_end.current`): 2025-03-31 [SOURCE: p.1]",
                 "- **Comparative period end** (`period_end.comparative`): 2024-03-31 [SOURCE: p.1]"):  # fmt: skip
        assert line in text
    assert "(`statement_basis`)" not in text and "- **Statement basis used:** consolidated [CALCULATED: extraction]" in text


def test_the_header_borrower_line_resolves_to_the_entity_name_without_printing_its_id(golden):
    header = memo(golden).split("## 1. ")[0]

    assert "**Borrower:** Acme Industries Limited [SOURCE: p.1]" in header and "`entity_name`" not in header


def test_a_missing_attribute_still_gets_its_id_on_its_line_and_is_unverified(golden):
    golden["attributes"] = [a for a in golden["attributes"] if a["id"] != "scale"]

    assert "- **Scale** (`scale`): not found [UNVERIFIED]" in memo(golden)


# --- the traceability check ------------------------------------------------------------------------------------------------------------------


def test_the_checker_accepts_the_golden_memo_and_a_memo_with_a_missing_attribute(golden):
    assert problems(memo(golden), golden) == []
    missing = copy.deepcopy(golden)
    next(a for a in missing["attributes"] if a["id"] == "scale").update(status="not_found", page_number=None, evidence_quote=None, raw_text=None, normalised_value=None)

    assert problems(memo(missing), missing) == []


def test_the_checker_finds_a_section_1_label_that_names_a_page_the_attribute_was_not_read_on(golden):
    text = memo(golden).replace("- **Scale** (`scale`): crore [SOURCE: p.1]", "- **Scale** (`scale`): crore [SOURCE: p.2]")

    assert any("is not a page the field or attribute beside it was read on" in p for p in problems(text, golden))


def test_the_checker_finds_a_borrower_line_with_the_wrong_page(golden):
    text = memo(golden).replace("**Borrower:** Acme Industries Limited [SOURCE: p.1]", "**Borrower:** Acme Industries Limited [SOURCE: p.7]")

    assert any("[SOURCE: p.7]" in p for p in problems(text, golden))


def test_the_checker_finds_an_attribute_id_that_does_not_exist(golden):
    text = memo(golden).replace("(`scale`)", "(`period_end.previous`)")

    assert any("unknown attribute ID period_end.previous" in p for p in problems(text, golden))


def test_the_checker_finds_a_label_that_disagrees_with_the_attributes_status(golden):
    unverified = memo(golden).replace("- **Scale** (`scale`): crore [SOURCE: p.1]", "- **Scale** (`scale`): crore [UNVERIFIED]")
    absent = copy.deepcopy(golden)
    next(a for a in absent["attributes"] if a["id"] == "scale").update(status="not_found")
    sourced = memo(absent).replace("- **Scale** (`scale`): not found [UNVERIFIED]", "- **Scale** (`scale`): crore [SOURCE: p.1]")

    assert any("does not agree with the status of scale" in p for p in problems(unverified, golden))
    assert any("does not agree with the status of scale" in p for p in problems(sourced, absent))
