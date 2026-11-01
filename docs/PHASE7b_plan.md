# Phase 7b plan: expanded evaluation — a proposal for the owner

| Item | Value |
|---|---|
| Status | **Proposal. Written 2026-11-01 against PRD v0.4.68. Nothing is approved, nothing is run, nothing under `private/` was opened, no model call was made and no spend was incurred.** |
| Why this is only a plan | The Section Q row says: "Not started; to be specified by the owner. The owner assigns the documents; the held-out work stays closed until the owner says otherwise." The documents and the money are yours to decide, so the first step is the decisions in section 5. |
| Rules that already bind it | PRD O.2 and O.3, the assignment record (`tests/eval/assignments.jsonl`), AC-E-7, the one-shot held-out ledger. Section 2 lists them. |

## 1. What 7b is for

The PRD defines three kinds of evidence and keeps them apart (O.3): software correctness (done: 5043 tests), **extraction quality** (SC-01 to SC-05 and SC-12 on real reports) and product value (not measured by this PRD). **7b is the second.** Today there is no release evidence for it:

- The targets of SC-01, SC-03 and SC-05 are still **placeholders** ("re-set after the tuning-set baseline"). No baseline has been approved, so there is nothing yet to report a held-out run against.
- The two held-out runs so far (`H-20261025T174648Z`: H1, H2, 0 of 12 gate entries matched; `H-20261026T092850Z`: H3 stopped on the then 25 MB size limit and never read, H4 0 of 6) cover only the gate's three fields. They are not SC-01 to SC-12 reports. H1 to H4 have each used their one shot.
- SC-12 has a counting tool and a tuning baseline for the tuning documents; the other SCs have no evaluation report.

## 2. What the PRD already fixes (not for me to change)

1. **Order** (O.3): (1) run the pipeline on the **tuning set**, record counts for SC-01 to SC-05 and SC-12 and each `requires_review` reason; (2) fix defects found there, in the tuning set only; (3) I propose targets from the measured baseline, **you approve**, and they replace the E.2 placeholders; (4) run the **held-out set once** and report against them.
2. **Documents are assigned before any inspection** and recorded (append-only, committed) in `assignments.jsonl`; the report cites that commit and the file's SHA-256. A held-out document inspected to debug moves to tuning and is never held out again.
3. **Held-out results never change** prompts, phrase lists, locator settings or rule thresholds. Held-out IDs, hashes and labels never appear in configuration, prompts, phrase lists or their change records (AC-E-7).
4. **One shot per document**, through `python -m credit_intel.evaluation.heldout --held-out-run`; the run is frozen (a clean tree at `HEAD`); each run is reported **separately by run id**, never merged; counts, not percentages claimed (small sets).
5. **No performance claim** in the README, documents or memo until a recorded evaluation report backs it.
6. **Labels are made by hand from the rendered pages** (by you, or checked by you) and kept in `private/eval/`. I do not open `private/` or read statement pages; I work from counts the tools print.

## 3. What is missing before a run can start

| # | Gap | Who |
|---|---|---|
| G1 | **New documents.** H1 to H4 are used and the held-out work on them is closed; S3 and the OD-17 labels are left alone by your instruction. A held-out report needs new, public documents assigned **before** anyone looks at them. The PRD asks for at least one INR report with lakh/crore scales and one in another currency among the held-out documents, and about five public ones in all (O.2). | You |
| G2 | **Labels** for every new document (value, page, quote, statement pages), hand-made and double-checked. This is the largest cost and it is yours. | You |
| G3 | **A tool that reports SC-01 to SC-12 together.** The gate compares three fields; `recall.py` scores SC-12; `summary.py` prints counts for one run. There is no tool that scores all in-scope fields (SC-01), not-found correctness (SC-03), page references (SC-05) and the `requires_review` reason counts against a label file, or that builds the dated report with the assignment commit and SHA-256 (O.3, O.2 step 5 of the integrity rules). | Me, after you decide the label scope (OD-42) |
| G4 | **The held-out tool covers the gate's three fields only** ("gate fields only", v0.4.41). Extending it to the SC fields is a change to a deliberately narrow exception and needs your explicit approval and a PRD change. | You decide; then me |
| G5 | **Spend.** The Phase 6 cap of USD 0.15 has about USD 0.04 or more used (my estimate, computed not read from a manifest; the OD-25 container run added roughly USD 0.001). One extraction call on a real report cost about USD 0.001 (3,805 tokens in, 992 out); a document needing several pages or a retry costs more. SC-11 asks for at most USD 0.25 a document. | You |
| G6 | **Sizes and scans.** The size limit is now 100 MB (it was 25 MB when H3 stopped); OCR needs `--ocr` and a tuned scan; no scanned document has been through the container. | You decide scope |

## 4. Proposed sequence (each step waits for your word)

1. **Decide** the open items in section 5. I write the PRD change that records them (v0.4.69), for your approval; I do not change the PRD without it.
2. **You assign** the new documents (tuning and held-out, public metadata only, before anyone looks) and I append the lines to `assignments.jsonl` and commit them, with the validator test. Only then does anyone open a page.
3. **I build the scoring tool (G3)** offline, against synthetic documents and synthetic label files, with tests and mutation checks as for every earlier tool. It prints counts only. No real document is touched.
4. **Tuning baseline** (live, your approval for each send and for the spend): you run it in your terminal on the tuning documents, as in the gate rounds; I see only the printed counts. I report SC-01 to SC-05, SC-12 and the reason counts.
5. **Fix defects found in the tuning set only**, small changes, each tested (CLAUDE.md), nothing tuned on held-out data.
6. **I propose targets** from the baseline; you approve; the PRD placeholders are replaced.
7. **Held-out run once** (with the extension of G4 if you approve it, otherwise the gate fields only), reported by run id against the approved targets, with SC-06 to SC-11 reported from the test suite and the manifests: SC-10 and SC-11 from the manifests of these runs (the model's real latency and cost), SC-08 from a manual review of each evaluation memo with a checklist (**yours, or someone you name; I cannot judge my own output**).
8. **Evaluation report and exit summary**, as for earlier phases; nothing claimed beyond the recorded counts.

## 5. Decisions for you (proposals marked; none applied)

| # | Decision | Options | Trade-offs | My proposal |
|---|---|---|---|---|
| OD-41 | Which documents, how many, and what coverage | (a) The PRD's plan: about five new public annual reports of non-financial companies, at least one INR with lakh/crore scales and one in another currency; split between tuning and held-out. (b) A smaller set (two tuning, two held-out). (c) Only what exists (no new documents). | (a) is the PRD's design and the only way to a defensible report, with wide uncertainty at this size, reported as counts. (b) is cheaper and gives less. (c) is not possible: all four held-out documents are used and tuning is two. | (a) if labelling effort allows, else (b). **Yours.** Assign before anyone inspects. |
| OD-42 | What the label files cover | (a) The gate's three fields in both periods (as before). (b) The full in-scope field set of SC-01. (c) (a) for held-out, (b) for tuning. | (a) is little labelling and cannot support SC-01 or SC-03. (b) is a lot of hand labelling per document, and is what the PRD's SC-01 means. | (b) for tuning, so the baseline is real, and (a) for held-out unless you approve G4. **Yours.** |
| OD-43 | Extend the held-out tool beyond the gate's three fields (G4) | (a) No: held-out stays gate fields only. (b) Yes: score the SC fields too, by a PRD change that keeps every other precondition. | (a) keeps the narrow exception and gives a held-out report that cannot cover SC-01, SC-03, SC-05. (b) widens a protected path and needs careful tests (a held-out document must still be refused everywhere else). | (b), with a full test of the guard, **if** you want SC-01 on held-out. If not, say so now and the held-out claim will say "gate fields only". |
| OD-44 | Spend cap for 7b | (a) Keep USD 0.15 total. (b) A new cap for 7b, with a per-run token ceiling (NFR-09 already requires one). | (a) is probably too small for five documents with SC fields. Costs so far are about USD 0.001 a document for the gate's pages. | (b), USD 0.50 for 7b, each send still approved by you and run in your terminal. **Yours.** |
| OD-45 | Who does the SC-08 manual review and the labelling check | (a) You. (b) Someone you name. (c) Me (not acceptable for SC-08: I wrote the memo code). | | (a) or (b). |
| OD-46 | Scanned documents in 7b | (a) Out: 7b is text-layer reports; OCR keeps its own tuning evidence (the two tuning scans; S3 closed). (b) In: assign scans and run `--ocr`. | (b) needs scans assigned and labelled and is a second, slower project. | (a). |
| OD-47 | The three closed things | H1 to H4 remain used; S3 and the OD-17 result labels stay untouched; no held-out page opened | | Unchanged, as you have instructed. |

## 6. What 7b will not do

No change to extraction, validation, evidence, calculation, rules, labelling or the memo and report text except defects found **in the tuning set**, each with its own test and your approval. No tuning on held-out data. No accuracy claim from the held-out set before the report exists, and then only counts. I will not open `private/`, read a statement page, or send any document without your explicit approval in your terminal.
