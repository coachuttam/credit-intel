"""A currency and scale the model did not propose, read from the pages inside a whole run, and the manifest record (PRD v0.4.37; B-310). Synthetic PDF, a fake provider."""

import io
import json
from datetime import UTC, datetime, timedelta

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.llm.provider import FakeProvider

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
SETTINGS = '[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def cli(tmp_path, pdf, reply):
    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS, encoding="utf-8")
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    out, err = io.StringIO(), io.StringIO()
    code = main([str(pdf), "--config", str(config), "--output-dir", str(tmp_path / "runs")], provider_factory=lambda s, e: FakeProvider(script=[reply]),
                clock=lambda: next(ticks), stdout=out, stderr=err, assignments=tmp_path / "none.jsonl", env={})  # fmt: skip
    folder = tmp_path / out.getvalue().strip()
    return code, {name: (folder / name).read_text(encoding="utf-8") for name in ("manifest.json", "results.json", "memo.md")} if code == 0 else {}


def test_the_manifest_records_each_derivation_and_the_results_hold_the_page_line_as_the_evidence(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")
    reply = fx.reply(fx.good_attributes(pdf, drop=("reporting_currency", "scale")), json.loads(fx.good_response(pdf))["fields"])

    code, files = cli(tmp_path, pdf, reply)

    manifest, results = json.loads(files["manifest.json"]), json.loads(files["results.json"])
    assert code == 0
    assert manifest["attribute_derivations"] == [{"attribute": "reporting_currency", "page": 1, "why": "no_proposal"}, {"attribute": "scale", "page": 1, "why": "no_proposal"}]
    attributes = {a["attribute"]: a for a in results["attributes"]}
    assert attributes["scale"]["status"] == "extracted" and attributes["scale"]["normalised_value"] == "crore" and attributes["scale"]["evidence_quote"] == "(Rs. in crore)"
    assert attributes["reporting_currency"]["normalised_value"] == "INR" and attributes["reporting_currency"]["page_number"] == 1
    assert sum(1 for f in results["fields"] if f["status"] == "extracted") == 6


def test_a_run_whose_attributes_the_model_proposed_has_no_such_key_in_its_manifest(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")

    code, files = cli(tmp_path, pdf, fx.good_response(pdf))

    assert code == 0 and "attribute_derivations" not in files["manifest.json"]


def test_a_run_is_the_same_whether_the_model_proposed_the_attributes_or_the_code_read_them(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")
    fields = json.loads(fx.good_response(pdf))["fields"]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    _, proposed = cli(tmp_path / "a", pdf, fx.good_response(pdf))
    _, derived = cli(tmp_path / "b", pdf, fx.reply(fx.good_attributes(pdf, drop=("reporting_currency", "scale")), fields))

    p, d = json.loads(proposed["results.json"]), json.loads(derived["results.json"])
    assert [(f["field_name"], f["value"], f["status"]) for f in p["fields"]] == [(f["field_name"], f["value"], f["status"]) for f in d["fields"]]
    assert p["metrics"] == d["metrics"] and p["indicators"] == d["indicators"]
