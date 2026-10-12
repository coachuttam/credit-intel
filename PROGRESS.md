# Progress

## Phase 0 — Project setup (2026-10-12)
- [x] Git repository initialised
- [x] `.gitignore` excluding virtualenvs, caches, secrets, and private financial documents
- [x] uv project on Python 3.12 (`pyproject.toml`, `.python-version`)
- [x] pytest added as a dev dependency
- [x] Placeholder test runs via `uv run pytest tests/ -q`
- [x] `CLAUDE.md` project rules
- [x] `PROGRESS.md` and `tests/BEHAVIOURS.md` trackers
- [ ] `docs/PRD.md` — awaiting the full PRD text from the project owner

## Phase 1
Not started. Awaiting review of Phase 0.

## Decisions
- `uv init --bare` was used so no placeholder application code (`main.py`) was generated.
- No runtime dependencies yet; AI and PDF-processing libraries will be chosen in a later phase.
