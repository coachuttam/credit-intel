# PRD v0.4.20 — draft amendment to FR-005.9 (period-end evidence)

| Item | Value |
|---|---|
| Status | **Items A and B approved by the owner on 2026-10-20 and applied to `docs/PRD.md` as v0.4.20; Item C deferred until A and B are replayed.** Kept as the record of the reasoning. |
| Drafted | 2026-10-20 |
| Changes | FR-005.9 (criterion 9 of FR-005), Appendix B.6 (new examples), Appendix A.3 (gap 2 row), Revision History (new row). No other requirement. |
| Evidence | The G5 first run on tuning document R1 and its offline diagnosis (`PROGRESS.md`, "G5 first run" and "G5 offline diagnosis"), counts only, plus the owner's confirmation of 2026-10-20 that the only full date on R1 physical page 195 is the signing date. Tuning set only (O.2). |
| Approval needed | The owner's choice on each of the three items below. The assistant implements nothing until then. |

## 1. Why

Two gaps in FR-005.9 as written (v0.4.13) showed up on the first real tuning document:

1. **A full date that wraps across lines is not read as one date.** On R1, the model proposed a full period-end date that occurs once on physical page 194 but on no single line of its text. The "raw text is in a title or column header" check and the page scan for full dates both work line by line, so neither saw it. Four of R1's nine candidate pages (194, 196, 274 and 276) were left without a validated period and without columns, because the page scan finds no full date on them, and every field proposed from them failed. Only page 194 was shown to hold a wrapped date; why the other three have no scannable date was not examined (no page text was read).
2. **The year-only rule accepts any full date "elsewhere on the same statement page".** On R1 physical page 195 the page's only full date is the signing date. The headers `2025` and `2024` were validated by it, so the columns were given period ends 17 days after the real one (and a year before that). This is B-133 specification gap 2 (Appendix A.3), now seen on a real page. In the run it failed safe, because the model claimed the true period end and the columns did not match it. It would not fail safe if a model claimed the signing date as the period end, since the verifier would then confirm a wrong period.

## 2. Current text (v0.4.19, bullet 4 of criterion 9)

> a year-only or financial-year header (`2025`, `FY2025`, `2024-25`, `FY 2024-25`), **only** if a full date in an accepted form appears elsewhere on the same statement page, and the header's year (the later year, for `2024-25`) equals that date's year.

## 3. Proposed wording

### Item A — a full date may wrap across lines (recommended)

Add to the list of accepted forms, after the bullets:

> A written or numeric full date whose words are on consecutive lines of the same title or column-header block is read as one date, in word order, provided the lines are adjacent (no other line between them) and the block is the one the date's quote cites. The stored raw text is the date as quoted, with its line break normalised to a single space for matching (FR-005.2 matching is unchanged). Nothing is joined across a page boundary or across a figure line.

### Item B — which date may validate a year-only header (recommended; closes gap 2)

Replace bullet 4 with:

> a year-only or financial-year header (`2025`, `FY2025`, `2024-25`, `FY 2024-25`), **only** if exactly one full date in an accepted form, with the header's year (the later year, for `2024-25`), appears **in the title or column-header block of the same statement page** (the text above the page's first figure line, as for the period-end quote itself). A full date elsewhere on the page, for example in a signature block, an approval statement or a note, validates nothing. If the block holds two different full dates of that year, or none, the header is not validated (`period_mismatch`); it is never guessed.

### Item C — a continuation page's year-only headers (optional; owner's choice)

Statements often run over several pages and a later page repeats only the year headers (R1 pages 195 and 197 look like this by their counts: validated year headers, a single full date, and, for 195, that date being the signing date; where the statement's real date sits was not examined). With Item B alone such a page has no full date of its own in its block, so its year headers stay unvalidated and its fields stay `requires_review` (`period_mismatch`). That is safe but loses the page. If the owner wants it recovered:

> A year-only or financial-year header on a page that continues a statement run (FR-013 rule 6) is also validated if the header's year equals the year of a current period-end that is validated by a full date in the title or column-header block of **the first page of the same statement run**, and no other full date of that year is in either block. The raw text and the page from which the date was taken are stored in `validation`.

I recommend including Item C only after Items A and B are replayed, because the replay will show how many fields it would recover. Without C the behaviour is conservative and the loss is visible as counts.

## 4. Effects

- **No change** to: the ambiguous numeric date rule, the comparative derivation of v0.4.13 (it still needs the current period validated by a full date), the 28/29 February rule, the consecutive-period rule (H.1.1), or any reason code.
- **Fail-safe direction:** every new restriction (B, and C's "no other date") only moves a period from validated to `period_mismatch`. Item A moves some from `period_mismatch` to validated only when the whole date is genuinely in the header block.
- **Appendix B.6, example 22** (header "As at March 31," over `2025` and `2024`, the same statement page showing a full date): still valid, provided that full date is in the title or header block, which in that example it is. The example text is clarified to say so.
- **Code affected** (when approved): the page scan `find_full_dates` and the period resolver (`periods.py`), the header-line check in `attributes.py`, and the anchor search in `columns.py`. All are deterministic and tested on synthetic pages.

## 5. New acceptance examples (Appendix B.6, to be added)

| # | Page | Expected |
|---|---|---|
| 23 | Title "Balance sheet as at March 31," and, on the next line, "2025"; headers `2025`, `2024` below | Item A: one full date, current period 2025-03-31; comparative derived 2024-03-31 (v0.4.13). |
| 24 | Year headers `2025`, `2024`; the only full date on the page is in a "Signed on behalf of the Board … April 17, 2025" block below the figures | Item B: not validated; both periods `period_mismatch`. A claimed period of 2025-04-17 is also refused. |
| 25 | Year headers `2025`, `2024`; the title block holds two different full dates of 2025 | Not validated (`period_mismatch`), never guessed. |
| 26 | A wrapped date whose two halves have a figure line between them | Not joined; not validated. |
| 27 | (Item C, if adopted) Page 2 of a statement run has headers `2025`, `2024` and no date; page 1's title holds "March 31, 2025" | Page 2 periods validated from page 1's date; the page recorded in `validation`. Without C: `period_mismatch`. |

## 6. Tests, when approved (synthetic PDFs generated at test time)

One test per row 23 to 27, one regression for example 22, a property test that no page whose block holds no full date can ever validate a year-only header under Item B, and a replay of the cached R1 reply (offline, no spend) reported as counts only.

## 7. Revision History row (draft)

| 0.4.20 | (date of approval) | **Specification change to FR-005.9, authorised by the project owner on (date).** (A) a full date wrapped across adjacent lines of a title or column-header block is read as one date; (B) a year-only or financial-year header is validated only by exactly one full date of its year in the title or column-header block of the same page, not by a date elsewhere on the page (resolves B-133 specification gap 2); (C) [adopted / not adopted] a continuation page's year-only headers may be validated by the first page of the same statement run. Evidence: the G5 first run on tuning document R1, counts only. Appendix A.3 gap 2 and Appendix B.6 are updated. Nothing else changes. |

## 8. Decisions needed from the owner

1. Item A: adopt as worded, change, or reject.
2. Item B: adopt as worded, change, or reject.
3. Item C: adopt now, adopt after the replay of A and B, or not at all.
4. Whether the amendment is applied as v0.4.20 in `docs/PRD.md` by the assistant on the owner's word, or edited by the owner.
