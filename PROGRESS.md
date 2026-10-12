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

## Phase 1
Not started. Awaiting review of Phase 0.

## Decisions
- `uv init --bare` was used so no placeholder application code (`main.py`) was generated.
- No runtime dependencies installed yet; AI and PDF-processing libraries are chosen (D-01, D-02) but are installed only in the phase that needs them.
- PRD v0.1 key decisions: CLI-only Release 1; text-based PDFs only (no OCR); two annual periods; LLM extracts but never calculates; evidence quotes verified deterministically on the cited page; `Decimal` arithmetic; rules configured in TOML via stdlib `tomllib`; no composite risk score or credit decision; LLM self-reported confidence not used.
- **D-01 (2026-10-12): pdfplumber (MIT licence) for PDF text extraction.** Chosen over PyMuPDF (AGPL-3.0) to keep commercial use open. Wrapped behind a replaceable `TextExtractor` interface. Financial table extraction must be tested against representative PDFs in Phase 1. Not installed yet; transitive dependency licences to be confirmed at install time.
- **D-02 (2026-10-12): OpenAI API as initial LLM provider; `gpt-4o-mini` as proposed baseline model.** Availability, structured-output support, and pricing to be verified at the start of Phase 2. Provider and model are configurable. API key via `OPENAI_API_KEY` environment variable only, never in Git. Only public or synthetic financial data may be sent to the hosted API. No SDK installed, no `.env` created, and no API calls made yet.
