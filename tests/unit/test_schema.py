"""Financial data schema and LLM response schema (PRD H.1 to H.3, FR-003, FR-004; B-202)."""

import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from credit_intel.models import (
    Candidate,
    DocumentAttribute,
    DocumentAttributeName,
    ExtractableFieldName,
    ExtractedField,
    ExtractionResponse,
    FieldName,
    Origin,
    PeriodRole,
    ProposedAttribute,
    ProposedField,
    Scale,
    StatementBasis,
    Status,
    StatusReason,
    ValueInterpretation,
    make_field_id,
)

SHA = "a" * 64
ALL_PASSED = {
    "evidence_verified": True,
    "value_in_evidence": True,
    "label_verified": True,
    "period_end_verified": True,
    "period_column_verified": True,
    "sign_verified": True,
    "scale_verified": True,
    "currency_verified": True,
}


def source_field(**overrides) -> dict:
    base = {
        "field_id": "revenue.2025-03-31.consolidated",
        "field_name": "revenue",
        "origin": "source",
        "period_end": "2025-03-31",
        "period_length_months": 12,
        "period_role": "current",
        "statement_basis": "consolidated",
        "status": "extracted",
        "value": "14823000000",
        "currency": "INR",
        "raw_value": "1,482.30",
        "value_interpretation": "number",
        "scale": "crore",
        "source_document": {"file_name": "report.pdf", "sha256": SHA},
        "page_number": 114,
        "evidence_quote": "Revenue from operations 14 1,482.30 1,356.75",
        "line_item_label": "Revenue from operations",
        "validation": ALL_PASSED,
    }
    return base | overrides


def derived_field(**overrides) -> dict:
    base = {
        "field_id": "ebit.2025-03-31.consolidated",
        "field_name": "ebit",
        "origin": "derived",
        "period_end": "2025-03-31",
        "period_length_months": 12,
        "period_role": "current",
        "statement_basis": "consolidated",
        "status": "extracted",
        "value": "100",
        "currency": "INR",
        "derivation": {
            "method_id": "EBIT-1",
            "formula": "profit_before_tax + interest_expense",
            "input_field_ids": ["profit_before_tax.2025-03-31.consolidated"],
        },
    }
    return base | overrides


def review(**overrides) -> dict:
    """A source field that failed a check."""
    base = source_field(status="requires_review", status_reason="sign_mismatch", value=None)
    return base | overrides


def rejected(**data) -> str:
    with pytest.raises(ValidationError) as excinfo:
        ExtractedField.model_validate(data)
    return str(excinfo.value)


# --- enumerations: exactly the PRD's values --------------------------------------


def test_field_names_are_the_h3_set_plus_derived_ebit():
    assert [m.value for m in FieldName] == [
        "revenue", "net_profit", "operating_profit", "profit_before_tax", "interest_expense",
        "current_assets", "current_liabilities", "total_borrowings", "borrowings_non_current",
        "borrowings_current", "current_maturities_long_term_borrowings", "total_equity", "ebit",
    ]  # fmt: skip


def test_the_model_may_never_return_ebit():
    assert "ebit" not in {m.value for m in ExtractableFieldName}
    assert {m.value for m in ExtractableFieldName} == {m.value for m in FieldName} - {"ebit"}


def test_statuses_are_exactly_the_four_in_h2():
    assert {m.value for m in Status} == {"extracted", "not_found", "conflicting", "requires_review"}


def test_status_reasons_are_the_h1_list():
    assert {m.value for m in StatusReason} == {
        "evidence_not_verified", "value_not_in_evidence", "sign_mismatch", "period_not_verified",
        "scale_not_verified", "scale_ambiguous", "currency_not_verified", "label_not_recognised",
        "period_mismatch", "basis_unknown", "implausible_value", "missing_input",
        "currency_mismatch", "borrowings_classification_unresolved",
    }  # fmt: skip


def test_scales_bases_and_roles():
    assert {m.value for m in Scale} == {"units", "thousands", "lakh", "millions", "crore", "billions"}
    assert {m.value for m in StatementBasis} == {"consolidated", "standalone", "unknown"}
    assert {m.value for m in PeriodRole} == {"current", "comparative"}
    assert {m.value for m in Origin} == {"source", "derived"}
    assert {m.value for m in ValueInterpretation} == {"number", "reported_nil"}


# --- field IDs (H.1.1) ------------------------------------------------------------


def test_field_id_form():
    assert (
        make_field_id(FieldName.REVENUE, date(2025, 3, 31), StatementBasis.CONSOLIDATED)
        == "revenue.2025-03-31.consolidated"
    )
    assert (
        make_field_id(FieldName.TOTAL_EQUITY, date(2024, 3, 31), StatementBasis.UNKNOWN)
        == "total_equity.2024-03-31.unknown"
    )


@pytest.mark.parametrize(
    "field_id",
    [
        "revenue.2025-03-31.standalone",  # wrong basis
        "revenue.2024-03-31.consolidated",  # wrong period
        "net_profit.2025-03-31.consolidated",  # wrong name
        "revenue.FY2025.consolidated",  # labels are never identifiers (H.1.1)
        "",
    ],
)
def test_a_field_id_that_does_not_match_its_parts_is_rejected(field_id):
    assert "field_id must be revenue.2025-03-31.consolidated" in rejected(**source_field(field_id=field_id))


# --- valid records -----------------------------------------------------------------


def test_a_verified_source_field_is_valid_and_keeps_decimal_precision():
    record = ExtractedField.model_validate(source_field(value="14823000000.50"))

    assert record.status is Status.EXTRACTED
    assert record.value == Decimal("14823000000.50")
    assert isinstance(record.value, Decimal)


def test_a_derived_field_is_valid():
    record = ExtractedField.model_validate(derived_field())

    assert record.origin is Origin.DERIVED
    assert record.derivation is not None and record.raw_value is None


def test_a_reported_nil_with_value_zero_is_valid():
    record = ExtractedField.model_validate(
        source_field(raw_value="–", value_interpretation="reported_nil", value="0")
    )

    assert record.value == 0


def test_the_record_is_json_serialisable_and_round_trips():
    record = ExtractedField.model_validate(source_field())
    again = ExtractedField.model_validate_json(record.model_dump_json())

    assert again == record
    assert json.loads(record.model_dump_json())["value"] == "14823000000"


def test_records_are_immutable():
    record = ExtractedField.model_validate(source_field())
    with pytest.raises(ValidationError):
        record.value = Decimal(1)


# --- statuses and reasons ------------------------------------------------------------


def test_requires_review_needs_a_reason_and_no_value():
    assert ExtractedField.model_validate(review()).status is Status.REQUIRES_REVIEW
    assert "requires_review needs a status_reason" in rejected(**review(status_reason=None))
    assert "value is null unless the status is extracted" in rejected(**review(value="5"))


def test_an_extracted_field_has_no_reason():
    assert "an extracted field has no status_reason" in rejected(**source_field(status_reason="sign_mismatch"))


def test_an_extracted_field_needs_value_and_currency():
    assert "requires value and currency" in rejected(**source_field(value=None))
    assert "requires value and currency" in rejected(**source_field(currency=None))


def test_not_found_has_no_value_and_may_omit_a_reason():
    record = ExtractedField.model_validate(review(status="not_found", status_reason=None))

    assert record.status is Status.NOT_FOUND and record.value is None


def test_conflicting_needs_two_candidates_and_no_value():
    candidate = {
        "page_number": 3, "evidence_quote": "Revenue 1,000", "line_item_label": "Revenue",
        "raw_value": "1,000", "value": "1000",
    }  # fmt: skip
    other = candidate | {"page_number": 9, "value": "1100", "raw_value": "1,100"}
    ok = review(status="conflicting", status_reason=None, candidates=[candidate, other])

    record = ExtractedField.model_validate(ok)
    assert [c.value for c in record.candidates] == [Decimal("1000"), Decimal("1100")]
    assert "at least two candidates" in rejected(**ok | {"candidates": [candidate]})
    assert "at least two candidates" in rejected(**ok | {"candidates": []})


@pytest.mark.parametrize("check", list(ALL_PASSED))
def test_a_source_field_is_not_extracted_unless_every_check_passed(check):
    for failing in (False, None):
        validation = ALL_PASSED | {check: failing}
        assert "every check passed" in rejected(**source_field(validation=validation))


def test_a_failed_check_is_fine_on_a_field_that_needs_review():
    validation = ALL_PASSED | {"sign_verified": False}

    assert ExtractedField.model_validate(review(validation=validation)).validation is not None


def test_a_reported_nil_must_have_the_value_zero():
    assert "reported nil has the value 0" in rejected(
        **source_field(raw_value="–", value_interpretation="reported_nil", value="5")
    )


# --- source and derived attributes ---------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["raw_value", "value_interpretation", "scale", "source_document", "page_number",
     "evidence_quote", "line_item_label", "validation"],
)  # fmt: skip
def test_a_source_field_requires_every_source_attribute(name):
    data = source_field()
    del data[name]

    assert f"a source field requires {name}" in rejected(**data)


def test_a_source_field_has_no_derivation():
    derivation = derived_field()["derivation"]

    assert "a source field has no derivation" in rejected(**source_field(derivation=derivation))


def test_a_derived_field_requires_a_derivation_and_no_source_attributes():
    data = derived_field()
    del data["derivation"]
    assert "a derived field requires a derivation" in rejected(**data)
    assert "a derived field has no raw_value" in rejected(**derived_field(raw_value="1"))


# --- format rules -----------------------------------------------------------------------------


@pytest.mark.parametrize("currency", ["inr", "IN", "INRR", "₹", "123", ""])
def test_currency_must_be_three_capital_letters(currency):
    assert "ISO 4217" in rejected(**source_field(currency=currency))


@pytest.mark.parametrize("sha", ["A" * 64, "a" * 63, "g" * 64, ""])
def test_the_document_sha256_form_is_checked(sha):
    assert "sha256" in rejected(**source_field(source_document={"file_name": "r.pdf", "sha256": sha}))


@pytest.mark.parametrize("page", [0, -1, 1.5, "3", True])
def test_page_numbers_are_positive_integers(page):
    with pytest.raises(ValidationError):
        ExtractedField.model_validate(source_field(page_number=page))


def test_only_twelve_month_periods_are_supported():
    with pytest.raises(ValidationError):
        ExtractedField.model_validate(source_field(period_length_months=6))


@pytest.mark.parametrize("value", [1.5, 100.0, 1e20])
def test_binary_floats_are_never_accepted_as_values(value):
    assert "binary float" in rejected(**source_field(value=value))


def test_unknown_attributes_are_rejected():
    with pytest.raises(ValidationError):
        ExtractedField.model_validate(source_field(confidence=0.9))  # no LLM confidence scores (H.1.2)


def test_unknown_status_reason_and_status_are_rejected():
    with pytest.raises(ValidationError):
        ExtractedField.model_validate(review(status_reason="because"))
    with pytest.raises(ValidationError):
        ExtractedField.model_validate(source_field(status="validated"))


def test_candidate_values_are_decimals_not_floats():
    with pytest.raises(ValidationError):
        Candidate.model_validate(
            {"page_number": 1, "evidence_quote": "q", "line_item_label": "l", "raw_value": "1", "value": 1.5}
        )


# --- document-level attributes (H.1.2) --------------------------------------------------------------


def attribute(**overrides) -> dict:
    base = {
        "attribute": "reporting_currency", "raw_text": "(₹ in crore)", "normalised_value": "INR",
        "page_number": 112, "evidence_quote": "(₹ in crore)", "status": "extracted",
    }  # fmt: skip
    return base | overrides


def test_a_document_attribute_is_valid():
    assert DocumentAttribute.model_validate(attribute()).normalised_value == "INR"


def test_period_end_attributes_need_a_role_and_others_must_not_have_one():
    period = attribute(attribute="period_end", normalised_value="2025-03-31")
    with pytest.raises(ValidationError, match="needs a period_role"):
        DocumentAttribute.model_validate(period)
    assert DocumentAttribute.model_validate(period | {"period_role": "current"}).period_role is PeriodRole.CURRENT
    with pytest.raises(ValidationError, match="only period_end has a period_role"):
        DocumentAttribute.model_validate(attribute(period_role="current"))


def test_an_extracted_attribute_needs_its_evidence():
    for name in ("raw_text", "normalised_value", "page_number", "evidence_quote"):
        with pytest.raises(ValidationError, match=f"requires .*{name}"):
            DocumentAttribute.model_validate(attribute(**{name: None}))


def test_attribute_statuses_are_limited_to_the_three_in_h12():
    with pytest.raises(ValidationError):
        DocumentAttribute.model_validate(attribute(status="conflicting"))
    absent = DocumentAttribute.model_validate(
        {"attribute": "entity_name", "status": "not_found"}
    )
    assert absent.status is Status.NOT_FOUND
    with pytest.raises(ValidationError, match="requires_review needs a status_reason"):
        DocumentAttribute.model_validate({"attribute": "scale", "status": "requires_review"})


# --- the LLM response (FR-003, FR-004) ----------------------------------------------------------------------


def proposed(**overrides) -> dict:
    base = {
        "field_name": "revenue", "period_role": "current", "raw_value": "1,482.30", "scale": "crore",
        "currency": "INR", "page_number": 114,
        "evidence_quote": "Revenue from operations 14 1,482.30 1,356.75",
        "line_item_label": "Revenue from operations",
    }  # fmt: skip
    return base | overrides


PROPOSED_ATTRIBUTE = {
    "attribute": "period_end", "period_role": "current", "raw_text": "As at 31 March 2025",
    "normalised_value": "2025-03-31", "page_number": 112, "evidence_quote": "As at 31 March 2025",
}  # fmt: skip


def response(*fields, attributes=(PROPOSED_ATTRIBUTE,)) -> str:
    return json.dumps({"attributes": list(attributes), "fields": list(fields)})


def test_a_valid_response_parses():
    parsed = ExtractionResponse.model_validate_json(response(proposed()))

    assert parsed.fields[0].field_name == "revenue"
    assert parsed.fields[0].raw_value == "1,482.30"
    assert parsed.attributes[0].normalised_value == "2025-03-31"


def test_an_empty_response_is_valid_and_missing_fields_are_left_to_the_caller():
    assert ExtractionResponse.model_validate_json(response(attributes=())).fields == ()


def test_unknown_field_names_are_rejected():
    for name in ("ebit", "ebitda", "Revenue", ""):
        with pytest.raises(ValidationError):
            ExtractionResponse.model_validate_json(response(proposed(field_name=name)))


def test_unknown_attributes_are_rejected_anywhere_in_the_response():
    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate_json(response(proposed(confidence=0.9)))
    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate_json(
            json.dumps({"attributes": [], "fields": [], "notes": "x"})
        )
    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate_json(
            response(attributes=[PROPOSED_ATTRIBUTE | {"confidence": 1}])
        )


@pytest.mark.parametrize("raw", [1482.3, 1482, True, None, ""])
def test_the_raw_value_must_be_a_non_empty_string(raw):
    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate_json(response(proposed(raw_value=raw)))


@pytest.mark.parametrize(
    "overrides",
    [{"page_number": 0}, {"page_number": "3"}, {"currency": "inr"}, {"scale": "lakhs"},
     {"period_role": "prior"}, {"evidence_quote": ""}, {"line_item_label": ""}],
)  # fmt: skip
def test_malformed_proposed_fields_are_rejected(overrides):
    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate_json(response(proposed(**overrides)))


def test_a_field_missing_a_required_member_is_rejected():
    data = proposed()
    del data["evidence_quote"]

    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate_json(response(data))


def test_text_that_is_not_json_is_rejected():
    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate_json("not json")


def test_the_same_field_may_appear_on_several_pages():
    parsed = ExtractionResponse.model_validate_json(
        response(proposed(page_number=3), proposed(page_number=114))
    )

    assert [f.page_number for f in parsed.fields] == [3, 114]


# --- the JSON schema sent to the model ---------------------------------------------------------------------


def test_the_json_schema_forbids_additional_properties_everywhere():
    schema = ExtractionResponse.model_json_schema()
    objects = [schema] + [d for d in schema["$defs"].values() if d.get("type") == "object"]

    assert len(objects) == 3  # response, field, attribute
    assert all(o.get("additionalProperties") is False for o in objects)


def test_the_json_schema_lists_exactly_the_extractable_field_names():
    schema = ExtractionResponse.model_json_schema()

    assert set(schema["$defs"]["ExtractableFieldName"]["enum"]) == {m.value for m in ExtractableFieldName}
    assert "ebit" not in schema["$defs"]["ExtractableFieldName"]["enum"]


def test_the_json_schema_requires_the_evidence_members():
    schema = ExtractionResponse.model_json_schema()

    assert set(schema["$defs"]["ProposedField"]["required"]) == set(ProposedField.model_fields)
    assert schema["required"] == ["attributes", "fields"]
    assert set(ProposedAttribute.model_fields) >= {"attribute", "raw_text", "evidence_quote"}


def test_the_json_schema_is_stable_between_calls():
    assert json.dumps(ExtractionResponse.model_json_schema(), sort_keys=True) == json.dumps(
        ExtractionResponse.model_json_schema(), sort_keys=True
    )


def test_document_attribute_names_are_the_h12_set():
    assert {m.value for m in DocumentAttributeName} == {
        "entity_name", "period_end", "statement_basis", "reporting_currency", "scale",
    }  # fmt: skip
