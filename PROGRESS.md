# Progress

## Phase 0 — Project setup (2026-10-12)
- [x] Git repository initialised
- [x] `.gitignore` excluding virtualenvs, caches, secrets, and private financial documents
- [x] uv project on Python 3.12 (`pyproject.toml`, `.python-version`)
- [x] pytest added as a dev dependency
- [x] Placeholder test runs via `uv run pytest tests/ -q`
- [x] `CLAUDE.md` project rules
- [x] `PROGRESS.md` and `tests/BEHAVIOURS.md` trackers
- [x] `docs/PRD.md` v0.1 drafted (2026-10-12)
- [x] PRD v0.2: OQ-1 and OQ-2 resolved (2026-10-12)
- [x] PRD v0.2 reviewed and approved by project owner (2026-10-12; committed in `1b83722`) — Phase 0 exit criterion
- [x] PRD v0.3 approved by the project owner **as a specification only** (2026-10-13). Produced by a staged review (audit → diagnosis → revision) and a second audit; incorporates owner decisions D-06 to D-12. Approval covers what is to be built; implementation status is tracked below and in `tests/BEHAVIOURS.md`.

### Open questions from the PRD (see PRD Appendix)
- OQ-1 PDF library — **resolved**: pdfplumber (MIT), PRD D-01
- OQ-2 LLM provider/model — **resolved**: OpenAI API, `gpt-4o-mini` proposed, PRD D-02
- OQ-3 evaluation documents and tuning/held-out split — open
- OQ-4 synthetic-PDF tool — **resolved**: reportlab (dev-only), installed in Phase 1
- OQ-5 lease liabilities — **closed for Release 1** in PRD v0.3 (excluded, no setting; D-07)
- OQ-6 analyst override file — open
- Open decisions in PRD v0.3 (no defaults adopted): OD-1 (period-column method; before Phase 2), OD-3 (locator settings, SC-12 target; before first evaluation report), OD-6 (parse limits; by Phase 6), OD-7 (PDF header leniency; after public-report check), OD-8 (token ceiling — owner's approval message for this item was incomplete; before first live LLM call), OD-9 (borrowings when current maturities are not presented separately; before Phase 3), OD-10 (statements whose title names no basis; before Phase 2)

## Phase 1 — PDF ingestion and extraction (started 2026-10-12)
Scope: FR-001, FR-002, D-01 table-extraction check. Plan approved 2026-10-12.

- [x] Commit 1 — package layout (`src/credit_intel/`, `ingestion/`), `uv_build` backend, dependencies, licence notes
- [x] Commit 2 — validation and error codes (FR-001.1–.5, .7–.9); `E-INPUT-NO-TEXT-LAYER` defined, raised in commit 3
  - `ingestion/validation.py::validate_pdf` checks in order: readable → size → `%PDF-` signature → SHA-256 → parse/encryption → page count
  - Verified pdfplumber 0.11.10 behaviour before mapping errors: user-password PDFs raise `PdfminerException` wrapping `PDFPasswordIncorrect`; **owner-password-only PDFs open normally**, so encryption is detected via the document's `/Encrypt` entry; corrupt/truncated files raise `PdfminerException` wrapping `PDFSyntaxError`/`PSEOF`
  - Any exception raised by the PDF library while parsing the (untrusted) input maps to `E-INPUT-CORRUPT`; the original is kept as `__cause__` and its text is never shown to users. The broad `except` wraps only the two parsing calls (`pdfplumber.open`, page-tree load); our own code sits outside it, so programming errors surface instead of being reported as corrupt input (regression test included)
  - Known limitation: the file is opened several times (signature, hash, parse, later extraction). The SHA-256 identifies the bytes at hashing time; a file edited or replaced mid-run could be read differently by later steps. Inputs are assumed stable during a run; if enforcement is needed, read once and parse from in-memory bytes
  - Unreadable-file test simulates `PermissionError` instead of using `chmod`, which root and some containers bypass
  - Synthetic PDFs built with reportlab in pytest `tmp_path` (`tests/conftest.py`); none written to the repository
- [x] Commit 3 — page text extraction behind `TextExtractor` (FR-002.1–.5) and `E-INPUT-NO-TEXT-LAYER` (FR-001.6)
  - `TextExtractor.extract_pages()` added; pdfplumber code stays in `pdfplumber_extractor.py`
  - `ingestion/ingest.py::ingest` = `validate_pdf` → `extract_pages` → numbering check → no-text check; returns `IngestedDocument(file_info, pages)`
  - Text is stored exactly as pdfplumber's default `extract_text()` returns it (empty string for pages without text); no cleanup, so it stays usable as evidence
  - A page "has text" if it contains any non-whitespace character; the PDF is rejected only if no page has text
  - Page labels come from the PDF's `/PageLabels` metadata via pdfminer; an absent or malformed label tree gives `None` and never rejects the document
  - Python 3.12 check moved to `tests/test_package.py`; `tests/test_placeholder.py` removed
  - Limitations: (1) page labels are metadata, not printed footer numbers — many reports define none; (2) only pdfplumber's default (non-layout) text mode is used; column/table fidelity is assessed in commit 5 (D-01); (3) the former FR-001.6 "minimum share of candidate pages" clause is removed in the PRD v0.3 draft (D-03), so there is nothing further to implement for it; (4) extraction speed is not yet measured (SC-10)
- [x] Commit 4 — statement locator (FR-013) and statement-basis check (H.4.6), implemented 2026-10-13
  - `ingestion/locator.py`: `locate_statements` (rules 1–5, 7–8), `parse_page_range`, `statement_runs` (rule 6), `check_statement_basis` (H.4.6); works on `PageText` from ingestion, no second PDF parse
  - `config.LocatorSettings` holds the PRD's initial phrase lists and thresholds; new error codes `E-INPUT-PAGE-RANGE` and `E-EXTRACT-BASIS-UNAVAILABLE` (messages state what the user should do)
  - Tests: 85 new test cases (including parametrised cases) in `tests/unit/test_locator.py` (B-121–B-130); 15 deliberate bugs were introduced in a scratch copy and each made at least one test fail (two initially survived — missing title requirement and missing NFKC — and tests were added for both)
  - Owner-approved clarifications (2026-10-13): (1) a statement's basis (H.4.6) comes from its title block — the line(s) containing the title phrase, plus the line directly above or below only if it holds nothing but a basis word (e.g. "STANDALONE" / "(Consolidated)"); basis words elsewhere (company names, notes, other lines) are ignored; if the basis cannot be established it stays `unknown`, and absent consolidated evidence is never read as standalone; (2) whitespace is allowed around page-range numbers, hyphens, and commas but not inside a number (`1 - 10` valid, `1 0` invalid); (3) `LocatorResult.range_pages_without_text` is an approved additional output field: pages in the requested range without usable text, in ascending order, empty for keyword location
  - Limitations: (1) phrase lists and thresholds are **not validated on real documents** (OD-3); no statement-location accuracy is claimed; (2) `E-EXTRACT-NO-STATEMENT-PAGES` is not raised here — the locator returns an empty result and FR-003.7 (Phase 2) raises it; (3) settings are not yet loaded from `config/settings.toml`, and `--pages`/`--basis` are not wired to a CLI (FR-014, Phase 5); (4) the manifest and memo listing of range pages without text depends on FR-012/FR-009 (Phase 5); (5) a basis word on a separate line is recognised only when that line is directly adjacent to the title and contains nothing else; other layouts give basis `unknown`
- [ ] Commit 5 — D-01 table-extraction check: **synthetic half done 2026-10-13; public-report half not done**, so D-01 and the Phase 1 exit criterion are **not yet met**
  - Method: synthetic statement pages drawn with reportlab (right-aligned figure columns, note column, two-line and FY-style headers, section headings, wrapped labels, blank cells, nil dashes, bracketed negatives, Indian grouping, a landscape page with two statements side by side), passed through the project's `PdfplumberExtractor`; tolerance limits measured by varying spacing and offsets one at a time. Scratch scripts were not committed
  - Works (synthetic): aligned rows stay on one line with columns in order; `(245.10)`, `-`, `–`, `1,23,456.70` and note references are kept verbatim; two-line headers keep dates in column order; section headings stay on their own line; page text stays per physical page, so citations by page number are unaffected
  - Fails (synthetic, default settings): (1) a blank cell leaves no placeholder; (2) a figure more than 3pt off its row's baseline moves to its own line; (3) figures 3pt or less apart merge into one token; (4) letter spacing above 3pt splits a figure into characters; (5) side-by-side statements share text lines. Cases (3) and (4) make FR-005.2 fail, so such values become `requires_review` (safe). Cases (1) and (2) are the dangerous ones for OD-1 option (a): in case (2) the row reads `Borrowings 14 98,765.40`, and matching by text order alone could attribute the comparative figure to the current period
  - OD-1 evidence (**OD-1 remains open**): pdfplumber word positions placed both figures of case (2) under the correct column headers by horizontal position, so option (b) handled the case that defeats option (a). Word-position extraction is **promising on synthetic evidence only**; validation on real public reports is required before OD-1 is decided
  - Not tested: the `₹` symbol (reportlab's built-in fonts cannot draw it; the synthetic page extracted it as `n`), real fonts, kerning, scanned-then-OCRed text layers, and tables drawn as images
  - Limitation of the sample: synthetic layouts are idealised; tolerance thresholds are pdfplumber defaults (3pt) and real reports may differ. No claim is made about real-document extraction quality
- [ ] Public annual-report check (D-01, B-133) — **evidence collected 2026-10-13; awaiting project-owner review. D-01, OD-1, and the Phase 1 exit remain open.** Procedure: `docs/d01_public_report_checklist.md`; row-level text, renders, and logs are in git-ignored `private/d01/`
  - Documents (both **tuning set**, assigned 2026-10-13 before inspection; never to be used as held-out): R1 Infosys Integrated Annual Report 2024-25 (369 pages, Ind AS, ₹ crore, standalone and consolidated); R2 Microsoft FY2025 financial statements (80 pages, US GAAP, USD millions). Source URLs not yet recorded (owner to supply)
  - Pages inspected: R1 physical 194–197 (standalone) and 274–277 (consolidated); R2 physical 36 (income statements) and 38 (balance sheets). Expected values read from rendered pages
  - Ingestion: both OK with default settings; 46.4 s for R1 (369 pages), 16.0 s for R2 (80 pages); no PDF page labels in either; both start with `%PDF-`
  - Row results (34 rows classified; 2 fields not presented): **OK 28, SPLIT 4, LABEL-WRAP 2, MERGED 0, OFF-ROW 0, REORDERED 0, LOST 0**. All 4 SPLITs are in R2 (`88, 136`, `72, 361`, `268, 477`, `(4,901 )`); printed figures are intact on the rendered pages, so these are extraction splits. Under FR-005.2 they would become `requires_review` (safe, but unusable)
  - Faithfully extracted: `₹` (U+20B9), Indian grouping (`1,24,936`), Western grouping on R1's consolidated P&L as printed (`162,990`), brackets (`(963)`), nil `–`, decimal note references (`2.17`), and compound note references
  - Word positions (OD-1 evidence): every probed figure in both reports, and every SPLIT fragment, fell under the correct period header by horizontal position; decimal note references fell under "Note". **Caveat:** a naive nearest-column rule also assigned a number inside a wrapped label (R2 p38, `7,434`, far left of the figure columns) to the 2025 column, so a position-based method would need a maximum-distance rule. Promising, but two documents only — **OD-1 not decided**
  - Locator (OD-3 tuning evidence, no settings changed): R1 selected 6 of 8 statement pages, missed 197 and 277 (continuation pages with OCI/EPS only; no H.3 field), plus 3 false positives (p30 summary page; notes p263, p346). R2: **0 candidates** — plural titles ("BALANCE SHEETS", "INCOME STATEMENTS") fail the boundary rule and US line-item wording is not in the phrase lists
  - Basis: R1 standalone statements are titled without a basis word ("Balance Sheet"), so `--basis standalone` stops with `E-EXTRACT-BASIS-UNAVAILABLE`; R2 titles name no basis. Real evidence for OD-10
  - Label checks (FR-005.10 tuning evidence): R1 prints "Finance cost" (singular); R2 uses "Total revenue", "Operating income", "Income before income taxes", "Net income", "Total stockholders’ equity" (U+2019 apostrophe, not normalised by NFKC), and debt lines "Short-term debt" / "Current portion of long-term debt" / "Long-term debt" with no "non-current liabilities" heading. Proposals only; no lists changed
  - Specification gaps found (for owner decision; PRD unchanged): (1) FR-005.9 rejects the comparative year in the common header "As at March 31," / "2025 2024" (and "June 30, 2025 2024"), because a year-only header must equal the full date's year; (2) FR-005.9's "full date elsewhere on the page" could match the audit-signature date ("April 17, 2025" on R1 pp. 195, 197); (3) R2's income statement has three year columns, and PRD F.1 does not say how a third period is handled; (4) under D-12, R2's separately presented "Current portion of long-term debt" has no inclusion/exclusion phrase, so `total_borrowings` would be `requires_review`
  - No new synthetic test added: the SPLIT mechanism (spacing above the 3pt tolerance) is already characterised by B-132
  - What this sample cannot show: two reports show that failure modes occur, not how often; no extraction-accuracy figure is claimed

### Known gaps between the code and PRD v0.3 (recorded 2026-10-13)
- FR-002.3: determinism is tested within one process only (B-115); the fresh-process golden-output test PRD v0.3 requires does not exist yet (B-120, planned)
- G.1: no CLI exit codes exist yet (FR-014, Phase 5); the seven implemented input-error messages do not yet include the "what the user should do" text
- FR-001.6 page-range case and FR-013: implemented in commit 4 (see above); SC-12 recall not yet measured
- Fixed 2026-10-13: `CLAUDE.md` and `.gitignore` no longer describe committed fixture PDFs; the `tests/fixtures/` exceptions for PDF, XLSX, and CSV files were removed, so these file types are ignored everywhere

### Dependencies added (2026-10-12)
| Package | Version | Group | Licence (from installed metadata) | Pulled in by |
|---|---|---|---|---|
| pdfplumber | 0.11.10 | runtime | MIT | — (D-01) |
| pdfminer.six | 20260107 | runtime | MIT | pdfplumber |
| pypdfium2 | 5.14.0 | runtime | Apache-2.0 / BSD-3-Clause; bundles PDFium binary with permissive third-party licences (see below) | pdfplumber |
| pillow | 12.3.0 | runtime | MIT-CMU | pdfplumber, reportlab |
| charset-normalizer | 3.5.2 | runtime | MIT | pdfminer.six |
| cryptography | 50.0.2 | runtime | Apache-2.0 OR BSD-3-Clause | pdfminer.six |
| cffi | 2.1.1 | runtime | MIT-0 | cryptography |
| pycparser | 3.11 | runtime | BSD-3-Clause | cffi |
| reportlab | 5.0.1 | dev | BSD | — (synthetic test PDFs; resolves OQ-4 for now) |

Licence notes:
- No copyleft licence found among runtime dependencies.
- pypdfium2's bundled native libraries (abseil, AGG 2.3, fast_float, FreeType, ICU, Little-CMS, libjpeg-turbo, OpenJPEG, libpng, llvm-libc, PDFium, simdutf, zlib) all carry permissive licences. FreeType's FTL requires a credit in documentation if the software is redistributed.
- reportlab (dev only) ships a sample font (DarkGarden) under GPL alongside its BSD code; we do not use that font, and reportlab is never a runtime dependency.
- Licences were read from installed package metadata, not legal review.

## Decisions
- `uv init --bare` was used so no placeholder application code (`main.py`) was generated.
- Dependencies are installed only in the phase that needs them: pdfplumber added in Phase 1; OpenAI SDK deferred to Phase 2.
- Phase 1: `uv_build` build backend with `module-name = "credit_intel"` (copied from `uv init --package` output for uv 0.12.6) so the src-layout package is installed into the venv and importable by tests.
- PRD v0.1 key decisions: CLI-only Release 1; text-based PDFs only (no OCR); two annual periods; LLM extracts but never calculates; evidence quotes verified deterministically on the cited page; `Decimal` arithmetic; rules configured in TOML via stdlib `tomllib`; no composite risk score or credit decision; LLM self-reported confidence not used.
- **D-01 (2026-10-12): pdfplumber (MIT licence) for PDF text extraction.** Chosen over PyMuPDF (AGPL-3.0) to keep commercial use open. Wrapped behind a replaceable `TextExtractor` interface. Financial table extraction must be tested against representative PDFs in Phase 1. Installed in Phase 1 (0.11.10); transitive dependency licences confirmed — see Phase 1 "Dependencies added".
- **D-02 (2026-10-12): OpenAI API as initial LLM provider; `gpt-4o-mini` as proposed baseline model.** Availability, structured-output support, and pricing to be verified at the start of Phase 2. Provider and model are configurable. API key via `OPENAI_API_KEY` environment variable only, never in Git. Only public or synthetic financial data may be sent to the hosted API. No SDK installed, no `.env` created, and no API calls made yet.
