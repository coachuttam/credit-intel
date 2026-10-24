# OD-9 options note — total borrowings when no separate current-maturities row is presented

| Item | Value |
|---|---|
| Status | **Decided by the owner on 2026-10-24: Option C, applied in PRD v0.4.23.** Kept as the record of the options. |
| Drafted | 2026-10-24 |
| Blocks | Phase 3 step 3b (`total_borrowings` by `BORR-SUM`). The PRD says OD-9 must be decided before Phase 3 implements it. Steps 3a, 3c, 3d and 3e do not depend on it and are built. |
| Sources | `docs/PRD.md` (H.3, H.5 rules 4 and 5, D-12, MET-04, RI-004, Appendix A.2); the G5 gate (`PROGRESS.md`). No page of any report was read for this note. |

## 1. The question

When no total of borrowings is reported, the code derives it by adding mutually exclusive components: non-current borrowings plus current borrowings, and also current maturities of long-term borrowings **only when they are a separate row and shown not to be inside current borrowings** (D-12). H.5 rule 5 sorts that into four cases:

| Case | Meaning | Treatment today |
|---|---|---|
| `included_in_current` | A configured phrase ("including current maturities") sits in the current-borrowings label | Not added; specified |
| `separate_component` | Its own row, and an exclusion phrase ("excluding current maturities") is in a label | Added; specified |
| `unresolved` | Its own row, but neither of the above | `requires_review` (`borrowings_classification_unresolved`); specified |
| **`not_presented`** | **No such row on the balance-sheet pages** | **No treatment specified. This is OD-9** |

In the `not_presented` case the question is whether the sum of the two borrowing lines is the borrower's debt, or whether current maturities could be hiding under another caption.

## 2. Why it matters

- **Debt-to-equity (MET-04)** needs `total_borrowings`. Most reports do not print a total line, so for them this case decides whether MET-04 exists at all.
- **RI-004 (increasing leverage)** reads MET-04: C1 fires if D/E rose by 20% or more, C2 if D/E is above 2.00. A debt figure that is too low can make a rule fail to fire.
- **The direction of the possible error is the dangerous one for credit work.** If maturities sit under another caption and are left out, debt and D/E are **understated**, which is optimistic. Failing the other way, by marking more cases for review, only costs coverage.
- **The tuning gate.** The owner's gate requires borrowings to extract on both tuning reports and match hand-checked values. The treatment decides what "match" means for a report with no total line.

## 3. Options

### Option A — sum the presented borrowing lines and disclose (the PRD's option a)
`total_borrowings` = non-current borrowings + current borrowings, status `extracted`, `component_classification` = `not_presented`, and the absence is disclosed in the derivation and the memo.
- **Gives** D/E for the common presentation where maturities sit inside current borrowings (the usual Ind AS and IFRS layout). The PRD records this advantage.
- **Cannot detect** maturities placed under another caption, so it may understate debt.
- **Risk:** silent optimism, softened only by the disclosure text.

### Option B — mark `total_borrowings` as `requires_review` (the PRD's option b)
The derived total is `requires_review`, so MET-04 is `input_requires_review` and RI-004 cannot evaluate those conditions.
- **Strictest.** Never uses an unverified assumption.
- **Leaves D/E undefined for most reports without a total line**, which makes MET-04 and RI-004 mostly empty in practice. The PRD says so.

### Option C — Option A with a machine-visible caveat (new)
As A, but the derived total and MET-04 carry a named caveat (for example `borrowings_not_presented_assumption`), which the memo prints beside D/E and RI-004 repeats in its explanation: "total borrowings may exclude current maturities shown elsewhere". The value is used, and the analyst is told exactly what was assumed, in a field the code can test.
- **Keeps the coverage of A** and adds a visible, testable disclosure.
- **Cost:** a small addition to the metric result (a list of caveats), and one more thing for the memo to print in Phase 5.
- **Still understates** if maturities are elsewhere; it only makes the assumption visible.

### Option D — a setting (new)
A configured choice between the A/C behaviour and the B behaviour, with a stated default.
- **Gives the analyst control** per run.
- **Adds a setting the PRD does not have**, and a manifest entry. The PRD avoids settings for definitional choices (lease liabilities have none, D-07). I would not choose this unless you want per-run control.

## 4. What evidence would settle it

The PRD asks for public-report evidence on how current maturities are presented. The two tuning reports are public. Three questions, answered for each, would help; you can answer from the balance sheet in the report, and nothing else is needed:

1. **Is there a row for "current maturities of long-term borrowings" (or "current portion of long-term debt") by itself?**
2. **If not, does the current-borrowings row say that it includes them, or is there a note to that effect?**
3. **Is there a reported total of borrowings?**

Suggested pages (physical page numbers): R1 consolidated balance sheet, pages 274 and 275; R2 balance sheets, page 38. These are tuning documents, so reading them is allowed. I will not read them for this.

Two remarks on what to expect, from general knowledge and not from the reports: the US layout often prints "current portion of long-term debt" as its own row, which would fall in the `unresolved` or `separate_component` cases, not this one; the Indian layout usually includes current maturities in current borrowings, with the detail in a note.

## 5. Recommendation

**Option C.** It keeps the usable D/E that A gives, and answers the main weakness of A: the assumption is stated in the result, where the memo and the risk rule can show it, not buried in a derivation record. B is safer on paper but would leave the leverage metric and its rule nearly empty, which defeats the point of Release 1. D adds a setting without a need.

If you prefer the strictest reading while the evidence is thin, **B for now and revisit after the tuning round** is a defensible second choice. It can be loosened later without breaking anything, whereas tightening after reports have been produced would change results.

## 6. If you choose

- **A or C:** `BORR-SUM` in `not_presented` returns the sum, `extracted`, with the classification recorded (and, for C, the caveat). Tests: both lines present; a missing component gives `not_found` (H.5 rule 4, never zero); a reported nil is a zero, not missing; currency mismatch; the caveat present and absent.
- **B:** the same function returns `requires_review` with a new reason that H.1 does not list; **the reason list would need a PRD amendment** (for example `borrowings_not_presented`), since `borrowings_classification_unresolved` means a different case.
- **The phrase lists** for the inclusion and exclusion phrases (D-12) are needed for the other cases whichever you choose; they are tuning-set items.

I would write the PRD wording (v0.4.23) for your choice, as for the earlier amendments, before any code.

## 7. Decisions needed

1. Option A, B, C or D.
2. Whether you will answer the three evidence questions for R1 and R2, or decide without them.
3. Whether I draft the PRD wording (v0.4.23) for the chosen option.
