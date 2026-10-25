# PRD v0.4.33 — draft amendment: a bracketed expense in an "income (expense)" table is a positive expense (FR-006.5, FR-005.6)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25, limited to expense rows in "income (expense)"-type tables, and applied to `docs/PRD.md` as v0.4.33. Kept as the record of the reasoning.** One narrowing against the first draft: the heading must be within 8 lines above the row (the draft said anywhere above it on the page). |
| Drafted | 2026-10-25 |
| Evidence | Tuning report R2, Note 3 (physical page 49): the note's table is headed as "other income (expense)" and prints interest expense in parentheses. The owner's reference holds the expense as a magnitude (2,385 and 2,935 million). Tuning set only (O.2). |
| Changes | FR-006.5 (one exception, interest expense only), FR-005.6 (a note that the sign check is unchanged), the label settings (one phrase list), Appendix B.6 examples 75 to 79, Revision History. |
| Not changed | FR-006.5 everywhere else: a negative `interest_expense` with no such heading is still `requires_review` (`implausible_value`). The sign check of FR-005.6. Every other field. |

## 1. Why

A table of "other income (expense)" prints income as plain numbers and expense in brackets: the bracket means "an expense", not "a negative amount of interest expense". Today the pipeline reads the bracket as a minus (FR-005.6, correctly: the page shows a bracket and the value must be negative), and then FR-006.5 marks a negative `interest_expense` as implausible and clears it. So a correctly read interest expense from such a table can never be used, and the gate cannot match R2's value.

## 2. Proposed text (narrow)

Add to FR-006.5, after the sentence that lists the negative values that are implausible:

> **One exception (v0.4.33).** A bracketed (negative-marked) figure on a row read as `interest_expense` is a positive expense, and its value is stored as the magnitude, when the row is under a heading that marks the table as one of income and expense. A heading is a line **within the 8 lines above the row** (provisional setting `expense_heading_window`), with no figure on it, whose casefolded text contains one of the configured phrases (provisional: `income (expense)`, `(expense) income`, `income/(expense)`, `(expense)/income`, `income and expense`). A phrase further up the page does not count, so a second table on the page is not covered by the first one's heading. The raw value stays as printed, the sign check of FR-005.6 is applied first and is unchanged (the model's raw value must show the bracket that the page shows), and the record notes that the magnitude rule was applied. Nowhere else does a bracket change into a positive amount: a negative `interest_expense` with no such heading, and every other field, stay as FR-006.5 says.

The phrase list is a setting (`LabelSettings.expense_table_headings`), extended only from tuning-set evidence (O.2).

## 3. Effects and risks

- **R2:** the interest expense from Note 3 becomes usable, both periods, once the note's page is part of the run; whether it then matches is for the gate.
- **A wrong flip:** an interest *income* row mistaken for interest expense would be stored as a positive expense. The label check (FR-005.10) still has to accept the row's label as an interest-expense phrase first, so income rows ("interest and dividends income") are not read as this field.
- **Narrow by design:** only `interest_expense`; only under a heading with one of the phrases; the bracket must be on the page. A heading missing from the phrase list leaves the old behaviour (`requires_review`), which fails safe.
- **Unchanged:** the memo shows the printed value; the value used in the coverage ratio is the positive expense.

## 4. Acceptance examples (Appendix B.6, to be added as 75 to 79)

| # | Case (synthetic) | Expected |
|---|---|---|
| 75 | Table headed "Other income (expense), net"; row "Interest expense (2,385)"; model returns raw `(2,385)` | `extracted`, value `2385`, raw value as printed, the record notes the rule |
| 76 | The same row under a heading with no such phrase (for example "Finance costs"), or whose only such heading is more than 8 lines above | `requires_review` (`implausible_value`), as today |
| 77 | The same table, row "Interest and dividends income 4,100" read as `interest_expense` | not accepted: the label is not an interest-expense phrase |
| 78 | The same table, the row printed without brackets (a plain positive figure) | `extracted`, value as printed, no rule applied |
| 79 | The same table, a field other than `interest_expense` printed in brackets | the field's own rules apply; nothing changes |

## 5. What I need from the owner

1. Approve, change or reject section 2 (including the five phrases).
2. If approved, I apply the PRD as v0.4.33 and implement it in one step with tests, then add the note page to R2's run.
