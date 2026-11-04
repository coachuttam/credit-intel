# Phase 7b, step 3: the tuning baseline and proposed targets (a proposal for the owner's approval)

Dated 2026-11-04. Nothing here is a PRD change. Approving it replaces the placeholders in E.2 (O.3 step 3), which is a PRD change with a version bump, drafted only on the owner's word. No held-out document has been opened, and nothing was sent for this document.

## 1. The baseline (tuning set only, counts only)

The owner reported these figures, and I re-ran `score --report` on the cache (offline, nothing sent) and got the same counts. Assignment record last touched at `6c12512`; scorer `ce5ded8`/`e73080b`; prompt `extraction-v5`; gpt-4o-mini; max output 4096.

| Measure | R1 | R2 | Together |
|---|---|---|---|
| SC-01 (labelled present, value, scale, currency, period end) | 14/14 | 22/22 | **36/36** |
| SC-02 candidates (extracted for an absent field; extracted with a different value) | 0 / 0 | 0 / 0 | **0 / 0** |
| SC-03 (labelled absent, reported `not_found`) | 10/10 | 2/2 | **12/12** |
| SC-04 (extracted source records that passed every check) | 14/14 | 20/20 | **34/34** |
| SC-05 (cited page among the labelled pages, for matched source values) | 14/14 | 20/20 | **34/34** |
| `requires_review` reasons; `conflicting` | none | none | none |

R2's two derived total-borrowings values are matched but have no cited page, which is why SC-04 and SC-05 have 34, not 36. **SC-12 (run 2026-11-04, offline, counts only, `recall`):** R1 passed: all 4 ground-truth statement pages are among 9 candidate pages, none missed, not cap-limited. R2 passed: both ground-truth pages are among 2 candidate pages, none missed. 2 of 2 documents pass the v0.4.49 target.

No defect was found, so step 2 (fixes in the tuning set) is empty and the tree stays at the commit the held-out run will name.

## 2. What the baseline does and does not tell us

**It tells us**
- On these two documents, with these labels, nothing diverges: no wrong value, no value for an absent field, no `requires_review`. The scorer and the labels agree with the pipeline field for field.
- Two currencies and scales (INR crore, USD millions) and two derivations of total borrowings (none presented; a sum of three parts) work on real documents.
- Every extracted source value passed the deterministic checks and cited a labelled page.

**It does not tell us**
1. **It is not a rate for unseen documents.** Both documents were used to tune. The prompt (`extraction-v5`), the locator phrases and the borrowings handling were adopted in rounds on R1 and R2. A 100% on them is partly by construction.
2. **The only earlier held-out results were poor.** The first held-out round matched 0/12 (H1, H2) and 0/6 (H4); H3 was never read (the old size limit). Those documents have been used and are closed, and the pipeline has changed since, but they are the only out-of-sample evidence this project has. A fresh pass is not to be assumed.
3. **Two documents, correlated fields.** The 36 fields come from two reports, not 36 independent samples. Taken as independent (which flatters), a perfect 36/36 gives a one-sided 95% lower bound of about 92% for SC-01; 34/34 about 92% for SC-05; 12/12 about 78% for SC-03. Over two documents the honest figure is wider than these.
4. **SC-03 is thin and structural.** Of the 12 absent entries, 10 are R1's five fields over two periods (no borrowings family and no operating profit, because R1 has no borrowings at all), and 2 are R2's interest expense. That is six distinct absent cases, and none is the hard one: a field the report does print under a name the model might mistake.
5. **R2 did not run on the locator's choice of pages.** Its pages (36 and 38) were given by hand with a basis assertion, because their titles name no basis and the run drops such pages. (Correction of my first wording, which repeated that the locator finds no candidates there: SC-12 below shows it does find both statement pages. What R2 did not exercise is a run that goes from locator to extraction without a page range.) R1 ran through the locator.
6. **Never seen in real use:** a `requires_review` reason, a `conflicting` field, a standalone basis, a scanned page, a statement longer than two pages for one statement type, a value in a note rather than on the face of the statements.
7. **The held-out run measures 3 of 12 fields.** By OD-43 the held-out tool compares only profit before tax, interest expense and total borrowings, both periods. Nine of the twelve fields (revenue, net profit, operating profit, current assets and liabilities, the three borrowings parts, total equity) have a tuning figure and no held-out figure. SC-01, SC-03 and SC-05 are therefore tuning evidence for the full set, and held-out evidence for these three fields only.
8. **SC-04 is consistency, not correctness** (PRD SC-04): it shows the extracted values agree with the cited text.

## 3. Proposed targets

**Principle.** The baseline gives no reason to tighten the E.2 placeholders (it is a fit to the tuning set) and none to loosen them (no failures). With at most 12 held-out values, a percentage is one or two values wide, so the targets are stated as counts that equal the placeholders.

**T1 — the tuning set, as a regression bar (full field set).** SC-01 36/36, SC-03 12/12, SC-04 34/34, SC-05 34/34, SC-02 0 candidates. Any change from this after 7b is explained before the held-out run. This is a statement about R1 and R2, not about unseen reports.

**T2 — the held-out set, once (the gate's three fields; H5 and H6; up to 12 values).** Recommended:

| Measure | Target for the held-out run | Equivalent to the E.2 placeholder |
|---|---|---|
| SC-01 | at least **11 of 12** values match, **and no mismatch** (a wrong value is a finding whatever the count) | 90% |
| SC-03 | **every** held-out entry labelled "report presents none" is reported `not_found`; if there is none, reported as **not measured**, not as met | 95%, with fewer than 20 cases |
| SC-05 | **every** matched source value cites a labelled page; the denominator is reported | 95%, with fewer than 20 cases |
| SC-02 | any value given for an absent field, and any wrong value, is listed and looked at individually | "investigate every occurrence" |

Options: (A) the table above, recommended; (B) stricter, 12/12 for SC-01; (C) no pass/fail, counts only. Under any option the result is reported as counts on two documents ("x of y"), with no accuracy claim beyond that (O.2).

**Pre-commitments I propose to record with the targets**
- A miss is reported as a miss. A document inspected to find out why moves to the tuning set, and the next report says so (O.2). Nothing from the held-out run changes the prompt, locator, labels or thresholds before it is reported.
- The held-out tool needs the response cache empty and a clean tree at the commit you name. I propose to move the current `.cache/llm` aside (as was done in `llm_replay_backup`), so the R1 and R2 baseline stays replayable, and to name the commit at that time.
- You, not the pipeline, write the H5 and H6 references, including `pages` and `assert_basis` if a page range is needed. The owner labelling from rendered pages is allowed by O.2; reading pipeline output of a held-out document is not.
- One shot per document: the ledger allows it, so a document that stops on a catalogued error is used up (as H3 was). Every option the run needs (page range, basis assertion, token ceiling) is therefore fixed in the reference and the command before the run, from public metadata and your labelling, not from any trial run on the held-out pages.

## 4. What I need from you

1. Approve T1 and T2 (A, B or C), or change them.
2. Say whether to run SC-12 for the baseline now (offline, counts).
3. On approval I draft PRD v0.4.70 (E.2 targets and the row 7b step) for your approval before applying it.
