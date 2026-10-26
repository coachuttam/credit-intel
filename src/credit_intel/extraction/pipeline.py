"""The offline extraction pipeline, from a PDF to the run's field set (Phase 2 step 9).

``run_extraction`` chains the committed stages in the FR-011 order: the PDF is validated
and its text read (FR-001, FR-002); the statement pages are located, or the supplied page
range is used (FR-013); the model is asked once for the fields (FR-003, FR-004: gates,
cache, token ceiling, one corrective retry); word positions are read for the candidate pages
only; the document-level attributes and then every proposed field are verified (FR-005); and
the field set is built (FR-006, H.4).

It stops at the field set. The run directory, manifest, ``results.json``, the error
catalogue's exit codes and the command line (FR-009 to FR-012, FR-014) are Phase 5, so a
catalogued failure simply propagates as ``IngestionError``. Logging uses the standard
library only. At INFO a line holds a stage name, counts, durations and a short document
hash, never document text, quotes, file names or values (FR-012.3).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from credit_intel.config import (
    OCR_LANGUAGE,
    OcrSettings,
    ColumnSettings,
    DeclarationSettings,
    IngestionSettings,
    LabelSettings,
    LLMSettings,
    LocatorSettings,
    PricingSettings,
)
from credit_intel.extraction.assertion import BasisAssertion, apply_assertion
from credit_intel.extraction.attributes import VerifiedAttributes, verify_attributes
from credit_intel.extraction.extract import ExtractionResult, extract_fields
from credit_intel.extraction.field_set import FieldSet, build_field_set
from credit_intel.extraction.ocr_evidence import OcrReading, OcrRunRecord, mean_confidence
from credit_intel.extraction.prompt import Prompt, load_prompt
from credit_intel.extraction.verify import FieldRefiling, FieldScan, FieldVerification, FieldVerifier, VerificationContext
from credit_intel.extraction.bases import drop_unknown_basis_pages
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.extractor import OcrExtractor, TextExtractor, WordExtractor
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.locator import check_statement_basis, locate_statements, parse_page_range
from credit_intel.ingestion.ocr_pages import plan_ocr_pages, render_dpis, require_page_range_for_scan
from credit_intel.ingestion.models import IngestedDocument, LocatorResult, OcrPage
from credit_intel.llm.budget import TokenBudget
from credit_intel.llm.cache import DEFAULT_CACHE_DIR, ResponseCache
from credit_intel.llm.cost import estimate_cost
from credit_intel.llm.gateway import LLMGateway
from credit_intel.llm.provider import LLMProvider
from credit_intel.pagefilter.filter import PageFilterOutcome, PageFilterSetup, filter_candidates, unavailable_outcome
from credit_intel.models import SourceDocument, StatementBasis, Status

logger = logging.getLogger("credit_intel.pipeline")

from credit_intel.states import (  # noqa: E402  (FR-011 states; defined once in states.py)
    FAILED,
    FIELDS_EXTRACTED,
    RECEIVED,
    STATEMENTS_LOCATED,
    TEXT_EXTRACTED,
    VALIDATED,
    VALIDATED_FIELDS,
)


@dataclass(frozen=True)
class RunStats:
    llm_calls: int  # provider calls made; a cache hit or a refused call makes none
    tokens_used: int  # counted against the per-run ceiling (NFR-09)
    cache_hits: int
    cache_misses: int
    llm_retries: int = 0  # attempts made again after a transient failure (FR-011.3)
    input_tokens: int = 0  # as reported by the provider, over the calls made
    output_tokens: int = 0
    estimated_cost: Decimal | None = None  # USD, only if prices are configured (D-02)
    cached_input_tokens: int = 0  # what the cache hits stand for: not billed, but the size of the request (comparing runs)
    cached_output_tokens: int = 0


@dataclass(frozen=True)
class ExtractionRun:
    source_document: SourceDocument
    page_count: int
    configured_basis: StatementBasis
    located: LocatorResult
    extraction: ExtractionResult
    attributes: VerifiedAttributes
    verifications: tuple[FieldVerification, ...]
    field_set: FieldSet
    stats: RunStats
    # The model's verified basis attribute names another basis than the configured one.
    # Nothing is blocked (each field carries its own page's basis); the analyst can see it.
    attribute_basis_differs: bool
    # The analyst's assertion of the basis for the pages of a ``--pages`` run, and where it was needed
    # (H.4.6, v0.4.24); ``None`` if none was given.
    basis_assertion: BasisAssertion | None = None
    # What the optional page classifier did (PRD v0.4.31); ``None`` when it was not switched on.
    page_filter: PageFilterOutcome | None = None
    # A total_borrowings proposal verified as a borrowings component because its row is one (PRD v0.4.38); empty if none.
    field_refilings: tuple[FieldRefiling, ...] = ()
    # A borrowings component row the model did not propose, proposed by the code from a balance-sheet page (PRD v0.4.39); empty if none.
    field_scans: tuple[FieldScan, ...] = ()
    # What OCR read and from which engine (PRD v0.4.44); ``None`` when OCR was not used, so the manifest has no ``ocr`` block.
    ocr: OcrRunRecord | None = None


def _ocr_column_settings(column_settings: ColumnSettings | None, ocr: OcrSettings | None) -> ColumnSettings:
    """The text-layer column settings with the two the OCR settings replace (PRD FR-005 criterion 11)."""
    assert ocr is not None and ocr.column_margin_pt is not None and ocr.split_figure_gap_pt is not None
    return replace(column_settings or ColumnSettings(), column_margin_pt=ocr.column_margin_pt, split_figure_gap_pt=ocr.split_figure_gap_pt)


def _ocr_record(engine: OcrExtractor, settings: OcrSettings, pages: dict[int, OcrPage], used: list[int]) -> OcrRunRecord:
    return OcrRunRecord(
        engine=engine.name,
        engine_version=engine.version,
        dpi_cap=settings.dpi,
        language=OCR_LANGUAGE,
        ocr_pages={n: mean_confidence([w.confidence for w in page.words]) for n, page in pages.items()},
        page_dpi={n: page.dpi for n, page in pages.items() if page.dpi is not None},
        text_layer_pages=tuple(n for n in used if n not in pages),
    )


def _ocr_range(document: IngestedDocument, page_range: str | None, locator_settings: LocatorSettings | None) -> tuple[int, ...] | None:
    """The pages of the page range, checked before any OCR (FR-001A.3); ``None`` for a document with a text layer and no range.

    A document without a text layer needs ``--pages``, and the range must lie inside the document: otherwise ``E-INPUT-PAGE-RANGE``.
    """
    require_page_range_for_scan(document.pages, page_range)
    if page_range is None:
        return None
    return parse_page_range(page_range, len(document.pages), (locator_settings or LocatorSettings()).max_candidates)


def _read_by_ocr(
    document: IngestedDocument,
    used: tuple[int, ...],
    settings: OcrSettings,
    engine: OcrExtractor | None,
    extractor: object,
) -> tuple[IngestedDocument, dict[int, OcrPage]]:
    """Read the image-only pages among ``used`` by OCR (FR-001A); return the document with their text in place.

    The page cap (``E-INPUT-OCR-FAILED``), an empty plan (``E-INPUT-NO-TEXT-LAYER``), a missing engine and the engine's own
    errors all belong to the text stage (G.1).
    """
    coverage = extractor.image_coverage(document.file_info.path)  # type: ignore[attr-defined]
    planned = plan_ocr_pages(document.pages, coverage, used, settings)
    if not planned:
        return document, {}
    if engine is None:
        raise IngestionError(ErrorCode.OCR_UNAVAILABLE)
    assert settings.timeout_seconds is not None
    read = {page.page_number: page for page in engine.ocr_pages(document.file_info.path, planned, dpi=render_dpis(planned, coverage, settings.dpi), timeout_seconds=settings.timeout_seconds)}
    replaced = tuple(read[p.page_number].page_text() if p.page_number in read else p for p in document.pages)
    return IngestedDocument(file_info=document.file_info, pages=replaced), read


def run_extraction(
    path: Path,
    provider: LLMProvider,
    llm: LLMSettings,
    *,
    basis: StatementBasis = StatementBasis.CONSOLIDATED,
    page_range: str | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    prompt: Prompt | None = None,
    extractor: TextExtractor | WordExtractor | None = None,
    ingestion_settings: IngestionSettings | None = None,
    locator_settings: LocatorSettings | None = None,
    label_settings: LabelSettings | None = None,
    declaration_settings: DeclarationSettings | None = None,
    column_settings: ColumnSettings | None = None,
    pricing: PricingSettings | None = None,
    assert_basis: StatementBasis | None = None,
    observer: Callable[[str, dict[str, object]], None] | None = None,
    page_filter: PageFilterSetup | None = None,
    ocr_settings: OcrSettings | None = None,
    ocr_extractor: OcrExtractor | None = None,
) -> ExtractionRun:
    """Run the pipeline on one PDF and return its field set and statistics.

    ``observer(state, counts)`` is told about each stage from ``validated`` onwards, with the same counts that
    are logged (the caller owns ``received``). Raises ``IngestionError`` for a catalogued failure (the input, no candidate pages, a
    missing configured basis, invalid model output twice, or the token ceiling).

    With ``ocr_settings.enabled`` (PRD v0.4.44, FR-001A), a document without a text layer is not refused: its image-only pages
    among those of ``page_range`` are read by ``ocr_extractor`` and their text takes the place of the empty text layer. OCR
    runs only for a page range; a run without one locates statements in the text layer as before.
    """
    if basis not in (StatementBasis.CONSOLIDATED, StatementBasis.STANDALONE):
        raise ValueError("the configured basis is consolidated or standalone")
    if assert_basis is not None and page_range is None:
        raise ValueError("an assertion of the basis needs a page range (H.4.6)")
    prompt = prompt or load_prompt()
    if extractor is None:
        from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

        extractor = PdfplumberExtractor()
    cache = ResponseCache(cache_dir)
    budget = TokenBudget(llm.token_ceiling)
    gateway = LLMGateway(provider, cache, budget)

    started = time.perf_counter()
    stage = RECEIVED
    document_tag = "-"

    def log(state: str, **counts: object) -> None:
        elapsed = int((time.perf_counter() - started) * 1000)
        detail = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("stage=%s doc=%s ms=%d %s", state, document_tag, elapsed, detail)
        if observer is not None and state != RECEIVED:
            observer(state, dict(counts))

    try:
        log(RECEIVED)
        stage = VALIDATED
        def validated(info) -> None:  # called once validation passes, before the text is read
            nonlocal document_tag, stage
            document_tag = info.sha256[:12]
            log(VALIDATED, pages=info.page_count)
            stage = TEXT_EXTRACTED

        ocr_on = ocr_settings is not None and ocr_settings.enabled
        document = ingest(path, ingestion_settings, extractor, on_validated=validated, ocr_enabled=ocr_on)  # type: ignore[arg-type]
        ocr_pages: dict[int, OcrPage] = {}
        if ocr_on:
            assert ocr_settings is not None
            try:
                used = _ocr_range(document, page_range, locator_settings)
            except IngestionError:  # the text layer has been read; what is wrong is the page range, a statements_located failure (G.1)
                log(TEXT_EXTRACTED, pages_with_text=sum(1 for p in document.pages if p.has_text))
                stage = STATEMENTS_LOCATED
                raise
            if used is not None:
                document, ocr_pages = _read_by_ocr(document, used, ocr_settings, ocr_extractor, extractor)
        counts = {"ocr_pages": len(ocr_pages)} if ocr_pages else {}
        log(TEXT_EXTRACTED, pages_with_text=sum(1 for p in document.pages if p.has_text), **counts)

        stage = STATEMENTS_LOCATED
        located = locate_statements(document.pages, locator_settings, page_range)
        assertion = None
        asserted_basis = None
        if located.candidates:  # a missing basis is a statements_located failure (G.1); no pages is fields_extracted
            if assert_basis is not None:  # H.4.6 (v0.4.24): a conflicting page stops the run here, before any model call
                assertion = apply_assertion({p.page_number: p for p in document.pages}, located, assert_basis, locator_settings)
            asserted_basis = assertion.basis.value if assertion is not None and assertion.applied_pages else None
            check_statement_basis(document.pages, located, basis.value, locator_settings, asserted_basis=asserted_basis)
            # H.4.6 (v0.4.21): pages whose basis is unknown are not sent (not for a page range).
            located = drop_unknown_basis_pages({p.page_number: p for p in document.pages}, located, locator_settings)
        asserted = {"asserted_pages": len(assertion.applied_pages)} if assertion is not None else {}
        log(STATEMENTS_LOCATED, method=located.method, candidates=len(located.candidates), **asserted)

        # PRD v0.4.31: the optional classifier may remove candidate pages (never add one); with it off nothing here runs.
        page_filter_outcome = None
        if page_filter is not None and page_filter.settings.enabled and located.candidates:
            if page_filter.classifier is None:
                candidate_pages = tuple(sorted(c.page_number for c in located.candidates))
                page_filter_outcome = unavailable_outcome(page_filter.settings, page_filter.unavailable_reason or "unavailable", candidate_pages)
            else:
                located, page_filter_outcome = filter_candidates(
                    located, {p.page_number: p.text for p in document.pages}, page_filter.classifier, page_filter.settings, basis,
                    document_tag=document_tag, filter_page_ranges=page_filter.filter_page_ranges,
                )

        stage = FIELDS_EXTRACTED
        extraction = extract_fields(
            document, located, gateway, llm, prompt, basis.value, locator_settings, asserted_basis
        )
        log(
            FIELDS_EXTRACTED,
            fields=len(extraction.response.fields),
            attributes=len(extraction.response.attributes),
            attempts=extraction.attempts,
            llm_calls=gateway.calls,
            retries=getattr(provider, "retries", 0),
            tokens=budget.used,
            cache_hits=cache.hits,
        )

        stage = VALIDATED_FIELDS
        candidates = sorted(c.page_number for c in located.candidates)
        by_number = {p.page_number: p for p in document.pages}
        pages = {n: by_number[n] for n in candidates}
        layer_pages = [n for n in candidates if n not in ocr_pages]
        words = {w.page_number: w for w in extractor.extract_words(document.file_info.path, layer_pages)} if layer_pages else {}  # type: ignore[union-attr]
        words.update({n: ocr_pages[n].page_words() for n in candidates if n in ocr_pages})  # an OCR page's boxes are the engine's
        source = SourceDocument(file_name=document.file_info.file_name, sha256=document.file_info.sha256)
        attributes = verify_attributes(
            list(extraction.response.attributes),
            {n: p.text for n, p in pages.items()},
            locator_settings,
            declaration_settings,
            assertion,
            basis,
        )
        verifier = FieldVerifier(
            VerificationContext(
                source_document=source,
                pages=pages,
                page_words=words,
                located=located,
                attributes=attributes,
                label_settings=label_settings,
                declaration_settings=declaration_settings,
                column_settings=column_settings,
                locator_settings=locator_settings,
                assertion=assertion,
                ocr_column_settings=_ocr_column_settings(column_settings, ocr_settings) if ocr_pages else None,
                ocr=OcrReading(ocr_extractor.name, ocr_extractor.version, ocr_settings.dpi, ocr_pages) if ocr_pages and ocr_extractor and ocr_settings else None,
            )
        )
        verifications = verifier.verify_all(extraction.response)
        field_set = build_field_set(verifications, attributes, located, basis, source)
        log(VALIDATED_FIELDS, **field_set.counts, ignored=len(field_set.ignored), unplaced=len(field_set.unplaced))
    except IngestionError as error:
        logger.info("stage=%s doc=%s after=%s code=%s", FAILED, document_tag, stage, error.code.value)
        raise

    basis_attribute = attributes.statement_basis
    return ExtractionRun(
        source_document=source,
        page_count=document.file_info.page_count,
        configured_basis=basis,
        located=located,
        extraction=extraction,
        attributes=attributes,
        verifications=verifications,
        field_set=field_set,
        stats=RunStats(
            gateway.calls,
            budget.used,
            cache.hits,
            cache.misses,
            getattr(provider, "retries", 0),
            gateway.input_tokens,
            gateway.output_tokens,
            estimate_cost(gateway.input_tokens, gateway.output_tokens, pricing) if pricing else None,
            gateway.cached_input_tokens,
            gateway.cached_output_tokens,
        ),
        attribute_basis_differs=(
            basis_attribute.status is Status.EXTRACTED and basis_attribute.normalised_value != basis.value
        ),
        basis_assertion=assertion,
        page_filter=page_filter_outcome,
        field_refilings=verifier.refilings,
        field_scans=verifier.scans,
        ocr=_ocr_record(ocr_extractor, ocr_settings, ocr_pages, candidates) if ocr_pages and ocr_extractor and ocr_settings else None,
    )
