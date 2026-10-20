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
- ``reporting_currency`` and ``scale``: the quote itself supports them (FR-005.8).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from credit_intel.config import DeclarationSettings, LocatorSettings
from credit_intel.extraction.declarations import check_currency, check_scale
from credit_intel.extraction.periods import PeriodEvidence, periods_are_consecutive, resolve_anchor_texts
from credit_intel.extraction.presence import check_presence, normalise_for_match
from credit_intel.ingestion.locator import fold_phrase, is_figure_word, lines_of, title_block_bases
from credit_intel.models import (
    DocumentAttribute,
    DocumentAttributeName,
    PeriodRole,
    ProposedAttribute,
    Scale,
    Status,
    StatusReason,
)

_ISO_CURRENCY = re.compile(r"[A-Z]{3}")
_BASES = ("consolidated", "standalone")

Name = DocumentAttributeName


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
    if not _ISO_CURRENCY.fullmatch(code) or not check_currency(
        code, proposal.evidence_quote, settings=declarations
    ).ok:
        return StatusReason.CURRENCY_NOT_VERIFIED
    return None


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


def verify_attributes(
    proposed: Sequence[ProposedAttribute],
    pages: Mapping[int, str],
    locator_settings: LocatorSettings | None = None,
    declaration_settings: DeclarationSettings | None = None,
) -> VerifiedAttributes:
    """Verify the proposed document-level attributes against the candidate pages.

    ``pages`` maps the candidate page numbers to their text.
    """

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
    currency = simple(Name.REPORTING_CURRENCY, lambda p: _currency_reason(p, pages, declaration_settings))
    scale = simple(Name.SCALE, lambda p: _scale_reason(p, pages, declaration_settings))

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
    return VerifiedAttributes(entity, current, comparative, basis, currency, scale, evidence)


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
