"""Reconciling duplicate occurrences of a field (PRD FR-006.2, H.4.1, H.4.2, H.4.6).

The same field, period and basis may be read from several pages. Verified (``extracted``)
occurrences are reconciled:

- identical values agree (an exact match is required when two occurrences are printed
  with the same precision);
- values printed with different precision agree if they differ by at most half a unit of
  the coarser value's last printed digit, in base units: with ``b`` the coarser value
  printed with ``p`` decimal places in a scale of size ``s``, ``|a - b| <= 0.5 * 10**-p * s``
  (H.4.2). Printed precision is read from the raw value, so ``1,234.50`` has two places;
- when they agree, the most precise value is used (ties go to the primary statement page,
  then the lowest page number) and the other occurrences are kept as
  ``corroborating_evidence``;
- otherwise the field is ``conflicting``: no value, every candidate with its evidence.

Occurrences that failed verification are never merged into a value. They are listed in the
record's ``validation.details`` so nothing is dropped silently, and a field with no verified
occurrence is the highest-ranked failed one. Nothing is rounded, averaged or picked "most
likely" (H.4.7).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from credit_intel.config import FIELD_STATEMENT_TYPES
from credit_intel.extraction.missing import H3_FIELDS, PERIOD_ROLES
from credit_intel.extraction.normalise import apply_scale, parse_value
from credit_intel.ingestion.models import LocatorResult
from credit_intel.models import ExtractedField, FieldName, Status

HALF = Decimal("0.5")


def primary_page(located: LocatorResult, field_name: FieldName) -> int | None:
    """The primary statement page of a field: the highest-scoring candidate page of the
    field's statement type, the lowest page number on a tie."""
    statement_type = FIELD_STATEMENT_TYPES.get(field_name.value)
    pages = [c for c in located.candidates if statement_type in c.statement_types]
    if not pages:
        return None
    return min(pages, key=lambda c: (-(c.score or 0), c.page_number)).page_number


@dataclass(frozen=True)
class _Occurrence:
    field: ExtractedField
    step: Decimal  # the size, in base units, of the last printed digit
    rank: tuple  # lower is better: primary page first, then page, then the text

    @property
    def evidence_key(self) -> tuple:
        return (self.field.page_number, self.field.evidence_quote, self.field.raw_value)


def _step(record: ExtractedField) -> Decimal:
    """``10**-p * s``: one unit of the last printed digit, in base units (H.4.2)."""
    parsed = parse_value(record.raw_value or "")
    places = 0 if parsed is None else max(0, -int(parsed.value.as_tuple().exponent))
    assert record.scale is not None
    return Decimal(1).scaleb(-places) * apply_scale(Decimal(1), record.scale)


def _consistent(a: _Occurrence, b: _Occurrence) -> bool:
    if a.step == b.step:
        return a.field.value == b.field.value
    fine, coarse = (a, b) if a.step < b.step else (b, a)
    assert fine.field.value is not None and coarse.field.value is not None
    return abs(fine.field.value - coarse.field.value) <= HALF * coarse.step


def _evidence(record: ExtractedField) -> dict:
    return {
        "page_number": record.page_number,
        "page_label": record.page_label,
        "evidence_quote": record.evidence_quote,
        "line_item_label": record.line_item_label,
        "raw_value": record.raw_value,
    }


def _rebuild(record: ExtractedField, **updates: object) -> ExtractedField:
    """A validated copy: the schema's invariants are checked on the result."""
    data = record.model_dump()
    data.update(updates)
    return ExtractedField.model_validate(data)


def _with_details(record: ExtractedField, **extra: object) -> dict:
    assert record.validation is not None
    validation = record.validation.model_dump()
    validation["details"] = {**validation["details"], **extra}
    return validation


def _other_occurrences(others: Sequence[ExtractedField]) -> list[dict]:
    return [
        {
            "page_number": o.page_number,
            "raw_value": o.raw_value,
            "evidence_quote": o.evidence_quote,
            "status": o.status.value,
            "status_reason": o.status_reason.value if o.status_reason else None,
        }
        for o in others
    ]


def _distinct(occurrences: Sequence[_Occurrence], exclude: Sequence[tuple] = ()) -> list[_Occurrence]:
    seen = set(exclude)
    kept = []
    for occurrence in sorted(occurrences, key=lambda o: o.rank):
        if occurrence.evidence_key not in seen:
            seen.add(occurrence.evidence_key)
            kept.append(occurrence)
    return kept


def _reconcile_group(group: Sequence[ExtractedField], primary: int | None) -> ExtractedField:
    def occurrence(record: ExtractedField) -> _Occurrence:
        rank = (
            0 if record.page_number == primary else 1,
            record.page_number or 0,
            record.raw_value or "",
            record.evidence_quote or "",
        )
        step = _step(record) if record.status is Status.EXTRACTED else Decimal(0)
        return _Occurrence(record, step, rank)

    occurrences = [occurrence(r) for r in group]
    verified = [o for o in occurrences if o.field.status is Status.EXTRACTED]
    failed = sorted((o for o in occurrences if o.field.status is not Status.EXTRACTED), key=lambda o: o.rank)

    if not verified:
        chosen, *rest = failed
        extra = _other_occurrences([o.field for o in rest])
        if not extra:
            return chosen.field
        return _rebuild(chosen.field, validation=_with_details(chosen.field, other_occurrences=extra))

    reference = min(verified, key=lambda o: (o.step, o.rank))
    unverified = _other_occurrences([o.field for o in failed])
    extra = {"unverified_occurrences": unverified} if unverified else {}

    if all(_consistent(reference, o) for o in verified):
        corroborating = _distinct(verified, exclude=[reference.evidence_key])
        updates: dict = {}
        if corroborating:
            updates["corroborating_evidence"] = [_evidence(o.field) for o in corroborating]
        if extra:
            updates["validation"] = _with_details(reference.field, **extra)
        return _rebuild(reference.field, **updates) if updates else reference.field

    candidates = _distinct(verified)
    primary_occurrence = min(verified, key=lambda o: o.rank)
    return _rebuild(
        primary_occurrence.field,
        status=Status.CONFLICTING,  # the occurrence was extracted, so its reason is already null
        value=None,
        currency=None,
        corroborating_evidence=[],
        candidates=[{**_evidence(o.field), "value": o.field.value} for o in candidates],
        validation=_with_details(
            primary_occurrence.field,
            conflict={
                "rule": "H.4.2",
                "values": [str(o.field.value) for o in candidates],
                "primary_page": primary_occurrence.field.page_number,
            },
            **extra,
        ),
    )


_FIELD_ORDER = {name: index for index, name in enumerate(H3_FIELDS)}
_ROLE_ORDER = {role: index for index, role in enumerate(PERIOD_ROLES)}


def reconcile(fields: Sequence[ExtractedField], located: LocatorResult) -> tuple[ExtractedField, ...]:
    """One record per field ID, from every occurrence of it, in field order (current period
    first, then by basis).

    ``fields`` are the verified source fields of one run (after the basis filter).
    """
    groups: dict[str, list[ExtractedField]] = defaultdict(list)
    for record in fields:
        groups[record.field_id].append(record)
    result = [
        _reconcile_group(group, primary_page(located, group[0].field_name))
        for group in groups.values()
    ]
    return tuple(
        sorted(
            result,
            key=lambda r: (_FIELD_ORDER[r.field_name], _ROLE_ORDER[r.period_role], r.statement_basis.value),
        )
    )
