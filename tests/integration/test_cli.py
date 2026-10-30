"""The command line: every exit path and every rejection (PRD FR-014.1 to FR-014.7, FR-011.2, FR-011.4, SEC-10; Phase 5 step 5k; B-269)."""

import io
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from importlib import metadata
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.evaluation.guard import MEMBERS
from credit_intel.ingestion.errors import CATALOGUE, ErrorCode, IngestionError
from credit_intel.llm.factory import build_provider
from credit_intel.llm.provider import FakeProvider

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
SETTINGS = '[llm]\nprovider = "{provider}"\nmodel_id = "m"\ntoken_ceiling = {ceiling}\nmax_output_tokens = 2000\n'


def clock(start=START):
    ticks = iter(start + timedelta(milliseconds=7 * n) for n in range(10_000))
    return lambda: next(ticks)


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the response cache and the default output directory are relative to it


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def settings(tmp_path, provider="fake", ceiling=1_000_000):
    path = tmp_path / "settings.toml"
    path.write_text(SETTINGS.format(provider=provider, ceiling=ceiling), encoding="utf-8")
    return path


def records(tmp_path, *rows):
    path = tmp_path / "assignments.jsonl"
    lines = [json.dumps(dict(zip(MEMBERS, (doc, sha, group, "2026-10-24", "assigned", None, None), strict=True))) for doc, sha, group in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def call(tmp_path, *argv, replies=None, factory=None, start=START, env=None, assignments=None, provider="fake", ceiling=1_000_000):
    out, err = io.StringIO(), io.StringIO()
    config = settings(tmp_path, provider, ceiling)
    full = [*argv, "--config", str(config)] if "--config" not in argv else list(argv)
    code = main(full, provider_factory=factory or (lambda s, e: FakeProvider(script=replies or [])), clock=clock(start), stdout=out, stderr=err,
                assignments=assignments or tmp_path / "none.jsonl", env={} if env is None else env)  # fmt: skip
    return code, out.getvalue(), err.getvalue()


def runs(tmp_path):
    return sorted((tmp_path / "runs").iterdir()) if (tmp_path / "runs").exists() else []


def manifest_of(folder):
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


# --- success (FR-014.2) --------------------------------------------------------------------------------------------------------------------------


def test_a_good_run_exits_0_prints_only_the_run_folder_and_writes_the_three_files(pdf, tmp_path):
    code, out, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    folder = Path(out.strip())
    assert code == 0 and out.count("\n") == 1 and folder.parent == Path("runs") and folder.is_dir()
    assert sorted(p.name for p in folder.iterdir()) == ["manifest.json", "memo.md", "results.json"]
    assert manifest_of(folder)["final_state"] == "exported" and manifest_of(folder)["requested_basis"] == "consolidated"


def test_standard_error_holds_the_stage_log_with_counts_and_no_document_text(pdf, tmp_path):
    code, out, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    assert code == 0 and "INFO credit_intel.run stage=calculated" in err and "stage=exported" in err
    for forbidden in ("Total current assets", "1,482.30", "Acme", "statement.pdf", str(tmp_path)):
        assert forbidden not in err and forbidden not in out


def test_the_options_are_passed_to_the_run(pdf, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"borrower_name": "Zebra Ltd"}), encoding="utf-8")
    code, out, _ = call(tmp_path, str(pdf), "--pages", "1", "--profile", str(profile), "--output-dir", str(tmp_path / "elsewhere"),
                        replies=[fx.good_response(pdf)])  # fmt: skip

    folder = Path(out.strip())
    manifest = manifest_of(folder)
    assert code == 0 and folder.parent == tmp_path / "elsewhere" and not (tmp_path / "runs").exists()
    assert manifest["locator_method"] == "page_range" and manifest["profile_file_name"] == "profile.json"
    assert "Zebra Ltd [ANALYST-PROVIDED]" in (folder / "memo.md").read_text(encoding="utf-8")


def test_a_run_served_from_the_cache_needs_no_provider_and_no_key(pdf, tmp_path):
    call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    def no_provider(settings, env):
        raise AssertionError("the provider must not be built for a cache hit")

    code, out, _ = call(tmp_path, str(pdf), factory=no_provider, start=START + timedelta(seconds=9))

    assert code == 0 and manifest_of(Path(out.strip()))["cache"] == {"hits": 1, "misses": 0} and len(runs(tmp_path)) == 2


# --- argument errors (FR-014.4) ----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [[], ["--pages", "1"], ["statement.pdf", "--unknown"], ["statement.pdf", "--basis", "unknown"], ["statement.pdf", "--basis", "x"],
                                  ["a.pdf", "b.pdf"], ["statement.pdf", "--pages"]])  # fmt: skip
def test_an_argument_error_exits_2_with_the_usage_on_standard_error_and_nothing_on_standard_output(tmp_path, argv):
    out, err = io.StringIO(), io.StringIO()

    code = main(argv, stdout=out, stderr=err, env={})

    assert code == 2 and out.getvalue() == "" and "usage: credit-intel" in err.getvalue()
    assert not (tmp_path / "runs").exists()


def test_help_exits_0_and_names_every_option_of_fr_014(tmp_path):
    out, err = io.StringIO(), io.StringIO()

    code = main(["--help"], stdout=out, stderr=err, env={})
    text = err.getvalue() + out.getvalue()

    assert code == 0
    for option in ("--pages", "--basis", "--profile", "--output-dir", "--config", "--confirm-public-document"):
        assert option in text


# --- catalogued failures (FR-014.3, FR-011.2) --------------------------------------------------------------------------------------------------


def failed(tmp_path, *argv, expect_code, expect_exit, **kw):
    code, out, err = call(tmp_path, *argv, **kw)
    assert code == expect_exit and out == "", (code, err)
    error_lines = [line for line in err.splitlines() if line.startswith("E-")]  # the rest of standard error is the INFO stage log
    assert len(error_lines) == 1 and error_lines[0].startswith(f"{expect_code}: "), err
    assert "Traceback" not in err
    return err


def test_a_missing_file_exits_3_and_writes_nothing(tmp_path):
    failed(tmp_path, str(tmp_path / "absent.pdf"), expect_code="E-INPUT-NOT-FOUND", expect_exit=3)

    assert runs(tmp_path) == []


def test_a_file_that_is_not_a_pdf_exits_3_and_leaves_a_manifest_only_record(tmp_path):
    text = tmp_path / "note.pdf"
    text.write_text("not a pdf", encoding="utf-8")

    err = failed(tmp_path, str(text), expect_code="E-INPUT-NOT-PDF", expect_exit=3)
    (folder,) = runs(tmp_path)

    assert f"Run record: runs/{folder.name}" in err and [p.name for p in folder.iterdir()] == ["manifest.json"]
    assert (manifest_of(folder)["final_state"], manifest_of(folder)["error_code"], manifest_of(folder)["failed_stage"]) == ("failed", "E-INPUT-NOT-PDF", "validated")


def test_a_page_range_outside_the_document_exits_3(pdf, tmp_path):
    failed(tmp_path, str(pdf), "--pages", "99", expect_code="E-INPUT-PAGE-RANGE", expect_exit=3)


def test_a_document_with_no_statement_pages_exits_4(tmp_path):
    blank = fx.blank_text_pdf(tmp_path / "blank.pdf")

    failed(tmp_path, str(blank), expect_code="E-EXTRACT-NO-STATEMENT-PAGES", expect_exit=4)


def test_a_basis_the_document_does_not_have_exits_4(pdf, tmp_path):
    failed(tmp_path, str(pdf), "--basis", "standalone", expect_code="E-EXTRACT-BASIS-UNAVAILABLE", expect_exit=4)
    (folder,) = runs(tmp_path)

    assert manifest_of(folder)["requested_basis"] == "standalone" and manifest_of(folder)["failed_stage"] == "statements_located"


@pytest.mark.parametrize(
    "text",
    ["{not json", "[]", '"x"', '{"unknown": "x"}', '{"notes": 5}', '{"notes": null}', json.dumps({"notes": "x" * 501}), json.dumps({"borrower_name": ["a"]})],
)
def test_every_rejected_profile_exits_3_before_anything_is_read_or_sent_or_written(pdf, tmp_path, text):
    profile = tmp_path / "profile.json"
    profile.write_text(text, encoding="utf-8")

    err = failed(tmp_path, str(pdf), "--profile", str(profile), expect_code="E-INPUT-PROFILE-INVALID", expect_exit=3)

    assert runs(tmp_path) == [] and str(profile) not in err


def test_a_missing_profile_file_exits_3_with_the_profile_code(pdf, tmp_path):
    failed(tmp_path, str(pdf), "--profile", str(tmp_path / "none.json"), expect_code="E-INPUT-PROFILE-INVALID", expect_exit=3)


def test_a_settings_file_without_a_token_ceiling_exits_6(pdf, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\nmax_output_tokens = 10\n', encoding="utf-8")

    err = failed(tmp_path, str(pdf), "--config", str(bad), expect_code="E-CONFIG-INVALID", expect_exit=6)

    assert "token_ceiling" in err and runs(tmp_path) == []


def test_a_missing_settings_file_exits_6(pdf, tmp_path):
    failed(tmp_path, str(pdf), "--config", str(tmp_path / "nowhere.toml"), expect_code="E-CONFIG-INVALID", expect_exit=6)


def test_a_missing_api_key_exits_5_in_the_extraction_stage(pdf, tmp_path):
    failed(tmp_path, str(pdf), "--confirm-public-document", factory=build_provider, provider="openai", expect_code="E-LLM-AUTH", expect_exit=5)
    (folder,) = runs(tmp_path)

    assert manifest_of(folder)["failed_stage"] == "fields_extracted" and manifest_of(folder)["cache"] is None


def test_a_reply_that_is_invalid_twice_exits_5(pdf, tmp_path):
    failed(tmp_path, str(pdf), replies=["not json", "still not json"], expect_code="E-LLM-INVALID-OUTPUT", expect_exit=5)


def test_an_unavailable_provider_exits_5(pdf, tmp_path):
    class Down:
        def complete(self, request):
            raise IngestionError(ErrorCode.LLM_UNAVAILABLE)

    failed(tmp_path, str(pdf), factory=lambda s, e: Down(), expect_code="E-LLM-UNAVAILABLE", expect_exit=5)


def test_a_token_ceiling_that_would_be_exceeded_exits_5_before_any_call(pdf, tmp_path):
    def no_call(settings, env):
        raise AssertionError("no call should be made")

    failed(tmp_path, str(pdf), ceiling=10, factory=no_call, expect_code="E-LLM-BUDGET-EXCEEDED", expect_exit=5)


def test_an_existing_run_folder_exits_7_and_is_left_alone(pdf, tmp_path):
    code, out, _ = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])
    folder = tmp_path / out.strip()
    before = {p.name: p.read_bytes() for p in folder.iterdir()}

    failed(tmp_path, str(pdf), replies=[fx.good_response(pdf)], expect_code="E-EXPORT-FAILED", expect_exit=7)  # the same clock gives the same run ID

    assert code == 0 and {p.name: p.read_bytes() for p in folder.iterdir()} == before and runs(tmp_path) == [folder]


def test_every_catalogue_code_in_these_tests_has_its_documented_exit_code():
    assert {c: CATALOGUE[c].exit_code for c in (ErrorCode.NOT_FOUND, ErrorCode.NO_STATEMENT_PAGES, ErrorCode.LLM_AUTH, ErrorCode.CONFIG_INVALID, ErrorCode.EXPORT_FAILED)} == {
        ErrorCode.NOT_FOUND: 3, ErrorCode.NO_STATEMENT_PAGES: 4, ErrorCode.LLM_AUTH: 5, ErrorCode.CONFIG_INVALID: 6, ErrorCode.EXPORT_FAILED: 7}  # fmt: skip


# --- unexpected errors (FR-014.5) ----------------------------------------------------------------------------------------------------------------


def test_an_unexpected_error_exits_1_names_the_run_id_and_shows_no_trace_or_text(pdf, tmp_path):
    class Broken:
        def complete(self, request):
            raise RuntimeError("secret statement text 1,482.30")

    code, out, err = call(tmp_path, str(pdf), factory=lambda s, e: Broken())

    assert code == 1 and out == "" and "Traceback" not in err and "secret statement text" not in err and "1,482.30" not in err
    (folder,) = runs(tmp_path)
    assert f"Internal error. Run ID: {folder.name}." in err
    assert (manifest_of(folder)["final_state"], manifest_of(folder)["error_code"]) == ("failed", None)


def test_an_unexpected_error_before_the_run_is_recorded_still_exits_1_with_an_unknown_run_id(pdf, tmp_path, monkeypatch):
    monkeypatch.setattr("credit_intel.service.load_pricing", lambda *a, **k: 1 / 0)

    code, out, err = call(tmp_path, str(pdf))

    assert code == 1 and "Run ID: unknown" in err and out == "" and runs(tmp_path) == []


def test_an_interrupt_exits_130_quietly(pdf, tmp_path):
    class Interrupt:
        def complete(self, request):
            raise KeyboardInterrupt

    code, out, err = call(tmp_path, str(pdf), factory=lambda s, e: Interrupt())

    assert code == 130 and out == "" and "Interrupted." in err and "Traceback" not in err


def test_the_stack_trace_is_available_at_debug_level_only(pdf, tmp_path, caplog):
    class Broken:
        def complete(self, request):
            raise RuntimeError("boom")

    with caplog.at_level("DEBUG", logger="credit_intel.cli"):
        call(tmp_path, str(pdf), factory=lambda s, e: Broken())

    assert any(r.exc_info and r.levelname == "DEBUG" for r in caplog.records)


# --- the send rule (SEC-10, decision 1) ----------------------------------------------------------------------------------------------------------


def sha_of(path):
    from credit_intel.evaluation.guard import file_sha256

    return file_sha256(path)


def refused_before_anything(tmp_path, pdf, reason, *argv, **kw):
    """The refusal of PRD v0.4.27: the catalogued failure E-INPUT-SEND-REFUSED, exit 3, one fixed reason word, before any provider or file."""

    def no_provider(settings, env):
        raise AssertionError("nothing may be sent")

    code, out, err = call(tmp_path, str(pdf), *argv, factory=no_provider, provider="openai", **kw)
    error_lines = [line for line in err.splitlines() if line.startswith("E-")]
    assert code == 3 and out == "" and len(error_lines) == 1, err
    assert error_lines[0].startswith("E-INPUT-SEND-REFUSED: ") and error_lines[0].endswith(f"({reason})"), error_lines[0]
    assert runs(tmp_path) == [] and "Refused" not in err and "Traceback" not in err  # no failure record: nothing was received
    assert sha_of(pdf)[:12] not in err and str(tmp_path) not in err and "H9" not in err and "R9" not in err  # no hash, no path, no neutral ID
    return err


def test_a_document_not_on_the_record_is_not_sent_without_the_confirmation(pdf, tmp_path):
    err = refused_before_anything(tmp_path, pdf, "not_recorded", assignments=records(tmp_path))

    assert "--confirm-public-document" in err  # the action says what to do


def test_the_confirmation_lets_a_document_not_on_the_record_be_sent_and_a_notice_is_printed(pdf, tmp_path):
    code, out, err = call(tmp_path, str(pdf), "--confirm-public-document", replies=[fx.good_response(pdf)], provider="openai", assignments=records(tmp_path))

    assert code == 0 and "will be sent to the hosted API" in err and Path(out.strip()).is_dir()


def test_a_tuning_document_is_sent_without_the_confirmation(pdf, tmp_path):
    code, out, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)], provider="openai", assignments=records(tmp_path, ("R9", sha_of(pdf), "tuning")))

    assert code == 0 and Path(out.strip()).is_dir()


def test_b6_139_the_held_out_tool_variables_do_not_open_the_ordinary_command_line(pdf, tmp_path):
    record = records(tmp_path, ("H9", sha_of(pdf), "held_out"))
    env = {"CREDIT_INTEL_HELD_OUT_APPROVED": "0123456789abcdef0123", "CREDIT_INTEL_PRIVATE_APPROVED": "1"}  # the tool's approval, read only by the tool

    refused_before_anything(tmp_path, pdf, "held_out", assignments=record, env=env)
    refused_before_anything(tmp_path, pdf, "held_out", "--confirm-public-document", assignments=record, env=env)


def test_a_held_out_document_is_never_sent_even_with_the_confirmation(pdf, tmp_path):
    record = records(tmp_path, ("H9", sha_of(pdf), "held_out"))

    refused_before_anything(tmp_path, pdf, "held_out", assignments=record)
    err = refused_before_anything(tmp_path, pdf, "held_out", "--confirm-public-document", assignments=record)

    assert "a held-out document cannot be sent" in err


def test_a_record_that_cannot_be_read_refuses_every_document(pdf, tmp_path):
    bad = tmp_path / "assignments.jsonl"
    bad.write_text("{not json\n", encoding="utf-8")

    refused_before_anything(tmp_path, pdf, "record_unreadable", "--confirm-public-document", assignments=bad)


def test_with_no_record_file_a_document_needs_the_confirmation(pdf, tmp_path):
    refused_before_anything(tmp_path, pdf, "not_recorded")


def test_a_refusal_is_a_catalogued_failure_that_scripts_can_tell_from_a_usage_error(pdf, tmp_path):
    from credit_intel.ingestion.errors import CATALOGUE, ErrorCode

    refused, _, _ = call(tmp_path, str(pdf), provider="openai", factory=lambda s, e: None)
    usage, _, _ = call(tmp_path, str(pdf), "--assert-basis", "consolidated")

    assert refused == CATALOGUE[ErrorCode.SEND_REFUSED].exit_code == 3 and usage == 2


def test_nothing_is_checked_or_announced_when_the_provider_sends_nothing_off_the_machine(pdf, tmp_path):
    code, out, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)], assignments=records(tmp_path, ("H9", sha_of(pdf), "held_out")))

    assert code == 0 and "hosted API" not in err


# --- logging and the entry point ---------------------------------------------------------------------------------------------------------------


def test_the_log_level_can_be_raised_by_the_environment(pdf, tmp_path):
    code, out, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)], env={"CREDIT_INTEL_LOG_LEVEL": "WARNING"})

    assert code == 0 and "stage=" not in err and Path(out.strip()).is_dir()


def test_the_console_script_points_at_the_command_and_the_module_runs_it(tmp_path):
    (entry,) = [e for e in metadata.entry_points(group="console_scripts") if e.name == "credit-intel"]
    done = subprocess.run([sys.executable, "-m", "credit_intel"], capture_output=True, cwd=tmp_path, env={**os.environ})

    assert entry.value == "credit_intel.cli:run"
    assert done.returncode == 2 and b"usage: credit-intel" in done.stderr and done.stdout == b""


def test_an_installed_run_of_the_real_entry_point_with_a_missing_file_exits_3(tmp_path):
    config = settings(tmp_path)
    done = subprocess.run([sys.executable, "-m", "credit_intel", str(tmp_path / "absent.pdf"), "--config", str(config)], capture_output=True, cwd=tmp_path,
                          env={**os.environ, "CREDIT_INTEL_PARSE_TIMEOUT_SECONDS": "60", "CREDIT_INTEL_PARSE_MEMORY_MB": "2048"})

    assert done.returncode == 3 and done.stdout == b"" and done.stderr.startswith(b"E-INPUT-NOT-FOUND: ")


def test_a_failure_record_is_attempted_only_for_a_failure_that_was_recorded_and_not_for_the_export_itself(pdf, tmp_path, monkeypatch):
    import credit_intel.service as service

    attempts = []
    real = service.export_failure
    monkeypatch.setattr(service, "export_failure", lambda *a, **k: attempts.append(1) or real(*a, **k))
    profile = tmp_path / "profile.json"
    profile.write_text("{not json", encoding="utf-8")
    text = tmp_path / "note.pdf"
    text.write_text("not a pdf", encoding="utf-8")

    call(tmp_path, str(tmp_path / "absent.pdf"))  # not found: nothing was recorded
    call(tmp_path, str(pdf), "--profile", str(profile))  # bad profile: failed before `received`
    assert attempts == []
    call(tmp_path, str(text))  # recorded in `validated`
    assert attempts == [1]
    call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])
    call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])  # the second export is refused: the output location is what failed
    assert attempts == [1]
