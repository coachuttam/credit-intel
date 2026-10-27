"""The SC-12 counting report (PRD SC-12, OD-3, v0.4.49): per-document recall of the locator against a labels file.

Synthetic documents and synthetic page lists only. The messages are checked for the absence of the page lists they were given.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from credit_intel.config import LocatorSettings
from credit_intel.evaluation import recall
from credit_intel.evaluation.guard import MEMBERS, SendRefused
from credit_intel.evaluation.recall import LabelsError, load_labels, parse_labels, report_document, score_document, summary
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.locator import locate_statements
from test_locator import BALANCE_SHEET, BALANCE_SHEET_CONTINUED, CONTENTS, NOTE_21, PROFIT_AND_LOSS

SHA = "a" * 64


def labels_text(income=(2,), balance=(3,), sha=SHA, doc="T1"):
    return json.dumps({"document_id": doc, "sha256": sha, "statement_pages": {"income_statement": list(income), "balance_sheet": list(balance)}})


def record_line(document_id, sha, set_):
    return json.dumps(dict(zip(MEMBERS, [document_id, sha, set_, "2026-10-27", "assigned", None, None])), separators=(",", ":"))


def assignments(tmp_path, pdf, set_="tuning", doc="T1"):
    path = tmp_path / "assignments.jsonl"
    path.write_text(record_line(doc, hashlib.sha256(pdf.read_bytes()).hexdigest(), set_) + "\n", encoding="utf-8")
    return path


def labels_file(tmp_path, pdf, income=(2,), balance=(3,), doc="T1"):
    path = tmp_path / "labels.json"
    path.write_text(labels_text(income, balance, hashlib.sha256(pdf.read_bytes()).hexdigest(), doc), encoding="utf-8")
    return path


PAGES = [CONTENTS, PROFIT_AND_LOSS, BALANCE_SHEET, BALANCE_SHEET_CONTINUED, NOTE_21]


# --- labels files ----------------------------------------------------------------------------------------


def test_a_valid_labels_file_is_read():
    labels = parse_labels(labels_text(income=(2, 3), balance=(3, 4)))
    assert labels.income_statement == (2, 3) and labels.balance_sheet == (3, 4) and labels.pages == (2, 3, 4)


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"document_id": "T1", "sha256": SHA}),
        json.dumps({"sha256": SHA, "document_id": "T1", "statement_pages": {"income_statement": [1], "balance_sheet": [2]}}),
        labels_text(sha="A" * 64),
        labels_text(sha="a" * 63),
        labels_text(doc=""),
        labels_text(income=()),
        labels_text(balance=()),
        labels_text(income=(0,)),
        labels_text(income=(3, 2)),
        labels_text(income=(2, 2)),
        json.dumps({"document_id": "T1", "sha256": SHA, "statement_pages": {"balance_sheet": [1], "income_statement": [2]}}),
        json.dumps({"document_id": "T1", "sha256": SHA, "statement_pages": {"income_statement": [True], "balance_sheet": [2]}}),
        json.dumps({"document_id": "T1", "sha256": SHA, "statement_pages": {"income_statement": ["2"], "balance_sheet": [2]}}),
    ],
)
def test_a_malformed_labels_file_is_refused_without_repeating_its_pages(text):
    with pytest.raises(LabelsError) as error:
        parse_labels(text)
    assert "777" not in str(error.value)


def test_an_oversize_or_missing_labels_file_is_refused(tmp_path):
    big = tmp_path / "big.json"
    big.write_text(" " * (recall.MAX_BYTES + 1), encoding="utf-8")
    with pytest.raises(LabelsError):
        load_labels(big)
    with pytest.raises(LabelsError):
        load_labels(tmp_path / "absent.json")


# --- scoring -----------------------------------------------------------------------------------------------


def located(pages=PAGES, settings=None, tmp_path=None):
    from credit_intel.ingestion.models import PageText

    return locate_statements([PageText(i, t) for i, t in enumerate(pages, start=1)], settings)


def test_every_labelled_page_found_passes():
    result = score_document(parse_labels(labels_text(income=(2,), balance=(3, 4))), located())
    assert (result.found, result.missed, result.cap_limited, result.passed) == (3, (), False, True)
    assert result.truth_pages == 3 and result.candidate_pages >= 3


def test_one_missed_page_fails_and_is_listed():
    result = score_document(parse_labels(labels_text(income=(2,), balance=(3,))), located([CONTENTS, PROFIT_AND_LOSS, NOTE_21]))
    assert result.missed == (3,) and not result.passed and result.found == 1


def test_a_page_labelled_in_both_statements_counts_once():
    result = score_document(parse_labels(labels_text(income=(2,), balance=(2,))), located())
    assert result.truth_pages == 1 and result.passed


def test_extra_candidates_do_not_fail_the_document():
    result = score_document(parse_labels(labels_text(income=(2,), balance=(3,))), located())
    assert result.candidate_pages > result.truth_pages and result.passed


def test_a_cap_limited_document_fails_even_if_every_labelled_page_is_found():
    settings = replace(LocatorSettings(), max_candidates=3)
    pages = [PROFIT_AND_LOSS, BALANCE_SHEET, PROFIT_AND_LOSS, BALANCE_SHEET, PROFIT_AND_LOSS]
    result = score_document(parse_labels(labels_text(income=(1,), balance=(1,))), located(pages, settings))
    assert result.cap_limited and result.qualifying_pages > 3 and not result.passed
    assert result.missed == ()  # page 1 is kept: the document fails on the cap alone


def test_a_page_range_is_not_a_locator_result():
    from credit_intel.ingestion.models import PageText

    ranged = locate_statements([PageText(i, t) for i, t in enumerate(PAGES, start=1)], None, "2-3")
    with pytest.raises(LabelsError):
        score_document(parse_labels(labels_text()), ranged)


def test_a_label_outside_the_document_is_refused():
    with pytest.raises(LabelsError):
        score_document(parse_labels(labels_text(income=(2,), balance=(9,))), located(), page_count=5)


def test_the_summary_counts_documents_not_pages():
    ok = score_document(parse_labels(labels_text()), located())
    bad = score_document(parse_labels(labels_text(balance=(5,))), located([CONTENTS, PROFIT_AND_LOSS, NOTE_21, NOTE_21, NOTE_21]))
    out = summary([ok, bad])
    assert out["passed"] == 1 and out["of"] == 2 and out["set"] == "tuning"
    assert set(out) == {"set", "documents", "passed", "of"}


# --- the report on a document ----------------------------------------------------------------------------


def test_report_document_on_a_tuning_pdf(tmp_path, make_pdf):
    pdf = make_pdf(PAGES)
    result = report_document(pdf, labels_file(tmp_path, pdf), assignments=assignments(tmp_path, pdf))
    assert result.passed and result.document_id == "T1"


def test_report_refuses_a_held_out_document_before_reading_it(tmp_path, make_pdf, monkeypatch):
    pdf = make_pdf(PAGES)
    monkeypatch.setattr(recall, "ingest", lambda *_: pytest.fail("a held-out page was read"))
    with pytest.raises(SendRefused):
        report_document(pdf, labels_file(tmp_path, pdf), assignments=assignments(tmp_path, pdf, set_="held_out"))


def test_report_refuses_labels_for_another_document_or_an_unrecorded_one(tmp_path, make_pdf):
    pdf = make_pdf(PAGES)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(labels_text(sha="b" * 64), encoding="utf-8")
    with pytest.raises(LabelsError):
        report_document(pdf, wrong, assignments=assignments(tmp_path, pdf))
    with pytest.raises(LabelsError):
        report_document(pdf, labels_file(tmp_path, pdf, doc="OTHER"), assignments=assignments(tmp_path, pdf))
    absent = tmp_path / "empty.jsonl"
    absent.write_text("", encoding="utf-8")
    with pytest.raises(LabelsError):
        report_document(pdf, labels_file(tmp_path, pdf), assignments=absent)


# --- the command line --------------------------------------------------------------------------------------


def test_check_labels_prints_a_count_not_the_pages(tmp_path, capsys):
    path = tmp_path / "labels.json"
    path.write_text(labels_text(income=(2, 7), balance=(3,)), encoding="utf-8")
    assert recall.main(["--check-labels", str(path)]) == 0
    out = capsys.readouterr().out
    assert '"pages": 3' in out and "7" not in out.replace('"pages": 3', "")


def test_check_labels_reports_a_bad_file_with_exit_1(tmp_path, capsys):
    path = tmp_path / "labels.json"
    path.write_text("nope", encoding="utf-8")
    assert recall.main(["--check-labels", str(path)]) == 1
    assert "unusable" in capsys.readouterr().err


def test_the_command_line_needs_exactly_one_mode(tmp_path):
    with pytest.raises(SystemExit):
        recall.main([])


def test_the_report_command_prints_counts_only(tmp_path, make_pdf, monkeypatch, capsys):
    pdf = make_pdf(PAGES)
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    monkeypatch.setattr(recall, "load_current_sets", lambda *a, **k: {sha: ("T1", "tuning")})
    monkeypatch.setattr(recall, "refuse_if_held_out", lambda *a, **k: None)
    assert recall.main(["--report", str(pdf), str(labels_file(tmp_path, pdf))]) == 0
    line = capsys.readouterr().out
    assert line.startswith("recall: ") and json.loads(line[len("recall: "):])["passed"] == 1
    assert "Profit" not in line and str(pdf) not in line


def test_the_module_never_sends_anything():
    source = Path(recall.__file__).read_text(encoding="utf-8")
    assert "openai" not in source and "run_extraction" not in source and "requests" not in source
