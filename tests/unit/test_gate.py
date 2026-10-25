"""The gate's reference files, comparison and verdict (PRD Phase 2 exit conditions, O.2; Phase 5 Part 2 preparation; B-274).

Synthetic values only. Every message the gate prints is checked for the absence of the figures it was given.
"""

import json
from datetime import date
from decimal import Decimal

import pytest

from calc_records import CUR, D24, D25, rec
from credit_intel.evaluation import gate
from credit_intel.evaluation.gate import GateReferenceError, compare, evaluate_gate, load_reference
from credit_intel.evaluation.guard import MEMBERS
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status, StatusReason as R

COMP = PeriodRole.COMPARATIVE
SHA = "a" * 64
SECRET = "999,111.22"


def entry(field, period, printed, end, page=3, scale="units"):
    return {"field": field, "period": period, "period_end": end, "page": page, "printed": printed, "scale": scale}


def base():
    return {
        "document_id": "R1", "sha256": SHA, "basis": "consolidated",
        "entries": [
            entry("profit_before_tax", "current", "352.70", "2025-03-31"), entry("profit_before_tax", "comparative", "300.10", "2024-03-31"),
            entry("interest_expense", "current", "38.50", "2025-03-31"), entry("interest_expense", "comparative", "35.00", "2024-03-31"),
            entry("total_borrowings", "current", "550.00", "2025-03-31"), entry("total_borrowings", "comparative", "470.00", "2024-03-31"),
        ],
    }  # fmt: skip


def write(tmp_path, data, name="ref.json"):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def field_set(overrides=None, extra=()):
    values = {(F.PROFIT_BEFORE_TAX, CUR): "352.70", (F.PROFIT_BEFORE_TAX, COMP): "300.10", (F.INTEREST_EXPENSE, CUR): "38.50", (F.INTEREST_EXPENSE, COMP): "35.00",
              (F.TOTAL_BORROWINGS, CUR): "550.00", (F.TOTAL_BORROWINGS, COMP): "470.00"}  # fmt: skip
    values.update(overrides or {})
    records = [rec(n, v, role=r, end=D25 if r is CUR else D24) for (n, r), v in values.items() if v is not None]
    return FieldSet(Basis.CONSOLIDATED, (*records, *extra), (), (), ("consolidated",))


# --- the reference file ------------------------------------------------------------------------------------------------------------------------


def test_a_good_reference_is_read_with_the_values_scaled_and_signed(tmp_path):
    data = base()
    data["entries"][0] = entry("profit_before_tax", "current", "(1,234.50)", "2025-03-31", scale="crore")
    data["entries"][2] = entry("interest_expense", "current", "-", "2025-03-31")

    reference = load_reference(write(tmp_path, data))

    by = {(e.field, e.role): e for e in reference.entries}
    assert (reference.document_id, reference.sha256, reference.basis) == ("R1", SHA, Basis.CONSOLIDATED) and len(reference.entries) == 6
    assert by[(F.PROFIT_BEFORE_TAX, CUR)].expected == Decimal("-12345000000.00") and by[(F.INTEREST_EXPENSE, CUR)].expected == Decimal(0)
    assert by[(F.TOTAL_BORROWINGS, COMP)].period_end == date(2024, 3, 31) and by[(F.TOTAL_BORROWINGS, COMP)].pages == (3,)


def test_a_total_that_the_report_does_not_print_is_given_as_parts_and_is_their_sum(tmp_path):
    data = base()
    data["entries"][4] = {"field": "total_borrowings", "period": "current", "period_end": "2025-03-31",
                          "parts": [{"printed": "400.00", "scale": "crore", "page": 5}, {"printed": "150.00", "scale": "crore", "page": 6}]}  # fmt: skip

    entry_ = next(e for e in load_reference(write(tmp_path, data)).entries if e.field is F.TOTAL_BORROWINGS and e.role is CUR)

    assert entry_.expected == Decimal("5500000000.00") and entry_.pages == (5, 6)


def mutated(change):
    data = base()
    change(data)
    return data


BAD = {
    "top keys out of order": lambda d: d.update(entries=d.pop("entries"), document_id=d.pop("document_id")),
    "an extra top key": lambda d: d.update(notes="x"),
    "a missing top key": lambda d: d.pop("basis"),
    "document id with a space": lambda d: d.update(document_id="R 1"),
    "document id too long": lambda d: d.update(document_id="R" * 33),
    "sha not hex": lambda d: d.update(sha256="g" * 64),
    "sha too short": lambda d: d.update(sha256="a" * 63),
    "basis unknown": lambda d: d.update(basis="unknown"),
    "entries not a list": lambda d: d.update(entries={}),
    "an entry that is not an object": lambda d: d["entries"].append("x"),
    "an unknown entry key": lambda d: d["entries"][0].update(note="x"),
    "an unknown field": lambda d: d["entries"][0].update(field="revenue"),
    "a field outside the gate": lambda d: d["entries"][0].update(field="borrowings_current"),
    "an unknown period": lambda d: d["entries"][0].update(period="previous"),
    "a bad date": lambda d: d["entries"][0].update(period_end="31/03/2025"),
    "a missing date": lambda d: d["entries"][0].pop("period_end"),
    "a figure that cannot be read": lambda d: d["entries"][0].update(printed="12,34"),
    "a figure that is not text": lambda d: d["entries"][0].update(printed=352.7),
    "an unknown scale": lambda d: d["entries"][0].update(scale="tens"),
    "a missing scale": lambda d: d["entries"][0].pop("scale"),
    "page zero": lambda d: d["entries"][0].update(page=0),
    "page as text": lambda d: d["entries"][0].update(page="3"),
    "page true": lambda d: d["entries"][0].update(page=True),
    "an entry repeated": lambda d: d["entries"].__setitem__(1, dict(d["entries"][0])),
    "an entry missing": lambda d: d["entries"].pop(),
    "parts on another field": lambda d: d["entries"][0].update(parts=[{"printed": "1", "scale": "units", "page": 1}] * 2),
    "parts with a printed value": lambda d: d["entries"][4].update(parts=[{"printed": "1", "scale": "units", "page": 1}] * 2),
    "one part only": lambda d: d["entries"].__setitem__(4, {"field": "total_borrowings", "period": "current", "period_end": "2025-03-31", "parts": [{"printed": "1", "scale": "units", "page": 1}]}),
    "a part with an extra key": lambda d: d["entries"].__setitem__(4, {"field": "total_borrowings", "period": "current", "period_end": "2025-03-31", "parts": [{"printed": "1", "scale": "units", "page": 1, "x": 1}] * 2}),
}  # fmt: skip


@pytest.mark.parametrize("name", list(BAD))
def test_a_reference_with_a_problem_is_refused_and_the_message_holds_no_figure(tmp_path, name):
    data = base()
    data["entries"][1]["printed"] = SECRET  # a figure that must never be repeated in a message
    BAD[name](data)

    with pytest.raises(GateReferenceError) as caught:
        load_reference(write(tmp_path, data))

    assert SECRET not in str(caught.value) and "352.70" not in str(caught.value) and str(tmp_path) not in str(caught.value)


@pytest.mark.parametrize("text", ["", "{not json", "[]", "null", '"x"'])
def test_a_file_that_is_not_a_json_object_is_refused(tmp_path, text):
    with pytest.raises(GateReferenceError):
        load_reference(write(tmp_path, text))


def test_a_missing_or_oversized_or_binary_file_is_refused(tmp_path):
    with pytest.raises(GateReferenceError):
        load_reference(tmp_path / "absent.json")
    with pytest.raises(GateReferenceError, match="64 KiB"):
        load_reference(write(tmp_path, "x" * 70_000))
    (tmp_path / "bin.json").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(GateReferenceError):
        load_reference(tmp_path / "bin.json")


def test_a_missing_entry_is_named_by_field_and_period(tmp_path):
    data = base()
    data["entries"] = [e for e in data["entries"] if not (e["field"] == "interest_expense" and e["period"] == "comparative")]

    with pytest.raises(GateReferenceError, match="interest_expense.comparative"):
        load_reference(write(tmp_path, data))


# --- the comparison ----------------------------------------------------------------------------------------------------------------------------


def reference(tmp_path, data=None):
    return load_reference(write(tmp_path, data or base()))


def outcomes(report):
    return {(e["field"], e["period"]): (e["outcome"], e["reason"]) for e in report["entries"]}


def test_six_matching_values_pass(tmp_path):
    report = compare(reference(tmp_path), field_set())

    assert report["passed"] and report["counts"] == {"match": 6, "mismatch": 0, "missing": 0} and report["replayed"] is True


def test_a_value_that_differs_fails_the_gate(tmp_path):
    report = compare(reference(tmp_path), field_set({(F.INTEREST_EXPENSE, CUR): "38.51"}))

    assert not report["passed"] and report["counts"] == {"match": 5, "mismatch": 1, "missing": 0}
    assert outcomes(report)[("interest_expense", "current")] == ("mismatch", "value_differs")


def test_a_value_from_the_wrong_period_column_is_a_mismatch(tmp_path):
    fs = field_set({(F.PROFIT_BEFORE_TAX, CUR): None}, extra=[rec(F.PROFIT_BEFORE_TAX, "352.70", role=CUR, end=date(2024, 3, 31))])

    assert outcomes(compare(reference(tmp_path), fs))[("profit_before_tax", "current")] == ("mismatch", "period_end_differs")


def test_a_value_read_from_the_other_basis_is_never_used_so_it_shows_as_missing(tmp_path):
    fs = field_set({(F.INTEREST_EXPENSE, COMP): None}, extra=[rec(F.INTEREST_EXPENSE, "35.00", role=COMP, end=D24, basis=Basis.STANDALONE)])

    report = compare(reference(tmp_path), fs)

    assert outcomes(report)[("interest_expense", "comparative")] == ("missing", "no_record") and not report["passed"]


def test_a_field_set_of_another_basis_than_the_reference_is_refused(tmp_path):
    with pytest.raises(ValueError):
        compare(reference(tmp_path), FieldSet(Basis.STANDALONE, field_set().fields, (), (), ()))


def test_every_way_a_value_can_be_wrong_is_reported_together(tmp_path):
    fs = field_set({(F.PROFIT_BEFORE_TAX, CUR): None}, extra=[rec(F.PROFIT_BEFORE_TAX, "1.00", role=CUR, end=date(2024, 3, 31))])

    assert outcomes(compare(reference(tmp_path), fs))[("profit_before_tax", "current")] == ("mismatch", "value_differs,period_end_differs")


@pytest.mark.parametrize(("status", "reason", "shown"), [(Status.NOT_FOUND, None, "not_found"), (Status.REQUIRES_REVIEW, R.LABEL_NOT_RECOGNISED, "label_not_recognised"), (Status.REQUIRES_REVIEW, R.SCALE_NOT_VERIFIED, "scale_not_verified")])
def test_a_value_that_is_not_extracted_is_missing_with_its_reason(tmp_path, status, reason, shown):
    fs = field_set({(F.PROFIT_BEFORE_TAX, COMP): None}, extra=[rec(F.PROFIT_BEFORE_TAX, "300.10", status=status, reason=reason, role=COMP, end=D24)])

    report = compare(reference(tmp_path), fs)

    assert not report["passed"] and report["counts"] == {"match": 5, "mismatch": 0, "missing": 1}
    assert outcomes(report)[("profit_before_tax", "comparative")] == ("missing", shown)


def test_a_field_with_no_record_at_all_is_missing(tmp_path):
    report = compare(reference(tmp_path), field_set({(F.INTEREST_EXPENSE, CUR): None}))

    assert outcomes(report)[("interest_expense", "current")] == ("missing", "no_record") and not report["passed"]


def test_a_right_value_read_from_another_page_still_matches_and_the_page_is_flagged(tmp_path):
    report = compare(reference(tmp_path, mutated(lambda d: d["entries"][0].update(page=9))), field_set())

    assert report["passed"]
    flags = {(e["field"], e["period"]): e["page_agrees"] for e in report["entries"]}
    assert flags[("profit_before_tax", "current")] is False and flags[("profit_before_tax", "comparative")] is True


def test_a_derived_total_is_compared_by_its_value_and_has_no_page_flag(tmp_path):
    parts = {"field": "total_borrowings", "period": "current", "period_end": "2025-03-31",
             "parts": [{"printed": "400.00", "scale": "units", "page": 5}, {"printed": "150.00", "scale": "units", "page": 6}]}  # fmt: skip
    fs = field_set({(F.TOTAL_BORROWINGS, CUR): None}, extra=[rec(F.BORROWINGS_NON_CURRENT, "400.00", role=CUR, end=D25), rec(F.BORROWINGS_CURRENT, "150.00", role=CUR, end=D25)])
    data = base()
    data["entries"][4] = parts

    report = compare(reference(tmp_path, data), fs)
    row = next(e for e in report["entries"] if e["field"] == "total_borrowings" and e["period"] == "current")

    assert row["outcome"] == "match" and row["origin"] == "derived" and row["page_agrees"] is None and report["passed"]


def test_a_derived_total_that_does_not_add_up_to_the_reference_fails(tmp_path):
    fs = field_set({(F.TOTAL_BORROWINGS, CUR): None}, extra=[rec(F.BORROWINGS_NON_CURRENT, "400.00", role=CUR, end=D25), rec(F.BORROWINGS_CURRENT, "151.00", role=CUR, end=D25)])

    report = compare(reference(tmp_path), fs)

    assert outcomes(report)[("total_borrowings", "current")] == ("mismatch", "value_differs")


def test_the_report_holds_no_value_quote_or_label(tmp_path):
    text = json.dumps(compare(reference(tmp_path), field_set({(F.INTEREST_EXPENSE, CUR): "38.51"})))

    for forbidden in ("352.70", "38.50", "38.51", "550.00", "Profit", "quote", "label"):
        assert forbidden not in text


# --- the verdict -------------------------------------------------------------------------------------------------------------------------------


def assignments(tmp_path, *rows):
    path = tmp_path / "assignments.jsonl"
    path.write_text("\n".join(json.dumps(dict(zip(MEMBERS, (doc, sha, group, "2026-10-24", "assigned", None, None), strict=True))) for doc, sha, group in rows) + "\n", encoding="utf-8")
    return path


def passed(document_id, ok=True):
    return {"document_id": document_id, "passed": ok}


def test_the_gate_passes_only_when_every_tuning_document_on_the_record_passes(tmp_path):
    record = assignments(tmp_path, ("R1", "1" * 64, "tuning"), ("R2", "2" * 64, "tuning"), ("H1", "3" * 64, "held_out"))

    assert evaluate_gate([passed("R1"), passed("R2")], record)["passed"]
    assert not evaluate_gate([passed("R1"), passed("R2", ok=False)], record)["passed"]
    assert not evaluate_gate([passed("R1")], record)["passed"]  # R2 was not reported
    assert not evaluate_gate([passed("R1"), passed("R2"), passed("H1")], record)["passed"]  # a held-out document is not a tuning report
    assert not evaluate_gate([passed("R1"), passed("R1")], record)["passed"]
    assert evaluate_gate([passed("R1"), passed("R2")], record)["tuning_documents"] == ["R1", "R2"]


def test_a_document_moved_to_tuning_must_be_reported_too(tmp_path):
    record = assignments(tmp_path, ("R1", "1" * 64, "tuning"), ("R2", "2" * 64, "tuning"), ("H1", "3" * 64, "tuning"))

    assert not evaluate_gate([passed("R1"), passed("R2")], record)["passed"]
    assert evaluate_gate([passed("R1"), passed("R2"), passed("H1")], record)["passed"]


def test_a_seventh_entry_that_repeats_one_is_refused_as_a_repeat(tmp_path):
    data = base()
    data["entries"].append(dict(data["entries"][0]))

    with pytest.raises(GateReferenceError, match="repeated"):
        load_reference(write(tmp_path, data))
