"""The tuning scorer: labels file, SC-01 to SC-05 counts and reason counts (PRD O.2, O.3; Phase 7b).

Synthetic values only. Every message and report is checked for the absence of the figures it was given.
"""

import json
import tempfile
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from calc_records import CUR, D24, D25, conflicting, rec
from credit_intel.evaluation.score import LabelsError, aggregate, load_labels, score_document
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, Scale, StatementBasis as Basis, Status, StatusReason as R

COMP = PeriodRole.COMPARATIVE
SHA = "a" * 64
SECRET = "777,123.45"
SCORED = [name for name in F if name is not F.EBIT]
END = {"current": "2025-03-31", "comparative": "2024-03-31"}


def label(field, period, printed="10", page=3, scale="units", **extra):
    base = {"field": field.value, "period": period, "period_end": END[period], "printed": printed, "scale": scale, "currency": "INR", "page": page}
    return {**base, **extra}


def absent(field, period):
    return {"field": field.value, "period": period, "absent": True}


def full(overrides=None):
    """Twenty-four present entries (ten each), with the given (field, period) replaced."""
    entries = {(n, p): label(n, p) for n in SCORED for p in ("current", "comparative")}
    entries.update(overrides or {})
    return {"document_id": "R1", "sha256": SHA, "basis": "consolidated", "entries": list(entries.values())}


def write(tmp_path, data, name="labels.json"):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def r(name, value="10", role=CUR, **kw):
    """A source record whose scale is units, so the value is the printed one."""
    return rec(name, value, role=role, end=D25 if role is CUR else D24, **kw).model_copy(update={"scale": Scale.UNITS})


def field_set(drop=(), replace=None, extra=()):
    records = {(n, p): r(n, role=p) for n in SCORED for p in (CUR, COMP)}
    for key in drop:
        records.pop(key, None)
    records.update(replace or {})
    return FieldSet(Basis.CONSOLIDATED, (*records.values(), *extra), (), (), ("consolidated",))


def labels_of(data):
    with tempfile.TemporaryDirectory() as directory:
        return load_labels(write(Path(directory), data))


def score(labels_data=None, **kw):
    return score_document(labels_of(labels_data or full()), field_set(**kw))


def entry_of(report, field, period):
    return next(e for e in report["entries"] if e["field"] == field.value and e["period"] == period)


# --- the labels file ----------------------------------------------------------------------------------------------------------------------------


def test_a_full_labels_file_is_read_and_scaled(tmp_path):
    data = full({(F.REVENUE, "current"): label(F.REVENUE, "current", "(1,234.50)", scale="crore")})
    labels = load_labels(write(tmp_path, data))

    revenue = next(e for e in labels.entries if e.field is F.REVENUE and e.role is CUR)
    assert len(labels.entries) == 24 and revenue.expected == Decimal("-12345000000") and revenue.currency == "INR" and revenue.pages == (3,)


def test_a_field_may_be_labelled_absent_and_a_total_may_be_given_as_parts(tmp_path):
    parts = {"field": "total_borrowings", "period": "current", "period_end": END["current"], "currency": "INR",
             "parts": [{"printed": "4", "scale": "units", "page": 5}, {"printed": "6", "scale": "units", "page": 6}]}  # fmt: skip
    labels = load_labels(write(tmp_path, full({(F.OPERATING_PROFIT, "current"): absent(F.OPERATING_PROFIT, "current"), (F.TOTAL_BORROWINGS, "current"): parts})))

    absent_ones = [e for e in labels.entries if e.absent]
    total = next(e for e in labels.entries if e.field is F.TOTAL_BORROWINGS and e.role is CUR)
    assert [(e.field, e.role) for e in absent_ones] == [(F.OPERATING_PROFIT, CUR)] and total.expected == Decimal(10) and total.pages == (5, 6) and total.scale is None


def test_a_value_printed_on_two_pages_may_be_given_as_a_list(tmp_path):
    entry = label(F.REVENUE, "current")
    entry.pop("page")
    entry["pages"] = [9, 4, 9]
    labels = load_labels(write(tmp_path, full({(F.REVENUE, "current"): entry})))

    assert next(e for e in labels.entries if e.field is F.REVENUE and e.role is CUR).pages == (4, 9)


def mutated(change):
    data = full()
    change(data)
    return data


def drop_entry(data):
    data["entries"].pop(0)


def repeat_entry(data):
    data["entries"].append(deepcopy(data["entries"][0]))


def ebit_entry(data):
    data["entries"][0] = label(F.EBIT, "current")


def set_on_first(**changes):
    def apply(data):
        data["entries"][0].update(changes)

    return apply


def other_end(data):
    entry = next(e for e in data["entries"] if e["field"] == "revenue" and e["period"] == "current")
    entry["period_end"] = "2025-04-30"


def absent_with_value(data):
    data["entries"][0] = {**absent(F.REVENUE, "current"), "printed": SECRET}


def both_page_and_pages(data):
    data["entries"][0]["pages"] = [3]


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (drop_entry, "every field and period needs an entry"),
        (repeat_entry, "repeated"),
        (ebit_entry, "derived"),
        (set_on_first(field="turnover"), "not recognised"),
        (set_on_first(period="previous"), "not recognised"),
        (set_on_first(period_end="31 March 2025"), "ISO date"),
        (set_on_first(currency="rupees"), "three capital letters"),
        (set_on_first(currency=None), "three capital letters"),
        (set_on_first(scale="lakhs"), "scale is not one of"),
        (set_on_first(printed=SECRET + "x"), "cannot be read as a figure"),
        (set_on_first(printed=5), "printed must be a string"),
        (set_on_first(page=0), "page must be"),
        (set_on_first(page=True), "page must be"),
        (set_on_first(colour="red"), "unknown key"),
        (other_end, "do not share one period_end"),
        (absent_with_value, "absent must be true"),
        (both_page_and_pages, "exactly one of page and pages"),
        (lambda d: d.update(basis="group"), "basis must be"),
        (lambda d: d.update(sha256="xyz"), "sha256 must be"),
        (lambda d: d.update(document_id="R 1"), "document_id must be"),
        (lambda d: d.update(entries={}), "entries must be a list"),
        (lambda d: d.update(assert_basis="consolidated"), "assert_basis needs pages"),
        (lambda d: d.update(pages="36-38", assert_basis="both"), "assert_basis must be"),
        (lambda d: d.update(pages="abc"), "pages must be a page range"),
        (lambda d: d.update(extra=1), "must be an object with the keys"),
        (lambda d: d.pop("sha256"), "must be an object with the keys"),
    ],
)
def test_a_labels_file_with_a_problem_is_refused_and_the_message_holds_no_figure(tmp_path, change, fragment):
    with pytest.raises(LabelsError, match=fragment) as caught:
        load_labels(write(tmp_path, mutated(change)))

    assert SECRET not in str(caught.value) and SECRET.split(",")[0] not in str(caught.value)


def test_parts_are_for_total_borrowings_only_and_need_two_components(tmp_path):
    parts = [{"printed": "4", "scale": "units", "page": 5}, {"printed": "6", "scale": "units", "page": 5}]
    other = {**label(F.REVENUE, "current"), "parts": parts}
    for key in ("printed", "scale", "page"):
        other.pop(key)
    with pytest.raises(LabelsError, match="total_borrowings only"):
        load_labels(write(tmp_path, full({(F.REVENUE, "current"): other})))
    one = {"field": "total_borrowings", "period": "current", "period_end": END["current"], "currency": "INR", "parts": parts[:1]}
    with pytest.raises(LabelsError, match="at least two"):
        load_labels(write(tmp_path, full({(F.TOTAL_BORROWINGS, "current"): one})))


@pytest.mark.parametrize("text", ["", "[]", "42", "not json", '{"entries": 1}'])
def test_a_file_that_is_not_a_labels_object_is_refused(tmp_path, text):
    with pytest.raises(LabelsError):
        load_labels(write(tmp_path, text))


def test_a_missing_oversized_or_binary_file_is_refused(tmp_path):
    with pytest.raises(LabelsError, match="cannot be read"):
        load_labels(tmp_path / "nope.json")
    with pytest.raises(LabelsError, match="larger than 64 KiB"):
        load_labels(write(tmp_path, " " * (64 * 1024 + 1)))
    binary = tmp_path / "b.json"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(LabelsError, match="cannot be read"):
        load_labels(binary)


def test_a_missing_entry_is_named_by_field_and_period(tmp_path):
    data = full()
    data["entries"] = [e for e in data["entries"] if not (e["field"] == "total_equity" and e["period"] == "comparative")]

    with pytest.raises(LabelsError, match=r"missing: total_equity\.comparative"):
        load_labels(write(tmp_path, data))


# --- SC-01 -------------------------------------------------------------------------------------------------------------------------------------


def test_every_value_right_scores_all_twenty_four_and_everything_else_is_clean():
    report = score()

    assert report["counts"] == {
        "sc01": {"match": 24, "of": 24},
        "sc02": {"extracted_for_absent": 0, "value_differs": 0},
        "sc03": {"correct": 0, "undecided": 0, "of": 0},
        "sc04": {"passed": 24, "of": 24},
        "sc05": {"page_agrees": 24, "of": 24},
    }


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (r(F.REVENUE, "11"), "value_differs"),
        (rec(F.REVENUE, "10", end=D24).model_copy(update={"scale": Scale.UNITS}), "period_end_differs"),
        (rec(F.REVENUE, "10", currency="USD").model_copy(update={"scale": Scale.UNITS}), "currency_differs"),
        (rec(F.REVENUE, "10"), "scale_differs"),  # the helper's own scale is crore
    ],
)
def test_each_way_a_value_can_be_wrong_has_its_own_code(record, expected):
    report = score(replace={(F.REVENUE, CUR): record})

    assert entry_of(report, F.REVENUE, "current")["outcome"] == "mismatch" and expected in entry_of(report, F.REVENUE, "current")["reason"].split(",")
    assert report["counts"]["sc01"] == {"match": 23, "of": 24}


def test_every_difference_is_reported_together():
    wrong = rec(F.REVENUE, "11", currency="USD", end=D24)

    assert entry_of(score(replace={(F.REVENUE, CUR): wrong}), F.REVENUE, "current")["reason"] == "value_differs,period_end_differs,currency_differs,scale_differs"


@pytest.mark.parametrize(
    ("record", "shown"),
    [
        (rec(F.REVENUE, status=Status.NOT_FOUND), "not_found"),
        (rec(F.REVENUE, status=Status.REQUIRES_REVIEW, reason=R.LABEL_NOT_RECOGNISED), "label_not_recognised"),
        (conflicting(F.REVENUE, ["10", "12"]), "conflicting"),
    ],
)
def test_a_value_that_is_not_extracted_is_missing_with_its_reason(record, shown):
    report = score(replace={(F.REVENUE, CUR): record})

    assert entry_of(report, F.REVENUE, "current")["outcome"] == "missing" and entry_of(report, F.REVENUE, "current")["reason"] == shown


def test_a_field_with_no_record_is_missing_and_a_record_of_the_other_basis_is_never_used():
    other = rec(F.REVENUE, "10", basis=Basis.STANDALONE).model_copy(update={"scale": Scale.UNITS})
    report = score(drop=[(F.REVENUE, CUR)], extra=(other,))

    assert entry_of(report, F.REVENUE, "current")["outcome"] == "missing" and entry_of(report, F.REVENUE, "current")["reason"] == "no_record"


def test_a_field_set_of_another_basis_than_the_labels_is_refused():
    with pytest.raises(ValueError, match="another statement basis"):
        score_document(labels_of(full()), FieldSet(Basis.STANDALONE, (), (), (), ()))


# --- SC-02 and SC-03 -----------------------------------------------------------------------------------------------------------------------------


def test_a_value_given_for_a_field_the_report_does_not_present_is_a_hallucination_candidate_and_is_wrong():
    data = full({(F.OPERATING_PROFIT, "current"): absent(F.OPERATING_PROFIT, "current")})
    report = score(data)

    assert entry_of(report, F.OPERATING_PROFIT, "current")["outcome"] == "wrong" and report["counts"]["sc02"]["extracted_for_absent"] == 1
    assert report["counts"]["sc03"] == {"correct": 0, "undecided": 0, "of": 1} and report["counts"]["sc01"]["of"] == 23


def test_a_wrong_value_is_a_candidate_too_and_is_counted_apart():
    report = score(replace={(F.REVENUE, CUR): r(F.REVENUE, "11")})

    assert report["counts"]["sc02"] == {"extracted_for_absent": 0, "value_differs": 1}


def test_not_found_or_no_record_is_correct_for_an_absent_field():
    data = full({(F.OPERATING_PROFIT, "current"): absent(F.OPERATING_PROFIT, "current"), (F.OPERATING_PROFIT, "comparative"): absent(F.OPERATING_PROFIT, "comparative")})
    report = score(data, replace={(F.OPERATING_PROFIT, CUR): rec(F.OPERATING_PROFIT, status=Status.NOT_FOUND)}, drop=[(F.OPERATING_PROFIT, COMP)])

    assert report["counts"]["sc03"] == {"correct": 2, "undecided": 0, "of": 2} and report["counts"]["sc02"]["extracted_for_absent"] == 0


@pytest.mark.parametrize("record", [rec(F.OPERATING_PROFIT, status=Status.REQUIRES_REVIEW, reason=R.LABEL_NOT_RECOGNISED), conflicting(F.OPERATING_PROFIT, ["1", "2"])])
def test_a_field_with_no_value_but_not_not_found_is_undecided_not_correct_and_not_wrong(record):
    data = full({(F.OPERATING_PROFIT, "current"): absent(F.OPERATING_PROFIT, "current")})
    report = score(data, replace={(F.OPERATING_PROFIT, CUR): record})

    assert report["counts"]["sc03"] == {"correct": 0, "undecided": 1, "of": 1} and report["counts"]["sc02"]["extracted_for_absent"] == 0


def test_absent_total_borrowings_is_judged_with_its_components_as_the_gate_does():
    data = full({(F.TOTAL_BORROWINGS, "current"): absent(F.TOTAL_BORROWINGS, "current")})
    nothing = {k: rec(k[0], status=Status.NOT_FOUND, role=k[1]) for k in [(F.TOTAL_BORROWINGS, CUR), (F.BORROWINGS_NON_CURRENT, CUR), (F.BORROWINGS_CURRENT, CUR), (F.CURRENT_MATURITIES_LONG_TERM_BORROWINGS, CUR)]}
    clean = score(data, replace=nothing)
    component_only = score(data, replace={**nothing, (F.BORROWINGS_CURRENT, CUR): r(F.BORROWINGS_CURRENT)})

    assert clean["counts"]["sc03"]["correct"] == 1 and entry_of(component_only, F.TOTAL_BORROWINGS, "current")["outcome"] == "wrong"
    assert component_only["counts"]["sc02"]["extracted_for_absent"] == 1


def test_a_total_built_from_parts_is_matched_by_the_sum_and_has_no_page_flag():
    parts = {"field": "total_borrowings", "period": "current", "period_end": END["current"], "currency": "INR",
             "parts": [{"printed": "4", "scale": "units", "page": 5}, {"printed": "6", "scale": "units", "page": 6}]}  # fmt: skip
    components = {(F.BORROWINGS_NON_CURRENT, CUR): r(F.BORROWINGS_NON_CURRENT, "4"), (F.BORROWINGS_CURRENT, CUR): r(F.BORROWINGS_CURRENT, "6"), (F.TOTAL_BORROWINGS, CUR): rec(F.TOTAL_BORROWINGS, status=Status.NOT_FOUND),
                  (F.CURRENT_MATURITIES_LONG_TERM_BORROWINGS, CUR): rec(F.CURRENT_MATURITIES_LONG_TERM_BORROWINGS, status=Status.NOT_FOUND)}  # no separate current-maturities row
    report = score(full({(F.TOTAL_BORROWINGS, "current"): parts}), replace=components)

    total = entry_of(report, F.TOTAL_BORROWINGS, "current")
    assert total["outcome"] == "match" and total["page_agrees"] is None


# --- SC-04 and SC-05 -----------------------------------------------------------------------------------------------------------------------------


def test_a_source_value_cited_from_another_page_still_matches_and_is_not_a_page_agreement():
    elsewhere = r(F.REVENUE).model_copy(update={"page_number": 9})
    report = score(replace={(F.REVENUE, CUR): elsewhere})

    assert entry_of(report, F.REVENUE, "current")["outcome"] == "match" and entry_of(report, F.REVENUE, "current")["page_agrees"] is False
    assert report["counts"]["sc05"] == {"page_agrees": 23, "of": 24}


def test_a_wrong_value_has_no_ground_truth_page_so_it_is_not_scored_for_pages():
    report = score(replace={(F.REVENUE, CUR): r(F.REVENUE, "11").model_copy(update={"page_number": 9})})

    assert report["counts"]["sc05"] == {"page_agrees": 23, "of": 23}


def test_a_page_in_the_list_of_labelled_pages_agrees():
    entry = label(F.REVENUE, "current")
    entry.pop("page")
    entry["pages"] = [3, 8]
    report = score(full({(F.REVENUE, "current"): entry}), replace={(F.REVENUE, CUR): r(F.REVENUE).model_copy(update={"page_number": 8})})

    assert entry_of(report, F.REVENUE, "current")["page_agrees"] is True


def test_a_check_that_did_not_pass_is_counted_against_sc04():
    bad = r(F.REVENUE)
    bad = bad.model_copy(update={"validation": bad.validation.model_copy(update={"sign_verified": False})})
    report = score(replace={(F.REVENUE, CUR): bad})

    assert report["counts"]["sc04"] == {"passed": 23, "of": 24}


# --- reasons, statuses, aggregate, privacy -------------------------------------------------------------------------------------------------------


def test_the_reasons_and_statuses_are_counted_over_the_whole_run():
    review = rec(F.REVENUE, status=Status.REQUIRES_REVIEW, reason=R.LABEL_NOT_RECOGNISED)
    twice = rec(F.NET_PROFIT, status=Status.REQUIRES_REVIEW, reason=R.LABEL_NOT_RECOGNISED)
    other = rec(F.TOTAL_EQUITY, status=Status.REQUIRES_REVIEW, reason=R.EVIDENCE_NOT_VERIFIED)
    report = score(replace={(F.REVENUE, CUR): review, (F.NET_PROFIT, CUR): twice, (F.TOTAL_EQUITY, CUR): other})

    assert report["reasons"] == {"evidence_not_verified": 1, "label_not_recognised": 2}
    assert report["statuses"] == {"extracted": 21, "not_found": 0, "conflicting": 0, "requires_review": 3}


def test_the_aggregate_sums_counts_and_lists_a_document_that_did_not_replay():
    review = rec(F.NET_PROFIT, status=Status.REQUIRES_REVIEW, reason=R.LABEL_NOT_RECOGNISED)
    one, two = score(replace={(F.NET_PROFIT, CUR): review}), score(replace={(F.REVENUE, CUR): r(F.REVENUE, "11"), (F.NET_PROFIT, COMP): review.model_copy(update={"period_role": COMP})})
    total = aggregate([{"replayed": True, **one, "document_id": "R1"}, {"replayed": True, **two, "document_id": "R2"}, {"replayed": False, "document_id": "R3", "reason": "cache_miss"}])

    assert total["counts"]["sc01"] == {"match": 45, "of": 48} and total["fractions"]["sc01"] == "45/48" and total["reasons"] == {"label_not_recognised": 2}
    assert total["not_replayed"] == ["R3"] and total["documents"] == ["R1", "R2", "R3"] and total["set"] == "tuning"


def test_the_report_holds_no_value_quote_or_label():
    values = {(F.REVENUE, CUR): r(F.REVENUE, "777123.45")}
    text = json.dumps(score(full({(F.REVENUE, "current"): label(F.REVENUE, "current", "888,999.01")}), replace=values))

    for forbidden in (SECRET, "777,123", "888,999", "revenue 7", "Acme", date(2025, 3, 31).isoformat()):
        assert forbidden not in text
