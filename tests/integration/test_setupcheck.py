"""The model-free setup check of a reference or labels file against its own document (Phase 7c, S-4). Synthetic documents only."""

import json
import subprocess
import sys
from decimal import Decimal

import pytest

import pipeline_fixture as fx
from credit_intel.config import load_llm_settings
from credit_intel.evaluation.guard import MEMBERS, SendRefused, file_sha256
from credit_intel.evaluation.setupcheck import SetupCheckError, _figure, _spaced, _items, _magnitudes, check_setup, main, setup_from_gate_reference, setup_from_labels

ROWS = [*fx.ROWS,
        ("Profit before tax", "", "352.70", "300.10"),
        ("Finance costs", "20", "38.50", "35.00"),
        ("Non-current borrowings", "16", "400.00", "350.00"),
        ("Current borrowings", "17", "150.00", "120.00")]  # fmt: skip
END = {"current": "2025-03-31", "comparative": "2024-03-31"}
PRINTED = {"profit_before_tax": ("352.70", "300.10"), "interest_expense": ("38.50", "35.00")}


@pytest.fixture
def llm(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n', encoding="utf-8")
    return load_llm_settings(path, {})


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf", rows=ROWS)


def reference_data(pdf, page=1, printed=None, **options):
    printed = printed or {}
    entries = []
    for period, index in (("current", 0), ("comparative", 1)):
        for field in PRINTED:
            entries.append({"field": field, "period": period, "period_end": END[period], "page": page, "printed": printed.get((field, period), PRINTED[field][index]), "scale": "crore"})
        nc, cur = (("400.00", "150.00"), ("350.00", "120.00"))[index]
        entries.append({"field": "total_borrowings", "period": period, "period_end": END[period],
                        "parts": [{"printed": nc, "scale": "crore", "page": page}, {"printed": cur, "scale": "crore", "page": page}]})  # fmt: skip
    head = {"document_id": "R9", "sha256": file_sha256(pdf), "basis": "consolidated", **options}
    return {**head, "entries": entries}


def write(tmp_path, data, name="ref.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def records(tmp_path, pdf, group="tuning"):
    path = tmp_path / "assignments.jsonl"
    path.write_text(json.dumps(dict(zip(MEMBERS, ("R9", file_sha256(pdf), group, "2026-10-24", "assigned", None, None), strict=True))) + "\n", encoding="utf-8")
    return path


def ledger(tmp_path, pdf=None):
    """A held-out ledger (none yet, or with one used document), in a file of its own."""
    from credit_intel.evaluation.heldout import LEDGER_MEMBERS

    path = tmp_path / ("ledger.jsonl" if pdf is None else "ledger_used.jsonl")
    path.write_text("" if pdf is None else "".join(json.dumps(dict(zip(LEDGER_MEMBERS, ("R9", file_sha256(pdf), "H-1", event, "2026-11-04T00:00:00Z", "c" * 40, "a" * 64), strict=True)), separators=(",", ":")) + "\n" for event in ("started", "completed")), encoding="utf-8")
    return path


def check(tmp_path, pdf, llm, data, group="tuning", used=False):
    return check_setup(setup_from_gate_reference(write(tmp_path, data)), pdf, llm, records(tmp_path, pdf, group), ledger(tmp_path, pdf if used else None))


# --- the parts ---------------------------------------------------------------------------------------------------------------------------


def test_magnitudes_read_the_figures_of_a_page_whatever_their_sign_or_punctuation():
    assert _magnitudes("Profit (987.60) and 1,234.50, and -5 then Rs. 7.25 - nil") >= {Decimal("987.60"), Decimal("1234.50"), Decimal(5), Decimal("7.25"), Decimal(0)}
    assert Decimal("999") not in _magnitudes("Profit 998 and 1000")


@pytest.mark.parametrize(
    ("printed", "magnitude"),
    [("1,234.50", Decimal("1234.50")), ("(987.60)", Decimal("987.60")), ("$ 1,234", Decimal(1234)), ("$1,234", Decimal(1234)), ("-5", Decimal(5)), ("nil", Decimal(0)), ("-", Decimal(0)), ("1 234", Decimal(1234)), ("@ 7", Decimal(7))],
)
def test_the_magnitude_of_a_printed_figure_ignores_its_sign_a_currency_symbol_and_spaces(printed, magnitude):
    assert _figure(printed) == magnitude


@pytest.mark.parametrize(
    ("printed", "text", "expected"),
    [
        ("12,345", "Total 12,345 6,000", True),
        ("12,345", "Total 12, 345 6,000", True),  # split by a gap in the text layer
        ("12,345", "Total 1 2,345 6,000", True),
        ("12,345", "Total 12,  345", False),  # two spaces are not one gap
        ("12,345", "Total 112,345", False),  # inside a longer figure
        ("12,345", "Total 12,3456", False),
        ("12,345", "Total 12,345.50", False),
        ("12,345", "Total 6,000 12,34 5", True),  # a gap before the last digit is still one gap
        ("12,345", "Total 1 2,34 5", False),  # two gaps
        ("(987.60)", "Profit (987.60)", True),
        ("", "anything", False),
    ],
)
def test_a_figure_split_by_one_space_is_found_but_not_inside_a_longer_figure(printed, text, expected):
    assert _spaced(printed, text) is expected


@pytest.mark.parametrize("printed", ["", "abc", "12 34 x"])
def test_a_printed_text_that_is_not_a_figure_has_no_magnitude(printed):
    assert _figure(printed) is None


def test_the_items_of_a_file_are_its_printed_figures_with_their_pages_and_parts_are_separate_items():
    entries = [
        {"field": "revenue", "period": "current", "printed": "1", "page": 3},
        {"field": "revenue", "period": "comparative", "printed": "2", "pages": [9, 4, 9]},
        {"field": "total_borrowings", "period": "current", "parts": [{"printed": "4", "page": 5}, {"printed": "6", "page": 6}]},
        {"field": "total_borrowings", "period": "comparative", "presented": False},
        {"field": "net_profit", "period": "current", "absent": True},
    ]

    assert [(i.printed, i.pages) for i in _items(entries)] == [("1", (3,)), ("2", (4, 9)), ("4", (5,)), ("6", (6,))]


# --- a titled document ----------------------------------------------------------------------------------------------------------------------


def test_a_reference_that_matches_its_document_is_ready_and_the_report_holds_only_booleans_and_counts(pdf, tmp_path, llm):
    report = check(tmp_path, pdf, llm, reference_data(pdf))

    assert report["ready"] and report["values"] == 8 and report["figure_found_on_labelled_page"] == 8 and report["printed_text_found_literally"] == 8
    assert report["sha256_matches"] and report["basis_gate_passes"] and report["every_labelled_page_is_sent"] and report["candidate_pages_sent"] == 1
    text = json.dumps(report)
    for forbidden in ("352.70", "400.00", "Profit before tax", "statement.pdf", str(tmp_path)):
        assert forbidden not in text


def test_a_figure_that_is_not_on_its_labelled_page_is_found_and_the_reference_is_not_ready(pdf, tmp_path, llm):
    report = check(tmp_path, pdf, llm, reference_data(pdf, printed={("profit_before_tax", "current"): "999.99"}))

    assert not report["ready"] and report["figure_found_on_labelled_page"] == 7 and report["printed_text_found_literally"] == 7


def test_a_page_outside_the_document_is_found(pdf, tmp_path, llm):
    report = check(tmp_path, pdf, llm, reference_data(pdf, page=5))

    assert not report["ready"] and report["labelled_pages_in_document"] is False and report["figure_found_on_labelled_page"] == 0


def test_a_page_range_that_leaves_out_a_labelled_page_is_found(tmp_path, llm):
    two = fx.balance_sheet_pdf(tmp_path / "two.pdf", rows=ROWS, narrative_page="The directors report.")
    report = check(tmp_path, two, llm, reference_data(two, page=1, pages="2"))

    assert not report["ready"] and report["page_range_covers_labelled_pages"] is False


def test_a_labelled_page_that_the_run_would_not_send_is_found(tmp_path, llm):
    two = fx.balance_sheet_pdf(tmp_path / "two.pdf", rows=ROWS, narrative_page="The directors report. Profit before tax 352.70 300.10")
    report = check(tmp_path, two, llm, reference_data(two, page=2, pages="1"))

    assert not report["ready"] and report["page_range_covers_labelled_pages"] is False and report["every_labelled_page_is_sent"] is False


def test_a_page_that_is_not_the_statement_is_found(tmp_path, llm):
    other = fx.blank_text_pdf(tmp_path / "other.pdf")
    report = check(tmp_path, other, llm, reference_data(other))

    assert not report["ready"] and report["figure_found_on_labelled_page"] == 0 and report["printed_text_found_literally"] == 0
    assert report["basis_gate_passes"] is False and report["basis_gate_error"] == "E-EXTRACT-NO-STATEMENT-PAGES" and report["every_labelled_page_is_sent"] is False


# --- a document whose titles name no basis ----------------------------------------------------------------------------------------------


@pytest.fixture
def untitled(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "untitled.pdf", rows=ROWS, title="Balance Sheet")


def test_without_the_assertion_the_basis_gate_stops_an_untitled_document_and_with_it_the_reference_is_ready(untitled, tmp_path, llm):
    without = check(tmp_path, untitled, llm, reference_data(untitled, pages="1"))
    with_assertion = check(tmp_path, untitled, llm, reference_data(untitled, pages="1", assert_basis="consolidated"))

    assert not without["ready"] and without["basis_gate_passes"] is False and without["basis_gate_error"] == "E-EXTRACT-BASIS-UNAVAILABLE"
    assert with_assertion["ready"] and with_assertion["basis_gate_passes"] and with_assertion["every_labelled_page_is_sent"]


def test_a_document_run_by_the_locator_alone_is_checked_the_same_way(pdf, tmp_path, llm):
    report = check(tmp_path, pdf, llm, reference_data(pdf))

    assert report["locator"] == "keywords" and report["ready"]


# --- labels files, refusals, the command -------------------------------------------------------------------------------------------------------


def test_a_labels_file_of_the_scorer_is_read_too(pdf, tmp_path, llm):
    from test_score_run import labels_data  # the scorer's own builder of a 24-entry file

    path = write(tmp_path, labels_data(pdf), "labels.json")
    report = check_setup(setup_from_labels(path), pdf, llm, records(tmp_path, pdf), ledger(tmp_path))

    assert report["values"] == 7 * 2 + 4 and report["ready"]


def test_an_unrecorded_document_or_another_documents_file_is_refused(pdf, tmp_path, llm):
    data = reference_data(pdf)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(SendRefused, match="not on the assignment record"):
        check_setup(setup_from_gate_reference(write(tmp_path, data)), pdf, llm, empty, ledger(tmp_path))
    with pytest.raises(SetupCheckError, match="not written for this document"):
        check(tmp_path, pdf, llm, {**data, "document_id": "R2"})


# --- a held-out document that no round has used (the owner's decision of 2026-11-05) ----------------------------------------------------------------


def test_an_unused_held_out_document_may_be_checked_before_its_one_shot_and_the_report_says_so(pdf, tmp_path, llm):
    report = check(tmp_path, pdf, llm, reference_data(pdf), group="held_out")

    assert report["set"] == "held_out" and report["pre_run_setup_check"] is True and report["ready"] is True
    text = json.dumps(report)
    for forbidden in ("352.70", "400.00", "Profit before tax", "statement.pdf", str(tmp_path)):
        assert forbidden not in text


def test_a_tuning_document_is_not_marked_as_a_pre_run_check(pdf, tmp_path, llm):
    assert check(tmp_path, pdf, llm, reference_data(pdf))["pre_run_setup_check"] is False


def test_a_held_out_document_that_a_round_has_used_stays_closed(pdf, tmp_path, llm):
    with pytest.raises(SendRefused, match="a round has used it: it stays closed"):
        check(tmp_path, pdf, llm, reference_data(pdf), group="held_out", used=True)


def test_a_released_held_out_document_may_be_checked_and_one_used_again_after_its_release_is_closed(pdf, tmp_path, llm):
    from credit_intel.evaluation.ledger import LEDGER_MEMBERS, RELEASE_MEMBERS

    sha = file_sha256(pdf)
    base = ("R9", sha, "H-1", "{}", "2026-11-04T00:00:00Z", "c" * 40, "a" * 64)

    def lines(*events):
        out = []
        for event in events:
            members = RELEASE_MEMBERS if event == "released" else LEDGER_MEMBERS
            values = [event if v == "{}" else v for v in base] + (["stopped before any page was read"] if event == "released" else [])
            out.append(json.dumps(dict(zip(members, values, strict=True)), separators=(",", ":")))
        return "\n".join(out) + "\n"

    path = tmp_path / "released.jsonl"
    path.write_text(lines("started", "completed", "released"), encoding="utf-8")
    setup = setup_from_gate_reference(write(tmp_path, reference_data(pdf)))
    assert check_setup(setup, pdf, llm, records(tmp_path, pdf, "held_out"), path)["pre_run_setup_check"] is True
    path.write_text(lines("started", "completed", "released", "started"), encoding="utf-8")
    with pytest.raises(SendRefused, match="stays closed"):
        check_setup(setup, pdf, llm, records(tmp_path, pdf, "held_out"), path)


def test_a_used_tuning_sha_in_the_ledger_does_not_close_a_tuning_document(pdf, tmp_path, llm):
    assert check(tmp_path, pdf, llm, reference_data(pdf), used=True)["ready"] is True


@pytest.mark.parametrize("damage", ["not json\n", '{"document_id":"R9"}\n', "\r\n", '{"a":1}'])
def test_an_unreadable_ledger_refuses_everything(pdf, tmp_path, llm, damage):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(damage, encoding="utf-8")
    setup = setup_from_gate_reference(write(tmp_path, reference_data(pdf)))
    for group in ("tuning", "held_out"):
        with pytest.raises(SendRefused, match="cannot be read"):
            check_setup(setup, pdf, llm, records(tmp_path, pdf, group), bad)


@pytest.mark.parametrize("damage", ["not json\n", '{"document_id":"R9"}\n'])
def test_an_unreadable_assignment_record_refuses_everything(pdf, tmp_path, llm, damage):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(damage, encoding="utf-8")
    with pytest.raises(SendRefused, match="cannot be read"):
        check_setup(setup_from_gate_reference(write(tmp_path, reference_data(pdf))), pdf, llm, bad, ledger(tmp_path))


def test_a_missing_assignment_record_means_the_document_is_not_on_it(pdf, tmp_path, llm):
    with pytest.raises(SendRefused, match="not on the assignment record"):
        check_setup(setup_from_gate_reference(write(tmp_path, reference_data(pdf))), pdf, llm, tmp_path / "none.jsonl", ledger(tmp_path))


def test_the_dry_run_still_refuses_a_held_out_document_unless_the_setup_check_asks(pdf, tmp_path, llm):
    from credit_intel.evaluation.dry_run import dry_run

    held = records(tmp_path, pdf, "held_out")
    with pytest.raises(SendRefused, match="held out"):
        dry_run(pdf, llm, assignments=held)
    assert dry_run(pdf, llm, assignments=held, allow_unused_held_out=True)["set"] == "held_out"


def test_a_bad_file_is_refused_without_a_value(pdf, tmp_path):
    bad = write(tmp_path, {"document_id": "R9"}, "bad.json")
    with pytest.raises(SetupCheckError):
        setup_from_gate_reference(bad)
    with pytest.raises(SetupCheckError):
        setup_from_labels(bad)


def run_main(capsys, *argv):
    code = main([*map(str, argv)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_command_exits_0_when_ready_1_when_not_and_2_on_a_refusal(pdf, tmp_path, capsys):
    good = write(tmp_path, reference_data(pdf), "good.json")
    bad = write(tmp_path, reference_data(pdf, printed={("profit_before_tax", "current"): "999.99"}), "bad.json")
    record, empty = records(tmp_path, pdf), ledger(tmp_path)

    code0, out0, err0 = run_main(capsys, "--gate-reference", pdf, good, "--assignments", record, "--ledger", empty)
    code1, out1, _ = run_main(capsys, "--gate-reference", pdf, bad, "--assignments", record, "--ledger", empty)
    code2, out2, err2 = run_main(capsys, "--gate-reference", pdf, good, "--assignments", records(tmp_path, pdf, "held_out"), "--ledger", ledger(tmp_path, pdf))
    code3, out3, _ = run_main(capsys, "--gate-reference", pdf, good, "--assignments", records(tmp_path, pdf, "held_out"), "--ledger", empty)

    assert (code0, code1, code2, code3) == (0, 1, 2, 0) and '"ready": true' in out0 and err0 == "" and '"ready": false' in out1
    assert out2 == "" and "stays closed" in err2 and '"pre_run_setup_check": true' in out3
    for forbidden in ("352.70", "999.99", "Profit", str(tmp_path)):
        assert forbidden not in out0 + out1


def test_the_command_needs_something_to_do_and_runs_as_a_module(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        main([])
    done = subprocess.run([sys.executable, "-m", "credit_intel.evaluation.setupcheck", "--labels", str(tmp_path / "x.pdf"), str(tmp_path / "none.json")], capture_output=True, cwd=tmp_path)

    assert stop.value.code == 2 and done.returncode == 2 and b"setupcheck: refused" in done.stderr and done.stdout == b""


# --- each condition of 'ready' on its own (the others true) ---------------------------------------------------------------------------------


def manual(pdf, items, **options):
    from credit_intel.evaluation.setupcheck import Item, Setup

    return Setup("R9", file_sha256(pdf), "consolidated", options.get("pages"), options.get("assert_basis"), tuple(Item(printed, pages) for printed, pages in items))


def run(tmp_path, pdf, llm, setup):
    return check_setup(setup, pdf, llm, records(tmp_path, pdf), ledger(tmp_path))


def test_a_range_that_is_wider_than_the_labelled_pages_still_covers_them(tmp_path, llm):
    two = fx.balance_sheet_pdf(tmp_path / "two.pdf", rows=ROWS, narrative_page="The directors report.")
    report = run(tmp_path, two, llm, manual(two, [("352.70", (1,))], pages="1-2"))

    assert report["page_range_covers_labelled_pages"] is True and report["ready"] is True


def test_a_labelled_page_the_locator_would_not_send_alone_makes_the_reference_not_ready(tmp_path, llm):
    two = fx.balance_sheet_pdf(tmp_path / "two.pdf", rows=ROWS, narrative_page="The directors report. Profit before tax 352.70 300.10")
    report = run(tmp_path, two, llm, manual(two, [("352.70", (2,))]))

    assert report["figure_found_on_labelled_page"] == 1 and report["page_range_covers_labelled_pages"] and report["basis_gate_passes"]
    assert report["labelled_pages_in_document"] and report["values_on_text_layer_pages"] == 1
    assert report["every_labelled_page_is_sent"] is False and report["ready"] is False


def test_a_reference_with_nothing_labelled_is_not_ready(pdf, tmp_path, llm):
    report = run(tmp_path, pdf, llm, manual(pdf, []))

    assert report["values"] == 0 and report["every_labelled_page_is_sent"] is False and report["ready"] is False


def test_a_value_labelled_on_a_page_that_is_not_in_the_document_is_not_ready_even_if_found_on_another(pdf, tmp_path, llm):
    report = run(tmp_path, pdf, llm, manual(pdf, [("352.70", (1, 9))]))

    assert report["figure_found_on_labelled_page"] == 1 and report["labelled_pages_in_document"] is False and report["ready"] is False


def test_a_value_labelled_on_a_page_with_no_text_layer_is_not_ready_even_if_found_on_another(tmp_path, llm):
    from reportlab.pdfgen import canvas

    path = tmp_path / "gap.pdf"
    fx.balance_sheet_pdf(tmp_path / "base.pdf", rows=ROWS)
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.setFont("Helvetica", 10)
    for number, line in enumerate(["Acme Industries Limited", "Consolidated Balance Sheet", "(Rs. in crore)", "As at 31 March 2025 31 March 2024", "Profit before tax 352.70 300.10"]):
        pdf.drawString(72, 780 - 15 * number, line)
    pdf.showPage()
    pdf.showPage()  # a second page with nothing drawn on it
    pdf.save()
    report = run(tmp_path, path, llm, manual(path, [("352.70", (1, 2))]))

    assert report["figure_found_on_labelled_page"] == 1 and report["values_on_text_layer_pages"] == 0 and report["ready"] is False


def test_a_figure_split_by_a_gap_is_found_but_not_as_the_exact_printed_text(tmp_path, llm):
    split = fx.split_figure_pdf(tmp_path / "split.pdf", [("Profit before tax", ["35", "2.70"], ["300.10"]), ("Finance costs", ["38.50"], ["35.00"])], heading="Consolidated Statement of Profit and Loss")
    report = run(tmp_path, split, llm, manual(split, [("352.70", (1,)), ("38.50", (1,))]))

    assert report["figure_found_on_labelled_page"] == 2 and report["printed_text_found_literally"] == 1


def test_the_report_says_it_is_for_a_tuning_document_and_counts_the_pages_dropped_for_an_unknown_basis(pdf, tmp_path, llm, monkeypatch):
    from credit_intel.evaluation import setupcheck

    real = setupcheck.dry_run
    monkeypatch.setattr(setupcheck, "dry_run", lambda *a, **k: {**real(*a, **k), "removed_for_unknown_basis": [3, 4]})
    report = run(tmp_path, pdf, llm, manual(pdf, [("352.70", (1,))]))

    assert report["set"] == "tuning" and report["pages_dropped_for_unknown_basis"] == 2
