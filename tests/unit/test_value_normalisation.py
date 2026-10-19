"""Raw value normalisation (PRD FR-004.3, FR-004.4, D-08; B-203).

The raw value is read as printed. Anything that cannot be read with certainty is
unparsable (``None``): it is never guessed and never turned into zero.
"""

from decimal import Decimal

import pytest

from credit_intel.extraction.normalise import (
    UNPARSABLE_REASON,
    ParsedValue,
    apply_scale,
    parse_value,
)
from credit_intel.models import Scale, StatusReason, ValueInterpretation

NUMBER = ValueInterpretation.NUMBER
NIL = ValueInterpretation.REPORTED_NIL


def read(raw: str) -> tuple[Decimal, bool]:
    parsed = parse_value(raw)
    assert parsed is not None and parsed.interpretation is NUMBER, raw
    return parsed.value, parsed.negative_marker


# --- numbers, grouping and decimals -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1482.30", "1482.30"),
        ("1,482.30", "1482.30"),
        ("1,234,567.89", "1234567.89"),  # Western grouping
        ("1,23,456", "123456"),  # Indian grouping (FR-004.3)
        ("1,23,456.70", "123456.70"),
        ("12,34,567", "1234567"),
        ("1,23,45,678", "12345678"),
        ("12,345", "12345"),  # valid in both systems
        ("0", "0"),
        ("0.00", "0.00"),
        ("5", "5"),
        ("999", "999"),
        ("1000000", "1000000"),  # grouping is optional
    ],
)
def test_well_formed_numbers_are_read_exactly(raw, expected):
    assert read(raw) == (Decimal(expected), False)


def test_decimal_places_as_printed_are_kept():
    value, _ = read("1,482.30")

    assert str(value) == "1482.30"  # the printed precision matters for H.4.2


def test_values_are_decimal_never_binary_floats():
    value, _ = read("0.1")

    assert isinstance(value, Decimal)
    assert value == Decimal("0.1") and value != Decimal(0.1)


@pytest.mark.parametrize(
    "raw",
    [
        "1,2345",  # grouping that is neither Western nor Indian
        "12,34",
        "1,23,4567",
        "1,234,56",
        ",123",
        "1,,234",
        "1,23,456,7",
        "1.234,56",  # decimal comma
        "1.234.567",
        "1e5",
        "1E5",
        "0x10",
        "+5",
        "5%",
        "1,234.",
        ".5",
        "1 234",  # internal space: a split figure
        "(4,901 )",
        "1,234.5.6",
        "abc",
        "N/A",
        "n.a.",
        "",
        "   ",
        "()",
        "$",
    ],
)
def test_anything_not_certain_is_unparsable(raw):
    assert parse_value(raw) is None


def test_an_over_long_string_is_unparsable():
    assert parse_value("1" * 65) is None
    assert parse_value("1" * 64) is not None


def test_non_ascii_digits_are_unparsable_but_fullwidth_digits_are_normalised():
    assert parse_value("١٢") is None  # Arabic-Indic digits
    assert read("１，２３４．５０") == (Decimal("1234.50"), False)  # NFKC


# --- negative markers -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(1,234)", "-1234"),
        ("(245.10)", "-245.10"),
        ("(1,02,345.00)", "-102345.00"),
        ("-1,234.50", "-1234.50"),
        ("−1,234.50", "-1234.50"),  # U+2212
        ("–1,234.50", "-1234.50"),  # U+2013
        ("-12", "-12"),
        ("  (12)  ", "-12"),
    ],
)
def test_negative_markers_give_a_negative_value_and_are_reported(raw, expected):
    assert read(raw) == (Decimal(expected), True)


@pytest.mark.parametrize("raw", ["(1,234", "1,234)", "((1,234))", "(-1,234)", "-(1,234)", "--5", "- 5", "5-"])
def test_unbalanced_doubled_or_detached_markers_are_unparsable(raw):
    assert parse_value(raw) is None


def test_zero_in_brackets_is_zero_with_the_marker_reported():
    parsed = parse_value("(0.00)")

    assert parsed == ParsedValue(Decimal("0.00"), NUMBER, True)
    assert not parsed.value.is_signed()  # no negative zero


# --- currency symbols --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["$1,234", "$ 1,234", "₹1,23,456", "€1,234", "£1,234", "¥1,234"],
)
def test_one_leading_currency_symbol_is_ignored(raw):
    value, negative = read(raw)

    assert value > 0 and not negative


def test_a_currency_symbol_with_a_negative_marker():
    assert read("($1,234)") == (Decimal("-1234"), True)
    assert read("-$1,234") == (Decimal("-1234"), True)
    assert read("(₹1,23,456.70)") == (Decimal("-123456.70"), True)


@pytest.mark.parametrize("raw", ["$$1,234", "1,234$", "$-1,234", "$(1,234)", "INR 1,234", "Rs. 1,234", "USD1,234"])
def test_other_currency_forms_are_unparsable(raw):
    assert parse_value(raw) is None


# --- the nil convention (D-08) -----------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["-", "–", "—", "nil", "NIL", "Nil", "nIl", " – ", "－"])
def test_a_lone_dash_or_nil_is_a_reported_zero(raw):
    parsed = parse_value(raw)

    assert parsed == ParsedValue(Decimal(0), NIL, False)


@pytest.mark.parametrize(
    "raw",
    ["−", "‐", "‑", "--", "––", "- -", "nill", "nil.", "n/a", "$ -", "(-)", "-nil", "0-"],
)
def test_other_symbols_are_never_zero(raw):
    # FR-004.3: a blank cell, a missing value or any other symbol is never zero.
    assert parse_value(raw) is None


def test_nil_has_no_digits_and_zero_is_a_number_not_a_nil():
    assert parse_value("0").interpretation is NUMBER
    assert parse_value("-").interpretation is NIL


# --- determinism and round trips ------------------------------------------------------------------------------


def western(n: int) -> str:
    return f"{n:,}"


def indian(n: int) -> str:
    text = str(n)
    if len(text) <= 3:
        return text
    head, tail = text[:-3], text[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail])


@pytest.mark.parametrize("n", [0, 1, 99, 100, 999, 1000, 12345, 99999, 100000, 123456, 1234567, 12345678, 987654321, 10**12])
def test_western_and_indian_formatting_round_trip(n):
    assert read(western(n)) == (Decimal(n), False)
    assert read(indian(n)) == (Decimal(n), False)
    assert read(f"({indian(n)})") == (Decimal(-n), True)


def test_parsing_is_repeatable():
    assert parse_value("(1,23,456.70)") == parse_value("(1,23,456.70)")


def test_a_non_string_is_a_programming_error():
    with pytest.raises(TypeError):
        parse_value(1234)  # type: ignore[arg-type]


def test_the_unparsable_reason_is_a_provisional_placeholder():
    # FR-004.3 names no reason; the OD-1 proposal defers it (U-1, U-2).
    assert UNPARSABLE_REASON is StatusReason.PERIOD_NOT_VERIFIED


# --- applying the declared scale (H.1: values are held in base units) ----------------------------------------------


@pytest.mark.parametrize(
    ("scale", "expected"),
    [
        (Scale.UNITS, "1482.30"),
        (Scale.THOUSANDS, "1482300"),
        (Scale.LAKH, "148230000"),
        (Scale.MILLIONS, "1482300000"),
        (Scale.CRORE, "14823000000"),
        (Scale.BILLIONS, "1482300000000"),
    ],
)
def test_scale_is_applied_exactly(scale, expected):
    result = apply_scale(Decimal("1482.30"), scale)

    assert result == Decimal(expected)
    assert "E" not in str(result)  # positional form
    assert isinstance(result, Decimal)


def test_scale_keeps_every_digit_and_the_sign():
    assert apply_scale(Decimal("-0.0000001"), Scale.CRORE) == Decimal("-1")
    assert apply_scale(Decimal("123456789.123456789"), Scale.THOUSANDS) == Decimal("123456789123.456789")
    assert apply_scale(Decimal("0"), Scale.CRORE) == 0
    assert apply_scale(Decimal("1.5"), "lakh") == Decimal("150000")  # the enum's value is accepted


def test_an_unknown_scale_is_rejected():
    with pytest.raises(ValueError):
        apply_scale(Decimal(1), "myriad")  # type: ignore[arg-type]
