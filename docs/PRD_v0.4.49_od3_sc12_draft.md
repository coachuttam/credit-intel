# PRD v0.4.49 draft: OD-3 decided, the SC-12 target (specification only)

| Item | Value |
|---|---|
| Status | **Draft. Not applied.** `docs/PRD.md` is unchanged (0.4.48). It needs the owner's word and a version bump before anything is edited. |
| Drafted | 2026-10-27 |
| Source | The owner's decision of 2026-10-27 on `docs/OD-3_sc12_options.md`: "Option 2 for OD-3, (a) for locator settings". |
| Version | 0.4.49 |
| Kind | Sets a success-criterion target and closes a decision. No code, setting, locator rule, phrase or test changes. The SC-12 report is not built by this change. |

## 1. What the owner decided

- **Target (Option 2):** a document passes SC-12 only if **every** ground-truth primary-statement page (income statement and balance sheet, continuation pages included) is among the locator's candidate pages. Any missed page fails that document, and the report lists each missed page by number.
- **Locator settings (a):** the FR-013 initial values are kept as they are. No value is adjusted before measuring.

## 2. Points the decision leaves open (my proposals, for you to confirm or change)

| # | Point | Proposal |
|---|---|---|
| 1 | **Documents with more qualifying pages than `max_candidates` (15).** Such a document cannot pass, whatever the locator does. | The report marks it **"cap-limited"** and counts it as **not passed**, with the number of qualifying pages before the cap (the FR-013 observation already records it). It is not excused. A cap-limited result is the evidence for a later decision on the cap, which is a separate owner decision. |
| 2 | **What the target is reported as.** | Per document: pass or fail, ground-truth pages, candidate pages, missed pages. Across a run: "N of M documents passed". No merged percentage of pages. Each held-out run stays separate, by run id (v0.4.42). |
| 3 | **Which documents the target applies to.** | Held-out documents run **after** this version. H1 to H4 were run before a target existed and are not re-scored against it. S3 is OCR-only and outside SC-12. |
| 4 | **Tuning documents.** | They give a counts-only baseline, never a pass/fail judged for a decision, and no setting is changed in response (AC-E-7). Reading their labels in `private/eval/` needs your separate authorisation, which has not been given. |
| 5 | **Rule 4 title scoring** (the "revisit under OD-3 if the cap removes any qualifying page" text). | The text stays. Under (a) nothing is revisited now; a cap removing a qualifying page on a held-out document is reported as a SC-12 failure and is a defect for the owner, not a trigger to retune on that document. |

## 3. Exact text changes if approved

1. **Success-criteria table, SC-12 target cell** (line 192), from *"Not yet set (OD-3). Measured and reported as counts until a target is approved."* to: *"Every ground-truth primary-statement page is a candidate page, **per document** (v0.4.49). A document with any missed page fails and the missed pages are listed. A document with more qualifying pages than `max_candidates` is reported as cap-limited and counts as failed. Reported per held-out run, never merged."*
2. **Evaluation-method row for SC-12** (line 1529): add that the report gives, per document, pass or fail and the missed page numbers.
3. **FR-013 initial-settings paragraph** (line 567): *"validating them is OD-3"* becomes *"the owner decided on 2026-10-27 to keep them (OD-3 option (a)); they stay unvalidated until measured on a held-out run"*.
4. **Appendix A.1 decisions table, OD-3 row** (line 1755): mark **Decided 2026-10-27: target option 2, locator settings option (a)**. **A.2 row** (line 1784): Decided, with the same text.
5. **Item 8 note / Section T.1** (line 1714): unchanged. Release 1's record stays as it is.
6. **Revision history:** a 0.4.49 row, and the version cell and Status cell sentence in Section A.

## 4. What is not changed

The locator rules and settings, SC-10, any other success criterion, the held-out record, the one-shot rule, and Release 1's approval. Rule 7 of the evaluation list (line 684) already says SC-12 is reported; it is edited only to add "against the SC-12 target".

## 5. Implementation consequence

The target cannot be reported until the **SC-12 counting report** exists. It is not built, and this version does not build it. If you approve this draft, the next steps would be, each needing your word:

1. Apply this draft as PRD v0.4.49.
2. Build the report: it takes the candidate pages from a run and the ground-truth pages from a labels file, and prints per-document counts and missed page numbers (counts only; no real figures committed; tests on synthetic data).
3. Authorise a counts-only read of the tuning labels, for a baseline.

## 6. What I need from you

1. Approve, or change, the five proposals in section 2 (point 1 matters most).
2. "Apply" to apply it as v0.4.49.
