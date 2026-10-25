"""The evaluation of Jev + OpenAI against OpenAI-only: the estimate, the live gate, the comparison, and the guards (PRD v0.4.31; B-300). Mocked clients; no network."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal

import pytest

import pipeline_fixture as fx
from credit_intel.config import JevSettings, PricingSettings
from credit_intel.evaluation.gate import GateReferenceError
from credit_intel.evaluation.guard import ENV_PRIVATE_APPROVED, MEMBERS, SendRefused, file_sha256
from credit_intel.evaluation.jev_eval import evaluate, main, verdict, worst_case_usd
from credit_intel.llm.provider import FakeProvider
from credit_intel.pagefilter.classifier import FakeClassifier
from credit_intel.pagefilter.labels import ClassifierError, PageBasis, PageClassification, PageType

PRICES = PricingSettings(Decimal("0.15"), Decimal("0.60"))
JEV = JevSettings(enabled=True, price_input_per_million=Decimal("0.042"))
SETTINGS = '[llm]\nprovider = "openai"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n[pricing]\ninput_per_million = 0.15\noutput_per_million = 0.60\n'


def label(page_type=PageType.BALANCE_SHEET, conf=0.95, basis=PageBasis.CONSOLIDATED, basis_conf=0.9, tokens=500):
    return PageClassification(page_type, conf, basis, basis_conf, "jev-1.14.0", tokens, 20)


def classifier():
    return FakeClassifier({1: label(), 2: label(basis=PageBasis.STANDALONE, basis_conf=0.92)})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pdf = fx.two_basis_pdf(tmp_path / "statement.pdf")
    records = tmp_path / "assignments.jsonl"
    records.write_text(json.dumps(dict(zip(MEMBERS, ("R9", file_sha256(pdf), "tuning", "2026-10-24", "assigned", None, None), strict=True))) + "\n", encoding="utf-8")
    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS, encoding="utf-8")
    return pdf, records, config


def run_main(pdf, records, config, tmp_path, *argv, env=None, provider=None, classifier_=None):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([str(pdf), "--config", str(config), *argv], env=env or {}, provider=provider, classifier=classifier_, assignments=records, cache_dir=tmp_path / "cache")
    return code, out.getvalue(), err.getvalue()


# --- the estimate: offline, free, no key ----------------------------------------------------------------------------------------------


def test_the_default_prints_an_estimate_and_makes_no_call(setup, tmp_path):
    pdf, records, config = setup
    provider, fake = FakeProvider(), classifier()

    code, out, _ = run_main(pdf, records, config, tmp_path, env={"CREDIT_INTEL_JEV_PRICE_INPUT_PER_MILLION": "0.042"}, provider=provider, classifier_=fake)

    estimate = json.loads(out.split("jev eval estimate: ", 1)[1])
    assert code == 0 and provider.calls == [] and fake.calls == []
    assert estimate["jev"]["pages_read"] == 2 and estimate["jev"]["estimated_input_tokens"] > 0 and estimate["jev"]["estimated_cost_usd"] is not None
    assert estimate["worst_case_usd_evaluation"] is not None and "Acme" not in out and "1,482.30" not in out


def test_the_estimate_can_include_every_page(setup, tmp_path):
    pdf, records, config = setup

    _, out, _ = run_main(pdf, records, config, tmp_path, "--all-pages")

    estimate = json.loads(out.split("jev eval estimate: ", 1)[1])
    assert estimate["jev"]["all_pages"] and estimate["jev"]["pages_read"] == 2  # the synthetic document has two pages with text


def test_the_worst_case_adds_the_jev_cost_to_two_openai_calls():
    estimate = {"jev": {"estimated_cost_usd": "0.0001"}, "worst_case_usd_one_call": "0.005"}

    assert worst_case_usd(estimate) == Decimal("0.0101") and worst_case_usd({"jev": {"estimated_cost_usd": None}, "worst_case_usd_one_call": "0.005"}) is None


# --- the live gate: nothing is called unless the spend is covered ---------------------------------------------------------------------


def test_live_needs_a_maximum_spend_that_covers_the_worst_case(setup, tmp_path):
    pdf, records, config = setup
    provider, fake = FakeProvider(), classifier()
    env = {"CREDIT_INTEL_JEV_PRICE_INPUT_PER_MILLION": "0.042"}

    none = run_main(pdf, records, config, tmp_path, "--live", env=env, provider=provider, classifier_=fake)
    low = run_main(pdf, records, config, tmp_path, "--live", "--max-spend", "0.0001", env=env, provider=provider, classifier_=fake)

    assert none[0] == 1 and "--max-spend" in none[2] and low[0] == 1 and "worst case" in low[2]
    assert provider.calls == [] and fake.calls == []


def test_live_needs_both_prices_so_the_worst_case_can_be_bounded(setup, tmp_path):
    pdf, records, config = setup

    code, _, err = run_main(pdf, records, config, tmp_path, "--live", "--max-spend", "1", env={}, provider=FakeProvider(), classifier_=classifier())

    assert code == 1 and "prices" in err


def test_a_covered_live_run_compares_the_two_modes_and_prints_counts_only(setup, tmp_path):
    pdf, records, config = setup
    provider = FakeProvider(script=[fx.good_response(pdf), fx.good_response(pdf)])
    env = {"CREDIT_INTEL_JEV_PRICE_INPUT_PER_MILLION": "0.042", "CREDIT_INTEL_TOKEN_CEILING": "1000000"}

    code, out, _ = run_main(pdf, records, config, tmp_path, "--live", "--max-spend", "1", env=env, provider=provider, classifier_=classifier())

    result = json.loads(out.split("jev eval: ", 1)[1])
    assert code == 0 and len(provider.calls) == 2  # one call per mode: the replies differ in cache key because the pages sent differ
    assert result["openai_only"]["openai"]["pages_sent"] == [1, 2] and result["jev_plus_openai"]["openai"]["pages_sent"] == [1]
    v = result["verdict"]
    assert v["fields_not_lost"] and v["fields_lost"] == 0 and v["openai_input_tokens_lower"] and v["pages_dropped"] == [2] and v["fallbacks"] == 0
    assert result["jev_plus_openai"]["page_filter"]["jev_input_tokens"] == 1000 and result["jev_plus_openai"]["page_filter"]["jev_cost_usd"] == "0.000042"
    assert "Acme" not in out and "1,482.30" not in out and "Consolidated" not in out


def test_the_page_agreement_counts_the_labels_against_the_locator_and_the_title(setup, tmp_path):
    pdf, records, config = setup
    provider = FakeProvider(script=[fx.good_response(pdf), fx.good_response(pdf)])

    result = evaluate(pdf, fx.LLM, provider, classifier(), JEV, pricing=PRICES, assignments=records, cache_dir=tmp_path / "cache", env={})

    agreement = result["jev_plus_openai"]["agreement"]
    assert agreement["type_compared"] == 2 and agreement["type_agree"] == 2  # both pages are balance sheets to the locator and to Jev
    assert agreement["basis_compared"] == 2 and agreement["basis_agree"] == 2  # page 1 titled consolidated, page 2 standalone


def test_a_failing_classifier_gives_the_same_extraction_and_the_verdict_says_so(setup, tmp_path):
    pdf, records, config = setup
    provider = FakeProvider(script=[fx.good_response(pdf)])  # the second mode sends the same pages, so it is a cache hit
    failing = FakeClassifier({1: ClassifierError("timeout"), 2: ClassifierError("server")})

    result = evaluate(pdf, fx.LLM, provider, failing, JEV, pricing=PRICES, assignments=records, cache_dir=tmp_path / "cache", env={})

    assert len(provider.calls) == 1 and result["verdict"]["fields_not_lost"] and result["verdict"]["openai_input_tokens_delta"] == 0
    assert result["verdict"]["fallbacks"] == 2 and result["verdict"]["pages_dropped"] == [] and not result["verdict"]["openai_input_tokens_lower"]


def test_all_pages_finds_statement_pages_the_locator_did_not_select(setup, tmp_path):
    pdf, records, config = setup
    provider = FakeProvider(script=[fx.good_response(pdf), fx.good_response(pdf)])
    seen = []

    def script(page, text):
        seen.append(page)
        return label(PageType.PROFIT_LOSS, 0.97)

    result = evaluate(pdf, fx.LLM, provider, FakeClassifier(script), JEV, pricing=PRICES, assignments=records, cache_dir=tmp_path / "cache", env={}, all_pages=True,
                      page_range="1")  # only page 1 is the candidate, so page 2 is outside it  # fmt: skip

    assert result["locator_check"] == {"classified_outside_candidates": 1, "statement_pages_found": [2], "errors": 0}


def test_a_range_is_filtered_in_the_evaluation_so_that_what_it_would_remove_can_be_measured(setup, tmp_path):
    pdf, records, config = setup
    provider = FakeProvider(script=[fx.good_response(pdf), fx.good_response(pdf)])

    result = evaluate(pdf, fx.LLM, provider, classifier(), JEV, pricing=PRICES, assignments=records, cache_dir=tmp_path / "cache", env={}, page_range="1-2")

    assert result["openai_only"]["openai"]["pages_sent"] == [1, 2] and result["jev_plus_openai"]["openai"]["pages_sent"] == [1]


# --- the guards: neither model is ever run on a document that may not be sent -------------------------------------------------------


def test_a_held_out_document_is_refused_before_anything_is_read_or_called(setup, tmp_path):
    pdf, records, config = setup
    held = tmp_path / "held.jsonl"
    held.write_text(records.read_text().replace('"tuning"', '"held_out"'), encoding="utf-8")
    provider, fake = FakeProvider(), classifier()

    with pytest.raises(SendRefused):
        evaluate(pdf, fx.LLM, provider, fake, JEV, assignments=held, cache_dir=tmp_path / "cache", env={})

    assert provider.calls == [] and fake.calls == []


def test_a_document_that_is_not_recorded_is_refused(setup, tmp_path):
    pdf, _, _ = setup

    with pytest.raises(SendRefused):
        evaluate(pdf, fx.LLM, FakeProvider(), classifier(), JEV, assignments=tmp_path / "none.jsonl", cache_dir=tmp_path / "cache", env={})


def test_a_document_under_private_needs_the_owners_approval_of_the_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "private").mkdir()
    pdf = fx.two_basis_pdf(tmp_path / "private" / "report.pdf")
    records = tmp_path / "assignments.jsonl"
    records.write_text(json.dumps(dict(zip(MEMBERS, ("R9", file_sha256(pdf), "tuning", "2026-10-24", "assigned", None, None), strict=True))) + "\n", encoding="utf-8")
    provider, fake = FakeProvider(), classifier()

    with pytest.raises(SendRefused):
        evaluate(pdf, fx.LLM, provider, fake, JEV, assignments=records, cache_dir=tmp_path / "cache", env={})
    assert provider.calls == [] and fake.calls == []
    provider = FakeProvider(script=[fx.good_response(pdf), fx.good_response(pdf)])
    result = evaluate(pdf, fx.LLM, provider, classifier(), JEV, assignments=records, cache_dir=tmp_path / "cache", env={ENV_PRIVATE_APPROVED: "1"})
    assert result["document_id"] == "R9"


def test_main_reports_a_refusal_without_a_trace_or_a_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pdf = fx.two_basis_pdf(tmp_path / "statement.pdf")
    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS, encoding="utf-8")
    provider, fake = FakeProvider(), classifier()

    code, out, err = run_main(pdf, tmp_path / "none.jsonl", config, tmp_path, "--live", "--max-spend", "1", env={"CREDIT_INTEL_JEV_PRICE_INPUT_PER_MILLION": "0.042"}, provider=provider, classifier_=fake)

    assert code == 1 and out == "" and "refused" in err and "Traceback" not in err and provider.calls == [] and fake.calls == []


def test_a_live_run_without_the_owners_token_ceiling_stops_before_any_call(setup, tmp_path):
    pdf, records, config = setup
    config.write_text(SETTINGS.replace("token_ceiling = 1000000\n", ""), encoding="utf-8")  # OD-8: the ceiling has no default
    provider, fake = FakeProvider(), classifier()

    code, _, err = run_main(pdf, records, config, tmp_path, "--live", "--max-spend", "1", env={"CREDIT_INTEL_JEV_PRICE_INPUT_PER_MILLION": "0.042"}, provider=provider, classifier_=fake)

    assert code == 1 and "E-CONFIG-INVALID" in err and provider.calls == [] and fake.calls == []


def test_a_reference_for_another_document_is_refused(setup, tmp_path):
    pdf, records, config = setup
    from credit_intel.evaluation.gate import Reference

    other = Reference("R9", "0" * 64, StatementBasis_CONSOLIDATED, None, None, ())

    with pytest.raises(GateReferenceError):
        evaluate(pdf, fx.LLM, FakeProvider(), classifier(), JEV, reference=other, assignments=records, cache_dir=tmp_path / "cache", env={})


StatementBasis_CONSOLIDATED = __import__("credit_intel.models", fromlist=["StatementBasis"]).StatementBasis.CONSOLIDATED


# --- the verdict -----------------------------------------------------------------------------------------------------------------------


def mode(tokens, cost, extracted, counts=None):
    out = {"openai": {"openai_input_tokens": tokens, "openai_cost_usd": cost}, "extracted_fields": extracted}
    if counts:
        out["openai"]["gate_counts"] = counts
    return out


def page_filter(cost="0.0001", dropped=(2,), fallbacks=0, latency=300):
    return {"jev_cost_usd": cost, "pages_dropped": list(dropped), "fallbacks": fallbacks, "latency_ms": latency}


def test_the_verdict_reports_lost_and_gained_fields_tokens_and_the_total_cost():
    plain = mode(3000, "0.0010", [("revenue", "current"), ("net_profit", "current")])
    jev = {**mode(2500, "0.0009", [("revenue", "current"), ("profit_before_tax", "current")]), "page_filter": page_filter()}

    v = verdict(plain, jev, False)

    assert v["fields_lost"] == 1 and not v["fields_not_lost"] and v["fields_gained"] == 1 and v["openai_input_tokens_delta"] == -500 and v["openai_input_tokens_lower"]
    assert v["total_cost_usd_openai_only"] == "0.0010" and v["total_cost_usd_jev_plus_openai"] == "0.0010" and not v["total_cost_lower"] and v["latency_added_ms"] == 300


def test_the_verdict_says_when_the_total_cost_is_lower_and_when_matches_are_lost():
    plain = mode(3000, "0.0010", [("revenue", "current")], {"match": 2, "mismatch": 0, "missing": 4})
    better = {**mode(2000, "0.0006", [("revenue", "current")], {"match": 2, "mismatch": 0, "missing": 4}), "page_filter": page_filter("0.00005")}
    worse = {**mode(2000, "0.0006", [("revenue", "current")], {"match": 1, "mismatch": 1, "missing": 4}), "page_filter": page_filter("0.00005")}

    assert verdict(plain, better, True)["total_cost_lower"] and verdict(plain, better, True)["matches_not_lost"]
    assert not verdict(plain, worse, True)["matches_not_lost"]


# --- the dry run's estimate of the classifier ---------------------------------------------------------------------------------------------


def test_the_dry_run_adds_the_classifier_estimate_only_when_asked(setup):
    from credit_intel.evaluation.dry_run import dry_run

    pdf, records, _ = setup

    plain = dry_run(pdf, fx.LLM, pricing=PRICES, assignments=records)
    with_jev = dry_run(pdf, fx.LLM, pricing=PRICES, assignments=records, jev=JEV)
    everything = dry_run(pdf, fx.LLM, pricing=PRICES, assignments=records, jev=JEV, jev_all_pages=True)

    assert "jev" not in plain
    assert with_jev["jev"]["pages_read"] == 2 and with_jev["jev"]["model"] == "jev-latest" and not with_jev["jev"]["all_pages"]
    assert with_jev["jev"]["estimated_cost_usd"] == format(Decimal(with_jev["jev"]["estimated_input_tokens"]) * Decimal("0.042") / Decimal(1_000_000), "f")
    assert {k: v for k, v in with_jev.items() if k != "jev"} == plain  # the rest of the dry run is unchanged
    assert everything["jev"]["all_pages"] and everything["jev"]["pages_read"] == 2


def test_the_estimate_has_no_cost_without_a_price(setup):
    from credit_intel.evaluation.dry_run import dry_run

    pdf, records, _ = setup

    assert dry_run(pdf, fx.LLM, assignments=records, jev=JevSettings(enabled=True))["jev"]["estimated_cost_usd"] is None
