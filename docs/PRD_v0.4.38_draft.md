# PRD v0.4.38 — draft amendment: a `total_borrowings` proposal whose row is a borrowings component is re-filed as that component (FR-005.10, H.5 rule 5)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("approve v0.4.38, accept the limit"); applied to `docs/PRD.md` as v0.4.38 and implemented. Kept as the record of the reasoning.** |
| Drafted | 2026-10-25 |
| Evidence | Tuning report R2, pages 36 to 38 and 49, under `extraction_v8`, from the cached reply: counts and the printed row labels only (the owner authorised the label print on 2026-10-25). Tuning set only (O.2). |
| Changes | FR-005.10 (one paragraph), H.5 rule 5 (a pointer), the manifest (a block, only when it applies), Appendix B.6 examples 109 to 114, Revision History. |
| Not changed | The label phrases of D-12; `BORR-SUM`; every other field; any proposal whose label is already recognised for its own field; every value. |

## 1. Why

On R2 the model proposed `total_borrowings` for both periods, and both proposals carry the row label `Long-term debt`. That row is a **component** (D-12 accepts it as `borrowings_non_current`), not a total, so the label check for `total_borrowings` rejects it (`label_not_recognised`). That rejection is right. But the model proposed no component fields, so `BORR-SUM` has nothing to add and the gate for R2 stays at 2 missing (total borrowings, both periods).

The model's choice of field for a debt row has varied between prompts (v5: no debt rows proposed; v8: component rows proposed into the total field), the same fragility as the currency and scale attributes (v0.4.37). A rule in code fixes the field once, deterministically, and does not depend on the prompt.

## 2. The proposal

> **Component re-filing (v0.4.38).** When a `total_borrowings` proposal fails the label check (FR-005.10), and the printed row label of the figure the proposal cites is **recognised for exactly one borrowings component field** (`borrowings_non_current`, `borrowings_current` or `current_maturities_long_term_borrowings`, by the D-12 phrases and the existing inclusion and exclusion guards), the proposal is **re-filed** as a proposal for that component: same page, quote, raw value, period and evidence. It is then verified as that field, with every check that field has (the figure on the page, the column and period, the scale and currency, the label). Nothing about the proposal is changed except the field name. `BORR-SUM` then adds the components as today.
>
> A proposal is **not** re-filed when its label is recognised for no component, or for more than one, or when a proposal for that component and period already exists (the model's own proposal is kept, and the re-filed one is dropped, never added twice, so the figure cannot be counted twice). A `total_borrowings` proposal whose label **is** recognised stays a total. The re-filing is recorded in `manifest.json` (`field_refilings`: the field proposed, the field used, the page, the period; present only when there was one), and the field record in `results.json` shows the field used.

## 3. Why this is safe and narrow

- **Only the field name moves.** The figure, quote and page are the model's; the verifier checks them against the page exactly as for any component. A figure that is not on the page, or is in the wrong column, still fails.
- **The label decides, as always.** The same phrases that classify a component in `BORR-SUM` decide the re-filing; no new phrase is introduced. An unrecognised label stays `requires_review`.
- **No double count.** A component proposed by the model and the same component re-filed from the total field cannot both enter the sum (the model's is kept).
- **Total rows are untouched.** A row that prints a total (`Total borrowings`) is recognised for `total_borrowings` and is never re-filed.
- **Replayable.** The rule reads only the cached reply and the page, so the R2 gate can be replayed for free.

## 4. Expected effect (to be confirmed by a free replay once built)

On the cached R2 `extraction_v8` reply, the two `Long-term debt` proposals would be re-filed as `borrowings_non_current` for the current and comparative periods. Whether the gate's `total_borrowings` then matches depends on the other debt rows (`Short-term debt` and `Current portion of long-term debt`): the model proposed none of them, so `BORR-SUM` would sum the long-term row alone, and **the total would not equal the owner's reference (three parts)**. I expect the gate to show a **mismatch or a `not_presented`/incomplete result, not a match**, and I will report what it actually shows. The rule makes the existing proposals usable; it does not find rows the model never proposed.

That is the honest limit: this amendment removes one prompt-dependent failure but, on this reply, probably does not pass the R2 borrowings gate. Passing needs the model to propose the other two rows, which is a prompt matter (option 1 of my earlier note), or a deterministic scan of the debt page for rows the model did not propose, which is a larger change that I am **not** proposing here.

## 5. Acceptance examples (Appendix B.6, to be added as 109 to 114; synthetic pages)

| # | Case | Expected |
|---|---|---|
| 109 | `total_borrowings` proposed with the row label `Long-term debt` | re-filed as `borrowings_non_current`; verified as that field; recorded in the manifest |
| 110 | `total_borrowings` proposed with the row label `Short-term debt` | re-filed as `borrowings_current` |
| 111 | `total_borrowings` proposed with the row label `Total borrowings` | stays a total; no re-filing |
| 112 | `total_borrowings` proposed with a label recognised for no field | stays `requires_review` (`label_not_recognised`) |
| 113 | The model also proposed `borrowings_non_current` for the same period | the model's proposal is kept; the re-filed one is dropped; counted once |
| 114 | The re-filed figure is not on the page | fails its own check as that field; never extracted |

## 6. What I need from the owner

1. Approve, change or reject section 2, in particular that the label decides and that the model's own component proposal wins a clash.
2. Accept the section 4 limit: this probably does not pass the R2 borrowings gate by itself.
3. If approved, I implement it with tests and mutation checks, replay the cached R2 `extraction_v8` reply for free and show the gate counts, with no live call.
