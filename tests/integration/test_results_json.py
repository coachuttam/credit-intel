"""results.json: contents, determinism and the golden file (PRD FR-010.1, FR-012.2, K.10; Phase 5 step 5d; B-259).

A synthetic balance sheet, a scripted fake provider and no network. The golden file was reviewed by hand
(the current ratios 1,482.30 / 900.00 = 1.647 and 1,356.75 / 850.00 = 1.59617647... and each indicator were checked against
the page and the rules); it depends on reportlab's byte output for the synthetic PDF and is regenerated only in a reviewed
change: build the PDF and reply as this test does and run ``results_child.py``.
"""

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.export.results import SCHEMA_VERSION, build_results, render_results
from credit_intel.llm.provider import FakeProvider
from credit_intel.run import run_pipeline

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parent / "fixtures" / "results_golden.json"
TOP_KEYS = {"schema_version", "document", "extraction", "attributes", "fields", "derived_fields", "ignored_fields", "metrics",
            "comparisons", "indicators", "disabled_rules", "provisional_notice", "analyst_provided"}  # fmt: skip


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def run(pdf, cache, **kw):
    return run_pipeline(pdf, FakeProvider(script=[fx.good_response(pdf)]), fx.LLM, cache_dir=cache, **kw)


def text_of(result):
    return render_results(result.extraction, result.metrics, result.rules, result.profile)


@pytest.fixture
def result(pdf, tmp_path):
    return run(pdf, tmp_path / "cache")


# --- the golden file ---------------------------------------------------------------------------------------------------------------------------------


def test_the_results_match_the_reviewed_golden_file_byte_for_byte(result):
    assert text_of(result).encode("utf-8") == GOLDEN.read_bytes()


def test_a_fresh_process_with_a_different_hash_seed_gives_the_same_bytes(pdf, tmp_path):
    reply = tmp_path / "reply.json"
    reply.write_text(fx.good_response(pdf), encoding="utf-8")

    done = subprocess.run(
        [sys.executable, str(HERE / "results_child.py"), str(pdf), str(reply), str(tmp_path / "other-cache")],
        env={**os.environ, "PYTHONHASHSEED": "31337"}, capture_output=True, check=True,
    )  # fmt: skip

    assert done.stdout == GOLDEN.read_bytes()


def test_two_runs_in_one_process_give_the_same_text_and_the_second_uses_the_cache(pdf, tmp_path):
    first = run(pdf, tmp_path / "cache")
    second = run(pdf, tmp_path / "cache")

    assert text_of(first) == text_of(second) and second.extraction.stats.cache_hits == 1


# --- what is in it -------------------------------------------------------------------------------------------------------------------------------------


def test_the_top_level_has_exactly_the_documented_keys_and_a_schema_version(result):
    data = json.loads(text_of(result))

    assert set(data) == TOP_KEYS and data["schema_version"] == SCHEMA_VERSION == "1"


def test_the_document_and_extraction_sections_describe_the_input(result, pdf):
    data = build_results(result.extraction, result.metrics, result.rules)

    assert data["document"] == {"file_name": "statement.pdf", "sha256": result.extraction.source_document.sha256, "page_count": 1}
    assert data["extraction"]["candidate_pages"] == [1] and data["extraction"]["locator_method"] == "keywords"
    assert data["extraction"]["configured_basis"] == "consolidated" and data["extraction"]["bases_present"] == ["consolidated"]


def test_every_field_the_run_holds_is_listed_once_with_its_evidence_unchanged(result):
    data = json.loads(text_of(result))
    records = {r.field_id + r.period_role.value: r for r in result.extraction.field_set.fields}

    assert len(data["fields"]) == len(records) == 24
    ids = [f["field_id"] for f in data["fields"]]
    assert len(ids) == len(set(ids))
    for written in data["fields"]:
        record = records[written["field_id"] + written["period_role"]]
        assert written["status"] == record.status.value and written["evidence_quote"] == record.evidence_quote
        assert written["page_number"] == record.page_number and written["raw_value"] == record.raw_value
        assert written["value"] == (None if record.value is None else format(record.value, "f"))


def test_a_stored_amount_is_written_exactly_as_the_decimal_string(result):
    data = json.loads(text_of(result))
    assets = next(f for f in data["fields"] if f["field_id"] == "current_assets.2025-03-31.consolidated")

    assert assets["value"] == "14823000000" and Decimal(assets["value"]) == Decimal("14823000000") and assets["raw_value"] == "1,482.30"


def test_derived_values_are_listed_apart_from_source_fields_and_carry_their_derivation(result):
    data = json.loads(text_of(result))

    derived = {d["field_name"]: d for d in data["derived_fields"]}
    assert set(derived) == {"ebit", "total_borrowings"} and all(d["origin"] == "derived" for d in data["derived_fields"])
    assert derived["ebit"]["derivation"]["method_id"] == "EBIT-PBT"
    assert all(f["origin"] == "source" for f in data["fields"])


def test_every_metric_has_a_unique_id_a_formula_and_inputs_and_is_marked_calculated(result):
    data = json.loads(text_of(result))

    ids = [m["id"] for m in data["metrics"]]
    assert len(ids) == len(set(ids)) == 9 and "MET-03.2025-03-31" in ids and "MET-01.2025-03-31" in ids
    for metric in data["metrics"]:
        assert metric["origin"] == "calculated" and metric["formula"] and metric["input_field_ids"]
        assert (metric["value"] is None) != (metric["undefined_reason"] is None)
    current_ratio = next(m for m in data["metrics"] if m["id"] == "MET-03.2025-03-31")
    assert current_ratio["value"] == "1.647" and current_ratio["unit"] == "ratio"


def test_the_seven_indicators_are_listed_with_their_conditions_and_the_provisional_notice(result):
    data = json.loads(text_of(result))

    assert [i["id"] for i in data["indicators"]] == [f"RI-00{n}" for n in range(1, 8)]
    assert "not universal banking standards" in data["provisional_notice"] and data["disabled_rules"] == []
    ri006 = next(i for i in data["indicators"] if i["id"] == "RI-006")
    assert ri006["outcome"] == "triggered" and ri006["severity"] == "info" and ri006["conditions"][0]["field_ids"]
    ri003 = next(i for i in data["indicators"] if i["id"] == "RI-003")
    assert [c["condition_id"] for c in ri003["conditions"]] == ["C1", "C2"] and ri003["conditions"][0]["threshold"] == "1.00"


def test_the_attributes_are_listed_with_their_evidence(result):
    data = json.loads(text_of(result))

    names = [(a["attribute"], a["period_role"]) for a in data["attributes"]]
    assert ("entity_name", None) in names and ("period_end", "current") in names and ("period_end", "comparative") in names
    assert all(a["status"] == "extracted" and a["evidence_quote"] for a in data["attributes"])


# --- nothing that changes between runs, no floats in money, and a stable shape ----------------------------------------------------------------------


def test_the_file_holds_no_timestamp_run_id_or_other_thing_that_changes_between_runs(result):
    data = json.loads(text_of(result))
    keys = set()

    def walk(node):
        if isinstance(node, dict):
            keys.update(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    assert not [k for k in keys if any(w in k.lower() for w in ("timestamp", "generated", "run_id", "created", "elapsed", "duration"))]


def test_no_amount_ratio_or_threshold_is_a_float(result):
    data = json.loads(text_of(result))
    floats = []

    def walk(node, path, layout):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, path + [key], layout or key == "details")
        elif isinstance(node, list):
            for item in node:
                walk(item, path, layout)
        elif isinstance(node, float) and not layout:
            floats.append(path)

    walk(data, [], False)
    assert floats == []


def test_keys_are_sorted_at_every_level_and_the_text_ends_with_one_newline(result):
    text = text_of(result)
    data = json.loads(text)

    assert text == json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n" and not text.endswith("\n\n")


def test_the_profile_appears_only_under_analyst_provided_and_changes_nothing_else(pdf, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"borrower_name": "Acme", "notes": "revenue 999"}), encoding="utf-8")

    with_profile = json.loads(text_of(run(pdf, tmp_path / "c1", profile_path=profile)))
    without = json.loads(text_of(run(pdf, tmp_path / "c2")))

    assert with_profile["analyst_provided"] == {"borrower_name": "Acme", "notes": "revenue 999"} and without["analyst_provided"] == {}
    with_profile.pop("analyst_provided"), without.pop("analyst_provided")
    assert with_profile == without
