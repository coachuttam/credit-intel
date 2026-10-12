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
- [ ] Commit 2 — validation and error codes (FR-001)
- [ ] Commit 3 — page text extraction behind `TextExtractor` (FR-002.1–.5)
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
