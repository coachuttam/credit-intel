"""The record of where each closed phrase came from, and the fit of the tuning matches to it (Phase 7c, S-5). Synthetic labels only."""

import json
from pathlib import Path

import pytest

from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, load_current_sets
from credit_intel.evaluation.provenance import MEMBERS, ORIGINS, PROVENANCE_PATH, ProvenanceError, fit, inventory, load_provenance, main, summary
from credit_intel.evaluation.score import LabelsError
from credit_intel.models import FieldName as F
from test_score import full, write


def table(*rows):
    return {(r[0], r[1]): dict(zip(MEMBERS, r, strict=True)) for r in rows}


# --- the committed record ------------------------------------------------------------------------------------------------------------------


def test_the_record_and_the_configured_phrases_are_the_same_set_so_neither_can_drift():
    recorded = set(load_provenance())

    assert recorded == set(inventory()), (sorted(set(inventory()) - recorded)[:3], sorted(recorded - set(inventory()))[:3])
    assert len(inventory()) == len(set(inventory())) == len(recorded)


def test_every_line_has_the_members_in_order_a_known_origin_and_a_consistent_document_list():
    tuning = {document for document, kind in load_current_sets(ASSIGNMENTS_PATH).values() if kind == "tuning"}
    for line in PROVENANCE_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        assert tuple(row) == MEMBERS and row["origin"] in ORIGINS
        if row["origin"] in ("tuning_added", "tuning_added_unverified"):
            assert row["documents"] and set(row["documents"]) <= {"R1", "R2"} <= tuning
        else:
            assert row["documents"] == []
        assert row["date"] is None or (len(row["date"]) == 10 and row["date"][4] == row["date"][7] == "-")
        assert row["record"]


def test_no_held_out_document_or_hash_appears_in_the_record():
    text = PROVENANCE_PATH.read_text(encoding="utf-8")
    for sha, (document_id, kind) in load_current_sets(ASSIGNMENTS_PATH).items():
        if kind == "held_out":
            assert f'"{document_id}"' not in text
            assert sha not in text and sha[:12] not in text


def test_the_summary_counts_the_record_and_reports_no_difference_from_the_configured_lists():
    result = summary()

    assert result["not_in_record"] == 0 and result["recorded_but_not_configured"] == 0 and result["phrases"] == sum(result["by_origin"].values())
    assert set(result["by_origin"]) <= set(ORIGINS) and set(result["by_group"]) == {"borrowings", "label", "locator"}


def test_a_provenance_file_with_a_problem_is_refused(tmp_path):
    good = '{"list":"a","phrase":"b","origin":"prd_initial","documents":[],"date":null,"record":"r"}'
    cases = {
        "members": '{"phrase":"b","list":"a","origin":"prd_initial","documents":[],"date":null,"record":"r"}',
        "origin": good.replace("prd_initial", "guess"),
        "twice": good + "\n" + good,
        "json": "not json",
    }
    for name, text in cases.items():
        path = tmp_path / f"{name}.jsonl"
        path.write_text(text + "\n", encoding="utf-8")
        with pytest.raises(ProvenanceError):
            load_provenance(path)
    with pytest.raises(ProvenanceError):
        load_provenance(tmp_path / "missing.jsonl")


# --- the fit -------------------------------------------------------------------------------------------------------------------------------


def labelled(tmp_path, labels, document_id="R1", name="labels.json"):
    data = full()
    data["document_id"] = document_id
    for entry in data["entries"]:
        key = (F(entry["field"]), entry["period"])
        if key in labels:
            entry["row_label"] = labels[key]
    return write(tmp_path, data, name)


ROWS = table(
    ("label.revenue", "revenue from operations", "prd_initial", [], None, "t"),
    ("label.net_profit", "net income", "tuning_added", ["R2"], "2026-10-25", "t"),
    ("label.operating_profit", "operating income", "tuning_added_unverified", ["R2"], None, "t"),
    ("label.profit_before_tax", "profit before tax", "unverified", [], None, "t"),
    ("label.borrowings_current.sectioned", "borrowings", "prd_initial", [], None, "t"),
)
LABELS = {
    (F.REVENUE, "current"): "Revenue from operations",
    (F.NET_PROFIT, "current"): "Net income",
    (F.OPERATING_PROFIT, "current"): "Operating income",
    (F.PROFIT_BEFORE_TAX, "current"): "Profit before tax",
    (F.TOTAL_EQUITY, "current"): "Shareholders funds",  # not on any list
    (F.BORROWINGS_CURRENT, "current"): "Borrowings",
    (F.CURRENT_ASSETS, "current"): "Total current assets",  # on the list but not in this synthetic record
}


def test_each_row_label_is_counted_by_the_origin_of_the_phrase_that_accepts_it_relative_to_its_document(tmp_path):
    result = fit([labelled(tmp_path, LABELS, "R2")], ROWS)

    assert result["by_origin"] == {
        "prd_initial": 2, "added_from_this_document": 1, "added_from_this_document_unverified": 1, "unverified": 1, "off_list": 1, "not_recorded": 1,
    }  # fmt: skip
    assert result["row_labelled_entries"] == 7 and result["set"] == "tuning" and set(result["by_document"]) == {"R2"}


def test_a_phrase_added_from_another_tuning_document_is_counted_apart(tmp_path):
    result = fit([labelled(tmp_path, LABELS, "R1")], ROWS)

    assert result["by_origin"]["added_from_another_tuning_document"] == 1 and result["by_origin"]["added_from_another_tuning_document_unverified"] == 1
    assert "added_from_this_document" not in result["by_origin"]


def test_documents_are_summed_and_listed_separately(tmp_path):
    result = fit([labelled(tmp_path, LABELS, "R1", "a.json"), labelled(tmp_path, {(F.NET_PROFIT, "current"): "Net income"}, "R2", "b.json")], ROWS)

    assert result["by_document"]["R2"] == {"added_from_this_document": 1} and result["by_origin"]["added_from_this_document"] == 1
    assert result["row_labelled_entries"] == 8


def test_entries_without_a_row_label_or_labelled_absent_are_not_counted(tmp_path):
    assert fit([labelled(tmp_path, {})], ROWS)["row_labelled_entries"] == 0


def test_the_fit_report_holds_no_phrase_or_label(tmp_path):
    text = json.dumps(fit([labelled(tmp_path, LABELS, "R2")], ROWS)) + json.dumps(summary())

    for forbidden in ("Net income", "net income", "Shareholders funds", "Borrowings", "revenue from operations"):
        assert forbidden not in text


def test_the_real_record_classes_a_label_by_the_phrase_it_matches(tmp_path):
    result = fit([labelled(tmp_path, {(F.INTEREST_EXPENSE, "current"): "Finance cost", (F.REVENUE, "current"): "Revenue from operations"}, "R1")])

    assert result["by_origin"] == {"added_from_this_document": 1, "prd_initial": 1}


# --- the command ---------------------------------------------------------------------------------------------------------------------------


def run_main(capsys, *argv):
    code = main([*map(str, argv)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_command_prints_the_inventory_and_the_fit_and_refuses_a_bad_file(tmp_path, capsys):
    code, out, err = run_main(capsys, "--inventory", "--fit", labelled(tmp_path, LABELS, "R2"))
    bad = Path(tmp_path / "bad.json")
    bad.write_text("[]", encoding="utf-8")
    code2, out2, err2 = run_main(capsys, "--fit", bad)

    assert code == 0 and err == "" and out.count("provenance: ") == 2 and '"not_in_record": 0' in out
    assert code2 == 2 and out2 == "" and "provenance: refused" in err2
    with pytest.raises(SystemExit) as stop:
        main([])
    assert stop.value.code == 2
    with pytest.raises(LabelsError):
        fit([bad])


def test_a_phrase_with_an_apostrophe_is_found_in_the_record_as_it_is_configured(tmp_path):
    result = fit([labelled(tmp_path, {(F.TOTAL_EQUITY, "current"): "Total stockholders' equity"}, "R2")])

    assert result["by_origin"] == {"added_from_this_document": 1}


def test_the_summary_counts_differences_between_a_record_and_the_configured_lists():
    short = table(("label.revenue", "revenue", "prd_initial", [], None, "t"), ("label.revenue", "sales", "prd_initial", [], None, "t"))
    result = summary(short)

    assert result["phrases"] == 2 and result["recorded_but_not_configured"] == 1 and result["not_in_record"] == len(set(inventory())) - 1
