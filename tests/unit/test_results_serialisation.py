"""Plain JSON from the objects of a run: exact decimals, no floats, stable order (PRD FR-010.1, FR-012.2; Phase 5 step 5d; B-258)."""

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

import pytest

from calc_records import CUR, D24, D25, rec
from credit_intel.export.results import to_jsonable
from credit_intel.models import FieldName as F, Status


class Colour(StrEnum):
    RED = "red"


@dataclass(frozen=True)
class Point:
    x: Decimal
    colour: Colour


@pytest.mark.parametrize(
    ("value", "text"),
    [(Decimal("1E+3"), "1000"), (Decimal("1.50"), "1.50"), (Decimal("0E-10"), "0.0000000000"), (Decimal("-0.5"), "-0.5"),
     (Decimal("14823000000"), "14823000000"), (Decimal("1.2E+5"), "120000"), (Decimal("33.33333333333333333333333333"), "33.33333333333333333333333333")],
)  # fmt: skip
def test_a_decimal_is_written_as_plain_digits_never_in_exponent_form(value, text):
    assert to_jsonable(value) == text


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_a_decimal_that_is_not_finite_is_refused(bad):
    with pytest.raises(TypeError):
        to_jsonable(bad)


@pytest.mark.parametrize("bad", [0.1, 1.0, float("nan"), float("inf"), -0.0])
def test_a_float_is_refused_anywhere_in_the_data(bad):
    with pytest.raises(TypeError):
        to_jsonable(bad)
    with pytest.raises(TypeError):
        to_jsonable({"a": [1, {"b": bad}]})
    with pytest.raises(TypeError):
        to_jsonable({"amount": bad, "details": {}})  # allowed only under "details", not beside it


def test_a_page_coordinate_in_a_checks_details_may_be_a_float_but_a_non_finite_one_may_not():
    assert to_jsonable({"details": {"column": {"region": [72.5, 430.25]}}}) == {"details": {"column": {"region": [72.5, 430.25]}}}
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(TypeError):
            to_jsonable({"details": {"x": bad}})


def test_the_details_allowance_does_not_spread_to_sibling_keys():
    with pytest.raises(TypeError):
        to_jsonable({"details": {"x": 1.5}, "value": 1.5})


def test_dates_enums_and_none_become_json_text_and_null():
    assert to_jsonable(date(2025, 3, 31)) == "2025-03-31" and to_jsonable(Colour.RED) == "red" and to_jsonable(None) is None
    assert to_jsonable(True) is True and to_jsonable(7) == 7 and to_jsonable("₹ crore") == "₹ crore"


def test_a_datetime_is_not_a_date_here_it_is_still_written_but_runs_never_hold_one():
    assert to_jsonable(datetime(2026, 10, 24, 9, 0, 0)) == "2026-10-24T09:00:00"  # isoformat; no result type carries a datetime


def test_containers_become_lists_and_dicts_and_sets_are_ordered():
    assert to_jsonable((1, 2)) == [1, 2] and to_jsonable([Decimal("1")]) == ["1"]
    assert to_jsonable({3, 1, 2}) == [1, 2, 3] and to_jsonable(frozenset({"b", "a"})) == ["a", "b"]
    assert to_jsonable(MappingProxyType({"k": Decimal("2")})) == {"k": "2"}


def test_enum_keys_become_their_values_and_other_keys_become_text():
    assert to_jsonable({Colour.RED: 1, 5: 2}) == {"red": 1, "5": 2}


def test_dataclasses_and_models_are_written_field_by_field():
    assert to_jsonable(Point(Decimal("2.50"), Colour.RED)) == {"x": "2.50", "colour": "red"}
    record = rec(F.REVENUE, "1200", role=CUR, end=D25)
    written = to_jsonable(record)
    assert written["value"] == "1200" and written["period_end"] == "2025-03-31" and written["status"] == "extracted"
    assert written["field_id"] == "revenue.2025-03-31.consolidated" and written["origin"] == "source"


def test_the_whole_of_a_field_record_survives_as_json_with_its_evidence_unchanged():
    record = rec(F.NET_PROFIT, "96", role=CUR, end=D25)

    text = json.dumps(to_jsonable(record), sort_keys=True)
    back = json.loads(text)

    assert back["evidence_quote"] == record.evidence_quote and back["raw_value"] == record.raw_value
    assert back["page_number"] == 3 and back["line_item_label"] == record.line_item_label
    assert back["validation"]["evidence_verified"] is True


def test_a_not_found_record_writes_null_for_what_it_does_not_have():
    written = to_jsonable(rec(F.REVENUE, status=Status.NOT_FOUND, role=CUR, end=D24))

    assert written["value"] is None and written["evidence_quote"] is None and written["status"] == "not_found"


def test_an_object_of_an_unknown_type_is_refused_not_guessed():
    with pytest.raises(TypeError):
        to_jsonable(object())
    with pytest.raises(TypeError):
        to_jsonable(b"bytes")


def test_the_same_data_gives_the_same_text_every_time():
    data = {"b": [Decimal("1.0"), date(2025, 1, 1)], "a": None}

    assert json.dumps(to_jsonable(data), sort_keys=True) == json.dumps(to_jsonable(data), sort_keys=True)
