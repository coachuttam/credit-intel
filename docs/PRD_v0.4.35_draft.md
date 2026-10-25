# PRD v0.4.35 — draft amendment: split figures are joined when they are one figure (FR-005.7, the column check)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 (with two extra tests) and applied to `docs/PRD.md` as v0.4.35 (v0.4.34, the Jev verifier draft, is not applied and stays parked). Kept as the record of the reasoning.** One addition found while building: the model returns the figure as printed with the pieces' space (`88, 136`, `(2,385 )`), which does not parse, so the raw value is read with the join's spaces removed (without it a join alone would not have cleared the stops). |
| Drafted | 2026-10-25 |
| Evidence | Tuning report R2, counts and word positions only (physical pages 36, 38 and 49). Tuning set only (O.2). The digits are not reproduced here; the shapes and distances are. |
| Changes | FR-005.7 (one bullet, one setting), the "deferred" line of FR-005.7 and Section U (split figures decided), Appendix B.6 examples 86 to 93, Revision History. |
| Not changed | Which column a figure belongs to, the sign, scale and currency checks, every reason code, every status. A figure is never moved to another column and two figures are never combined. |

## 1. Why

The PDF library sometimes reports one printed figure as two words. In R2 this stops four proposals with `cell_not_unique` (the column region holds two words where one figure should be), even though the model's value is right and on the page:

| Page | Row, period | The two words (shape) | Gap between them | Next figure in the neighbouring column |
|---|---|---|---|---|
| 36 | a profit row, 2024 column | `NN,` then `NNN` (a thousands group split off) | 0.0 pt | the 2023 column's figure starts 24.7 pt after this figure ends; the 2025 column's ends 24.9 pt before it starts |
| 38 | an equity row, 2024 column | `NNN,` then `NNN` | 0.0 pt | the 2025 column's figure ends 24.8 pt before |
| 49 | an expense row, 2025 column | `(N,NNN` then `)` (the closing bracket split off) | 0.72 pt | the 2024 column's figure starts 14.9 pt after the bracket ends |
| 49 | the same row, 2024 column | `(N,NNN` then `)` | 0.96 pt | the 2023 column's figure starts 14.9 pt after |

(The exact words and x positions were shown to the owner in the session; this file keeps only their shape.) Inside a figure the gaps are under one point; between two columns they are at least about 14 points. Neither piece parses as a figure alone (`NN,` and `(N,NNN` and `)` are not complete figures), and the joined text does.

**A read-only simulation of the rule on R2** (the figure lines of the cached run, pages 36, 38 and 49; nothing in the repository changed): 8 distinct figure lines examined; the rule would make **6 joins**, namely the four stops above and two more in the 2023 column of the same lines (which the run does not claim); **0 touching pairs were refused and 0 joins crossed a column**.

## 2. Proposed text

Add to FR-005.7, after the "Settings" bullet:

> **Split figures (v0.4.35).** The PDF library may report one printed figure as two or more consecutive words. Before the cells of a column are counted (criterion 7, conditions U and B), consecutive words of the figure line are joined into one word when **all** of these hold:
> 1. the words are consecutive on the line and the gap between each pair is at most `split_figure_gap_pt` (provisional setting, 2.0 points; 0 turns joining off), and the two words do not overlap by more than half a point;
> 2. **every one of the words overlaps the same column region** (the claimed period's column): words that belong to different columns are never joined, whatever the gap;
> 3. every word is a numeric token (G.0, including a lone `)`), and at least one of the words is **not** a complete figure on its own: two words that each parse as a figure are two figures and are never joined;
> 4. the joined text parses as one valid figure (grouping, brackets and sign as FR-005.6 and the figure rules read them), and a chain of pieces is joined only if the whole chain parses.
> The joined word takes the left edge of the first piece and the right edge of the last. It is used for the single-cell test, the value match and the sign check; the model's raw value must still equal the joined figure and show the bracket the page shows. Nothing is joined unless the column check is examining that column's region, and the original words stay in the record of the check.

**FR-005.7, deferred line** and **Section U (OD-1 row):** "split and unparsable figures" is decided for the case above; unparsable figures that do not meet the rule still fail safe (`requires_review`).

## 3. Why these constraints

- *Same column region, every word.* The column regions come from the validated period headers, so a figure is joined only inside the cell it is already being matched to. Words in neighbouring columns cannot be combined because the second would not overlap the claimed region.
- *Small gap.* Two points is above the largest observed split (0.96 pt) and far below the smallest column spacing observed (14.9 pt). It is a setting, extended only from tuning-set evidence.
- *Not a complete figure alone.* This is what prevents joining `100` and `200` (or two adjacent small figures) that happen to touch.
- *Must parse as one figure.* A pair that makes no valid figure is left as it is, and the cell stays not unique, which fails safe.

## 4. Effects and risks

- **R2:** the four stops above can clear. Whether each value then passes is for the checks that follow. Interest expense on page 49 also needs the v0.4.33 sign rule to see the joined, bracketed figure; with this amendment it can.
- **A wrong join** would need the model's raw value to equal the joined text, the joined text to sit entirely inside the claimed column, and the page to show the same sign marker. A join never changes a value the page does not show.
- **Held-out reports** may split figures differently; the rule is general and deterministic, and fails safe where it does not apply.

## 5. Acceptance examples (Appendix B.6, to be added as 86 to 93; synthetic pages)

| # | Case | Expected |
|---|---|---|
| 86 | Words `88,` and `136` touching (gap 0) inside the 2024 column; the model's raw value is `88,136` | joined into one figure; the cell is unique; the value matches |
| 87 | Words `(2,385` and `)` with a gap of 0.7 pt inside the 2025 column; raw value `(2,385)` | joined; the bracket gives the negative marker; the sign check passes |
| 88 | The same pair with a gap of 2.5 pt | not joined; `cell_not_unique` as before |
| 89 | `100` in the 2025 column and `200` in the 2024 column, a gap of 0.5 pt (adjacent columns forced together) | **not joined**: the second word is outside the claimed region |
| 90 | `(2,385` in the 2025 column and `)` placed inside the 2024 column's region | **not joined**: the words are not in the same region |
| 91 | `100` and `200`, both complete figures, gap 0 pt, both in one column region | not joined; `cell_not_unique` as before |
| 92 | `88,` and `13a` (the joined text is not a figure) | not joined |
| 93 | `1,` `24,` `936` (an Indian-grouped figure in three pieces), gaps 0 pt, one region | joined as `1,24,936`; and with the last piece 3 pt away, nothing is joined |
| 94 | After a join, the model's raw value drops the bracket the page shows (`2,385`) | the cell matches; the sign check fails (`sign_mismatch`) |
| 95 | `88,` `136` and a superscript footnote mark `1` touching the figure | `88,136` is joined; the mark is not; the cell is not unique |

## 6. What I need from the owner

1. Approve, change or reject section 2, including the 2.0 pt setting.
2. If approved, I implement it in one step (a helper in the column check, the setting, tests for examples 86 to 93 and for the four R2 shapes with synthetic text), run the mutation checks, replay the cached R2 run for free, and stop before any live call.
