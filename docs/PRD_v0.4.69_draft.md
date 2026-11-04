# PRD v0.4.69 — draft (specification of Phase 7b); approved by the owner on 2026-11-04 and applied to `docs/PRD.md` as written, apart from the five-column layout of the decision rows and the status cells of OD-41 to OD-47

Nothing below is applied to `docs/PRD.md`. It records your decisions of 2026-11-01 on `docs/PHASE7b_plan.md` (committed `b89e1f7`). On your word I apply it as written, run the suite and commit. It changes no code, no setting and no requirement of the product; it fixes the scope of the evaluation. Nothing was run and nothing under `private/` was opened.

## Two readings I need you to confirm

1. **"2 tuning documents."** I read this as the two existing tuning documents, **R1 and R2** (assigned 2026-10-13; their statement pages and gate fields are already labelled), which would now be labelled for the full SC-01 field set. If you meant two *new* tuning documents, say so; that is a different amount of labelling and needs two new assignment lines.
2. **"Pick the 2 held-out documents."** I cannot pick them. Under O.2 you select them from public metadata **before anyone inspects statement pages or output**, and the assignment is committed first. What I record is the constraint you set: one INR report with lakh/crore scales and one in another currency, from companies not in the tuning set, not previously used (not H1 to H4). The two assignment lines are appended only after you give me their neutral IDs (the next free ones, `H5` and `H6`) and SHA-256 values; I do not see the company names.

## 1. Header cells

- **Version** 0.4.68 → 0.4.69.
- **Status:** v0.4.68 → v0.4.69, and the sentence: "**v0.4.69 (2026-11-01)** specifies Phase 7b (the expanded evaluation) from the owner's decisions OD-41 to OD-47; it changes no requirement of the product."
- **Implementation status:** no change (7b is not started).

## 2. Section Q, row 7b

→ "| **7b — Expanded evaluation** | Split from Phase 7 by OD-27 (2026-10-30); specified in v0.4.69 (OD-41 to OD-47) | Phase 7 approved (2026-11-01). | (1) The two tuning documents (R1, R2) are labelled for the full SC-01 field set by the owner and a **tuning baseline** is recorded as counts for SC-01 to SC-05, SC-12 and each `requires_review` reason (O.3 step 1); (2) defects found in the tuning set are fixed in the tuning set only, each with a test and the owner's approval; (3) targets are proposed from the baseline and approved by the owner, replacing the placeholders of E.2; (4) the two held-out documents (one INR with lakh/crore scales, one in another currency; assigned and committed before anyone inspects them) are run once by the held-out tool, **on the gate's three fields only**, and reported by run id against the approved targets; (5) SC-06 to SC-11 are reported from the test suite and the manifests, and SC-08 from the owner's manual review of each evaluation memo; (6) an evaluation report and exit summary. **No held-out figure for SC-01, SC-03 or SC-05 results from this round** (OD-43); no accuracy claim is made from it. Not started. |"

## 3. Decision rows (Decisions table, after OD-40)

| ID | Text |
|---|---|
| OD-41 | **Decided 2026-11-01: option (b), as the owner set it.** Documents for 7b. Two tuning documents (R1 and R2, see the readings above) and two held-out documents, **one INR report using lakh/crore scales and one report in another currency**, selected by the owner before any inspection (O.2). Chosen over the PRD's planned five to avoid committing to full labelling of five documents before the pipeline's results on a smaller set are known. Options: (a) about five new public documents; (b) two and two; (c) only what exists. Trade-off: two held-out documents give counts, not rates, with wide uncertainty (O.2 Uncertainty). Proposal: none (the owner's decision). |
| OD-42 | **Decided 2026-11-01: as proposed.** Label scope. The tuning documents are labelled for the **full SC-01 field set**; the held-out documents for **the gate's three fields** (profit before tax, interest expense, total borrowings, both periods). |
| OD-43 | **Decided 2026-11-01: option (a), not this round.** The held-out tool stays at the gate's three fields (v0.4.41). Extending it to the full SC-01 field set is to be revisited in a later round once this smaller run has been reported. Consequence: SC-01, SC-03 and SC-05 have a tuning baseline but **no held-out figure** from 7b, and under O.3 only held-out results are release results, so they are not presented as such. |
| OD-44 | **Decided 2026-11-01: option (b), USD 0.50.** Spend for 7b. A cap of USD 0.50 for 7b (a budget decision, not a product setting), with the per-run token ceiling of NFR-09 in force. **Every send is approved by the owner and run in the owner's terminal.** The earlier Phase 6 cap of USD 0.15 is not changed by this row. |
| OD-45 | **Decided 2026-11-01: option (a).** SC-08 review. The owner does the manual review of each evaluation memo, with a checklist; the assistant that wrote the memo code does not judge it. |
| OD-46 | **Decided 2026-11-01: option (a).** Scans are out of the scope of 7b. OCR keeps its own tuning evidence (the two tuning scans); the held-out scan S3 stays closed. |
| OD-47 | **Decided 2026-11-01.** The closed things stay closed: H1 to H4 have used their shot and are not reused; S3 and the OD-17 result labels are left alone; no held-out statement page is opened. |

## 4. O.2, one added sentence (after the "Uncertainty" note)

"**(v0.4.69)** For Phase 7b the dataset is two tuning documents (R1, R2) and two held-out documents (OD-41); the planning estimate of about five above is not met in this round."

## 5. Revision row 0.4.69 (2026-11-01)

"**Specification change: Phase 7b (the expanded evaluation), authorised by the project owner on 2026-11-01** ('Decisions for Phase 7b ... Go ahead and commit the plan doc now, then draft v0.4.69 recording these for my approval'). Records OD-41 to OD-47 and the row 7b exit criteria (Section Q). **The effect, plainly:** the evaluation is smaller than the PRD's plan (two and two, not about five); the held-out tool is unchanged, so the held-out round reports the gate's three fields only and gives no held-out figure for SC-01, SC-03 or SC-05; the tuning baseline covers the full field set; spend is capped at USD 0.50 with every send approved by the owner. **Not changed:** any requirement of the product, any setting, any code. **Not started:** every step of 7b. **Needs from the owner before step 2:** the two held-out documents' neutral IDs and SHA-256 values (the assistant is not told the companies) and confirmation of the two readings above."

## 6. What happens after you approve this

1. I apply it, run the suite, commit.
2. You send me the two held-out IDs and SHA-256 values (after selecting from public metadata and before anyone opens a page); I append the two lines to `tests/eval/assignments.jsonl` with the validator test and commit them. Nothing else touches those documents until then.
3. I build the scoring tool for the tuning baseline offline (synthetic documents and label files), with tests and mutation checks.
