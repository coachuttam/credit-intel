"""The ablation: a tuning document scored without the phrases added from tuning documents (Phase 7c). Synthetic documents and records only."""

import json
from dataclasses import fields

import pytest

from credit_intel.config import BorrowingSettings, LabelSettings, LocatorSettings
from credit_intel.evaluation.ablation import MODES, counts_of, dropped, label_settings_without, locator_settings_without, main, run
from credit_intel.evaluation.guard import SendRefused
from credit_intel.evaluation.provenance import MEMBERS, inventory
from credit_intel.evaluation.score import LabelsError
from test_score_run import config, fill_cache, in_a_scratch_directory, labels_file, pdf, records, settings_for  # noqa: F401  (fixtures and builders of the scorer's own tests)


def table(*rows):
    return {(r[0], r[1]): dict(zip(MEMBERS, r, strict=True)) for r in rows}


ROWS = table(
    ("label.profit_before_tax", "profit before tax", "tuning_added", ["R9"], None, "t"),
    ("label.revenue", "total revenue", "tuning_added", ["R2"], None, "t"),
    ("label.net_profit", "net income", "tuning_added_unverified", ["R2"], None, "t"),
    ("label.operating_profit", "operating income", "prd_initial", [], None, "t"),
    ("label.total_equity", "total stockholders' equity", "unverified", [], None, "t"),
    ("label.borrowings_current.sectioned", "borrowings", "tuning_added", ["R9"], None, "t"),
    ("locator.title.balance_sheet", "balance sheets", "tuning_added", ["R9"], None, "t"),
    ("locator.line_item.income_statement", "net income", "tuning_added", ["R9"], None, "t"),
    ("locator.title_prefix", "consolidated", "tuning_added", ["R9"], None, "t"),
    ("locator.other_statement_title", "comprehensive income statements", "tuning_added_unverified", ["R9"], None, "t"),
)


# --- which phrases go ---------------------------------------------------------------------------------------------------------------------


def test_own_drops_what_was_added_from_this_document_and_added_drops_every_addition():
    assert dropped(ROWS, "R9", "own") == {k for k in ROWS if k in {("label.profit_before_tax", "profit before tax"), ("label.borrowings_current.sectioned", "borrowings"), ("locator.title.balance_sheet", "balance sheets"), ("locator.line_item.income_statement", "net income"), ("locator.title_prefix", "consolidated"), ("locator.other_statement_title", "comprehensive income statements")}}
    assert dropped(ROWS, "R1", "own") == set()
    assert len(dropped(ROWS, "R1", "added")) == 8  # unverified additions count; initial, rule-defined and unverified-without-document do not


def test_a_mode_outside_the_list_is_refused():
    assert MODES == ("own", "added")
    with pytest.raises(ValueError, match="mode must be"):
        dropped(ROWS, "R9", "everything")


def test_the_label_settings_lose_exactly_the_dropped_phrases_and_nothing_else():
    drop = {("label.profit_before_tax", "profit before tax"), ("label.borrowings_current.sectioned", "borrowings")}
    settings, base = label_settings_without(drop), LabelSettings()

    assert "profit before tax" not in settings.rules["profit_before_tax"].phrases and "profit/(loss) before tax" in settings.rules["profit_before_tax"].phrases
    assert settings.rules["borrowings_current"].sectioned_phrases == () and settings.rules["borrowings_current"].phrases == base.rules["borrowings_current"].phrases
    assert settings.rules["borrowings_current"].section == base.rules["borrowings_current"].section
    assert {f: r for f, r in settings.rules.items() if f not in ("profit_before_tax", "borrowings_current")} == {f: r for f, r in base.rules.items() if f not in ("profit_before_tax", "borrowings_current")}
    assert settings.section_headings == base.section_headings and settings.currency_symbols == base.currency_symbols


def test_nothing_dropped_means_the_default_settings():
    assert label_settings_without(set()) == LabelSettings() and locator_settings_without(set()) == LocatorSettings()


def test_the_locator_settings_lose_exactly_the_dropped_phrases():
    drop = {("locator.title.balance_sheet", "balance sheets"), ("locator.line_item.income_statement", "net income"), ("locator.title_prefix", "consolidated"),
            ("locator.other_statement_title", "comprehensive income statements")}  # fmt: skip
    settings, base = locator_settings_without(drop), LocatorSettings()

    assert "balance sheets" not in settings.title_phrases["balance_sheet"] and "balance sheet" in settings.title_phrases["balance_sheet"]
    assert "net income" not in settings.line_item_phrases["income_statement"] and "total revenue" in settings.line_item_phrases["income_statement"]
    assert settings.title_prefix_words == ("standalone", "separate") and settings.other_statement_title_phrases == ()
    assert settings.basis_phrases == base.basis_phrases and settings.prefix_connectors == base.prefix_connectors and settings.title_phrases["income_statement"] == base.title_phrases["income_statement"]
    assert {f.name for f in fields(settings)} == {f.name for f in fields(base)}


def test_the_whole_default_inventory_is_reachable_by_a_drop_key():
    keys = set(inventory())
    assert all(isinstance(k, tuple) and len(k) == 2 for k in keys)
    cut = locator_settings_without(keys), label_settings_without(keys)
    assert all(not p for rule in cut[1].rules.values() for p in rule.phrases + rule.sectioned_phrases)
    assert all(not v for v in cut[0].title_phrases.values()) and not cut[0].title_prefix_words and not cut[0].other_statement_title_phrases
    assert BorrowingSettings()  # the borrowings lists are not cut by this tool (documented)


def test_counts_hold_no_phrase_or_label():
    text = json.dumps(counts_of({"replayed": True, "counts": {"sc01": {"match": 1, "of": 2}, "sc02": {}, "sc03": {"correct": 0, "of": 0}}, "stages": {"x": 1}, "statuses": {}, "reasons": {}}))
    assert '"sc01": "1/2"' in text and '"sc03": "0/0"' in text and counts_of({"replayed": False, "reason": "cache_miss"}) == {"replayed": False, "reason": "cache_miss"}


# --- the replay ----------------------------------------------------------------------------------------------------------------------------


def test_without_a_phrase_added_from_the_document_its_entries_fall_and_the_stage_says_where(pdf, tmp_path, config):
    fill_cache(pdf, tmp_path)
    provenance = table(("label.profit_before_tax", "profit before tax", "tuning_added", ["R9"], None, "t"))
    result = run(pdf, labels_file(tmp_path, pdf), mode="own", locator=False, table=provenance, assignments=records(tmp_path, pdf),
                 cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))  # fmt: skip

    assert result["baseline"]["sc01"] == "16/16" and result["without"]["sc01"] == "14/16" and result["phrases_removed"] == 1
    assert sum(result["without"]["stages"].values()) == 2 and result["set"] == "tuning"


def test_another_documents_additions_do_not_touch_this_document_in_own_mode_but_do_in_added_mode(pdf, tmp_path, config):
    fill_cache(pdf, tmp_path)
    provenance = table(("label.profit_before_tax", "profit before tax", "tuning_added", ["R2"], None, "t"))
    kw = dict(assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))
    own = run(pdf, labels_file(tmp_path, pdf), mode="own", locator=False, table=provenance, **kw)
    added = run(pdf, labels_file(tmp_path, pdf), mode="added", locator=False, table=provenance, **kw)

    assert own["without"]["sc01"] == "16/16" and added["without"]["sc01"] == "14/16"


def test_cutting_the_locator_phrases_stops_a_run_that_uses_the_locator_and_leaves_the_baseline_alone(pdf, tmp_path, config):
    fill_cache(pdf, tmp_path)
    kw = dict(assignments=records(tmp_path, pdf), cache_dir=tmp_path / ".cache" / "llm", llm=settings_for(config))
    titles = table(("locator.title.balance_sheet", "balance sheet", "tuning_added", ["R9"], None, "t"), ("locator.line_item.balance_sheet", "total current assets", "tuning_added", ["R9"], None, "t"))
    prefix = table(("locator.title_prefix", "consolidated", "tuning_added", ["R9"], None, "t"))
    no_pages = run(pdf, labels_file(tmp_path, pdf), mode="own", locator=True, table=titles, **kw)
    no_basis = run(pdf, labels_file(tmp_path, pdf), mode="own", locator=True, table=prefix, **kw)
    kept = run(pdf, labels_file(tmp_path, pdf), mode="own", locator=False, table=titles, **kw)  # the same phrases, locator not cut

    assert no_pages["locator_cut"] is True and no_pages["baseline"]["sc01"] == "16/16" and no_pages["without"] == {"replayed": False, "reason": "E-EXTRACT-NO-STATEMENT-PAGES"}
    assert no_basis["without"]["replayed"] is False and no_basis["without"]["reason"] in ("E-EXTRACT-NO-STATEMENT-PAGES", "E-EXTRACT-BASIS-UNAVAILABLE")
    assert kept["locator_cut"] is False and kept["without"]["sc01"] == "16/16"


def test_a_held_out_document_is_refused_and_an_empty_cache_is_reported_not_retried(pdf, tmp_path, config):
    provenance = table(("label.profit_before_tax", "profit before tax", "tuning_added", ["R9"], None, "t"))
    with pytest.raises(SendRefused, match="held out"):
        run(pdf, labels_file(tmp_path, pdf), mode="own", locator=False, table=provenance, assignments=records(tmp_path, pdf, "held_out"), llm=settings_for(config))
    empty = run(pdf, labels_file(tmp_path, pdf), mode="own", locator=False, table=provenance, assignments=records(tmp_path, pdf), cache_dir=tmp_path / "empty", llm=settings_for(config))

    assert empty["baseline"] == {"replayed": False, "reason": "cache_miss"} and empty["without"] == {"replayed": False, "reason": "cache_miss"}


def test_labels_for_another_document_are_refused(pdf, tmp_path, config):
    provenance = table(("label.profit_before_tax", "profit before tax", "tuning_added", ["R9"], None, "t"))
    with pytest.raises(LabelsError, match="not written for this document"):
        run(pdf, labels_file(tmp_path, pdf, document_id="R2"), mode="own", locator=False, table=provenance, assignments=records(tmp_path, pdf), llm=settings_for(config))


def test_the_command_prints_counts_only_and_refuses_with_exit_2(pdf, tmp_path, config, capsys):
    fill_cache(pdf, tmp_path)
    code = main(["--mode", "own", "--report", str(pdf), str(labels_file(tmp_path, pdf)), "--assignments", str(records(tmp_path, pdf, "held_out")), "--config", str(config)])
    captured = capsys.readouterr()

    assert code == 2 and captured.out == "" and "ablation: refused" in captured.err and "352.70" not in captured.err
    with pytest.raises(SystemExit) as stop:
        main(["--report", str(pdf), str(labels_file(tmp_path, pdf))])
    assert stop.value.code == 2
