# Product Requirements Document — AI Credit Intelligence Platform

---

## A. Document Information

| Item | Value |
|---|---|
| Project name | AI Credit Intelligence Platform |
| Document | Product Requirements Document (PRD) |
| Version | 0.2 |
| Status | Draft — awaiting project-owner review |
| Date | 2026-10-12 |
| Owner | Project owner (repository maintainer) |
| Location | `docs/PRD.md` |

### A.1 Purpose of this document

This PRD defines what Release 1 of the AI Credit Intelligence Platform must do, how its correctness will be judged, and what is deliberately excluded. It is the reference for implementation phases, test design (`tests/BEHAVIOURS.md`), and progress tracking (`PROGRESS.md`). Requirements here take precedence over ad-hoc implementation choices. Changes to requirements are made by editing this document and bumping its version.

### A.2 Intended audience

- **Developer(s)** implementing the platform, including AI coding assistants operating under `CLAUDE.md`.
- **Reviewers** assessing engineering quality: hiring managers and technical interviewers at banking and financial-services software companies (for example, Azentio). The project is an independent portfolio prototype and is **not affiliated with, endorsed by, or integrated with** any such company.
- **Domain reviewers** (credit analysts or risk practitioners) who may assess whether outputs are sensible.

### A.3 Definitions and abbreviations

| Term | Definition |
|---|---|
| AML | Anti-Money Laundering. |
| Basis (statement basis) | Whether figures are *consolidated* (group) or *standalone* (single entity). |
| Comparative period | The prior period presented alongside the current period in a financial statement. |
| Credit memo | A document summarising a borrower's financial position and risks to support a human credit decision. |
| D/E | Debt-to-equity ratio. |
| Deterministic | Same inputs always produce the same outputs; no randomness or LLM involvement. |
| EBIT | Earnings Before Interest and Tax. |
| Evidence | A verbatim quote from a specific page of a source document that supports an extracted value. |
| Field | A single named financial data point (e.g. `revenue`) for a single reporting period. |
| FR / NFR | Functional Requirement / Non-Functional Requirement. |
| ICR | Interest coverage ratio. |
| LLM | Large Language Model. |
| OCR | Optical Character Recognition (extracting text from images of text). |
| Provenance | The traceable origin of a value: source document, page, and quote. |
| RAG | Retrieval-Augmented Generation. |
| Risk indicator | A rule-based, explainable flag highlighting a potential concern for human review. It is **not** a credit decision. |
| Run | One end-to-end processing of one document, identified by a run ID. |
| Scale | Multiplier in which figures are presented (units, thousands, millions, lakh, crore, billions). |
| Target | A provisional goal to be measured. Not an achieved result. |

---

## B. Executive Summary and Product Vision

The AI Credit Intelligence Platform helps credit analysts turn a company's financial statements (PDF) into an **evidence-backed draft credit memo**. It:

1. Extracts page-level text from a PDF.
2. Uses an LLM to locate and extract specific financial fields into a validated schema, each with a verbatim quote and page number.
3. Verifies that evidence deterministically against the source text.
4. Calculates financial ratios with deterministic, tested Python code.
5. Applies a transparent, configurable rules engine to raise potential risk indicators.
6. Assembles a draft credit memo in Markdown in which every material fact is labelled by origin (source, calculation, rule, or AI interpretation) and is traceable to evidence or explicitly marked unverified.

**Who it serves:** credit analysts, lending teams, and credit risk analysts who review borrower financials.

**Business problem:** preparing a first-draft credit analysis is repetitive, manual, and error-prone. The platform reduces the mechanical work (finding figures, transcribing them, computing ratios, cross-checking) while leaving judgement and decisions to people.

**Vision statement:** *Make every number in a draft credit memo traceable to its source in one click, and never let an AI system invent a figure or make a credit decision.*

**Portfolio context:** Release 1 is a portfolio prototype that demonstrates practical AI engineering — document processing, structured LLM outputs, deterministic calculation, evidence traceability, automated testing, and reliable error handling. It uses only public documents and synthetic borrower data. It is **not** a production lending system.

---

## C. Problem Statement

### C.1 Current effort

A typical first-pass review of a borrower's annual report involves:

- **Locating figures** across long documents (annual reports commonly run to 100–300+ pages), where the same figure may appear in highlights, management discussion, primary statements, and notes — sometimes rounded differently.
- **Transcribing values** into spreadsheets, handling scale (thousands, millions, lakh, crore), currency, and period alignment by hand.
- **Calculating ratios** and checking them against prior periods.
- **Identifying risk signals** such as falling revenue, losses, weakening liquidity, or rising leverage.
- **Writing a memo** that summarises findings and cites sources so a reviewer can verify them.

Each step is manual and repeated for every borrower. Transcription and scale errors propagate silently into ratios and conclusions. Citing sources is tedious, so it is often incomplete, which slows down review and audit.

> **Uncertainty:** this PRD does not quantify current analyst effort (hours per memo). No verified data is available in the project context. If such figures are needed for the portfolio narrative, they must come from a cited source or be clearly labelled as assumptions.

### C.2 How AI can assist — and where it must not

AI is useful for **reading and locating**: finding the page and line where "Revenue from operations" appears and returning it in structured form. AI is unreliable at **arithmetic and judgement**, and it can produce fluent but unsupported statements (hallucinations).

The platform therefore divides responsibilities:

| Task | Performed by |
|---|---|
| Locating and extracting field values with quotes | LLM, constrained by schema |
| Verifying quotes and values exist on the cited page | Deterministic Python |
| Unit/scale normalisation, period alignment | Deterministic Python |
| Ratio calculation | Deterministic Python |
| Risk indicators | Deterministic, configurable rules |
| Narrative commentary (optional) | LLM, given only verified structured data, labelled as AI interpretation, post-checked |
| Credit decision | **Human only — never the system** |

---

## D. Target Users and Use Cases

### D.1 Personas

| Persona | Need | How the platform helps |
|---|---|---|
| **Credit analyst** | Prepare a first-draft analysis of a borrower quickly and accurately. | Extracts figures with evidence, computes ratios, drafts memo sections. |
| **Lending team member / relationship manager** | Understand a borrower's financial position and open questions before a credit discussion. | Readable memo with clear risk indicators and a list of questions. |
| **Credit risk analyst / reviewer** | Independently verify claims in a memo and challenge weak analysis. | Every figure links to document, page, and quote; rules and thresholds are visible. |

### D.2 Primary workflow (Release 1)

1. **Provide document.** The analyst runs the command-line tool with a path to a financial statement PDF, and optionally a synthetic borrower profile (JSON) and a page range.
2. **Validate.** The system checks file type, size, page count, encryption, and presence of a text layer. It rejects unsupported files with a clear error.
3. **Extract text.** The system extracts text page by page, preserving page numbers.
4. **Locate statements.** The system identifies candidate pages containing primary financial statements (income statement, balance sheet), using deterministic keyword heuristics or the analyst-supplied page range.
5. **Extract fields.** The LLM extracts the defined fields for the current and comparative periods, each with value, scale, currency, period, page, and verbatim quote.
6. **Validate and verify.** The system validates output against the schema, verifies each quote appears on the cited page, checks the value appears in the quote, and detects missing, duplicate, and conflicting values.
7. **Calculate.** Ratios are computed deterministically from verified fields only.
8. **Evaluate rules.** Risk indicator rules run against calculated metrics and field statuses.
9. **Draft memo.** The system assembles a Markdown memo with labelled facts, evidence references, open issues, and analyst questions.
10. **Review.** The analyst reads the memo, checks evidence, resolves open questions outside the tool, and makes their own judgement. The memo is a draft and states so.

### D.3 Secondary use cases

- **Re-run for reproducibility:** re-processing the same document with the same configuration and cached LLM responses produces an identical memo.
- **Threshold tuning:** a reviewer edits the rules configuration file and re-runs to see how indicators change. No code change is required.
- **Evaluation:** the developer runs the evaluation harness over a labelled dataset to measure extraction and memo quality.

---

## E. Goals and Success Criteria

> **All numeric values in this section are provisional TARGETS. None has been measured. Results will be recorded in `PROGRESS.md` (or a dedicated evaluation report) only after evaluation runs are performed on the dataset defined in Section O.**

### E.1 Goals

- **G1:** Produce a reproducible, evidence-backed draft credit memo from a supported financial PDF.
- **G2:** Never present an invented value or invented evidence as fact.
- **G3:** Make every risk indicator explainable and configurable.
- **G4:** Fail clearly and safely on unsupported inputs and external failures.
- **G5:** Keep the system small and simple enough for one developer to build, test, and explain.

### E.2 Success criteria (provisional targets)

| ID | Dimension | Metric | Provisional target |
|---|---|---|---|
| SC-01 | Field extraction | Share of in-scope ground-truth fields extracted with correct value, scale, currency, and period (exact match after normalisation) | ≥ 90% on evaluation set |
| SC-02 | Hallucinated values | Share of fields given status `extracted` whose value does not exist in the document | 0 observed; investigate every occurrence |
| SC-03 | Not-found correctness | Share of fields absent from the document that are correctly reported `not_found` (not given a value) | ≥ 95% |
| SC-04 | Evidence verification | Share of `extracted` fields whose quote is verified verbatim on the cited page | 100% — enforced by construction (unverified fields cannot be `extracted`; see FR-005) |
| SC-05 | Page-reference correctness | Share of `extracted` fields whose cited page matches a ground-truth page for that value | ≥ 95% |
| SC-06 | Calculation accuracy | Share of calculation test cases (including edge cases) producing the exact expected result or expected undefined status | 100% |
| SC-07 | Risk-rule accuracy | Share of rule test cases producing the expected trigger state | 100% |
| SC-08 | Unsupported-claim rate | Share of material factual claims in the memo that are neither traceable (to evidence, calculation, or rule ID) nor labelled unverified, as judged by manual review | 0 in source/calculated/rule sections; ≤ 2% of AI-interpretation sentences before rejection by post-check |
| SC-09 | Error handling | Share of catalogued failure scenarios (Section G, FR-011) producing the documented error code, a non-zero exit, and no partial output presented as complete | 100% |
| SC-10 | Latency | End-to-end wall-clock time for a document of ≤ 50 pages, with ≤ 15 candidate statement pages sent to the LLM | ≤ 120 s at the 90th percentile |
| SC-11 | API cost | LLM API cost per document under the same conditions as SC-10 | ≤ USD 0.25 per document (to be revalidated against verified pricing for the configured model; see D-02) |

**Rationale:** deterministic components (calculation, rules, evidence verification) must meet 100% because they are fully specified and testable. LLM-dependent components have realistic, non-perfect targets, and their failures must surface as `requires_review` or `not_found` rather than as wrong facts.

---

## F. Scope and Release Strategy

### F.1 Release 1 — Credit Memo Generator (in scope)

| Capability | Notes |
|---|---|
| PDF ingestion | Text-based PDFs only; no OCR. |
| Financial data extraction | Fixed field set (Section H.3) for two periods: current and comparative. |
| Evidence preservation | Page number and verbatim quote for every extracted value; deterministic verification. |
| Deterministic financial calculations | Five metrics (Section I). |
| Rules-based risk indicators | Seven configurable rules (Section J). |
| Draft credit memo generation | Template-first. Optional LLM narrative is strictly labelled and post-checked. |
| Markdown export | Memo (`.md`), plus a JSON sidecar containing structured results and the run manifest. |
| Automated tests | Unit, integration (with a fake LLM provider), and regression tests. |
| Interface | **Command-line interface only.** |

**Supported document profile for Release 1:**

- Annual financial statements of a **non-financial corporate** borrower.
- English language, with a selectable text layer.
- Two consecutive annual periods presented (current and comparative).

Bank, insurer, and other financial-institution statements are out of scope because the defined ratios do not apply to them meaningfully.

### F.2 Future releases (not in Release 1)

| Enhancement | Indicative trigger |
|---|---|
| Web interface and REST API (FastAPI) | After Release 1 is complete and reviewed (Phase 6). |
| Docker and cloud deployment | Phase 7. |
| Compliance RAG assistant (PostgreSQL + pgvector) | Phase 8, optional. |
| LangGraph workflow orchestration | Phase 8 — only if the workflow gains real branching or human-in-the-loop steps that justify it. |
| AML investigation support using synthetic transaction alerts | Phase 8, optional. |
| Optional integration with authorised enterprise systems | Only with explicit authorisation; never assumed. |
| OCR for scanned PDFs, multi-document comparison, quarterly periods, analyst override files | Candidates for later releases. |

Requirements in Sections G–K apply to **Release 1 only** unless marked otherwise.

---

## G. Functional Requirements

Priority: **Must** = required for Release 1; **Should** = expected unless descoped by explicit decision.

### FR-001 — PDF upload and validation (Must)

**Behaviour:** the CLI accepts a local file path, validates it before any processing, and rejects invalid input with a specific error code.

**Acceptance criteria:**

1. A file whose content does not start with the PDF signature (`%PDF-`) is rejected with `E-INPUT-NOT-PDF`, whatever its extension.
2. A file larger than the configured maximum (default 25 MB) is rejected with `E-INPUT-TOO-LARGE`.
3. A PDF with more pages than the configured maximum (default 400) is rejected with `E-INPUT-TOO-MANY-PAGES`.
4. An encrypted or password-protected PDF is rejected with `E-INPUT-ENCRYPTED`.
5. A corrupt or unparsable PDF is rejected with `E-INPUT-CORRUPT`.
6. A PDF in which no page (or fewer than a configured minimum share of candidate pages) has extractable text is rejected with `E-INPUT-NO-TEXT-LAYER`, and the message states that OCR is not supported.
7. A missing path or unreadable file produces `E-INPUT-NOT-FOUND`.
8. A SHA-256 hash of the input file is computed and recorded in the run manifest.
9. The original file is never modified.

### FR-002 — Page-level text extraction (Must)

**Behaviour:** text is extracted per page and stored with its 1-based physical page number. Printed page labels are stored separately where available.

**Acceptance criteria:**

1. Output is an ordered list of `{page_number, page_label (optional), text}`, with exactly one entry per physical page.
2. Page numbers in every downstream artefact refer to 1-based physical page numbers. Printed labels (e.g. "45") are shown alongside where available.
3. Extraction of the same file is byte-identical across runs (deterministic).
4. Pages with no text are retained with empty text, not dropped, so numbering never shifts.
5. Document text is treated as data only. It is never executed, evaluated, or interpreted as instructions to the system (see M).
6. A deterministic **statement locator** ranks pages likely to contain the income statement and balance sheet, using configurable keywords. The analyst may override this with an explicit page range (`--pages`).

### FR-003 — Financial field extraction (Must)

**Behaviour:** the LLM, called through a provider interface, receives candidate page texts (each tagged with its page number) and returns the fields in Section H.3 for the current and comparative periods.

**Acceptance criteria:**

1. Only candidate pages (FR-002.6) are sent to the LLM, not the whole document.
2. The prompt instructs the model to return only values present in the text, to return `not_found` when a value is absent, and to quote the supporting text verbatim. Prompts are versioned files, and their version is recorded in the run manifest.
3. The model does not perform arithmetic. It extracts reported figures only. Derived values (e.g. EBIT when not reported) are computed in Python (Section I).
4. The extraction call uses the provider's structured-output or JSON mode where available.
5. Every LLM response is cached by `(document hash, page set, prompt version, model ID, schema version)` to support reproducibility (FR-012) and control cost.
6. With a fake provider in tests, the extraction pipeline runs end to end with no network access.

### FR-004 — Structured output validation (Must)

**Behaviour:** LLM output is parsed and validated against the Pydantic schema (Section H) before any further use.

**Acceptance criteria:**

1. Output that is not valid JSON or does not match the schema triggers **one** retry, which includes the validation error message. If the retry also fails, the run fails with `E-LLM-INVALID-OUTPUT`, and the raw response is saved to the run directory for diagnosis.
2. Unknown field names are rejected. Missing expected fields are treated as `not_found`.
3. Values must parse as decimal numbers. Formatting such as thousands separators, parentheses for negatives (`(1,234)`), and currency symbols is normalised deterministically. Unparsable values become `requires_review`.
4. Values are held as `decimal.Decimal`, never binary floats.

### FR-005 — Source evidence and page-number preservation (Must)

**Behaviour:** every extracted value carries a page number and verbatim quote, which are verified deterministically.

**Acceptance criteria:**

1. The quote must occur on the cited page's text after whitespace normalisation (collapse runs of whitespace; normalise Unicode NFKC). No other fuzzy matching is used.
2. The raw value string returned by the model must occur within the verified quote.
3. A field may have status `extracted` only if criteria 1 and 2 both pass. Otherwise its status is `requires_review`, with reason `evidence_not_verified` or `value_not_in_evidence`.
4. Evidence is never edited, summarised, or regenerated after verification. The memo reproduces it verbatim (truncated with an ellipsis only for display, with the full text in the JSON sidecar).
5. Every value shown in the memo carries a reference to its field ID, which resolves to document, page, and quote.

### FR-006 — Missing and conflicting information detection (Must)

**Behaviour:** absent, duplicated, inconsistent, and conflicting values are detected and surfaced. They are never silently resolved.

**Acceptance criteria:**

1. A required field with no verified value is marked `not_found`, and every metric that depends on it is reported as undefined, with reason `missing_input`.
2. Multiple verified occurrences of the same field, period, and basis are reconciled using the rules in Section H.4. Inconsistent occurrences produce status `conflicting`, with all candidate values and their evidence retained.
3. Fields marked `conflicting` or `requires_review` are **excluded** from calculations. Dependent metrics are undefined, with reason `input_conflicting` or `input_requires_review`.
4. The memo's "Missing information and conflicts" section lists every non-`extracted` field with its status, reason, and candidate evidence.

### FR-007 — Financial ratio calculations (Must)

**Behaviour:** the five metrics in Section I are computed by pure, deterministic Python functions.

**Acceptance criteria:**

1. Each metric function is pure: no I/O, no randomness, no LLM calls.
2. Each result records the formula, the input field IDs and values used, the period(s), and either a value or an explicit undefined status with a reason code.
3. Every edge case listed in Section I has a unit test.
4. Rounding is applied **only for display**. Stored values keep full `Decimal` precision. Display uses `ROUND_HALF_EVEN`: ratios to 2 decimal places and percentages to 1 decimal place.

### FR-008 — Rules-based risk indicator generation (Must)

**Behaviour:** configurable rules (Section J) evaluate calculated metrics and field statuses and produce explainable indicators.

**Acceptance criteria:**

1. Rules and thresholds are loaded from a TOML configuration file. Changing a threshold requires no code change.
2. Each rule evaluation produces one of `triggered`, `not_triggered`, or `not_evaluable`. `not_evaluable` (e.g. missing inputs) is never reported as `not_triggered`.
3. Every triggered indicator includes: rule ID, rule name, the condition and threshold applied, the actual values, severity, and references to the supporting field IDs and metric IDs.
4. No overall score, rating, grade, approval, or rejection is produced.
5. The configuration file's SHA-256 hash is recorded in the run manifest.

### FR-009 — Draft credit memo creation (Must)

**Behaviour:** the system assembles the memo described in Section K.

**Acceptance criteria:**

1. Sections K.1–K.9 are always present, in order. When a section has no content, it says so (e.g. "No risk indicators triggered by the configured rules").
2. Every factual statement carries one origin label: `[SOURCE]`, `[CALCULATED]`, `[RULE]`, `[AI INTERPRETATION]`, `[ANALYST-PROVIDED]`, or `[UNVERIFIED]`.
3. Factual sections are produced by a deterministic template from structured data. The LLM is not used to state figures.
4. Optional LLM narrative (Should) receives only verified structured data, never raw document text. It must cite field, metric, or rule IDs. It passes a deterministic post-check: every number in the narrative must equal a known value (after display rounding), and every cited ID must exist. Sentences that fail are removed, and the memo notes how many were removed. `--no-narrative` disables the LLM narrative entirely.
5. The memo header states that it is a **draft for human review** and not a credit decision.

### FR-010 — Markdown export (Must)

**Behaviour:** results are written to an output directory per run.

**Acceptance criteria:**

1. Outputs are `memo.md`, `results.json` (fields, metrics, indicators, evidence), and `manifest.json` (see FR-012), written to `<output_dir>/<run_id>/`.
2. `memo.md` renders correctly as CommonMark: headings, tables, and block quotes for evidence.
3. Files are written atomically (write to a temporary file, then rename) so a failed run never leaves a file that looks complete.
4. Existing run directories are never overwritten.

### FR-011 — Error handling and processing status (Must)

**Behaviour:** the pipeline progresses through explicit states and fails safely.

**States:** `received → validated → text_extracted → fields_extracted → validated_fields → calculated → rules_evaluated → memo_generated → exported`, or `failed` (with stage and error code).

**Acceptance criteria:**

1. Each stage transition is logged with a timestamp. The final state is recorded in the manifest.
2. A documented error catalogue (input, extraction, LLM, configuration, and export errors) maps each failure to a code, a user-facing message, and a non-zero CLI exit code.
3. LLM/API failures (timeout, rate limit, 5xx) are retried with exponential backoff, up to a configured limit (default 3 attempts). After that the run fails with `E-LLM-UNAVAILABLE`. Authentication failures are not retried (`E-LLM-AUTH`).
4. Error messages never include API keys, document text or quotes, or stack traces at the default log level.
5. Partial field extraction does **not** fail the run. Missing fields flow through as `not_found`, and the memo reports them. The run fails only when it cannot produce a trustworthy memo at all (e.g. invalid input, no LLM response).
6. Every catalogued failure scenario has an automated test (SC-09).

### FR-012 — Logging and reproducibility (Must)

**Behaviour:** every run is reproducible and auditable.

**Acceptance criteria:**

1. `manifest.json` records: run ID, timestamps, input file name and SHA-256, page count, candidate pages, code version (git commit hash, and whether the working tree is dirty), package versions, LLM provider and model ID, prompt version, schema version, rules-config hash, cache hits and misses, token usage, estimated cost, final state, and error code if any.
2. Re-running with the same input, configuration, code version, and cached LLM responses produces byte-identical `results.json` and `memo.md`, excluding timestamps and run ID, which are confined to the manifest and the memo header.
3. Logging uses the Python standard library `logging` module. At the default `INFO` level, logs contain stage events, counts, durations, and identifiers — not document text, quotes, or financial values. Those appear only at `DEBUG`, which is documented as unsuitable for sensitive data.
4. LLM temperature is set to 0 (or the provider's most deterministic setting). Reproducibility relies on the response cache, not on model determinism, which is not guaranteed.

---

## H. Financial Data Schema

### H.1 Extracted field structure

Proposed Pydantic model (illustrative; final names are set during Phase 2):

| Attribute | Type | Description |
|---|---|---|
| `field_id` | string | Stable ID, e.g. `revenue.FY2025.consolidated`. |
| `field_name` | enum | One of the names in H.3. |
| `value` | Decimal or null | Normalised value in base currency units (scale applied). Null unless status is `extracted`. |
| `raw_value` | string or null | The value exactly as printed, e.g. `(1,234.5)`. |
| `currency` | ISO 4217 code or null | e.g. `INR`, `USD`, `AED`. |
| `scale` | enum | `units`, `thousands`, `lakh`, `millions`, `crore`, `billions`, as declared in the document. |
| `period_end` | date | Period end date, e.g. `2025-03-31`. |
| `period_length_months` | int | 12 for annual periods (Release 1 supports 12 only). |
| `period_role` | enum | `current` or `comparative`. |
| `statement_basis` | enum | `consolidated`, `standalone`, or `unknown`. |
| `source_document` | object | File name and SHA-256. |
| `page_number` | int | 1-based physical page. |
| `page_label` | string or null | Printed page label, if available. |
| `evidence_quote` | string | Verbatim quote from the page. |
| `line_item_label` | string | The label as printed, e.g. "Revenue from operations". |
| `status` | enum | See H.2. |
| `status_reason` | enum or null | e.g. `evidence_not_verified`, `value_not_in_evidence`, `scale_unknown`, `period_mismatch`. |
| `validation` | object | Deterministic check results: `evidence_verified`, `value_in_evidence`, `scale_detected`, `currency_detected`, `period_matched`. |
| `candidates` | list | For `conflicting` fields: every candidate value with its own evidence. |
| `corroborating_evidence` | list | Additional consistent occurrences (see H.4). |

**Confidence:** the system does **not** use LLM self-reported confidence scores. They are not calibrated and could mislead reviewers. Trust is expressed through the deterministic `validation` checks and the `status`.

### H.2 Statuses

| Status | Meaning | Used in calculations? |
|---|---|---|
| `extracted` | A value was found, and its evidence and value were verified on the cited page, with scale, currency, and period determined. | Yes |
| `not_found` | No value was found in the provided pages. | No — dependent metrics undefined |
| `conflicting` | Two or more verified occurrences disagree beyond tolerance (H.4). | No — dependent metrics undefined |
| `requires_review` | A value was proposed but failed a verification or normalisation check, or is ambiguous (e.g. unknown scale or basis). | No — dependent metrics undefined |

### H.3 Release 1 field set

Each field is extracted for the current and comparative periods.

| Field | Description / typical labels | Notes |
|---|---|---|
| `revenue` | Revenue from operations; Revenue; Turnover | Excludes "other income". "Total income" is **not** revenue. |
| `net_profit` | Profit/(loss) for the year | Total profit for the period, after tax, before attribution to non-controlling interests. |
| `operating_profit` | Operating profit; EBIT (if reported) | Optional. Used for EBIT if present. |
| `profit_before_tax` | Profit/(loss) before tax | Used to derive EBIT. |
| `interest_expense` | Finance costs; Interest expense | See MET-05 limitations (I.2). |
| `current_assets` | Total current assets | |
| `current_liabilities` | Total current liabilities | |
| `total_borrowings` | Borrowings (non-current + current, including current maturities of long-term debt) | Lease liabilities excluded by default (I.4). If only components are reported, they are summed in Python, recording each component's evidence. |
| `total_equity` | Total equity | |

Document-level attributes, extracted once with evidence: `entity_name`, `reporting_currency`, `scale`, `statement_basis`, `period_end` (current and comparative).

### H.4 Handling duplicates, units, periods, and conflicts

1. **Duplicates.** The same field, period, and basis may appear on several pages (e.g. highlights page and balance sheet). If the values agree after normalisation, they are a single field. Evidence from the primary statement page is the main evidence, and other occurrences are kept as `corroborating_evidence`.
2. **Rounding tolerance.** Values that differ only through presentation rounding (e.g. `1,234.56 crore` in the statement vs `1,235 crore` in highlights) are treated as consistent when the more precise value rounds to the less precise one at its stated precision. The more precise value is used.
3. **Inconsistent units/scale.** Every value is normalised to base units using the scale declared on its page (e.g. "₹ in crore", "USD '000"). If the scale cannot be determined for a value, its status is `requires_review` (`scale_unknown`). Lakh = 10^5 and crore = 10^7.
4. **Currency.** If fields needed for a single metric are in different currencies, the metric is undefined (`currency_mismatch`). Release 1 performs **no** currency conversion.
5. **Different reporting periods.** Only 12-month periods are supported. A field whose period cannot be matched to the document's current or comparative period end is `requires_review` (`period_mismatch`). Metrics never combine fields from mismatched periods.
6. **Conflicting statements.**
   - Consolidated and standalone figures are **different facts, not conflicts**. The analyst selects the basis by configuration (default: consolidated). Fields from the other basis are ignored, and the memo notes that both were present.
   - If the basis cannot be determined, the field is `requires_review` (`basis_unknown`).
   - Genuine disagreements within one basis and period, beyond rounding tolerance, are `conflicting`, and every candidate is listed with evidence.
   - Restated comparatives are noted if the document labels them as restated. Release 1 processes one document, so cross-document restatement is out of scope.
7. **No guessing.** The system never fills a missing value, averages conflicting values, picks the "most likely" candidate, or infers a value from narrative text without verifiable evidence.

---

## I. Financial Calculations

### I.1 Principles

- All arithmetic is done in Python using `decimal.Decimal`. The LLM never performs arithmetic.
- Inputs must have status `extracted`, or be derived deterministically from `extracted` inputs, and must share currency, basis, and period length.
- Every result is either a value or an explicit undefined status with one of these reason codes: `missing_input`, `input_conflicting`, `input_requires_review`, `zero_denominator`, `non_positive_base`, `not_meaningful_negative_equity`, `not_applicable_no_interest`, `currency_mismatch`, `period_mismatch`.
- Results are labelled `[CALCULATED]` and reference their input field IDs.

**Derived input — EBIT.** If `operating_profit` is `extracted`, EBIT = `operating_profit`. Otherwise EBIT = `profit_before_tax + interest_expense`, computed in Python with both inputs recorded. The memo states which method was used.

### I.2 Metrics

#### MET-01 — Revenue growth

- **Formula:** (revenue_current − revenue_comparative) ÷ revenue_comparative × 100.
- **Inputs:** `revenue` (current and comparative), the same basis and currency, and consecutive 12-month periods.
- **Unit:** percent.
- **Edge cases:**
  - comparative revenue = 0 → undefined (`zero_denominator`);
  - comparative revenue < 0 → undefined (`non_positive_base`);
  - current revenue < 0 → `requires_review` on the input;
  - either input missing → undefined (`missing_input`).
- **Acceptance tests:**
  - 100 → 110 gives 10.0%;
  - 100 → 90 gives −10.0%;
  - 0 → 50 is undefined (`zero_denominator`);
  - a missing comparative is undefined (`missing_input`).
- **Limitations:** does not separate acquisitions, disposals, currency effects, or changes in accounting policy. A single-year change may be noisy.

#### MET-02 — Net profit margin

- **Formula:** net_profit ÷ revenue × 100, for the same period.
- **Inputs:** `net_profit`, `revenue`.
- **Unit:** percent.
- **Edge cases:**
  - revenue = 0 → undefined (`zero_denominator`);
  - revenue < 0 → undefined (`non_positive_base`);
  - negative net profit gives a valid negative margin.
- **Acceptance tests:**
  - 10 / 200 gives 5.0%;
  - −10 / 200 gives −5.0%;
  - revenue 0 is undefined.
- **Limitations:** distorted by one-off items, discontinued operations, and minority interests. It is not comparable across industries.

#### MET-03 — Current ratio

- **Formula:** current_assets ÷ current_liabilities.
- **Inputs:** `current_assets`, `current_liabilities`, from the same balance-sheet date.
- **Unit:** ratio (×).
- **Edge cases:**
  - current liabilities = 0 → undefined (`zero_denominator`);
  - a negative input → `requires_review` on that input, because a negative balance-sheet total is implausible.
- **Acceptance tests:**
  - 150 / 100 gives 1.50;
  - 80 / 100 gives 0.80;
  - 100 / 0 is undefined.
- **Limitations:** a point-in-time measure that is sensitive to working-capital timing and to window dressing. It ignores the liquidity quality of inventory and receivables.

#### MET-04 — Debt-to-equity ratio

- **Formula:** total_borrowings ÷ total_equity.
- **Inputs:** `total_borrowings`, `total_equity`, from the same balance-sheet date.
- **Unit:** ratio (×).
- **Edge cases:**
  - equity = 0 → undefined (`zero_denominator`);
  - equity < 0 → undefined (`not_meaningful_negative_equity`), which is itself surfaced by RI-004;
  - borrowings = 0 gives 0.00 (valid);
  - borrowings not found → undefined (`missing_input`), with **no** substitution of total liabilities.
- **Acceptance tests:**
  - 200 / 100 gives 2.00;
  - 0 / 100 gives 0.00;
  - 50 / −10 is undefined (negative equity).
- **Limitations:** "debt" is defined differently across institutions (with or without lease liabilities, or using total liabilities). Release 1 uses interest-bearing borrowings excluding leases. This is a configurable, documented choice, not a standard.

#### MET-05 — Interest coverage ratio

- **Formula:** EBIT ÷ interest_expense.
- **Inputs:** EBIT (I.1) and `interest_expense`, for the same period.
- **Unit:** ratio (×).
- **Edge cases:**
  - interest expense = 0 → undefined (`not_applicable_no_interest`);
  - negative EBIT gives a valid negative ratio, flagged by RI-005;
  - negative interest expense → `requires_review`.
- **Acceptance tests:**
  - 300 / 100 gives 3.00;
  - −50 / 100 gives −0.50;
  - 300 / 0 is undefined (not applicable).
- **Limitations:** "finance costs" may include lease interest, unwinding of discounts, and FX differences, so it may not equal cash interest. EBIT derived from PBT inherits any one-off items.

### I.3 Period comparison

- Comparison-based rules (RI-001, RI-003, RI-004) need each metric for both the current and the comparative period.
- If either is undefined, the comparison is undefined, and the rule is `not_evaluable`.

### I.4 Configurable definitions

These are recorded in the run manifest:

- statement basis (default `consolidated`);
- whether lease liabilities are included in borrowings (default `false`).

### I.5 Testing

- Each metric has table-driven unit tests covering all edge cases above.
- Property-style tests (e.g. scaling both inputs by the same factor leaves a ratio unchanged) are a Should.

---

## J. Risk Indicator Rules

### J.1 Rules engine design

- Rules are declared in `config/risk_rules.toml`, read with Python's standard-library `tomllib`, so no extra dependency is needed.
- Each rule has: `id`, `name`, `description`, `inputs` (metric or field IDs), `condition`, `thresholds`, `severity`, `enabled`.
- Rule logic is implemented as small, named, unit-tested Python functions. Configuration supplies parameters, not code. No `eval` or expression language is used.
- **Severity levels:** `info`, `watch`, `elevated`. These describe how urgently a human should look, **not** creditworthiness.
- Each evaluation produces `triggered`, `not_triggered`, or `not_evaluable`, along with the values used, the threshold, and the evidence references.

### J.2 Thresholds are provisional

> **The default thresholds below are illustrative placeholders chosen for demonstration and testing. They are NOT universal banking standards, regulatory requirements, or the policy of any institution.** Real thresholds vary by institution, industry, borrower size, and product, and must be set by the institution's credit policy. The memo states this wherever thresholds are shown.

### J.3 Release 1 rules

| ID | Name | Condition (provisional defaults) | Severity | Not evaluable when |
|---|---|---|---|---|
| RI-001 | Declining revenue | Revenue growth < 0% → `watch`; ≤ −10% → `elevated` | watch / elevated | MET-01 undefined |
| RI-002 | Negative net profit | Current-period `net_profit` < 0 | elevated | `net_profit` not `extracted` |
| RI-003 | Deteriorating liquidity | Current ratio < 1.00 (current period) → `elevated`; **or** current ratio fell by ≥ 10% relative to the comparative period → `watch` | watch / elevated | MET-03 undefined for the required period(s) |
| RI-004 | Increasing leverage | D/E rose by ≥ 20% relative to the comparative period → `watch`; D/E > 2.00 → `elevated`; equity ≤ 0 (either period) → `elevated` with reason "negative or zero equity" | watch / elevated | Borrowings or equity not `extracted` |
| RI-005 | Weak interest coverage | ICR < 1.50 → `watch`; ICR < 1.00 (incl. negative) → `elevated` | watch / elevated | EBIT or interest expense not `extracted`; `not_applicable_no_interest` → `not_triggered` with note |
| RI-006 | Missing financial information | Any H.3 field required by MET-01–MET-05 is `not_found` | info | Never (always evaluable) |
| RI-007 | Conflicting source values | Any field is `conflicting` or `requires_review` | watch | Never (always evaluable) |

When a rule has two severity tiers and both conditions are met, the higher severity is reported, and both conditions are listed.

### J.4 Indicator explanation format

Each triggered indicator renders as follows (illustrative):

> **RI-003 Deteriorating liquidity — elevated** `[RULE]`
> Condition: current ratio < 1.00 (provisional threshold, configurable).
> Observed: current ratio FY2025 = 0.84 `[CALCULATED: MET-03.FY2025]` from current assets 840.0 crore `[SOURCE: p.112]` ÷ current liabilities 1,000.0 crore `[SOURCE: p.112]`.

### J.5 Decision boundary

The system **must not** approve, reject, rate, grade, or score a borrower. It must not state or imply that a credit decision has been made or validated. Indicators are prompts for human investigation only.

---

## K. Credit Memo Output

### K.0 Memo header and labelling

The header contains:

- title, borrower name, document(s) reviewed, run ID, generation timestamp;
- the statement: **"DRAFT — generated for human review. Not a credit decision. Verify all figures against the cited sources."**;
- a legend for origin labels.

| Label | Meaning |
|---|---|
| `[SOURCE: p.N]` | A value or quote taken verbatim from the document and verified on page N. |
| `[CALCULATED: MET-xx]` | Computed deterministically by the platform from source values. |
| `[RULE: RI-xxx]` | Produced by a configured risk rule. |
| `[ANALYST-PROVIDED]` | Supplied in the (synthetic) borrower profile input; not verified against the document. |
| `[AI INTERPRETATION]` | LLM-written commentary based only on the items above. Not a verified fact. |
| `[UNVERIFIED]` | A statement that could not be traced to evidence. Shown only with this label. |

### K.1–K.9 Sections

| # | Section | Content | Produced by |
|---|---|---|---|
| 1 | Borrower overview | Entity name, reporting currency, scale, statement basis, period ends `[SOURCE]`. Industry, facility requested, and other profile details `[ANALYST-PROVIDED]`. | Template |
| 2 | Documents reviewed | File name, SHA-256, page count, candidate pages used, extraction date. | Template |
| 3 | Financial performance | Table of extracted fields for both periods, with status and page references. Optional short commentary `[AI INTERPRETATION]` (FR-009.4). | Template (+ optional LLM) |
| 4 | Financial ratios | Table of MET-01–MET-05 with values or undefined reasons, formulas, and inputs. | Template |
| 5 | Potential risk indicators | Triggered indicators (J.4 format), then `not_evaluable` rules with reasons. The provisional-threshold notice. | Template |
| 6 | Evidence and source references | One entry per field ID: page, page label, line-item label, and verbatim quote. | Template |
| 7 | Missing information and conflicts | Every `not_found`, `conflicting`, and `requires_review` field, with reasons and candidate evidence. | Template |
| 8 | Questions for the credit analyst | Deterministic questions generated from sections 5 and 7 (e.g. "Revenue FY2024 not found on pages 110–115 — confirm the figure from the audited statements"). Optional LLM-suggested questions labelled `[AI INTERPRETATION]`. | Template (+ optional LLM) |
| 9 | Limitations and human-review requirements | Fixed text: scope limits (text-based PDF, single document, no OCR, no currency conversion), metric limitations, provisional thresholds, LLM extraction limitations, and the statement that a qualified human must review and decide. | Template |

### K.10 Traceability rule

Material factual claims are numbers, dates, entity names, and statements about the presence or absence of items. Each one must carry a `[SOURCE]`, `[CALCULATED]`, `[RULE]`, or `[ANALYST-PROVIDED]` label that resolves to an ID in `results.json`. Otherwise it must be labelled `[UNVERIFIED]`. Automated tests check that every label in a generated memo resolves to an existing ID.

---

## L. Technical Architecture

### L.1 Approach

Release 1 is a **single-process, modular Python 3.12 package with a CLI**. It is a linear pipeline of plain functions, with no agent framework, web server, database, or queue. Each stage has typed inputs and outputs (Pydantic models), so each one can be tested in isolation.

### L.2 Technology evaluation

| Technology | Release 1? | Role / rationale | When it becomes necessary |
|---|---|---|---|
| Python 3.12 | Yes | Project standard (`CLAUDE.md`). | Already in place. |
| uv | Yes | Dependency, lockfile, and environment management. | Already in place. |
| Git | Yes | Version control. | Already in place. |
| pytest | Yes (dev) | Test runner. | Already in place. |
| Pydantic v2 | Yes | Schema validation for LLM output and inter-stage data; generates JSON schema for structured outputs. | Phase 2. |
| pdfplumber (MIT) | Yes | Page-level text extraction, behind a replaceable `TextExtractor` interface. See D-01. | Phase 1. |
| OpenAI Python SDK | Yes | Field extraction and optional narrative, behind a `LLMProvider` interface with a fake implementation for tests. See D-02. | Phase 2. |
| `tomllib`, `decimal`, `logging`, `hashlib`, `json`, `argparse` | Yes (stdlib) | Configuration, arithmetic, logging, hashing, output, CLI. No added dependencies. | — |
| FastAPI | No | REST API and web interface. | Phase 6, when a non-CLI client exists. |
| PostgreSQL + pgvector | No | Persistent storage and vector search for the compliance RAG assistant. | Phase 8, if the RAG assistant is built. Release 1 stores runs as files. |
| LangChain | No | Not required. A thin provider interface is simpler and easier to test. | Reconsider only if multiple retrieval or tool integrations make it pay for itself. |
| LangGraph | No | Not required. The Release 1 workflow is linear. | Phase 8, if workflows need branching, loops, or durable human-in-the-loop checkpoints. |
| Docker | No | Reproducible deployment. | Phase 7. |
| Cloud hosting | No | Demonstration deployment. | Phase 7. |

### L.2.1 Decision records

**D-01 — PDF extraction library: pdfplumber (decided 2026-10-12)**

- **Choice:** `pdfplumber`, licensed under the **MIT licence**, for page-level text extraction in Release 1.
- **Why:** a permissive licence keeps future commercial or enterprise use open. PyMuPDF was considered but rejected, because its AGPL-3.0 licence would require either open-sourcing derived work or buying a commercial licence.
- **Trade-offs accepted:**
  - It is slower than PyMuPDF. This should be acceptable within the FR-001 page limits, and SC-10 will measure it.
  - Printed page labels may not be exposed. FR-002 already treats page labels as optional ("where available"). Physical page numbers are always recorded.
- **Replaceability:** all PDF access goes through the `TextExtractor` interface in the `ingestion` module. No other module imports pdfplumber, so the library can be swapped without changing downstream code or tests beyond the extractor's own.
- **Verification required:** financial **table extraction must be tested against representative PDFs**, both synthetic fixtures and selected public annual reports. Those PDFs should include multi-column statements, current and comparative columns, bracketed negatives, and Indian digit grouping. Text order and column alignment are known weak points of PDF text extraction. If testing shows unacceptable results, layout-aware options (e.g. pdfplumber table APIs or word-position extraction) are evaluated before considering a different library.
- **At install time (Phase 1):** confirm the installed version, and confirm the licences of its transitive dependencies (e.g. `pdfminer.six`, `pypdfium2`), recording them in `PROGRESS.md`.

**D-02 — LLM provider: OpenAI API; proposed baseline model `gpt-4o-mini` (decided 2026-10-12)**

- **Choice:** the OpenAI API as the initial `LLMProvider` implementation. `gpt-4o-mini` is the **proposed** baseline model.
- **Subject to verification:** model availability, structured-output support, and current pricing must be checked against OpenAI's documentation when Phase 2 begins. Any change of model is recorded in `PROGRESS.md`. SC-11's cost target is re-checked against the verified pricing.
- **Configurability:** provider and model ID are configuration values (`config/settings.toml`, overridable by environment variable), never hard-coded in modules. Both are recorded in every run manifest (FR-012.1) and are part of the response-cache key (FR-003.5).
- **Structured output:** extraction uses the provider's JSON-schema structured-output mode where the chosen model supports it. Pydantic validation (FR-004) still applies to every response regardless.
- **Credentials:** the API key is read from the `OPENAI_API_KEY` environment variable (SEC-02, SEC-03). It is never committed, logged, or written to outputs.
- **Data restriction:** only public or synthetic financial data may be sent to the hosted API (SEC-10).
- **Testing:** the default test suite uses the fake provider and makes no API calls. Live calls are opt-in only (O.1).

### L.3 Module responsibilities

| Module (proposed) | Responsibility |
|---|---|
| `cli` | Parse arguments, invoke the pipeline, map errors to exit codes. |
| `config` | Load and validate settings and the rules TOML; expose limits and defaults. |
| `pipeline` | Orchestrate stages, track processing state, write the manifest. |
| `ingestion` | File validation (FR-001), page text extraction (FR-002), statement-page locator. |
| `llm` | `LLMProvider` interface, OpenAI provider implementation (D-02), a fake provider, retry/backoff, response cache, token/cost accounting. |
| `extraction` | Prompt construction (versioned prompts), structured-output parsing and validation (FR-003, FR-004). |
| `evidence` | Quote and value verification, normalisation of numbers, scale, and currency, reconciliation of duplicates and conflicts (FR-005, FR-006). |
| `models` | Pydantic models: fields, metrics, indicators, run manifest. |
| `calculations` | Pure metric functions (FR-007). |
| `risk` | Rules engine and rule functions (FR-008). |
| `memo` | Memo assembly, origin labelling, optional narrative post-check (FR-009). |
| `export` | Atomic writing of `memo.md`, `results.json`, `manifest.json` (FR-010). |

### L.4 Information flow

```
PDF file
  │  ingestion.validate            → FileInfo (hash, pages)              [FR-001]
  │  ingestion.extract_pages       → list[PageText]                       [FR-002]
  │  ingestion.locate_statements   → candidate pages
  ▼
llm + extraction                   → raw LLM JSON → validated ExtractionResult  [FR-003/004]
  ▼
evidence.verify / reconcile        → list[FinancialField] with statuses   [FR-005/006]
  ▼
calculations                       → list[MetricResult]                   [FR-007]
  ▼
risk                               → list[IndicatorResult]                [FR-008]
  ▼
memo                               → Memo (structured) → Markdown text    [FR-009]
  ▼
export                             → memo.md, results.json, manifest.json [FR-010/012]
```

Only the `llm` module makes network calls. Every stage after extraction is deterministic.

---

## M. Security and Privacy

| ID | Requirement |
|---|---|
| SEC-01 | **Public and synthetic data only.** The prototype processes only publicly available financial statements and synthetic borrower data. No real customer or confidential data. |
| SEC-02 | **API keys via environment variables** (optionally loaded from a local `.env`). Keys are never hard-coded, logged, written to outputs, or included in error messages. |
| SEC-03 | **`.env` excluded from Git** (already in `.gitignore`). An `.env.example` with placeholder names only may be committed. |
| SEC-04 | **File type and size validation** before parsing (FR-001). Validation is by content signature, not extension. |
| SEC-05 | **Safe error handling:** as specified in FR-011.2 and FR-011.4. |
| SEC-06 | **No execution of document content.** PDF JavaScript, embedded files, links, and form actions are ignored. Only text is extracted. Document text is never passed to `eval`, `exec`, shell commands, or template engines that execute code. |
| SEC-07 | **Prompt-injection containment.** Document text is placed in clearly delimited data sections of prompts. The LLM has no tools, no network access, and no ability to take actions. Its output is constrained to a schema and verified against source text. Instructions inside documents therefore cannot change system behaviour beyond producing values that verification rejects. |
| SEC-08 | **Minimal sensitive logging:** no document text, quotes, or financial values at `INFO` level or above (FR-012.3). |
| SEC-09 | **Human approval for consequential decisions:** the system produces drafts only. No credit decision, AML filing, or external action is taken automatically. |
| SEC-10 | **Data sent to the hosted LLM API (OpenAI, D-02):** only public or synthetic financial data may be sent. Real borrower, customer, or confidential data must never be sent. Requests are limited to candidate pages. OpenAI's API data-usage and retention terms are reviewed and recorded in `PROGRESS.md` before the first live call in Phase 2. |
| SEC-11 | **Dependency hygiene:** dependencies are pinned via `uv.lock`, and new dependencies require a documented reason. |

---

## N. Non-Functional Requirements

| ID | Quality | Requirement |
|---|---|---|
| NFR-01 | Accuracy | Meets the SC-01 to SC-08 targets on the evaluation set before Release 1 is declared complete, or the shortfall is documented with analysis. |
| NFR-02 | Traceability | Every value in the memo resolves to a field, metric, or rule ID. Every field resolves to document, page, and quote (FR-005, K.10). |
| NFR-03 | Reliability | Transient LLM failures are retried (FR-011.3). Partial extraction degrades gracefully. No crash produces output that looks complete. |
| NFR-04 | Maintainability | Small modules with single responsibilities. Type hints throughout. Configuration is separate from code. Each new dependency is justified in `PROGRESS.md`. |
| NFR-05 | Testability | Every module is testable without network access. The LLM is behind an interface with a fake implementation. Calculation and rule functions are pure. |
| NFR-06 | Reproducibility | Same inputs, configuration, code, and cache give identical outputs (FR-012.2). Dependencies are locked with `uv.lock`. |
| NFR-07 | Security | Section M requirements are met and tested where testable. |
| NFR-08 | Performance | Meets the SC-10 target. Text extraction and all deterministic stages complete in seconds for documents within limits. |
| NFR-09 | Cost control | Only candidate pages are sent to the LLM. Responses are cached. Token usage and estimated cost are recorded per run. A configurable per-run token ceiling aborts with `E-LLM-BUDGET-EXCEEDED` before overspending. |

---

## O. Testing and Evaluation

### O.1 Automated tests

| Level | Scope | Examples |
|---|---|---|
| Unit | Pure functions and models | Metric edge cases (Section I); rule trigger and threshold boundaries (exactly at threshold); number parsing (`(1,234)`, `1,23,456` Indian grouping); scale normalisation; quote verification; schema validation. |
| Integration | Pipeline stages with a **fake LLM provider** and small synthetic PDFs in `tests/fixtures/` | End-to-end run produces `memo.md`, `results.json`, and `manifest.json`; every catalogued error code is triggered; missing and conflicting values flow to the memo. |
| Regression | Golden outputs | A fixed synthetic PDF plus recorded LLM responses produce byte-identical `results.json` and `memo.md` (excluding timestamps). Any intended change updates the golden files in a reviewed commit. |
| Live (opt-in) | Real LLM provider | Marked and skipped by default (e.g. `pytest -m live`). Never run in the default suite, so `uv run pytest tests/ -q` needs no network or API key. |

Every behaviour is recorded in `tests/BEHAVIOURS.md` with its test and status, per `CLAUDE.md`.

### O.2 Evaluation dataset plan

- **Synthetic documents (planned: ~10):** generated programmatically from known ground-truth values. They cover clean statements, missing fields, conflicting values between highlights and statements, mixed scales, negative equity, zero interest, losses, consolidated plus standalone, and a document containing prompt-injection text. Ground truth is known by construction. A PDF-generation tool (e.g. a dev-only dependency) is chosen in Phase 2 and justified at that time.
- **Public documents (planned: ~5):** publicly available annual reports of non-financial companies, with varied layouts and currencies (including INR with lakh/crore scales). Ground truth (value, page, quote) is **labelled manually and double-checked** by the developer. Public PDFs are **not committed** (licensing and repository size). The dataset stores source URL, retrieval date, SHA-256, and the labels.
- **Format:** one ground-truth JSON per document under `tests/eval/` (labels only), validated by the same Pydantic models.

> **Uncertainty:** the specific public documents are not yet selected, and dataset sizes are planning estimates. Small datasets give wide uncertainty on percentage metrics, so results will be reported with counts (e.g. "43/46 fields"), not just percentages.

### O.3 Evaluation metrics and measurement

| Measure | Method |
|---|---|
| Extraction accuracy (SC-01) | Compare normalised values, scale, currency, and period to ground truth. |
| Hallucinated values (SC-02) | Count `extracted` fields with no ground-truth counterpart. |
| Not-found correctness (SC-03) | Ground-truth absent fields vs system status. |
| Evidence correctness (SC-04, SC-05) | Automated verification rate. Cited page vs ground-truth page(s). |
| Calculation accuracy (SC-06) | Unit test pass rate over the specified cases. |
| Rule correctness (SC-07) | Unit test pass rate over the specified cases. |
| Unsupported claims (SC-08) | Automated label-resolution check, plus manual review of each evaluation memo using a checklist. |
| Failure rates (SC-09) | Error-scenario test pass rate. Run failure rate over the evaluation set. |
| Latency (SC-10) | Per-stage and end-to-end timings from the manifest. |
| Cost (SC-11) | Token usage × the provider's published price at measurement time, recorded with the date. |

The evaluation harness writes a dated report. **No performance claim is made in documentation, README, or memo until it is backed by a recorded evaluation report.**

---

## P. Repository Structure

Proposed structure. Existing files are marked ✓. Nothing else is created until its phase.

```
ai-credit-intelligence/
├── CLAUDE.md                 ✓ Project rules for humans and AI assistants
├── PROGRESS.md               ✓ Phase checklist, decisions log, evaluation results
├── pyproject.toml            ✓ uv project definition and dependencies
├── uv.lock                   ✓ Locked dependency versions
├── .python-version           ✓ Python 3.12 pin
├── .gitignore                ✓ Excludes secrets, venvs, caches, private documents
├── .env.example                Placeholder environment variable names (Phase 2)
├── config/
│   ├── settings.toml           Limits, defaults, basis, LLM model ID (Phase 1–2)
│   └── risk_rules.toml         Risk rules and provisional thresholds (Phase 4)
├── prompts/                    Versioned prompt templates (Phase 2)
├── docs/
│   ├── PRD.md                ✓ This document
│   └── decisions/              Short architecture decision records, as needed
├── src/
│   └── credit_intel/           Application package (src layout; build backend added in Phase 1)
│       ├── cli.py
│       ├── config.py
│       ├── pipeline.py
│       ├── models.py
│       ├── ingestion/
│       ├── llm/
│       ├── extraction/
│       ├── evidence/
│       ├── calculations/
│       ├── risk/
│       ├── memo/
│       └── export/
├── tests/
│   ├── BEHAVIOURS.md         ✓ Expected behaviours ↔ tests ↔ status
│   ├── test_placeholder.py   ✓ Removed when the first real test exists
│   ├── unit/
│   ├── integration/
│   ├── regression/             Golden outputs
│   ├── fixtures/               Synthetic PDFs and recorded LLM responses (committed)
│   └── eval/                   Ground-truth labels and the evaluation harness
└── runs/                       Run outputs (git-ignored; added to .gitignore in Phase 1)
```

**Roles of tracking files:**

- `CLAUDE.md` governs *how* work is done.
- This PRD defines *what* is built.
- `PROGRESS.md` records *what has been done*, decisions, and measured results.
- `tests/BEHAVIOURS.md` maps each expected behaviour to its test and current status.

---

## Q. Development Phases

Each phase ends with a review by the project owner before the next begins (Section U).

| Phase | Goal | Entry conditions | Acceptance criteria (exit) |
|---|---|---|---|
| **0 — Setup and specification** | Repository, tooling, PRD | — | Git, uv, Python 3.12, and pytest in place. `CLAUDE.md`, `PROGRESS.md`, and `BEHAVIOURS.md` exist. PRD reviewed and approved. |
| **1 — PDF ingestion and extraction** | FR-001, FR-002 | Phase 0 approved (including D-01). | pdfplumber is wrapped by the `TextExtractor` interface. Validation rejects every invalid case with the correct code. Page text extraction is deterministic and preserves page numbers. Statement-table text extraction has been checked against representative PDFs (D-01), with findings recorded. The statement locator ranks the correct pages on synthetic fixtures. All tests pass. Behaviours recorded. |
| **2 — Structured financial extraction** | FR-003 to FR-006 | Phase 1 approved. D-02 model availability and pricing verified. API data terms reviewed (SEC-10). `OPENAI_API_KEY` set in the local environment (not in Git). | Pydantic schema implemented. The fake provider supports offline tests. Evidence verification and reconciliation are fully unit-tested. Statuses are correct on synthetic fixtures. Response caching works. First small evaluation run recorded (counts, not claims). |
| **3 — Deterministic calculations** | FR-007 | Phase 2 approved (or the schema is stable enough to build calculations against fixtures). | All five metrics are implemented as pure functions. Every edge case in Section I is tested and passing. `Decimal` is used throughout. |
| **4 — Risk indicators** | FR-008 | Phase 3 approved. | Rules load from TOML. All seven rules are tested at, below, and above thresholds, plus `not_evaluable` cases. No scoring or decision output exists. |
| **5 — Credit memo generation** | FR-009 to FR-012 → **Release 1** | Phase 4 approved. | Release 1 Definition of Done (Section T) met in full. |
| **6 — Interface and API** | FastAPI service and simple web UI | Release 1 complete. | API exposes run submission and status/results. The same pipeline is reused. API tests pass. No new behaviour bypasses the evidence and labelling rules. |
| **7 — Evaluation, security, deployment** | Hardening and deployment | Phase 6 approved (or Release 1, if Phase 6 is deferred). | Expanded evaluation. Security review against Section M. Docker image builds and runs. Optional cloud demo deployed with secrets managed securely. |
| **8 — Optional extensions** | RAG assistant, LangGraph, AML support, authorised integrations | Phase 7 approved. A written justification exists for each extension. | Each extension has its own mini-PRD, acceptance criteria, and tests before implementation. |

---

## R. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Hallucinated values or claims** | Wrong figures presented as fact | Deterministic quote and value verification (FR-005). Template-generated factual sections. Narrative post-check (FR-009.4). Origin labels. `[UNVERIFIED]` label. SC-02 and SC-08 evaluation. |
| **Incorrect financial extraction** (wrong line item, period, or sign) | Wrong ratios and indicators | Field definitions with explicit inclusions and exclusions (H.3). Period and basis matching. Sign normalisation tests. Evaluation on labelled data. Analyst review of the evidence section. |
| **Table extraction errors** (columns merged or misaligned in text) | Values attributed to the wrong period | Value-in-quote check. Period-column labels required in the evidence. `requires_review` on ambiguity. Fixtures with multi-column layouts. Layout-aware extraction considered if evaluation shows a need. |
| **Inconsistent reporting periods** | Invalid comparisons | Explicit period matching. 12-month periods only. `period_mismatch` status. No cross-period metrics. |
| **Ambiguous ratio definitions** | Disagreement with analyst expectations | Documented definitions and limitations (Section I). Configurable choices recorded in the manifest. Memo shows formulas and inputs. |
| **API failures / rate limits** | Failed runs | Retries with backoff. Clear error codes. Response cache. Offline tests via the fake provider. |
| **Cost overruns** | Unexpected spend | Candidate-page selection. Caching. Per-run token ceiling. Cost recorded per run (NFR-09). |
| **Prompt injection via documents** | Manipulated output | Data-only treatment of document text. No tools or actions for the LLM. Schema-constrained output. Evidence verification. Injection fixture in the test set (SEC-07). |
| **Excessive architectural complexity** | Unfinished project, hard to explain | Linear pipeline. No agent frameworks, database, or web server in Release 1. Each new dependency needs a documented trigger (L.2). Phase reviews. |
| **Scope creep** | Release 1 delayed | Out-of-scope list (Section S). Future items held for Phases 6–8. |
| **Misinterpretation as a decision tool** | Inappropriate reliance | Draft disclaimers. No scores or decisions. Provisional-threshold notices. Limitations section in every memo. |
| **PDF library limitations** (pdfplumber text order, column alignment, speed) | Mis-attributed values, slower runs | Representative-PDF testing in Phase 1. Replaceable `TextExtractor` interface. Evidence verification catches mis-read values (D-01). |
| **Model availability or pricing changes** (`gpt-4o-mini`) | Broken runs or cost overrun | Model is configurable. Availability and pricing are verified at Phase 2 start. Cost is recorded per run (D-02, NFR-09). |

---

## S. Out of Scope (Release 1)

- Autonomous credit decisions, including approval, rejection, credit scores, ratings, grades, or pricing.
- Real customer, borrower, or confidential data.
- Integration with proprietary Azentio products or any other enterprise system without explicit authorisation.
- Regulatory certification or compliance claims (e.g. for model risk management or lending regulations).
- Automatic AML detection, filing, or reporting (e.g. suspicious activity reports).
- Training or fine-tuning machine-learning models.
- Complex multi-agent orchestration and agent frameworks.
- OCR of scanned documents; non-English documents; quarterly or interim periods; currency conversion; multi-document comparison.
- Financial-institution borrowers (banks, insurers, NBFCs).
- Web UI, REST API, database, Docker, and cloud deployment (planned for later phases).

---

## T. Definition of Done — Release 1

Release 1 is complete when **all** of the following are true and verified:

1. Given a supported financial PDF (Section F.1), the CLI produces `memo.md`, `results.json`, and `manifest.json`.
2. Every value in the memo is labelled by origin and resolves to evidence or a calculation or rule ID, or is labelled `[UNVERIFIED]`. The automated label-resolution test passes.
3. Missing, conflicting, and review-required values are identified and listed in the memo. None is silently resolved or used in calculations.
4. All five metrics and seven rules are implemented as specified, with every documented edge case tested.
5. Re-running with the same inputs, configuration, code version, and cached responses produces identical outputs (regression test passes).
6. Every catalogued error scenario has a passing test.
7. `uv run pytest tests/ -q` passes with no network access and no API key, and the result is reported truthfully.
8. An evaluation report exists with measured results against SC-01 to SC-11, presented as counts and percentages, with shortfalls explained. No unmeasured claims are made.
9. The memo's limitations section and the project README document scope, limitations, provisional thresholds, and the human-decision boundary.
10. `PROGRESS.md` and `tests/BEHAVIOURS.md` are up to date. The project owner has reviewed and approved the release.

---

## U. Development Governance

1. **Incremental implementation:** work proceeds phase by phase (Section Q). A phase does not start until the previous phase is reviewed and approved by the project owner.
2. **Small, reviewable changes:** each commit addresses one focused change, with a clear message (conventional-commit style, e.g. `feat:`, `fix:`, `test:`, `docs:`, `chore:`).
3. **Test coverage for meaningful changes:** behaviour changes come with tests. Behaviours are added to `tests/BEHAVIOURS.md` before or alongside implementation.
4. **Truthful reporting:** test and evaluation results are reported exactly as observed, including failures. A test is never reported as passing unless it was run.
5. **Documentation updates:** requirement changes update this PRD (with a version bump). Decisions are recorded in `PROGRESS.md` or `docs/decisions/`. `PROGRESS.md` is updated at the end of each change set.
6. **Dependency discipline:** dependencies are added only via `uv add`, only when their phase requires them, and with a recorded reason.
7. **Review gates:** the project owner reviews the PRD, each phase exit, and Release 1 completion.

---

## Appendix — Open Questions

| # | Question | Needed by | Status |
|---|---|---|---|
| OQ-1 | PDF extraction library and its licence. | Start of Phase 1 | **Resolved 2026-10-12:** pdfplumber (MIT) — see D-01. |
| OQ-2 | LLM provider and model. | Start of Phase 2 | **Resolved 2026-10-12:** OpenAI API, proposed baseline `gpt-4o-mini`, subject to verification — see D-02. |
| OQ-3 | Which public annual reports form the evaluation set. | Phase 2 | Open |
| OQ-4 | Tool for generating synthetic PDF fixtures (dev-only dependency). | Phase 1–2 | Open |
| OQ-5 | Whether lease liabilities should be included in borrowings by default for the demonstration. | Phase 3 | Open |
| OQ-6 | Whether an analyst override file (resolving conflicts with a recorded rationale) should enter Release 1 or wait for a later release. | Phase 5 planning | Open |

## Revision History

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-10-12 | Initial draft for project-owner review. |
| 0.2 | 2026-10-12 | Resolved OQ-1 (pdfplumber, D-01) and OQ-2 (OpenAI API, `gpt-4o-mini` proposed, D-02); updated SEC-10, phase entry criteria, and risks; removed duplicated text in SEC-05 and Phase 5 exit criteria (now references to FR-011 and Section T). |
