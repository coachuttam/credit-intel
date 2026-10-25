# PRD v0.4.37 — draft amendment: the code reads the currency and scale declaration when the model's proposal is missing or has no usable evidence (H.1.2, FR-005.8)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("approve v0.4.37"); applied to `docs/PRD.md` as v0.4.37 and implemented. Kept as the record of the reasoning.** |
| Drafted | 2026-10-25 |
| Evidence | Tuning report R2 with the Note 3 page added (pages 36 to 38 and 49), four prompts, counts and booleans only (`PROGRESS.md`, gate steps 4 to 6). Tuning set only (O.2). |
| Changes | H.1.2 (one paragraph), FR-005.8 (a pointer), the manifest (a block, only when it applies), Appendix B.6 examples 102 to 108, Revision History. |
| Not changed | `statement_basis`, `period_end`, `entity_name`; any attribute the model proposed that verified (it is kept); an attribute whose proposal **contradicts** the pages (it stays `requires_review`); every field check; every value. |

## 1. Why

The gate's remaining blocker is not the fields. It is two document-level attributes, the currency and the scale, which the model has to propose and which gate every field (H.1.2). On R2 with four candidate pages the same report has been read four ways:

| Prompt | Currency and scale attributes | Result |
|---|---|---|
| `extraction_v5` | proposed, quote on the wrong page (fixed by v0.4.36) | 16 of 16 fields extract |
| `extraction_v4` | currency not on the page, scale lost | 0 |
| `extraction_v6` | `value_not_in_evidence`, current-period fields only | 0 |
| `extraction_v7` | currency `evidence_not_verified`, scale never proposed | 0 |

The pages declare the same thing every time: one unit line (`(In millions…)`) and one currency sign. Every field's own checks (FR-005.8) read that declaration from the page already. Only the **document-level record of it** depends on what the model chooses to quote, and that varies with every prompt change. A gate that passes only on the one reply where the model happened to write a usable quote is not a gate a held-out report can be expected to pass.

## 2. The proposal

For `reporting_currency` and `scale` **only**, after the model's proposals are verified (including the page repair of v0.4.36), if the attribute is not `extracted` **because there was no usable proposal**, the code reads the declaration from the candidate pages:

> **Declared by the pages (v0.4.37).** An attribute is derived by the code when (a) the model proposed none, or its proposal failed with `evidence_not_verified` or `value_not_in_evidence` (it has no usable evidence), and (b) the candidate pages declare **exactly one** value of it between them: one scale (the scale words of FR-005.8, any page) or one currency code (an ISO code, or a symbol or name configured for one). The derived record takes the **lowest-numbered candidate page** that declares it, the line of that page that holds the declaration as its quote, and the declaration as printed as its raw text; it is `extracted`. The derivation is recorded in `manifest.json` (`attribute_derivations`: the attribute, the page, and why: no proposal, or the proposal's failure). **Nothing is derived** when the pages declare more than one value (the attribute stays as the model left it, `requires_review`/`not_found`), when they declare none, or when the model's proposal failed because it **contradicts** the pages (`scale_not_verified`, `scale_ambiguous`, `currency_not_verified`): a claim that disagrees with the page is a warning, not a gap to fill. A proposal that verified is never replaced.

## 3. Why this is safe and narrow

- **The same evidence, read by code.** The declaration is a printed fact on a candidate page; the code finds it with the tests FR-005.8 already applies to the model's quote. The result is deterministic and replayable from the pages alone.
- **Two attributes only.** The basis is a statement about one page's title (H.4.6) and is covered by the analyst's assertion where needed; the period and the entity are not declarations that repeat across pages.
- **Contradiction and conflict fail safe.** A wrong claim by the model, or two scales on the candidate pages, never produce a value.
- **Fields still check themselves.** Each field's scale and currency are checked on its own page or its statement run's first page (FR-005.8). A field on a page with a different unit still fails there.
- **One ambiguity to accept:** a symbol can stand for more than one currency. The configured table maps `$` to USD only; if the owner wants `$` to be ambiguous (and so never derived), it is one entry in the table.

## 4. Expected effect (to be confirmed by a free replay once built)

On R2, the `extraction_v7` reply (scale never proposed, currency without usable evidence) and the `extraction_v5` reply would both have their two attributes derived from pages 36 to 38 and 49, which declare millions and one currency sign. The v7 reply's 16 proposals should then extract; the gate for R2 would stand at the same 4 matched, 2 missing (total borrowings, which depends on the debt rows) as under v5. The `extraction_v6` reply has no comparative proposals, so it would still be incomplete. If a held-out report's pages declare two scales (for example `in millions` and `in thousands`), nothing changes for it.

## 5. Acceptance examples (Appendix B.6, to be added as 102 to 108; synthetic pages)

| # | Case | Expected |
|---|---|---|
| 102 | The model proposes no scale; the candidate pages declare `in millions` only | `extracted`, `millions`, the lowest page that declares it and that line as the quote; recorded in the manifest |
| 103 | The model's currency proposal fails with `value_not_in_evidence`; the pages carry `$` only | `extracted`, `USD`, recorded in the manifest |
| 104 | The model proposes `crore`; the pages declare `in millions` | not replaced: `requires_review` (`scale_not_verified`) |
| 105 | The pages declare `in millions` on one page and `in thousands` on another | not derived |
| 106 | The pages carry `$` on one page and `₹` on another | not derived |
| 107 | The model's proposal verified | kept; no derivation recorded |
| 108 | No candidate page declares a scale | stays `not_found`; never guessed |

## 6. What I need from the owner

1. Approve, change or reject section 2 (including that a proposal which contradicts the pages is not overridden, and that `$` maps to USD as configured).
2. If approved, I implement it with tests and mutation checks, replay the cached R2 runs for free (v5, v6, v7) and show the gate counts, with no live call.
3. Then the R2 `extraction_v8` live round (your option 1), with R1 for the adoption check, as already set out.
