# PRD v0.4.71 — draft (status: Phase 7b closed, held-out target not met); approved by the owner on 2026-11-05 and applied to `docs/PRD.md` as written, with the status cells of OD-49 and the Implementation status sentence added

Nothing below is applied to `docs/PRD.md`. It records the result of held-out run `H-20261104T182619Z` and your decisions of 2026-11-05 ("Close 7b now, with the miss reported"; "state plainly that the tuning baseline (36/36) did not generalize to unseen documents ... Don't soften it"). On your word I apply it as written, run the suite and commit. It changes no code, no setting and no requirement of the product other than recording results in E.2 and Section Q.

## 1. Header cells
Version 0.4.70 → 0.4.71. Status: v0.4.70 → v0.4.71, plus: "**v0.4.71 (2026-11-05)** records the result of the Phase 7b held-out run, in which the targets of E.2 were **not met**, and closes row 7b; it changes no requirement of the product." Implementation status: add: "The Phase 7b held-out run (2026-11-04) matched 0 of 12 gate values on two unseen reports; the tuning baseline did not generalise (E.2, Section Q row 7b)."

## 2. E.2, results added to the three rows (appended after each v0.4.70 target text)

- **SC-01:** "**Result (v0.4.71): not met.** Held-out run `H-20261104T182619Z` (H5 and H6, 2026-11-04, freeze commit `3f1a7c8`): **0 of 12 values matched, 0 mismatched, 12 missing.** The tuning baseline of 36 of 36 did not generalise to unseen documents; this was the caveat recorded with the targets (both tuning documents were used to tune), now observed. The earlier held-out rounds were 0 of 12 and 0 of 6. No accuracy claim is made for the pipeline on unseen documents other than this result."
- **SC-03:** "**Result (v0.4.71): not measured** in the held-out run (no reference entry stated that the report presents none). Tuning: 12 of 12."
- **SC-05:** "**Result (v0.4.71): not measured** in the held-out run (no matched source value). Tuning: 34 of 34."

## 3. Section Q, row 7b, status sentence
Replace the v0.4.70 "Status" text with: "**Closed by the owner on 2026-11-05 with the held-out target not met (v0.4.71).** Done: the scorer and the tuning baseline (SC-01 36/36, SC-02 none, SC-03 12/12, SC-04 34/34, SC-05 34/34, SC-12 2 of 2), the targets (OD-48), the assignment of H5 and H6, the move of S3 to tuning (unopened), and one held-out run: **SC-01 0 of 12, target not met; SC-03 and SC-05 not measured.** Not done: step (5), the report of SC-06 to SC-11 from the test suite and the manifests, and the SC-08 review; the closure is the owner's decision. H5 and H6 are spent and stay closed. No second held-out round is planned; a diagnosis of the gap on the tuning documents is proposed separately (`docs/PHASE7c_diagnosis_plan.md`)."

## 4. Decision row (after OD-48)
| OD-49 | **Decided 2026-11-05.** Close 7b with the miss; no second held-out round yet; H5 and H6 stay closed | (a) Close with the miss reported. (b) Source new held-out documents now. (c) Inspect H5 and H6 to find the cause (moves them to tuning). | (a). H5 and H6 are spent whatever is done, and cannot confirm a fix. A second round waits for a diagnosis on tuning documents. | Closed. The diagnosis plan awaits the owner's decision. |

## 5. Revision row 0.4.71 (2026-11-05)
"**Status change: Phase 7b held-out result and closure, authorised by the project owner on 2026-11-05** ('Close 7b now, with the miss reported ... Don't soften it'). Records held-out run `H-20261104T182619Z`: SC-01 0 of 12 (target of at least 11 of 12 with no mismatch **not met**), SC-03 and SC-05 not measured, no wrong value extracted. **The effect, plainly:** the tuning baseline did not generalise to unseen documents; across the three held-out rounds to date no gate value has been matched on an unseen report (0 of 30 values), and no accuracy claim beyond that is made. **Not changed:** any requirement, setting or code; nothing from the run changed a prompt, list, label, locator setting or threshold. **Not done:** the SC-06 to SC-11 report and the SC-08 review for 7b."
