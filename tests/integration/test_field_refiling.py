"""A total_borrowings proposal on a borrowings component row is verified as that component (PRD v0.4.38; B-311). Synthetic PDF, a fake provider."""

import io
import json
from datetime import UTC, datetime, timedelta

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.llm.provider import FakeProvider

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
SETTINGS = '[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'
ROWS = [
    ("Long-term debt", "", "300.00", "250.00"),
    ("Short-term debt", "", "120.00", "100.00"),
    ("Total borrowings", "", "420.00", "350.00"),
    ("Other obligations", "", "55.00", "45.00"),
    ("Total current assets", "14", "1,482.30", "1,356.75"),
]


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def two_page_pdf(path):
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), invariant=1)
    fx._statement_page(pdf, fx.ROWS, "Consolidated Balance Sheet", "(Rs. in crore)")
    fx._statement_page(pdf, ROWS, "Consolidated Balance Sheet", "(Rs. in crore)")
    pdf.save()
    return path


def run(tmp_path, proposals, pdf_builder=None, page=1, edit=None):
    pdf = (pdf_builder or (lambda p: fx.balance_sheet_pdf(p, rows=ROWS)))(tmp_path / "statement.pdf")
    fields = [fx.field(pdf, name, role, raw, needle, page=page) for name, role, raw, needle in proposals]
    if edit:
        edit(fields)
    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS, encoding="utf-8")
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    out, err = io.StringIO(), io.StringIO()
    code = main([str(pdf), "--config", str(config), "--output-dir", str(tmp_path / "runs")], provider_factory=lambda s, e: FakeProvider(script=[fx.reply(fx.good_attributes(pdf), fields)]),
                clock=lambda: next(ticks), stdout=out, stderr=err, assignments=tmp_path / "none.jsonl", env={})  # fmt: skip
    folder = tmp_path / out.getvalue().strip()
    assert code == 0, err.getvalue()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    return manifest, {(f["field_name"], f["period_role"]): f for f in results["fields"]}


def test_a_long_term_debt_row_proposed_as_the_total_is_verified_as_the_non_current_component(tmp_path):
    manifest, fields = run(tmp_path, [("total_borrowings", "current", "300.00", "Long-term debt")])

    assert fields[("total_borrowings", "current")]["status"] == "not_found"
    assert fields[("borrowings_non_current", "current")]["status"] == "extracted"
    assert manifest["field_refilings"] == [{"proposed": "total_borrowings", "used": "borrowings_non_current", "page": 1, "period": "current"}]


def test_a_short_term_debt_row_proposed_as_the_total_is_verified_as_the_current_component(tmp_path):
    manifest, fields = run(tmp_path, [("total_borrowings", "comparative", "100.00", "Short-term debt")])

    assert fields[("borrowings_current", "comparative")]["status"] == "extracted"
    assert manifest["field_refilings"][0]["used"] == "borrowings_current"


def test_a_row_that_prints_a_total_stays_a_total_and_nothing_is_recorded(tmp_path):
    manifest, fields = run(tmp_path, [("total_borrowings", "current", "420.00", "Total borrowings")])

    assert fields[("total_borrowings", "current")]["status"] == "extracted"
    assert "field_refilings" not in manifest


def test_a_row_recognised_for_no_field_stays_requires_review(tmp_path):
    manifest, fields = run(tmp_path, [("total_borrowings", "current", "55.00", "Other obligations")])

    assert fields[("total_borrowings", "current")]["status"] == "requires_review"
    assert "field_refilings" not in manifest


def test_the_models_own_component_proposal_wins_and_the_figure_is_counted_once(tmp_path):
    manifest, fields = run(
        tmp_path,
        [("total_borrowings", "current", "300.00", "Long-term debt"), ("borrowings_non_current", "current", "300.00", "Long-term debt")],
    )

    extracted = [key for key, f in fields.items() if f["status"] == "extracted"]
    assert extracted == [("borrowings_non_current", "current")]
    assert "field_refilings" not in manifest


def test_a_re_filed_figure_that_is_not_on_the_page_fails_its_own_check(tmp_path):
    _, fields = run(tmp_path, [("total_borrowings", "current", "999.00", "Long-term debt")])

    assert fields[("borrowings_non_current", "current")]["status"] != "extracted"


def test_the_page_recorded_is_the_page_the_figure_was_cited_on(tmp_path):
    manifest, fields = run(tmp_path, [("total_borrowings", "current", "300.00", "Long-term debt")], two_page_pdf, page=2)

    assert fields[("borrowings_non_current", "current")]["status"] == "extracted"
    assert manifest["field_refilings"][0]["page"] == 2


def test_a_proposal_that_cites_a_page_that_is_not_there_is_left_alone(tmp_path):
    def cite_page_nine(fields):
        fields[0]["page_number"] = 9

    manifest, fields = run(tmp_path, [("total_borrowings", "current", "300.00", "Long-term debt")], edit=cite_page_nine)

    assert fields[("total_borrowings", "current")]["status"] == "requires_review"
    assert "field_refilings" not in manifest


def test_two_proposals_for_the_same_row_and_period_make_one_component(tmp_path):
    proposal = ("total_borrowings", "current", "300.00", "Long-term debt")

    manifest, fields = run(tmp_path, [proposal, proposal])

    assert len(manifest["field_refilings"]) == 1
    assert fields[("borrowings_non_current", "current")]["status"] == "extracted"


def test_a_row_recognised_for_two_components_is_not_re_filed(tmp_path, monkeypatch):
    from credit_intel.extraction import verify

    real = verify.check_label

    def both_components(name, *args, **kwargs):
        result = real("borrowings_non_current" if name == "borrowings_current" else name, *args, **kwargs)
        return result

    monkeypatch.setattr(verify, "check_label", both_components)

    manifest, fields = run(tmp_path, [("total_borrowings", "current", "300.00", "Long-term debt")])

    assert "field_refilings" not in manifest
    assert fields[("total_borrowings", "current")]["status"] == "requires_review"
