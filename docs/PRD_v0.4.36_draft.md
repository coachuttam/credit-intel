# PRD v0.4.36 — draft amendment: a currency or scale declaration is verified on the page that holds it (H.1.2, FR-005.1, FR-005.8)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25, with two additions, and applied to `docs/PRD.md` as v0.4.36. Kept as the record of the reasoning.** Additions: (1) no repair if the candidate pages declare conflicting currencies or scales (example 100 and 101 below); (2) each repair (page cited → page used) is recorded in the manifest. The cited page is therefore not kept in the attribute record, only in the manifest. |
| Drafted | 2026-10-25 |
| Evidence | Tuning report R2, the runs with the Note 3 page added (pages 36 to 38 and 49), under three prompts (`extraction_v4` earlier on pages 36-38, `extraction_v5` and `extraction_v7` on 36-38,49): counts and booleans only. Tuning set only (O.2). |
| Changes | H.1.2 (the check column for `reporting_currency` and `scale`), the record of an attribute (one optional field), Appendix B.6 examples 96 to 100, Revision History. |
| Not changed | Which attributes exist, their statuses, FR-005.8's tests of what a declaration says (symbol, code, name; the scale word), `statement_basis` (its page is the title block of the cited page and is never repaired), `period_end`, `entity_name`, and every field check. |

## 1. Why: what R2 shows

With four candidate pages the model cites **page 36** for the currency and scale attributes in every run, with the 13-character quote `(In millions)`. That text is on pages **37, 38 and 49**; page 36 prints a longer unit line (`(In millions, except per share amounts)`). The evidence check (the quote must be on the cited page) refuses both attributes, and every field that depends on them (H.1.2) stops at `scale_not_verified`: 16 of 16 proposals, including the profit before tax and interest expense the gate needs, whose own checks pass.

Two prompt changes aimed at it did not move the model: `extraction_v5` kept citing page 36; `extraction_v7`, which says outright that `page_number` is the page holding the quote, cited page 36 again and also dropped the scale attribute. The same attributes are accepted when the run has three pages, so the declaration is right and on the pages; only the **page number the model writes** is wrong.

## 2. The proposal

For `reporting_currency` and `scale` **only**, change the evidence check from "the quote is on the page the model cited" to:

> The quote must be on at least one candidate page of the run. If it is on the cited page, that page is the attribute's page. If it is not, the attribute's page is the **lowest-numbered candidate page that holds the quote**, and the record keeps the page the model cited as `cited_page`. If it is on no candidate page, the attribute is `requires_review` (`evidence_not_verified`), as today. Everything else about the attribute (the raw text in the quote, the ISO code, the declaration test of FR-005.8 and its source, v0.4.30) is unchanged.

Why only these two: a currency or scale declaration is a statement about the whole set of statements and is repeated on page after page; which page it is read from does not change what it says. `statement_basis` is different (it is the title block of a particular page, H.4.6) and so are `period_end` and `entity_name`; they keep the strict rule.

## 3. Effects and risks

- **R2:** the cached run on pages 36-38,49 under `extraction_v5` has its currency and scale quotes on pages 37, 38 and 49; the attributes would be extracted and the 16 proposals would reach their own checks (the join of v0.4.35 already clears the four split-figure stops). Whether the gate values then match is for the gate.
- **A wrong repair** needs the quote to be a real declaration text that exists on a candidate page: the declaration test still applies to that text, and the field-level scale and currency checks (FR-005.8) still read each field's own cited page or its statement run's first page. A page with a different unit would still give `scale_ambiguous` or `scale_not_verified` at the field.
- **Deterministic and replayable:** the page is chosen by the code from the text, not by the model.
- **Held-out reports** with several candidate pages benefit equally; a single-page run is unchanged.

## 4. Acceptance examples (Appendix B.6, to be added as 96 to 100; synthetic pages)

| # | Case | Expected |
|---|---|---|
| 96 | Currency quote `(In millions)` cited on page 1; it is on pages 2 and 3, not page 1 | `extracted`; its page is 2; `cited_page` is 1 |
| 97 | The same quote cited on the right page | `extracted`; no `cited_page` |
| 98 | The quote is on no candidate page | `requires_review` (`evidence_not_verified`) |
| 99 | A `statement_basis` quote that is on another page than the cited one | still `requires_review`: no repair |
| 100 | The quote is on another page and the candidate pages declare two scales | not repaired; `requires_review` (`scale_ambiguous`) |
| 101 | The same with two currencies | not repaired; `requires_review` (`currency_not_verified`) |

## 5. What I need from the owner

1. Approve, change or reject section 2 (including that only `reporting_currency` and `scale` are repaired).
2. If approved, I implement it in one step with tests and mutation checks, replay the cached R2 runs for free, and show the gate counts, with no live call.
