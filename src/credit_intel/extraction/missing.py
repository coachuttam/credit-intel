"""Fields that were not found (PRD FR-006.1, FR-004.3, H.4.7).

Every H.3 field is expected for the current and the comparative period. One with no
record at all becomes ``not_found``; it is never filled with zero (a reported nil is a
different thing: the document printed a dash). A field that was proposed but failed a
check is not missing: it is already a record (``requires_review`` or ``conflicting``),
and so is one whose basis could not be read, so no ``not_found`` is placed beside it.

A period whose end date was not validated has no date to give a record, and its
absence is reported by the period-end attribute, so no records are made for it.
"""

from collections.abc import Sequence

from credit_intel.extraction.attributes import VerifiedAttributes
from credit_intel.models import (
    ExtractedField,
    FieldName,
    Origin,
    PeriodRole,
    SourceDocument,
    StatementBasis,
    Status,
    make_field_id,
)

# The twelve fields the model may return (H.3); EBIT is derived, never extracted.
H3_FIELDS: tuple[FieldName, ...] = tuple(name for name in FieldName if name is not FieldName.EBIT)
PERIOD_ROLES: tuple[PeriodRole, ...] = (PeriodRole.CURRENT, PeriodRole.COMPARATIVE)


def missing_fields(
    present: Sequence[ExtractedField],
    attributes: VerifiedAttributes,
    basis: StatementBasis,
    source_document: SourceDocument,
) -> tuple[ExtractedField, ...]:
    """A ``not_found`` record for each H.3 field and validated period with no record.

    ``present`` are the run's records after the basis filter. The new records have the
    run's ``basis`` and are in field order, current period first.
    """
    have = {(record.field_name, record.period_role) for record in present}
    records = []
    for name in H3_FIELDS:
        for role in PERIOD_ROLES:
            period_end = attributes.period_end(role)
            if period_end is None or (name, role) in have:
                continue
            records.append(
                ExtractedField(
                    field_id=make_field_id(name, period_end, basis),
                    field_name=name,
                    origin=Origin.SOURCE,
                    period_end=period_end,
                    period_length_months=12,
                    period_role=role,
                    statement_basis=basis,
                    status=Status.NOT_FOUND,
                    source_document=source_document,
                )
            )
    return tuple(records)
