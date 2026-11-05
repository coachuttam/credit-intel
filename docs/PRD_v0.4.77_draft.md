# PRD v0.4.77 — draft (repository publication: status, licence, known issues); approved by the owner on 2026-11-05 and applied to `docs/PRD.md`, with the proposal file marked superseded

Documentation and status only. No behaviour, requirement or threshold changes. `docs/PRD.md` is not touched until you approve.

## Edits to `docs/PRD.md` on approval
1. **Header and revision row 0.4.77** (version 0.4.76 → 0.4.77; Status line names this change).
2. **New decision OD-54, the repository licence:** MIT, copyright "2026 Uttam Kumar", in `LICENSE`. Consistent with D-01, which chose pdfplumber (MIT) to keep commercial use open. `pyproject.toml` is not changed (it is a frozen path of the held-out tool).
3. **Implementation status row:** the README's Status section now states the Phase 7b miss (0 of 12 on the latest round, 0 of 30 over three rounds), links `docs/PHASE7c_findings_report.md`, and says a second held-out round is planned before any accuracy claim. It also corrects two stale README statements: that the owner had not approved the release (approved 2026-10-26) and that the image had not been built or run (built and run by the owner on one real document, 2026-11-01; v0.4.67). The TLS proxy stays "written, not run".
4. **New `docs/KNOWN_ISSUES.md`,** linked from the README: two open defects found by informal manual cross-check on 2026-11-05 (`current_assets` showing `10000.00` against contrary evidence; `current_liabilities` citing the wrong balance-sheet line), not root-caused, not in the formal evaluation set. They are open items, not requirements.
5. **Repository hygiene:** `.archify/` and `docs/architecture/pipeline.*.json` (diagram-tool run output with absolute local paths) are git-ignored; `docs/PRD_v0.4_proposal.md` revisions 4–13 are committed as the owner's record, with one line added at its head saying it is superseded by `docs/PRD.md`.

## Tests
`tests/unit/test_readme.py`: the Status test now asserts the miss, the findings link and "none is claimed" instead of "not been evaluated".
