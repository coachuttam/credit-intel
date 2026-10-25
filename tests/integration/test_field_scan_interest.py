"""The interest-expense row the model did not propose, read from an income-statement page (PRD v0.4.40; B-313). Synthetic PDFs, a fake provider."""

from decimal import Decimal

import pipeline_fixture as fx
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import FieldName, PeriodRole, StatementBasis, Status

CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE
TITLE = "Consolidated Statement of Profit and Loss"
ROWS = [("Finance cost", "2,385.00", "2,935.00")]


def attributes(pdf):
    return [
        fx.attribute(pdf, "entity_name", "Acme Industries Limited", "Acme Industries Limited", "Acme Industries Limited"),
        fx.attribute(pdf, "period_end", "March 31, 2025", "2025-03-31", "Year ended March 31,\n2025 2024", "current"),
        fx.attribute(pdf, "statement_basis", "Consolidated", "consolidated", TITLE),
        fx.attribute(pdf, "reporting_currency", "Rs.", "INR", "(Rs. in crore)"),
        fx.attribute(pdf, "scale", "in crore", "crore", "(Rs. in crore)"),
    ]


def run(tmp_path, pdf, proposals=(), attribute_list=None):
    fields = [fx.field(pdf, name, role, raw, label) for name, role, raw, label in proposals]
    provider = FakeProvider(script=[fx.reply(attribute_list if attribute_list is not None else attributes(pdf), fields)])
    return run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "cache", page_range="1", assert_basis=StatementBasis.CONSOLIDATED)


def interest(result, role):
    return result.field_set.get(FieldName.INTEREST_EXPENSE, role)


def test_a_finance_cost_row_the_model_did_not_propose_is_read_for_both_periods(tmp_path):
    pdf = fx.income_expense_pdf(tmp_path / "p.pdf", heading=TITLE, rows=ROWS)

    result = run(tmp_path, pdf)

    assert (interest(result, CUR).status, interest(result, COMP).status) == (Status.EXTRACTED, Status.EXTRACTED)
    assert interest(result, CUR).value == Decimal("23850000000.00") and interest(result, CUR).raw_value == "2,385.00"
    assert [(s.field, s.page, s.period, s.label) for s in result.field_scans] == [
        ("interest_expense", 1, "current", "Finance cost"),
        ("interest_expense", 1, "comparative", "Finance cost"),
    ]


def test_the_models_own_proposal_for_a_period_is_kept_and_only_the_other_period_is_read(tmp_path):
    pdf = fx.income_expense_pdf(tmp_path / "p.pdf", heading=TITLE, rows=ROWS)

    result = run(tmp_path, pdf, [("interest_expense", "current", "2,385.00", "Finance cost")])

    assert [(s.field, s.period) for s in result.field_scans] == [("interest_expense", "comparative")]
    assert interest(result, CUR).status is Status.EXTRACTED and interest(result, COMP).status is Status.EXTRACTED


def test_two_recognised_rows_add_nothing(tmp_path):
    pdf = fx.income_expense_pdf(tmp_path / "p.pdf", heading=TITLE, rows=[*ROWS, ("Interest expense", "10.00", "9.00")])

    result = run(tmp_path, pdf)

    assert result.field_scans == () and interest(result, CUR).status is Status.NOT_FOUND


def test_a_finance_cost_row_on_a_balance_sheet_page_is_not_read(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "bs.pdf", rows=[*fx.ROWS, ("Finance cost", "", "2,385.00", "2,935.00")])

    result = run(tmp_path, pdf, attribute_list=fx.good_attributes(pdf))

    assert result.attributes.scale.status is Status.EXTRACTED  # the attributes hold, so only the page decides
    assert not [s for s in result.field_scans if s.field == "interest_expense"]


def test_a_bracketed_row_under_an_income_expense_heading_is_read_as_a_positive_expense(tmp_path):
    rows = [("Other income (expense), net", "", ""), ("Interest expense", "(2,385.00)", "(2,935.00)")]
    pdf = fx.income_expense_pdf(tmp_path / "p.pdf", heading=TITLE, rows=rows)

    result = run(tmp_path, pdf)

    assert interest(result, CUR).status is Status.EXTRACTED and interest(result, CUR).value == Decimal("23850000000.00")
    assert interest(result, CUR).validation.details["sign"]["expense_table_rule"] is True


def test_a_row_the_labels_do_not_recognise_adds_nothing(tmp_path):
    pdf = fx.income_expense_pdf(tmp_path / "p.pdf", heading=TITLE, rows=[("Interest and dividends income", "4,100.00", "3,900.00")])

    result = run(tmp_path, pdf)

    assert result.field_scans == ()
