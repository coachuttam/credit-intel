# PRD v0.4.30 — draft amendment: the document currency attribute is supported by the cited page, as a field's currency already is (FR-005.8, H.1.2)

| Item | Value |
|---|---|
| Status | **Adopted by the owner on 2026-10-25 ("adopt v0.4.30") and applied to `docs/PRD.md` as v0.4.30.** Kept as the record of the reasoning. |
| Drafted | 2026-10-25 |
| Evidence | Live rounds R2-1 (`extraction_v2`) and R2-3 (`extraction_v4`) on tuning document R2, and their free replays and probes (`PROGRESS.md`), counts and booleans only. Tuning set only (O.2). Nothing from H1 or H2. |
| Changes | FR-005.8 (criterion 8, one sentence), H.1.2 (the `reporting_currency` row of the attribute table), Appendix B.6 examples 68 to 71, Section U, Revision History. |
| Not changed | The presence check (FR-005.1: the quote is on the cited page and the raw text is in the quote), the ISO-code form check, the scale attribute, a field's own currency check, the dependency of fields on `reporting_currency` (H.1.2), or any reason code. No rule is removed; one more source of support is allowed. |

## 1. Why

R2 is a US-style filing. Its pages print `$` beside the first figure of many rows and state the unit in a line such as "(In millions, except per share amounts)". Counts from the live rounds and replays:

- The **field-level** currency check (FR-005.8) passed for all 14 proposals in the replay: the proposed code was USD and the cited page holds a dollar sign. It reads the cited page, or the first page of the statement run.
- The **attribute** `reporting_currency` failed under `extraction_v2` with `currency_not_verified`: its check reads only the model's evidence quote, and the quote it chose was a line with no sign, code or name (the unit line). Under H.1.2, a field may not be `extracted` if its document-level currency is not `extracted`, so 12 of 14 proposals stop on this one attribute.
- A prompt change (`extraction_v4`) did not fix it: the model again quoted a line without the sign, and the same change dropped the `scale` attribute altogether. `extraction_v4` is rejected; the default prompt is unchanged.

So the same fact, "the page declares a currency", is accepted for a field and refused for the document attribute, depending on which line the model happens to quote. The gap is in the rule, not in the page: the model is not asked to find where the sign is, and a quote is a poor place to require it.

## 2. Current text

FR-005.8: "Its currency must be supported in the same way (symbol, ISO code, or currency name)" — for a field, on the cited page or the first page of its statement run. H.1.2 table: `reporting_currency` | ISO 4217 code | "Currency declaration (FR-005.8)". In the code, the attribute's check is `check_currency(code, evidence_quote)`: the quote only.

## 3. Proposed wording

Add to FR-005.8 (criterion 8), after the sentence "No supporting declaration gives `scale_not_verified` or `currency_not_verified`.":

> **The document-level currency (v0.4.30).** The `reporting_currency` attribute is supported when its ISO code, or a symbol or name configured for that code, is in the model's evidence quote **or** on the page the attribute cites. Either source is enough. The two other conditions are unchanged: the quote is on the cited page and the raw text is in the quote (FR-005.1), and the normalised value is a three-letter ISO 4217 code. A page that declares no such sign, code or name leaves the attribute `requires_review` (`currency_not_verified`).

H.1.2, `reporting_currency` row, Check column: "Currency declaration (FR-005.8): in the quote or on the cited page (v0.4.30)".

## 4. Effects and risks

- **Never stricter than today.** The new source is added to the old one. A document that passes today (R1: the quote carries the sign) passes unchanged, so no regression is possible for a document whose quote already carries the sign.
- **Same exposure as a field.** A sign for another currency elsewhere on the same page does not support the proposed code; only a token configured for the proposed code counts, as for fields. A page that declares one currency in its title and mentions another in a note is a risk shared with the field-level check; the attribute does not add to it.
- **R2, expected after this change (to be confirmed by a free replay once built):** the 12 `currency_not_verified` stops clear when the page holds the sign. Whether each field then extracts is not claimed. The two split-figure stops and the interest-expense and borrowings fields are separate.
- **Existing tests:** the cases that expect `currency_not_verified` for a quote without a sign while the page has one change to the new expectation; those with no sign on the page stay.
- **Not in this amendment:** the split-figure rule (net profit and total equity, comparative, on R2), a note page for interest expense, and the R2 borrowings labels.

## 5. New acceptance examples (Appendix B.6, to be added as 68 to 71)

| # | Case (synthetic) | Expected |
|---|---|---|
| 68 | Proposed `reporting_currency` USD; the quote is a line that states only the unit ("(In millions)") and is on the page; the page prints `$` beside a figure | `extracted`; fields that depend on it are not blocked by it |
| 69 | Same, but the page prints no sign, code or name for USD anywhere | `requires_review` (`currency_not_verified`), as today |
| 70 | Proposed `reporting_currency` INR; the page prints only `$` | `requires_review` (`currency_not_verified`): the sign is not one configured for INR |
| 71 | Proposed USD; the quote itself carries `$` (as today) | `extracted`, unchanged |

## 6. What I need from the owner

1. Adopt the wording in section 3, change it, or leave R2 out of the gate.
2. If adopted, I apply the PRD as v0.4.30, implement it in one small step with tests and a free replay of R2, and stop for your approval before any live call. No further live round is needed to test it: the cached reply from R2-1 under the default prompt can be replayed.
