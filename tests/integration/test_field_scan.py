"""A borrowings component row the model did not propose is read from the balance-sheet page by the code (PRD v0.4.39; B-312). Synthetic PDF, a fake provider."""

import io
import json
from datetime import UTC, datetime, timedelta

import pytest
from reportlab.pdfgen import canvas

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.llm.provider import FakeProvider

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
SETTINGS = '[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'
DEBT = [
    ("Long-term debt", "", "300.00", "250.00"),
    ("Short-term debt", "", "120.00", "100.00"),
    ("Current portion of long-term debt", "", "40.00", "30.00"),
]
STATEMENT = [("Total current assets", "14", "1,482.30", "1,356.75"), ("Total equity", "", "600.00", "500.00"), ("Total current liabilities", "15", "900.00", "850.00")]


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def run(tmp_path, rows=None, proposals=(), attributes=None, build=None, extra_args=()):
    pdf = (build or (lambda p: fx.balance_sheet_pdf(p, rows=[*(DEBT if rows is None else rows), *STATEMENT])))(tmp_path / "statement.pdf")
    fields = [fx.field(pdf, name, role, raw, needle) for name, role, raw, needle in proposals]
    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS, encoding="utf-8")
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    out, err = io.StringIO(), io.StringIO()
    reply = fx.reply(attributes if attributes is not None else fx.good_attributes(pdf), fields)
    code = main([str(pdf), "--config", str(config), "--output-dir", str(tmp_path / "runs"), *extra_args], provider_factory=lambda s, e: FakeProvider(script=[reply]),
                clock=lambda: next(ticks), stdout=out, stderr=err, assignments=tmp_path / "none.jsonl", env={})  # fmt: skip
    assert code == 0, err.getvalue()
    folder = tmp_path / out.getvalue().strip()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    return manifest, {(f["field_name"], f["period_role"]): f for f in results["fields"]}


def status(fields, name, role):
    return fields[(name, role)]["status"]


def test_the_three_debt_rows_are_read_for_both_periods_when_the_model_proposed_none(tmp_path):
    manifest, fields = run(tmp_path)

    for name in ("borrowings_non_current", "borrowings_current", "current_maturities_long_term_borrowings"):
        for role in ("current", "comparative"):
            assert status(fields, name, role) == "extracted"
    assert fields[("borrowings_non_current", "current")]["origin"] == "source"
    assert sorted((s["field"], s["period"]) for s in manifest["field_scans"])[0] == ("borrowings_current", "comparative")
    assert len(manifest["field_scans"]) == 6 and {s["page"] for s in manifest["field_scans"]} == {1}
    assert {s["label"] for s in manifest["field_scans"]} == {"Long-term debt", "Short-term debt", "Current portion of long-term debt"}


def test_the_models_own_proposal_for_a_field_and_period_is_kept_and_not_scanned(tmp_path):
    manifest, fields = run(tmp_path, proposals=[("borrowings_non_current", "current", "300.00", "Long-term debt")])

    assert status(fields, "borrowings_non_current", "current") == "extracted"
    assert ("borrowings_non_current", "current") not in {(s["field"], s["period"]) for s in manifest["field_scans"]}
    assert ("borrowings_non_current", "comparative") in {(s["field"], s["period"]) for s in manifest["field_scans"]}


def test_a_page_with_no_recognised_debt_row_adds_nothing_and_has_no_manifest_block(tmp_path):
    manifest, fields = run(tmp_path, rows=[("Lease liabilities", "", "55.00", "45.00")])

    assert "field_scans" not in manifest
    assert all(status(fields, n, r) == "not_found" for n in ("borrowings_non_current", "borrowings_current") for r in ("current", "comparative"))


def test_two_recognised_lines_for_one_field_add_nothing_for_that_field(tmp_path):
    rows = [*DEBT, ("Short-term debt", "", "5.00", "4.00")]

    manifest, fields = run(tmp_path, rows=rows)

    assert status(fields, "borrowings_current", "current") == "not_found"
    assert {s["field"] for s in manifest["field_scans"]} == {"borrowings_non_current", "current_maturities_long_term_borrowings"}


def test_a_page_that_is_not_a_balance_sheet_is_not_scanned(tmp_path):
    def build(path):
        pdf = canvas.Canvas(str(path), invariant=1)
        fx._statement_page(pdf, fx.ROWS, "Consolidated Balance Sheet", "(Rs. in crore)")
        fx._statement_page(pdf, [*DEBT, *STATEMENT], "Consolidated Statement of Cash Flows", "(Rs. in crore)")
        pdf.save()
        return path

    manifest, fields = run(tmp_path, build=build, extra_args=("--pages", "1-2", "--assert-basis", "consolidated"))

    assert "field_scans" not in manifest and status(fields, "borrowings_non_current", "current") == "not_found"


def test_a_contradicted_scale_blocks_the_scan(tmp_path):
    def attributes(pdf):
        return [dict(a, normalised_value="lakh") if a["attribute"] == "scale" else a for a in fx.good_attributes(pdf)]

    pdf = fx.balance_sheet_pdf(tmp_path / "pre.pdf", rows=DEBT)
    manifest, fields = run(tmp_path, attributes=attributes(pdf))

    assert "field_scans" not in manifest
    assert all(status(fields, "borrowings_non_current", r) != "extracted" for r in ("current", "comparative"))


def test_a_dash_in_the_column_is_read_as_printed_and_goes_to_the_same_checks(tmp_path):
    rows = [("Long-term debt", "", "-", "250.00")]

    manifest, fields = run(tmp_path, rows=rows)

    assert ("borrowings_non_current", "current") in {(s["field"], s["period"]) for s in manifest["field_scans"]}
    assert fields[("borrowings_non_current", "current")]["evidence_quote"].split()[-2] == "-"


def test_a_lease_liability_row_is_not_recognised(tmp_path):
    manifest, _ = run(tmp_path, rows=[("Lease liabilities", "", "55.00", "45.00")])

    assert "field_scans" not in manifest



def test_a_row_with_no_figure_in_a_period_column_adds_nothing_for_that_period(tmp_path):
    manifest, fields = run(tmp_path, rows=[("Long-term debt", "", "300.00", "")])

    assert [(s["field"], s["period"]) for s in manifest["field_scans"]] == [("borrowings_non_current", "current")]
    assert status(fields, "borrowings_non_current", "comparative") == "not_found"


def test_the_page_recorded_is_the_page_the_row_was_read_from(tmp_path):
    def build(path):
        pdf = canvas.Canvas(str(path), invariant=1)
        fx._statement_page(pdf, fx.ROWS, "Consolidated Balance Sheet", "(Rs. in crore)")
        fx._statement_page(pdf, [*DEBT, *STATEMENT], "Consolidated Balance Sheet", "(Rs. in crore)")
        pdf.save()
        return path

    manifest, fields = run(tmp_path, build=build)

    assert {s["page"] for s in manifest["field_scans"]} == {2}
    assert fields[("borrowings_non_current", "current")]["page_number"] == 2
