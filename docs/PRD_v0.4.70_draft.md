# PRD v0.4.70 — draft for the owner's approval (targets for Phase 7b; not applied)

Nothing below is applied to `docs/PRD.md`. It records your decisions of 2026-11-04 on `docs/PHASE7b_targets_proposal.md` (committed `3d9a00c`; corrected afterwards in one place, see section 6) and replaces the placeholders of E.2 for SC-01, SC-03 and SC-05 (O.3 step 3). On your word I apply it as written, run the suite and commit. It changes no code and no setting of the product. Nothing was run for this draft and no held-out document was opened.

## 1. Header cells

- **Version** 0.4.69 → 0.4.70. **Status:** v0.4.69 → v0.4.70, plus the sentence: "**v0.4.70 (2026-11-04)** records the tuning baseline of Phase 7b and the owner's approval of the targets that replace the E.2 placeholders for SC-01, SC-03 and SC-05; it changes no other requirement."
- **Implementation status:** no change.

## 2. E.2, the three rows (the new target cells)

| ID | New "Provisional target" cell |
|---|---|
| SC-01 | "**Targets (v0.4.70, approved 2026-11-04; counts, not percentages).** *Tuning set, regression bar, full field set:* 36 of 36 labelled-present fields matched (baseline of 2026-11-04, R1 14/14 and R2 22/22); a change is explained before the held-out run. *Held-out run (Phase 7b: H5 and H6, the gate's three fields, both periods, up to 12 values; OD-43):* **at least 11 of 12 values match and none is a mismatch** (a value that differs from the owner's reference). The 90% placeholder it replaces is the same bar in counts. No held-out figure exists for the other nine fields; those are tuning evidence only. Reported as counts on two documents, with no accuracy claim beyond that (O.2)." |
| SC-03 | "**Targets (v0.4.70).** *Tuning set:* 12 of 12 labelled-absent fields reported `not_found` (10 + 2). *Held-out run:* **every** entry the owner labels 'the report presents none' is reported `not_found`; if the held-out references hold no such entry, SC-03 is reported as **not measured** and is not counted as met. The 95% placeholder it replaces is the same bar for fewer than 20 cases." |
| SC-05 | "**Targets (v0.4.70).** *Tuning set:* 34 of 34 matched source values cite a labelled page (a derived value has no cited page and is left out). *Held-out run:* **every** matched source value cites a page the owner labelled; the denominator is reported. The 95% placeholder it replaces is the same bar for fewer than 20 cases." |

SC-02 and SC-04 keep their text. The baseline for SC-02 is zero candidates in either direction (extracted for an absent field; extracted with a different value), and for SC-04 34 of 34.

## 3. Section Q, row 7b (progress cell)

→ keep the text of v0.4.69 and replace its last sentence ("Not started.") with: "**Status (v0.4.70):** step (1) done: the scorer (`score.py`, `ce5ded8`, `e73080b`) and the baseline of 2026-11-04 (SC-01 36/36, SC-02 none, SC-03 12/12, SC-04 34/34, SC-05 34/34, SC-12 2 of 2 documents, no `requires_review` reason); step (2) empty, since no defect was found; step (3) done by the owner's approval of the targets in E.2 and OD-48. Steps (4) to (6) not started. The held-out references for H5 and H6, the move of the response cache aside and the commit the run names are the owner's and mine, in that order, before the run."

## 4. Decision row (after OD-47)

| ID | Decision | Options | Decision / proposal | Status |
|---|---|---|---|---|
| OD-48 | **Decided 2026-11-04: T1 as proposed; T2 option (A).** Targets for Phase 7b | (A) 11 of 12 held-out values match with no mismatch; every labelled-absent entry `not_found` (else 'not measured'); every matched source value on a labelled page. (B) 12 of 12. (C) counts only, no pass/fail. | (A), equal to the E.2 placeholders in counts. Chosen over (B) because, with a two-document correlated sample and the only earlier held-out results at 0/12 and 0/6, a literal 12/12 would say little about the system whatever it did. The tuning baseline (36/36, 12/12, 34/34, 34/34, zero SC-02 candidates) is the regression bar (T1). Pre-commitments: a miss is reported as a miss; a document inspected to find out why moves to the tuning set and the next report says so (O.2); nothing from the held-out run changes the prompt, locator, labels or thresholds before it is reported; the response cache is moved aside (so the tuning baseline stays replayable) and the tree is clean at the commit the owner names; the references, including `pages` and `assert_basis` if needed, are the owner's labelling and every run option is fixed before the one shot. | Targets set. The held-out run is not done. |

## 5. Revision row 0.4.70 (2026-11-04)

"**Specification change: targets for Phase 7b (O.3 step 3), authorised by the project owner on 2026-11-04** ('T1 approved ... T2: Option A ... draft PRD v0.4.70'). Replaces the E.2 placeholders for SC-01, SC-03 and SC-05 with the counts in section 2 and records the baseline, OD-48 and the status of row 7b. **The effect, plainly:** the held-out bar is the old placeholder expressed in counts, on at most 12 values from two documents and three fields; the tuning baseline is perfect on two documents the system was tuned on and is a regression bar, not a rate for unseen reports; the full field set has no held-out figure this round (OD-43). **Not changed:** any requirement of the product, any setting, any code. **Not started:** the held-out run."

## 6. A correction to the proposal

My first draft of the proposal said the locator found no candidates on R2. SC-12 shows it finds both statement pages (2 of 2); R2's pages were given by hand because their titles name no basis and the run drops such pages. The proposal and `PROGRESS.md` now say that. It changes no target.

## 7. After approval

I apply it, run the suite and commit. The remaining 7b steps, in order, each on your word: the references for H5 and H6 are yours to write; I then move `.cache/llm` aside, check the tree is clean at the commit you name, and you run the one held-out command with the owner's approval variable. I report by run id, counts only.
