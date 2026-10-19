"""Field verification and assembly on real PDFs (PRD FR-005.3, H.1; step 7e; B-216).

Appendix B Examples 1 to 3 and B.6 rows 1, 2 and 11 to 14. Synthetic reportlab PDFs
generated at test time: years centred over right-aligned figures, a Note column, a
scale and currency declaration, and Non-current and Current liabilities headings.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from credit_intel.extraction.attributes import verify_attributes
from credit_intel.extraction.verify import FieldVerifier, VerificationContext
from credit_intel.ingestion.models import CandidatePage, LocatorResult
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor
from credit_intel.models import (
    DocumentAttributeName as Name,
    ExtractableFieldName as F,
    ExtractionResponse,
    PeriodRole,
    ProposedAttribute,
    ProposedField,
    Scale,
    SourceDocument,
    Status,
    StatusReason as R,
    ValueInterpretation,
)

CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE
D25, D24 = date(2025, 3, 31), date(2024, 3, 31)

ROWS = [
    # label, note, current, comparative ("" is a blank cell)
    ("Total current assets", "14", "1,482.30", "1,356.75"),
    ("Total current liabilities", "15", "900.00", "850.00"),
    ("Total equity", "", "600.00", "500.00"),
    ("Non-current liabilities", None, None, None),
    ("Borrowings", "16", "300.00", "250.00"),
    ("Current liabilities", None, None, None),
    ("Borrowings", "17", "120.00", "100.00"),
    ("Profit/(loss) for the year", "", "(245.10)", "312.40"),
    ("Finance costs", "", "-", "5.00"),
    ("Other income", "", "7.00", "6.00"),
    ("Revenue from operations", "", "", "1.00"),
    ("Total borrowings", "", "420.00", "350.00"),
]


def statement_pdf(path: Path, rows=ROWS, scale_line="(Rs. in crore)", extra_lines=(), header=True, pages=1, first_label=None, header_cells=None, titles=None) -> Path:
    pdf = canvas.Canvas(str(path), invariant=1)
    if first_label:
        pdf.addPageLabel(0, style="ARABIC", start=first_label)
    for page in range(pages):
        pdf.setFont("Helvetica", 10)
        y = 780
        if page == 0:
            pdf.drawString(72, y, "Acme Industries Limited")
            y -= 15
        title = (titles or {}).get(page, "Consolidated Balance Sheet")
        if title:
            pdf.drawString(72, y, title)
            y -= 15
        if scale_line and page == 0:
            pdf.drawString(72, y, scale_line)
            y -= 15
        for extra in extra_lines:
            pdf.drawString(72, y, extra)
            y -= 15
        if header:
            pdf.drawString(300, y, "Note")
            cells = (header_cells or {}).get(page, [("31 March 2025", 400), ("31 March 2024", 480)])
            for text, x in cells:
                pdf.drawCentredString(x, y, text)
            y -= 15
        for label, note, current, comparative in rows:
            pdf.drawString(72, y, label)
            if note:
                pdf.drawString(305, y, note)
            if current:
                pdf.drawRightString(430, y, current)
            if comparative:
                pdf.drawRightString(510, y, comparative)
            y -= 14
        pdf.showPage()
    pdf.save()
    return path


def build(path: Path, *, candidates=(1,), located=None, attribute_changes=None, **options):
    pdf = statement_pdf(path, **options)
    extractor = PdfplumberExtractor()
    pages = {p.page_number: p for p in extractor.extract_pages(pdf) if p.page_number in candidates}
    words = {w.page_number: w for w in extractor.extract_words(pdf, sorted(candidates))}
    texts = {n: p.text for n, p in pages.items()}

    def line(needle, page=1):
        return next(l for l in texts[page].split("\n") if needle in l)

    proposals = {
        "entity": ProposedAttribute(attribute=Name.ENTITY_NAME, raw_text="Acme Industries Limited",
                                    normalised_value="Acme Industries Limited", page_number=1,
                                    evidence_quote="Acme Industries Limited"),
        "current": ProposedAttribute(attribute=Name.PERIOD_END, period_role=CUR, raw_text="31 March 2025",
                                     normalised_value="2025-03-31", page_number=1,
                                     evidence_quote=line("31 March 2025")),
        "comparative": ProposedAttribute(attribute=Name.PERIOD_END, period_role=COMP, raw_text="31 March 2024",
                                         normalised_value="2024-03-31", page_number=1,
                                         evidence_quote=line("31 March 2025")),
        "basis": ProposedAttribute(attribute=Name.STATEMENT_BASIS, raw_text="Consolidated",
                                   normalised_value="consolidated", page_number=1,
                                   evidence_quote="Consolidated Balance Sheet"),
        "currency": ProposedAttribute(attribute=Name.REPORTING_CURRENCY, raw_text="Rs.", normalised_value="INR",
                                      page_number=1, evidence_quote=scale_line_text(options)),
        "scale": ProposedAttribute(attribute=Name.SCALE, raw_text="in crore", normalised_value="crore",
                                   page_number=1, evidence_quote=scale_line_text(options)),
    }
    for key, change in (attribute_changes or {}).items():
        if change is None:
            del proposals[key]
        else:
            proposals[key] = proposals[key].model_copy(update=change)
    attributes = verify_attributes(list(proposals.values()), texts)
    located = located or LocatorResult(
        "keywords", tuple(CandidatePage(n, ("balance_sheet",), 9, ()) for n in sorted(candidates))
    )
    context = VerificationContext(
        source_document=SourceDocument(file_name="s.pdf", sha256="a" * 64),
        pages=pages, page_words=words, located=located, attributes=attributes,
    )
    return FieldVerifier(context), line, attributes


def scale_line_text(options):
    return options.get("scale_line", "(Rs. in crore)") or "Consolidated Balance Sheet"


def proposal(line, field, role, raw, needle, label=None, scale=Scale.CRORE, currency="INR", page=1, quote=None):
    return ProposedField(
        field_name=field, period_role=role, raw_value=raw, scale=scale, currency=currency,
        page_number=page, evidence_quote=quote or line(needle),
        line_item_label=label or needle,
    )


@pytest.fixture
def env(tmp_path):
    return build(tmp_path / "s.pdf")


def verify(env, field, role, raw, needle, **kw):
    verifier, line, _ = env
    return verifier.verify(proposal(line, field, role, raw, needle, **kw))


# --- a clean field (B.6 row 1) -------------------------------------------------------------------------------


def test_b6_row_1_a_clean_field_is_extracted_in_base_units(env):
    result = verify(env, F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets")
    record = result.field

    assert result.reasons == () and record.status is Status.EXTRACTED and record.status_reason is None
    assert record.value == Decimal("14823000000.00") and record.currency == "INR"
    assert record.field_id == "current_assets.2025-03-31.consolidated"
    assert record.period_end == D25 and record.period_role is CUR
    assert record.scale is Scale.CRORE and record.value_interpretation is ValueInterpretation.NUMBER
    assert record.page_number == 1 and record.source_document.sha256 == "a" * 64


def test_the_comparative_figure_is_extracted_for_the_comparative_period(env):
    record = verify(env, F.CURRENT_ASSETS, COMP, "1,356.75", "Total current assets").field

    assert record.status is Status.EXTRACTED and record.period_end == D24
    assert record.field_id == "current_assets.2024-03-31.consolidated"
    assert record.value == Decimal("13567500000.00")


def test_every_check_is_recorded_as_passed(env):
    validation = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field.validation

    assert validation.all_passed()
    assert validation.details["column"]["token"]["text"] == "600.00"
    assert validation.details["column"]["conditions"]["boundary"] is True
    assert validation.details["column"]["anchor_quotes"] == ["31 March 2025"]
    assert validation.details["label"]["matched_phrase"] == "total equity"
    assert validation.details["scale"]["supported_by"] == "cited_page"
    assert validation.details["period"]["evidence"]["method"] == "full_date"


def test_the_evidence_is_stored_exactly_as_proposed(env):
    verifier, line, _ = env
    given = proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", label="Total Equity ")

    record = verifier.verify(given).field

    assert record.raw_value == "600.00" and record.evidence_quote == line("Total equity")
    assert record.line_item_label == "Total Equity "


def test_a_padded_quote_is_kept_as_proposed(env):
    verifier, line, _ = env
    padded = "  " + line("Total equity") + "  "
    given = proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", quote=padded)

    record = verifier.verify(given).field

    assert record.status is Status.EXTRACTED and record.evidence_quote == padded


def test_the_page_label_of_the_cited_page_is_recorded(tmp_path):
    env = build(tmp_path / "pl.pdf", first_label=45)

    assert verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field.page_label == "45"


def test_the_record_is_json_serialisable(env):
    record = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field

    json.dumps(record.model_dump(mode="json"))


# --- Example 1: the period column -----------------------------------------------------------------------------------


def test_example_1_the_comparative_figure_for_the_current_period_is_rejected(env):
    result = verify(env, F.CURRENT_ASSETS, CUR, "1,356.75", "Total current assets")

    assert result.field.status is Status.REQUIRES_REVIEW
    assert result.field.status_reason is R.PERIOD_NOT_VERIFIED
    assert result.field.value is None and result.field.currency is None
    assert result.field.validation.period_column_verified is False
    assert result.field.validation.sign_verified is None


def test_example_1_the_note_reference_is_not_a_value(env):
    result = verify(env, F.CURRENT_ASSETS, CUR, "14", "Total current assets")

    assert result.field.status_reason is R.PERIOD_NOT_VERIFIED


# --- Example 2: sign ------------------------------------------------------------------------------------------------------


def test_example_2_an_unbracketed_value_for_a_bracketed_cell_is_a_sign_mismatch(env):
    result = verify(env, F.NET_PROFIT, CUR, "245.10", "Profit/(loss) for the year", label="Profit/(loss) for the year")

    assert result.field.status_reason is R.SIGN_MISMATCH and result.field.value is None
    assert result.field.validation.sign_verified is False
    assert result.field.validation.period_column_verified is True


def test_example_2_the_bracketed_value_is_negative(env):
    record = verify(env, F.NET_PROFIT, CUR, "(245.10)", "Profit/(loss) for the year").field

    assert record.status is Status.EXTRACTED and record.value == Decimal("-2451000000.00")


# --- Example 3: scale -------------------------------------------------------------------------------------------------------


def test_example_3_a_scale_the_page_does_not_declare_is_not_verified(env):
    result = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", scale=Scale.LAKH)

    assert result.field.status_reason is R.SCALE_NOT_VERIFIED
    assert result.field.validation.scale_verified is False


def test_example_3_two_declarations_make_the_scale_ambiguous(tmp_path):
    env = build(tmp_path / "a.pdf", extra_lines=("(Rs. in lakh)",))
    result = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity")

    assert result.field.status_reason is R.SCALE_AMBIGUOUS


def test_b6_row_11_a_thousands_page_scales_by_a_thousand_and_the_note_is_not_a_value(tmp_path):
    rows = [("Total current assets", "14", "840,000", "760,000")]
    env = build(tmp_path / "k.pdf", rows=rows, scale_line="(Rs. in thousands)",
                attribute_changes={"scale": {"raw_text": "in thousands", "normalised_value": "thousands"}})

    current = verify(env, F.CURRENT_ASSETS, CUR, "840,000", "Total current assets", scale=Scale.THOUSANDS).field
    note = verify(env, F.CURRENT_ASSETS, CUR, "14", "Total current assets", scale=Scale.THOUSANDS).field

    assert current.status is Status.EXTRACTED and current.value == Decimal("840000000")
    assert note.status is Status.REQUIRES_REVIEW


# --- B.6 rows 2, 13, 14 and labels ----------------------------------------------------------------------------------------


def test_b6_row_2_text_that_is_not_on_the_page_is_not_verified(env):
    verifier, line, _ = env
    given = proposal(line, F.REVENUE, CUR, "9,999.00", "x", quote="Revenue from operations 9,999.00")

    result = verifier.verify(given)

    assert result.field.status_reason is R.EVIDENCE_NOT_VERIFIED
    assert result.field.validation.evidence_verified is False


def test_b6_row_13_a_nil_dash_is_a_reported_zero(env):
    record = verify(env, F.INTEREST_EXPENSE, CUR, "-", "Finance costs").field

    assert record.status is Status.EXTRACTED and record.value == 0
    assert record.value_interpretation is ValueInterpretation.REPORTED_NIL
    assert record.raw_value == "-"
    assert record.validation.sign_verified is True


def test_b6_row_14_a_blank_cell_with_a_proposal_is_not_accepted(env):
    result = verify(env, F.REVENUE, CUR, "1.00", "Revenue from operations")

    assert result.field.status_reason is R.PERIOD_NOT_VERIFIED
    assert verify(env, F.REVENUE, COMP, "1.00", "Revenue from operations").field.status is Status.EXTRACTED


def test_a_label_that_is_not_the_fields_is_not_recognised(env):
    result = verify(env, F.REVENUE, CUR, "7.00", "Other income")

    assert result.field.status_reason is R.LABEL_NOT_RECOGNISED
    assert result.field.validation.label_verified is False
    assert result.field.validation.period_column_verified is True


def test_borrowings_are_placed_by_their_section_heading(env):
    non_current = verify(env, F.BORROWINGS_NON_CURRENT, CUR, "300.00", "Borrowings 16", label="Borrowings").field
    current = verify(env, F.BORROWINGS_CURRENT, CUR, "120.00", "Borrowings 17", label="Borrowings").field
    wrong = verify(env, F.BORROWINGS_CURRENT, CUR, "300.00", "Borrowings 16", label="Borrowings")

    assert non_current.status is Status.EXTRACTED and non_current.value == Decimal("3000000000.00")
    assert current.status is Status.EXTRACTED and current.value == Decimal("1200000000.00")
    assert wrong.field.status_reason is R.LABEL_NOT_RECOGNISED


# --- the order of reasons (FR-005.3) -----------------------------------------------------------------------------------------


def test_evidence_not_verified_comes_before_everything(env):
    verifier, line, _ = env
    given = proposal(line, F.REVENUE, CUR, "9.00", "x", quote="Nothing like this on the page 9.00", scale=Scale.LAKH, currency="USD")

    result = verifier.verify(given)

    assert result.reasons[0] is R.EVIDENCE_NOT_VERIFIED
    assert result.field.status_reason is R.EVIDENCE_NOT_VERIFIED
    assert set(result.reasons) >= {R.EVIDENCE_NOT_VERIFIED, R.SCALE_NOT_VERIFIED, R.CURRENCY_NOT_VERIFIED}


def test_evidence_not_verified_comes_before_value_not_in_evidence_when_both_fail(env):
    verifier, line, _ = env
    given = proposal(line, F.REVENUE, CUR, "5.55", "x", quote="Nothing like this on the page")

    result = verifier.verify(given)

    assert result.reasons[:2] == (R.EVIDENCE_NOT_VERIFIED, R.VALUE_NOT_IN_EVIDENCE)


def test_the_row_label_comes_before_a_period_that_was_not_validated(tmp_path):
    env = build(tmp_path / "o.pdf", attribute_changes={"comparative": {"normalised_value": "2024-03-30"}})

    result = verify(env, F.REVENUE, COMP, "6.00", "Other income")

    assert result.reasons[:2] == (R.LABEL_NOT_RECOGNISED, R.PERIOD_MISMATCH)


def test_an_ambiguous_scale_comes_before_the_currency(tmp_path):
    env = build(tmp_path / "a2.pdf", extra_lines=("(Rs. in lakh)",))

    result = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", currency="USD")

    assert result.reasons == (R.SCALE_AMBIGUOUS, R.CURRENCY_NOT_VERIFIED)


def test_the_field_and_attribute_scale_reasons_become_one_scale_reason(tmp_path):
    # Two declarations on the page make the field's own check ambiguous, while the missing
    # scale attribute alone would say not verified: the field carries one scale reason.
    env = build(tmp_path / "a3.pdf", extra_lines=("(Rs. in lakh)",), attribute_changes={"scale": None})

    result = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity")

    assert result.reasons == (R.SCALE_AMBIGUOUS,)


def test_value_not_in_evidence_comes_second(env):
    result = verify(env, F.TOTAL_EQUITY, CUR, "5.55", "Total equity")

    assert result.field.status_reason is R.VALUE_NOT_IN_EVIDENCE


def test_the_row_label_comes_before_the_period_column_and_the_scale(env):
    result = verify(env, F.REVENUE, CUR, "6.00", "Other income", scale=Scale.LAKH)

    assert result.reasons[:3] == (R.LABEL_NOT_RECOGNISED, R.PERIOD_NOT_VERIFIED, R.SCALE_NOT_VERIFIED)


def test_the_period_column_comes_before_the_sign_and_the_scale(env):
    result = verify(env, F.NET_PROFIT, CUR, "312.40", "Profit/(loss) for the year", scale=Scale.LAKH)

    assert result.reasons == (R.PERIOD_NOT_VERIFIED, R.SCALE_NOT_VERIFIED)


def test_the_sign_comes_before_the_scale_and_the_scale_before_the_currency(env):
    result = verify(env, F.NET_PROFIT, CUR, "245.10", "Profit/(loss) for the year", scale=Scale.LAKH, currency="USD")

    assert result.reasons == (R.SIGN_MISMATCH, R.SCALE_NOT_VERIFIED, R.CURRENCY_NOT_VERIFIED)
    assert result.field.status_reason is R.SIGN_MISMATCH


def test_a_currency_the_page_does_not_support_is_not_verified(env):
    result = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", currency="USD")

    assert result.field.status_reason is R.CURRENCY_NOT_VERIFIED
    assert result.field.validation.currency_verified is False


def test_a_field_cited_to_a_page_that_is_not_a_candidate_is_not_verified(env):
    verifier, line, _ = env
    given = proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=7)

    result = verifier.verify(given)

    assert result.field.status_reason is R.EVIDENCE_NOT_VERIFIED
    assert result.field.validation.scale_verified is None


# --- document-level attributes block fields (H.1.2) ----------------------------------------------------------------------------


def test_a_missing_currency_attribute_blocks_every_field(tmp_path):
    env = build(tmp_path / "c.pdf", attribute_changes={"currency": None})

    result = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity")

    assert result.field.status_reason is R.CURRENCY_NOT_VERIFIED
    assert result.field.validation.currency_verified is True  # the field's own check passes
    assert result.field.validation.details["blocked_by"] == ["currency_not_verified"]


def test_a_missing_scale_attribute_blocks_every_field(tmp_path):
    env = build(tmp_path / "s2.pdf", attribute_changes={"scale": None})

    assert verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity").field.status_reason is R.SCALE_NOT_VERIFIED


def test_a_missing_basis_attribute_blocks_the_field_but_its_own_page_still_gives_it_a_basis(tmp_path):
    env = build(tmp_path / "b.pdf", attribute_changes={"basis": None})

    result = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity")

    assert result.field.status_reason is R.BASIS_UNKNOWN
    assert result.field.field_id == "total_equity.2025-03-31.consolidated"


def test_an_unknown_basis_is_reported_before_a_failed_period_column(tmp_path):
    env = build(tmp_path / "b2.pdf", attribute_changes={"basis": None})

    result = verify(env, F.CURRENT_ASSETS, CUR, "1,356.75", "Total current assets")

    assert result.reasons == (R.BASIS_UNKNOWN, R.PERIOD_NOT_VERIFIED)


def test_an_unvalidated_comparative_blocks_only_its_own_fields(tmp_path):
    env = build(tmp_path / "p.pdf", attribute_changes={"comparative": {"normalised_value": "2024-03-30"}})

    current = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity")
    comparative = verify(env, F.TOTAL_EQUITY, COMP, "500.00", "Total equity")

    assert current.field.status is Status.EXTRACTED
    assert comparative.field.status_reason is R.PERIOD_MISMATCH
    assert comparative.field.period_end == date(2024, 3, 30)  # the claimed date, not a validated one
    assert comparative.field.validation.period_end_verified is False
    assert comparative.field.validation.period_column_verified is None


def test_a_period_with_no_date_at_all_cannot_be_given_a_field(tmp_path):
    env = build(tmp_path / "n.pdf", attribute_changes={"comparative": None})

    result = verify(env, F.TOTAL_EQUITY, COMP, "500.00", "Total equity")

    assert result.field is None and result.reasons[0] is R.PERIOD_MISMATCH


# --- a continuation page uses the first page of its run (FR-005.8, FR-013 rule 6) -----------------------------------------------


def test_a_second_page_in_the_run_takes_its_scale_and_currency_from_the_first(tmp_path):
    located = LocatorResult("keywords", (CandidatePage(1, ("balance_sheet",), 9, ()), CandidatePage(2, ("balance_sheet",), 5, ())))
    env = build(tmp_path / "r.pdf", candidates=(1, 2), located=located, pages=2)
    verifier, line, _ = env

    result = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=2))

    assert result.field.status is Status.EXTRACTED
    assert result.field.validation.details["scale"]["supported_by"] == "run_start"
    assert result.field.validation.details["currency"]["supported_by"] == "run_start"


def test_a_year_only_header_on_a_second_page_is_derived_from_the_current_period_of_the_first(tmp_path):
    located = LocatorResult("keywords", (CandidatePage(1, ("balance_sheet",), 9, ()), CandidatePage(2, ("balance_sheet",), 5, ())))
    # The second page (index 1) has only a year-only comparative header.
    env = build(tmp_path / "y.pdf", candidates=(1, 2), located=located, pages=2,
                header_cells={0: [("31 March 2025", 400), ("31 March 2024", 480)], 1: [("2024", 480)]})
    verifier, line, _ = env

    result = verifier.verify(proposal(line, F.TOTAL_EQUITY, COMP, "500.00", "Total equity", page=2))

    assert result.field.status is Status.EXTRACTED, result.reasons
    assert result.field.validation.details["column"]["anchor_quotes"] == ["2024"]


def test_without_a_run_the_second_page_has_no_declaration(tmp_path):
    located = LocatorResult("page_range", (CandidatePage(1, (), None, ()), CandidatePage(2, (), None, ())))
    env = build(tmp_path / "r2.pdf", candidates=(1, 2), located=located, pages=2)
    verifier, line, _ = env

    result = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=2))

    assert result.field.status_reason is R.SCALE_NOT_VERIFIED


# --- the basis of each field (H.4.6, step 8a) -----------------------------------------------------------------------------------


def two_pages(tmp_path, titles, name="bases.pdf", **kw):
    located = LocatorResult("keywords", (CandidatePage(1, ("balance_sheet",), 9, ()), CandidatePage(2, ("balance_sheet",), 5, ())))
    return build(tmp_path / name, candidates=(1, 2), located=located, pages=2, titles=titles, **kw)


def test_each_field_takes_the_basis_of_its_own_statement(tmp_path):
    env = two_pages(tmp_path, {0: "Consolidated Balance Sheet", 1: "Standalone Balance Sheet"})
    verifier, line, _ = env

    first = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=1)).field
    second = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=2)).field

    assert first.field_id == "total_equity.2025-03-31.consolidated" and first.status is Status.EXTRACTED
    assert second.field_id == "total_equity.2025-03-31.standalone"
    assert second.validation.details["basis"] == {"value": "standalone", "read_from": "cited_page"}


def test_a_continuation_page_without_a_title_takes_the_basis_of_its_runs_first_page(tmp_path):
    env = two_pages(tmp_path, {0: "Consolidated Balance Sheet", 1: None})
    verifier, line, _ = env

    record = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=2)).field

    assert record.field_id.endswith(".consolidated") and record.status is Status.EXTRACTED
    assert record.validation.details["basis"] == {"value": "consolidated", "read_from": "run_start"}


def test_a_statement_with_no_basis_wording_is_unknown_not_standalone(tmp_path):
    env = build(tmp_path / "nb.pdf", titles={0: "Balance Sheet"}, attribute_changes={"basis": None})
    verifier, line, _ = env

    result = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity"))

    assert result.field.field_id.endswith(".unknown") and result.field.status_reason is R.BASIS_UNKNOWN


def test_a_page_without_basis_wording_is_unknown_even_when_the_documents_basis_is_verified(tmp_path):
    env = two_pages(tmp_path, {0: "Consolidated Balance Sheet", 1: "Balance Sheet"})
    verifier, line, attributes = env

    result = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity", page=2))

    assert attributes.statement_basis.status is Status.EXTRACTED
    assert result.field.field_id.endswith(".unknown") and result.field.status_reason is R.BASIS_UNKNOWN


def test_a_title_naming_both_bases_is_unknown(tmp_path):
    env = build(tmp_path / "both.pdf", titles={0: "Consolidated and Standalone Balance Sheet"},
                attribute_changes={"basis": None})
    verifier, line, _ = env

    result = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity"))

    assert result.field.field_id.endswith(".unknown") and R.BASIS_UNKNOWN in result.reasons


def test_with_no_title_anywhere_and_no_run_the_basis_is_unknown(tmp_path):
    located = LocatorResult("page_range", (CandidatePage(1, (), None, ()),))
    env = build(tmp_path / "nt.pdf", titles={0: None}, located=located, attribute_changes={"basis": None})
    verifier, line, _ = env

    result = verifier.verify(proposal(line, F.TOTAL_EQUITY, CUR, "600.00", "Total equity"))

    assert result.field.field_id.endswith(".unknown") and result.field.validation.details["basis"]["read_from"] is None


# --- the whole response ----------------------------------------------------------------------------------------------------------


def test_verify_all_checks_every_proposed_field_in_order(env):
    verifier, line, _ = env
    fields = (
        proposal(line, F.CURRENT_ASSETS, CUR, "1,482.30", "Total current assets"),
        proposal(line, F.CURRENT_ASSETS, CUR, "1,356.75", "Total current assets"),
        proposal(line, F.TOTAL_EQUITY, COMP, "500.00", "Total equity"),
    )

    results = verifier.verify_all(ExtractionResponse(attributes=(), fields=fields))

    assert [r.field.status for r in results] == [Status.EXTRACTED, Status.REQUIRES_REVIEW, Status.EXTRACTED]
    assert [r.proposed for r in results] == list(fields)


def test_verification_is_repeatable_and_reuses_the_page_analysis(env):
    first = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity")
    second = verify(env, F.TOTAL_EQUITY, CUR, "600.00", "Total equity")

    assert first == second


# --- properties over generated proposals (fixed seed) --------------------------------------------------------------------------


def test_properties_hold_for_generated_proposals(tmp_path):
    import random

    from credit_intel.extraction.normalise import apply_scale, parse_value
    from credit_intel.extraction.verify import _ORDER

    env = build(tmp_path / "prop.pdf")
    verifier, line, _ = env
    rng = random.Random(20261019)
    text_lines = [l for l in PdfplumberExtractor().extract_pages(tmp_path / "prop.pdf")[0].text.split("\n")]
    row_lines = [l for l in text_lines if any(ch.isdigit() for ch in l) and not l.startswith("Note")]
    needles = {
        F.REVENUE: "Revenue from operations", F.NET_PROFIT: "Profit/(loss)", F.INTEREST_EXPENSE: "Finance costs",
        F.CURRENT_ASSETS: "Total current assets", F.CURRENT_LIABILITIES: "Total current liabilities",
        F.TOTAL_BORROWINGS: "Total borrowings", F.BORROWINGS_NON_CURRENT: "Borrowings 16",
        F.BORROWINGS_CURRENT: "Borrowings 17", F.TOTAL_EQUITY: "Total equity",
    }
    checked = extracted = 0
    for _ in range(400):
        field = rng.choice(list(needles))
        role = rng.choice([CUR, COMP])
        quote = next(l for l in row_lines if l.startswith(needles[field].split()[0]) and needles[field] in l)
        tokens = quote.split()
        right = tokens[-2] if role is CUR else tokens[-1]
        proposed = ProposedField(
            field_name=field,
            period_role=role,
            raw_value=right if rng.random() < 0.7 else rng.choice(tokens),
            scale=Scale.CRORE if rng.random() < 0.8 else rng.choice(list(Scale)),
            currency="INR" if rng.random() < 0.85 else rng.choice(["USD", "EUR"]),
            page_number=1 if rng.random() < 0.9 else 2,
            evidence_quote=quote if rng.random() < 0.9 else "invented text 1.00",
            line_item_label=" ".join(tokens[:2]),
        )
        result = verifier.verify(proposed)
        checked += 1
        record = result.field
        assert record is not None  # both periods have dates in this document
        # the reasons are in the PRD order, and the status follows them
        assert list(result.reasons) == sorted(result.reasons, key=_ORDER.index)
        if record.status is Status.EXTRACTED:
            extracted += 1
            assert result.reasons == () and record.status_reason is None
            assert record.validation.all_passed()
            parsed = parse_value(record.raw_value)
            assert record.value == apply_scale(parsed.value, record.scale)
            assert record.currency == "INR" and record.scale is Scale.CRORE
            assert record.evidence_quote == proposed.evidence_quote and record.raw_value == proposed.raw_value
        else:
            assert record.status_reason is result.reasons[0]
            assert record.value is None and record.currency is None
        # the evidence is never edited
        assert record.line_item_label == proposed.line_item_label
        assert record.field_id.endswith(f".{record.statement_basis.value}")
        assert verifier.verify(proposed) == result
    assert checked == 400 and 0 < extracted < checked
