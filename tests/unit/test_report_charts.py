"""The two charts of the PDF report (PRD FR-015 criterion 4, v0.4.56; step 4 of its build; B-329).

Every number a chart prints must also be in the memo, with the same ID and label; an OCR or unverified value is never plotted.
"""

import copy
import dataclasses
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from report_results import RUN_ID, WHEN, golden, rich, set_field  # noqa: E402

from credit_intel.memo.render import render_memo  # noqa: E402
from credit_intel.memo.sections import DRAFT_STATEMENT  # noqa: E402
from credit_intel.report import ReportError, build_pdf, charts, check, make_report  # noqa: E402
from credit_intel.report.mdparse import parser, plain  # noqa: E402
from credit_intel.report.check import read_pages  # noqa: E402


def memo_of(data):
    return render_memo(data, RUN_ID, WHEN)


def slots(chart):
    return [s for p in chart.panels for s in p.slots]


def by_id(chart_list, record_id):
    return next(s for c in chart_list for s in slots(c) if s.record_id == record_id)


# --- building the data -------------------------------------------------------------------------------------------------------------------------


def test_there_are_two_charts_each_with_two_panels_of_two_slots():
    bars, dots = charts.build_charts(golden())
    assert (bars.kind, dots.kind) == ("bars", "dots")
    assert [p.name for p in bars.panels] == ["Revenue", "Net profit"] and [p.name for p in dots.panels] == ["Current ratio", "Interest coverage ratio"]
    assert all([s.role for s in p.slots] == ["comparative", "current"] for c in (bars, dots) for p in c.panels)


def test_the_golden_results_plot_only_the_current_ratio():
    bars, dots = charts.build_charts(golden())
    assert not bars.plotted() and bars.source_text() == charts.NOTHING
    assert [s.record_id for s in dots.plotted()] == ["MET-03.2024-03-31", "MET-03.2025-03-31"]
    assert [s.shown for s in dots.plotted()] == ["1.60", "1.65"]
    assert [s.label for s in dots.plotted()] == ["[CALCULATED: MET-03.2024-03-31]", "[CALCULATED: MET-03.2025-03-31]"]
    assert all(s.note == "not plotted: not defined: missing input" for s in dots.panels[1].slots)
    assert all(s.note == "not plotted: not found" for s in slots(bars))


def test_a_field_slot_carries_the_memos_displayed_string_label_and_the_stored_value_as_its_height():
    bars, _ = charts.build_charts(rich())
    revenue_now = by_id([bars], "revenue.2025-03-31.consolidated")
    assert (revenue_now.shown, revenue_now.label, revenue_now.height) == ("14,823.00 (INR crore)", "[SOURCE: p.1]", 148230000000.0)
    assert revenue_now.caption == "2025-03-31 current" and revenue_now.note is None
    loss = by_id([bars], "net_profit.2025-03-31.consolidated")
    assert loss.shown == "(310.00) (INR crore)" and loss.height == -3100000000.0  # the brackets are plain text, not Markdown escapes


def test_a_value_read_by_ocr_is_not_plotted_with_the_memos_words():
    bars, _ = charts.build_charts(rich(ocr_net_profit=True))
    slot = by_id([bars], "net_profit.2025-03-31.consolidated")
    assert not slot.plotted and slot.shown is None and slot.note == "not plotted: requires review"
    assert by_id([bars], "net_profit.2024-03-31.consolidated").plotted  # the other period still is


def test_a_field_marked_extracted_but_read_by_ocr_is_still_not_plotted():
    data = rich()
    set_field(data, "net_profit.2025-03-31.consolidated", "(310.00)", "-3100000000", source="ocr")
    assert not by_id(charts.build_charts(data), "net_profit.2025-03-31.consolidated").plotted


@pytest.mark.parametrize("status, words", [("not_found", "not found"), ("requires_review", "requires review"), ("conflicting", "conflicting")])
def test_a_field_that_is_not_extracted_is_not_plotted(status, words):
    data = rich()
    set_field(data, "revenue.2025-03-31.consolidated", "14,823.00", None, status=status)
    slot = by_id(charts.build_charts(data), "revenue.2025-03-31.consolidated")
    assert not slot.plotted and slot.note == f"not plotted: {words}"


@pytest.mark.parametrize("status, reason", [("requires_review", "period_mismatch"), ("conflicting", None)])
def test_a_field_that_keeps_its_value_but_is_not_extracted_is_not_plotted(status, reason):
    data = rich()
    set_field(data, "revenue.2025-03-31.consolidated", "14,823.00", "148230000000", status=status, reason=reason)  # the value is still there
    slot = by_id(charts.build_charts(data), "revenue.2025-03-31.consolidated")
    assert not slot.plotted and slot.note.startswith("not plotted: ")


def test_the_label_of_a_slot_names_the_page_the_field_was_read_on():
    data = rich()
    set_field(data, "revenue.2025-03-31.consolidated", "14,823.00", "148230000000", page=7)
    slot = by_id(charts.build_charts(data), "revenue.2025-03-31.consolidated")
    assert slot.label == "[SOURCE: p.7]"
    assert charts.traceability(charts.build_charts(data), memo_of(data), data, parser().parse) == []


def test_a_run_that_found_no_period_dates_still_gets_its_charts_with_the_role_as_the_caption():
    data = rich()
    for record in [*data["fields"], *data["derived_fields"]]:
        record["period_end"] = None
    for metric in data["metrics"]:
        metric["period_ends"] = []
    bars, dots = charts.build_charts(data)
    assert [s.caption for p in bars.panels for s in p.slots] == ["comparative", "current", "comparative", "current"]
    assert all(s.caption in ("comparative", "current") for p in dots.panels for s in p.slots)
    memo = memo_of(data)
    cs = charts.build_charts(data)
    assert check.problems(build_pdf(memo, cs), memo, cs, data) == []


def test_the_caption_is_the_period_end_and_the_role_or_the_role_alone():
    assert charts._slot_caption("2025-03-31", "current") == "2025-03-31 current" and charts._slot_caption(None, "current") == "current" and charts._slot_caption("", "comparative") == "comparative"


def test_a_missing_record_is_not_plotted():
    data = rich()
    data["fields"] = [r for r in data["fields"] if r["field_name"] != "revenue"]
    slot = charts.build_charts(data)[0].panels[0].slots[0]
    assert not slot.plotted and slot.note == "not plotted: not found"


def test_a_metric_that_is_defined_but_rests_on_an_input_that_is_not_verified_is_not_plotted():
    _, dots = charts.build_charts(rich())  # MET-05 has values here but ebit and interest expense are not found
    assert all(not s.plotted and s.note == "not plotted: an input is not verified" for s in dots.panels[1].slots)


def test_a_metric_whose_inputs_are_all_verified_is_plotted():
    _, dots = charts.build_charts(rich(inputs_for_coverage=True))
    assert [s.shown for s in dots.panels[1].slots] == ["7.25", "2.50"] and [s.height for s in dots.panels[1].slots] == [7.25, 2.5]


def test_a_metric_resting_on_a_value_read_by_ocr_is_not_plotted():
    data = rich(inputs_for_coverage=True)
    set_field(data, "ebit.2025-03-31.consolidated", "500.00", "5000000000", source="ocr")
    slot = by_id(charts.build_charts(data), "MET-05.2025-03-31")
    assert not slot.plotted and slot.note == "not plotted: an input is not verified"


def test_a_missing_metric_is_not_plotted():
    data = rich()
    data["metrics"] = [m for m in data["metrics"] if m["metric_id"] != "MET-03"]
    assert all(s.note == "not plotted: not defined" for s in charts.build_charts(data)[1].panels[0].slots)


def test_the_source_line_names_what_is_plotted_with_its_labels():
    bars, _ = charts.build_charts(rich(ocr_net_profit=True))
    assert bars.source_text() == (
        "Plotted: revenue.2024-03-31.consolidated [SOURCE: p.1]; revenue.2025-03-31.consolidated [SOURCE: p.1]; net_profit.2024-03-31.consolidated [SOURCE: p.1]"
    )


def test_the_text_a_chart_prints_has_its_title_names_captions_values_notes_and_source_line():
    bars, _ = charts.build_charts(rich(ocr_net_profit=True))
    text = charts.expected_text(bars).splitlines()
    assert text[0] == charts.TITLE_BARS and "Revenue" in text and "2025-03-31 current" in text
    assert "14,823.00" in text and "(INR crore)" in text  # the number, and its unit on a line of its own
    assert "not plotted: requires review" in text and text[-1] == bars.source_text()
    assert charts.charts_text(list(charts.build_charts(rich()))).startswith("Charts\n")


def test_a_displayed_string_is_split_into_its_number_and_its_unit():
    assert charts._split_unit("1,482.30 (INR crore)") == ("1,482.30", "(INR crore)")
    assert charts._split_unit("14,823,000,000 INR") == ("14,823,000,000 INR", None)
    assert charts._split_unit("nil (reported as a dash) (INR crore)") == ("nil", "(reported as a dash) (INR crore)")


# --- the criterion itself: no number in a chart that is not also in the memo -----------------------------------------------------------------------------


NUMBER = re.compile(r"\d[\d,.\-]*\d|\d")


@pytest.mark.parametrize("data", [golden(), rich(), rich(ocr_net_profit=True), rich(inputs_for_coverage=True)], ids=["golden", "rich", "rich-ocr", "rich-coverage"])
def test_every_number_a_chart_prints_is_also_in_the_memo_text(data):
    memo_text = check._memo_text(memo_of(data))
    for chart in charts.build_charts(data):
        for number in NUMBER.findall(charts.expected_text(chart)):
            assert number in memo_text, number


@pytest.mark.parametrize("data", [golden(), rich(), rich(ocr_net_profit=True), rich(inputs_for_coverage=True)], ids=["golden", "rich", "rich-ocr", "rich-coverage"])
def test_the_data_lists_pass_the_traceability_check_against_the_memo_and_the_results(data):
    assert charts.traceability(charts.build_charts(data), memo_of(data), data, parser().parse) == []


def tampered(chart_list, panel_index, chart_index, slot_index, **changes):
    chart_list = list(chart_list)
    chart = chart_list[chart_index]
    panel = chart.panels[panel_index]
    slot = dataclasses.replace(panel.slots[slot_index], **changes)
    panels = list(chart.panels)
    panels[panel_index] = dataclasses.replace(panel, slots=tuple(slot if i == slot_index else s for i, s in enumerate(panel.slots)))
    chart_list[chart_index] = dataclasses.replace(chart, panels=tuple(panels))
    return chart_list


def trace(chart_list, data):
    return charts.traceability(chart_list, memo_of(data), data, parser().parse)


def test_a_displayed_value_that_is_not_in_the_memos_row_is_found():
    data = rich()
    found = trace(tampered(charts.build_charts(data), 0, 0, 1, shown="14,832.00 (INR crore)"), data)
    assert found == ["chart 1, current slot of panel 1: no row of the memo has its ID, its value and its label"]


def test_a_label_that_is_not_in_the_memos_row_is_found():
    data = rich()
    assert any("no row of the memo" in p for p in trace(tampered(charts.build_charts(data), 0, 0, 1, label="[SOURCE: p.9]"), data))


def test_an_id_whose_row_has_another_value_is_found():
    data = rich()  # the value of revenue 2024 under the ID of revenue 2025
    assert any("no row of the memo" in p for p in trace(tampered(charts.build_charts(data), 0, 0, 1, shown="12,100.50 (INR crore)"), data))


def test_a_height_that_is_not_the_stored_value_is_found():
    data = rich()
    found = trace(tampered(charts.build_charts(data), 0, 0, 1, height=1.0), data)
    assert found == ["chart 1, current slot of panel 1: its height is not the stored value"]


def test_a_slot_that_is_not_plotted_has_nothing_to_trace():
    data = rich(ocr_net_profit=True)
    assert trace(tampered(charts.build_charts(data), 1, 0, 1, note="not plotted: whatever"), data) == []


def test_the_traceability_messages_never_quote_the_memo():
    data = rich()
    found = trace(tampered(charts.build_charts(data), 0, 0, 1, shown="SECRET 1 (INR crore)"), data)
    assert found and all("SECRET" not in p and "14,823" not in p for p in found)


# --- in the PDF -------------------------------------------------------------------------------------------------------------------------------------------


def report(data):
    memo = memo_of(data)
    cs = charts.build_charts(data)
    return memo, cs, build_pdf(memo, cs)


@pytest.mark.parametrize("data", [golden(), rich(), rich(ocr_net_profit=True), rich(inputs_for_coverage=True)], ids=["golden", "rich", "rich-ocr", "rich-coverage"])
def test_the_report_with_charts_passes_the_report_check(data):
    memo, cs, pdf = report(data)
    assert check.problems(pdf, memo, cs, data) == []


def test_the_charts_print_their_titles_values_and_source_lines():
    memo, cs, pdf = report(rich())
    bodies, _ = read_pages(pdf)
    text = re.sub(r"\s+", " ", " ".join(bodies))
    for chart in cs:
        assert chart.title in text
    for value in ("14,823.00", "12,100.50", "850.25", "(310.00)", "1.60", "1.65"):
        assert value in text
    assert "Plotted: revenue.2024-03-31.consolidated [SOURCE: p.1]" in text


def test_the_charts_sit_between_section_4_and_section_5():
    memo, cs, pdf = report(rich())
    text = "\n".join(read_pages(pdf)[0])
    assert text.index("4. Financial ratios") < text.index("Charts") < text.index("5. Potential risk indicators")


def test_the_chart_page_has_no_image_and_no_link():
    _, _, pdf = report(rich())
    assert b"/Subtype /Image" not in pdf and b"/URI" not in pdf and b"/Annots" not in pdf


def test_a_report_with_charts_is_byte_identical_twice():
    memo, cs, pdf = report(rich())
    assert build_pdf(memo, cs) == pdf


def test_charts_without_a_section_5_to_precede_are_a_render_error():
    memo = f"# Draft credit memo\n\n**Run ID:** `{RUN_ID}`  \n\n> **{DRAFT_STATEMENT}**\n\n## 1. Borrower overview\n\ntext\n"
    with pytest.raises(ReportError) as error:
        build_pdf(memo, charts.build_charts(golden()))
    assert error.value.reason == "render_error"


def test_charts_cannot_be_checked_without_the_results():
    memo, cs, pdf = report(golden())
    assert check.problems(pdf, memo, cs, None) == ["the charts cannot be checked without the results"]


def test_a_chart_number_that_is_not_in_the_data_list_that_was_checked_is_found():
    data = rich()
    memo = memo_of(data)
    honest = charts.build_charts(data)
    altered = tampered(honest, 0, 0, 1, shown="14,832.00 (INR crore)")
    pdf = build_pdf(memo, altered)  # the PDF prints a number the memo does not have
    found = check.problems(pdf, memo, honest, data)
    assert any(p.startswith("the text differs") for p in found)


def test_a_chart_label_that_is_not_expected_is_found():
    data = rich()
    memo, honest = memo_of(data), charts.build_charts(data)
    pdf = build_pdf(memo, tampered(honest, 0, 0, 1, label="[SOURCE: p.9]"))
    assert any(p.startswith("origin labels differ") for p in check.problems(pdf, memo, honest, data))


def test_charts_that_do_not_trace_to_the_memo_stop_the_report_in_the_worker():
    data = rich()
    memo = memo_of(golden())  # a memo that does not hold the values that the charts are built from
    outcome = make_report(memo, data)
    assert (outcome.status, outcome.reason) == ("failed", "check_failed") and outcome.pdf is None


def test_make_report_with_results_writes_the_report_with_charts():
    data = rich()
    memo, cs, pdf = report(data)
    outcome = make_report(memo, data)
    assert outcome.status == "written" and outcome.pdf == pdf


def test_a_character_the_font_lacks_in_a_chart_stops_the_build():
    data = rich()
    set_field(data, "revenue.2025-03-31.consolidated", "漢", "148230000000")
    with pytest.raises(ReportError) as error:
        build_pdf(memo_of(data), charts.build_charts(data))
    assert error.value.reason == "glyph_missing"


# --- drawing never breaks on odd values ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("values", [("0", "0"), ("-5000", "-9000"), ("1", "100000000000000"), ("7", None)], ids=["zero", "all-negative", "wide-range", "one-missing"])
def test_odd_values_are_drawn_without_error(values):
    data = rich()
    for role, value in zip(("2025", "2024"), values):
        record = set_field(data, f"revenue.{role}-03-31.consolidated", "5.00", value if value is not None else "0")
        if value is None:
            record.update(status="not_found", value=None)
    memo = memo_of(data)
    cs = charts.build_charts(data)
    assert check.problems(build_pdf(memo, cs), memo, cs, data) == []


def test_two_equal_ratios_and_one_ratio_alone_are_drawn():
    data = rich(inputs_for_coverage=True)
    for metric in data["metrics"]:
        if metric["id"].startswith("MET-03"):
            metric["value"] = "1.5"
        if metric["id"] == "MET-05.2024-03-31":
            metric.update(value=None, undefined_reason="missing_input")
    memo = memo_of(data)
    cs = charts.build_charts(data)
    assert check.problems(build_pdf(memo, cs), memo, cs, data) == []


def test_the_plain_helper_resolves_escapes_and_code_marks():
    assert plain(r"\(310.00\) (INR crore)") == "(310.00) (INR crore)" and plain("`a_b` c") == "a_b c"
