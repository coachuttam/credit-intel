# PRD v0.4.42 — amendment: the held-out run covers the held-out documents no earlier run has used (O.2, v0.4.41)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-26 and applied to `docs/PRD.md` as v0.4.42, with implementation. Kept as the record of the reasoning.** |
| Drafted | 2026-10-26 |
| Evidence | The first held-out run (run H-20261025T174648Z) used H1 and H2. The owner then assigned H3 and H4 as held out (2026-10-26). H1 and H2 stay recorded as held out and are used. |
| Changes | The required set of the held-out run tool (O.2 text of v0.4.41), two refusal definitions, Appendix B.6 examples 142 to 144, a requirement note for the evaluation report, the Revision History. |
| Not changed | The freeze check, the ledger, the one-shot rule, the other refusal words, the send exception, the output labelling. |

## 1. The problem

v0.4.41 requires a run to cover exactly the documents the record shows as held out, and refuses a document that has a ledger line. After H3 and H4 are assigned, the record shows H1, H2, H3 and H4 as held out. H1 and H2 are used, so a run over all four is refused (`already_used`) and a run over H3 and H4 alone is refused (`not_the_held_out_set`): no later run could start.

## 2. The change

> **Required set (v0.4.42).** A held-out run covers exactly the documents the assignment record shows as held out that have **no line in the ledger**. A document an earlier run used stays recorded as held out, and is neither required nor allowed in a later run. A run is refused (`already_used`) if a document given has a ledger line, or if no held-out document without a ledger line remains. A held-out document without a ledger line that is left out, an extra document, or a document given twice is refused (`not_the_held_out_set`).

## 3. Requirement note for the evaluation report

When the success-criteria report (SC-01 to SC-12) is built, it reports **each held-out run separately, by run id**, and never merges runs into one pass rate or one set of counts.

## 4. Tests

Three new tests: a used document is not required and a run over the unused one proceeds; with every held-out document used the run is refused whether or not any document is given; a used document given with an unused one refuses the whole run. One more: an unused document left out is still refused.
