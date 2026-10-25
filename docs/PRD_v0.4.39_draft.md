# PRD v0.4.39 — draft amendment: the code reads borrowings component rows the model did not propose (FR-005.10, H.5 rule 5)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("approve v0.4.39, scan on every document, source origin"); applied to `docs/PRD.md` as v0.4.39 and implemented. Kept as the record of the reasoning.** |
| Drafted | 2026-10-25 |
| Evidence | Tuning reports R2 (pages 36 to 38 and 49) and R1 (pages 274 to 277), under `extraction_v5`, `v8` and `v9`, counts and printed row labels only (`PROGRESS.md`, gate steps 6 to 8). Tuning set only (O.2). |
| Changes | FR-005.10 (one paragraph), H.5 rule 5 (a pointer), the manifest (a block, only when it applies), Appendix B.6 examples 115 to 122, Revision History. |
| Not changed | The label phrases of D-12; `BORR-SUM`; v0.4.38 re-filing; every field other than the three borrowings components; every verification check; every value. |

## 1. Why

`BORR-SUM` adds the borrowings **components** that the extraction yields. On R2 the number of debt rows the model proposes depends on the prompt:

| Prompt | Debt rows proposed on R2 (per period) | Effect |
|---|---|---|
| `extraction_v5`, `v7` | none | total borrowings `missing_input` |
| `extraction_v8` | one (`Long-term debt`, filed as the total) | re-filed by v0.4.38; the other two rows absent |
| `extraction_v9` | two (`Long-term debt`; `Current portion of long-term debt` filed in the wrong field) | still missing; and on R1 (which presents no borrowings) it proposed four debt rows that fail the label check, so the "none presented" match was lost |

Three prompts, three different answers, and a prompt that finds more debt on R2 invents it on R1. Whether a debt row exists is a fact of the page, not a judgement. The labels that identify a debt row are already fixed, tested and recorded as tuning evidence (D-12). The code can read them itself.

## 2. The proposal

> **Component rows read by the code (v0.4.39).** After the model's proposals are re-filed (v0.4.38) and before they are verified, the code looks, **on each candidate page whose statement type is the balance sheet**, for figure lines whose row label is recognised (FR-005.10, the D-12 phrases, with the section-heading rule and the inclusion and exclusion guards unchanged) for one of the three components `borrowings_non_current`, `borrowings_current`, `current_maturities_long_term_borrowings`. For each such field and each period, if the model proposed **no** value for that field and period, the code adds a proposal for it: the page, the line as printed as the quote, the label as printed, the figure in that period's column as the raw value, and the scale and currency of the document attributes. The proposal then goes through **every check a model proposal goes through** (FR-005.1 to 5.10), unchanged: the quote on the page, the value in the quote, the column and period, the row label, the scale and currency, the basis.
>
> **Nothing is added** when: the model proposed that field for that period (the model's proposal stands, and is verified as before); more than one line of the run is recognised for the same field (the code does not choose; the field stays as it is); the document's currency or scale attribute is not `extracted`; the page's period columns are not valid (FR-005.7); the line has no figure in the period's column (a dash or `nil` is read as printed and is a value to the same checks); or the page is not a balance sheet (a note, a schedule, a maturity table is never scanned). A line is never added for `total_borrowings`, `revenue` or any other field.
>
> Every added proposal is recorded in `manifest.json` (`field_scans`: the field, the page, the period, and the label as printed; present only when there was one). In `results.json` the field is an ordinary `source` field with its page and quote; nothing marks the model as its author.

## 3. Why this is safe and narrow

- **Same checks, same evidence.** The code only does what the model was asked to do: it quotes a page line and the figure in a column. If the page does not support the value, the verifier rejects it exactly as it would reject the model.
- **Only labels already approved.** No new phrase. A row the D-12 labels do not recognise is not read.
- **Where the model is silent, not where it speaks.** The model's own proposal for a field and period always wins; the scan fills only a gap. This is the same clash rule as v0.4.38.
- **Ambiguity declines.** Two recognised lines for one field (for example a balance sheet and a summary table on the same page) add nothing.
- **R1.** A report that presents no borrowings has no recognised row, so nothing is added, and the "none presented" result is unchanged, whichever prompt is used. (To be confirmed by a free replay on the cached R1 runs; an R1 page whose row is recognised would be a finding, not an assumption.)
- **Replayable and free.** The scan reads only the cached reply, the page text and the page words.

## 4. Expected effect (to be confirmed by a free replay once built)

On R2 the page prints its debt on three captioned rows (D-12). Under any cached reply, the scan should add the rows the model omitted, for both periods, and `BORR-SUM` should then sum three components, which is the owner's reference (three parts). I **expect** the R2 borrowings entries to move from missing to a match under `extraction_v5`, `v8` and `v9` alike, which would make the gate independent of the debt wording of the prompt. I have **not** seen the page text; if the replay shows a mismatch or a stop, I will report which check failed. The R1 gate stays 4 matches, 2 missing (interest expense) under `v5`; interest expense is a separate open item.

## 5. Acceptance examples (Appendix B.6, to be added as 115 to 122; synthetic pages)

| # | Case | Expected |
|---|---|---|
| 115 | The model proposes no debt field; a balance-sheet page has rows `Long-term debt`, `Short-term debt`, `Current portion of long-term debt` | three components added for each period; each verified; recorded in the manifest |
| 116 | The model proposed `borrowings_non_current` for a period | the model's proposal is kept; the scan adds nothing for that field and period |
| 117 | The page has no recognised debt row | nothing added; no manifest block |
| 118 | Two lines on the run are recognised for `borrowings_current` | nothing added for that field |
| 119 | The row is recognised, but on a note page | not scanned |
| 120 | The currency or scale attribute is not `extracted` | nothing added |
| 121 | The figure in the period's column is a dash | read as printed and verified by the same checks; never turned into a number |
| 122 | A lease-liability row | not recognised; nothing added |

## 6. Decisions for the owner

1. Approve, change or reject section 2, in particular: the scan fills gaps only; ambiguity declines; balance-sheet pages only; and the added field carries no marker beyond the manifest block.
2. **Whether a scan-added value is a `source` field or needs a new origin.** The value is printed on the page and read by code, so I propose `source`, with the manifest as the record. A third origin value would touch the results schema and the memo labels.
3. Whether the scan should also run for a document where the model proposed **no** borrowings field at all, as I propose, or only when the model proposed at least one (narrower, but the R2 `extraction_v5` reply proposes none).
4. If approved, I implement it with tests and mutation checks, replay the cached R2 and R1 runs (v5, v8, v9) for free, and show the gate counts, with no live call.
