# Product Requirements Document — AI Credit Intelligence Platform

---

## A. Document Information

| Item | Value |
|---|---|
| Project name | AI Credit Intelligence Platform |
| Document | Product Requirements Document (PRD) |
| Version | 0.3 |
| Status | Approved v0.3 — **specification only** (2026-10-13). Approval covers what is to be built, not what exists. |
| Implementation status | Only FR-001 and FR-002 are implemented (Phase 1 commits 1–3); FR-002.3's fresh-process test is still planned. Everything else is specified but not implemented. The authoritative status is `PROGRESS.md` and `tests/BEHAVIOURS.md`. |
| Date | 2026-10-13 |
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
| Candidate page | A page selected by the statement locator (FR-013), or listed in an analyst-supplied page range, whose text is sent for field extraction. |
| Comparative period | The prior period presented alongside the current period in a financial statement. |
| Derived value | A value computed in Python from other fields (e.g. EBIT from profit before tax plus finance costs). It carries a derivation record instead of a quote (H.5). |
| Credit memo | A document summarising a borrower's financial position and risks to support a human credit decision. |
| D/E | Debt-to-equity ratio. |
| Deterministic | Same inputs always produce the same outputs; no randomness or LLM involvement. |
| EBIT | Earnings Before Interest and Tax. |
| Evidence | A verbatim quote from a specific page of a source document that supports an extracted value. |
| Field | A single named financial data point (e.g. `revenue`) for a single reporting period. |
| FR / NFR | Functional Requirement / Non-Functional Requirement. |
| ICR | Interest coverage ratio. |
| LLM | Large Language Model. |
| Held-out set | Evaluation documents never used to tune prompts, phrase lists, or thresholds; used only for reported results (O.2). |
| OCR | Optical Character Recognition (extracting text from images of text). |
| Page label | The PDF's page-label metadata (e.g. "iv", "45"), where the document defines it. Not the number printed in a page footer. |
| Period identifier | The ISO 8601 period-end date (e.g. `2025-03-31`) used in all field and metric IDs (H.1.1). "FY" labels are for display only. |
| Provenance | The traceable origin of a value: source document, page, and quote — or, for a derived value, the IDs of its inputs. |
| RAG | Retrieval-Augmented Generation. |
| Risk indicator | A rule-based, explainable flag highlighting a potential concern for human review. It is **not** a credit decision. |
| Run | One end-to-end processing of one document, identified by a run ID. |
| Scale | Multiplier in which figures are presented (units, thousands, millions, lakh, crore, billions). |
| Target | A provisional goal to be measured. Not an achieved result. |
| Tuning set | Evaluation documents that may be inspected and used to adjust prompts, phrase lists, and thresholds (O.2). |

---

## B. Executive Summary and Product Vision

The AI Credit Intelligence Platform helps credit analysts turn a company's financial statements (PDF) into an **evidence-backed draft credit memo**. It:

1. Extracts page-level text from a PDF.
2. Uses an LLM to locate and extract specific financial fields into a validated schema, each with a verbatim quote and page number.
3. Verifies that evidence deterministically against the source text, including the value's sign, period column, scale, and currency.
4. Calculates financial ratios with deterministic, tested Python code.
5. Applies a transparent, configurable rules engine to raise potential risk indicators.
6. Assembles a draft credit memo in Markdown from a deterministic template, in which every material fact is labelled by origin (source, calculation, rule, or analyst-provided) and is traceable to evidence or explicitly marked unverified.

**Who it serves:** credit analysts, lending teams, and credit risk analysts who review borrower financials.

**Business problem:** preparing a first-draft credit analysis is repetitive, manual, and error-prone. The platform reduces the mechanical work (finding figures, transcribing them, computing ratios, cross-checking) while leaving judgement and decisions to people.

**Vision statement:** *Make every number in a draft credit memo traceable to its source in one click, and never let an AI system invent a figure or make a credit decision.*

**Portfolio context:** Release 1 is a portfolio prototype that demonstrates practical AI engineering — document processing, structured LLM outputs, deterministic calculation, evidence traceability, automated testing, and reliable error handling. It uses only public documents and synthetic borrower data. It is **not** a production lending system.

### B.1 System at a glance

| Step | Module | Done by | Output | Stops the run when |
|---|---|---|---|---|
| 1. Validate PDF | `ingestion` | Deterministic code | File info with SHA-256 | Missing, too large, not a PDF, corrupt, encrypted, too many pages (FR-001) |
| 2. Extract page text | `ingestion` | Deterministic code (pdfplumber) | One text entry per physical page | No page has text (FR-001.6) |
| 3. Locate statements | `ingestion` | Deterministic keyword rules, or the analyst's page range | Candidate pages | Invalid page range (FR-013); configured statement basis not present (H.4.6) |
| 4. Extract fields | `llm`, `extraction` | **LLM** — reads and quotes only; no arithmetic | Proposed values, each with page and quote | No candidate pages; LLM unavailable or invalid output (FR-003, FR-004) |
| 5. Verify and reconcile | `evidence` | Deterministic code | Fields with statuses; unverifiable values become `requires_review` | — (unverifiable values are reported, not fatal) |
| 6. Derive and calculate | `calculations` | Deterministic code (`Decimal`) | Derived values with input records; five metrics | — (undefined results are reported, not fatal) |
| 7. Evaluate rules | `risk` | Deterministic configurable rules | Indicators: `triggered` / `not_triggered` / `not_evaluable` | — |
| 8. Draft memo and export | `memo`, `export` | Deterministic template | `memo.md`, `results.json`, `manifest.json` | Output cannot be written (FR-010) |
| 9. Review and decide | — | **Human analyst** | The credit judgement | — |

**What the system cannot conclude:**
- It never approves, rejects, rates or scores a borrower, and never states that a credit decision has been made (J.5).
- It never presents an unverified or conflicting value as fact.
- It never fills a missing value, never treats a blank as zero, and never mixes consolidated with standalone figures.

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
| Verifying quotes, values, sign, period column, scale, and currency against the cited page | Deterministic Python |
| Unit/scale normalisation, period alignment | Deterministic Python |
| Ratio calculation and derived values | Deterministic Python |
| Risk indicators | Deterministic, configurable rules |
| Memo text | Deterministic template (LLM commentary deferred beyond Release 1; FR-009.4) |
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
6. **Validate and verify.** The system validates output against the schema, verifies each quote appears on the cited page, checks that the value appears in the quote with the correct sign, in the correct period column, and with a declared scale and currency, and detects missing, duplicate, and conflicting values.
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
| SC-01 | Field extraction | Share of in-scope ground-truth fields extracted with correct value, scale, currency, and period (exact match after normalisation) | Placeholder 90%; **re-set after the tuning-set baseline** (O.3) |
| SC-02 | Hallucinated values | Share of fields given status `extracted` whose value does not exist in the document | 0 observed; investigate every occurrence |
| SC-03 | Not-found correctness | Share of fields absent from the document that are correctly reported `not_found` (not given a value) | Placeholder 95%; **re-set after the tuning-set baseline** (O.3) |
| SC-04 | Evidence verification | Share of `extracted` source fields that passed every deterministic check in FR-005.1, .2, and .6–.10 (quote on page, value in quote, sign, period column, scale, currency, period-end evidence, row label) | 100% — enforced by construction (fields failing any check cannot be `extracted`). **This shows consistency with the cited text, not that the value is correct**; correctness is measured by SC-01 and SC-05. |
| SC-05 | Page-reference correctness | Share of `extracted` fields whose cited page matches a ground-truth page for that value | Placeholder 95%; **re-set after the tuning-set baseline** (O.3) |
| SC-06 | Calculation accuracy | Share of calculation test cases (including edge cases) producing the exact expected result or expected undefined status | 100% |
| SC-07 | Risk-rule accuracy | Share of rule test cases producing the expected trigger state | 100% |
| SC-08 | Unsupported-claim rate | Share of material factual claims in the memo that are neither traceable (to evidence, calculation, or rule ID) nor labelled unverified, as judged by manual review | 0 in all memo sections (Release 1 memos contain no AI-generated text; FR-009.4) |
| SC-09 | Error handling | Share of catalogued failure scenarios (Section G, FR-011) producing the documented error code, a non-zero exit, and no partial output presented as complete | 100% |
| SC-10 | Latency | End-to-end wall-clock time for a document of ≤ 50 pages, with ≤ 15 candidate statement pages sent to the LLM | ≤ 120 s at the 90th percentile |
| SC-11 | API cost | LLM API cost per document under the same conditions as SC-10 | ≤ USD 0.25 per document (to be revalidated against verified pricing for the configured model; see D-02) |
| SC-12 | Statement-page recall | Share of ground-truth primary-statement pages (income statement and balance sheet, including continuation pages) that the locator (FR-013) includes among candidate pages | **Not yet set** (OD-3). Measured and reported as counts until a target is approved. |

**Rationale:** deterministic components (calculation, rules, evidence verification) must meet 100% because they are fully specified and testable. The LLM-dependent percentages (SC-01, SC-03, SC-05) were chosen without any measurement, so they are **placeholders**, not justified targets. They are replaced by targets set from a measured tuning-set baseline (O.3). Whatever the targets, LLM failures must surface as `requires_review` or `not_found` rather than as wrong facts.

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
| Draft credit memo generation | Deterministic template only. LLM-generated commentary is deferred (FR-009.4, D-05). |
| Markdown export | Memo (`.md`), plus a JSON sidecar containing structured results and the run manifest. |
| Automated tests | Unit, integration (with a fake LLM provider), and regression tests. |
| Interface | **Command-line interface only.** |

**Supported document profile for Release 1:**

- Annual financial statements of a **non-financial corporate** borrower.
- English language, with a selectable text layer.
- Two consecutive annual periods presented (current and comparative): the comparative period ends on the same month and day one calendar year before the current period (H.1.1). 52/53-week reporting years are out of scope.

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
| LLM-generated memo commentary (FR-009.4) | Deferred by D-05; reconsider only with evidence that it adds value without unsupported claims. |
| Including lease liabilities in borrowings (configurable) | Excluded in Release 1 (D-07). Would need lease-liability fields and evidence rules. |
| Opt-in fallback to another statement basis | Not in Release 1 (D-06). If ever added: opt-in only, recorded in the manifest, prominently disclosed in the memo, and never mixing bases. |
| OCR for scanned PDFs, multi-document comparison, quarterly periods, analyst override files | Candidates for later releases. |

Requirements in Sections G–K apply to **Release 1 only** unless marked otherwise.

---

## G. Functional Requirements

Priority: **Must** = required for Release 1; **Should** = expected unless descoped by explicit decision.

### FR-001 — PDF upload and validation (Must)

**Behaviour:** ingestion accepts a local file path (supplied by the CLI, FR-014, or by a direct call), validates it before any processing, and rejects invalid input with a specific error code (G.1).

**Acceptance criteria:**

1. A file whose content does not start with the PDF signature (`%PDF-`) is rejected with `E-INPUT-NOT-PDF`, whatever its extension. (Whether to accept bytes before the signature is OD-7; the strict rule stands until then.)
2. A file larger than the configured maximum (default 25 MB) is rejected with `E-INPUT-TOO-LARGE`.
3. A PDF with more pages than the configured maximum (default 400) is rejected with `E-INPUT-TOO-MANY-PAGES`.
4. An encrypted or password-protected PDF is rejected with `E-INPUT-ENCRYPTED`.
5. A corrupt or unparsable PDF is rejected with `E-INPUT-CORRUPT`.
6. A PDF in which no page has extractable text is rejected with `E-INPUT-NO-TEXT-LAYER`, and the message states that OCR is not supported. A page has extractable text if its extracted text contains at least one non-whitespace character. (The former "minimum share of candidate pages" clause is removed by D-03; the page-range case is covered by FR-013 rule 8.)
7. A missing path or unreadable file produces `E-INPUT-NOT-FOUND`.
8. A SHA-256 hash of the input file's bytes is computed and returned with the validated file information. It is recorded in the run manifest once FR-012 is implemented.
9. The original file is never modified.

### FR-002 — Page-level text extraction (Must)

**Behaviour:** text is extracted per page and stored with its 1-based physical page number. The PDF's page-label metadata is stored separately where the document defines it.

**Acceptance criteria:**

1. Output is an ordered list of `{page_number, page_label (optional), text}`, with exactly one entry per physical page.
2. Page numbers in every downstream artefact refer to 1-based physical page numbers. Page labels (PDF metadata such as "iv" or "45") are shown alongside where defined; numbers printed in page footers are **not** detected.
3. Extraction is deterministic: the same file, with the dependency versions locked in `uv.lock`, always yields identical page entries. This is verified by a golden-output test run in a fresh process (O.1).
4. Pages with no text are retained with empty text, not dropped, so numbering never shifts.
5. Document text is treated as data only. It is stored exactly as the extractor returns it, without cleanup, and is never executed, evaluated, or interpreted as instructions to the system (see M).
6. *Moved to FR-013 (statement page location) in v0.3.* This ID is retained so earlier references remain traceable.

### FR-003 — Financial field extraction (Must)

**Behaviour:** the LLM, called through a provider interface, receives candidate page texts (each tagged with its page number) and returns the fields in Section H.3 for the current and comparative periods.

**Acceptance criteria:**

1. Only candidate pages (FR-013) are sent to the LLM, not the whole document.
2. The prompt instructs the model to return only values present in the text, to return `not_found` when a value is absent, and to quote the supporting text verbatim. Prompts are versioned files, and their version is recorded in the run manifest.
3. The model does not perform arithmetic. It extracts reported figures only. Derived values (e.g. EBIT when not reported) are computed in Python with a derivation record (H.5).
4. The extraction call uses the provider's structured-output or JSON mode where available.
5. **Response cache.** Every LLM response is cached locally, to support reproducibility (FR-012) and control cost.
   - **Location:** `.cache/llm/`, which is excluded from Git. The cache is local only, and is never committed or uploaded.
   - **Key:** the SHA-256 of a canonical JSON object (keys sorted, UTF-8, no insignificant whitespace) holding every input that can affect the response:
     - document SHA-256;
     - ordered candidate page numbers;
     - provider and model ID;
     - prompt version and schema version;
     - generation settings (temperature, maximum output tokens, structured-output mode).
   - **Entry:** one file `<key>.json` holding the key's input object, the raw response text, token usage, and the creation time (UTC). It never contains API keys, request headers, or other credentials.
   - **Hit:** a readable entry whose stored input object equals the current one is used without calling the LLM, and is counted as a hit in the manifest.
   - **Miss:** no entry, an unreadable entry, or a stored input object that differs. The LLM is called and the entry is written atomically, replacing any unreadable one; this counts as a miss.
   - **Invalidation and clearing:** entries never expire. Changing any key input is a miss by construction. To clear the cache, delete `.cache/llm/`, which is documented in the README.
6. With a fake provider in tests, the extraction pipeline runs end to end with no network access.
7. If the locator returns no candidate pages and no page range was supplied, extraction does not call the LLM and the run fails with `E-EXTRACT-NO-STATEMENT-PAGES`. The message suggests supplying a page range (D-04).

### FR-004 — Structured output validation (Must)

**Behaviour:** LLM output is parsed and validated against the Pydantic schema (Section H) before any further use.

**Acceptance criteria:**

1. Output that is not valid JSON or does not match the schema triggers **one** retry, which includes the validation error message. If the retry also fails, the run fails with `E-LLM-INVALID-OUTPUT`, and the raw response is saved to the run directory for diagnosis. The corrective retry is a new LLM call: transient failures during it are retried under FR-011.3, and its tokens count toward the per-run ceiling (NFR-09).
2. Unknown field names are rejected. Missing expected fields are treated as `not_found`.
3. Values must parse as decimal numbers. Formatting such as thousands separators (including Indian grouping such as `1,23,456`), parentheses for negatives (`(1,234)`), and currency symbols is normalised deterministically. Unparsable values become `requires_review`.
   - **Nil convention (D-08).** A raw value consisting only of a dash (`-`, `–`, or `—`) or the word `nil` (any case), with no digits, is read as a **document-reported zero**: the value is 0, the raw text is preserved, and `value_interpretation = reported_nil` (H.1).
   - It is accepted only if the period-column check (FR-005.7) and the row-label check (FR-005.10) pass for that dash's position. Otherwise the field is `requires_review`.
   - A blank cell, a missing value, or any other symbol is **never** zero. It is `not_found` if nothing was proposed, or `requires_review` if an unrecognised symbol was proposed.
4. Values are held as `decimal.Decimal`, never binary floats.

### FR-005 — Source evidence and page-number preservation (Must)

**Behaviour:** every extracted value carries a page number and verbatim quote. These are verified deterministically, both for **presence** (the quote and value appear on the page) and for **interpretation** (the value is in a recognised row, has the right sign, sits in the right period column, belongs to a period with a supported end date, and has a declared scale and currency).

**Acceptance criteria:**

1. The quote must occur on the cited page's text after whitespace normalisation (collapse runs of whitespace; normalise Unicode NFKC). No other fuzzy matching is used.
2. The raw value string returned by the model must occur within the verified quote.
3. A field may have status `extracted` only if criteria 1, 2, and 6–10 all pass. Otherwise its status is `requires_review`, with the reason of the first failing check, in this order: `evidence_not_verified` (1), `value_not_in_evidence` (2), `label_not_recognised` (10), `period_mismatch` (9), `period_not_verified` (7), `sign_mismatch` (6), `scale_not_verified` / `scale_ambiguous` / `currency_not_verified` (8).
4. Evidence is never edited, summarised, or regenerated after verification. The memo reproduces it verbatim (truncated with an ellipsis only for display, with the full text in the JSON sidecar).
5. Every value shown in the memo carries a reference to its field ID, which resolves to document, page, and quote — or, for a derived value, to its input field IDs (H.5).
6. **Sign.** The occurrence of the raw value inside the quote that is used for criterion 7 is checked for a negative marker. A marker is either enclosing parentheses `( … )` or a minus or dash (`-`, `−` U+2212, `–` U+2013) directly attached to the digits. It counts whether it is part of the returned raw value (e.g. `(245.10)`) or surrounds that occurrence in the quote. If a marker is present, the parsed value must be negative; if absent, it must not be negative. Otherwise the reason is `sign_mismatch`. A dash standing alone is the nil convention (FR-004.3), never a sign, and a reported nil passes this check. (Example: Appendix B, Example 2.)
7. **Period column.** The quote must contain the line-item row. The system determines the left-to-right order of the period columns from the column-header text (the period-end dates or years shown above the figures). It uses the cited page, or, if that page has no column header and the locator selected it, the first page of the same statement run (FR-013 rule 6). It then verifies that the value occupies the column of the period claimed for it, so the current-period value cannot be the comparative-period figure or a note reference. If the column order cannot be determined, or the value is in a different column, the reason is `period_not_verified`. The mapping method is open decision OD-1; whichever method is chosen must be deterministic and tested on fixtures that include a note-reference column. (Example: Appendix B, Example 1.)
8. **Scale and currency.** The field's scale must be supported by a scale declaration found on the cited page, or, when the locator selected the page, on the first page of the same statement run (FR-013 rule 6) (e.g. "₹ in crore", "(Rs. in lakh)", "USD '000", "in millions"). Its currency must be supported in the same way (symbol, ISO code, or currency name). Phrase lists are configurable. No supporting declaration gives `scale_not_verified` or `currency_not_verified`. Two different scale declarations on the cited page gives `scale_ambiguous`. (Example: Appendix B, Example 3.)
9. **Period-end evidence (D-11).** Each period-end date used for a field must be supported by a quote from a statement title or column header on a candidate page. It is stored with both its raw text and its normalised ISO date (H.1.2). Accepted forms:
   - a written date with day, month name, and year (e.g. `31 March 2025`, `March 31, 2025`), optionally preceded by "as at", "as of", "year ended", or "for the year ended";
   - an ISO date (`2025-03-31`);
   - a numeric date (`31.03.2025`, `31/03/2025`, `31-03-2025`), **only** if it can be read one way: day and month are equal, or one of them is greater than 12;
   - a year-only or financial-year header (`2025`, `FY2025`, `2024-25`, `FY 2024-25`), **only** if a full date in an accepted form appears elsewhere on the same statement page, and the header's year (the later year, for `2024-25`) equals that date's year.

   Anything else, including an ambiguous numeric date such as `03/04/2025`, is **not guessed**. That period is unvalidated, and every field of that period is `requires_review` with reason `period_mismatch`. The later validated date is the current period. The comparative period must meet the consecutive-period rule (H.1.1). (Example: Appendix B.6, rows 3 and 4.)
10. **Row label (D-10).** The quoted row's label is the text before its first figure (a note reference counts as a figure).
    - **Normalisation:** the label is normalised as in FR-013 rule 1, and leading item markers are removed: Roman numerals, single letters, or digits, optionally in parentheses or followed by `.` or `)`.
    - **Match:** the result must equal one of the field's configured label phrases (H.3). Otherwise the reason is `label_not_recognised`.
    - **Tuning:** label lists may be extended **only** from tuning-set evidence (O.2), never from held-out documents. This check is the main protection against a value taken from the wrong row.
    - **Section heading:** for fields whose label is shared between sections (`borrowings_non_current`, `borrowings_current`), the nearest section heading above the row on the page must also match the field's configured heading ("non-current liabilities" or "current liabilities"). Otherwise the reason is `label_not_recognised`.

### FR-006 — Missing and conflicting information detection (Must)

**Behaviour:** absent, duplicated, inconsistent, and conflicting values are detected and surfaced. They are never silently resolved.

**Acceptance criteria:**

1. A required field with no verified value is marked `not_found`, and every metric that depends on it is reported as undefined, with reason `missing_input`.
2. Multiple verified occurrences of the same field, period, and basis are reconciled using the rules in Section H.4. Inconsistent occurrences produce status `conflicting`, with all candidate values and their evidence retained.
3. Fields marked `conflicting` or `requires_review` are **excluded** from calculations. Dependent metrics are undefined, with reason `input_conflicting` or `input_requires_review`.
4. The memo's "Missing information and conflicts" section lists every non-`extracted` field with its status, reason, and candidate evidence.
5. **Plausibility.** Before any calculation, a value that is implausible for its field is set to `requires_review` with reason `implausible_value`: a negative `revenue`, `current_assets`, `current_liabilities`, `total_borrowings`, `borrowings_non_current`, `borrowings_current`, or `interest_expense`. Negative `net_profit`, `profit_before_tax`, `operating_profit`, and `total_equity` are valid. (These checks moved here from Section I in v0.3, so that no later stage changes a field's status.)

### FR-007 — Financial ratio calculations (Must)

**Behaviour:** the five metrics in Section I are computed by pure, deterministic Python functions.

**Acceptance criteria:**

1. Each metric function is pure: no I/O, no randomness, no LLM calls.
2. Each result records the formula, the input field IDs and values used, the period(s), and either a value or an explicit undefined status with a reason code.
3. Every edge case listed in Section I has a unit test.
4. Rounding is applied **only for display**. Stored values keep full `Decimal` precision. Display uses `ROUND_HALF_EVEN`: ratios to 2 decimal places and percentages to 1 decimal place.
5. Derived inputs (EBIT, and total borrowings when only components are reported) are produced by pure functions that return a derivation record (H.5). Calculation functions never change the status of a field.

### FR-008 — Rules-based risk indicator generation (Must)

**Behaviour:** configurable rules (Section J) evaluate calculated metrics and field statuses and produce explainable indicators.

**Acceptance criteria:**

1. Rules and thresholds are loaded from a TOML configuration file. Changing a threshold requires no code change.
2. **Per-condition evaluation (D-09).** Each condition of a rule is evaluated independently and recorded as `{condition_id, result, values used, missing_inputs}`. The rule's overall result is:
   - `triggered` if **any** evaluable condition fires, even if other conditions could not be evaluated. Missing inputs for one condition never suppress another condition that fired.
   - `not_triggered` only if **every** condition was evaluable and none fired.
   - `not_evaluable` otherwise, listing the missing inputs.

   The reported severity is the highest severity among the conditions that fired. `not_evaluable` is never reported as `not_triggered`.
3. Every triggered indicator includes: rule ID, rule name, the condition and threshold applied, the actual values, severity, and references to the supporting field IDs and metric IDs.
4. No overall score, rating, grade, approval, or rejection is produced.
5. The configuration file's SHA-256 hash is recorded in the run manifest.

### FR-009 — Draft credit memo creation (Must)

**Behaviour:** the system assembles the memo described in Section K.

**Acceptance criteria:**

1. Sections K.1–K.9 are always present, in order. When a section has no content, it says so (e.g. "No risk indicators triggered by the configured rules").
2. Every factual statement carries one origin label: `[SOURCE]`, `[CALCULATED]`, `[RULE]`, `[ANALYST-PROVIDED]`, or `[UNVERIFIED]`. (`[AI INTERPRETATION]` is reserved and is not produced in Release 1.)
3. The whole memo is produced by a deterministic template from structured data. The LLM is not called during memo generation.
4. **Deferred beyond Release 1 (D-05).** LLM-generated commentary is not part of Release 1. If reconsidered later, the previous specification is the starting point: the LLM receives only verified structured data, never raw document text; it must cite field, metric, or rule IDs; and it passes a deterministic post-check (every number equals a known value after display rounding, and every cited ID exists), with failing sentences removed and counted.
5. The memo header states that it is a **draft for human review** and not a credit decision.

### FR-010 — Markdown export (Must)

**Behaviour:** results are written to an output directory per run.

**Acceptance criteria:**

1. Outputs are `memo.md`, `results.json` (fields, metrics, indicators, evidence), and `manifest.json` (see FR-012), written to `<output_dir>/<run_id>/`. The run ID is `<UTC timestamp to the microsecond, YYYYMMDDTHHMMSS.ffffffZ>-<first 8 hex characters of the input SHA-256>`, e.g. `20261013T101530.123456Z-1a2b3c4d`. If that directory already exists, the run fails with `E-EXPORT-FAILED` and nothing is overwritten (criterion 4).
2. `memo.md` renders correctly as CommonMark: headings, tables, and block quotes for evidence.
3. Files are written atomically (write to a temporary file, then rename) so a failed run never leaves a file that looks complete.
4. Existing run directories are never overwritten.

### FR-011 — Error handling and processing status (Must)

**Behaviour:** the pipeline progresses through explicit states and fails safely.

**States:** `received → validated → text_extracted → statements_located → fields_extracted → validated_fields → calculated → rules_evaluated → memo_generated → exported`, or `failed` (with stage and error code).

**Acceptance criteria:**

1. Each stage transition is logged with a timestamp. The final state is recorded in the manifest.
2. Every anticipated failure maps to exactly one entry in the error catalogue (G.1), which gives its code, stage, user-facing message, CLI exit code, and retry behaviour. A failure not in the catalogue is an internal error (exit code 1) and indicates a bug.
3. LLM/API failures (timeout, rate limit, 5xx) are retried with exponential backoff, up to a configured limit (default 3 attempts). After that the run fails with `E-LLM-UNAVAILABLE`. Authentication failures are not retried (`E-LLM-AUTH`).
4. Error messages never include API keys, document text or quotes, or stack traces at the default log level.
5. Partial field extraction does **not** fail the run. Missing fields flow through as `not_found`, and the memo reports them. The run fails only when it cannot produce a trustworthy memo at all (e.g. invalid input, no LLM response).
6. Every catalogued failure scenario has an automated test (SC-09).

### FR-012 — Logging and reproducibility (Must)

**Behaviour:** every run is reproducible and auditable.

**Acceptance criteria:**

1. `manifest.json` records: run ID, timestamps, input file name and SHA-256, page count, locator method, candidate pages (and `range_pages_without_text`), requested statement basis and bases found, profile file name if supplied, code version (git commit hash, and whether the working tree is dirty), package versions, LLM provider and model ID, prompt version, schema version, rules-config hash, cache hits and misses, token usage, estimated cost, final state, and error code if any.
2. Re-running with the same input, configuration, code version, and cached LLM responses produces byte-identical `results.json` and `memo.md`, excluding timestamps and run ID, which are confined to the manifest and the memo header.
3. Logging uses the Python standard library `logging` module. At the default `INFO` level, logs contain stage events, counts, durations, and identifiers — not document text, quotes, or financial values. Those appear only at `DEBUG`, which is documented as unsuitable for sensitive data.
4. LLM temperature is set to 0 (or the provider's most deterministic setting). Reproducibility relies on the response cache, not on model determinism, which is not guaranteed.

### FR-013 — Statement page location (Must; formerly FR-002.6)

**Behaviour:** a deterministic locator selects the pages likely to contain the primary financial statements (income statement and balance sheet). An analyst-supplied page range replaces the locator's selection.

**Input:**
- `pages`: the ordered `PageText` entries from FR-002.
- `settings`, which are configurable:
  - for each statement type (`income_statement`, `balance_sheet`), a list of *title phrases* and a list of *line-item phrases*;
  - `min_line_items_with_title`, `min_line_items_without_title`, `title_weight`, and `max_candidates`.
- `page_range` (optional): a string such as `"110-115,120"`.

**Processing rules:**
1. **Matching text.** For matching only, each page's text is normalised: Unicode NFKC, case-folded, and runs of whitespace collapsed to one space. The stored page text is never changed.
2. **Phrase counting.** A phrase is *present* on a page if its normalised form occurs in the normalised page text with no letter or digit immediately before or after it. So "total equity" is present in "total equity and liabilities", but "total assets" is not present in "total current assets". For each page and statement type, the locator counts the **distinct** title phrases and the **distinct** line-item phrases present. Repeated occurrences of the same phrase do not add to the count.
3. **Qualification.** A page qualifies for a statement type if it has (a) at least one title phrase **and** at least `min_line_items_with_title` line-item phrases, or (b) at least `min_line_items_without_title` line-item phrases. Rule (a) rejects contents pages, which name statements but list no line items. Rule (b) admits continuation pages without a title.
4. **Score.** A qualifying page's score is the sum, over the statement types it qualifies for, of `title_weight × title phrases + line-item phrases`.
5. **Selection.** Qualifying pages are ranked by score (highest first), with ties broken by the lower page number. At most `max_candidates` pages are kept, and the result is returned in ascending page order.
6. **Statement runs.** Consecutive selected pages that share a statement type form one *statement run*. The first page of the run is "the first page of the statement" used by FR-005.8.
7. **Page range override.** If `page_range` is supplied, the locator's ranking is not used. The candidates are exactly the pages in the range, in ascending order.
   - **Syntax:** comma-separated items, each `N` or `N-M`, where N and M are 1-based physical page numbers, `N ≤ M`, and whitespace is ignored. Overlapping items are merged.
   - **Invalid ranges:** an empty, malformed, reversed, or out-of-document range, or one covering more than `max_candidates` pages, is rejected with `E-INPUT-PAGE-RANGE`.
8. **Text in a page range.** If no page in a supplied range has extractable text (FR-001.6 definition), the run fails with `E-INPUT-NO-TEXT-LAYER`. Pages without text inside a valid range are kept, listed in the manifest (`range_pages_without_text`), and shown in memo section 2 (Documents reviewed).

**Output:** `LocatorResult` with:
- `method`: `keywords` or `page_range`;
- `candidates`: a tuple of `CandidatePage`, each with `page_number`, `statement_types`, `score` (null for a page range), and `matched_phrases` (empty for a page range).

**Failure behaviour:** an empty keyword result is **not** an error at this stage. Extraction then stops with `E-EXTRACT-NO-STATEMENT-PAGES` (FR-003.7, D-04).

**Initial settings:** these are configurable, with initial values chosen to separate contents pages, statement pages, continuation pages, and notes pages in the synthetic fixtures (Appendix B, Example 5). **They are not validated on real documents**; validating them is OD-3.

| Setting | Initial value | Basis |
|---|---|---|
| `min_line_items_with_title` | 2 | Rejects contents pages (titles only) |
| `min_line_items_without_title` | 4 | Admits untitled continuation pages; rejects notes pages that mention one line item |
| `title_weight` | 3 | Ranks titled statement pages above continuation pages |
| `max_candidates` | 15 | Matches the SC-10 cost/latency assumption |
| Title phrases — income statement | "statement of profit and loss", "statement of profit or loss", "profit and loss statement", "income statement", "statement of comprehensive income" | Common IFRS / Ind AS / US titles |
| Title phrases — balance sheet | "balance sheet", "statement of financial position" | as above |
| Line-item phrases — income statement | "revenue from operations", "total income", "total expenses", "finance costs", "profit before tax", "tax expense", "profit for the year" | Lines from the H.3 field set and statement totals |
| Line-item phrases — balance sheet | "total non-current assets", "total current assets", "total assets", "total equity", "total non-current liabilities", "total current liabilities", "total equity and liabilities", "borrowings" | as above |

**Acceptance criteria:**
1. On a fixture with a contents page naming both statements, a titled balance-sheet page, an untitled continuation page, a titled income-statement page, and a notes page mentioning one line item, exactly the three statement pages are selected (Appendix B, Example 5).
2. Matching is insensitive to case, whitespace runs, and Unicode compatibility forms, and respects the boundary rule in rule 2. Repeating a phrase does not change a page's score.
3. Ties are broken by the lower page number. The result never exceeds `max_candidates` and is returned in ascending page order.
4. Valid page ranges parse as specified. Every invalid form listed in rule 7 raises `E-INPUT-PAGE-RANGE`.
5. A document with no qualifying page returns an empty `LocatorResult` without raising an error.
6. Page texts are unchanged after location, and repeated calls on the same input give identical results.
7. On the evaluation set, statement-page recall (SC-12) is measured and reported as counts.

### FR-014 — Command-line interface (Must; Phase 5)

**Behaviour:** one command runs the full pipeline for one document.

**Acceptance criteria:**
1. **Command:** `credit-intel <pdf_path> [--pages RANGE] [--basis consolidated|standalone] [--profile PROFILE_JSON] [--output-dir DIR] [--config SETTINGS_TOML]`.
   - **Defaults:** `--output-dir runs` and `--config config/settings.toml`.
   - **Basis:** `--basis` overrides the configured statement basis (default `consolidated`) for this run. It is the explicit, user-approved override required by H.4.6.
2. **On success:** exit code 0, and the run directory path is printed to standard output.
3. **On a catalogued failure:** the error code and safe message (G.1) are printed to standard error, and the process exits with the catalogue's exit code. No output file is left looking complete (FR-010.3).
4. **Argument errors** (missing path, unknown option) exit with code 2, which is argparse's convention.
5. **Unexpected exceptions** exit with code 1. The message gives the run ID and does not show a stack trace at the default log level (FR-011.4).
6. Every exit path in criteria 2–5 and every rejection in criterion 7 has an automated test.
7. **Profile file (`--profile`).** A JSON object whose only allowed keys are `borrower_name`, `industry`, `facility_requested`, and `notes`. Each is optional, and each value is a string of at most 500 characters.
   - **Rejected** with `E-INPUT-PROFILE-INVALID`: invalid JSON, a non-object, an unknown key, a non-string value, or a value longer than 500 characters.
   - **Use of profile values:** they appear only in memo section 1, labelled `[ANALYST-PROVIDED]`. They are **never** used as financial evidence, as inputs to calculations, or in risk rules.

### G.1 Error catalogue

Every anticipated failure has exactly one code. Messages are fixed, user-safe text (FR-011.4). They may append only the file name or numeric limits, and they state what the user should do.

The "Code status" column records what exists in the code today. **No exit codes are implemented yet** (FR-014, Phase 5). The current input-error messages do not yet include the "What the user should do" text; that is a later code change.

| Code | Stage | Meaning | What the user should do | Exit code | Retried? | Code status |
|---|---|---|---|---|---|---|
| `E-INPUT-NOT-FOUND` | validated | File missing, not a regular file, or unreadable | Check the path and file permissions | 3 | No | Implemented (Phase 1) |
| `E-INPUT-TOO-LARGE` | validated | File exceeds `max_file_bytes` | Supply a smaller file or only the financial-statements section | 3 | No | Implemented (Phase 1) |
| `E-INPUT-NOT-PDF` | validated | Content lacks the `%PDF-` signature | Supply a PDF file | 3 | No | Implemented (Phase 1) |
| `E-INPUT-CORRUPT` | validated / text_extracted | The PDF library cannot parse the file or a page | Re-download or re-export the PDF | 3 | No | Implemented (Phase 1) |
| `E-INPUT-ENCRYPTED` | validated | Encrypted, including owner-password-only | Supply an unencrypted copy | 3 | No | Implemented (Phase 1) |
| `E-INPUT-TOO-MANY-PAGES` | validated | Page count exceeds `max_pages` | Supply only the relevant pages | 3 | No | Implemented (Phase 1) |
| `E-INPUT-NO-TEXT-LAYER` | text_extracted / statements_located | No page (or no page in a supplied range) has extractable text; OCR not supported | Supply a text-based PDF, or a page range that contains text | 3 | No | Implemented for whole documents (Phase 1); page-range case specified (FR-013 rule 8) |
| `E-INPUT-PAGE-RANGE` | statements_located | Page range empty, malformed, reversed, out of the document, or larger than `max_candidates` | Correct `--pages` (e.g. `110-115,120`) | 3 | No | Specified (FR-013) |
| `E-INPUT-PROFILE-INVALID` | received | Profile file invalid (FR-014.7) | Fix the profile file to the documented keys and limits | 3 | No | Specified |
| `E-EXTRACT-NO-STATEMENT-PAGES` | fields_extracted | No candidate pages and no page range supplied | Supply the statement pages with `--pages` | 4 | No | Specified (FR-003.7) |
| `E-EXTRACT-BASIS-UNAVAILABLE` | statements_located | The configured statement basis is not present; the message lists the bases found | Review the document; to analyse another basis, re-run with `--basis` | 4 | No | Specified (H.4.6) |
| `E-LLM-INVALID-OUTPUT` | fields_extracted | Output still invalid after one corrective retry | Re-run; report if it persists | 5 | Once, with the validation error | Specified (FR-004.1) |
| `E-LLM-UNAVAILABLE` | fields_extracted | Timeout, rate limit, or server error after retries | Re-run later | 5 | Yes, with backoff (FR-011.3) | Specified |
| `E-LLM-AUTH` | fields_extracted | Authentication failed | Check `OPENAI_API_KEY` | 5 | No | Specified |
| `E-LLM-BUDGET-EXCEEDED` | fields_extracted | Per-run token ceiling would be exceeded | Narrow `--pages`, or raise the ceiling deliberately | 5 | No | Specified (NFR-09; ceiling value is OD-8) |
| `E-CONFIG-INVALID` | received | Settings or rules file missing, unparsable, or failing validation | Fix the named setting | 6 | No | Specified |
| `E-EXPORT-FAILED` | exported | Output cannot be written, or the run directory already exists (FR-010) | Check the output directory and re-run | 7 | No | Specified |

**Internal errors** are failures not listed above, such as an extractor that breaks the 1..N page-numbering contract (implemented as `RuntimeError`). They exit with code 1 and are treated as bugs, not as bad input.

---

## H. Financial Data Schema

### H.1 Extracted field structure

Proposed schema. This is a Pydantic model, because it is validated from LLM output (L.1). Final attribute names are set during Phase 2.

**Required** column:
- **Always:** present for every field.
- **Source:** required when `origin = source`; null for derived values.
- **Extracted:** required when `status = extracted`; may be null otherwise.
- **Optional:** may be null.

| Attribute | Type | Required | Description |
|---|---|---|---|
| `field_id` | string | Always | `<field_name>.<period_end>.<statement_basis>`, e.g. `revenue.2025-03-31.consolidated` (H.1.1). |
| `field_name` | enum | Always | One of the names in H.3. |
| `origin` | enum | Always | `source` (read from the document) or `derived` (computed in Python; H.5). |
| `period_end` | date | Always | Period end date, e.g. `2025-03-31`. |
| `period_length_months` | int | Always | 12 for annual periods (Release 1 supports 12 only). |
| `period_role` | enum | Always | `current` or `comparative`. |
| `statement_basis` | enum | Always | `consolidated`, `standalone`, or `unknown`. |
| `status` | enum | Always | See H.2. |
| `status_reason` | enum or null | When status ≠ `extracted` | e.g. `evidence_not_verified`, `value_not_in_evidence`, `sign_mismatch`, `period_not_verified`, `scale_not_verified`, `scale_ambiguous`, `currency_not_verified`, `label_not_recognised`, `scale_unknown`, `period_mismatch`, `basis_unknown`, `implausible_value`, `missing_input`, `currency_mismatch`, `borrowings_classification_unresolved`. |
| `value` | Decimal or null | Extracted | Normalised value in base currency units (scale applied). Null unless status is `extracted`. |
| `currency` | ISO 4217 code | Extracted | e.g. `INR`, `USD`, `AED`. |
| `raw_value` | string | Source | The value exactly as printed, e.g. `(1,234.5)` or `–`. |
| `value_interpretation` | enum | Source | `number`, or `reported_nil` for the nil convention (FR-004.3). |
| `scale` | enum | Source | `units`, `thousands`, `lakh`, `millions`, `crore`, `billions`, as declared in the document. |
| `source_document` | object | Source | File name and SHA-256. |
| `page_number` | int | Source | 1-based physical page. |
| `page_label` | string or null | Optional | PDF page-label metadata, if defined (FR-002.2). |
| `evidence_quote` | string | Source | Verbatim quote from the page, containing the line-item row. |
| `line_item_label` | string | Source | The label as printed, e.g. "Revenue from operations". |
| `validation` | object | Source | Results of the deterministic checks: `evidence_verified`, `value_in_evidence`, `label_verified`, `period_end_verified`, `period_column_verified`, `sign_verified`, `scale_verified`, `currency_verified` (FR-005.1–.10). |
| `derivation` | object or null | Derived | `{method_id, formula, input_field_ids, component_classification}` (H.5). Null for source values. |
| `candidates` | list | Optional | For `conflicting` fields: every candidate value with its own evidence. |
| `corroborating_evidence` | list | Optional | Additional consistent occurrences (see H.4). |

#### H.1.1 Period identifiers

- Every period is identified by its **period-end date** in ISO 8601 form (`YYYY-MM-DD`), validated from a statement title or column header (FR-005.9).
- Field IDs use the form `<field_name>.<period_end>.<statement_basis>`. Metric IDs use `<MET-ID>.<period_end>` (e.g. `MET-03.2025-03-31`). Comparison metrics use the current period's end date (e.g. `MET-01.2025-03-31` is growth from the comparative period to the period ending 2025-03-31).
- Labels such as "FY2025" may be shown alongside for readability but are **never** used as identifiers. Their meaning varies by jurisdiction (in India, FY2025 ends on 31 March 2025; elsewhere it often means calendar 2025).
- If a period-end date cannot be validated, the affected fields are `requires_review` with reason `period_mismatch` (FR-005.9).
- **Consecutive periods (D-11).** The comparative period-end must have the **same month and day** as the current period-end, in the **previous calendar year**. 28 February and 29 February count as the same day.
  - If this fails, every comparative-period field is `requires_review` (`period_mismatch`), and comparison metrics are undefined (`period_mismatch`).
  - 52/53-week reporting years are out of scope for Release 1.
  - Boundary tests: `2024-02-29` vs `2023-02-28` (valid); `2025-02-28` vs `2024-02-29` (valid); `2025-03-31` vs `2023-03-31` (two years: invalid); `2025-03-31` vs `2024-12-31` (invalid).

#### H.1.2 Document-level attributes

These attributes are extracted once per document with evidence, and checked deterministically. Each record holds: `attribute`, `raw_text`, `normalised_value`, `page_number`, `evidence_quote`, `status` (`extracted`, `not_found`, or `requires_review`), and `status_reason`.

| Attribute | Normalised form | Check |
|---|---|---|
| `entity_name` | text | Quote present on the cited page (FR-005.1) |
| `period_end` (current, comparative) | ISO date | FR-005.9 and the consecutive-period rule (H.1.1) |
| `statement_basis` | `consolidated` / `standalone` / `unknown` | Statement title phrase (H.4.6) |
| `reporting_currency` | ISO 4217 code | Currency declaration (FR-005.8) |
| `scale` | scale enum | Scale declaration (FR-005.8) |

A field may not be `extracted` if a document-level attribute it depends on (its period end, basis, currency, or scale) is not `extracted`.

**Confidence:** the system does **not** use LLM self-reported confidence scores. They are not calibrated and could mislead reviewers. Trust is expressed through the deterministic `validation` checks and the `status`.

### H.2 Statuses

| Status | Meaning | Used in calculations? |
|---|---|---|
| `extracted` | For a source value: found, and passed every check in FR-005 and FR-006.5. For a derived value: every input is `extracted` (H.5). | Yes |
| `not_found` | No value was found in the provided pages (or, for a derived value, an input is `not_found`). | No — dependent metrics undefined |
| `conflicting` | Two or more verified occurrences disagree beyond tolerance (H.4). | No — dependent metrics undefined |
| `requires_review` | A value was proposed but failed a verification, normalisation, or plausibility check, or is ambiguous (e.g. unknown scale or basis). | No — dependent metrics undefined |

No further statuses are added:
- **Validated:** "verified" is already what `extracted` requires.
- **Inferred:** computed values are expressed by `origin = derived` plus a derivation record.
- **Failed:** processing failures are run-level errors (G.1), not field statuses.

### H.3 Release 1 field set

Each field is extracted for the current and comparative periods.

| Field | Description; **initial label phrases** (FR-005.10) | Notes |
|---|---|---|
| `revenue` | "revenue from operations", "revenue", "turnover" | Excludes "other income". "Total income" is **not** revenue. |
| `net_profit` | "profit/(loss) for the year", "profit for the year", "profit/(loss) for the period", "profit for the period" | Total profit for the period, after tax, before attribution to non-controlling interests. |
| `operating_profit` | "operating profit", "ebit" | Optional. Used for EBIT if present. |
| `profit_before_tax` | "profit/(loss) before tax", "profit before tax" | Used to derive EBIT. |
| `interest_expense` | "finance costs", "interest expense" | See MET-05 limitations (I.2). |
| `current_assets` | "total current assets" | |
| `current_liabilities` | "total current liabilities" | |
| `total_borrowings` | "total borrowings" | Interest-bearing borrowings, **excluding lease liabilities** (D-07). Taken from a reported total line if one exists; otherwise derived from the components below (H.5, D-12). |
| `borrowings_non_current` | "borrowings" under the heading "non-current liabilities"; "non-current borrowings" | Optional component; used only to derive `total_borrowings`. Section heading checked (FR-005.10). |
| `borrowings_current` | "borrowings" under the heading "current liabilities"; "current borrowings" | Optional component, as presented. It may or may not already include current maturities (H.5, D-12). Section heading checked (FR-005.10). |
| `current_maturities_long_term_borrowings` | "current maturities of long-term borrowings", "current maturities of long-term debt" | Optional component, only when presented as its own row. Classified under H.5 (D-12). |
| `total_equity` | "total equity" | |

Derived (never extracted by the LLM): `ebit` (H.5). Document-level attributes are defined in H.1.2.

Label phrases are configurable. They are compared after normalisation (FR-005.10), and may be extended only from tuning-set evidence (O.2).

### H.4 Handling duplicates, units, periods, and conflicts

1. **Duplicates.** The same field, period, and basis may appear on several pages (e.g. highlights page and balance sheet). If the values agree after normalisation, they are a single field. Evidence from the primary statement page is the main evidence, and other occurrences are kept as `corroborating_evidence`.
2. **Rounding tolerance.** Values that differ only through presentation rounding (e.g. `1,234.56 crore` in the statement vs `1,235 crore` in highlights) are treated as consistent by a precise rule:
   - Let *b* be the less precise value, printed with *p* decimal places in a scale of size *s* (e.g. crore = 10^7). Let *a* be the more precise value.
   - After converting both to base units, they are consistent if |*a* − *b*| ≤ 0.5 × 10^(−*p*) × *s*. That is, they may differ by at most half a unit in *b*'s last printed digit.
   - Values printed with the same precision and scale must be exactly equal.
   - When consistent, the more precise value is used, and the other occurrence is kept as corroborating evidence.
3. **Inconsistent units/scale.** Every value is normalised to base units using the scale declared on its page (e.g. "₹ in crore", "USD '000"). If the scale cannot be determined for a value, its status is `requires_review` (`scale_unknown`). Lakh = 10^5 and crore = 10^7.
4. **Currency.** If fields needed for a single metric are in different currencies, the metric is undefined (`currency_mismatch`). Release 1 performs **no** currency conversion.
5. **Different reporting periods.** Only 12-month periods are supported. A field whose period cannot be matched to the document's current or comparative period end is `requires_review` (`period_mismatch`). Metrics never combine fields from mismatched periods.
6. **Conflicting statements.**
   - **Statement basis (D-06).** Consolidated and standalone figures are **different facts, not conflicts**, and are **never mixed**. Every field, derived value, and metric in a run uses one basis.
   - **How a statement's basis is established:** from its title, by configured phrases (e.g. "consolidated", "standalone", "separate"), quoted as evidence (H.1.2). A title that names no basis gives basis `unknown`, and that statement's fields are `requires_review` (`basis_unknown`). Treating an untitled statement as standalone is open decision OD-10.
   - **Which basis a run uses:** the configured basis (default `consolidated`), or the basis given with `--basis` for that run (FR-014). Fields of other bases are ignored, and the memo notes which other bases were present.
   - **Configured basis absent:** if no candidate page has a statement title of the configured basis, the run stops **before any LLM call** with `E-EXTRACT-BASIS-UNAVAILABLE`, which lists the bases found. The system **never switches basis automatically**. The analyst reviews the document and may re-run with `--basis`. Any future automatic fallback must be opt-in, recorded in the manifest, and prominently disclosed (F.2).
   - Genuine disagreements within one basis and period, beyond rounding tolerance, are `conflicting`, and every candidate is listed with evidence.
   - Restated comparatives are noted if the document labels them as restated. Release 1 processes one document, so cross-document restatement is out of scope.
7. **No guessing.** The system never fills a missing value, averages conflicting values, picks the "most likely" candidate, or infers a value from narrative text without verifiable evidence. An absent line item is `not_found`, never zero.

### H.5 Derived values

A derived value is computed by a pure Python function from other fields of the **same period and basis**. It never has a quote of its own; its evidence is the evidence of its inputs.

| Derived field | Method ID | Formula | Inputs (field names) | Used when |
|---|---|---|---|---|
| `ebit` | `EBIT-OP` | `ebit = operating_profit` | `operating_profit` | `operating_profit` is reported |
| `ebit` | `EBIT-PBT` | `ebit = profit_before_tax + interest_expense` | `profit_before_tax`, `interest_expense` | `operating_profit` is `not_found` |
| `total_borrowings` | `BORR-SUM` | `total_borrowings = borrowings_non_current + borrowings_current` (`+ current_maturities_long_term_borrowings` only when classified `separate_component`) | `borrowings_non_current`, `borrowings_current`, and possibly `current_maturities_long_term_borrowings` | No total borrowings line is reported |

**Rules:**
1. **Record.** Each derived value carries `origin = derived` and a derivation record `{method_id, formula, input_field_ids, component_classification}`. Source-only attributes (quote, page, raw value, scale) are null. All inputs must share one currency; otherwise the derived value is `requires_review` with reason `currency_mismatch`.
2. **Status.** The status is `extracted` only if every input is `extracted`. Otherwise it takes the first applicable status in this order, with reason `missing_input` or the input's reason: `not_found` → `conflicting` → `requires_review`.
3. **Method choice is fixed, not a fallback by quality.** `EBIT-OP` is used whenever `operating_profit` is reported, even if it is `conflicting` or `requires_review`; in that case the derived EBIT inherits that status. `EBIT-PBT` is used only when `operating_profit` is `not_found`.
4. **Missing components.** If `borrowings_non_current` or `borrowings_current` is `not_found`, `total_borrowings` is `not_found`. A missing component is never assumed to be zero. A reported nil (FR-004.3) is a reported zero, not a missing component.
5. **Borrowing component classification (D-12).** `BORR-SUM` adds only **mutually exclusive** components. It classifies `current_maturities_long_term_borrowings`, using evidence on the balance-sheet pages, into one of four cases. Each classification and its evidence quote is recorded in `component_classification`.
   - **`included_in_current`:** a configured inclusion phrase (e.g. "including current maturities") appears in the `borrowings_current` row label. The amount is **not** added, which prevents double counting.
   - **`separate_component`:** the amount is presented as its own row, **and** a configured exclusion phrase (e.g. "excluding current maturities") appears in the `borrowings_current` or the current-maturities row label. The amount **is** added.
   - **`unresolved`:** the amount is presented as its own row, but neither case above is established. `total_borrowings` is `requires_review` (`borrowings_classification_unresolved`) and is excluded from calculations. All components, their evidence, and the ambiguity are recorded.
   - **`not_presented`:** no such row is found on the balance-sheet candidate pages. The derivation records `not_presented`. **How `total_borrowings` is treated in this case is open decision OD-9, and no default is specified.** OD-9 must be decided before Phase 3, which implements `BORR-SUM`.

   Inclusion and exclusion phrase lists are configurable and tuned only on the tuning set. Lease liabilities are never a component (D-07).
6. **Memo labelling.** Derived values are labelled `[CALCULATED]`, never `[SOURCE]`. The memo shows the formula and links each input to its own source evidence (Appendix B, Example 4).
7. **Tests.** Each method has unit tests for:
   - the all-`extracted` case;
   - each non-`extracted` input status;
   - method selection;
   - each of the four borrowing classifications;
   - a reported nil component.

---

## I. Financial Calculations

### I.1 Principles

- All arithmetic is done in Python using `decimal.Decimal`. The LLM never performs arithmetic.
- Inputs must have status `extracted` (source values, or derived values per H.5) and must share currency, basis, and period length.
- Every result is either a value or an explicit undefined status with one of these reason codes: `missing_input`, `input_conflicting`, `input_requires_review`, `zero_denominator`, `non_positive_base`, `not_meaningful_negative_equity`, `not_applicable_no_interest`, `currency_mismatch`, `period_mismatch`.
- Results are labelled `[CALCULATED]` and reference their input field IDs.
- **Calculation functions never change field statuses.** Plausibility checks (e.g. negative revenue) happen earlier, in FR-006.5. Metric functions still handle such inputs defensively, because they are pure and may be called directly in tests, and return the undefined reasons listed below.

**Derived input — EBIT.** EBIT is the derived field `ebit` (H.5): method `EBIT-OP` when `operating_profit` is reported, otherwise `EBIT-PBT`. The memo states which method was used.

### I.2 Metrics

#### MET-01 — Revenue growth

- **Formula:** (revenue_current − revenue_comparative) ÷ revenue_comparative × 100.
- **Inputs:** `revenue` (current and comparative), the same basis and currency, and consecutive 12-month periods.
- **Unit:** percent.
- **Edge cases:**
  - comparative revenue = 0 → undefined (`zero_denominator`);
  - comparative revenue < 0 → undefined (`non_positive_base`). This is defensive only: in the pipeline, negative revenue is already `requires_review` (FR-006.5), so the result is `input_requires_review`;
  - current revenue < 0 → undefined (`input_requires_review`), through FR-006.5;
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
  - revenue < 0 → undefined (`non_positive_base`). This is defensive only: in the pipeline, the result is `input_requires_review` (FR-006.5);
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
  - a negative input → undefined (`input_requires_review`). A negative balance-sheet total is implausible, so FR-006.5 marks the input `requires_review` before calculation.
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
- **Limitations:** "debt" is defined differently across institutions (with or without lease liabilities, or using total liabilities). Release 1 uses interest-bearing borrowings **excluding lease liabilities**, with no setting to change this (D-07). This is a documented choice, not a standard. A borrower with large leases will show a lower D/E than a definition that includes them, and the memo's limitations section says so.

#### MET-05 — Interest coverage ratio

- **Formula:** EBIT ÷ interest_expense.
- **Inputs:** `ebit` (derived, H.5) and `interest_expense`, for the same period.
- **Unit:** ratio (×).
- **Edge cases:**
  - interest expense = 0 → undefined (`not_applicable_no_interest`);
  - negative EBIT gives a valid negative ratio, flagged by RI-005;
  - negative interest expense → undefined (`input_requires_review`), through FR-006.5.
- **Acceptance tests:**
  - 300 / 100 gives 3.00;
  - −50 / 100 gives −0.50;
  - 300 / 0 is undefined (not applicable).
- **Limitations:** "finance costs" may include lease interest, unwinding of discounts, and FX differences, so it may not equal cash interest. EBIT derived from PBT inherits any one-off items.

### I.3 Period comparison

- Comparison-based rules (RI-001, RI-003, RI-004) need each metric for both the current and the comparative period.
- If either is undefined, the comparison is undefined, and the rule is `not_evaluable`.

### I.4 Configurable definitions

Recorded in the run manifest:

- statement basis (default `consolidated`; per-run override `--basis`, FR-014; never switched automatically, H.4.6).

Lease liabilities are always excluded from borrowings in Release 1; there is no setting for this (D-07).

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
- Each condition is evaluated independently, and the rule's result follows FR-008.2: any condition that fires triggers the rule, whatever is missing elsewhere. Each result carries the per-condition outcomes, values used, thresholds, missing inputs, and evidence references.

### J.2 Thresholds are provisional

> **The default thresholds below are illustrative placeholders chosen for demonstration and testing. They are NOT universal banking standards, regulatory requirements, or the policy of any institution.** Real thresholds vary by institution, industry, borrower size, and product, and must be set by the institution's credit policy. The memo states this wherever thresholds are shown.

### J.3 Release 1 rules

Each rule lists its conditions. A condition is evaluable only when its own inputs are available (FR-008.2).

| ID | Name | Conditions (provisional defaults) → severity if fired | Inputs each condition needs |
|---|---|---|---|
| RI-001 | Declining revenue | C1: revenue growth < 0% → `watch`; C2: revenue growth ≤ −10% → `elevated` | C1, C2: MET-01 |
| RI-002 | Negative net profit | C1: current-period `net_profit` < 0 → `elevated` | C1: current `net_profit` |
| RI-003 | Deteriorating liquidity | C1: current ratio < 1.00 (current period) → `elevated`; C2: current ratio fell by ≥ 10% relative to the comparative period → `watch` | C1: MET-03 current. C2: MET-03 current **and** comparative |
| RI-004 | Increasing leverage | C1: D/E rose by ≥ 20% relative to the comparative period → `watch`; C2: D/E > 2.00 (current period) → `elevated`; C3: `total_equity` ≤ 0 in either period → `elevated`, reason "negative or zero equity" | C1: MET-04 both periods. C2: MET-04 current. C3: `total_equity` only. C3 fires if any period with `extracted` equity is ≤ 0; it is `not_triggered` only if both periods' equity is `extracted` and > 0. |
| RI-005 | Weak interest coverage | C1: ICR < 1.50 → `watch`; C2: ICR < 1.00 (including negative) → `elevated` | C1, C2: MET-05 current. If MET-05 is `not_applicable_no_interest`, both are `not_triggered`, with a note. |
| RI-006 | Missing financial information | C1: any input that MET-01–MET-05 need is `not_found`, after the H.5 methods are applied → `info`. An optional source field such as `operating_profit` being absent does not count when its derived alternative is available. | Always evaluable |
| RI-007 | Conflicting or unverified source values | C1: any field is `conflicting` or `requires_review` → `watch` | Always evaluable |

**Examples of the result rule:**
- **RI-004 with negative equity and missing borrowings:** C1 and C2 are `not_evaluable`, but C3 fires, so the rule is `triggered` (`elevated`), with C1 and C2's missing inputs listed.
- **RI-003 with a current ratio of 0.84 and no comparative period:** C1 fires, so the rule is `triggered`.
- **RI-003 with a current ratio of 1.20 and no comparative period:** C1 does not fire and C2 cannot be evaluated, so the rule is `not_evaluable`, not `not_triggered`.

### J.4 Indicator explanation format

Each triggered indicator renders as follows (illustrative):

> **RI-003 Deteriorating liquidity — elevated** `[RULE]`
> Condition: current ratio < 1.00 (provisional threshold, configurable).
> Observed: current ratio as at 2025-03-31 (FY2025) = 0.84 `[CALCULATED: MET-03.2025-03-31]` from current assets 840.0 crore `[SOURCE: p.112]` ÷ current liabilities 1,000.0 crore `[SOURCE: p.112]`.

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
| `[CALCULATED: MET-xx]` | Computed deterministically by the platform from source values, including derived values (H.5), whose inputs are listed. |
| `[RULE: RI-xxx]` | Produced by a configured risk rule. |
| `[ANALYST-PROVIDED]` | Supplied in the (synthetic) borrower profile input; not verified against the document. |
| `[UNVERIFIED]` | A statement that could not be traced to evidence. Shown only with this label. |

`[AI INTERPRETATION]` is reserved for possible future LLM commentary and does not appear in Release 1 memos (FR-009.4, D-05).

### K.1–K.9 Sections

| # | Section | Content | Produced by |
|---|---|---|---|
| 1 | Borrower overview | Entity name, reporting currency, scale, statement basis, period ends `[SOURCE]`. Profile values (FR-014.7: borrower name, industry, facility requested, notes) `[ANALYST-PROVIDED]`, never used in calculations or rules. | Template |
| 2 | Documents reviewed | File name, SHA-256, page count, statement basis used and other bases present, candidate pages used (and any range pages without text), extraction date. | Template |
| 3 | Financial performance | Table of fields for both periods (source and derived), with status, page references, and derivation formulas. | Template |
| 4 | Financial ratios | Table of MET-01–MET-05 with values or undefined reasons, formulas, and inputs. | Template |
| 5 | Potential risk indicators | Triggered indicators (J.4 format), then `not_evaluable` rules with reasons. The provisional-threshold notice. | Template |
| 6 | Evidence and source references | One entry per source field ID: page, page label, line-item label, and verbatim quote. One entry per derived field ID: method, formula, and input field IDs. | Template |
| 7 | Missing information and conflicts | Every `not_found`, `conflicting`, and `requires_review` field, with reasons and candidate evidence. | Template |
| 8 | Questions for the credit analyst | Deterministic questions generated from sections 5 and 7 (e.g. "Revenue for the period ending 2024-03-31 not found on pages 110–115 — confirm the figure from the audited statements"). | Template |
| 9 | Limitations and human-review requirements | Fixed text: scope limits (text-based PDF, single document, no OCR, no currency conversion, no 52/53-week years, lease liabilities excluded from borrowings), the nil-dash convention (FR-004.3), metric limitations, provisional thresholds, LLM extraction limitations, and the statement that a qualified human must review and decide. | Template |

### K.10 Traceability rule

Material factual claims are numbers, dates, entity names, and statements about the presence or absence of items. Each one must carry a `[SOURCE]`, `[CALCULATED]`, `[RULE]`, or `[ANALYST-PROVIDED]` label that resolves to an ID in `results.json`. Otherwise it must be labelled `[UNVERIFIED]`. Automated tests check that every label in a generated memo resolves to an existing ID.

---

## L. Technical Architecture

### L.1 Approach

Release 1 is a **single-process, modular Python 3.12 package with a CLI** (FR-014). It is a linear pipeline of plain functions, with no agent framework, web server, database, or queue. Each stage has typed inputs and outputs, so each one can be tested in isolation:
- **Internal data** that the system creates itself (e.g. `FileInfo`, `PageText`, `LocatorResult`, metric results) uses frozen standard-library dataclasses. Ingestion is implemented this way.
- **Data validated from outside the program** — LLM output (FR-004) and evaluation ground-truth labels (O.2) — uses Pydantic v2 models, which also generate the JSON schema sent to the provider.

### L.2 Technology evaluation

| Technology | Release 1? | Role / rationale | When it becomes necessary |
|---|---|---|---|
| Python 3.12 | Yes | Project standard (`CLAUDE.md`). | Already in place. |
| uv | Yes | Dependency, lockfile, and environment management. | Already in place. |
| Git | Yes | Version control. | Already in place. |
| pytest | Yes (dev) | Test runner. | Already in place. |
| Pydantic v2 | Yes | Validation of LLM output and evaluation labels; generates the JSON schema for structured outputs (L.1). | Phase 2. |
| reportlab (BSD) | Yes (dev only) | Generates synthetic test PDFs at test time. Never a runtime dependency. | Already in place (Phase 1). |
| pdfplumber (MIT) | Yes | Page-level text extraction, behind a replaceable `TextExtractor` interface. See D-01. | Phase 1. |
| OpenAI Python SDK | Yes | Field extraction only, behind a `LLMProvider` interface with a fake implementation for tests. See D-02. | Phase 2. |
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
  - Page labels come only from the PDF's page-label metadata, read through pdfminer where defined (implemented in Phase 1). Numbers printed in page footers are not detected. Physical page numbers are always recorded.
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

**D-03 — Remove the "minimum share of candidate pages" text check (decided 2026-10-13, PRD v0.3)**

- **Problem:** the former FR-001.6 clause applied a validation-stage rule to candidate pages, which only exist after statement location. Keyword-selected candidates always contain text, so the rule could never fire for them.
- **Decision:** reject only when no page has text (FR-001.6, already implemented). For an analyst-supplied page range, reject when no page in the range has text (FR-013 rule 8).
- **Consequence:** no minimum-share setting exists, and nothing remains to be configured or disabled.

**D-04 — No statement pages found → fail, do not fall back to the whole document (decided 2026-10-13, PRD v0.3)**

- **Options considered:**
  - (a) Fail with `E-EXTRACT-NO-STATEMENT-PAGES` and suggest `--pages`.
  - (b) Send every page to the LLM.
- **Decision:** (a).
- **Why:** (b) could send hundreds of pages, breaking the SC-10/SC-11 assumptions and the "candidate pages only" rule in SEC-10 and NFR-09. It would also hide locator failures from evaluation.
- **Consequence:** documents whose statement headings are not covered by the phrase lists need a page range until the lists are extended.

**D-05 — Defer LLM-generated memo commentary beyond Release 1 (decided 2026-10-13, PRD v0.3)**

- **Why:**
  - It carries the highest risk of unsupported claims.
  - The Definition of Done (Section T) is met by the deterministic template alone.
  - There is no evidence in the project that commentary adds value analysts need.
- **Consequence:**
  - No LLM call happens after extraction.
  - SC-08 must be 0 in all sections.
  - `[AI INTERPRETATION]` is reserved.
  - FR-009.4 is kept as a starting point if this is reconsidered.

**D-06 to D-12 — Decisions approved by the project owner on 2026-10-13 (PRD v0.3 review)**

| ID | Decision | Specified in |
|---|---|---|
| D-06 | The configured statement basis is always respected. If it is absent, the run stops with `E-EXTRACT-BASIS-UNAVAILABLE`, and the analyst may re-run with `--basis`. No automatic fallback, and bases are never mixed. | H.4.6, FR-014.1, G.1 |
| D-07 | Lease liabilities are excluded from borrowings in Release 1, with no setting. Inclusion is a possible future enhancement. OQ-5 is closed for Release 1. | H.3, I.4, MET-04, F.2 |
| D-08 | A standalone dash or "nil" in a verified row and period column is a document-reported zero. The raw text is preserved. Blanks and unrecognised symbols are never zero. | FR-004.3, FR-005.6, H.1 |
| D-09 | Rule conditions are evaluated independently. Any condition that fires triggers the rule, and missing inputs elsewhere never suppress it. | FR-008.2, J.1, J.3 |
| D-10 | Row-label check (FR-005.10), with label lists extended only from tuning-set evidence. | FR-005.10, H.3, O.2 |
| D-11 | Period-end dates require title or header evidence in an unambiguous form, and are never guessed. The comparative period must end on the same month and day one year earlier. 52/53-week years are excluded. | FR-005.9, H.1.1, H.1.2 |
| D-12 | Borrowing components must be mutually exclusive. Current maturities are added only when evidence shows them to be separate; overlap that cannot be resolved gives `requires_review`. | H.3, H.5 rule 5 |

The same review approved, as specification only:
- the profile schema (FR-014.7);
- the cache policy (FR-003.5);
- the run ID format (FR-010.1).

The per-run token ceiling remains open (OD-8).

### L.3 Module responsibilities

| Module (proposed) | Responsibility |
|---|---|
| `cli` | Parse arguments, invoke the pipeline, map errors to exit codes. |
| `config` | Load and validate settings and the rules TOML; expose limits and defaults. |
| `pipeline` | Orchestrate stages, track processing state, write the manifest. |
| `ingestion` | File validation (FR-001), page text extraction (FR-002), statement page location (FR-013). |
| `llm` | `LLMProvider` interface, OpenAI provider implementation (D-02), a fake provider, retry/backoff, response cache, token/cost accounting. |
| `extraction` | Prompt construction (versioned prompts), structured-output parsing and validation (FR-003, FR-004). |
| `evidence` | Quote, value, row-label, period-end, period-column, sign, scale, and currency verification; number normalisation, including the nil convention; plausibility checks; reconciliation of duplicates and conflicts; statement-basis check (FR-004.3, FR-005, FR-006, H.1.2, H.4). |
| `models` | Shared data types: dataclasses for internal data, Pydantic models for LLM output (L.1). Ingestion currently keeps its own types in `ingestion/models.py`. |
| `calculations` | Derived values (H.5) and pure metric functions (FR-007). |
| `risk` | Rules engine and rule functions (FR-008). |
| `memo` | Deterministic memo assembly and origin labelling (FR-009). |
| `export` | Atomic writing of `memo.md`, `results.json`, `manifest.json` (FR-010). |

### L.4 Information flow

```
PDF file
  │  ingestion.validate_pdf        → FileInfo (hash, page count)          [FR-001]  (implemented)
  │  ingestion.ingest              → IngestedDocument (FileInfo + pages)  [FR-002]  (implemented)
  │  ingestion.locate_statements   → LocatorResult (candidate pages)      [FR-013]
  ▼
llm + extraction                   → raw LLM JSON → validated ExtractionResult  [FR-003/004]
  ▼
evidence.verify / reconcile        → list[FinancialField] with statuses   [FR-005/006]
  ▼
calculations                       → derived fields + list[MetricResult]  [H.5, FR-007]
  ▼
risk                               → list[IndicatorResult]                [FR-008]
  ▼
memo                               → Memo (structured) → Markdown text    [FR-009]
  ▼
export                             → memo.md, results.json, manifest.json [FR-010/012]
```

Only the `llm` module makes network calls, and only during field extraction. Every stage after extraction is deterministic.

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
| SEC-12 | **Resource limits when parsing untrusted PDFs.** File size and page count are limited (FR-001.2, .3), but compressed PDF content can expand well beyond the file size, and the PDF library has no built-in time limit. **Before any multi-user or network-exposed deployment (Phase 6 onward), PDF parsing must run under a per-document time limit and a memory limit**, failing with a catalogued error. For Release 1 (local CLI; public and synthetic inputs only) this is a **documented limitation**. Whether to implement a limit earlier is open decision OD-6. |

---

## N. Non-Functional Requirements

| ID | Quality | Requirement |
|---|---|---|
| NFR-01 | Accuracy | Meets the SC-01 to SC-08 targets on the evaluation set before Release 1 is declared complete, or the shortfall is documented with analysis. |
| NFR-02 | Traceability | Every value in the memo resolves to a field, metric, or rule ID. Every source field resolves to document, page, and quote (FR-005); every derived field resolves to its input field IDs (H.5, K.10). |
| NFR-03 | Reliability | Transient LLM failures are retried (FR-011.3). Partial extraction degrades gracefully. No crash produces output that looks complete. |
| NFR-04 | Maintainability | Small modules with single responsibilities. Type hints throughout. Configuration is separate from code. Each new dependency is justified in `PROGRESS.md`. |
| NFR-05 | Testability | Every module is testable without network access. The LLM is behind an interface with a fake implementation. Calculation and rule functions are pure. |
| NFR-06 | Reproducibility | Same inputs, configuration, code, and cache give identical outputs (FR-012.2). Dependencies are locked with `uv.lock`. |
| NFR-07 | Security | Section M requirements are met and tested where testable. |
| NFR-08 | Performance | Meets the SC-10 target. Text extraction and all deterministic stages complete in seconds for documents within limits. |
| NFR-09 | Cost control | Only candidate pages are sent to the LLM. Responses are cached (FR-003.5). Token usage and estimated cost are recorded per run. A per-run token ceiling aborts with `E-LLM-BUDGET-EXCEEDED` before overspending. **The ceiling's value, and whether it has a default, is open decision OD-8.** It must be decided before the first live LLM call in Phase 2. |

---

## O. Testing and Evaluation

### O.1 Automated tests

| Level | Scope | Examples |
|---|---|---|
| Unit | Pure functions and models | Metric edge cases (Section I); derived-value methods and status rules (H.5); rule trigger and threshold boundaries (exactly at threshold); number parsing (`(1,234)`, `1,23,456` Indian grouping); scale normalisation; quote, sign, period-column, scale, and currency verification (FR-005); locator rules (FR-013); schema validation. |
| Integration | Pipeline stages with a **fake LLM provider** and small synthetic PDFs | PDF ingestion and extraction on synthetic PDFs (FR-001, FR-002, FR-013); full pipeline with the fake provider produces `memo.md`, `results.json`, and `manifest.json`; missing and conflicting values flow to the memo. |
| Evidence validation | FR-004.3, FR-005, FR-006, H.1.2, H.4, H.5 against synthetic page text | Every `requires_review` reason has at least one positive and one negative case: the Appendix B examples and every row of B.6. |
| CLI end-to-end | FR-014 via subprocess | Exit codes 0, 1, 2, and each G.1 code; standard output and standard error contents; profile validation; `--basis` and `--pages` behaviour. |
| Regression | Golden outputs | (a) Page extraction of a fixed synthetic PDF, run in a fresh process, matches a committed golden output (FR-002.3). (b) A fixed synthetic PDF plus recorded LLM responses produce byte-identical `results.json` and `memo.md` (excluding timestamps). Any intended change updates the golden files in a reviewed commit. |
| Live (opt-in) | Real LLM provider | Marked and skipped by default (e.g. `pytest -m live`). Never run in the default suite, so `uv run pytest tests/ -q` needs no network or API key. |

Every behaviour is recorded in `tests/BEHAVIOURS.md` with its test and status, per `CLAUDE.md`.

**Test data:**
- **Synthetic PDFs** are generated at test time with reportlab (dev-only) into pytest's temporary directories, with byte-identical output enabled. They are not committed.
- **Recorded LLM responses and golden outputs** are committed under `tests/fixtures/`.
- **Real or public PDFs** are never committed.

### O.2 Evaluation dataset plan

- **Synthetic documents (planned: ~10):** generated programmatically with reportlab from known ground-truth values. They cover:
  - clean statements and missing fields;
  - conflicting values between highlights and statements;
  - mixed scales;
  - negative equity, zero interest, and losses shown in parentheses;
  - a note-reference column next to current and comparative columns;
  - consolidated plus standalone statements;
  - a contents page that names the statements;
  - a document containing prompt-injection text.

  Ground truth is known by construction.
- **Public documents (planned: ~5):** publicly available annual reports of non-financial companies, with varied layouts and currencies (including INR with lakh/crore scales). Ground truth (value, page, quote, statement pages) is **labelled manually and double-checked** by the developer. Public PDFs are **not committed** (licensing and repository size). The dataset stores source URL, retrieval date, SHA-256, and the labels.
- **Format:** one ground-truth JSON per document under `tests/eval/` (labels only), validated by Pydantic models (L.1).
- **Tuning versus held-out split:**
  - Each document is assigned to the **tuning set** or the **held-out set** *before* it is used for any adjustment, and the assignment is recorded in `tests/eval/` with the date.
  - Prompts, locator phrase lists, locator settings, and verification phrase lists are adjusted **only** using tuning-set documents.
  - Held-out documents are run only to produce release evaluation reports.
  - If a held-out document is inspected to debug a failure, it moves to the tuning set, and the next report says so.
  - Where available, the held-out set includes at least one INR report with lakh/crore scales and at least one report in another currency.
  - The exact split is recorded when OQ-3 is resolved; with ~5 public documents, both sets will be small, and results are reported as counts.

> **Uncertainty:** the specific public documents are not yet selected, and dataset sizes are planning estimates. Small datasets give wide uncertainty on percentage metrics, so results will be reported with counts (e.g. "43/46 fields"), not just percentages.

### O.3 Evaluation metrics and measurement

| Measure | Method |
|---|---|
| Extraction accuracy (SC-01) | Compare normalised values, scale, currency, and period to ground truth. |
| Hallucinated values (SC-02) | Count `extracted` fields with no ground-truth counterpart. |
| Not-found correctness (SC-03) | Ground-truth absent fields vs system status. |
| Evidence correctness (SC-04, SC-05) | Automated verification rate, plus counts of each `requires_review` reason. Cited page vs ground-truth page(s). |
| Statement-page recall (SC-12) | Candidate pages (FR-013) vs ground-truth statement pages, per document, reported as counts. |
| Calculation accuracy (SC-06) | Unit test pass rate over the specified cases. |
| Rule correctness (SC-07) | Unit test pass rate over the specified cases. |
| Unsupported claims (SC-08) | Automated label-resolution check, plus manual review of each evaluation memo using a checklist. |
| Failure rates (SC-09) | Error-scenario test pass rate. Run failure rate over the evaluation set. |
| Latency (SC-10) | Per-stage and end-to-end timings from the manifest. |
| Cost (SC-11) | Token usage × the provider's published price at measurement time, recorded with the date. |

**Establishing targets (baseline first).**
1. Run the pipeline on the **tuning set** and record counts for SC-01 to SC-05 and SC-12, plus the count of each `requires_review` reason.
2. Fix defects found in the tuning set only.
3. Propose targets from the measured baseline. The project owner approves them, and they replace the placeholders in E.2.
4. Run the **held-out set once** and report it against the approved targets.

Held-out results are never used to change prompts, label or phrase lists, locator settings, or rule thresholds.

The evaluation harness writes a dated report that states which documents were tuning and which were held-out. Only held-out results are presented as release results. **No performance claim is made in documentation, README, or memo until it is backed by a recorded evaluation report.**

Three kinds of evidence are kept separate, and none substitutes for another:
- **Software correctness** (automated tests pass) shows that the specified behaviour is implemented.
- **Extraction quality** (SC-01 to SC-05, SC-12 on held-out documents) shows how well the system reads real reports.
- **Product value** (whether analysts save time or trust the output) is not measured by this PRD; see the optional hypotheses in Appendix C.

---

## P. Repository Structure

Proposed structure. Items that exist as of PRD v0.3 are marked ✓. Nothing else is created until its phase.

```
ai-credit-intelligence/
├── CLAUDE.md                 ✓ Project rules for humans and AI assistants
├── PROGRESS.md               ✓ Phase checklist, decisions log, evaluation results
├── pyproject.toml            ✓ uv project definition and dependencies
├── uv.lock                   ✓ Locked dependency versions
├── .python-version           ✓ Python 3.12 pin
├── .gitignore                ✓ Excludes secrets, venvs, caches, private documents
├── .env.example                Placeholder environment variable names (Phase 2)
├── .cache/llm/                 Local LLM response cache (git-ignored; added with FR-003.5, Phase 2)
├── config/
│   ├── settings.toml           Limits, defaults, basis, locator settings, LLM model ID (when first loaded from file: Phase 2 or 5)
│   └── risk_rules.toml         Risk rules and provisional thresholds (Phase 4)
├── prompts/                    Versioned prompt templates (Phase 2)
├── docs/
│   ├── PRD.md                ✓ This document
│   └── decisions/              Short architecture decision records, as needed
├── src/
│   └── credit_intel/         ✓ Application package (src layout; uv_build backend)
│       ├── cli.py                (FR-014, Phase 5)
│       ├── config.py         ✓ Settings dataclasses (ingestion limits so far)
│       ├── pipeline.py
│       ├── models.py
│       ├── ingestion/        ✓ validation, extraction, errors, models (FR-001, FR-002); locator (FR-013) next
│       ├── llm/
│       ├── extraction/
│       ├── evidence/
│       ├── calculations/
│       ├── risk/
│       ├── memo/
│       └── export/
├── tests/
│   ├── BEHAVIOURS.md         ✓ Expected behaviours ↔ tests ↔ status
│   ├── conftest.py           ✓ Synthetic-PDF builders (reportlab, generated at test time)
│   ├── test_package.py       ✓ Package and Python-version checks
│   ├── unit/                 ✓ Unit tests
│   ├── integration/
│   ├── regression/             Golden outputs
│   ├── fixtures/               Recorded LLM responses and golden outputs (committed; no PDFs)
│   └── eval/                   Ground-truth labels, tuning/held-out assignment, evaluation harness
└── runs/                       Run outputs (git-ignored; added to .gitignore with the export step, Phase 5)
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
| **1 — PDF ingestion and extraction** | FR-001, FR-002, FR-013 | Phase 0 approved (including D-01). | pdfplumber is wrapped by the `TextExtractor` interface. Validation rejects every invalid case with the correct code. Page text extraction is deterministic and preserves page numbers. The statement locator meets FR-013's acceptance criteria 1–6 on synthetic fixtures. Statement-table text extraction has been checked against representative PDFs (D-01), with findings recorded, including how column order, note references, and parenthesised negatives survive extraction (input to OD-1). All tests pass. Behaviours recorded. |
| **2 — Structured financial extraction** | FR-003 to FR-006 | Phase 1 approved. OD-1 decided. OD-8 decided before the first live call. D-02 model availability and pricing verified. API data terms reviewed (SEC-10). `OPENAI_API_KEY` set in the local environment (not in Git). | Pydantic schema implemented. The fake provider supports offline tests. Evidence verification (FR-004.3, FR-005.1–.10, H.1.2), the basis check (H.4.6), plausibility checks (FR-006.5), and reconciliation are fully unit-tested, including Appendix B examples 1–3 and the relevant B.6 rows. The response cache follows FR-003.5. Statuses are correct on synthetic fixtures. Response caching works. Tuning/held-out assignment recorded. First small evaluation run on the tuning set recorded (counts, not claims). |
| **3 — Deterministic calculations** | H.5, FR-007 | Phase 2 approved (or the schema is stable enough to build calculations against fixtures). | Derived values (H.5) and all five metrics are implemented as pure functions. Every edge case in H.5 (including the four borrowing classifications) and Section I is tested and passing. `Decimal` is used throughout. |
| **4 — Risk indicators** | FR-008 | Phase 3 approved. | Rules load from TOML. All seven rules are tested at, below, and above thresholds, per condition, including the J.3 partial-evaluability examples. No scoring or decision output exists. |
| **5 — Credit memo generation and CLI** | FR-009 to FR-012, FR-014, G.1 → **Release 1** | Phase 4 approved. | Release 1 Definition of Done (Section T) met in full. |
| **6 — Interface and API** | FastAPI service and simple web UI | Release 1 complete. SEC-12 parsing limits implemented. | API exposes run submission and status/results. The same pipeline is reused. API tests pass. No new behaviour bypasses the evidence and labelling rules. |
| **7 — Evaluation, security, deployment** | Hardening and deployment | Phase 6 approved (or Release 1, if Phase 6 is deferred). | Expanded evaluation. Security review against Section M. Docker image builds and runs. Optional cloud demo deployed with secrets managed securely. |
| **8 — Optional extensions** | RAG assistant, LangGraph, AML support, authorised integrations | Phase 7 approved. A written justification exists for each extension. | Each extension has its own mini-PRD, acceptance criteria, and tests before implementation. |

---

## R. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Hallucinated values or claims** | Wrong figures presented as fact | Deterministic quote and value verification (FR-005). Memo produced entirely by template; no LLM commentary (D-05). Origin labels. `[UNVERIFIED]` label. SC-02 and SC-08 evaluation. |
| **Incorrect financial extraction** (wrong line item, period, sign, or scale) | Wrong ratios and indicators | Field definitions with explicit inclusions and exclusions (H.3). Row-label and section-heading check (FR-005.10). Period-end evidence (FR-005.9). Sign, period-column, scale, and currency verification (FR-005.6–.8). Plausibility checks (FR-006.5). Evaluation on held-out data. Analyst review of the evidence section. **Residual risk:** a row whose label matches the configured list but whose meaning differs (e.g. an unusual sub-total with a standard label) still passes; this is caught only by evaluation (SC-01) and analyst review. |
| **Table extraction errors** (columns merged or misaligned in text) | Values attributed to the wrong period | Period-column verification (FR-005.7) gives `requires_review` when column order cannot be established. Fixtures with multi-column layouts and note-reference columns. Method chosen on Phase 1 evidence (OD-1). Layout-aware extraction considered if evaluation shows a need. |
| **Derived values without traceable inputs** | Unverifiable EBIT or borrowings figures | Derivation records with input field IDs (H.5). Derived status follows its inputs. `[CALCULATED]` labelling. |
| **Pathological or malicious PDFs** (decompression bombs, very slow pages) | Hung or exhausted process | File size and page limits (FR-001). Documented limitation for Release 1. Time and memory limits mandatory before Phase 6 (SEC-12, OD-6). |
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
- OCR of scanned documents; non-English documents; quarterly or interim periods; 52/53-week reporting years; currency conversion; multi-document comparison.
- Financial-institution borrowers (banks, insurers, NBFCs).
- Web UI, REST API, database, Docker, and cloud deployment (planned for later phases).

---

## T. Definition of Done — Release 1

Release 1 is complete when **all** of the following are true and verified:

1. Given a supported financial PDF (Section F.1), the CLI (FR-014) produces `memo.md`, `results.json`, and `manifest.json`.
2. Every value in the memo is labelled by origin and resolves to evidence or a calculation or rule ID, or is labelled `[UNVERIFIED]`. The automated label-resolution test passes.
3. Missing, conflicting, and review-required values are identified and listed in the memo. None is silently resolved or used in calculations.
4. All five metrics and seven rules are implemented as specified, with every documented edge case tested.
5. Re-running with the same inputs, configuration, code version, and cached responses produces identical outputs (regression test passes).
6. Every error in the catalogue (G.1) has a passing test.
7. `uv run pytest tests/ -q` passes with no network access and no API key, and the result is reported truthfully.
8. An evaluation report exists with measured results against SC-01 to SC-12 on the held-out set (O.2), presented as counts and percentages, with shortfalls explained. No unmeasured claims are made.
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

## Appendix A — Open Questions and Open Decisions

### A.1 Open questions

| # | Question | Needed by | Status |
|---|---|---|---|
| OQ-1 | PDF extraction library and its licence. | Start of Phase 1 | **Resolved 2026-10-12:** pdfplumber (MIT) — see D-01. |
| OQ-2 | LLM provider and model. | Start of Phase 2 | **Resolved 2026-10-12:** OpenAI API, proposed baseline `gpt-4o-mini`, subject to verification — see D-02. |
| OQ-3 | Which public annual reports form the evaluation set, and their tuning/held-out assignment (O.2). | Phase 2 | Open |
| OQ-4 | Tool for generating synthetic PDF fixtures (dev-only dependency). | Phase 1–2 | **Resolved 2026-10-12:** reportlab (BSD), dev-only, installed in Phase 1 (recorded in `PROGRESS.md`). |
| OQ-5 | Whether lease liabilities should be included in borrowings by default for the demonstration. | Phase 3 | **Closed for Release 1 (2026-10-13):** excluded, with no setting (D-07). Inclusion is a future enhancement (F.2). |
| OQ-6 | Whether an analyst override file (resolving conflicts with a recorded rationale) should enter Release 1 or wait for a later release. | Phase 5 planning | Open |

### A.2 Open decisions

These cannot be responsibly settled without evidence the project does not yet have. The numbering follows the v0.3 review, whose items D2, D4, and D5 were decided and became D-03, D-04, and D-05.

| # | Decision | Options | Consequences | Evidence needed / needed by |
|---|---|---|---|---|
| OD-1 | How FR-005.7 maps a value to its period column | (a) **Order in text:** match the order of numbers in the quoted row to the order of period headers on the page. (b) **Word positions:** use word x-coordinates from the PDF to align values under headers. | (a) needs only page text but fails when a cell is blank or a dash, or when headers wrap. (b) is more robust to alignment but requires `TextExtractor` to return word positions, which is more code and a larger interface. In both cases, uncertainty gives `requires_review`, never a guess. | Commit 5 / D-01 findings on synthetic and public PDFs. Before Phase 2 starts. |
| OD-3 | Validation of the FR-013 initial settings and an SC-12 target | (a) Keep the initial values and set a target after measuring on the tuning set. (b) Adjust the values first, then set the target. | Setting a target before measurement would be arbitrary. Until a target exists, SC-12 is reported as counts only. | Public reports in the tuning set (OQ-3). Before the first evaluation report. |
| OD-6 | Implement SEC-12 parse limits before Phase 6? | (a) Documented limitation only in Release 1. (b) Run extraction in a subprocess with a timeout (works on all platforms; moderate complexity). (c) Signal-based timeout (Unix only; main thread only). | (a) is simplest but leaves a slow or hostile PDF able to hang a local run. (b) adds process management. (c) is not portable. | Timings from public-report runs. Mandatory by Phase 6 regardless. |
| OD-7 | Accept bytes before the `%PDF-` signature? | (a) Strict: the file must start with it (current). (b) Lenient: the signature must appear within the first 1,024 bytes, as many PDF readers allow. | (a) may reject some real PDFs. (b) admits more files to the parser, which still rejects non-PDF content as `E-INPUT-CORRUPT`. | Whether any public report fails (a). Revisit after the public-report check. |
| OD-8 | Per-run token ceiling (NFR-09): its value, and whether it has a default | (a) A required setting with no default; a missing value fails with `E-CONFIG-INVALID`. (b) A default value derived from measured tuning-set token counts and verified pricing. **Neither is adopted.** The owner's approval message for this item was incomplete. | No value is specified. Until decided, no live LLM call may be made (Phase 2 entry). | Verified pricing (D-02) and token counts from the tuning set. Before the first live call. |
| OD-9 | Borrowings when no separate current-maturities row is presented (H.5 rule 5, `not_presented`) | (a) Sum the presented borrowing lines, and disclose the absence in the derivation and the memo. (b) Mark `total_borrowings` as `requires_review`. **Neither is adopted.** | (a) gives D/E for the common Ind AS presentation, where maturities sit inside current borrowings, but cannot detect maturities placed under another caption. (b) is strictest, but would leave D/E undefined for most reports without a total line. | Before Phase 3. Public-report evidence on how maturities are presented. |
| OD-10 | A statement whose title names no basis (common for companies without subsidiaries) | (a) Keep basis `unknown` → `requires_review` (current specification). (b) Treat it as standalone **only** when the analyst passes `--basis standalone` explicitly and no statement is titled consolidated; record this in the manifest and disclose it in the memo header. | (a) makes such companies unprocessable. (b) relies on an explicit analyst assertion, never automatic. | Before Phase 2. |

## Appendix B — Worked Examples

All data is synthetic.

**Example 1 — Period column (FR-005.7).** Page 112 text:
```
Particulars                      Note   As at 31 March 2025   As at 31 March 2024
Total current assets              14          1,482.30              1,356.75
```
- **Mistake:** the LLM returns `current_assets` for period end 2025-03-31 with raw value `1,356.75`, which is the comparative figure.
- **Presence checks:** the quote is on the page and the value is in the quote, so FR-005.1 and .2 pass.
- **Column check:** the header order (note, 2025-03-31, 2024-03-31) places `1,356.75` in the 2024-03-31 column. FR-005.7 fails, so the status is `requires_review` with reason `period_not_verified`.
- **Same outcome if the LLM returns `14`:** that value sits in the note column.

**Example 2 — Sign (FR-005.6).** The row is `Profit/(loss) for the year   (245.10)   312.40`.
- **Mistake:** the LLM returns raw value `245.10`, parsed as +245.10.
- **Sign check:** the occurrence in the quote is enclosed in parentheses, so the value must be negative. The status is `requires_review` with reason `sign_mismatch`.
- **Correct case:** a raw value of `(245.10)` parsed as −245.10 passes.

**Example 3 — Scale (FR-005.8).** The page header says `(₹ in crore)`.
- **Mistake:** the LLM reports scale `lakh`.
- **Scale check:** no lakh declaration is found on the page or the statement's first page. The status is `requires_review` with reason `scale_not_verified`.
- **Two declarations:** if the page contained both "₹ in crore" and "₹ in lakh", the reason would be `scale_ambiguous`.

**Example 4 — Derived EBIT (H.5).** `operating_profit` is `not_found`. `profit_before_tax.2025-03-31.consolidated` = 352.70 and `interest_expense.2025-03-31.consolidated` = 38.50 are both `extracted` from page 114. The derived record:
```json
{"field_id": "ebit.2025-03-31.consolidated", "origin": "derived", "status": "extracted",
 "value": "391.20",
 "derivation": {"method_id": "EBIT-PBT",
                "formula": "ebit = profit_before_tax + interest_expense",
                "input_field_ids": ["profit_before_tax.2025-03-31.consolidated",
                                    "interest_expense.2025-03-31.consolidated"]}}
```
- **In the memo:** EBIT 391.20 crore `[CALCULATED]`, with the formula and both inputs linked to page 114.
- **If an input is not usable:** were `interest_expense` `requires_review`, `ebit` would be `requires_review` and MET-05 undefined (`input_requires_review`).

**Example 5 — Statement locator (FR-013).** With the initial settings:

| Page | Content | Matched phrases | Result |
|---|---|---|---|
| 3 | Contents: "Balance Sheet … 112", "Statement of Profit and Loss … 114" | 2 titles, 0 line items | Rejected (rule 3a needs ≥ 2 line items; rule 3b needs ≥ 4) |
| 112 | "Balance Sheet" with total non-current assets, total current assets, total assets, total equity, borrowings, total current liabilities | 1 title, 6 line items | Selected (score 3 × 1 + 6 = 9) |
| 113 | Untitled continuation: total non-current liabilities, total current liabilities, total equity and liabilities, borrowings | 0 titles, 5 line items ("total equity" is also present inside "total equity and liabilities") | Selected by rule 3b (score 5) |
| 114 | "Statement of Profit and Loss" with revenue from operations, total income, total expenses, finance costs, profit before tax, tax expense, profit for the year | 1 title, 7 line items | Selected (score 10) |
| 160 | Note 21 mentioning "revenue from operations" | 0 titles, 1 line item | Rejected |

Result: candidates 112, 113, 114, in page order. Pages 112–113 form one balance-sheet statement run, and page 112 is its first page (FR-013 rule 6).

### B.6 Behaviour example table

Synthetic inputs. Each row states the expected outcome and the requirement that decides it, and is intended to become at least one test. Amounts are in ₹ crore unless stated.

| # | Input | Expected outcome | Requirement |
|---|---|---|---|
| 1 | `revenue` 1,482.30 quoted from p.114 row "Revenue from operations", under header "Year ended 31 March 2025", "₹ in crore" on page | `extracted`; value 14,823,000,000 in base units; evidence p.114 | FR-005.1–.10 |
| 2 | LLM quotes text that is not on the cited page | `requires_review` (`evidence_not_verified`); excluded from calculations | FR-005.1, .3 |
| 3 | Column headers `31 March 2025` and `31 March 2024` | Period ends 2025-03-31 (current) and 2024-03-31 (comparative); both validated | FR-005.9, H.1.1 |
| 4 | Column headers `03/04/2025` and `03/04/2024` | Ambiguous dates, not guessed: all fields of both periods `requires_review` (`period_mismatch`); dependent metrics undefined | FR-005.9 |
| 5 | Header `2024-25`, and the same page's title says "for the year ended 31 March 2025" | Period end 2025-03-31, with raw text `2024-25` preserved | FR-005.9 |
| 6 | Comparative period ends 2023-03-31, current 2025-03-31 | Comparative fields `requires_review` (`period_mismatch`); MET-01 undefined (`period_mismatch`) | H.1.1 |
| 7 | Highlights page `1,235` vs statement `1,234.56` for the same field, period, and basis | Consistent (difference ≤ 0.5 crore); value 1,234.56; highlights kept as corroborating evidence | H.4.2 |
| 8 | Statement `1,234.56` vs another candidate page `1,198.20` for the same field, period, and basis | `conflicting`; both candidates listed with evidence; excluded from calculations; RI-007 C1 fires | H.4.6, FR-006.2 |
| 9 | Configured basis consolidated; only titles "Standalone Balance Sheet" etc. on candidate pages | Run stops before any LLM call with `E-EXTRACT-BASIS-UNAVAILABLE` ("bases found: standalone") | H.4.6, D-06 |
| 10 | Same document, re-run with `--basis standalone` | Standalone fields used; IDs end `.standalone` | FR-014.1, H.4.6 |
| 11 | Row "Total current assets 14 840,000 760,000" under "(₹ in thousands)" | Current value 840,000 × 10^3; note-reference `14` is not a value | FR-005.7, .8 |
| 12 | Row "Profit/(loss) for the year (245.10) 312.40"; LLM returns `245.10` | `requires_review` (`sign_mismatch`) | FR-005.6 |
| 13 | Row "Borrowings – 120.00" under "Current liabilities"; current-period column holds `–` | `borrowings_current` = 0, `value_interpretation = reported_nil`, raw `–` preserved | FR-004.3, D-08 |
| 14 | `borrowings_current` cell blank (no symbol), nothing proposed | `not_found`, never zero; `total_borrowings` `not_found`; MET-04 undefined (`missing_input`) | FR-004.3, H.5 rule 4 |
| 15 | Separate row "Current maturities of long-term borrowings 50.00"; current-borrowings label has no inclusion or exclusion phrase | `total_borrowings` `requires_review` (`borrowings_classification_unresolved`); MET-04 undefined | H.5 rule 5, D-12 |
| 16 | `operating_profit` and `interest_expense` both `not_found`; `profit_before_tax` `extracted` | `ebit` (EBIT-PBT) `not_found` (`missing_input`); MET-05 undefined; RI-005 `not_evaluable`; RI-006 fires | H.5, J.3 |
| 17 | `interest_expense` = 0 (or a reported nil) | MET-05 undefined (`not_applicable_no_interest`); RI-005 `not_triggered`, with a note | MET-05, J.3 |
| 18 | `total_equity` −40.00 (current); borrowings `not_found` | MET-04 undefined (`missing_input`); RI-004 C3 fires → `triggered` (`elevated`), C1 and C2 `not_evaluable` | MET-04, FR-008.2, J.3 |
| 19 | PDF whose pages contain only images or shapes | `E-INPUT-NO-TEXT-LAYER` ("OCR is not supported") | FR-001.6 |
| 20 | `--pages 5-7` where pages 5–7 have no text, but other pages do | `E-INPUT-NO-TEXT-LAYER` (page-range case) | FR-013 rule 8 |
| 21 | Current ratio 1.20, comparative not available | RI-003 C1 `not_triggered`, C2 `not_evaluable` → rule `not_evaluable` | FR-008.2, J.3 |

## Appendix C — Optional Improvements (not adopted in v0.3)

These were identified in the v0.3 review. They are **not requirements** unless a later revision adopts them.

1. **Financial-institution warning:** if the document looks like a bank, insurer, or NBFC statement (deterministic phrase rules), add a prominent memo warning that the ratios may not apply.
2. **Commercial hypotheses** to test before any commercial claim:
   - analysts spend significant time transcribing and drafting first-pass analyses;
   - values linked to evidence reduce review time compared with checking from scratch;
   - there is an accuracy level below which checking the output costs more than doing the work manually;
   - enterprise buyers need integration with loan-origination or financial-spreading systems, and data residency (likely excluding hosted LLMs for real data);
   - the buyer (credit-risk or IT leadership) differs from the user (analysts).
3. **Governance rule:** a commit that changes a decision also updates this PRD or `PROGRESS.md` in the same commit.
4. **Environment variable names** for the provider and model override in D-02 (for example `CREDIT_INTEL_LLM_MODEL`).
5. **Development hygiene:**
   - a dev-only coverage tool;
   - a shared fake extractor for tests;
   - a README.

## Revision History

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-10-12 | Initial draft for project-owner review. |
| 0.2 | 2026-10-12 | Resolved OQ-1 (pdfplumber, D-01) and OQ-2 (OpenAI API, `gpt-4o-mini` proposed, D-02); updated SEC-10, phase entry criteria, and risks; removed duplicated text in SEC-05 and Phase 5 exit criteria (now references to FR-011 and Section T). |
| 0.3 | 2026-10-13 | Approved by the project owner as a specification only (2026-10-13). **First review:**
- value checks for period, sign, scale, and currency (FR-005.6–.8);
- derived values (H.5) and ISO period IDs (H.1.1), replacing the former `revenue.FY2025.consolidated` format;
- statement locator FR-013 (formerly FR-002.6);
- CLI FR-014 and error catalogue G.1;
- tuning/held-out split (O.2);
- plausibility checks moved to FR-006.5;
- LLM commentary deferred (D-03 to D-05).

**Second review (owner decisions D-06 to D-12):**
- per-condition rule evaluation (FR-008.2, J.3);
- period-end evidence (FR-005.9, H.1.2);
- nil convention (FR-004.3);
- basis never switched automatically (H.4.6, new `E-EXTRACT-BASIS-UNAVAILABLE`);
- leases excluded, with no setting;
- borrowing component classification (H.5 rule 5);
- row-label check (FR-005.10);
- consecutive-period rule;
- profile schema (new `E-INPUT-PROFILE-INVALID`), cache policy, and run ID;
- system-at-a-glance table (B.1) and behaviour example table (B.6);
- SC-01, SC-03, and SC-05 relabelled as placeholders;
- RI-007 renamed "Conflicting or unverified source values" (same ID);
- open decisions OD-8 to OD-10 added, with no defaults adopted; OQ-5 closed for Release 1;
- the identifier change-log appendix removed (this entry replaces it). |
