"""The optional page classifier inside a whole run and the command (PRD v0.4.31; B-298). Mocked classifiers and providers only; no network."""

import io
import json
import logging
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.config import JevSettings
from credit_intel.evaluation.guard import MEMBERS
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import FieldName, PeriodRole
from credit_intel.pagefilter.classifier import FakeClassifier
from credit_intel.pagefilter.filter import PageFilterSetup
from credit_intel.pagefilter.labels import ClassifierError, PageBasis, PageClassification, PageType

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
JEV = JevSettings(enabled=True, price_input_per_million=None)
SETTINGS = '[llm]\nprovider = "{provider}"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'
SHA_LENGTH = 64


def label(page_type=PageType.BALANCE_SHEET, conf=0.95, basis=PageBasis.CONSOLIDATED, basis_conf=0.9, tokens=100):
    return PageClassification(page_type, conf, basis, basis_conf, "jev-1.14.0", tokens, 12)


def standalone_second_page():
    return FakeClassifier({1: label(), 2: label(basis=PageBasis.STANDALONE, basis_conf=0.92)})


def ticks():
    counter = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    return lambda: next(counter)


# --- inside the pipeline -----------------------------------------------------------------------------------------------------------


@pytest.fixture
def two_pages(tmp_path):
    return fx.two_basis_pdf(tmp_path / "statement.pdf")


def extract(pdf, tmp_path, page_filter=None, **kw):
    provider = FakeProvider(script=[fx.good_response(pdf)])
    run = run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "cache", page_filter=page_filter, **kw)
    return run, provider


def test_a_page_the_classifier_is_sure_is_on_the_other_basis_is_not_sent_and_the_fields_are_the_same(two_pages, tmp_path):
    plain, plain_provider = extract(two_pages, tmp_path / "a")
    filtered, filtered_provider = extract(two_pages, tmp_path / "b", PageFilterSetup(JEV, standalone_second_page()))

    assert [c.page_number for c in plain.located.candidates] == [1, 2] and [c.page_number for c in filtered.located.candidates] == [1]
    assert filtered.page_filter.pages_dropped == (2,) and filtered.page_filter.pages_sent == (1,)
    assert [(f.field_id, f.raw_value, f.status) for f in filtered.field_set.fields] == [(f.field_id, f.raw_value, f.status) for f in plain.field_set.fields]
    assert len(filtered_provider.calls[0].user) < len(plain_provider.calls[0].user)  # fewer pages in the prompt
    assert "=== PAGE 2 ===" in plain_provider.calls[0].user and "=== PAGE 2 ===" not in filtered_provider.calls[0].user
    assert filtered.stats.input_tokens <= plain.stats.input_tokens


def test_without_the_step_nothing_of_it_is_recorded_and_the_classifier_is_never_called(two_pages, tmp_path):
    classifier = standalone_second_page()

    run, _ = extract(two_pages, tmp_path, PageFilterSetup(JevSettings(enabled=False), classifier))

    assert run.page_filter is None and classifier.calls == [] and [c.page_number for c in run.located.candidates] == [1, 2]


def test_a_classifier_that_always_fails_gives_exactly_the_run_without_it(two_pages, tmp_path):
    plain, _ = extract(two_pages, tmp_path / "a")
    failing = FakeClassifier({1: ClassifierError("timeout"), 2: RuntimeError("down")})

    filtered, provider = extract(two_pages, tmp_path / "b", PageFilterSetup(JEV, failing))

    assert filtered.located == plain.located and filtered.field_set.counts == plain.field_set.counts
    assert [f.model_dump(mode="json") for f in filtered.field_set.fields] == [f.model_dump(mode="json") for f in plain.field_set.fields]
    assert filtered.page_filter.fallbacks == 2 and filtered.page_filter.pages_dropped == () and "=== PAGE 2 ===" in provider.calls[0].user


def test_a_classifier_switched_on_but_missing_is_recorded_and_the_run_is_unchanged(two_pages, tmp_path):
    plain, _ = extract(two_pages, tmp_path / "a")

    filtered, _ = extract(two_pages, tmp_path / "b", PageFilterSetup(JEV, None, "no_key"))

    assert filtered.located == plain.located and filtered.page_filter.skipped_reason == "no_key" and not filtered.page_filter.active
    assert filtered.page_filter.pages_sent == (1, 2)


def test_a_page_range_is_never_filtered(two_pages, tmp_path):
    classifier = FakeClassifier({1: label(), 2: label(PageType.OTHER, 0.99)})

    run, _ = extract(two_pages, tmp_path, PageFilterSetup(JEV, classifier), page_range="1-2")

    assert [c.page_number for c in run.located.candidates] == [1, 2] and classifier.calls == [] and run.page_filter.skipped_reason == "page_range"


def test_the_classifier_cannot_change_what_the_verifier_decides(two_pages, tmp_path):
    """A label that disagrees with the page (the page really is a balance sheet) changes which pages are sent, never a field's status."""
    wrong = FakeClassifier({1: label(PageType.BALANCE_SHEET, 0.99, PageBasis.CONSOLIDATED, 0.99), 2: label(PageType.BALANCE_SHEET, 0.99, PageBasis.CONSOLIDATED, 0.99)})

    run, _ = extract(two_pages, tmp_path, PageFilterSetup(JEV, wrong))

    current_assets = run.field_set.get(FieldName.CURRENT_ASSETS, PeriodRole.CURRENT)
    assert current_assets.raw_value == "1,482.30" and current_assets.field_id.endswith(".consolidated")  # the page's own title decides the basis


def test_the_log_lines_of_a_run_carry_the_label_confidence_fallback_latency_and_no_text(two_pages, tmp_path, caplog):
    caplog.set_level(logging.INFO)

    extract(two_pages, tmp_path, PageFilterSetup(JEV, standalone_second_page()))

    lines = [r.getMessage() for r in caplog.records if r.name == "credit_intel.pagefilter"]
    assert len(lines) == 3 and "page=2 type=balance_sheet type_conf=0.950 basis=standalone basis_conf=0.920 decision=dropped fallback=no" in lines[1]
    assert "Acme" not in caplog.text and "1,482.30" not in caplog.text


# --- through the command -----------------------------------------------------------------------------------------------------------


def cli(tmp_path, pdf, *argv, env=None, classifier=None, classifier_factory=None, provider="fake", assignments=None, replies=None):
    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS.format(provider=provider), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    factory = classifier_factory or (lambda jev, environment: classifier)
    code = main([str(pdf), *argv, "--config", str(config), "--output-dir", str(tmp_path / "runs")],
                provider_factory=lambda s, e: FakeProvider(script=replies or [fx.good_response(pdf)]), clock=ticks(), stdout=out, stderr=err,
                assignments=assignments or tmp_path / "none.jsonl", env=env if env is not None else {}, classifier_factory=factory)  # fmt: skip
    return code, out.getvalue(), err.getvalue()


def files_of(tmp_path, out):
    folder = tmp_path / out.strip()
    return {name: (folder / name).read_text(encoding="utf-8") for name in ("results.json", "manifest.json", "memo.md")}


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def strip(results):
    results = json.loads(results)
    results["extraction"].pop("page_filter", None)
    return results


def test_with_use_jev_off_the_run_is_exactly_as_before_and_the_files_have_no_trace_of_it(tmp_path, two_pages):
    classifier = standalone_second_page()
    (tmp_path / "base").mkdir()
    baseline = cli(tmp_path / "base", two_pages, classifier=None)
    code, out, _ = cli(tmp_path, two_pages, env={}, classifier=classifier)

    files = files_of(tmp_path, out)
    assert code == 0 and classifier.calls == [] and baseline[0] == 0
    assert "page_filter" not in files["results.json"] and "page_filter" not in files["manifest.json"] and "Jev" not in files["memo.md"]
    assert files["results.json"] == files_of(tmp_path / "base", baseline[1])["results.json"]


def test_with_use_jev_true_a_dropped_page_is_in_both_records_and_the_results_stay_deterministic(tmp_path, two_pages):
    code, out, err = cli(tmp_path, two_pages, env={"USE_JEV": "true"}, classifier=standalone_second_page())

    files = files_of(tmp_path, out)
    results, manifest = json.loads(files["results.json"]), json.loads(files["manifest.json"])
    assert code == 0 and results["extraction"]["candidate_pages"] == [1]
    assert results["extraction"]["page_filter"] == {"enabled": True, "threshold": 0.85, "requested_model": "jev-latest", "model_ids": ["jev-1.14.0"],
                                                    "skipped_reason": None, "pages_sent": [1], "pages_dropped": [2]}  # fmt: skip
    pages = manifest["page_filter"]["pages"]
    assert [p["page"] for p in pages] == [1, 2] and pages[1]["decision"] == "dropped" and pages[1]["latency_ms"] == 12 and manifest["page_filter"]["calls"] == 2
    assert "latency" not in files["results.json"] and "Jev" not in files["memo.md"] and "stage=pages_filtered" in err


def test_the_results_of_a_run_with_the_step_are_the_results_without_it_apart_from_the_page_lists(tmp_path, two_pages):
    (tmp_path / "base").mkdir()
    _, base_out, _ = cli(tmp_path / "base", two_pages)
    _, out, _ = cli(tmp_path, two_pages, env={"USE_JEV": "true"}, classifier=standalone_second_page())
    plain, filtered = json.loads(files_of(tmp_path / "base", base_out)["results.json"]), strip(files_of(tmp_path, out)["results.json"])

    assert plain["extraction"].pop("candidate_pages") == [1, 2] and filtered["extraction"].pop("candidate_pages") == [1]
    assert plain == filtered


def test_a_classifier_that_fails_every_time_still_gives_exit_0_and_the_same_results(tmp_path, two_pages):
    (tmp_path / "base").mkdir()
    _, base_out, _ = cli(tmp_path / "base", two_pages)
    failing = FakeClassifier({1: RuntimeError("down"), 2: ClassifierError("timeout")})

    code, out, _ = cli(tmp_path, two_pages, env={"USE_JEV": "true"}, classifier=failing)

    assert code == 0 and strip(files_of(tmp_path, out)["results.json"]) == json.loads(files_of(tmp_path / "base", base_out)["results.json"])
    assert json.loads(files_of(tmp_path, out)["manifest.json"])["page_filter"]["fallbacks"] == 2


def test_use_jev_true_without_a_key_runs_without_it_and_says_so(tmp_path, two_pages):
    code, out, _ = cli(tmp_path, two_pages, env={"USE_JEV": "true"}, classifier=None)

    part = json.loads(files_of(tmp_path, out)["results.json"])["extraction"]["page_filter"]
    assert code == 0 and part["skipped_reason"] == "no_key" and part["pages_sent"] == [1, 2] and part["pages_dropped"] == []


def test_a_classifier_that_cannot_even_be_built_does_not_stop_the_run(tmp_path, two_pages):
    def broken(jev, environment):
        raise RuntimeError("the SDK is not installable here")

    code, out, _ = cli(tmp_path, two_pages, env={"USE_JEV": "true"}, classifier_factory=broken)

    assert code == 0 and json.loads(files_of(tmp_path, out)["results.json"])["extraction"]["page_filter"]["skipped_reason"] == "error"


def test_a_bad_use_jev_value_is_a_configuration_error(tmp_path, two_pages):
    code, _, err = cli(tmp_path, two_pages, env={"USE_JEV": "maybe"}, classifier=None)

    assert code == 6 and "E-CONFIG-INVALID" in err and "USE_JEV" in err and "maybe" not in err


def test_a_bad_steps_table_is_a_configuration_error_only_when_the_step_is_on(tmp_path, two_pages):
    config = tmp_path / "settings.toml"
    for use in ({}, {"USE_JEV": "true"}):
        config.write_text(SETTINGS.format(provider="fake") + '[steps]\nclassify = "gpt"\n', encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        code = main([str(two_pages), "--config", str(config), "--output-dir", str(tmp_path / "runs")], provider_factory=lambda s, e: FakeProvider(script=[fx.good_response(two_pages)]),
                    clock=ticks(), stdout=out, stderr=err, assignments=tmp_path / "none.jsonl", env=use, classifier_factory=lambda j, e: None)  # fmt: skip
        assert code == (6 if use else 0)


# --- the send rule covers the classifier -------------------------------------------------------------------------------------------


class HostedClassifier(FakeClassifier):
    sends_off_machine = True


def record(tmp_path, pdf, group):
    from credit_intel.evaluation.guard import file_sha256

    path = tmp_path / "assignments.jsonl"
    path.write_text(json.dumps(dict(zip(MEMBERS, ("D", file_sha256(pdf), group, "2026-10-24", "assigned", None, None), strict=True))) + "\n", encoding="utf-8")
    return path


def test_a_hosted_classifier_makes_the_send_rule_apply_even_with_a_local_extractor(tmp_path, two_pages):
    classifier = HostedClassifier({1: label(), 2: label()})

    code, out, err = cli(tmp_path, two_pages, env={"USE_JEV": "true"}, classifier=classifier)

    assert code == 3 and out == "" and "E-INPUT-SEND-REFUSED" in err and "(not_recorded)" in err and classifier.calls == []


def test_the_confirmation_lets_a_public_document_be_classified_and_a_notice_is_printed(tmp_path, two_pages):
    classifier = HostedClassifier({1: label(), 2: label(basis=PageBasis.STANDALONE, basis_conf=0.9)})

    code, _, err = cli(tmp_path, two_pages, "--confirm-public-document", env={"USE_JEV": "true"}, classifier=classifier)

    assert code == 0 and "will be sent to the hosted API" in err and classifier.calls == [1, 2]


def test_a_held_out_document_is_never_classified_whatever_the_flags(tmp_path, two_pages):
    classifier = HostedClassifier({1: label(), 2: label()})

    code, _, err = cli(tmp_path, two_pages, "--confirm-public-document", env={"USE_JEV": "true", "CREDIT_INTEL_PRIVATE_APPROVED": "1"}, classifier=classifier,
                       assignments=record(tmp_path, two_pages, "held_out"))  # fmt: skip

    assert code == 3 and "(held_out)" in err and classifier.calls == []


def test_a_document_under_private_is_refused_for_both_models_unless_the_owner_approved_the_run(tmp_path):
    (tmp_path / "private").mkdir()
    pdf = fx.balance_sheet_pdf(tmp_path / "private" / "report.pdf")
    tuning = record(tmp_path, pdf, "tuning")

    refused = cli(tmp_path, pdf, provider="openai", assignments=tuning)
    approved = cli(tmp_path, pdf, provider="openai", assignments=tuning, env={"CREDIT_INTEL_PRIVATE_APPROVED": "1"})
    unrecorded = cli(tmp_path, pdf, "--confirm-public-document", provider="openai", env={"CREDIT_INTEL_PRIVATE_APPROVED": "1"})

    assert refused[0] == 3 and "(private_path)" in refused[2]
    assert approved[0] == 0
    assert unrecorded[0] == 3 and "(private_path)" in unrecorded[2]


# --- the SDK is not even imported when the step is off ---------------------------------------------------------------------------


def test_a_fresh_process_without_use_jev_never_imports_the_sdk(tmp_path, two_pages):
    script = (
        "import io, sys\n"
        "from pathlib import Path\n"
        "import pipeline_fixture as fx\n"
        "from credit_intel.cli import main\n"
        "from credit_intel.llm.provider import FakeProvider\n"
        f"pdf = Path(r'{two_pages}')\n"
        f"config = Path(r'{tmp_path / 's.toml'}')\n"
        "config.write_text(" + repr(SETTINGS.format(provider="fake")) + ")\n"
        f"code = main([str(pdf), '--config', str(config), '--output-dir', r'{tmp_path / 'fresh'}'],\n"
        "            provider_factory=lambda s, e: FakeProvider(script=[fx.good_response(pdf)]),\n"
        f"            stdout=io.StringIO(), stderr=io.StringIO(), assignments=Path(r'{tmp_path / 'none.jsonl'}'), env={{}})\n"
        "print(code, 'typesafe_sdk' in sys.modules)\n"
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=tmp_path, env={"PYTHONPATH": str(Path(fx.__file__).parent), "PATH": "/usr/bin:/bin"})

    assert done.stdout.strip() == "0 False", done.stderr[-500:]
