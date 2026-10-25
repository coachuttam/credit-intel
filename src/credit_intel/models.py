"""Financial data schema (PRD Section H) and the LLM response schema (FR-003, FR-004).

Pydantic models are used here because this data is validated from outside the
program: LLM output (FR-004) and, later, evaluation labels (L.1). Ingestion keeps
its own plain dataclasses in ``ingestion/models.py``.

H.1 says the final attribute names are set during Phase 2. These are the Phase 2
names. Where the PRD is silent the choice is recorded in the docstring.
"""

import re
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

# --- Enumerations (H.1, H.2, H.3) ---------------------------------------------


class FieldName(StrEnum):
    """The Release 1 field set (H.3), plus the one derived field, ``ebit``."""

    REVENUE = "revenue"
    NET_PROFIT = "net_profit"
    OPERATING_PROFIT = "operating_profit"
    PROFIT_BEFORE_TAX = "profit_before_tax"
    INTEREST_EXPENSE = "interest_expense"
    CURRENT_ASSETS = "current_assets"
    CURRENT_LIABILITIES = "current_liabilities"
    TOTAL_BORROWINGS = "total_borrowings"
    BORROWINGS_NON_CURRENT = "borrowings_non_current"
    BORROWINGS_CURRENT = "borrowings_current"
    CURRENT_MATURITIES_LONG_TERM_BORROWINGS = "current_maturities_long_term_borrowings"
    TOTAL_EQUITY = "total_equity"
    EBIT = "ebit"  # derived only: "never extracted by the LLM" (H.3, H.5)


# The names the LLM may return. ``ebit`` is computed in Python and never extracted.
# Its members compare equal to the same-named ``FieldName`` members (both are ``str``).
ExtractableFieldName = StrEnum(
    "ExtractableFieldName",
    {member.name: member.value for member in FieldName if member is not FieldName.EBIT},
)


class Origin(StrEnum):
    SOURCE = "source"
    DERIVED = "derived"


class PeriodRole(StrEnum):
    CURRENT = "current"
    COMPARATIVE = "comparative"


class StatementBasis(StrEnum):
    CONSOLIDATED = "consolidated"
    STANDALONE = "standalone"
    UNKNOWN = "unknown"


class Status(StrEnum):
    """H.2. No further statuses are added."""

    EXTRACTED = "extracted"
    NOT_FOUND = "not_found"
    CONFLICTING = "conflicting"
    REQUIRES_REVIEW = "requires_review"


class StatusReason(StrEnum):
    """The status reasons listed in H.1."""

    EVIDENCE_NOT_VERIFIED = "evidence_not_verified"
    VALUE_NOT_IN_EVIDENCE = "value_not_in_evidence"
    SIGN_MISMATCH = "sign_mismatch"
    PERIOD_NOT_VERIFIED = "period_not_verified"
    SCALE_NOT_VERIFIED = "scale_not_verified"
    SCALE_AMBIGUOUS = "scale_ambiguous"
    CURRENCY_NOT_VERIFIED = "currency_not_verified"
    LABEL_NOT_RECOGNISED = "label_not_recognised"
    PERIOD_MISMATCH = "period_mismatch"
    BASIS_UNKNOWN = "basis_unknown"
    IMPLAUSIBLE_VALUE = "implausible_value"
    MISSING_INPUT = "missing_input"
    CURRENCY_MISMATCH = "currency_mismatch"
    BORROWINGS_CLASSIFICATION_UNRESOLVED = "borrowings_classification_unresolved"


class ValueInterpretation(StrEnum):
    NUMBER = "number"
    REPORTED_NIL = "reported_nil"  # the nil convention (FR-004.3, D-08)


class Scale(StrEnum):
    UNITS = "units"
    THOUSANDS = "thousands"
    LAKH = "lakh"
    MILLIONS = "millions"
    CRORE = "crore"
    BILLIONS = "billions"


class DocumentAttributeName(StrEnum):
    """H.1.2. ``period_end`` is recorded once per role (current, comparative)."""

    ENTITY_NAME = "entity_name"
    PERIOD_END = "period_end"
    STATEMENT_BASIS = "statement_basis"
    REPORTING_CURRENCY = "reporting_currency"
    SCALE = "scale"


# --- Field IDs (H.1.1) --------------------------------------------------------


def make_field_id(field_name: FieldName, period_end: date, basis: StatementBasis) -> str:
    """``<field_name>.<period_end>.<statement_basis>``, e.g. ``revenue.2025-03-31.consolidated``."""
    return f"{FieldName(field_name).value}.{period_end.isoformat()}.{StatementBasis(basis).value}"


# --- Shared building blocks ---------------------------------------------------

_CURRENCY = re.compile(r"[A-Z]{3}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class _Model(BaseModel):
    """Unknown attributes are rejected (FR-004.2) and records are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _reject_float(value: object) -> object:
    # FR-004.4: values are Decimal, never binary floats.
    if isinstance(value, float):
        raise ValueError("a binary float is not accepted; use a decimal string or integer")
    return value


class SourceDocument(_Model):
    file_name: StrictStr = Field(min_length=1)
    sha256: StrictStr

    @field_validator("sha256")
    @classmethod
    def _sha256_form(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class Evidence(_Model):
    """One occurrence of a value on a page (used for corroboration and candidates)."""

    page_number: StrictInt = Field(ge=1)  # 1-based physical page
    page_label: StrictStr | None = None
    evidence_quote: StrictStr = Field(min_length=1)
    line_item_label: StrictStr = Field(min_length=1)
    raw_value: StrictStr = Field(min_length=1)


class Candidate(Evidence):
    """A candidate value of a ``conflicting`` field, with its own evidence."""

    value: Decimal

    @field_validator("value", mode="before")
    @classmethod
    def _no_float(cls, value: object) -> object:
        return _reject_float(value)


class Validation(_Model):
    """Results of the deterministic checks (FR-005.1 to .10).

    ``None`` means the check was not evaluated, for example because an earlier
    check it depends on failed. ``details`` holds supporting records such as the
    column, the anchor quote and a derivation note.
    """

    evidence_verified: bool | None = None
    value_in_evidence: bool | None = None
    label_verified: bool | None = None
    period_end_verified: bool | None = None
    period_column_verified: bool | None = None
    sign_verified: bool | None = None
    scale_verified: bool | None = None
    currency_verified: bool | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)

    def all_passed(self) -> bool:
        return all(
            getattr(self, name) is True
            for name in (
                "evidence_verified",
                "value_in_evidence",
                "label_verified",
                "period_end_verified",
                "period_column_verified",
                "sign_verified",
                "scale_verified",
                "currency_verified",
            )
        )


class Derivation(_Model):
    method_id: StrictStr = Field(min_length=1)
    formula: StrictStr = Field(min_length=1)
    input_field_ids: tuple[StrictStr, ...] = Field(min_length=1)
    component_classification: StrictStr | None = None


# --- The extracted field record (H.1) -----------------------------------------


class BasisEvidence(StrEnum):
    """How the basis of a field or of the ``statement_basis`` attribute was established (H.1, H.4.6, v0.4.24)."""

    TITLE = "title"  # a title block of its own page, or of the first page of its statement run
    ANALYST_ASSERTION = "analyst_assertion"  # asserted by the analyst for a ``--pages`` run


class ExtractedField(_Model):
    """One field for one period and basis (H.1).

    Conditional requirements follow H.1's "Required" column:
    - source values carry the evidence attributes (a ``not_found`` one only needs its
      source document); derived values carry a derivation and none of them;
    - ``value`` and ``currency`` are required when ``status`` is ``extracted``,
      and ``value`` is null otherwise;
    - a ``status_reason`` is null when extracted and required for
      ``requires_review``. H.1 asks for a reason whenever the status is not
      ``extracted``, but lists no reason for ``not_found`` or ``conflicting``,
      so those two may omit it (recorded as an open point);
    - a source field is ``extracted`` only if every deterministic check passed
      (FR-005.3).
    """

    field_id: StrictStr
    field_name: FieldName
    origin: Origin
    period_end: date
    period_length_months: Literal[12]  # Release 1 supports 12-month periods only
    period_role: PeriodRole
    statement_basis: StatementBasis
    basis_evidence: BasisEvidence = BasisEvidence.TITLE
    status: Status
    status_reason: StatusReason | None = None
    value: Decimal | None = None
    currency: StrictStr | None = None
    raw_value: StrictStr | None = Field(default=None, min_length=1)
    value_interpretation: ValueInterpretation | None = None
    scale: Scale | None = None
    source_document: SourceDocument | None = None
    page_number: StrictInt | None = Field(default=None, ge=1)
    page_label: StrictStr | None = None
    evidence_quote: StrictStr | None = Field(default=None, min_length=1)
    line_item_label: StrictStr | None = Field(default=None, min_length=1)
    validation: Validation | None = None
    derivation: Derivation | None = None
    candidates: tuple[Candidate, ...] = ()
    corroborating_evidence: tuple[Evidence, ...] = ()

    @field_validator("value", mode="before")
    @classmethod
    def _no_float(cls, value: object) -> object:
        return _reject_float(value)

    @field_validator("currency")
    @classmethod
    def _currency_form(cls, value: str | None) -> str | None:
        if value is not None and not _CURRENCY.fullmatch(value):
            raise ValueError("currency must be an ISO 4217 code of three capital letters")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "ExtractedField":
        expected = make_field_id(self.field_name, self.period_end, self.statement_basis)
        if self.field_id != expected:
            raise ValueError(f"field_id must be {expected}")

        source_attributes = {
            "raw_value": self.raw_value,
            "value_interpretation": self.value_interpretation,
            "scale": self.scale,
            "source_document": self.source_document,
            "page_number": self.page_number,
            "evidence_quote": self.evidence_quote,
            "line_item_label": self.line_item_label,
            "validation": self.validation,
        }
        if self.origin is Origin.SOURCE:
            # A field that was not found has no evidence to carry, but still says which
            # document was searched.
            required = (
                {"source_document": self.source_document}
                if self.status is Status.NOT_FOUND
                else source_attributes
            )
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ValueError(f"a source field requires {', '.join(missing)}")
            if self.derivation is not None:
                raise ValueError("a source field has no derivation")
        else:
            present = [name for name, value in source_attributes.items() if value is not None]
            if present:
                raise ValueError(f"a derived field has no {', '.join(present)}")
            if self.derivation is None:
                raise ValueError("a derived field requires a derivation")

        if self.status is Status.EXTRACTED:
            if self.status_reason is not None:
                raise ValueError("an extracted field has no status_reason")
            if self.value is None or self.currency is None:
                raise ValueError("an extracted field requires value and currency")
            if self.origin is Origin.SOURCE:
                assert self.validation is not None  # guaranteed above
                if not self.validation.all_passed():
                    raise ValueError("a source field is extracted only if every check passed")
                if (
                    self.value_interpretation is ValueInterpretation.REPORTED_NIL
                    and self.value != 0
                ):
                    raise ValueError("a reported nil has the value 0")
        else:
            if self.value is not None:
                raise ValueError("value is null unless the status is extracted")
            if self.status is Status.REQUIRES_REVIEW and self.status_reason is None:
                raise ValueError("requires_review needs a status_reason")

        if self.status is Status.CONFLICTING and len(self.candidates) < 2:
            raise ValueError("a conflicting field lists at least two candidates")
        return self


# --- Document-level attributes (H.1.2) ----------------------------------------


class DocumentAttribute(_Model):
    """A document-level attribute with its evidence."""

    attribute: DocumentAttributeName
    period_role: PeriodRole | None = None  # only for ``period_end``
    raw_text: StrictStr | None = None
    normalised_value: StrictStr | None = None
    page_number: StrictInt | None = Field(default=None, ge=1)
    evidence_quote: StrictStr | None = Field(default=None, min_length=1)
    status: Literal[Status.EXTRACTED, Status.NOT_FOUND, Status.REQUIRES_REVIEW]
    status_reason: StatusReason | None = None
    # Only for ``statement_basis`` when it is extracted: ``title`` (verified from a title block) or
    # ``analyst_assertion`` (H.4.6, v0.4.24), which has no raw text, page or quote.
    basis_evidence: BasisEvidence | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "DocumentAttribute":
        if self.basis_evidence is not None and (
            self.attribute is not DocumentAttributeName.STATEMENT_BASIS or self.status is not Status.EXTRACTED
        ):
            raise ValueError("only an extracted statement_basis has a basis_evidence")
        if self.basis_evidence is BasisEvidence.ANALYST_ASSERTION:
            if self.normalised_value is None:
                raise ValueError("an asserted basis needs its value")
            if any(getattr(self, name) is not None for name in ("raw_text", "page_number", "evidence_quote")):
                raise ValueError("an asserted basis has no raw text, page or quote")
            return self
        is_period = self.attribute is DocumentAttributeName.PERIOD_END
        if is_period and self.period_role is None:
            raise ValueError("period_end needs a period_role")
        if not is_period and self.period_role is not None:
            raise ValueError("only period_end has a period_role")
        if self.status is Status.EXTRACTED:
            if self.status_reason is not None:
                raise ValueError("an extracted attribute has no status_reason")
            missing = [
                name
                for name in ("raw_text", "normalised_value", "page_number", "evidence_quote")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"an extracted attribute requires {', '.join(missing)}")
        elif self.status is Status.REQUIRES_REVIEW and self.status_reason is None:
            raise ValueError("requires_review needs a status_reason")
        return self


# --- What the LLM returns (FR-003, FR-004) --------------------------------------


class ProposedField(_Model):
    """One value proposed by the model. Every check on it is made in Python.

    The model supplies the evidence and its own reading of scale and currency; the
    period end and statement basis come from the document-level attributes, and
    the status is decided only by the deterministic checks (FR-005). Strict string
    types make a JSON number for ``raw_value`` a validation error.
    """

    field_name: ExtractableFieldName  # type: ignore[valid-type]
    period_role: PeriodRole
    raw_value: StrictStr = Field(min_length=1)
    scale: Scale
    currency: StrictStr
    page_number: StrictInt = Field(ge=1)
    evidence_quote: StrictStr = Field(min_length=1)
    line_item_label: StrictStr = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def _currency_form(cls, value: str) -> str:
        if not _CURRENCY.fullmatch(value):
            raise ValueError("currency must be an ISO 4217 code of three capital letters")
        return value


class ProposedAttribute(_Model):
    """A document-level attribute proposed by the model (H.1.2)."""

    attribute: DocumentAttributeName
    period_role: PeriodRole | None = None
    raw_text: StrictStr = Field(min_length=1)
    normalised_value: StrictStr = Field(min_length=1)
    page_number: StrictInt = Field(ge=1)
    evidence_quote: StrictStr = Field(min_length=1)


class ExtractionResponse(_Model):
    """The structured output requested from the model (FR-003.4, FR-004).

    Unknown field names and unknown attributes are rejected (FR-004.2). A field the
    model does not return is treated as ``not_found`` by the caller, not here.
    Several entries for one field and period are allowed: the same figure may appear
    on more than one page (H.4.1).
    """

    attributes: tuple[ProposedAttribute, ...]
    fields: tuple[ProposedField, ...]
