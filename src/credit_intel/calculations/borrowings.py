"""Total borrowings (PRD H.3, H.5 rule 5, D-12; Phase 3 step 3b).

A reported total of borrowings is used as it is. Otherwise ``total_borrowings`` is derived by
``BORR-SUM`` from mutually exclusive components: non-current borrowings plus current
borrowings, and current maturities of long-term borrowings only when they are a separate
component. The current-maturities row is classified from the evidence in the row labels:

- ``included_in_current``: an inclusion phrase is in the current-borrowings label. Not added.
- ``separate_component``: its own row, and an exclusion phrase is in either label. Added.
- ``unresolved``: its own row, but neither of the above. ``requires_review``
  (``borrowings_classification_unresolved``).
- ``not_presented``: no such row. The two presented lines are summed and the value carries the
  caveat ``borrowings_not_presented_assumption`` (PRD v0.4.23, OD-9).

Lease liabilities are never a component (D-07). A missing component is never zero (rule 4); a
reported nil is a zero. Statuses follow ``derived.py``.
"""

import re

from credit_intel.calculations.derived import _derive
from credit_intel.config import BorrowingSettings
from credit_intel.extraction.field_set import FieldSet
from credit_intel.ingestion.locator import fold_phrase
from credit_intel.models import ExtractedField, FieldName, Origin, PeriodRole, Status, StatusReason

BORR_SUM = "BORR-SUM"
INCLUDED_IN_CURRENT = "included_in_current"
SEPARATE_COMPONENT = "separate_component"
UNRESOLVED = "unresolved"
NOT_PRESENTED = "not_presented"
CAVEAT_NOT_PRESENTED = "borrowings_not_presented_assumption"

_BASE = "total_borrowings = borrowings_non_current + borrowings_current"


def _label(record: ExtractedField | None) -> str:
    """The row label as printed: the verified one when the verifier stored it, else the proposed one."""
    if record is None or record.status is Status.NOT_FOUND:
        return ""
    stored = (record.validation.details.get("label") if record.validation is not None else None) or {}
    text = stored.get("label") if isinstance(stored, dict) else None
    return fold_phrase(text or record.line_item_label or "")


def _has_phrase(label: str, phrases: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(fold_phrase(phrase))}(?!\w)", label) for phrase in phrases)


def classify_current_maturities(
    current: ExtractedField | None, maturities: ExtractedField | None, settings: BorrowingSettings | None = None
) -> str:
    """The H.5 rule 5 case for the current-maturities row, from the two row labels."""
    settings = settings or BorrowingSettings()
    current_label = _label(current)
    if _has_phrase(current_label, settings.inclusion_phrases):
        return INCLUDED_IN_CURRENT
    if maturities is None or maturities.status is Status.NOT_FOUND:
        return NOT_PRESENTED
    if _has_phrase(current_label, settings.exclusion_phrases) or _has_phrase(_label(maturities), settings.exclusion_phrases):
        return SEPARATE_COMPONENT
    return UNRESOLVED


def derive_total_borrowings(
    non_current: ExtractedField | None,
    current: ExtractedField | None,
    maturities: ExtractedField | None,
    settings: BorrowingSettings | None = None,
) -> ExtractedField | None:
    """``total_borrowings`` for one period by ``BORR-SUM``, or ``None`` if there is no record at all."""
    case = classify_current_maturities(current, maturities, settings)
    both = [FieldName.BORROWINGS_NON_CURRENT, FieldName.BORROWINGS_CURRENT]
    if case == SEPARATE_COMPONENT:
        names, given = [*both, FieldName.CURRENT_MATURITIES_LONG_TERM_BORROWINGS], [non_current, current, maturities]
        formula, combine = f"{_BASE} + current_maturities_long_term_borrowings", lambda v: v[0] + v[1] + v[2]
    else:
        names, given = both, [non_current, current]
        formula, combine = _BASE, lambda v: v[0] + v[1]
    return _derive(
        FieldName.TOTAL_BORROWINGS, BORR_SUM, formula, names, given, combine,
        context=[maturities], classification=case,
        unresolved=StatusReason.BORROWINGS_CLASSIFICATION_UNRESOLVED if case == UNRESOLVED else None,
        record_inputs=[*both, FieldName.CURRENT_MATURITIES_LONG_TERM_BORROWINGS] if case == UNRESOLVED else None,
    )  # fmt: skip


def total_borrowings_for(
    field_set: FieldSet, role: PeriodRole, settings: BorrowingSettings | None = None
) -> ExtractedField | None:
    """The run's total of borrowings for a period: the reported one if there is a record that is
    not ``not_found`` (even unverified, as for operating profit), else the derived one."""
    reported = field_set.get(FieldName.TOTAL_BORROWINGS, role)
    if reported is not None and reported.status is not Status.NOT_FOUND:
        return reported
    derived = derive_total_borrowings(
        field_set.get(FieldName.BORROWINGS_NON_CURRENT, role),
        field_set.get(FieldName.BORROWINGS_CURRENT, role),
        field_set.get(FieldName.CURRENT_MATURITIES_LONG_TERM_BORROWINGS, role),
        settings,
    )
    return derived if derived is not None else reported


def caveats_of(record: ExtractedField | None) -> tuple[str, ...]:
    """The caveats a total of borrowings carries: the not-presented assumption, whatever its value."""
    if (
        record is not None
        and record.origin is Origin.DERIVED
        and record.status is Status.EXTRACTED
        and record.derivation is not None
        and record.derivation.method_id == BORR_SUM
        and record.derivation.component_classification == NOT_PRESENTED
    ):
        return (CAVEAT_NOT_PRESENTED,)
    return ()
