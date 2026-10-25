"""A mis-cited currency and scale declaration inside a whole run, and the manifest record of the repair (PRD v0.4.36; B-307). Synthetic PDFs, a fake provider."""

import io
import json
from datetime import UTC, datetime, timedelta

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.extraction.attributes import PageRepair
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import FieldName, PeriodRole, Status

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
SETTINGS = '[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def mis_cited(pdf, page=2):
    """The good reply, but the model cites ``page`` for the currency and scale declarations (page 2 is a narrative page, not a candidate)."""
    reply = json.loads(fx.good_response(pdf))
    for attribute in reply["attributes"]:
        if attribute["attribute"] in ("reporting_currency", "scale"):
            attribute["page_number"] = page
    return json.dumps(reply)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf", narrative_page="Directors report. The company had a good year.")


def test_a_run_with_the_declarations_cited_on_the_wrong_page_still_extracts_every_field_and_reports_the_repair(pdf, tmp_path):
    run = run_extraction(pdf, FakeProvider(script=[mis_cited(pdf)]), fx.LLM, cache_dir=tmp_path / "cache")

    assert run.field_set.counts["extracted"] == 6 and run.field_set.get(FieldName.CURRENT_ASSETS, PeriodRole.CURRENT).status is Status.EXTRACTED
    assert run.attributes.scale.page_number == 1 and run.attributes.reporting_currency.page_number == 1
    assert run.attributes.page_repairs == (PageRepair("reporting_currency", 2, 1), PageRepair("scale", 2, 1))


def test_a_run_with_the_declarations_cited_right_reports_no_repair(pdf, tmp_path):
    run = run_extraction(pdf, FakeProvider(script=[fx.good_response(pdf)]), fx.LLM, cache_dir=tmp_path / "cache")

    assert run.attributes.page_repairs == () and run.field_set.counts["extracted"] == 6


def cli(tmp_path, pdf, reply):
    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS, encoding="utf-8")
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    out, err = io.StringIO(), io.StringIO()
    code = main([str(pdf), "--config", str(config), "--output-dir", str(tmp_path / "runs")], provider_factory=lambda s, e: FakeProvider(script=[reply]),
                clock=lambda: next(ticks), stdout=out, stderr=err, assignments=tmp_path / "none.jsonl", env={})  # fmt: skip
    folder = tmp_path / out.getvalue().strip()
    return code, {name: (folder / name).read_text(encoding="utf-8") for name in ("manifest.json", "results.json")} if code == 0 else {}


def test_the_manifest_records_each_repair_as_cited_page_to_page_used(pdf, tmp_path):
    code, files = cli(tmp_path, pdf, mis_cited(pdf))

    manifest, results = json.loads(files["manifest.json"]), json.loads(files["results.json"])
    assert code == 0
    assert manifest["attribute_page_repairs"] == [{"attribute": "reporting_currency", "cited_page": 2, "page_used": 1},
                                                  {"attribute": "scale", "cited_page": 2, "page_used": 1}]  # fmt: skip
    pages = {a["attribute"]: a["page_number"] for a in results["attributes"]}
    assert pages["scale"] == 1 and pages["reporting_currency"] == 1  # the record holds the page the declaration is on
    assert all("cited_page" not in attribute for attribute in results["attributes"])  # the attribute records carry no trace of the model's wrong page


def test_a_run_without_a_repair_has_no_such_key_in_its_manifest(pdf, tmp_path):
    code, files = cli(tmp_path, pdf, fx.good_response(pdf))

    assert code == 0 and "attribute_page_repairs" not in files["manifest.json"]
