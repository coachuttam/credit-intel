# PRD v0.4.32 — draft amendment: a report that presents no borrowings is `not_found`, and the gate can say so (H.5 rule 4, the gate reference)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("approve v0.4.32") and applied to `docs/PRD.md` as v0.4.32.** Kept as the record of the reasoning. The gate's reference form is not yet implemented. |
| Drafted | 2026-10-25 |
| Evidence | The owner's hand check of tuning report R1 (2026-10-25): the consolidated balance sheet (physical page 275) shows lease liabilities and no borrowings, and page 307 states that there are no outstanding borrowings. |
| Changes | H.5 rule 4 (one sentence added, no behaviour changed), Section F.2 (leases named as a future field), the gate reference format and its match rule (`docs/gate_round_guide.md` and `evaluation/gate.py`), Appendix B.6 examples 72 to 74, Revision History. |
| Not changed | Any extraction, verification, derivation or metric. A statement-evidenced zero is **not** introduced. |

## 1. Why

The gate asks for total borrowings on both tuning reports. R1 presents none. Today a report with no borrowing line already gives `total_borrowings` as `not_found` with reason `missing_input` (H.5 rule 4: a missing component is never assumed to be zero), and the debt-to-equity ratio is undefined for that reason. So the behaviour the owner wants exists. What is missing is a way for the owner's reference to say "none presented", because the reference format requires a figure for every entry, so R1 cannot currently be written down.

## 2. Proposed text

**H.5 rule 4**, add after the last sentence:

> A report that presents no borrowing line at all leaves `total_borrowings` `not_found` (reason `missing_input`) in both periods. It is never zero, including when a note states that there are no outstanding borrowings: reading that statement as a zero is not part of Release 1. Lease liabilities are not borrowings and are not added (they stay excluded, as in rule 5); a separate lease-liabilities field is a possible later addition and is not part of Release 1.

**F.2 (out of scope for Release 1)**, add a line: "A lease-liabilities field (a separate field, never added to borrowings)."

**The gate reference** (`docs/gate_round_guide.md`, `evaluation/gate.py`; the gate is an evaluation tool and is not a requirement of the product): an entry for `total_borrowings` may be written `{"field": "total_borrowings", "period": ..., "period_end": ..., "presented": false}` instead of a figure. Match rule for such an entry:

- `match` if the derived `total_borrowings` is `not_found` and no borrowing component (`borrowings_non_current`, `borrowings_current`, the current-maturities row) is `extracted` for that period;
- `mismatch` if the pipeline produces any total or any extracted component, **zero included**;
- `missing` if the field is `requires_review` or `conflicting` (the pipeline could not decide), as for any other entry.

The file format keeps no free text. The comparison stays counts-only.

## 3. Effects

- R1's two borrowings entries become writable, and a pipeline that finds no borrowings for R1 matches them. A pipeline that invented a borrowing figure, or a zero, for R1 would fail the gate, which is the point.
- No product behaviour changes. Existing runs, goldens and the memo are untouched.
- If a later report presents borrowings in a note only, this does not cover it; that is a separate decision.

## 4. Acceptance examples (Appendix B.6, to be added as 72 to 74)

| # | Case (synthetic) | Expected |
|---|---|---|
| 72 | A balance sheet with lease liabilities and no borrowing row; reference entry `presented: false` | `total_borrowings` is `not_found` (`missing_input`); the entry is `match` |
| 73 | The same, but the pipeline extracts a `borrowings_current` of zero (a nil row) | the entry is `mismatch` |
| 74 | The same, with `borrowings_current` `requires_review` | the entry is `missing` |

## 5. What I need from the owner

1. Approve, change or reject section 2.
2. If approved, I apply the PRD as v0.4.32 and implement the reference form in the gate loader and the guide, with tests, then fill R1's two borrowings entries (`presented: false`). No live call is involved.
