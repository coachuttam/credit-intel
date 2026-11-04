"""The tuning scorer end to end on a synthetic statement: fill the cache once, replay it offline, score it against full-field-set labels (Phase 7b)."""

import json
import subprocess
import sys

import pytest

import pipeline_fixture as fx
from credit_intel.evaluation.guard import MEMBERS, SendRefused, file_sha256
from credit_intel.evaluation.score import LabelsError, load_labels, main, replay
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import load_prompt
from credit_intel.llm.provider import FakeProvider

ROWS = [*fx.ROWS,
        ("Profit before tax", "", "352.70", "300.10"),
        ("Finance costs", "20", "38.50", "35.00"),
        ("Non-current borrowings", "16", "400.00", "350.00"),
        ("Current borrowings", "17", "150.00", "120.00")]  # fmt: skip
PRESENT = {  # field: (current, comparative) as printed, in crore, on page 1
    "current_assets": ("1,482.30", "1,356.75"), "current_liabilities": ("900.00", "850.00"), "total_equity": ("600.00", "500.00"),
    "profit_before_tax": ("352.70", "300.10"), "interest_expense": ("38.50", "35.00"),
    "borrowings_non_current": ("400.00", "350.00"), "borrowings_current": ("150.00", "120.00"),
}  # fmt: skip
ABSENT = ("revenue", "net_profit", "operating_profit", "current_maturities_long_term_borrowings")
END = {"current": "2025-03-31", "comparative": "2024-03-31"}


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n', encoding="utf-8")
    return path


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf", rows=ROWS)


def reply(pdf):
    data = json.loads(fx.good_response(pdf))
    data["fields"] += [
        fx.field(pdf, "profit_before_tax", "current", "352.70", "Profit before tax"), fx.field(pdf, "profit_before_tax", "comparative", "300.10", "Profit before tax"),
        fx.field(pdf, "interest_expense", "current", "38.50", "Finance costs"), fx.field(pdf, "interest_expense", "comparative", "35.00", "Finance costs"),
        fx.field(pdf, "borrowings_non_current", "current", "400.00", "Non-current borrowings"), fx.field(pdf, "borrowings_non_current", "comparative", "350.00", "Non-current borrowings"),
        fx.field(pdf, "borrowings_current", "current", "150.00", "Current borrowings"), fx.field(pdf, "borrowings_current", "comparative", "120.00", "Current borrowings"),
    ]  # fmt: skip
    return json.dumps(data)


def fill_cache(pdf, tmp_path, text=None):
    run_extraction(pdf, FakeProvider(script=[text or reply(pdf)]), fx.LLM.__class__(provider="fake", model_id="m", token_ceiling=1_000_000, max_output_tokens=2000),
                   cache_dir=tmp_path / ".cache" / "llm", prompt=load_prompt())  # fmt: skip


def labels_data(pdf, **over):
    entries = []
    for period, index in (("current", 0), ("comparative", 1)):
        for field, values in PRESENT.items():
            entries.append({"field": field, "period": period, "period_end": END[period], "printed": values[index], "scale": "crore", "currency": "INR", "page": 1})
        entries.append({"field": "total_borrowings", "period": period, "period_end": END[period], "currency": "INR",
                        "parts": [{"printed": PRESENT["borrowings_non_current"][index], "scale": "crore", "page": 1},
                                  {"printed": PRESENT["borrowings_current"][index], "scale": "crore", "page": 1}]})  # fmt: skip
        entries += [{"field": f, "period": period, "absent": True} for f in ABSENT]
    data = {"document_id": "R9", "sha256": file_sha256(pdf), "basis": "consolidated", "entries": entries}
    data.update(over)
    return data


def records(tmp_path, pdf, group="tuning"):
    path = tmp_path / "assignments.jsonl"
    path.write_text(json.dumps(dict(zip(MEMBERS, ("R9", file_sha256(pdf), group, "2026-10-24", "assigned", None, None), strict=True))) + "\n", encoding="utf-8")
    return path


def labels_file(tmp_path, pdf, **over):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(labels_data(pdf, **over)), encoding="utf-8")
    return path


def settings_for(config):
    from credit_intel.config import load_llm_settings

    return load_llm_settings(config, {})


def test_a_cached_run_scores_every_labelled_entry_and_the_absent_fields_are_correct(pdf, tmp_path, config):
    fill_cache(pdf, tmp_path)

    report = replay(pdf, load_labels(labels_file(tmp_path, pdf)), assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert report["replayed"] and report["set"] == "tuning" and report["counts"] == {
        "sc01": {"match": 16, "of": 16}, "sc02": {"extracted_for_absent": 0, "value_differs": 0},
        "sc03": {"correct": 8, "undecided": 0, "of": 8}, "sc04": {"passed": 14, "of": 14}, "sc05": {"page_agrees": 14, "of": 14},
    }  # fmt: skip


def test_a_label_that_differs_from_the_extraction_is_a_mismatch_and_a_wrongly_absent_field_is_a_candidate(pdf, tmp_path, config):
    fill_cache(pdf, tmp_path)
    data = labels_data(pdf)
    for e in data["entries"]:
        if (e["field"], e["period"]) == ("total_equity", "current"):
            e["printed"] = "601.00"
        if (e["field"], e["period"]) == ("current_liabilities", "current"):
            e.clear()
            e.update({"field": "current_liabilities", "period": "current", "absent": True})
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    report = replay(pdf, load_labels(path), assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert report["counts"]["sc01"] == {"match": 14, "of": 15} and report["counts"]["sc02"] == {"extracted_for_absent": 1, "value_differs": 1}
    assert report["counts"]["sc03"]["of"] == 9 and report["counts"]["sc03"]["correct"] == 8


def test_an_empty_cache_is_a_failure_to_replay_and_nothing_is_sent(pdf, tmp_path, config):
    report = replay(pdf, load_labels(labels_file(tmp_path, pdf)), assignments=records(tmp_path, pdf), cache_dir=tmp_path / "empty", llm=settings_for(config))

    assert report == {"set": "tuning", "document_id": "R9", "replayed": False, "reason": "cache_miss"}


def test_a_held_out_document_is_refused_before_anything_is_read(pdf, tmp_path, config):
    labels = load_labels(labels_file(tmp_path, pdf))

    with pytest.raises(SendRefused, match="held out"):
        replay(pdf, labels, assignments=records(tmp_path, pdf, group="held_out"), llm=settings_for(config))


def test_labels_written_for_another_document_are_refused(pdf, tmp_path, config):
    for over in ({"document_id": "R2"}, {"sha256": "b" * 64}):
        with pytest.raises(LabelsError, match="not written for this document"):
            replay(pdf, load_labels(labels_file(tmp_path, pdf, **over)), assignments=records(tmp_path, pdf), llm=settings_for(config))


def run_main(capsys, *argv):
    code = main([*map(str, argv)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_command_prints_counts_only_with_the_report_date_and_exits_0(pdf, tmp_path, config, capsys):
    fill_cache(pdf, tmp_path)
    code, out, err = run_main(capsys, "--report", pdf, labels_file(tmp_path, pdf), "--assignments", records(tmp_path, pdf), "--config", config)

    last = json.loads(out.strip().splitlines()[-1].removeprefix("score: "))
    assert code == 0 and err == "" and last["fractions"]["sc01"] == "16/16" and last["documents"] == ["R9"] and last["tuning_documents_on_record"] == ["R9"]
    assert last["set"] == "tuning" and len(last["date"]) == 10 and "assignments_commit" in last
    for forbidden in ("352.70", "38.50", "400.00", "Profit before tax", "Finance costs", "Acme", "statement.pdf", str(tmp_path)):
        assert forbidden not in out


def test_the_command_exits_1_when_a_document_could_not_be_replayed(pdf, tmp_path, config, capsys):
    code, out, _ = run_main(capsys, "--report", pdf, labels_file(tmp_path, pdf), "--assignments", records(tmp_path, pdf), "--config", config)

    assert code == 1 and '"not_replayed": ["R9"]' in out


def test_a_refusal_or_a_bad_labels_file_exits_2_and_says_nothing_about_values(pdf, tmp_path, config, capsys):
    fill_cache(pdf, tmp_path)
    code, out, err = run_main(capsys, "--report", pdf, labels_file(tmp_path, pdf), "--assignments", records(tmp_path, pdf, group="held_out"), "--config", config)
    bad = tmp_path / "bad.json"
    bad.write_text('{"document_id": "R9"}', encoding="utf-8")
    code2, out2, err2 = run_main(capsys, "--report", pdf, bad, "--assignments", records(tmp_path, pdf), "--config", config)

    assert (code, code2) == (2, 2) and "held out" in err and "labels file" in err2 and out == out2 == ""


def test_check_labels_validates_a_file_without_a_document(pdf, tmp_path, capsys):
    code, out, _ = run_main(capsys, "--check-labels", labels_file(tmp_path, pdf))
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    code2, _, err2 = run_main(capsys, "--check-labels", bad)

    assert code == 0 and '"present": 16' in out and '"absent": 8' in out and "352.70" not in out
    assert code2 == 2 and "score: refused" in err2


def test_the_command_needs_something_to_do(capsys):
    with pytest.raises(SystemExit) as stop:
        main([])

    assert stop.value.code == 2


def test_the_module_runs_as_a_command(tmp_path):
    done = subprocess.run([sys.executable, "-m", "credit_intel.evaluation.score", "--check-labels", str(tmp_path / "none.json")], capture_output=True, cwd=tmp_path)

    assert done.returncode == 2 and b"score: refused" in done.stderr and done.stdout == b""


# --- stage attribution and the label summary (Phase 7c) ---------------------------------------------------------------------------------------


def test_a_field_the_model_left_out_is_attributed_to_the_model_and_a_row_the_code_reads_is_not(pdf, tmp_path, config):
    data = json.loads(reply(pdf))
    data["fields"] = [f for f in data["fields"] if not (f["field_name"] == "profit_before_tax" or (f["field_name"] == "borrowings_current" and f["period_role"] == "current"))]
    fill_cache(pdf, tmp_path, json.dumps(data))

    report = replay(pdf, load_labels(labels_file(tmp_path, pdf)), assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    stages = {(e["field"], e["period"]): (e["stage"], e["stage_reason"]) for e in report["entries"] if e["stage"]}
    assert stages[("profit_before_tax", "current")] == ("not_proposed", None) and stages[("profit_before_tax", "comparative")] == ("not_proposed", None)
    assert report["counts"]["sc01"]["match"] == report["counts"]["sc01"]["of"] - len(stages)
    assert report["stages"] == {"not_proposed": 2}  # the omitted current borrowings row is read by the code (v0.4.39), so the total still derives


def test_check_labels_counts_the_features_and_row_labels_it_found(pdf, tmp_path, capsys):
    data = labels_data(pdf)
    data["features"] = {"title_names_basis": True, "period_header": "two_year_columns"}
    next(e for e in data["entries"] if e["field"] == "current_assets" and e["period"] == "current")["row_label"] = "Total current assets"
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    code, out, _ = run_main(capsys, "--check-labels", path)

    assert code == 0 and '"features": 2' in out and '"row_labels": 1' in out and "Total current assets" not in out
