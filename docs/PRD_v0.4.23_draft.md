# PRD v0.4.23 — draft amendment: the `not_presented` case of `BORR-SUM` (OD-9, option C)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-24 ("yes to all four") and applied to `docs/PRD.md` as v0.4.23.** Kept as the record of the reasoning. |
| Drafted | 2026-10-24 |
| Owner decision this rests on | "C" (2026-10-24), from `docs/OD-9_options_note.md`: sum the presented borrowing lines, with a machine-visible caveat. |
| Changes | H.5 rule 5 (the `not_presented` bullet), MET-04 (a caveat on the result), FR-007 acceptance criterion 2, Appendix A.2 and A.3 (OD-9 row), Appendix B.6 (examples), Revision History. No other requirement. |
| Blocks | Phase 3 step 3b. |

## 1. Why

H.5 rule 5 sorts current maturities of long-term borrowings into four cases. Three have a treatment. `not_presented` (no such row on the balance-sheet pages) has none, and the PRD says it must be decided before Phase 3 implements `BORR-SUM`. The owner chose to sum the presented borrowing lines and to make the assumption visible in the result.

The assumption is that current maturities are not hiding under another caption. If they are, debt is understated, which is the optimistic error, and RI-004 (which reads debt-to-equity) could fail to fire. The caveat is therefore part of the value, in a form the code can test and the memo and the risk rule can print, not a sentence in a derivation record.

## 2. Current text (v0.4.22, H.5 rule 5)

> - **`not_presented`:** no such row is found on the balance-sheet candidate pages. The derivation records `not_presented`. **How `total_borrowings` is treated in this case is open decision OD-9, and no default is specified.**

## 3. Proposed wording

### H.5 rule 5 — replace the `not_presented` bullet

> - **`not_presented`:** no such row is found on the balance-sheet candidate pages. `total_borrowings` is the sum of `borrowings_non_current` and `borrowings_current` and records `component_classification = not_presented`. Rules 1, 2 and 4 apply as for the other cases: it is `extracted` only if both components are `extracted` and share a currency; a missing component makes it `not_found`, never zero; a reported nil is a zero, not a missing component. A derived value in this case carries the **caveat `borrowings_not_presented_assumption`**: "total borrowings may exclude current maturities of long-term borrowings shown under another caption." The caveat belongs to the value. Every metric that reads it repeats it (MET-04), the memo prints it beside the value (Section K), and the explanation of any risk rule that reads that metric (RI-004) includes it.

### MET-04 — add

> - **Caveats.** If `total_borrowings` is derived with `component_classification = not_presented`, the result carries the caveat `borrowings_not_presented_assumption` whatever its value, including 0.00. A reported total of borrowings carries no caveat. A comparison (I.3) of two MET-04 results carries the caveats of either.

### FR-007, acceptance criterion 2 — add

> Each result also lists any caveats, as stable identifiers. A caveat is not a reason: the result is still defined.

### Appendix A.2 and A.3 — OD-9

> Decided in v0.4.23: option C (sum the presented borrowing lines, with the caveat). Rows updated.

## 4. Effects

- **The case becomes usable.** Reports with no total line and no separate current-maturities row now give a debt figure and MET-04, labelled.
- **The error direction is stated, not removed.** A report that places current maturities under another caption still understates debt. The caveat tells the reader and the risk rule's explanation, which was the point of option C over option A.
- **No change** to the other three cases, to a reported total, to the missing-component rule, or to lease liabilities (D-07).
- **The tuning gate.** For a report with no total line, the derived total is compared with a hand-checked sum of the two presented lines.
- **Code affected when approved:** a new `calculations/borrowings.py` (`BORR-SUM`, the four classifications); `MetricResult` gains a `caveats` field and `compare` carries the union; `total_borrowings_for` offers the derived total when no total is reported. The inclusion and exclusion phrase lists (D-12) are configuration, tuned only on tuning-set documents.

## 5. New acceptance examples (Appendix B.6, to be added as 40 to 44)

| # | Case | Expected |
|---|---|---|
| 40 | No total line; non-current borrowings 700, current borrowings 300; no current-maturities row; equity 500 | `total_borrowings` 1,000, `extracted`, `not_presented`, caveat present; MET-04 = 2.00 with the caveat |
| 41 | A reported total of borrowings is present | Used as reported; no derivation, no caveat |
| 42 | No total line; current borrowings `not_found` | `total_borrowings` `not_found` (`missing_input`); no value, so no caveat |
| 43 | No total line; non-current borrowings a reported nil (a dash), current borrowings 300 | `total_borrowings` 300, `extracted`, caveat present |
| 44 | A separate current-maturities row with an exclusion phrase in a label | `separate_component`: added; no `not_presented` caveat |

## 6. Tests, when approved

One test per row 40 to 44; the other three classifications unchanged; the caveat present exactly when the classification is `not_presented`, absent for a reported total, and carried by MET-04 and by a comparison; a property test that the derived total is always the exact sum of its two components; a replay-free fixture check; and mutation checks on each rule.

## 7. Revision History row (draft)

| 0.4.23 | (date of approval) | **Specification change to H.5 rule 5, MET-04 and FR-007 criterion 2, authorised by the project owner on (date)** ("C", 2026-10-24; resolves OD-9). In the `not_presented` case `total_borrowings` is the sum of non-current and current borrowings, with `component_classification = not_presented` and the caveat `borrowings_not_presented_assumption`, which MET-04 repeats, the memo prints and RI-004's explanation includes. Rules 1, 2 and 4 are unchanged. Results list their caveats. Appendix A.2 and A.3 and Appendix B.6 examples 40 to 44 are updated or added. Nothing else changes. |

## 8. Decisions needed from the owner

1. Adopt the wording as drafted, change it, or reject it.
2. The caveat text and identifier (`borrowings_not_presented_assumption`): keep, or change.
3. Whether a caveat on a **zero** debt figure should stay (as drafted: whatever its value). A reported 0.00 is rare, and the assumption applies equally.
4. Whether I apply it to `docs/PRD.md` as v0.4.23 on your word, then implement step 3b.
