# CLAUDE.md — AI Credit Intelligence Platform

Project rules for anyone (human or AI) working in this repository.
Product requirements live in `docs/PRD.md`.

## Environment
- Python 3.12, managed with **uv**. Do not use pip, poetry, or conda directly.
- Add dependencies with `uv add <pkg>` (runtime) or `uv add --dev <pkg>` (dev only).
- Run tests with `uv run pytest tests/ -q`.

## How we work
1. **Make small changes.** One focused change at a time; keep diffs reviewable.
2. **Test every meaningful change.** Add or update a test alongside the change and run the suite before declaring it done. Never report a test as passing unless it was actually run.
3. **Preserve financial evidence.** Source documents and extracted figures must remain traceable: every number used in an analysis should link back to its source (document, page, line item). Never overwrite, mutate, or discard original inputs.
4. **Use deterministic Python calculations.** Financial ratios, totals, and scores are computed in plain, tested Python — never by an LLM. AI may extract or summarise, but arithmetic is deterministic and reproducible.
5. **Explain important engineering decisions.** Record the reasoning for non-obvious choices (in the PR/commit message, `PROGRESS.md`, or a short note in `docs/`).

## Data handling
- Never commit real financial documents, `.env` files, or secrets (see `.gitignore`).
- Use synthetic or anonymised fixtures under `tests/fixtures/` for tests.

## Tracking
- `PROGRESS.md` — what has been done, what is next.
- `tests/BEHAVIOURS.md` — expected system behaviours and their test status.
