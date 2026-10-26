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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from credit_intel.config import (
    FIELD_STATEMENT_TYPES,
    ColumnSettings,
    DeclarationSettings,
    LabelSettings,
    LocatorSettings,
)
from credit_intel.extraction.assertion import BasisAssertion
from credit_intel.extraction.assignment import ColumnCheck, ColumnClaim, Outcome, check_column, link_quote
from credit_intel.extraction.attributes import VerifiedAttributes, blocking_reasons
from credit_intel.extraction.bases import field_basis
from credit_intel.extraction.columns import PageStructure, analyse_structure
from credit_intel.extraction.declarations import check_currency, check_scale, check_sign
from credit_intel.extraction.ocr_evidence import OcrReading, ocr_evidence_for
from credit_intel.extraction.labels import LabelCheck, check_label, expense_table_heading, row_label
from credit_intel.extraction.normalise import apply_scale, parse_value
from credit_intel.extraction.periods import page_period_resolver
from credit_intel.extraction.presence import check_presence
from credit_intel.extraction.runs import statement_run_start
from credit_intel.ingestion.locator import title_lines
from credit_intel.ingestion.models import LocatorResult, PageText, PageWords
from credit_intel.models import (
    BasisEvidence,
    EvidenceSource,
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
ASSERTION_SOURCE = "analyst_assertion"  # `details.basis.read_from` for a basis the analyst asserted
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
    R.OCR_UNCONFIRMED,  # last: a field that fails an earlier check keeps that reason (FR-005 criterion 11)
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
    assertion: BasisAssertion | None = None  # the analyst's assertion of the basis (H.4.6, v0.4.24)
    ocr_column_settings: ColumnSettings | None = None  # the column settings for pages read by OCR, instead of column_settings (v0.4.44)
    ocr: OcrReading | None = None  # the pages whose text is an OCR reading; a field cited on one is OCR evidence (v0.4.44)


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


# The component fields a failed ``total_borrowings`` proposal can be re-filed as (PRD v0.4.38).
_BORROWING_COMPONENTS = ("borrowings_non_current", "borrowings_current", "current_maturities_long_term_borrowings")


# The fields the code reads when the model proposed none, and the statement each is read from (PRD v0.4.39, v0.4.40).
_SCANNED_FIELDS = {**{name: "balance_sheet" for name in _BORROWING_COMPONENTS}, "interest_expense": "income_statement"}


@dataclass(frozen=True)
class FieldRefiling:
    """A ``total_borrowings`` proposal whose row is a borrowings component, verified as that component (PRD v0.4.38)."""

    proposed: str
    used: str
    page: int
    period: str


@dataclass(frozen=True)
class FieldScan:
    """A borrowings component or interest-expense row the model did not propose, read from its statement's page by the code (PRD v0.4.39, v0.4.40)."""

    field: str
    page: int
    period: str
    label: str  # the row label as printed


class FieldVerifier:
    def __init__(self, context: VerificationContext) -> None:
        self._ctx = context
        self._structures: dict[int, PageStructure | None] = {}
        self.refilings: tuple[FieldRefiling, ...] = ()
        self.scans: tuple[FieldScan, ...] = ()

    def _columns(self, page_number: int) -> ColumnSettings | None:
        """The column settings for a page: the OCR ones for a page read by OCR (FR-005 criterion 11), else the text-layer ones."""
        ctx = self._ctx
        if ctx.ocr is not None and ctx.ocr_column_settings is not None and page_number in ctx.ocr.pages:
            return ctx.ocr_column_settings
        return ctx.column_settings

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
                    self._columns(page_number),
                    ctx.locator_settings,
                    known_current=ctx.attributes.period_end(PeriodRole.CURRENT),
                )
                self._structures[page_number] = analyse_structure(
                    words, resolver, self._columns(page_number), ctx.locator_settings
                )
        return self._structures[page_number]

    def verify_all(self, response: ExtractionResponse) -> tuple[FieldVerification, ...]:
        proposals, self.refilings = self._refiled(response.fields)
        added, self.scans = self._scanned(proposals)
        return tuple(self.verify(proposed) for proposed in (*proposals, *added))

    def _statement_pages(self, statement_type: str) -> list[int]:
        """The candidate pages of a statement: located as one, or (a page range records no types) titled as one."""
        ctx = self._ctx
        located = {c.page_number: c.statement_types for c in ctx.located.candidates}
        return [
            number
            for number, page in sorted(ctx.pages.items())
            if statement_type in located.get(number, ())
            or any(t.statement_type == statement_type for t in title_lines(page.text, ctx.locator_settings))
        ]

    def _scanned(self, proposals: Sequence[ProposedField]) -> tuple[tuple[ProposedField, ...], tuple[FieldScan, ...]]:
        """PRD v0.4.39: a borrowings component row the model did not propose is proposed by the code, to the same checks.

        Only a gap is filled: the model's proposal for a field and period always stands. A field with more than one
        recognised line on the run, or a document whose currency or scale or period columns are not validated, adds nothing.
        """
        ctx = self._ctx
        attributes = ctx.attributes
        if attributes.scale.status is not Status.EXTRACTED or attributes.reporting_currency.status is not Status.EXTRACTED:
            return (), ()
        found: dict[str, list[tuple[int, PageStructure, object]]] = {name: [] for name in _SCANNED_FIELDS}
        for statement_type in sorted(set(_SCANNED_FIELDS.values())):
            names = [name for name, kind in _SCANNED_FIELDS.items() if kind == statement_type]
            for number in self._statement_pages(statement_type):
                structure = self._structure(number)
                if structure is None or not structure.valid:
                    continue
                page_lines = [candidate.text for candidate in structure.lines]
                for line in structure.lines:
                    for name in names:
                        if check_label(name, line.text, page_lines, line.index, ctx.label_settings).ok:
                            found[name].append((number, structure, line))
        taken = {(p.field_name.value, p.period_role) for p in proposals}
        added: list[ProposedField] = []
        scans: list[FieldScan] = []
        for name, matches in found.items():
            if len(matches) != 1:
                continue
            number, structure, line = matches[0]
            for role in (PeriodRole.CURRENT, PeriodRole.COMPARATIVE):
                period_end, valid = _period(attributes, role)
                columns = [c for c in structure.columns if c.period_end == period_end]
                if (name, role) in taken or not valid or not columns:
                    continue
                words = [w for w in line.words if w.x0 < columns[0].x1 and w.x1 > columns[0].x0]
                if not words:
                    continue
                added.append(
                    ProposedField.model_validate(
                        {
                            "field_name": name,
                            "period_role": role.value,
                            "raw_value": " ".join(w.text for w in words),
                            "scale": attributes.scale.normalised_value,
                            "currency": attributes.reporting_currency.normalised_value,
                            "page_number": number,
                            "evidence_quote": line.text,
                            "line_item_label": row_label(line.text),
                        }
                    )
                )
                scans.append(FieldScan(name, number, role.value, row_label(line.text)))
        return tuple(added), tuple(scans)

    def _component_for(self, proposed: ProposedField) -> str | None:
        """The one component field whose label rule the cited figure's row satisfies, if ``total_borrowings`` does not (v0.4.38)."""
        structure = self._structure(proposed.page_number)
        if structure is None:
            return None
        _, line = link_quote(proposed.raw_value, proposed.evidence_quote, structure)
        if line is None:
            return None
        ctx = self._ctx
        page_lines = [candidate.text for candidate in structure.lines]
        if check_label("total_borrowings", line.text, page_lines, line.index, ctx.label_settings).ok:
            return None
        recognised = [
            name
            for name in _BORROWING_COMPONENTS
            if check_label(name, line.text, page_lines, line.index, ctx.label_settings).ok
        ]
        return recognised[0] if len(recognised) == 1 else None

    def _refiled(self, proposals: Sequence[ProposedField]) -> tuple[tuple[ProposedField, ...], tuple[FieldRefiling, ...]]:
        """PRD v0.4.38: a ``total_borrowings`` proposal on a component row is verified as that component.

        Only the field name changes. It is dropped, not added, if the model already proposed that component for the period.
        """
        taken = {(p.field_name.value, p.period_role) for p in proposals}
        result: list[ProposedField] = []
        refilings: list[FieldRefiling] = []
        for proposed in proposals:
            component = self._component_for(proposed) if proposed.field_name.value == FieldName.TOTAL_BORROWINGS.value else None
            if component is None:
                result.append(proposed)
            elif (component, proposed.period_role) not in taken:
                taken.add((component, proposed.period_role))
                result.append(proposed.model_copy(update={"field_name": type(proposed.field_name)(component)}))
                refilings.append(FieldRefiling(proposed.field_name.value, component, proposed.page_number, proposed.period_role.value))
            # else: the model's own component proposal stands and this one is dropped, so the figure is counted once
        return tuple(result), tuple(refilings)

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
        basis_evidence = BasisEvidence.TITLE
        if (
            basis_info[0] is StatementBasis.UNKNOWN
            and ctx.assertion is not None
            and proposed.page_number in ctx.assertion.applied_pages
        ):  # the assertion fills a page whose own evidence gives no basis (H.4.6, v0.4.24); it never replaces a known one
            basis_info = (ctx.assertion.basis, ASSERTION_SOURCE)
            basis_evidence = BasisEvidence.ANALYST_ASSERTION
        if basis_info[0] is StatementBasis.UNKNOWN:
            failing.add(R.BASIS_UNKNOWN)

        # FR-005 criterion 11: a page read by OCR gives evidence that is never extracted
        is_ocr = ctx.ocr is not None and proposed.page_number in ctx.ocr.pages
        if is_ocr:
            failing.add(R.OCR_UNCONFIRMED)

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
                column = check_column(
                    structure, ColumnClaim(period_end, proposed.raw_value, proposed.evidence_quote, True),
                    (self._columns(proposed.page_number) or ColumnSettings()).split_figure_gap_pt,
                )  # fmt: skip
                column_verified = column.outcome is Outcome.PASS
            if not column_verified:
                failing.add(R.PERIOD_NOT_VERIFIED)

        # FR-005.6, sign
        # A figure the PDF library reported in pieces is read as the joined figure (PRD v0.4.35): the raw value, as printed, has the pieces' spaces.
        parsed = parse_value(column.raw_figure if column is not None and column.raw_figure is not None else proposed.raw_value)
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
        # FR-006.5 (v0.4.33): a bracketed interest expense under the heading of an income-and-expense table is a positive expense.
        expense_rule = bool(
            extracted and parsed is not None and parsed.value < 0 and name is FieldName.INTEREST_EXPENSE
            and structure is not None and line is not None
            and expense_table_heading([candidate.text for candidate in structure.lines], line.index, ctx.label_settings)
        )  # fmt: skip
        validation = Validation(
            evidence_verified=presence.evidence_verified,
            value_in_evidence=presence.value_in_evidence,
            label_verified=label.ok if label is not None else None,
            period_end_verified=period_valid,
            period_column_verified=column_verified,
            sign_verified=sign.ok if sign is not None else None,
            scale_verified=scale.ok if scale is not None else None,
            currency_verified=currency.ok if currency is not None else None,
            details=self._details(role, label, column, sign, scale, currency, blockers, basis_info, expense_rule),
        )
        record = ExtractedField(
            field_id=make_field_id(name, period_end, basis),
            field_name=name,
            origin=Origin.SOURCE,
            period_end=period_end,
            period_length_months=12,
            period_role=role,
            statement_basis=basis,
            basis_evidence=basis_evidence,
            status=Status.EXTRACTED if extracted else Status.REQUIRES_REVIEW,
            status_reason=None if extracted else reasons[0],
            value=apply_scale(abs(parsed.value) if expense_rule else parsed.value, proposed.scale) if extracted and parsed is not None else None,
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
            evidence_source=EvidenceSource.OCR if is_ocr else EvidenceSource.TEXT_LAYER,
            ocr_evidence=ocr_evidence_for(ctx.ocr, proposed.page_number, proposed.evidence_quote, line.words if line is not None else None)
            if is_ocr and ctx.ocr is not None
            else None,
        )
        return FieldVerification(proposed, record, reasons)

    def _details(self, role, label, column, sign, scale, currency, blockers, basis_info, expense_rule=False) -> dict:
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
            "sign": None
            if sign is None
            else {"marker_on_page": sign.marker_present, "raw_negative": sign.negative, **({"expense_table_rule": True} if expense_rule else {})},
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
                **({"joined_pieces": [list(chain) for chain in column.joined_pieces]} if column.joined_pieces else {}),  # only when a join happened (v0.4.35)
                "region_words": [w.text for w in column.region_words],
                "token": None
                if token is None
                else {"text": token.text, "x0": token.x0, "x1": token.x1, "top": token.top, "bottom": token.bottom},
            }
        return details
