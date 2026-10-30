"""Derived values (PRD H.5): EBIT from operating profit, or from profit before tax plus interest.

A derived value is computed from other fields of the same period and basis. It has no quote
of its own: its evidence is the evidence of its inputs, named in its derivation record, and
a derived value that is ``conflicting`` lists the combined candidate results.

Status (H.5 rule 2): ``extracted`` only if every input is. Otherwise the first applicable of
``not_found`` (reason ``missing_input``), ``conflicting``, ``requires_review`` (the input's
reason). Where an input is ``conflicting`` but another input has no value, the combined
candidate results cannot be listed, so the result is ``requires_review`` with that other input's
reason (an interpretation: the field model requires candidates for a ``conflicting`` record).

Method choice (rule 3) is fixed: ``EBIT-OP`` whenever ``operating_profit`` is reported, whatever
its status, and ``EBIT-PBT`` only when it is ``not_found``. A missing input is never zero.
"""

from collections.abc import Callable, Sequence
from decimal import Decimal
from itertools import product

from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import (
    BasisEvidence,
    Candidate,
    Derivation,
    ExtractedField,
    FieldName,
    Origin,
    PeriodRole,
    Status,
    StatusReason,
    make_field_id,
)

EBIT_OP = "EBIT-OP"
EBIT_PBT = "EBIT-PBT"


def _options(record: ExtractedField) -> list[tuple[Decimal, Candidate]]:
    """The values a ``conflicting`` or ``extracted`` input can take, each with its evidence."""
    if record.status is Status.CONFLICTING:
        return [(c.value, c) for c in record.candidates]
    assert record.value is not None
    own = Candidate(
        page_number=record.page_number,
        page_label=record.page_label,
        evidence_quote=record.evidence_quote,
        line_item_label=record.line_item_label,
        raw_value=record.raw_value,
        value=record.value,
    )
    return [(record.value, own)]


def _combined_candidates(
    records: Sequence[ExtractedField], combine: Callable[[Sequence[Decimal]], Decimal]
) -> tuple[Candidate, ...]:
    """Every result the inputs allow, each carrying its inputs' evidence side by side."""
    results = []
    for choice in product(*(_options(record) for record in records)):
        evidence = [candidate for _, candidate in choice]
        results.append(
            Candidate(
                page_number=evidence[0].page_number,
                page_label=evidence[0].page_label,
                evidence_quote=" | ".join(e.evidence_quote for e in evidence),
                line_item_label=" + ".join(e.line_item_label for e in evidence),
                raw_value=" + ".join(e.raw_value for e in evidence),
                value=combine([value for value, _ in choice]),
            )
        )
    return tuple(results)


def _derive(
    name: FieldName,
    method_id: str,
    formula: str,
    wanted: Sequence[FieldName],
    given: Sequence[ExtractedField | None],
    combine: Callable[[Sequence[Decimal]], Decimal],
    context: Sequence[ExtractedField | None] = (),
    classification: str | None = None,
    unresolved: StatusReason | None = None,
    record_inputs: Sequence[FieldName] | None = None,
) -> ExtractedField | None:
    """One derived record from ``given`` (aligned with ``wanted``; ``None`` is a missing record).

    ``classification`` is recorded in the derivation (H.5 rule 5). ``unresolved`` is a reason that
    turns an otherwise ``extracted`` result into ``requires_review``. ``record_inputs`` names the
    fields listed in the derivation when they are not just the ones combined.
    ``context`` are other records of the same period (for example a ``not_found`` operating
    profit), used only to find the period and basis when no input has a record. Returns
    ``None`` when there is no record at all, because then there is no period or basis. Raises ``ValueError`` for inputs of different bases or
    periods roles, which is a caller error; inputs with different period ends are data, and
    give ``requires_review`` with ``period_mismatch``.
    """
    present = [record for record in given if record is not None]
    anchors = present or [record for record in context if record is not None]
    if not anchors:
        return None
    first = anchors[0]
    if any(r.statement_basis is not first.statement_basis or r.period_role is not first.period_role for r in [*present, *anchors]):
        raise ValueError("a derived value uses inputs of one basis and one period role")
    # A value derived from an input whose basis the analyst asserted rests on that assertion too (H.4.6, v0.4.24).
    asserted = any(r.basis_evidence is BasisEvidence.ANALYST_ASSERTION for r in present)
    if record_inputs:
        ids = tuple(make_field_id(field, first.period_end, first.statement_basis) for field in record_inputs)
    else:  # only inputs that have a record: an ID with no record in the results cannot be traced (K.10)
        ids = tuple(record.field_id for record in anchors)  # no input at all: the record it was anchored on
    derivation = Derivation(method_id=method_id, formula=formula, input_field_ids=ids, component_classification=classification)

    def build(status: Status, reason: StatusReason | None = None, value: Decimal | None = None,
              currency: str | None = None, candidates: tuple[Candidate, ...] = ()) -> ExtractedField:  # fmt: skip
        return ExtractedField(
            field_id=make_field_id(name, first.period_end, first.statement_basis),
            field_name=name, origin=Origin.DERIVED, period_end=first.period_end, period_length_months=12,
            period_role=first.period_role, statement_basis=first.statement_basis, status=status,
            status_reason=reason, value=value, currency=currency, derivation=derivation, candidates=candidates,
            basis_evidence=BasisEvidence.ANALYST_ASSERTION if asserted else BasisEvidence.TITLE,
        )  # fmt: skip

    statuses = [record.status if record is not None else Status.NOT_FOUND for record in given]
    if Status.NOT_FOUND in statuses:
        return build(Status.NOT_FOUND, StatusReason.MISSING_INPUT)
    review = [r for r in present if r.status is Status.REQUIRES_REVIEW]
    if Status.CONFLICTING in statuses and not review:
        return build(Status.CONFLICTING, candidates=_combined_candidates(present, combine))
    if review:
        return build(Status.REQUIRES_REVIEW, review[0].status_reason)
    if len({r.period_end for r in present}) > 1:
        return build(Status.REQUIRES_REVIEW, StatusReason.PERIOD_MISMATCH)
    if len({r.currency for r in present}) > 1:
        return build(Status.REQUIRES_REVIEW, StatusReason.CURRENCY_MISMATCH)
    if unresolved is not None:
        return build(Status.REQUIRES_REVIEW, unresolved)
    values = [r.value for r in present]
    assert all(v is not None for v in values)
    return build(Status.EXTRACTED, value=combine(values), currency=first.currency)  # type: ignore[arg-type]


def derive_ebit(
    operating_profit: ExtractedField | None,
    profit_before_tax: ExtractedField | None,
    interest_expense: ExtractedField | None,
) -> ExtractedField | None:
    """``ebit`` for one period (H.5): ``EBIT-OP`` if operating profit is reported, else ``EBIT-PBT``."""
    if operating_profit is not None and operating_profit.status is not Status.NOT_FOUND:
        return _derive(
            FieldName.EBIT, EBIT_OP, "ebit = operating_profit",
            [FieldName.OPERATING_PROFIT], [operating_profit], lambda values: values[0],
        )  # fmt: skip
    return _derive(
        FieldName.EBIT, EBIT_PBT, "ebit = profit_before_tax + interest_expense",
        [FieldName.PROFIT_BEFORE_TAX, FieldName.INTEREST_EXPENSE], [profit_before_tax, interest_expense],
        lambda values: values[0] + values[1], context=[operating_profit],
    )  # fmt: skip


def derive_ebit_for(field_set: FieldSet, role: PeriodRole) -> ExtractedField | None:
    """``ebit`` for one period of a run's field set (the configured basis only)."""
    return derive_ebit(
        field_set.get(FieldName.OPERATING_PROFIT, role),
        field_set.get(FieldName.PROFIT_BEFORE_TAX, role),
        field_set.get(FieldName.INTEREST_EXPENSE, role),
    )
