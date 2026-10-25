# PRD v0.4.40 — draft amendment: the code also reads the interest-expense row the model did not propose (FR-005.10, v0.4.39)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("approve v0.4.40, interest expense only"); applied to `docs/PRD.md` as v0.4.40 and implemented. Kept as the record of the reasoning.** |
| Drafted | 2026-10-25 |
| Evidence | Tuning report R1, physical page 276, under `extraction_v2`, `v5`, `v6`, `v8`, `v9` (cached replies) and a counts-only look at the page (owner-authorised 2026-10-25): the page prints a row labelled exactly `Finance cost`, with figures in both period columns, among the expense rows. No figure was printed. Tuning set only (O.2). |
| Changes | v0.4.39's scan (one sentence: which fields and which statement), the manifest block name stays `field_scans`, Appendix B.6 examples 123 to 127, Revision History. |
| Not changed | The label phrases of `interest_expense`; the sign rule (v0.4.33); every check; the three borrowings components; every other field. |

## 1. Diagnosis

On R1 the row exists, is read correctly by the pipeline's own tools, and its label is already accepted (`finance cost` is a configured phrase). The model simply never proposes it, under five different prompts, including `extraction_v6` which named the row in a note. The extraction step is therefore not failing on the page; it is **omitting** a field, which a prompt note has not fixed and which the v0.4.39 scan was designed to cover.

I tested the scan idea on the cached R1 reply, in a throwaway script outside the source tree: the scan, run for `interest_expense` on income-statement pages, adds the `Finance cost` row for both periods, both pass every check, and the R1 gate reads **6 matched, 0 mismatched, 0 missing** under `extraction_v5`. (A run of the same script on R2 shows 4/0/2 only because that script switched the borrowings scan off; it is not a finding about interest expense, which the model proposes on R2, and the scan fills gaps only.)

## 2. The proposal

> **Interest expense read by the code (v0.4.40).** The scan of v0.4.39 also covers `interest_expense`, on **income-statement pages** (a candidate page the locator selected for the income statement or, for a supplied page range, a page with an income-statement title line). Everything else in the v0.4.39 paragraph applies unchanged: it adds a proposal only for a period for which the model proposed none; it adds nothing when more than one line on the run is recognised for the field; the proposal goes through every check (including the bracket and heading rule of v0.4.33 for the sign); the added value is a `source` field recorded in the manifest (`field_scans`).

That is the whole change: one field and one statement type added to a rule the owner has approved.

## 3. Why this is safe and narrow

- **Same checks, same label list.** `finance costs`, `finance cost` and `interest expense` only. A row the labels do not recognise is not read.
- **Gap-filling only.** The model's own proposal for the period always wins.
- **Ambiguity declines.** A page that prints both `Finance cost` and `Interest expense` (two recognised lines) adds nothing for the field.
- **Income-statement pages only.** A note page, a segment table or a debt schedule is never scanned.
- **No change to R2.** The model proposes interest expense on R2, so the scan has nothing to fill. This is to be confirmed by a free replay with both scans on.

## 4. Expected effect (to be confirmed by a free replay once built)

R1: 6 matched, 0 mismatched, 0 missing (from the prototype above). R2: 6/0/0, unchanged from v0.4.39. Both would then pass the owner's gate on `extraction_v5` with no live call.

## 5. Acceptance examples (Appendix B.6, to be added as 123 to 127; synthetic pages)

| # | Case | Expected |
|---|---|---|
| 123 | The model proposes no interest expense; an income-statement page has a `Finance cost` row | added for each period; verified; recorded in the manifest |
| 124 | The model proposed `interest_expense` for a period | the model's proposal is kept; nothing added for that period |
| 125 | The page has both `Finance cost` and `Interest expense` rows | nothing added |
| 126 | The row is on a balance-sheet or note page | not scanned |
| 127 | The row sits under an `income (expense)` heading with a bracketed figure | added as a positive expense by the v0.4.33 rule |

## 6. What I need from the owner

1. Approve, change or reject section 2 (interest expense only, income-statement pages only).
2. Whether other gate-relevant fields (`profit_before_tax`) should join the scan. I do **not** propose it: the model already proposes it on both reports, and a profit row's label is less unambiguous than a cost row's.
3. If approved, I implement it with tests and mutation checks, replay R1 and R2 for free under `extraction_v5`, `v8` and `v9`, and show the gate counts, with no live call. No prompt change is proposed.
