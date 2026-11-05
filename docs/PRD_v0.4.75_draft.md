# PRD v0.4.75 — draft (a reason on every `not_found`); approved by the owner on 2026-11-05 with the three open points resolved, and applied to `docs/PRD.md` (examples 195 to 197); open points: (1) a period with no record stays a known gap, (2) `recognised_row_not_read` informs only, (3) the section 7 sentence is approved as written

The code follows in a separate step. It answers the owner's instruction of 2026-11-05 ("draft the PRD change for splitting not_found into 'not located in pages sent' vs. 'report presents none' where the code can tell … draft first, I review, then apply"). On your word I apply it, then build it (a change to the field set and the memo, with tests and mutation checks) as a separate step.

## 0. One thing the code cannot do, and the draft therefore does not promise

The code can never tell that **the report presents none**. A `not_found` field has no row with a recognised label on the pages sent; the report may print that row under a name the list does not know. The ablation of 2026-11-05 shows exactly this: with its own phrases removed, R2's rows read `not_found` though they are on the page. So the split I can draft honestly is by **what the code can tell about the pages sent**, in three cases, and "the report presents none" stays an analyst's judgement that the memo never makes for them. A feasibility probe on R1 and R2 (replayed from the cache, counts only): all 14 of their `not_found` records fall in the second case, which matches the owner's labels for them (absent); the first and third cases do not occur on these two documents, so the build will rely on synthetic pages for them.

## 1. The three reasons (new values of `status_reason`, used only with `status = not_found`)

| Reason | What the code can tell | Condition |
|---|---|---|
| `statement_not_in_pages_sent` | The statement the field is read from is not among the pages sent. | None of the pages sent has the field's statement type (income statement or balance sheet: H.3), by the locator's statement types, or for a page range by the locator's own page rules over the pages given (v0.4.74). |
| `no_recognised_row` | The statement is among the pages sent and none of its lines has a row label that the configured list accepts for the field. | At least one page of the field's statement type was sent and no line on those pages passes the row-label check (FR-005.10) for the field. **This does not say the report presents none; it may print the row under another name.** |
| `recognised_row_not_read` | A row with a recognised label is on the statement pages and the field was still not read. | At least one line passes the row-label check for the field and no value was proposed for the field and period, and none was added by the code's own scan (FR-005, v0.4.39, v0.4.40), for instance because the model returned nothing for it or because more than one such row was found. |

A `not_found` record that exists for another reason (a derived value whose input is `not_found`, H.5) keeps `status_reason` null, as today. A period with no validated period end still has **no record at all**, as today: that case (H5's `no_record`) is not covered by this draft, because a field ID needs the period end; it is listed as an open point below.

## 2. Edits to the PRD

- **H.1, the `status_reason` row.** Add `statement_not_in_pages_sent`, `no_recognised_row`, `recognised_row_not_read` to the list, and change "When status ≠ `extracted`" so that a `source` field with status `not_found` carries one of the three (a derived `not_found` and a `conflicting` field may still omit it).
- **H.2, the `not_found` row.** Meaning: "No value was found in the provided pages (or, for a derived value, an input is `not_found`). For a source value the reason says what could be told of the pages sent (below). **The system does not conclude that the report presents none.**" Add the table of section 1 below the statuses.
- **FR-004 criterion 2 and criterion 3** ("Missing expected fields are treated as `not_found`"; "It is `not_found` if nothing was proposed"): add "with the reason of H.2".
- **K.1–K.9, section 7 and section 8.** Section 7 shows, for a `not_found` field, the reason in words (as it already does for every reason: underscores read as spaces, so the words are the reason names) **plus one fixed sentence under the table: "‘No recognised row’ means no line on the statement pages has a label the system accepts; the report may print the row under another name."** The questions of section 8 for a `not_found` field keep their form and add the reason in brackets, as they do for the other statuses.
- **SC-03.** Unchanged: it still counts the fields the owner labels absent that are reported `not_found`. The reason is reported beside it, not instead of it (a labelled-absent field with `recognised_row_not_read` is a finding to look at, because a row the system recognises was on the page).
- **Appendix B.6.** Three examples, one per reason (a balance sheet only with `revenue` requested; a statement with no recognised row for `operating_profit`; a statement with two recognised rows for one borrowings component).
- **Where it is computed (not PRD text):** `extraction/missing.py` (`missing_fields`) gains the statement pages sent and their text, the locator result and the label settings; no new check is added to any other field.

## 3. Decision row (after OD-52)
| OD-53 | **Proposed 2026-11-05 (owner's instruction).** A reason on every source `not_found` | (a) Leave `not_found` without a reason. (b) Three reasons by what the code can tell about the pages sent (section 1). (c) A single flag "report presents none". | (b). (c) cannot be known to the code (section 0). (b) tells the analyst whether to look at other pages, at a differently named row, or at a row the system recognised and did not read. | For review; nothing built. |

## 4. Revision row 0.4.75 (when applied)
"**Specification change: a reason on every source `not_found`, authorised by the project owner on 2026-11-05.** Adds three `status_reason` values to H.1, H.2 and the memo, and one fixed sentence to memo section 7. **The effect, plainly:** the analyst learns, for a field that was not found, whether its statement was not among the pages sent, whether no line on it has a label the system accepts (which does **not** mean the report presents none), or whether a recognised row was there and not read. **Not changed:** any value, any status, any check, SC-03, the choice of pages. **Not covered:** a period with no validated period end, which still has no record."

## 5. Open points for the owner
1. **A period with no record.** H5's `no_record` is a field and period for which nothing exists because the period end was not validated. Giving it a record needs a period end for the field ID. Options: leave it; or show a memo line per period that says the period end was not validated and which attribute failed (no field record). I have not drafted either.
2. **Should `recognised_row_not_read` block anything?** As drafted it informs only. It could instead be `requires_review` (a recognised row exists, so the field is arguably not "not found"). That changes a status and the metrics that depend on it; I recommend against it in this version.
3. **Exact wording of the fixed sentence** in section 7 is yours to change.
