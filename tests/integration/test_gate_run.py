"""The gate end to end on a synthetic statement: fill the cache once, replay it offline, compare with a reference (B-275; Phase 5 Part 2 preparation)."""

import json
import sys
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.evaluation import gate
from credit_intel.evaluation.gate import GateReferenceError, load_reference, main, replay
from credit_intel.evaluation.guard import MEMBERS, SendRefused, file_sha256
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import StatementBasis

ROWS = [*fx.ROWS,
        ("Profit before tax", "", "352.70", "300.10"),
        ("Finance costs", "20", "38.50", "35.00"),
        ("Non-current borrowings", "16", "400.00", "350.00"),
        ("Current borrowings", "17", "150.00", "120.00")]  # fmt: skip


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


def reply(pdf, **changes):
    data = json.loads(fx.good_response(pdf))
    data["fields"] += [
        fx.field(pdf, "profit_before_tax", "current", "352.70", "Profit before tax"), fx.field(pdf, "profit_before_tax", "comparative", "300.10", "Profit before tax"),
        fx.field(pdf, "interest_expense", "current", "38.50", "Finance costs"), fx.field(pdf, "interest_expense", "comparative", "35.00", "Finance costs"),
        fx.field(pdf, "borrowings_non_current", "current", "400.00", "Non-current borrowings"), fx.field(pdf, "borrowings_non_current", "comparative", "350.00", "Non-current borrowings"),
        fx.field(pdf, "borrowings_current", "current", "150.00", "Current borrowings"), fx.field(pdf, "borrowings_current", "comparative", "120.00", "Current borrowings"),
    ]  # fmt: skip
    return json.dumps(data)


def fill_cache(pdf, tmp_path, text=None):
    from credit_intel.extraction.prompt import load_prompt

    run_extraction(pdf, FakeProvider(script=[text or reply(pdf)]), fx.LLM.__class__(provider="fake", model_id="m", token_ceiling=1_000_000, max_output_tokens=2000),
                   cache_dir=tmp_path / ".cache" / "llm", prompt=load_prompt())  # fmt: skip


def reference_data(pdf, group="tuning", total="parts", **over):
    def total_entry(period, end, nc, cur):
        if total == "reported":
            return {"field": "total_borrowings", "period": period, "period_end": end, "page": 1, "printed": "550.00" if period == "current" else "470.00", "scale": "crore"}
        return {"field": "total_borrowings", "period": period, "period_end": end,
                "parts": [{"printed": nc, "scale": "crore", "page": 1}, {"printed": cur, "scale": "crore", "page": 1}]}  # fmt: skip

    data = {
        "document_id": "R9", "sha256": file_sha256(pdf), "basis": "consolidated",
        "entries": [
            {"field": "profit_before_tax", "period": "current", "period_end": "2025-03-31", "page": 1, "printed": "352.70", "scale": "crore"},
            {"field": "profit_before_tax", "period": "comparative", "period_end": "2024-03-31", "page": 1, "printed": "300.10", "scale": "crore"},
            {"field": "interest_expense", "period": "current", "period_end": "2025-03-31", "page": 1, "printed": "38.50", "scale": "crore"},
            {"field": "interest_expense", "period": "comparative", "period_end": "2024-03-31", "page": 1, "printed": "35.00", "scale": "crore"},
            total_entry("current", "2025-03-31", "400.00", "150.00"), total_entry("comparative", "2024-03-31", "350.00", "120.00"),
        ],
    }  # fmt: skip
    data.update(over)
    return data


def records(tmp_path, pdf, group="tuning", extra=()):
    path = tmp_path / "assignments.jsonl"
    rows = [("R9", file_sha256(pdf), group), *extra]
    path.write_text("\n".join(json.dumps(dict(zip(MEMBERS, (d, s, g, "2026-10-24", "assigned", None, None), strict=True))) for d, s, g in rows) + "\n", encoding="utf-8")
    return path


def reference_file(tmp_path, pdf, **kw):
    path = tmp_path / "ref.json"
    path.write_text(json.dumps(reference_data(pdf, **kw)), encoding="utf-8")
    return path


def settings_for(config):
    from credit_intel.config import load_llm_settings

    return load_llm_settings(config, {})


def test_a_cached_run_that_extracts_all_six_values_passes_with_a_derived_total(pdf, tmp_path, config):
    fill_cache(pdf, tmp_path)

    report = replay(pdf, load_reference(reference_file(tmp_path, pdf)), assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert report["passed"] and report["counts"] == {"match": 6, "mismatch": 0, "missing": 0}
    assert {e["origin"] for e in report["entries"] if e["field"] == "total_borrowings"} == {"derived"}


def test_a_reported_total_is_compared_by_the_same_rule(pdf, tmp_path, config):
    text = json.loads(reply(pdf))
    text["fields"].remove(next(f for f in text["fields"] if f["field_name"] == "borrowings_current" and f["period_role"] == "current"))  # the model omits it; the code reads the row (v0.4.39)
    fill_cache(pdf, tmp_path, json.dumps(text))

    report = replay(pdf, load_reference(reference_file(tmp_path, pdf, total="reported")), assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert report["passed"] and report["counts"] == {"match": 6, "mismatch": 0, "missing": 0}


def test_an_empty_cache_is_a_failure_to_replay_and_nothing_is_sent(pdf, tmp_path, config):
    report = replay(pdf, load_reference(reference_file(tmp_path, pdf)), assignments=records(tmp_path, pdf), cache_dir=tmp_path / "empty", llm=settings_for(config))

    assert report["replayed"] is False and report["passed"] is False and report["reason"] == "cache_miss" and report["counts"]["missing"] == 6


def test_a_reference_value_that_differs_from_the_extraction_fails_the_gate(pdf, tmp_path, config):
    fill_cache(pdf, tmp_path)
    data = reference_data(pdf)
    data["entries"][0]["printed"] = "352.71"
    path = tmp_path / "ref.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    report = replay(pdf, load_reference(path), assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert not report["passed"] and report["counts"]["mismatch"] == 1


def test_a_missing_value_in_the_model_reply_is_missing_not_a_pass(pdf, tmp_path, config):
    data = json.loads(reply(pdf))
    data["fields"] = [f for f in data["fields"] if f["field_name"] != "interest_expense"]
    fill_cache(pdf, tmp_path, json.dumps(data))

    report = replay(pdf, load_reference(reference_file(tmp_path, pdf)), assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert not report["passed"] and report["counts"] == {"match": 4, "mismatch": 0, "missing": 2}


def test_a_stopped_run_is_reported_as_missing_with_the_error_code(pdf, tmp_path, config):
    data = reference_data(pdf, basis="standalone")
    path = tmp_path / "ref.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    report = replay(pdf, load_reference(path), assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert report["reason"] == "E-EXTRACT-BASIS-UNAVAILABLE" and report["counts"]["missing"] == 6 and not report["passed"]


def test_a_held_out_or_unrecorded_document_is_refused_before_anything_is_read(pdf, tmp_path, config):
    reference = load_reference(reference_file(tmp_path, pdf))

    with pytest.raises(SendRefused, match="held out"):
        replay(pdf, reference, assignments=records(tmp_path, pdf, group="held_out"), llm=settings_for(config))
    with pytest.raises(SendRefused, match="not on the assignment record"):
        replay(pdf, reference, assignments=_empty(tmp_path), llm=settings_for(config))


def _empty(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    return path


def test_a_reference_written_for_another_document_is_refused(pdf, tmp_path, config):
    data = reference_data(pdf, document_id="R2")
    path = tmp_path / "ref.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GateReferenceError, match="not written for this document"):
        replay(pdf, load_reference(path), assignments=records(tmp_path, pdf), llm=settings_for(config))
    data = reference_data(pdf, sha256="b" * 64)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GateReferenceError, match="not written for this document"):
        replay(pdf, load_reference(path), assignments=records(tmp_path, pdf), llm=settings_for(config))


# --- the command ----------------------------------------------------------------------------------------------------------------------------


def run_main(capsys, *argv):
    code = main([*map(str, argv)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_command_prints_counts_only_and_a_verdict_and_exits_0_on_a_pass(pdf, tmp_path, config, capsys):
    fill_cache(pdf, tmp_path)
    code, out, err = run_main(capsys, "--report", pdf, reference_file(tmp_path, pdf), "--assignments", records(tmp_path, pdf), "--config", config)

    assert code == 0 and out.strip().endswith("GATE: PASS") and err == ""
    for forbidden in ("352.70", "38.50", "400.00", "Profit before tax", "Finance costs", "Acme", "statement.pdf", str(tmp_path)):
        assert forbidden not in out


def test_the_command_fails_with_exit_1_when_the_extraction_does_not_match(pdf, tmp_path, config, capsys):
    data = json.loads(reply(pdf))
    data["fields"] = [f for f in data["fields"] if f["field_name"] != "profit_before_tax"]
    fill_cache(pdf, tmp_path, json.dumps(data))

    code, out, err = run_main(capsys, "--report", pdf, reference_file(tmp_path, pdf), "--assignments", records(tmp_path, pdf), "--config", config)

    assert code == 1 and out.strip().endswith("GATE: FAIL")


def test_the_gate_fails_when_a_tuning_document_on_the_record_is_not_reported(pdf, tmp_path, config, capsys):
    fill_cache(pdf, tmp_path)
    record = records(tmp_path, pdf, extra=[("R8", "8" * 64, "tuning")])

    code, out, _ = run_main(capsys, "--report", pdf, reference_file(tmp_path, pdf), "--assignments", record, "--config", config)

    assert code == 1 and '"tuning_documents": ["R8", "R9"]' in out and out.strip().endswith("GATE: FAIL")


def test_a_refusal_or_a_bad_reference_exits_2_and_says_nothing_about_values(pdf, tmp_path, config, capsys):
    fill_cache(pdf, tmp_path)
    held = records(tmp_path, pdf, group="held_out")

    code, out, err = run_main(capsys, "--report", pdf, reference_file(tmp_path, pdf), "--assignments", held, "--config", config)
    bad = tmp_path / "bad.json"
    bad.write_text('{"document_id": "R9"}', encoding="utf-8")
    code2, out2, err2 = run_main(capsys, "--report", pdf, bad, "--assignments", records(tmp_path, pdf), "--config", config)

    assert (code, code2) == (2, 2) and "held out" in err and "reference file" in err2 and out == out2 == ""


def test_check_reference_validates_a_file_without_a_document(pdf, tmp_path, capsys):
    code, out, err = run_main(capsys, "--check-reference", reference_file(tmp_path, pdf))
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    code2, _, err2 = run_main(capsys, "--check-reference", bad)

    assert code == 0 and '"reference_ok": true' in out and '"entries": 6' in out and "352.70" not in out
    assert code2 == 2 and "gate: refused" in err2


def test_the_command_needs_something_to_do(capsys):
    with pytest.raises(SystemExit) as stop:
        main([])

    assert stop.value.code == 2


def test_the_module_runs_as_a_command(tmp_path):
    import subprocess

    done = subprocess.run([sys.executable, "-m", "credit_intel.evaluation.gate", "--check-reference", str(tmp_path / "none.json")], capture_output=True, cwd=tmp_path)

    assert done.returncode == 2 and b"gate: refused" in done.stderr and done.stdout == b""


# --- a document that never names its basis (R2-like), with the live run's pages and assertion (v0.4.24; step A4) ------------------------------------------


@pytest.fixture
def untitled(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "untitled.pdf", rows=ROWS, title="Balance Sheet")


def untitled_reply(pdf):
    return reply(pdf).replace("Consolidated Balance Sheet", "Balance Sheet")


def fill_untitled(pdf, tmp_path):
    from credit_intel.extraction.prompt import load_prompt
    from credit_intel.models import StatementBasis

    run_extraction(pdf, FakeProvider(script=[untitled_reply(pdf)]), fx.LLM.__class__(provider="fake", model_id="m", token_ceiling=1_000_000, max_output_tokens=2000),
                   cache_dir=tmp_path / ".cache" / "llm", prompt=load_prompt(), page_range="1", assert_basis=StatementBasis.CONSOLIDATED)  # fmt: skip


def with_options(pdf, **options):
    data = reference_data(pdf)
    ordered = {"document_id": data["document_id"], "sha256": data["sha256"], "basis": data["basis"], **options, "entries": data["entries"]}
    return ordered


def write_reference(tmp_path, pdf, **options):
    path = tmp_path / "ref.json"
    path.write_text(json.dumps(with_options(pdf, **options)), encoding="utf-8")
    return path


def test_the_replay_uses_the_pages_and_the_assertion_of_the_live_run_and_reports_which_values_rest_on_it(untitled, tmp_path, config):
    fill_untitled(untitled, tmp_path)
    reference = load_reference(write_reference(tmp_path, untitled, pages="1", assert_basis="consolidated"))

    report = replay(untitled, reference, assignments=records(tmp_path, untitled), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert report["passed"] and report["counts"] == {"match": 6, "mismatch": 0, "missing": 0}
    assert report["basis_assertion"] == {"basis": "consolidated", "pages": [1], "applied_pages": [1]}
    assert {e["basis_evidence"] for e in report["entries"]} == {"analyst_assertion"}


def test_without_the_assertion_in_the_reference_an_untitled_document_stops_at_the_basis_gate(untitled, tmp_path, config):
    fill_untitled(untitled, tmp_path)

    report = replay(untitled, load_reference(write_reference(tmp_path, untitled, pages="1")), assignments=records(tmp_path, untitled),
                    cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))  # fmt: skip

    assert not report["passed"] and report["reason"] == "E-EXTRACT-BASIS-UNAVAILABLE" and report["counts"]["missing"] == 6


def test_pages_other_than_the_live_runs_are_a_cache_miss_not_a_pass(untitled, tmp_path, config):
    fill_untitled(untitled, tmp_path)
    two_pages = fx.balance_sheet_pdf(tmp_path / "two.pdf", rows=ROWS, title="Balance Sheet", narrative_page="The directors report.")
    reference = load_reference(write_reference(tmp_path, two_pages, pages="1-2", assert_basis="consolidated"))

    report = replay(two_pages, reference, assignments=records(tmp_path, two_pages), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))

    assert report["replayed"] is False and report["reason"] == "cache_miss"


def test_a_conflict_with_the_asserted_basis_is_reported_as_the_stop_it_is(tmp_path, config):
    pdf = fx.two_basis_pdf(tmp_path / "two.pdf")
    path = tmp_path / "ref.json"
    path.write_text(json.dumps(with_options(pdf, pages="1-2", assert_basis="consolidated")), encoding="utf-8")

    report = replay(pdf, load_reference(path), assignments=records(tmp_path, pdf), llm=settings_for(config))

    assert report["reason"] == "E-EXTRACT-BASIS-UNAVAILABLE" and not report["passed"]


def test_the_command_passes_an_untitled_document_with_its_assertion_and_prints_no_value(untitled, tmp_path, config, capsys):
    fill_untitled(untitled, tmp_path)
    code, out, err = run_main(capsys, "--report", untitled, write_reference(tmp_path, untitled, pages="1", assert_basis="consolidated"),
                              "--assignments", records(tmp_path, untitled), "--config", config)  # fmt: skip

    assert code == 0 and out.strip().endswith("GATE: PASS") and err == ""
    assert '"basis_evidence": "analyst_assertion"' in out and '"applied_pages": [1]' in out
    for forbidden in ("352.70", "38.50", "400.00", "Finance costs", "Acme", "untitled.pdf", str(tmp_path)):
        assert forbidden not in out


def test_check_reference_shows_the_pages_and_the_assertion_without_a_document(untitled, tmp_path, capsys):
    code, out, _ = run_main(capsys, "--check-reference", write_reference(tmp_path, untitled, pages="1", assert_basis="consolidated"))

    assert code == 0 and '"pages": "1"' in out and '"assert_basis": "consolidated"' in out and "352.70" not in out
