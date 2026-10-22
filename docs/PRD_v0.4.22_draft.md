# PRD v0.4.22 — draft amendment: the code derives the comparative period end (FR-005.9, H.1.2)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-22 ("1 yes, 2 requires_review, 3 keep, 4 yes") and applied to `docs/PRD.md` as v0.4.22.** Kept as the record of the reasoning. |
| Drafted | 2026-10-22 |
| Owner decision this rests on | "option b" (2026-10-22), chosen from the options after G5 run 3: have the code derive the comparative period end, not ask the model for it. |
| Changes | FR-005.9 (the derived-comparative bullet), H.1.2 (how a period-end attribute is evidenced), Appendix B.6 (examples), Revision History. No other requirement. |
| Evidence | G5 runs 2 and 3 on tuning document R1 and their offline replays (`PROGRESS.md`), counts only. Tuning set only (O.2). |

## 1. Why

Run 2 (prompt v2) extracted five current-period figures but proposed no comparative `period_end`, so the six comparative figures, each verified on the page, could not be placed. Run 3 (prompt v3) asked for it explicitly: the model then proposed one, but its quote was one character off the page, and the same change disturbed unrelated attributes (no scale, a wrong entity name), so nothing extracted. One sample per prompt cannot say why, and the comparative period end is not a judgement: when the current period end is proven and the page's column heading names the year before, the date follows. PRD v0.4.13 already derives that date from a validated current period. This amendment stops depending on the model to say it.

## 2. Current text (v0.4.21, FR-005.9, the derived-comparative bullet)

> A year-only or financial-year header whose year is exactly one year before the year of the validated current period is valid as the comparative period, provided the current period is validated by a full date. … The raw header text and the derived ISO date are both stored.

Today this validates a comparative the model proposed. If the model proposes none, the comparative period end stays `not_found` and every comparative figure is `requires_review`.

## 3. Proposed wording

Add to FR-005.9, after the derived-comparative bullet:

> - **Comparative derived by the code (v0.4.22).** The comparative period end is determined by the code, so it no longer depends on the model proposing it. When the current period end is validated (by a full date or by a year header validated under this criterion), the code looks for the comparative in the title or column-header block of each candidate page, in page order. A word in that block that is a year-only or financial-year token (the forms above) whose year (the later year, for `2024-25`) is exactly one year before the year of the current period end gives the comparative period end: the same month and day, in that year (D-11). The first such page is the comparative's evidence; its raw text is the token as printed, its quote is the header line that holds it, and the derivation is recorded in `validation`, as for a proposed comparative.
> - **Fails safe, as in v0.4.13.** A current period ending on 28 or 29 February, no validated current period, or no such token on any candidate page leaves the comparative unvalidated (`period_mismatch`). Only a token of exactly the previous year counts; several tokens that name that same year (`2024`, `FY2024`, `2023-24`) are one finding.
> - **A comparative the model proposed** is still checked as before and is used if it validates and equals the derived date. If it validates but differs from the derived date, the comparative is `requires_review` (`period_mismatch`), because two sources disagree. If it fails, the derived date is used and the failure is not an error. (The model is not asked to propose a comparative period end; this keeps replies from the earlier prompts valid.)

Change in H.1.2: a period-end attribute's evidence is "a quote from a title or column header on a candidate page, proposed by the model or, for the comparative, found by the code (v0.4.22)".

## 4. Effects

- **R1 under run 2 and run 3 replies:** the comparative period end would be derived from the year heading on pages 274 to 277. The six comparative figures in the run 2 reply were verified on the page (quote, value in quote, linking), so they should place and be checked against the comparative column. A free replay will show the counts.
- **Prompt:** none changes. `DEFAULT_PROMPT` stays `extraction_v2`. v3 stays a draft and is not adopted.
- **Risk:** a wrong comparative needs a validated current date and a heading that is exactly the previous year on a candidate page of the configured basis. Because pages of unknown basis are no longer sent, a heading cannot come from an unrelated statement. A three-column statement (a third year) is not made to work: the rule takes only the previous year.
- **Not in this amendment:** the scale attribute, the entity name, and operating profit's label; they are separate.

## 5. New acceptance examples (Appendix B.6, to be added as 34 to 38)

| # | Case | Expected |
|---|---|---|
| 34 | Current period 2025-03-31 validated by a full date in the header block; headers `2025` and `2024`; the model proposed no comparative period end | Comparative 2024-03-31, derived; raw text `2024`; the header line is the quote; comparative fields are placeable |
| 35 | Current period ending 28 February 2025; header `2024` | Comparative unvalidated (`period_mismatch`) |
| 36 | Current period validated; the only other header year on any candidate page is `2022` | Comparative unvalidated (`period_mismatch`) |
| 37 | The model proposed a comparative that validates and equals the derived date | Kept; one comparative, as before |
| 38 | The model proposed a comparative that validates but differs from the derived date | `requires_review` (`period_mismatch`) for the comparative period |
| 39 | The current period is not validated | No comparative is derived |

## 6. Tests, when approved (synthetic PDFs and page text, generated at test time)

One test per row 34 to 39; a property test that a derived comparative is always the same month and day one year before a validated current period and never exists without one; a pipeline test with a fake provider whose reply omits the comparative attribute and a check that the comparative fields place; and an offline replay of the cached R1 replies (v2 and v3), reported as counts only.

## 7. Revision History row (draft)

| 0.4.22 | (date of approval) | **Specification change to FR-005.9 and H.1.2, authorised by the project owner on (date)** ("option b", 2026-10-22). The comparative period end is derived by the code from a year heading exactly one year before a validated current period (same month and day), with the heading text and page as evidence; a model-proposed comparative is kept only if it equals the derived date, and a disagreement is `requires_review` (`period_mismatch`). Fails safe as in v0.4.13 (28 or 29 February, no validated current period, no such heading). Appendix B.6 examples 34 to 39 are added. Evidence: G5 runs 2 and 3 on tuning document R1, counts only. Nothing else changes. |

## 8. Decisions needed from the owner

1. Adopt the derivation as drafted, change it, or reject it.
2. When the model's comparative disagrees with the derived date: `requires_review` (as drafted), or trust the derived date and ignore the proposal.
3. Whether a model-proposed comparative should still be accepted when it validates and equals the derived date (as drafted), or be ignored altogether so the comparative never depends on the model.
4. Whether I apply it to `docs/PRD.md` as v0.4.22 on your word, then implement and replay.
