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

### Open questions from the PRD (see PRD Appendix)
- OQ-1 PDF library — **resolved**: pdfplumber (MIT), PRD D-01
- OQ-2 LLM provider/model — **resolved**: OpenAI API, `gpt-4o-mini` proposed, PRD D-02
- OQ-3 to OQ-6 — open; needed in Phases 1–5

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
  - Limitations: (1) page labels are metadata, not printed footer numbers — many reports define none; (2) only pdfplumber's default (non-layout) text mode is used; column/table fidelity is assessed in commit 5 (D-01); (3) the optional minimum text-share threshold (PRD FR-001.6, "share of candidate pages") is not implemented yet — it depends on candidate pages from the statement locator (commit 4) and is disabled by default; (4) extraction speed is not yet measured (SC-10)
- [ ] Commit 4 — statement locator (FR-002.6)
- [ ] Commit 5 — table-extraction check on synthetic PDFs (D-01)
- [ ] Public annual-report check (D-01) — **pending**: 1–2 public reports (ideally one Indian) to be placed in git-ignored `private/`; only findings are recorded, never contents

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
