# Phase 7b exit summary (expanded evaluation): closed with the held-out target missed

Dated 2026-11-05. Written for the owner. This is a statement of what was done and what the numbers say; it is not an approval request for any release claim, and none is made.

## 1. The outcome, plainly

**The held-out target was not met.** Run `H-20261104T182619Z` (documents H5 and H6, the gate's three fields, both periods, freeze commit `3f1a7c8`, prompt `extraction-v5`): **0 of 12 values matched, 0 mismatched, 12 missing** against a target of at least 11 of 12 with no mismatch.

**The tuning baseline (SC-01 36/36 on R1 and R2) did not generalise to unseen documents.** That was the caveat in `docs/PHASE7b_targets_proposal.md` (items 1 and 2: both documents were used to tune; the earlier held-out rounds were 0 of 12 and 0 of 6), and it is now observed. The three held-out rounds so far (H1 and H2, H4, H5 and H6) have matched 0 of 30 gate values between them. This is the project's only out-of-sample evidence, and it says the pipeline does not yet work on documents it was not tuned on.

No wrong value was extracted (0 mismatches, no SC-02 candidates). The failures are refusals by the checks or fields the model did not return. That means the design fails closed. It does not mean the pipeline is right, and it does not make 12 missing values acceptable.

## 2. Results, by run

| Measure | Tuning set (R1, R2), 2026-11-04 | Held-out run H-20261104T182619Z (H5, H6) |
|---|---|---|
| SC-01 | 36/36 (target T1: 36/36, met) | **0/12** (target T2: at least 11/12 with no mismatch, **not met**) |
| SC-02 candidates | 0 | 0 (nothing extracted) |
| SC-03 | 12/12 | **not measured** (no entry labelled "presented: false", checked by the owner) |
| SC-04 | 34/34 | not computed (nothing extracted) |
| SC-05 | 34/34 | **not measured** (no matched source value) |
| SC-12 | 2 of 2 documents | not applicable (pages were given) |
| Reasons for missing | none | H5: `label_not_recognised`, `period_mismatch`, `no_record`. H6: `basis_unknown`, `not_found`, `missing_input` |

Held-out cost USD 0.00209835 (computed from the two printed figures). The cost of R2's live send was not reported, so the OD-44 total (cap USD 0.50) is not summed; it is far below the cap on any reading.

## 3. What was built and decided in 7b

- **Plan and decisions** `docs/PHASE7b_plan.md`; PRD v0.4.69 (OD-41 to OD-47: two tuning and two held-out documents, full labels for tuning and the gate's three fields for held-out, no held-out tool extension, USD 0.50 cap, the owner's SC-08 review, scans out of scope, the closed things stay closed); v0.4.70 (targets T1 and T2, OD-48).
- **The tuning scorer** (`credit_intel.evaluation.score`): SC-01 to SC-05 and reason counts against hand-written 24-entry labels; offline replay from the cache; counts only; held-out documents refused; `--skeleton` and blank skeletons; 78 tests, 34 mutation checks (33 caught, 1 equivalent).
- **Assignments:** H5 and H6 appended to the record (`6c12512`), S3 moved to tuning, unopened (owner's decision; the held-out tool runs over every unused held-out document, so a run on H5 and H6 alone needed S3 out of the held-out set).
- **The run:** one shot per document, ledger committed (`ef669f7`).

## 4. What this does not show

- It does not show why the pipeline missed. H5 and H6 were not opened and no pipeline output beyond the printed counts was read; they stay closed (owner's decision).
- It does not tell whether the references' page ranges and basis assertions were right for the pipeline: they were fixed by hand before the one shot and cannot be tested after it. A setup error and a pipeline fault look the same in the counts.
- It gives no figure for the nine fields outside the gate's three (OD-43), no scan or OCR result (OD-46), and no SC-08 review. **Step (5) of the row 7b exit criteria, the report of SC-06 to SC-11 from the test suite and the manifests, was not compiled** (the owner closed 7b on the held-out result; the figures can be produced offline if wanted), so row 7b is closed by the owner's decision, not because every listed step was completed.
- It supports no accuracy claim. The only statement the evidence supports is: on a held-out run of two public reports, none of the 12 gate values was matched and none was wrong.

## 5. My mistakes in 7b

1. **Wrong cache directory.** I proposed moving `.cache/llm` aside before the held-out run. The tool uses `.cache/llm_heldout`. I found it when I read the tool, before anything was moved, and withdrew it.
2. **The S3 rule.** I planned a two-document held-out run without checking that the tool runs over every unused held-out document; S3 was one. I found it at the preconditions and the owner moved S3 to tuning.
3. **The R2 locator.** I repeated that the locator finds no candidates on R2; SC-12 showed it finds both statement pages. Corrected before it reached the PRD.
4. **No check of the references before the one shot.** The held-out tool has no step that tests, without the model, that each labelled value is on its labelled page and that the page range holds them. I told Uttam to choose pages carefully but did not say there was no way to check them first, and I did not propose building one. This is a gap in the process that I should have raised when the references were being written (see `docs/PHASE7c_diagnosis_plan.md`, S-4).

## 6. Status

7b is closed with the miss reported. No second held-out round is sourced (owner's decision). PRD wording is in `docs/PRD_v0.4.71_draft.md` for approval. The next piece of work is a diagnosis of the gap on tuning documents only (`docs/PHASE7c_diagnosis_plan.md`, a proposal).
