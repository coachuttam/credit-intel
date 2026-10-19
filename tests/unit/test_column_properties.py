"""Property tests for the period-column check (OD-1 step 6d; B-209; AC-OD1-26, AC-OD1-24).

Layouts are generated with a fixed seed from synthetic data only. Every property
is checked on every claim of every layout, so a single violation fails the test.
"""

import random
from collections import Counter
from datetime import date

import pytest

from credit_intel.extraction.assignment import ColumnClaim, Failure, Outcome, check_column
from credit_intel.extraction.columns import PageStructure, analyse_structure, group_lines
from credit_intel.ingestion.locator import is_nil_token, is_numeric_token
from credit_intel.ingestion.models import PageWords, Word
from credit_intel.models import StatusReason

PERIODS = {"2025": date(2025, 3, 31), "2024": date(2024, 3, 31), "2023": date(2023, 3, 31)}
SEED = 20261019
CASES = 300
VALUES = ["1,234.50", "(45.00)", "-", "nil", "9,99,999.00", "0.00", "−7,000", "12"]
LABEL_WORDS = ["Total", "assets", "Borrowings", "and", "paid-in", "capital", "7,434", "24,000", "(a)", "-"]


def resolve(anchor):
    return PERIOD_LOOKUP.get(anchor.text)


PERIOD_LOOKUP = PERIODS


def w(text, x0, row, width=None):
    top = 100 + 14 * row
    return Word(text, x0, x0 + (5.0 * len(text) if width is None else width), top, top + 10)


def random_layout(rng: random.Random) -> PageWords:
    """A statement page: title, header (optional Note, 2 or 3 years), 1-4 figure rows."""
    gap = rng.choice([80, 90, 100])
    base = rng.choice([300, 320, 340])
    years = list(PERIODS)[: rng.choice([2, 3])]
    columns = [base + i * gap for i in range(len(years))]
    words = [w("Consolidated", 72, 0), w("Balance", 150, 0), w("Sheet", 200, 0)]
    header_row = 1
    if rng.random() < 0.7:
        words.append(w("Note", columns[0] - rng.choice([40, 50, 60]), header_row))
    words += [w(year, x, header_row) for year, x in zip(years, columns)]
    limit = min(x.x0 for x in words if x.top == 100 + 14 * header_row) - 3
    for row in range(2, 2 + rng.randint(1, 4)):
        x = 72.0
        for text in rng.sample(LABEL_WORDS, rng.randint(1, 3)):
            width = 5.0 * len(text)
            if x + width < limit - 1 or rng.random() < 0.1:  # sometimes a label word reaches the columns
                words.append(w(text, x, row))
            x += width + 6
        if rng.random() < 0.5:
            words.append(w("14", limit + 8 if rng.random() < 0.5 else columns[0] - 20, row))  # note-ish
        for x in columns:
            if rng.random() < 0.8:
                words.append(w(rng.choice(VALUES), x + rng.choice([-30, -20, -10, 0, 1, 2, 3]), row))
        if rng.random() < 0.15:
            words.append(w("77.00", rng.choice([columns[0] + 35, columns[-1] + 70]), row))  # stray token
    return PageWords(1, 595.0, 842.0, 0, tuple(words))


def all_claims(page: PageWords, structure: PageStructure):
    """A claim for every value-like word on every line, for every period of the page."""
    for line in structure.lines:
        for word in line.words:
            if is_numeric_token(word.text) or is_nil_token(word.text):
                for period in PERIODS.values():
                    for label_ok in (True, False):
                        yield ColumnClaim(period, word.text, line.text, label_ok)


def shifted(page: PageWords, dx: float) -> PageWords:
    return PageWords(
        page.page_number,
        page.width,
        page.height,
        page.rotation,
        tuple(Word(x.text, x.x0 + dx, x.x1 + dx, x.top, x.bottom) for x in page.words),
    )


@pytest.fixture(scope="module")
def results():
    rng = random.Random(SEED)
    out = []
    for _ in range(CASES):
        page = random_layout(rng)
        structure = analyse_structure(page, resolve)
        out.append((page, structure, [(c, check_column(structure, c)) for c in all_claims(page, structure)]))
    return out


def test_the_generator_exercises_passes_and_the_main_failures(results):
    kinds = Counter(r.failure for _, _, rs in results for _, r in rs)

    assert kinds[None] > 100
    for expected in (
        Failure.VALUE_DIFFERS,
        Failure.LINE_UNVERIFIED,
        Failure.CELL_NOT_UNIQUE,
        Failure.CELL_BLANK,
        Failure.NO_COLUMN,
        Failure.LABEL_NOT_RECOGNISED,
    ):
        assert kinds[expected] > 0, expected
    assert sum(1 for _, s, _ in results if not s.valid) == 0  # all generated pages are structurally valid


def test_the_generator_places_numbers_wholly_left_of_the_label_limit(results):
    left = [
        word
        for _, structure, _ in results
        for line in structure.lines
        for word in line.words
        if is_numeric_token(word.text) and word.x1 <= structure.label_limit
    ]

    assert len(left) > 50


def test_figures_reaching_left_of_their_header_are_assigned_to_their_own_column(results):
    reaching = [
        r
        for _, _, rs in results
        for _, r in rs
        if r.outcome is Outcome.PASS and r.token.x0 < r.column.x0
    ]

    assert len(reaching) > 20


def test_a_token_wholly_left_of_the_label_limit_is_never_a_value(results):
    assert any(r.outcome is Outcome.PASS for _, _, rs in results for _, r in rs)
    for _, structure, rs in results:
        for _, r in rs:
            if r.outcome is Outcome.PASS:
                assert r.token.x1 > structure.label_limit


def test_a_pass_always_has_the_token_in_the_claimed_column_only(results):
    for _, structure, rs in results:
        for claim, r in rs:
            if r.outcome is not Outcome.PASS:
                continue
            column = r.column
            assert column.period_end == claim.period_end
            assert r.token.x0 < column.x1 and r.token.x1 > column.x0
            others = [c for c in structure.columns if c is not column]
            assert not any(r.token.x0 < c.x1 and r.token.x1 > c.x0 for c in others)
            if structure.note_span:  # never wholly a note reference
                assert not (r.token.x0 >= structure.note_span.x0 and r.token.x1 <= structure.note_span.x1)


def test_a_pass_has_every_condition_true_and_no_reasons(results):
    for _, _, rs in results:
        for claim, r in rs:
            if r.outcome is Outcome.PASS:
                c = r.conditions
                assert all(v is True for v in vars(c).values())
                assert r.reasons == () and r.failure is None and claim.label_ok


def test_an_unrecognised_label_is_never_a_pass_and_is_always_reported_first(results):
    for _, _, rs in results:
        for claim, r in rs:
            if not claim.label_ok:
                assert r.outcome is Outcome.FAIL and r.token is None
                assert r.reasons[0] is StatusReason.LABEL_NOT_RECOGNISED
                assert r.conditions.row_label is False


def test_a_failure_other_than_the_label_always_reports_period_not_verified(results):
    for _, _, rs in results:
        for _, r in rs:
            if r.failure not in (None, Failure.LABEL_NOT_RECOGNISED):
                assert StatusReason.PERIOD_NOT_VERIFIED in r.reasons


def test_the_label_limit_is_never_right_of_a_column_or_the_note_span(results):
    for _, structure, _ in results:
        edges = [c.x0 for c in structure.columns] + ([structure.note_span.x0] if structure.note_span else [])
        assert structure.label_limit == min(edges)


@pytest.mark.parametrize("dx", [25.0, -40.5, 200.25])
def test_shifting_every_x_by_a_constant_changes_no_outcome(results, dx):
    for page, structure, rs in results[:100]:
        moved_structure = analyse_structure(shifted(page, dx), resolve)
        assert moved_structure.problems == structure.problems
        assert moved_structure.label_limit == structure.label_limit + dx
        for claim, r in rs:
            moved = check_column(moved_structure, claim)
            assert (moved.outcome, moved.failure, moved.reasons) == (r.outcome, r.failure, r.reasons)
            assert (moved.token.text if moved.token else None) == (r.token.text if r.token else None)
            assert moved.conditions == r.conditions


def test_shuffling_the_word_order_changes_nothing(results):
    rng = random.Random(SEED + 1)
    for page, structure, rs in results[:60]:
        words = list(page.words)
        rng.shuffle(words)
        mixed = analyse_structure(PageWords(1, page.width, page.height, 0, tuple(words)), resolve)
        assert mixed == structure
        for claim, r in rs[:20]:
            assert check_column(mixed, claim) == r


def test_repeating_the_analysis_gives_identical_results(results):
    for page, structure, rs in results[:30]:
        assert analyse_structure(page, resolve) == structure
        for claim, r in rs[:10]:
            assert check_column(structure, claim) == r


def test_lines_do_not_depend_on_word_order():
    rng = random.Random(SEED + 2)
    for _ in range(50):
        page = random_layout(rng)
        words = list(page.words)
        expected = group_lines(words)
        rng.shuffle(words)
        assert group_lines(words) == expected
