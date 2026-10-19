"""Plausibility of extracted values (PRD FR-006.5).

Before any calculation, a value that is implausible for its field is set to
``requires_review`` with reason ``implausible_value``: a negative ``revenue``,
``current_assets``, ``current_liabilities``, ``total_borrowings``,
``borrowings_non_current``, ``borrowings_current`` or ``interest_expense``. Negative
``net_profit``, ``profit_before_tax``, ``operating_profit`` and ``total_equity`` are valid,
and a field the PRD does not list (such as the current maturities) is never judged. The
evidence is kept; only the status, the reason and the value change, so no later stage
needs to change a status (FR-006.5, FR-007.5).
"""

from collections.abc import Sequence

from credit_intel.models import ExtractedField, FieldName, Status, StatusReason

MUST_NOT_BE_NEGATIVE: frozenset[FieldName] = frozenset(
    {
        FieldName.REVENUE,
        FieldName.CURRENT_ASSETS,
        FieldName.CURRENT_LIABILITIES,
        FieldName.TOTAL_BORROWINGS,
        FieldName.BORROWINGS_NON_CURRENT,
        FieldName.BORROWINGS_CURRENT,
        FieldName.INTEREST_EXPENSE,
    }
)


def is_implausible(record: ExtractedField) -> bool:
    # Only an extracted field has a value (the schema requires it), so a field that
    # was not found, conflicts or needs review is never judged here.
    return record.field_name in MUST_NOT_BE_NEGATIVE and record.value is not None and record.value < 0


def apply_plausibility(fields: Sequence[ExtractedField]) -> tuple[ExtractedField, ...]:
    """Each implausible extracted field becomes ``requires_review``; the rest are unchanged."""
    result = []
    for record in fields:
        if not is_implausible(record):
            result.append(record)
            continue
        data = record.model_dump()
        if data["validation"] is not None:
            data["validation"]["details"] = {
                **data["validation"]["details"],
                "plausibility": {"rule": "FR-006.5", "value": str(record.value)},
            }
        data.update(
            status=Status.REQUIRES_REVIEW,
            status_reason=StatusReason.IMPLAUSIBLE_VALUE,
            value=None,
            currency=None,
        )
        result.append(ExtractedField.model_validate(data))
    return tuple(result)
