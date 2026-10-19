"""Sign, scale and currency checks (PRD FR-005.6, FR-005.8; step 7c; B-214).

Appendix B Examples 2 and 3 and B.6 rows 11 to 13. Pure functions on synthetic text.
"""

from decimal import Decimal

import pytest

from credit_intel.config import (
    BALANCE_SHEET,
    FIELD_STATEMENT_TYPES,
    INCOME_STATEMENT,
    DeclarationSettings,
    LabelSettings,
)
from credit_intel.extraction.declarations import (
    CITED_PAGE,
    RUN_START,
    check_currency,
    check_scale,
    check_sign,
    find_scales,
)
from credit_intel.extraction.normalise import apply_scale, parse_value
from credit_intel.models import Scale, StatusReason

REASON_NOT_VERIFIED = StatusReason.SCALE_NOT_VERIFIED
REASON_AMBIGUOUS = StatusReason.SCALE_AMBIGUOUS


# --- sign (FR-005.6) -------------------------------------------------------------------------


def sign(raw, token):
    return check_sign(parse_value(raw), parse_value(token))


def test_example_2_the_unbracketed_raw_value_for_a_bracketed_cell_is_a_mismatch():
    result = sign("245.10", "(245.10)")

    assert not result.ok and result.marker_present and not result.negative


def test_example_2_the_bracketed_raw_value_passes():
    assert sign("(245.10)", "(245.10)").ok


@pytest.mark.parametrize("minus", ["-", "−", "–"])
def test_an_attached_minus_must_be_matched_by_a_negative_raw_value(minus):
    assert sign(f"{minus}1,234", f"{minus}1,234").ok
    assert sign("(1,234)", f"{minus}1,234").ok  # brackets and a minus are both negative
    assert not sign("1,234", f"{minus}1,234").ok


def test_no_marker_on_the_page_means_the_raw_value_must_not_be_negative():
    assert sign("312.40", "312.40").ok
    assert not sign("(312.40)", "312.40").ok
    assert not sign("-312.40", "312.40").ok


def test_a_reported_nil_passes_whatever_the_dash():
    for dash in ("-", "–", "—"):
        result = sign(dash, dash)
        assert result.ok and not result.marker_present and not result.negative
    assert sign("nil", "-").ok


def test_a_nil_on_only_one_side_is_compared_like_any_other_value():
    assert not sign("-", "(5.00)").ok
    assert not sign("(5.00)", "-").ok
    assert sign("-", "5.00").ok  # no marker either side; the column check rejects the mismatch


def test_a_negative_zero_is_still_negative_by_its_marker():
    assert sign("(0.00)", "(0.00)").ok
    assert not sign("0.00", "(0.00)").ok


def test_the_result_reports_both_signs():
    result = sign("(5.00)", "5.00")

    assert (result.ok, result.marker_present, result.negative) == (False, False, True)


# --- finding scale declarations ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "scale"),
    [
        ("(₹ in crore)", Scale.CRORE),
        ("₹ in Crores", Scale.CRORE),
        ("(Rs. in lakh)", Scale.LAKH),
        ("Amount in Rs. Lakhs", Scale.LAKH),
        ("in ₹ lakh", Scale.LAKH),
        ("Rupees in crore", Scale.CRORE),
        ("USD '000", Scale.THOUSANDS),
        ("USD ’000", Scale.THOUSANDS),
        ("(USD 000s)", Scale.THOUSANDS),
        ("(000s)", Scale.THOUSANDS),
        ("(000)", Scale.THOUSANDS),
        ("in 000s", Scale.THOUSANDS),
        ("in 000", Scale.THOUSANDS),
        ("(in thousands)", Scale.THOUSANDS),
        ("in millions", Scale.MILLIONS),
        ("USD in Millions", Scale.MILLIONS),
        ("figures in USD millions, except per share", Scale.MILLIONS),
        ("in $ millions", Scale.MILLIONS),
        ("in mn", Scale.MILLIONS),
        ("in billions", Scale.BILLIONS),
        ("in bn", Scale.BILLIONS),
        ("in rupees", Scale.UNITS),
        ("(in actuals)", Scale.UNITS),
        ("in absolute figures", Scale.UNITS),
        ("in units", Scale.UNITS),
        ("in rupees crore", Scale.CRORE),
        ("in dollars thousands", Scale.THOUSANDS),
    ],
)
def test_declarations_in_the_forms_the_prd_gives(text, scale):
    assert find_scales(text) == {scale}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Total assets 1,740.00",
        "a guarantee of 5 crore was given",
        "increase in revenue",
        "the million-dollar question",
        "in the thousands of cases",
        "1,000 and 2,000",
        "in 0005",
        "9,000s",
    ],
)
def test_text_that_is_not_a_declaration_is_not_found(text):
    assert find_scales(text) == frozenset()


def test_a_page_can_declare_more_than_one_scale():
    assert find_scales("(₹ in crore) and also (₹ in lakh)") == {Scale.CRORE, Scale.LAKH}


def test_line_breaks_inside_a_declaration_do_not_stop_it():
    assert find_scales("Amounts in\n  Crore") == {Scale.CRORE}


# --- the scale check (Example 3) -----------------------------------------------------------------


CRORE_PAGE = "Balance Sheet (₹ in crore)\nTotal assets 1,740.00"


def test_example_3_a_scale_the_page_does_not_declare_is_not_verified():
    result = check_scale(Scale.LAKH, CRORE_PAGE)

    assert not result.ok and result.reason is REASON_NOT_VERIFIED


def test_the_declared_scale_is_verified():
    result = check_scale(Scale.CRORE, CRORE_PAGE)

    assert result.ok and result.reason is None and result.supported_by == CITED_PAGE


def test_example_3_two_different_declarations_on_the_cited_page_are_ambiguous():
    page = "(₹ in crore)\n... (₹ in lakh)"

    for claimed in (Scale.CRORE, Scale.LAKH, Scale.MILLIONS):
        result = check_scale(claimed, page)
        assert not result.ok and result.reason is REASON_AMBIGUOUS


def test_the_same_scale_declared_twice_is_not_ambiguous():
    assert check_scale(Scale.CRORE, "(₹ in crore) ... (Rs. in crores)").ok


def test_no_declaration_anywhere_is_not_verified():
    result = check_scale(Scale.CRORE, "Total assets 1,740.00", "Balance Sheet")

    assert not result.ok and result.reason is REASON_NOT_VERIFIED


def test_a_continuation_page_uses_the_first_page_of_its_run():
    result = check_scale(Scale.CRORE, "Total equity 600.00", CRORE_PAGE)

    assert result.ok and result.supported_by == RUN_START


def test_a_declaration_on_the_cited_page_takes_precedence_over_the_first_page():
    first = "(₹ in lakh)"
    cited = "(₹ in crore)"

    assert check_scale(Scale.CRORE, cited, first).ok
    result = check_scale(Scale.LAKH, cited, first)
    assert not result.ok and result.reason is REASON_NOT_VERIFIED


def test_two_scales_on_the_first_page_are_ambiguous_when_the_cited_page_declares_none():
    result = check_scale(Scale.CRORE, "Total equity 600.00", "(₹ in crore) (₹ in lakh)")

    assert not result.ok and result.reason is REASON_AMBIGUOUS


def test_a_scale_of_units_needs_a_declaration_like_any_other():
    assert not check_scale(Scale.UNITS, "Total assets 1,740.00").ok
    assert check_scale(Scale.UNITS, "(Amounts in rupees)").ok
    assert not check_scale(Scale.UNITS, CRORE_PAGE).ok


def test_the_result_records_what_was_declared_where():
    result = check_scale(Scale.CRORE, "(₹ in crore)", "(₹ in lakh)")

    assert result.declared_on_cited_page == {Scale.CRORE}
    assert result.declared_on_run_start == {Scale.LAKH}


def test_b6_row_11_thousands_scale_applies_exactly():
    page = "Total current assets 14 840,000 760,000\n(₹ in thousands)"

    assert check_scale(Scale.THOUSANDS, page).ok
    assert apply_scale(Decimal("840000"), Scale.THOUSANDS) == Decimal("840000000")


def test_b6_row_1_crore_scale_gives_base_units():
    assert apply_scale(Decimal("1482.30"), Scale.CRORE) == Decimal("14823000000.00")


# --- currency -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "text"),
    [
        ("INR", "All amounts in INR"),
        ("INR", "(₹ in crore)"),
        ("INR", "(Rs. in lakh)"),
        ("INR", "Amount in Rupees"),
        ("USD", "USD '000"),
        ("USD", "(in $ millions)"),
        ("USD", "US$ in millions"),
        ("USD", "All amounts in dollars"),
        ("EUR", "€ million"),
        ("GBP", "£ thousands"),
        ("AED", "AED in thousands"),
        ("AED", "amounts in Dirhams"),
        ("JPY", "¥ millions"),
        ("CHF", "CHF in millions"),
    ],
)
def test_a_symbol_an_iso_code_or_a_name_supports_the_currency(code, text):
    assert check_currency(code, text).ok


@pytest.mark.parametrize(
    ("code", "text"),
    [
        ("INR", "Total assets 1,740.00"),
        ("INR", "(in $ millions)"),
        ("USD", "(₹ in crore)"),
        ("USD", "Distribution in thousands of units"),
        ("ALL", "we reviewed all items and tried everything"),
        ("TRY", "we try to reach"),
        ("CHF", "(in $ millions)"),
        ("AUD", "(in $ millions)"),
        ("INR", "Rsvp by Friday"),
        ("INR", "cars and bars 12"),
        ("USD", "wildollars"),
        ("USD", ""),
    ],
)
def test_other_text_does_not_support_the_currency(code, text):
    assert not check_currency(code, text).ok


def test_an_iso_code_must_be_in_capitals_and_a_whole_word():
    assert check_currency("ALL", "Amounts in ALL").ok
    assert not check_currency("ALL", "Amounts in all").ok
    assert not check_currency("USD", "USDX").ok
    assert not check_currency("INR", "xINR").ok


def test_a_continuation_page_uses_the_first_page_of_its_run_for_currency():
    result = check_currency("INR", "Total equity 600.00", "(₹ in crore)")

    assert result.ok and result.supported_by == RUN_START
    assert check_currency("INR", "(Rs. in lakh)", "nothing").supported_by == CITED_PAGE


def test_no_support_anywhere_gives_no_source():
    result = check_currency("INR", "x", "y")

    assert not result.ok and result.supported_by is None


# --- settings ---------------------------------------------------------------------------------------------------


def test_every_extractable_field_has_a_statement_type_and_label_rule():
    assert set(FIELD_STATEMENT_TYPES) == set(LabelSettings().rules)
    assert set(FIELD_STATEMENT_TYPES.values()) == {INCOME_STATEMENT, BALANCE_SHEET}
    assert FIELD_STATEMENT_TYPES["revenue"] == INCOME_STATEMENT
    assert FIELD_STATEMENT_TYPES["total_equity"] == BALANCE_SHEET
    assert FIELD_STATEMENT_TYPES["interest_expense"] == INCOME_STATEMENT


def test_configured_scale_words_replace_the_defaults():
    settings = DeclarationSettings(scale_words={"crore": ("cr",)}, unit_currency_words=())

    assert find_scales("(in cr)", settings) == {Scale.CRORE}
    assert find_scales("(in crore)", settings) == frozenset()


def test_configured_currency_tokens_replace_the_defaults():
    settings = DeclarationSettings(currency_tokens={"INR": ("inr rupees",)})

    assert check_currency("INR", "amounts in inr rupees", settings=settings).ok
    assert not check_currency("INR", "(₹ in crore)", settings=settings).ok
