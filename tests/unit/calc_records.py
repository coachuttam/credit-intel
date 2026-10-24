"""Synthetic field records for the calculation tests (Phase 3). Not a test module."""

from datetime import date
from decimal import Decimal

from credit_intel.models import (
    Candidate,
    ExtractedField,
    FieldName as F,
    Origin,
    PeriodRole,
    Scale,
    SourceDocument,
    StatementBasis as Basis,
    Status,
    StatusReason as R,
    make_field_id,
)

DOC = SourceDocument(file_name="r.pdf", sha256="a" * 64)
D25, D24 = date(2025, 3, 31), date(2024, 3, 31)
CUR = PeriodRole.CURRENT
CHECKS = {
    k: True
    for k in (
        "evidence_verified", "value_in_evidence", "label_verified", "period_end_verified",
        "period_column_verified", "sign_verified", "scale_verified", "currency_verified",
    )
}  # fmt: skip


def cand(value, quote="row", label="row", raw=None, page=3):
    return Candidate(page_number=page, evidence_quote=quote, line_item_label=label, raw_value=raw or str(value), value=Decimal(value))


def rec(name, value="100", status=Status.EXTRACTED, reason=None, currency="INR", end=D25, role=CUR, basis=Basis.CONSOLIDATED, candidates=(), label=None):
    extracted = status is Status.EXTRACTED
    if status is Status.REQUIRES_REVIEW and reason is None:
        reason = R.LABEL_NOT_RECOGNISED
    if status is Status.NOT_FOUND:
        return ExtractedField(field_id=make_field_id(name, end, basis), field_name=name, origin=Origin.SOURCE, period_end=end,
                              period_length_months=12, period_role=role, statement_basis=basis, status=status, source_document=DOC)  # fmt: skip
    return ExtractedField(
        field_id=make_field_id(name, end, basis), field_name=name, origin=Origin.SOURCE, period_end=end, period_length_months=12,
        period_role=role, statement_basis=basis, status=status, status_reason=reason if not extracted else None,
        value=Decimal(value) if extracted else None, currency=currency if extracted else None, raw_value=str(value),
        scale=Scale.CRORE, source_document=DOC, page_number=3, evidence_quote=f"{name.value} {value}", line_item_label=label or name.value,
        value_interpretation="number", validation={**CHECKS, "details": {}}, candidates=candidates,
    )  # fmt: skip


def conflicting(name, values):
    return rec(name, status=Status.CONFLICTING, candidates=tuple(cand(v, quote=f"{name.value} {v}", label=name.value) for v in values))
