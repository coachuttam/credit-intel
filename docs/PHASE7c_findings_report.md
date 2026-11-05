# Phase 7c findings report: the generalisation gap, on tuning evidence (for the owner's review)

Dated 2026-11-05. Everything here comes from the five tuning documents (R1, R2, S1, S2, S3, of which only R1 and R2 are text-layer reports with full labels) and from synthetic pages. H1 to H6 were not opened; their printed reason codes were used only to choose where to look (the owner's reading of O.2, 2026-11-05). Nothing here is a claim about unseen documents, and nothing is an accuracy figure.

## 1. The question and the short answer

**Question.** The tuning baseline was 36 of 36 (SC-01) on R1 and R2; the held-out run on H5 and H6 matched 0 of 12. Why?

**Short answer.** Nobody can say why for H5 and H6, because they are closed. What this phase can say is how the tuning score was built and where the pipeline is fragile on layouts the tuning documents do not exercise. Both are substantial, and several fragilities share names with H5's and H6's printed reasons. None of this proves any of them happened there.

## 2. What the evidence shows

| # | Finding | Evidence (counts) | Tied to H5/H6? |
|---|---|---|---|
| F1 | **R2's tuning score is largely a fit to R2.** With the row-label phrases added from R2 taken out, R2 falls from 22/22 to 4/22 (10 refused `label_not_recognised`, 6 absent, 2 derived totals). R1 falls from 14/14 to 12/14. | ablation, `docs/PHASE7c_diagnosis_plan.md` section 10; 18 of 34 row-labelled matches rest on a phrase added from the same document (S-5) | `label_not_recognised` is one of H5's reasons: a resemblance |
| F2 | **A `not_found` can hide a list failure.** The code finds a row for a field the model skipped by the same phrase list; without the phrase the field reads `not_found`, with no reason. | R1 ablation: 2 entries `not_proposed` | `not_found` is three of H6's six reasons: a resemblance |
| F3 | **The locator is a second single point of failure.** R1 without the locator phrases added for it does not degrade; the run stops with no result (`E-EXTRACT-BASIS-UNAVAILABLE`). | ablation with `--locator` | not shown |
| F4 | **A report whose titles name no basis produces no result unless the analyst supplies `--pages` and `--assert-basis`.** | V2: R2 by the locator alone finds its two pages, then stops at the basis gate | `basis_unknown` is one of H6's reasons: a resemblance |
| F5 | **A statement that continues on a second page lost its second-page values when the pages were given.** Specified behaviour (FR-005.8), fixed in PRD v0.4.74 / `1ad9da2`: R1 through an explicit range 10/14 -> 14/14. | V3, plus six verifier tests | H5 and H6 both used the explicit-pages route; the symptom (`scale_not_verified`) is not among their reasons: a candidate contributing factor |
| F6 | **Layouts a perfect model still fails on** (stress matrix, 25 synthetic pages, one factor at a time): row labels without "total" or a title "Statement of Assets and Liabilities" or wrapped labels with figures on the first line (no statement pages found); a synonym label or labels wrapped with figures on the second line (`label_not_recognised`); a fiscal-year-range header (`period_mismatch`); no scale or currency declared (`scale_not_verified`); a continuation page headed by bare years (`period_not_verified`). | `tests/integration/test_stress_matrix.py` | `label_not_recognised`, `period_mismatch` are among H5's reasons: resemblances |
| F7 | **The tuning pair cannot separate causes.** R1 and R2 differ on nearly every layout tag, so a feature breakdown of two documents says nothing. Their model replies were also obtained with the prompt that was tuned on them. | S-2 breakdown; ablation caveat | n/a |
| F8 | **A setup error cannot be told from a pipeline fault in the one-shot result**, and the held-out tool had no way to test a reference before the shot. Fixed in part: the setup check now tests the SHA, the pages, the figures on their pages, the locator and basis gate, a usable declaration and a period column for every labelled value, before a run, and may be used on an unused held-out document. | S-4 | the process gap behind H5 and H6 |

Resemblances in the table are resemblances of names only. The cached model replies are R1's and R2's; a document the model reads differently would behave differently in ways none of this measures.

## 3. What this phase could not do

- **Explain H5 or H6.** Both stay closed; any opening would move them to tuning and say nothing new about a held-out result.
- **Say how common any of these layouts is.** The stress layouts are mine; the tuning pair is two documents. Whether "Profit before taxation" or a fiscal-year header or a wrapped label is common in real reports is exactly what two documents cannot say.
- **Measure the model.** The model's own omissions and misreadings on a new document are not in any of this: the matrix uses a scripted perfect model and the ablation reuses cached replies.

## 4. Changes made, and changes not made

**Made (all offline, tested, committed):** the scorer and its stage attribution; the setup check and its widening; the phrase provenance record; the ablation; the layout stress matrix; the continuation-page rule for a page range (PRD v0.4.74, the only change to the pipeline).

**Not made, on purpose:** no phrase list, locator setting, period form or prompt was widened or changed. The owner ruled (2026-11-05) that the stress matrix shows what fails and not what is common, so that decision waits for more tuning documents or a clearer signal.

## 5. Options for the owner (none started)

1. **Source more tuning documents** (public reports chosen for differences in layout and vocabulary; labelled in full; freely used for diagnosis and fixes; not held-out). This is the only route that tells how common the fragilities are and finds ones nobody imagined. It needs the owner's selection and labelling and a spend cap (USD 1.00 is set for the phase, every send approved).
2. **A live variant on R1 or R2 with a second pair of statement pages (V4)**, to test vocabulary outside the first pair. One document, one send, exact command first. It adds little beyond option 1.
3. **Product transparency, no new extraction:** let the memo say, for a field that reads `not_found`, whether its row was not located in the pages sent or the report presents none, where the code can tell (F2). It changes what the analyst sees, not what is extracted; it needs a PRD change.
4. **Decide the fate of each characterised gap** (F6) only after option 1: widen a phrase list, accept a wrapped-label form, read a fiscal-year header. Each is a change to a closed list and would be justified from tuning evidence alone, with a test, a mutation check and the regression bar.
5. **Leave the pipeline as it is and say so**: the honest position today is the held-out record (0 of 30 gate values on unseen reports) and the findings above.

Recommendation: option 1, then option 4 on what it shows; option 3 in parallel, since it helps the analyst whatever the extraction does.
