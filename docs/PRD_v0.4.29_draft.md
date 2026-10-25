# PRD v0.4.29 — draft amendment: older year-columns, a currency sign after a row label, and the currency quote (FR-005.7, FR-005.9, FR-005.10, FR-005.8)

| Item | Value |
|---|---|
| Status | **Adopted by the owner on 2026-10-25 ("adopt A and B, prompt only") and applied to `docs/PRD.md` as v0.4.29.** Kept as the record of the reasoning. The prompt file `extraction_v4` is a tuning change, not the default. |
| Drafted | 2026-10-25 |
| Evidence | Live round R2-1 and its free replays on tuning document R2 (`PROGRESS.md`, counts only), pages 36 to 38. Tuning set only (O.2). Nothing from H1 or H2. |
| Changes | A. FR-005.9 and FR-005.7: older year-columns of a statement with more than two periods (closes the "three-year statements" item deferred in FR-005.7 and in Section U, OD-1). B. FR-005.10, criterion 10: a lone currency sign after the label is not part of the label. C. FR-005.8 / prompt: no PRD change; a new prompt file, `extraction_v4`, for the owner's review. Appendix B.6 examples 62 to 67, Section U, Revision History. |
| Not changed | The verification order, the reason codes, which fields are extracted (current and comparative only), H.1.1, or any other criterion. No rule is loosened for a value to pass; each change makes a rule read what the page prints. |

## 1. Why: three stops found by counts on R2

After the five row-label phrases of R2 (committed `2308e1f`), the replay of R2's cached reply still extracts none of its 14 proposals. By counts and enum names only:

| Stop | Count | Cause |
|---|---|---|
| `period_not_verified` | 7 | The income-statement page has three year-columns. Two resolve to a period end; the third (two years before the current period) does not, so the page has an `unvalidated_anchor` and its whole structure is invalid. 8 proposals fail with `structure_invalid`. The balance-sheet page (two columns) is valid: 5 proposals pass the column check, 1 fails `cell_not_unique`. |
| `currency_not_verified` | 5 | The field-level check passes for all 14 proposals (code USD, a dollar sign on the cited page). The document attribute `reporting_currency` fails: its check reads only the model's evidence quote (FR-005.8), and the quote it gave carried no sign or code. Fields inherit that (H.1.2). |
| `label_not_recognised` | 2 | The row `Net income $ ...` has a currency sign between its label and its first figure; the label is "the text before its first figure" and a lone sign is not a figure, so the label read is `net income $`. |

None of these is fixed by a phrase list. Annual reports with more than two periods and a currency sign printed beside the first figure of a row are ordinary, so the same stops would meet any report laid out like R2 (including held-out ones); that is why these are rules and not R2 patches.

## 2. A. Older year-columns (FR-005.9, FR-005.7)

**Current text** (FR-005.9, the v0.4.13 bullet): a year-only or financial-year header is valid as the comparative only if its year is *exactly one year* before the validated current period; any other header "stays unvalidated". FR-005.7 lists "three-year statements" among the items deferred.

**Proposed bullet, added after the v0.4.22 bullet of FR-005.9:**

> - **Older year-columns (v0.4.29).** A statement may print more than two periods. A year-only or financial-year header that is *consecutively* earlier than the comparative is valid as an **older period**, with the same month and day: a header exactly two years before the current period is valid only if a header exactly one year before it is also on the page and valid, a header three years before only if the two-year header is valid, and so on. At most `extra_period_columns` (provisional setting, default 2) older periods are accepted on a page; a further header stays unvalidated. The condition of the previous bullets still applies: the current period is validated by a full date, and the current period does not end on 28 or 29 February. A header that is not part of an unbroken run of consecutive earlier years (a gap, a repeat, a later year, a different month) stays unvalidated and still makes the page structure invalid (`unvalidated_anchor`).
> - **Older periods are recognised, not extracted.** A column of an older period gets a column region so that cells are assigned to the right column, and it is recorded in the structure. No field is proposed or extracted for it: the fields stay current and comparative (H.3), and the consecutive-period rule (H.1.1) is unchanged.

**FR-005.7**, deferred line: remove "three-year statements" from the deferred items (the rest of the line stands).

## 3. B. A currency sign after the label (FR-005.10, criterion 10)

**Current text:** "The quoted row's label is the text before its first figure (a note reference counts as a figure)."

**Proposed text:**

> The quoted row's label is the text before its first figure (a note reference counts as a figure). **One currency sign standing alone between the label and the first figure is not part of the label (v0.4.29):** if the last word before the first figure is a currency symbol (a non-alphabetic entry of the configured currency tokens: `$`, `₹`, `€`, `£`, `¥`), it is removed before the label is compared with the configured phrases. Only that one trailing word is removed, only a symbol (never a currency name or code), and only at the end of the label; a sign inside the label, or any other trailing word, leaves the label as printed and the usual exact comparison applies.

## 4. C. The currency quote (FR-005.8): no rule change

The rule stays as it is: a currency is supported by a sign, code or name in the model's own quote. Loosening it to read the whole page would let the attribute pass on text the model never cited. The fix is a prompt change (tuning lever 1 of the live-round plan): `prompts/extraction_v4.md` differs from the default `extraction_v2` by its version line and one added bullet, which tells the model that a `reporting_currency` quote must itself carry the sign or code (a code, a name, or a row on which the sign stands beside a figure), that a unit line such as "In millions" does not support a currency, and to leave the attribute out when the page prints none. `DEFAULT_PROMPT` stays `extraction_v2` until the owner adopts another. A prompt change is a new cache key, so it needs one live call (about $0.001) to try; whether it works is not known until then.

## 5. Effects and risks

- **R2, expected after A and B (to be confirmed by a free replay once built):** page 36 becomes a valid structure, so its income-statement proposals reach the column check; the two `Net income` stops clear. Whether each then passes is not claimed. The currency stop is addressed only by the live round with prompt v4.
- **Risk of A:** a wrong extra column. It is bounded: the header must be a year token in an unbroken descending run that starts at the comparative, with the current period validated by a full date; anything else stays invalid. No field is extracted for the older column, so a mistaken older column could only mis-assign a cell if it overlapped a current or comparative column, which the existing column-overlap checks already refuse.
- **Risk of B:** a label that really ends in a sign is rare; the sign is dropped only for the comparison, and the quote stored is still as printed.
- **Existing tests:** the AC-OD1 fixtures that treat a third column as an unvalidated anchor must change to the new expectation; the negative cases (a gap, a repeat) stay.
- **Not in this amendment:** interest expense (R2 prints it, if at all, in a note), the three borrowings labels for R2, and the `cell_not_unique` stop on the balance sheet. Each is its own round.

## 6. New acceptance examples (Appendix B.6, to be added as 62 to 67)

| # | Case (synthetic) | Expected |
|---|---|---|
| 62 | Header "Year ended March 31, 2026 2025 2024" over a three-column statement; current period validated by the full date | Anchors 2026, 2025 and 2024 validate (2025 as the comparative, 2024 as an older period); the structure is valid; fields are proposed and checked for 2026 and 2025 only |
| 63 | Header "March 31, 2026 2025 2023" (a gap) | The 2023 anchor stays unvalidated (`unvalidated_anchor`); the page structure is invalid, as today |
| 64 | Header "March 31, 2026 2024" (no 2025) | The 2024 anchor stays unvalidated; as today |
| 65 | A header with five years, `extra_period_columns` = 2 | The first three later years validate, the fourth and fifth do not; the structure is invalid |
| 66 | Row "Net income $ 1,482.30 1,356.75", field `net_profit` | The label compared is `net income`; accepted. The quote stored is the row as printed |
| 67 | Rows "Net income $ before tax 1.00" and "Net income USD 1.00" and "Total $ income 1.00" | Not accepted: the sign is not the last word, the trailing word is a code, the sign is inside the label |

## 7. What I need from the owner

1. Adopt A, B and the setting `extra_period_columns` = 2, change them, or leave R2's income-statement fields out of the gate.
2. Agree that C is a prompt change only (`extraction_v4`, not the default) and the one live call it needs.
3. If adopted, I apply the PRD as v0.4.29 and then implement in two small steps (A, then B), each with tests, a free replay of R2, and your approval before any live call.
