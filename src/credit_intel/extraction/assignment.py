"""Assigning a proposed value to a period column (PRD FR-005.7, OD-1 step 6c).

``check_column`` decides whether the value a model proposed for a period sits in
that period's column on the page: the quote is linked to exactly one word-line
(3.5), and on that line the conditions B (boundary), U (uniqueness), N (number) and
the value match are evaluated for the claimed column, together with S (the page
structure is valid) and R (the row label, supplied by the caller). Every
condition's result is recorded (3.7).

This is only the period-column part of the evidence checks. It never sets a field's
status. ``reasons`` lists the reasons that apply, in the order FR-005.3 ranks them,
so the caller (step 7) can merge them with the other checks. Sign (FR-005.6) is not
checked here: brackets and an attached minus are ignored when comparing values.
"""

from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from credit_intel.extraction.columns import (
    Column,
    Line,
    NoteSpan,
    PageStructure,
    PeriodAnchor,
    clean_text,
)
from credit_intel.extraction.normalise import CURRENCY_SYMBOLS, ParsedValue, parse_value
from credit_intel.ingestion.locator import is_nil_token, is_numeric_token, lines_of
from credit_intel.ingestion.models import Word
from credit_intel.models import StatusReason


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class Failure(StrEnum):
    """The first failing situation, in evaluation order (3.7)."""

    STRUCTURE_INVALID = "structure_invalid"  # S
    QUOTE_NOT_LINKED = "quote_not_linked"  # the raw value is on no quote line
    QUOTE_AMBIGUOUS = "quote_ambiguous"  # the raw value is on more than one quote line
    NO_FIGURE_LINE = "no_figure_line"
    FIGURE_LINE_AMBIGUOUS = "figure_line_ambiguous"
    NO_COLUMN = "no_column"  # the claimed period has no column on the page
    LINE_UNVERIFIED = "line_unverified"  # B
    CELL_BLANK = "cell_blank"
    CELL_NOT_UNIQUE = "cell_not_unique"  # U
    TOKEN_UNPARSABLE = "token_unparsable"  # N
    VALUE_DIFFERS = "value_differs"
    LABEL_NOT_RECOGNISED = "label_not_recognised"  # R


@dataclass(frozen=True)
class ColumnClaim:
    """A proposed value and where it is claimed to be.

    ``label_ok`` is the FR-005.10 result for the value line's row label, computed by
    the caller (built in step 7). ``raw_value`` is as the model returned it.
    """

    period_end: date
    raw_value: str
    evidence_quote: str
    label_ok: bool


@dataclass(frozen=True)
class Conditions:
    """Each condition's result; ``None`` means it was not evaluated (an earlier one failed)."""

    structure: bool | None = None  # S
    linked: bool | None = None  # the quote is linked to exactly one word-line (3.5)
    column: bool | None = None  # the claimed period has a column
    boundary: bool | None = None  # B, for every numeric or nil token right of the label limit
    unique: bool | None = None  # U
    number: bool | None = None  # N
    value_matches: bool | None = None
    row_label: bool | None = None  # R


@dataclass(frozen=True)
class ColumnCheck:
    outcome: Outcome
    failure: Failure | None
    reasons: tuple[StatusReason, ...]  # FR-005.3 order: label_not_recognised, then period_not_verified
    conditions: Conditions
    claim: ColumnClaim
    figure_line: Line | None = None
    column: Column | None = None
    anchors: tuple[PeriodAnchor, ...] = ()
    region_words: tuple[Word, ...] = ()
    token: Word | None = None  # the assigned token, only when the outcome is PASS
    parsed: ParsedValue | None = None


def _overlaps(word: Word, x0: float, x1: float) -> bool:
    return word.x0 < x1 and word.x1 > x0


def _is_value_like(text: str) -> bool:
    return is_numeric_token(text) or is_nil_token(text)


def _link_quote(claim: ColumnClaim, structure: PageStructure) -> tuple[Failure | None, Line | None]:
    """3.5: the figure line holding the quote's value line, or why there is none."""
    raw = clean_text(claim.raw_value)
    value_lines = [line for line in lines_of(claim.evidence_quote) if raw and raw in line]
    if not value_lines:
        return Failure.QUOTE_NOT_LINKED, None
    if len(value_lines) > 1:
        return Failure.QUOTE_AMBIGUOUS, None
    matching = [line for line in structure.lines if value_lines[0] in line.text]
    if not matching:
        return Failure.NO_FIGURE_LINE, None
    if len(matching) > 1:
        return Failure.FIGURE_LINE_AMBIGUOUS, None
    return None, matching[0]


def _same_value(proposed: ParsedValue | None, token: ParsedValue | None) -> bool:
    # Digits and decimals only: brackets and minus belong to the sign check (FR-005.6).
    return (
        proposed is not None
        and token is not None
        and abs(proposed.value) == abs(token.value)
        and proposed.interpretation == token.interpretation
    )


def check_column(structure: PageStructure, claim: ColumnClaim) -> ColumnCheck:
    """Evaluate the period-column conditions for one proposed value (3.6, 3.7)."""
    label_reasons = () if claim.label_ok else (StatusReason.LABEL_NOT_RECOGNISED,)

    def result(
        failure: Failure | None, conditions: Conditions, **details: object
    ) -> ColumnCheck:
        conditions = replace(conditions, row_label=claim.label_ok)
        if failure is None and not claim.label_ok:
            # Nothing is assigned when the row label is not recognised (AC-OD1-20).
            failure = Failure.LABEL_NOT_RECOGNISED
            details = {k: v for k, v in details.items() if k not in ("token", "parsed")}
        period_failed = failure not in (None, Failure.LABEL_NOT_RECOGNISED)
        reasons = label_reasons + ((StatusReason.PERIOD_NOT_VERIFIED,) if period_failed else ())
        outcome = Outcome.PASS if failure is None else Outcome.FAIL
        return ColumnCheck(outcome, failure, reasons, conditions, claim, **details)  # type: ignore[arg-type]

    if not structure.valid:
        return result(Failure.STRUCTURE_INVALID, Conditions(structure=False))
    failure, line = _link_quote(claim, structure)
    if failure is not None:
        return result(failure, Conditions(structure=True, linked=False))
    columns = [c for c in structure.columns if c.period_end == claim.period_end]
    if not columns:
        return result(
            Failure.NO_COLUMN, Conditions(structure=True, linked=True, column=False), figure_line=line
        )
    column = columns[0]
    assert line is not None and structure.label_limit is not None

    # B: every numeric or nil token right of the label limit overlaps exactly one period
    # region. One that overlaps none is a note reference if it touches the note span,
    # and a stray token otherwise. A token reaching into the note span from its own
    # period region (a right-aligned figure wider than its header) belongs to that
    # region (FR-005.7: "that column's region and no other").
    note: NoteSpan | None = structure.note_span

    def boundary_ok(word: Word) -> bool:
        regions = sum(_overlaps(word, c.x0, c.x1) for c in structure.columns)
        if regions == 1:
            return True
        return regions == 0 and note is not None and _overlaps(word, note.x0, note.x1)

    boundary = all(
        boundary_ok(w)
        for w in line.words
        if _is_value_like(w.text) and w.x1 > structure.label_limit
    )

    in_region = tuple(w for w in line.words if _overlaps(w, column.x0, column.x1))
    candidates = [
        w for w in in_region if _is_value_like(w.text) or any(ch.isdigit() for ch in w.text)
    ]
    others = [w for w in in_region if w not in candidates and w.text not in CURRENCY_SYMBOLS]
    blank = not candidates and not others
    unique = len(candidates) == 1 and not others

    token = candidates[0] if unique else None
    token_parsed = parse_value(token.text) if token is not None else None
    number = (
        token is not None and _is_value_like(token.text) and token_parsed is not None
    )
    matches = number and _same_value(parse_value(claim.raw_value), token_parsed)

    conditions = Conditions(
        structure=True,
        linked=True,
        column=True,
        boundary=boundary,
        unique=unique,
        number=number if unique else None,
        value_matches=matches if number else None,
    )
    details = {
        "figure_line": line,
        "column": column,
        "anchors": column.anchors,
        "region_words": in_region,
    }
    if not boundary:
        return result(Failure.LINE_UNVERIFIED, conditions, **details)
    if blank:
        return result(Failure.CELL_BLANK, conditions, **details)
    if not unique:
        return result(Failure.CELL_NOT_UNIQUE, conditions, **details)
    if not number:
        return result(Failure.TOKEN_UNPARSABLE, conditions, **details)
    if not matches:
        return result(Failure.VALUE_DIFFERS, conditions, **details)
    return result(None, conditions, token=token, parsed=token_parsed, **details)
