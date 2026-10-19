"""Field verification and assembly (PRD FR-005.3, H.1, H.1.2; Phase 2 step 7e).

``FieldVerifier.verify`` runs every deterministic check on one proposed field and
builds its ``ExtractedField``. A field is ``extracted`` only if every check passed;
otherwise it is ``requires_review`` with the reason of the first failing check in the
order of FR-005.3:

    evidence_not_verified, value_not_in_evidence, label_not_recognised, period_mismatch,
    [basis_unknown], period_not_verified, sign_mismatch, scale_not_verified or
    scale_ambiguous, currency_not_verified

``basis_unknown`` is not in the PRD's list; it sits next to ``period_mismatch``, the
other reason that comes from metadata rather than the row; a field takes the basis of its
own statement (H.4.6), not the document's. Evidence is never edited:
the quote, label and raw value are stored exactly as proposed. The value is the
parsed raw value (with its sign) scaled exactly, in ``Decimal``.

``reasons`` lists every failing reason in that order, so a caller can see all of them;
the field's ``status_reason`` is the first.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from credit_intel.config import (
    FIELD_STATEMENT_TYPES,
    ColumnSettings,
    DeclarationSettings,
    LabelSettings,
    LocatorSettings,
)
from credit_intel.extraction.assignment import ColumnCheck, ColumnClaim, Outcome, check_column, link_quote
from credit_intel.extraction.attributes import VerifiedAttributes, blocking_reasons
from credit_intel.extraction.bases import field_basis
from credit_intel.extraction.columns import PageStructure, analyse_structure
from credit_intel.extraction.declarations import check_currency, check_scale, check_sign
from credit_intel.extraction.labels import LabelCheck, check_label
from credit_intel.extraction.normalise import apply_scale, parse_value
from credit_intel.extraction.periods import page_period_resolver
from credit_intel.extraction.presence import check_presence
from credit_intel.extraction.runs import statement_run_start
from credit_intel.ingestion.models import LocatorResult, PageText, PageWords
from credit_intel.models import (
    ExtractedField,
    ExtractionResponse,
    FieldName,
    Origin,
    PeriodRole,
    ProposedField,
    SourceDocument,
    Status,
    StatementBasis,
    StatusReason,
    Validation,
    ValueInterpretation,
    make_field_id,
)

R = StatusReason
# FR-005.3 order. basis_unknown is placed with the other attribute-derived reason.
_ORDER = (
    R.EVIDENCE_NOT_VERIFIED,
    R.VALUE_NOT_IN_EVIDENCE,
    R.LABEL_NOT_RECOGNISED,
    R.PERIOD_MISMATCH,
    R.BASIS_UNKNOWN,
    R.PERIOD_NOT_VERIFIED,
    R.SIGN_MISMATCH,
    R.SCALE_NOT_VERIFIED,
    R.SCALE_AMBIGUOUS,
    R.CURRENCY_NOT_VERIFIED,
)


@dataclass(frozen=True)
class VerificationContext:
    """What verification needs: the candidate pages (text and words), the locator
    result, the verified document-level attributes, and the settings."""

    source_document: SourceDocument
    pages: Mapping[int, PageText]  # candidate pages only
    page_words: Mapping[int, PageWords]  # candidate pages only
    located: LocatorResult
    attributes: VerifiedAttributes
    label_settings: LabelSettings | None = None
    declaration_settings: DeclarationSettings | None = None
    column_settings: ColumnSettings | None = None
    locator_settings: LocatorSettings | None = None


@dataclass(frozen=True)
class FieldVerification:
    proposed: ProposedField
    # None when the claimed period has no usable end date at all (not proposed, or not an
    # ISO date), so there is no field ID to give it; ``reasons`` then holds period_mismatch.
    field: ExtractedField | None
    reasons: tuple[StatusReason, ...] = field(default_factory=tuple)


def _period(attributes: VerifiedAttributes, role: PeriodRole) -> tuple[date | None, bool]:
    """The claimed period-end and whether its attribute is validated."""
    attribute = (
        attributes.current_period_end if role is PeriodRole.CURRENT else attributes.comparative_period_end
    )
    if attribute.normalised_value is None:
        return None, False
    try:
        return date.fromisoformat(attribute.normalised_value.strip()), attribute.status is Status.EXTRACTED
    except ValueError:
        return None, False


class FieldVerifier:
    def __init__(self, context: VerificationContext) -> None:
        self._ctx = context
        self._structures: dict[int, PageStructure | None] = {}

    def _structure(self, page_number: int) -> PageStructure | None:
        if page_number not in self._structures:
            ctx = self._ctx
            words, page = ctx.page_words.get(page_number), ctx.pages.get(page_number)
            if words is None or page is None:
                self._structures[page_number] = None
            else:
                resolver = page_period_resolver(
                    words,
                    page.text,
                    ctx.column_settings,
                    ctx.locator_settings,
                    known_current=ctx.attributes.period_end(PeriodRole.CURRENT),
                )
                self._structures[page_number] = analyse_structure(
                    words, resolver, ctx.column_settings, ctx.locator_settings
                )
        return self._structures[page_number]

    def verify_all(self, response: ExtractionResponse) -> tuple[FieldVerification, ...]:
        return tuple(self.verify(proposed) for proposed in response.fields)

    def verify(self, proposed: ProposedField) -> FieldVerification:
        ctx = self._ctx
        attributes = ctx.attributes
        name = FieldName(proposed.field_name.value)
        role = proposed.period_role
        period_end, period_valid = _period(attributes, role)
        blockers = blocking_reasons(attributes, role)
        failing: set[StatusReason] = set()

        # FR-005.1 and .2
        texts = {n: p.text for n, p in ctx.pages.items()}
        presence = check_presence(texts, proposed.page_number, proposed.evidence_quote, proposed.raw_value)
        if not presence.evidence_verified:
            failing.add(R.EVIDENCE_NOT_VERIFIED)
        if not presence.value_in_evidence:
            failing.add(R.VALUE_NOT_IN_EVIDENCE)

        # Document-level attributes the field depends on (H.1.2)
        failing.update(blockers)

        basis_info = field_basis(name.value, proposed.page_number, ctx.pages, ctx.located, ctx.locator_settings)
        if basis_info[0] is StatementBasis.UNKNOWN:
            failing.add(R.BASIS_UNKNOWN)

        # Link the quote to a figure line, then FR-005.10 on that line
        structure = self._structure(proposed.page_number)
        line = None
        label: LabelCheck | None = None
        if structure is not None:
            failure, line = link_quote(proposed.raw_value, proposed.evidence_quote, structure)
            if line is not None:
                label = check_label(
                    name.value,
                    line.text,
                    [candidate.text for candidate in structure.lines],
                    line.index,
                    ctx.label_settings,
                )
                if not label.ok:
                    failing.add(R.LABEL_NOT_RECOGNISED)

        # FR-005.7, the period column. Only a field whose period is validated can claim one.
        column: ColumnCheck | None = None
        column_verified: bool | None = None
        if period_valid and period_end is not None:
            if structure is None:
                column_verified = False
            else:
                column = check_column(structure, ColumnClaim(period_end, proposed.raw_value, proposed.evidence_quote, True))
                column_verified = column.outcome is Outcome.PASS
            if not column_verified:
                failing.add(R.PERIOD_NOT_VERIFIED)

        # FR-005.6, sign
        parsed = parse_value(proposed.raw_value)
        sign = None
        if column is not None and column_verified and column.parsed is not None and parsed is not None:
            sign = check_sign(parsed, column.parsed)
            if not sign.ok:
                failing.add(R.SIGN_MISMATCH)

        # FR-005.8, scale and currency on the cited page or the first page of its statement run
        scale = currency = None
        page = ctx.pages.get(proposed.page_number)
        if page is not None:
            start = statement_run_start(ctx.located, proposed.page_number, FIELD_STATEMENT_TYPES[name.value])
            run_page = ctx.pages.get(start) if start is not None and start != proposed.page_number else None
            run_text = run_page.text if run_page is not None else None
            scale = check_scale(proposed.scale, page.text, run_text, ctx.declaration_settings)
            currency = check_currency(proposed.currency, page.text, run_text, ctx.declaration_settings)
            if not scale.ok:
                failing.add(scale.reason or R.SCALE_NOT_VERIFIED)
            if not currency.ok:
                failing.add(R.CURRENCY_NOT_VERIFIED)

        # Scale: one reason, the field's own check first, else the attribute's.
        if R.SCALE_AMBIGUOUS in failing and R.SCALE_NOT_VERIFIED in failing:
            failing.discard(R.SCALE_NOT_VERIFIED)
        reasons = tuple(reason for reason in _ORDER if reason in failing)

        if period_end is None:
            return FieldVerification(proposed, None, reasons)  # reasons holds period_mismatch

        # Each field has the basis of its own statement (H.4.6), not the document's one.
        basis = basis_info[0]
        extracted = not reasons
        validation = Validation(
            evidence_verified=presence.evidence_verified,
            value_in_evidence=presence.value_in_evidence,
            label_verified=label.ok if label is not None else None,
            period_end_verified=period_valid,
            period_column_verified=column_verified,
            sign_verified=sign.ok if sign is not None else None,
            scale_verified=scale.ok if scale is not None else None,
            currency_verified=currency.ok if currency is not None else None,
            details=self._details(role, label, column, sign, scale, currency, blockers, basis_info),
        )
        record = ExtractedField(
            field_id=make_field_id(name, period_end, basis),
            field_name=name,
            origin=Origin.SOURCE,
            period_end=period_end,
            period_length_months=12,
            period_role=role,
            statement_basis=basis,
            status=Status.EXTRACTED if extracted else Status.REQUIRES_REVIEW,
            status_reason=None if extracted else reasons[0],
            value=apply_scale(parsed.value, proposed.scale) if extracted and parsed is not None else None,
            currency=proposed.currency if extracted else None,
            raw_value=proposed.raw_value,
            # An unparsable raw value (which can never be extracted) is recorded as a number.
            value_interpretation=parsed.interpretation if parsed is not None else ValueInterpretation.NUMBER,
            scale=proposed.scale,
            source_document=ctx.source_document,
            page_number=proposed.page_number,
            page_label=page.page_label if page is not None else None,
            evidence_quote=proposed.evidence_quote,
            line_item_label=proposed.line_item_label,
            validation=validation,
        )
        return FieldVerification(proposed, record, reasons)

    def _details(self, role, label, column, sign, scale, currency, blockers, basis_info) -> dict:
        evidence = self._ctx.attributes.period_evidence.get(role)
        details: dict = {
            "period": {
                "role": role.value,
                "evidence": None
                if evidence is None
                else {
                    "raw_text": evidence.raw_text,
                    "method": evidence.method.value,
                    "derived_from": evidence.derived_from.isoformat() if evidence.derived_from else None,
                },
            },
            "blocked_by": [reason.value for reason in blockers],
            "basis": {"value": basis_info[0].value, "read_from": basis_info[1]},
            "label": None
            if label is None
            else {
                "label": label.label,
                "normalised": label.normalised,
                "matched_phrase": label.matched_phrase,
                "section": label.section,
            },
            "column": None,
            "sign": None if sign is None else {"marker_on_page": sign.marker_present, "raw_negative": sign.negative},
            "scale": None
            if scale is None
            else {
                "declared_on_cited_page": sorted(s.value for s in scale.declared_on_cited_page),
                "declared_on_run_start": sorted(s.value for s in scale.declared_on_run_start),
                "supported_by": scale.supported_by,
            },
            "currency": None if currency is None else {"supported_by": currency.supported_by},
        }
        if column is not None:
            token = column.token
            details["column"] = {
                "failure": column.failure.value if column.failure else None,
                "conditions": {k: v for k, v in vars(column.conditions).items()},
                "figure_line_index": column.figure_line.index if column.figure_line else None,
                "region": None if column.column is None else [column.column.x0, column.column.x1],
                "anchor_quotes": [a.text for a in column.anchors],
                "region_words": [w.text for w in column.region_words],
                "token": None
                if token is None
                else {"text": token.text, "x0": token.x0, "x1": token.x1, "top": token.top, "bottom": token.bottom},
            }
        return details
