"""Document-level attributes (PRD H.1.2, FR-005.9, H.4.6; Phase 2 step 7d).

The model proposes five attributes with evidence: the entity name, the current and
comparative period-ends, the statement basis, the reporting currency and the scale.
Each is checked deterministically here, and a field may not be ``extracted`` if an
attribute it depends on is not (``blocking_reason``).

- every attribute: the quote is on the cited (candidate) page (FR-005.1) and the raw
  text is in the quote (FR-005.2);
- ``period_end``: the raw text is in a title or column header (above the page's first
  figure line), validates under FR-005.9 (``periods``), and its ISO date equals the
  normalised value; the later of the two is the current period, and the comparative
  must be the previous year on the same month and day (H.1.1);
- ``statement_basis``: the raw text is in a title block that names exactly that basis
  (H.4.6);
- ``reporting_currency``: a sign, code or name for the code in the quote or on the cited page (FR-005.8, v0.4.30); ``scale``: the quote itself supports it (FR-005.8).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from credit_intel.config import DeclarationSettings, LocatorSettings
from credit_intel.extraction.declarations import check_currency, check_scale, find_currencies, find_scales
from credit_intel.extraction.periods import (
    Method,
    PeriodEvidence,
    header_year_tokens,
    parse_year_token,
    periods_are_consecutive,
    resolve_anchor_texts,
)
from credit_intel.extraction.assertion import BasisAssertion
from credit_intel.extraction.presence import check_presence, normalise_for_match
from credit_intel.ingestion.locator import fold_phrase, is_figure_word, lines_of, title_block_bases
from credit_intel.models import (
    BasisEvidence,
    DocumentAttribute,
    DocumentAttributeName,
    PeriodRole,
    ProposedAttribute,
    Scale,
    StatementBasis,
    Status,
    StatusReason,
)

_ISO_CURRENCY = re.compile(r"[A-Z]{3}")
_BASES = ("consolidated", "standalone")

Name = DocumentAttributeName


@dataclass(frozen=True)
class PageRepair:
    """A currency or scale declaration verified on another page than the one the model cited (PRD v0.4.36)."""

    attribute: str
    cited_page: int
    page_used: int


@dataclass(frozen=True)
class VerifiedAttributes:
    entity_name: DocumentAttribute
    current_period_end: DocumentAttribute
    comparative_period_end: DocumentAttribute
    statement_basis: DocumentAttribute
    reporting_currency: DocumentAttribute
    scale: DocumentAttribute
    # How each validated period-end was validated (raw text, method, derivation).
    period_evidence: Mapping[PeriodRole, PeriodEvidence] = field(default_factory=dict)
    # Each declaration verified on a page other than the cited one: the cited page and the page used (recorded in the manifest only).
    page_repairs: tuple[PageRepair, ...] = ()

    @property
    def all(self) -> tuple[DocumentAttribute, ...]:
        return (
            self.entity_name,
            self.current_period_end,
            self.comparative_period_end,
            self.statement_basis,
            self.reporting_currency,
            self.scale,
        )

    def period_end(self, role: PeriodRole) -> date | None:
        """The period-end, only if its attribute is ``extracted``."""
        attribute = (
            self.current_period_end if role is PeriodRole.CURRENT else self.comparative_period_end
        )
        if attribute.status is not Status.EXTRACTED or attribute.normalised_value is None:
            return None
        return date.fromisoformat(attribute.normalised_value)


def _record(proposal: ProposedAttribute, status: Status, reason: StatusReason | None) -> DocumentAttribute:
    return DocumentAttribute(
        attribute=proposal.attribute,
        period_role=proposal.period_role if proposal.attribute is Name.PERIOD_END else None,
        raw_text=proposal.raw_text,
        normalised_value=proposal.normalised_value.strip(),  # a derived form; the evidence is kept as proposed
        page_number=proposal.page_number,
        evidence_quote=proposal.evidence_quote,
        status=status,
        status_reason=reason,
    )


def _not_found(name: Name, role: PeriodRole | None = None) -> DocumentAttribute:
    return DocumentAttribute(attribute=name, period_role=role, status=Status.NOT_FOUND)


def _presence_reason(proposal: ProposedAttribute, pages: Mapping[int, str]) -> StatusReason | None:
    result = check_presence(pages, proposal.page_number, proposal.evidence_quote, proposal.raw_text)
    if not result.evidence_verified:
        return StatusReason.EVIDENCE_NOT_VERIFIED
    if not result.value_in_evidence:
        return StatusReason.VALUE_NOT_IN_EVIDENCE
    return None


def _header_lines(page_text: str) -> list[str]:
    """The page's lines above its first figure line: titles and column headers."""
    lines = lines_of(page_text)
    stop = next(
        (i for i, line in enumerate(lines) if any(is_figure_word(w) for w in line.split())),
        len(lines),
    )
    return [normalise_for_match(line) for line in lines[:stop]]


def _header_windows(page_text: str) -> list[str]:
    """Each header line and each pair of consecutive header lines (a wrapped date, v0.4.20)."""
    lines = _header_lines(page_text)
    return [*lines, *(f"{a} {b}" for a, b in zip(lines, lines[1:]))]


def _period_reason(
    proposal: ProposedAttribute,
    pages: Mapping[int, str],
    known_current: date | None,
) -> tuple[StatusReason | None, PeriodEvidence | None]:
    reason = _presence_reason(proposal, pages)
    if reason is not None:
        return reason, None
    page_text = pages[proposal.page_number]
    raw = normalise_for_match(proposal.raw_text)
    if not any(raw in window for window in _header_windows(page_text)):
        return StatusReason.PERIOD_MISMATCH, None
    found = resolve_anchor_texts([proposal.raw_text], page_text, known_current)[proposal.raw_text]
    if found.evidence is None or found.evidence.period_end.isoformat() != proposal.normalised_value.strip():
        return StatusReason.PERIOD_MISMATCH, None
    return None, found.evidence


def _basis_reason(
    proposal: ProposedAttribute, pages: Mapping[int, str], locator: LocatorSettings | None
) -> StatusReason | None:
    reason = _presence_reason(proposal, pages)
    if reason is not None:
        return reason
    value = proposal.normalised_value.strip()
    if value not in _BASES:  # "unknown", or anything else, is not a basis
        return StatusReason.BASIS_UNKNOWN
    raw = fold_phrase(proposal.raw_text)
    for block, basis in title_block_bases(pages[proposal.page_number], locator):
        if basis == value and raw in " ".join(block.split()):
            return None
    return StatusReason.BASIS_UNKNOWN


def _currency_reason(
    proposal: ProposedAttribute, pages: Mapping[int, str], declarations: DeclarationSettings | None
) -> StatusReason | None:
    reason = _presence_reason(proposal, pages)
    if reason is not None:
        return reason
    code = proposal.normalised_value.strip()
    if not _ISO_CURRENCY.fullmatch(code):
        return StatusReason.CURRENCY_NOT_VERIFIED
    # A sign, code or name for this code in the quote or on the cited page (FR-005.8, v0.4.30): the page is what a field's own
    # currency check already reads, and the model's choice of which line to quote is not evidence of where the page declares it.
    in_quote = check_currency(code, proposal.evidence_quote, settings=declarations).ok
    on_page = check_currency(code, pages.get(proposal.page_number, ""), settings=declarations).ok
    return None if in_quote or on_page else StatusReason.CURRENCY_NOT_VERIFIED


def _scale_reason(
    proposal: ProposedAttribute, pages: Mapping[int, str], declarations: DeclarationSettings | None
) -> StatusReason | None:
    reason = _presence_reason(proposal, pages)
    if reason is not None:
        return reason
    try:
        claimed = Scale(proposal.normalised_value.strip())
    except ValueError:
        return StatusReason.SCALE_NOT_VERIFIED
    return check_scale(claimed, proposal.evidence_quote, settings=declarations).reason


# Reason for disagreeing proposals of one attribute.
_CONFLICT_REASON = {
    Name.PERIOD_END: StatusReason.PERIOD_MISMATCH,
    Name.STATEMENT_BASIS: StatusReason.BASIS_UNKNOWN,
    Name.REPORTING_CURRENCY: StatusReason.CURRENCY_NOT_VERIFIED,
    Name.SCALE: StatusReason.SCALE_AMBIGUOUS,
}


def _choose(
    name: Name,
    role: PeriodRole | None,
    proposals: Sequence[ProposedAttribute],
    outcomes: Sequence[tuple[StatusReason | None, PeriodEvidence | None]],
) -> tuple[DocumentAttribute, PeriodEvidence | None]:
    """One record for all proposals of an attribute (and role).

    The first verified proposal wins if every verified one agrees. Verified proposals
    that disagree are not guessed between. If none is verified, the first one's
    failure is reported.
    """
    if not proposals:
        return _not_found(name, role), None
    verified = [(p, e) for p, (reason, e) in zip(proposals, outcomes) if reason is None]
    if not verified:
        return _record(proposals[0], Status.REQUIRES_REVIEW, outcomes[0][0]), None
    values = {p.normalised_value.strip() for p, _ in verified}
    if len(values) > 1 and name is not Name.ENTITY_NAME:
        return _record(verified[0][0], Status.REQUIRES_REVIEW, _CONFLICT_REASON[name]), None
    proposal, evidence = verified[0]
    return _record(proposal, Status.EXTRACTED, None), evidence


def _derived_comparative(
    pages: Mapping[int, str], current: date
) -> tuple[DocumentAttribute, PeriodEvidence] | None:
    """The comparative period end the code derives (FR-005.9, v0.4.22), with its evidence.

    The first candidate page, in page order, whose title or column-header block holds a
    year-only or financial-year token for exactly the year before ``current`` gives the
    same month and day in that year. The token is the raw text and its header line the
    quote. A current period ending on 28 or 29 February derives nothing (H.1.1 counts the
    two as the same day, so the earlier period end cannot be derived).
    """
    if current.month == 2 and current.day in (28, 29):
        return None
    year = current.year - 1
    for number in sorted(pages):
        for token, line in header_year_tokens(pages[number]):
            if parse_year_token(token) == year:
                derived = date(year, current.month, current.day)
                attribute = DocumentAttribute(
                    attribute=Name.PERIOD_END,
                    period_role=PeriodRole.COMPARATIVE,
                    raw_text=token,
                    normalised_value=derived.isoformat(),
                    page_number=number,
                    evidence_quote=line,
                    status=Status.EXTRACTED,
                )
                return attribute, PeriodEvidence(token, derived, Method.DERIVED_COMPARATIVE, derived_from=current)
    return None


_REPAIRABLE = (Name.REPORTING_CURRENCY, Name.SCALE)


def _declared_conflict(name: Name, pages: Mapping[int, str], settings: DeclarationSettings | None) -> bool:
    """Whether the candidate pages declare more than one currency (or more than one scale) between them (PRD v0.4.36)."""
    if name is Name.REPORTING_CURRENCY:
        return len(frozenset().union(*(find_currencies(text, settings) for text in pages.values()))) > 1
    return len(frozenset().union(*(find_scales(text, settings) for text in pages.values()))) > 1


def _repaired(
    proposal: ProposedAttribute, pages: Mapping[int, str], settings: DeclarationSettings | None
) -> tuple[ProposedAttribute, PageRepair | None, bool]:
    """The proposal with the page its quote is on, if the model cited another page (PRD v0.4.36).

    Only for the currency and scale declarations. If the quote is on the cited page, or on no candidate page, nothing changes. If
    the quote is on other candidate pages the lowest-numbered one is used, unless the candidate pages declare conflicting currencies
    (or scales): then nothing is repaired and the third value is ``True``.
    """
    if proposal.attribute not in _REPAIRABLE:
        return proposal, None, False
    quote = normalise_for_match(proposal.evidence_quote)
    holding = sorted(number for number, text in pages.items() if quote and quote in normalise_for_match(text))
    if not holding or proposal.page_number in holding:
        return proposal, None, False
    if _declared_conflict(proposal.attribute, pages, settings):
        return proposal, None, True
    used = holding[0]
    return proposal.model_copy(update={"page_number": used}), PageRepair(proposal.attribute.value, proposal.page_number, used), False


def verify_attributes(
    proposed: Sequence[ProposedAttribute],
    pages: Mapping[int, str],
    locator_settings: LocatorSettings | None = None,
    declaration_settings: DeclarationSettings | None = None,
    assertion: BasisAssertion | None = None,
    configured_basis: StatementBasis | None = None,
) -> VerifiedAttributes:
    """Verify the proposed document-level attributes against the candidate pages.

    ``pages`` maps the candidate page numbers to their text. ``assertion`` is the analyst's assertion of the
    basis for a ``--pages`` run (H.4.6, v0.4.24): if it was applied to a page and asserts ``configured_basis``,
    a ``statement_basis`` that is not verified from a title block is ``extracted`` by the assertion instead
    (no raw text, page or quote; what the model proposed is neither needed nor used). A ``statement_basis``
    verified from a title block is unchanged and has ``basis_evidence = title``.
    """

    repairs: list[PageRepair] = []
    blocked: set[int] = set()  # proposals whose declaration conflicts across the candidate pages: not repaired, and reviewed
    repaired_proposals = []
    for proposal in proposed:
        fixed, repair, conflict = _repaired(proposal, pages, declaration_settings)
        repaired_proposals.append(fixed)
        if repair is not None and repair not in repairs:
            repairs.append(repair)
        if conflict:
            blocked.add(id(fixed))
    proposed = repaired_proposals

    def group(name: Name, role: PeriodRole | None = None) -> list[ProposedAttribute]:
        # Only a period-end has a role. Strict mode makes the role nullable for every
        # attribute, and a model may fill it in for the others (seen on the first live run:
        # entity_name with "current"); that is meaningless, not a reason to drop the attribute.
        if name is not Name.PERIOD_END:
            return [p for p in proposed if p.attribute is name]
        return [p for p in proposed if p.attribute is name and p.period_role == role]

    def simple(name: Name, reason_of) -> DocumentAttribute:
        proposals = group(name)
        return _choose(name, None, proposals, [(reason_of(p), None) for p in proposals])[0]

    entity = simple(Name.ENTITY_NAME, lambda p: _presence_reason(p, pages))
    basis = simple(Name.STATEMENT_BASIS, lambda p: _basis_reason(p, pages, locator_settings))
    if basis.status is Status.EXTRACTED:
        basis = basis.model_copy(update={"basis_evidence": BasisEvidence.TITLE})
    elif assertion is not None and assertion.applied_pages and configured_basis is not None and assertion.basis is configured_basis:
        basis = DocumentAttribute(
            attribute=Name.STATEMENT_BASIS,
            normalised_value=assertion.basis.value,
            status=Status.EXTRACTED,
            basis_evidence=BasisEvidence.ANALYST_ASSERTION,
        )
    currency = simple(
        Name.REPORTING_CURRENCY,
        lambda p: StatusReason.CURRENCY_NOT_VERIFIED if id(p) in blocked else _currency_reason(p, pages, declaration_settings),
    )
    scale = simple(
        Name.SCALE, lambda p: StatusReason.SCALE_AMBIGUOUS if id(p) in blocked else _scale_reason(p, pages, declaration_settings)
    )

    # Periods: the current one first, so a comparative year can be derived from it.
    current_props = group(Name.PERIOD_END, PeriodRole.CURRENT)
    current, current_evidence = _choose(
        Name.PERIOD_END,
        PeriodRole.CURRENT,
        current_props,
        [_period_reason(p, pages, None) for p in current_props],
    )
    known = date.fromisoformat(current.normalised_value) if current.status is Status.EXTRACTED else None
    comparative_props = group(Name.PERIOD_END, PeriodRole.COMPARATIVE)
    comparative, comparative_evidence = _choose(
        Name.PERIOD_END,
        PeriodRole.COMPARATIVE,
        comparative_props,
        [_period_reason(p, pages, known) for p in comparative_props],
    )

    # v0.4.22: the code derives the comparative from a year heading one year before the current
    # period. A proposed comparative is kept only if it equals the derived date; a failed or
    # missing one is replaced by it; a validated one that differs is a disagreement.
    derived = (
        _derived_comparative(pages, date.fromisoformat(current.normalised_value))
        if current.status is Status.EXTRACTED
        else None
    )
    if derived is not None:
        derived_attribute, derived_evidence = derived
        if comparative.status is not Status.EXTRACTED:
            comparative, comparative_evidence = derived_attribute, derived_evidence
        elif comparative.normalised_value != derived_attribute.normalised_value:
            comparative = comparative.model_copy(
                update={"status": Status.REQUIRES_REVIEW, "status_reason": StatusReason.PERIOD_MISMATCH}
            )

    if current.status is Status.EXTRACTED and comparative.status is Status.EXTRACTED:
        current_date = date.fromisoformat(current.normalised_value)
        comparative_date = date.fromisoformat(comparative.normalised_value)
        if comparative_date >= current_date:  # the later validated date is the current period
            current = current.model_copy(
                update={"status": Status.REQUIRES_REVIEW, "status_reason": StatusReason.PERIOD_MISMATCH}
            )
            comparative = comparative.model_copy(
                update={"status": Status.REQUIRES_REVIEW, "status_reason": StatusReason.PERIOD_MISMATCH}
            )
        elif not periods_are_consecutive(current_date, comparative_date):
            comparative = comparative.model_copy(
                update={"status": Status.REQUIRES_REVIEW, "status_reason": StatusReason.PERIOD_MISMATCH}
            )

    evidence: dict[PeriodRole, PeriodEvidence] = {}
    if current.status is Status.EXTRACTED and current_evidence is not None:
        evidence[PeriodRole.CURRENT] = current_evidence
    if comparative.status is Status.EXTRACTED and comparative_evidence is not None:
        evidence[PeriodRole.COMPARATIVE] = comparative_evidence
    return VerifiedAttributes(entity, current, comparative, basis, currency, scale, evidence, tuple(repairs))


def blocking_reasons(attributes: VerifiedAttributes, period_role: PeriodRole) -> tuple[StatusReason, ...]:
    """Every reason a field of ``period_role`` cannot be ``extracted`` (H.1.2), in order.

    A field depends on its period-end, the statement basis, the reporting currency and
    the scale. Each reason is the attribute's own: an unvalidated period is
    ``period_mismatch`` (FR-005.9), then ``basis_unknown``, ``currency_not_verified``,
    and ``scale_not_verified`` or ``scale_ambiguous``. The entity name blocks nothing.
    """
    period = (
        attributes.current_period_end
        if period_role is PeriodRole.CURRENT
        else attributes.comparative_period_end
    )
    reasons: list[StatusReason] = []
    if period.status is not Status.EXTRACTED:
        reasons.append(StatusReason.PERIOD_MISMATCH)
    if attributes.statement_basis.status is not Status.EXTRACTED:
        reasons.append(StatusReason.BASIS_UNKNOWN)
    if attributes.reporting_currency.status is not Status.EXTRACTED:
        reasons.append(StatusReason.CURRENCY_NOT_VERIFIED)
    if attributes.scale.status is not Status.EXTRACTED:
        ambiguous = attributes.scale.status_reason is StatusReason.SCALE_AMBIGUOUS
        reasons.append(StatusReason.SCALE_AMBIGUOUS if ambiguous else StatusReason.SCALE_NOT_VERIFIED)
    return tuple(reasons)


def blocking_reason(attributes: VerifiedAttributes, period_role: PeriodRole) -> StatusReason | None:
    """The first of ``blocking_reasons``, or ``None``."""
    reasons = blocking_reasons(attributes, period_role)
    return reasons[0] if reasons else None
