"""The layout stress matrix (Phase 7c): what the deterministic pipeline does with a perfect model on layouts that differ in one factor.

Each variant is a synthetic page (``stress_layouts.py``) and the reply a careful model would give. A variant either reads in full or it fails in
one named way, and the failure is pinned here as a **characterisation of 2026-11-05, not a requirement**: where a variant fails, the test records the
gap, so a later change that closes it flips the test on purpose and the change is seen. These are layouts chosen by me, not a sample of real reports.
"""

import pytest

from stress_layouts import EXPECTED, VARIANTS, Layout, matrix, run_layout, variant

FULL = {"stopped": None, "right": EXPECTED, "extracted": EXPECTED, "of": EXPECTED, "reasons": {}}


def stop(code):
    return {"stopped": code, "extracted": 0, "of": EXPECTED, "reasons": {}}


def refused(reason, extracted=0, right=0):
    return {"stopped": None, "extracted": extracted, "right": right, "of": EXPECTED, "reasons": {reason: EXPECTED - extracted}}


# name -> what the pipeline does today. FULL is a read in full; everything else is a gap characterised on 2026-11-05.
TODAY = {
    "base": FULL,
    "labels with item markers": FULL,
    "labels in capitals": FULL,
    "labels without the word total": stop("E-EXTRACT-NO-STATEMENT-PAGES"),  # the locator does not find the page, so the run stops
    "one label a synonym": refused("label_not_recognised", extracted=4, right=4),  # equity under another name is refused, its pair of values only
    "labels wrapped, figures on the second line": refused("label_not_recognised"),  # the row label is the second line alone
    "labels wrapped, figures on the first line": stop("E-EXTRACT-NO-STATEMENT-PAGES"),
    "title names no basis, basis asserted": FULL,
    "title names no basis, not asserted": stop("E-EXTRACT-BASIS-UNAVAILABLE"),
    "title is statement of financial position": FULL,
    "title is statement of assets and liabilities": stop("E-EXTRACT-NO-STATEMENT-PAGES"),
    "header March 31, 2025": FULL,
    "header 31.03.2025": FULL,
    "header years under As at": FULL,
    "header Dec 31, 2025": FULL,
    "header FY 2024-25": refused("period_mismatch"),  # a fiscal-year range is not read as a period end
    "comparative column first": FULL,
    "no notes column": FULL,
    "scale in lakhs": FULL,
    "US dollars in millions, written out": FULL,
    "dollar sign in millions": FULL,
    "no scale or currency declared": refused("scale_not_verified"),
    "lakh digit grouping": FULL,
    "a negative figure in brackets": FULL,
    "statement on two pages, run by the locator": FULL,
    "statement on two pages, pages given": FULL,  # until v0.4.74 this lost the four values on the second page (`scale_not_verified`)
    "second page headed by years only, pages given": refused("period_not_verified", extracted=2, right=2),  # a bare year equal to the current year is not resolved without a full date on that page
}


def test_every_variant_has_a_pinned_outcome_and_none_is_left_out():
    assert set(TODAY) == set(VARIANTS)


@pytest.mark.parametrize("name", list(VARIANTS))
def test_each_layout_does_what_it_did_on_the_day_it_was_characterised(name, tmp_path):
    result = run_layout(tmp_path, VARIANTS[name])

    assert {k: result.get(k) for k in TODAY[name]} == TODAY[name], f"{name}: {result}"


def test_the_matrix_runs_all_variants_in_one_call(tmp_path):
    results = matrix(tmp_path)

    assert set(results) == set(VARIANTS) and sum(r["stopped"] is None and r["right"] == EXPECTED for r in results.values()) == sum(v is FULL for v in TODAY.values())


# --- the harness itself ----------------------------------------------------------------------------------------------------------------------


def test_a_model_that_reports_a_value_the_page_does_not_print_is_not_counted_as_right(tmp_path):
    wrong = variant(values=(("1,482.30", "9,999.99"), ("600.00", "500.00"), ("900.00", "850.00")))
    result = run_layout(tmp_path, wrong)

    assert result["right"] < EXPECTED and result["extracted"] < EXPECTED and "value_not_in_evidence" in str(result["reasons"])


def test_a_model_that_reports_the_other_period_s_figure_is_refused_and_not_counted_as_right(tmp_path):
    other_period = variant(values=(("1,356.75", "1,482.30"), ("500.00", "600.00"), ("850.00", "900.00")))  # the figures are on the page, in the wrong periods
    result = run_layout(tmp_path, other_period)

    assert result["right"] == 0 and result["extracted"] == 0 and result["reasons"] == {"period_not_verified": EXPECTED}


def test_a_value_is_right_only_if_it_is_what_the_page_prints_for_that_period(tmp_path):
    result = run_layout(tmp_path, variant(comparative_first=True))

    assert result["right"] == EXPECTED  # the columns are read by their headings, so the values still land in the right periods
