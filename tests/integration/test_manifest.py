"""manifest.json: what a run was and how it went (PRD FR-012.1, FR-012.3; Phase 5 step 5e; B-260).

A synthetic balance sheet, a scripted fake provider, a fixed clock and fixed code and package versions.
"""

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

import pipeline_fixture as fx
from credit_intel.export.manifest import (
    CodeVersion, build_manifest, code_version, package_versions, render_manifest, run_id, timestamp,
)  # fmt: skip
from credit_intel.ingestion.errors import IngestionError
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import StatementBasis
from credit_intel.run import run_pipeline
from credit_intel.states import STATES, Recorder

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
VERSION = CodeVersion("a" * 40, False)
PACKAGES = {"openai": "1.0", "pdfplumber": "2.0", "pydantic": "3.0", "python": "3.12.0"}
BASIS = StatementBasis.CONSOLIDATED


def clock():
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(1000))
    return lambda: next(ticks)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def good_run(pdf, tmp_path, **kw):
    recorder = Recorder(clock())
    result = run_pipeline(pdf, FakeProvider(script=[fx.good_response(pdf)]), fx.LLM, recorder=recorder, cache_dir=tmp_path / "cache", **kw)
    return recorder, result


def manifest_of(recorder, result=None, **kw):
    return build_manifest(recorder=recorder, llm=fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES, result=result, **kw)


# --- a finished run ---------------------------------------------------------------------------------------------------------------------------


def test_a_finished_run_records_everything_fr_012_1_lists(pdf, tmp_path):
    recorder, result = good_run(pdf, tmp_path)
    m = manifest_of(recorder, result, profile_file_name="profile.json")

    assert m["run_id"] == "20261024T101530.123456Z-" + result.extraction.source_document.sha256[:8]
    assert m["started_at"] == "20261024T101530.123456Z" and m["finished_at"] == timestamp(recorder.events[-1].at)
    assert m["input"] == {"file_name": "statement.pdf", "sha256": result.extraction.source_document.sha256, "page_count": 1}
    assert (m["locator_method"], m["candidate_pages"], m["range_pages_without_text"]) == ("keywords", [1], [])
    assert (m["requested_basis"], m["bases_found"], m["profile_file_name"]) == ("consolidated", ["consolidated"], "profile.json")
    assert m["code_version"] == {"git_commit": "a" * 40, "dirty": False} and m["package_versions"] == PACKAGES
    assert m["llm"] == {"provider": "fake", "model_id": "m", "token_ceiling": 1_000_000, "max_output_tokens": 2000}
    assert m["prompt_version"] == result.extraction.extraction.prompt_version and m["extraction_schema_version"] == "1"
    assert m["rules_config_sha256"] == result.rules_sha256 and re.fullmatch(r"[0-9a-f]{64}", m["rules_config_sha256"])
    assert m["cache"] == {"hits": 0, "misses": 1} and m["tokens"]["llm_calls"] == 1 and m["estimated_cost_usd"] is None
    assert (m["final_state"], m["failed_stage"], m["error_code"]) == ("rules_evaluated", None, None)
    assert [e["state"] for e in m["stage_events"]] == list(STATES[:8])


def test_the_stage_events_carry_timestamps_in_order_and_counts_only(pdf, tmp_path):
    recorder, result = good_run(pdf, tmp_path)
    events = manifest_of(recorder, result)["stage_events"]

    assert [e["at"] for e in events] == sorted(e["at"] for e in events) and len({e["at"] for e in events}) == 8
    assert events[-2]["counts"]["metrics_defined"] == 2 and all(isinstance(v, (int, str)) for e in events for v in e["counts"].values())


def test_a_cached_second_run_records_the_hit(pdf, tmp_path):
    good_run(pdf, tmp_path)
    recorder, result = good_run(pdf, tmp_path)

    m = manifest_of(recorder, result)
    assert m["cache"] == {"hits": 1, "misses": 0} and m["tokens"]["llm_calls"] == 0


def test_the_estimated_cost_is_an_exact_decimal_string_when_prices_are_configured(pdf, tmp_path):
    from decimal import Decimal
    from credit_intel.config import PricingSettings

    recorder, result = good_run(pdf, tmp_path, pricing=PricingSettings(Decimal("0.15"), Decimal("0.6")))

    cost = manifest_of(recorder, result)["estimated_cost_usd"]
    assert isinstance(cost, str) and Decimal(cost) > 0 and "e" not in cost.lower()


def test_the_text_is_sorted_json_with_one_final_newline_and_identical_for_identical_inputs(pdf, tmp_path):
    first = render_manifest(manifest_of(*good_run(pdf, tmp_path / "a")))
    second = render_manifest(manifest_of(*good_run(pdf, tmp_path / "b")))

    assert first == second and first.endswith("}\n") and not first.endswith("\n\n")
    data = json.loads(first)
    assert first == json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_the_profile_values_the_statement_text_and_the_path_are_not_written(pdf, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"borrower_name": "Zebra Holdings", "notes": "secret-note-77"}), encoding="utf-8")
    recorder, result = good_run(pdf, tmp_path, profile_path=profile)

    text = render_manifest(manifest_of(recorder, result, profile_file_name=profile.name))

    for forbidden in ("Zebra Holdings", "secret-note-77", str(tmp_path), "Total current assets", "1,482.30", "Acme Industries"):
        assert forbidden not in text


# --- a failed run -----------------------------------------------------------------------------------------------------------------------------


def test_a_run_that_fails_before_the_text_is_read_has_a_manifest_with_nothing_invented(tmp_path):
    missing = tmp_path / "absent.pdf"
    recorder = Recorder(clock())
    with pytest.raises(IngestionError):
        run_pipeline(missing, FakeProvider(script=[]), fx.LLM, recorder=recorder, cache_dir=tmp_path / "cache")

    m = manifest_of(recorder, input_file_name="absent.pdf")

    assert (m["final_state"], m["failed_stage"], m["error_code"]) == ("failed", "validated", "E-INPUT-NOT-FOUND")
    assert m["run_id"] is None and m["input"] == {"file_name": "absent.pdf", "sha256": None, "page_count": None}
    assert m["candidate_pages"] is None and m["cache"] is None and m["tokens"] is None and m["prompt_version"] is None
    assert m["requested_basis"] == "consolidated" and m["llm"]["model_id"] == "m"
    assert [e["state"] for e in m["stage_events"]] == ["received"]


def test_a_failure_after_the_input_was_read_still_gets_a_run_id_from_the_given_hash(tmp_path):
    blank = fx.blank_text_pdf(tmp_path / "blank.pdf")
    recorder = Recorder(clock())
    with pytest.raises(IngestionError):
        run_pipeline(blank, FakeProvider(script=[]), fx.LLM, recorder=recorder, cache_dir=tmp_path / "cache")

    m = manifest_of(recorder, input_file_name="blank.pdf", input_sha256="b" * 64)

    assert m["error_code"] == "E-EXTRACT-NO-STATEMENT-PAGES" and m["failed_stage"] == "fields_extracted" and m["run_id"].endswith("-bbbbbbbb")


def test_an_unexpected_error_is_a_failed_manifest_with_no_error_code(pdf, tmp_path):
    recorder = Recorder(clock())
    recorder.enter("received")
    recorder.fail(None)

    m = manifest_of(recorder)
    assert (m["final_state"], m["failed_stage"], m["error_code"]) == ("failed", "validated", None)


def test_a_manifest_needs_at_least_one_recorded_state():
    with pytest.raises(ValueError):
        manifest_of(Recorder())


# --- the pieces ---------------------------------------------------------------------------------------------------------------------------------


def test_the_run_id_is_utc_microseconds_and_the_first_eight_hex_of_the_hash():
    assert run_id(START, "1a2b3c4d" + "0" * 56) == "20261024T101530.123456Z-1a2b3c4d"
    assert run_id(START.replace(microsecond=5), "f" * 64).startswith("20261024T101530.000005Z")


@pytest.mark.parametrize("moment", [datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=UTC) .astimezone(__import__("datetime").timezone(timedelta(hours=2)))])
def test_a_timestamp_that_is_not_utc_is_refused(moment):
    with pytest.raises(ValueError):
        timestamp(moment)


def test_the_real_package_versions_and_code_version_have_the_right_shape(tmp_path):
    versions = package_versions()
    assert set(versions) == {"openai", "pdfplumber", "pydantic", "python"} and all(isinstance(v, str) for v in versions.values())
    assert package_versions(("no-such-package-xyz",))["no-such-package-xyz"] is None

    here = code_version()
    assert re.fullmatch(r"[0-9a-f]{40}", here.git_commit) and isinstance(here.dirty, bool)
    assert code_version(tmp_path) == CodeVersion(None, None)  # not a git checkout


def test_the_dirty_flag_is_false_for_a_clean_checkout_and_true_after_a_change(tmp_path):
    import subprocess

    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-q", "-m", "first")
    clean = code_version(tmp_path)
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    changed = code_version(tmp_path)
    (tmp_path / "untracked.txt").write_text("x", encoding="utf-8")

    assert clean.dirty is False and changed.dirty is True and clean.git_commit == changed.git_commit
    assert re.fullmatch(r"[0-9a-f]{40}", clean.git_commit)
