"""The final field set of a run (PRD FR-006, H.2, H.4).

``build_field_set`` turns the verified fields into the records the calculations and the
memo use, in this order: fields of another basis than the configured one are set aside
(D-06); duplicates are reconciled (H.4); implausible values are marked (FR-006.5); and a
``not_found`` record is added for every field and period still missing (FR-006.1).
Every record keeps its status; nothing downstream changes one.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from credit_intel.extraction.attributes import VerifiedAttributes
from credit_intel.extraction.bases import filter_by_basis
from credit_intel.extraction.missing import H3_FIELDS, PERIOD_ROLES, missing_fields
from credit_intel.extraction.plausibility import apply_plausibility
from credit_intel.extraction.reconcile import reconcile
from credit_intel.extraction.verify import FieldVerification
from credit_intel.ingestion.models import LocatorResult
from credit_intel.models import ExtractedField, FieldName, PeriodRole, SourceDocument, StatementBasis, Status

_FIELD_ORDER = {name: index for index, name in enumerate(H3_FIELDS)}
_ROLE_ORDER = {role: index for index, role in enumerate(PERIOD_ROLES)}


@dataclass(frozen=True)
class FieldSet:
    configured_basis: StatementBasis
    fields: tuple[ExtractedField, ...]  # the run's records, one per field ID
    ignored: tuple[ExtractedField, ...]  # verified fields of another basis, never used
    unplaced: tuple[FieldVerification, ...]  # fields with no usable period-end, so no record
    bases_present: tuple[str, ...]  # every known basis seen, for the memo

    @property
    def counts(self) -> dict[str, int]:
        """The number of records of each status."""
        found = Counter(record.status.value for record in self.fields)
        return {status.value: found.get(status.value, 0) for status in Status}

    def get(self, name: FieldName, role: PeriodRole) -> ExtractedField | None:
        """The run's record of a field and period, if the basis is the configured one."""
        for record in self.fields:
            if (
                record.field_name is name
                and record.period_role is role
                and record.statement_basis is self.configured_basis
            ):
                return record
        return None


def build_field_set(
    verifications: Sequence[FieldVerification],
    attributes: VerifiedAttributes,
    located: LocatorResult,
    configured_basis: StatementBasis,
    source_document: SourceDocument,
) -> FieldSet:
    if configured_basis not in (StatementBasis.CONSOLIDATED, StatementBasis.STANDALONE):
        raise ValueError("the configured basis is consolidated or standalone")
    records = [v.field for v in verifications if v.field is not None]
    unplaced = tuple(v for v in verifications if v.field is None)

    split = filter_by_basis(records, configured_basis.value, lambda record: record.statement_basis)
    reconciled = reconcile(split.kept, located)
    plausible = apply_plausibility(reconciled)
    absent = missing_fields(plausible, attributes, configured_basis, source_document)

    ordered = sorted(
        (*plausible, *absent),
        key=lambda r: (_FIELD_ORDER[r.field_name], _ROLE_ORDER[r.period_role], r.statement_basis.value),
    )
    return FieldSet(
        configured_basis=configured_basis,
        fields=tuple(ordered),
        ignored=tuple(split.ignored),
        unplaced=unplaced,
        bases_present=split.bases_present,
    )
