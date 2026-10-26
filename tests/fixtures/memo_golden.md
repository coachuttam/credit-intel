# Draft credit memo

**Borrower:** Acme Industries Limited [SOURCE: p.1]  
**Document reviewed:** statement.pdf [CALCULATED: document]  
**Run ID:** `20261024T101530.123456Z-0dd49919`  
**Generated:** `20261024T101530.123456Z` (UTC)

> **DRAFT — generated for human review. Not a credit decision. Verify all figures against the cited sources.**

**Origin labels**

| Label | Meaning |
|---|---|
| `[SOURCE: p.N]` | A value or quote taken verbatim from the document and verified on page N. |
| `[CALCULATED: ID]` | Computed deterministically by the platform from source values, or recorded by it about the run. The ID is in `results.json`. |
| `[RULE: RI-xxx]` | Produced by a configured risk rule. |
| `[ANALYST-PROVIDED]` | Supplied in the borrower profile input; not verified against the document. |
| `[UNVERIFIED]` | Could not be traced to evidence. |

## 1. Borrower overview

- **Entity name** (`entity_name`): Acme Industries Limited [SOURCE: p.1]
- **Reporting currency** (`reporting_currency`): INR [SOURCE: p.1]
- **Scale** (`scale`): crore [SOURCE: p.1]
- **Statement basis used:** consolidated [CALCULATED: extraction]
- **Current period end** (`period_end.current`): 2025-03-31 [SOURCE: p.1]
- **Comparative period end** (`period_end.comparative`): 2024-03-31 [SOURCE: p.1]

**Analyst-provided profile**

No borrower profile was supplied.

## 2. Documents reviewed

- **File name:** statement.pdf [CALCULATED: document]
- **SHA-256:** `0dd49919cbf0d0d50ee6aa5183ed3b19be9188eed39287c3539b4d3d5bc6b110` [CALCULATED: document]
- **Page count:** 1 [CALCULATED: document]
- **Statement basis used:** consolidated [CALCULATED: extraction]
- **Other bases present:** none [CALCULATED: extraction]
- **Pages used:** 1 (located by keywords) [CALCULATED: extraction]
- **Extraction date:** `20261024T101530.123456Z` (UTC) [CALCULATED: document]

## 3. Financial performance

Values are shown as printed in the document, with scale and currency; derived values are in whole units. The exact stored values are in `results.json`.

| Field ID | Value | Status | Origin | Notes |
|---|---|---|---|---|
| `revenue.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `revenue.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `net_profit.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `net_profit.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `operating_profit.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `operating_profit.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `profit_before_tax.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `profit_before_tax.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `interest_expense.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `interest_expense.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `current_assets.2025-03-31.consolidated` | 1,482.30 (INR crore) | extracted | [SOURCE: p.1] | — |
| `current_assets.2024-03-31.consolidated` | 1,356.75 (INR crore) | extracted | [SOURCE: p.1] | — |
| `current_liabilities.2025-03-31.consolidated` | 900.00 (INR crore) | extracted | [SOURCE: p.1] | — |
| `current_liabilities.2024-03-31.consolidated` | 850.00 (INR crore) | extracted | [SOURCE: p.1] | — |
| `borrowings_non_current.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `borrowings_non_current.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `borrowings_current.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `borrowings_current.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `current_maturities_long_term_borrowings.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `current_maturities_long_term_borrowings.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | — |
| `total_equity.2025-03-31.consolidated` | 600.00 (INR crore) | extracted | [SOURCE: p.1] | — |
| `total_equity.2024-03-31.consolidated` | 500.00 (INR crore) | extracted | [SOURCE: p.1] | — |
| `ebit.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | missing input; `ebit = profit_before_tax + interest_expense` (EBIT-PBT) |
| `ebit.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | missing input; `ebit = profit_before_tax + interest_expense` (EBIT-PBT) |
| `total_borrowings.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | missing input; `total_borrowings = borrowings_non_current + borrowings_current` (BORR-SUM); no total is reported, so it is derived |
| `total_borrowings.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | missing input; `total_borrowings = borrowings_non_current + borrowings_current` (BORR-SUM); no total is reported, so it is derived |

## 4. Financial ratios

Ratios are rounded for display (percentages to one decimal place, ratios to two); `results.json` keeps full precision.

| Metric ID | Metric | Value | Formula | Inputs | Origin |
|---|---|---|---|---|---|
| `MET-01.2025-03-31` | Revenue growth | not defined: missing input | `(revenue_current - revenue_comparative) / revenue_comparative x 100` | `revenue.2025-03-31.consolidated`, `revenue.2024-03-31.consolidated` | [CALCULATED: MET-01.2025-03-31] |
| `MET-02.2024-03-31` | Net profit margin | not defined: missing input | `net_profit / revenue x 100` | `net_profit.2024-03-31.consolidated`, `revenue.2024-03-31.consolidated` | [CALCULATED: MET-02.2024-03-31] |
| `MET-02.2025-03-31` | Net profit margin | not defined: missing input | `net_profit / revenue x 100` | `net_profit.2025-03-31.consolidated`, `revenue.2025-03-31.consolidated` | [CALCULATED: MET-02.2025-03-31] |
| `MET-03.2024-03-31` | Current ratio | 1.60 | `current_assets / current_liabilities` | `current_assets.2024-03-31.consolidated`, `current_liabilities.2024-03-31.consolidated` | [CALCULATED: MET-03.2024-03-31] |
| `MET-03.2025-03-31` | Current ratio | 1.65 | `current_assets / current_liabilities` | `current_assets.2025-03-31.consolidated`, `current_liabilities.2025-03-31.consolidated` | [CALCULATED: MET-03.2025-03-31] |
| `MET-04.2024-03-31` | Debt-to-equity ratio | not defined: missing input | `total_borrowings / total_equity` | `total_borrowings.2024-03-31.consolidated`, `total_equity.2024-03-31.consolidated` | [CALCULATED: MET-04.2024-03-31] |
| `MET-04.2025-03-31` | Debt-to-equity ratio | not defined: missing input | `total_borrowings / total_equity` | `total_borrowings.2025-03-31.consolidated`, `total_equity.2025-03-31.consolidated` | [CALCULATED: MET-04.2025-03-31] |
| `MET-05.2024-03-31` | Interest coverage ratio | not defined: missing input | `ebit / interest_expense` | `ebit.2024-03-31.consolidated`, `interest_expense.2024-03-31.consolidated` | [CALCULATED: MET-05.2024-03-31] |
| `MET-05.2025-03-31` | Interest coverage ratio | not defined: missing input | `ebit / interest_expense` | `ebit.2025-03-31.consolidated`, `interest_expense.2025-03-31.consolidated` | [CALCULATED: MET-05.2025-03-31] |

**Change from the comparative period to the current period**

| Metric | Relative change | Origin |
|---|---|---|
| `MET-02` | not defined: missing input | [CALCULATED: MET-02] |
| `MET-03` | 3.2% | [CALCULATED: MET-03] |
| `MET-04` | not defined: missing input | [CALCULATED: MET-04] |
| `MET-05` | not defined: missing input | [CALCULATED: MET-05] |


## 5. Potential risk indicators

> The thresholds are illustrative placeholders chosen for demonstration and testing. They are not universal banking standards, regulatory requirements or the policy of any institution. Real thresholds vary by institution, industry, borrower size and product, and must be set by the institution's credit policy. [CALCULATED: provisional_notice]

Indicators are prompts for a human to investigate. They are not a rating, a score or a credit decision.

> **RI-006 Missing financial information — info** [RULE: RI-006]
>
> Condition C1 (info): an input that revenue growth, net profit margin, the current ratio, debt-to-equity or interest coverage needs is not found. [RULE: RI-006]  
> Observed: inputs not found = 10 [RULE: RI-006]  
> Fields: `revenue.2025-03-31.consolidated` not found [UNVERIFIED]; `net_profit.2025-03-31.consolidated` not found [UNVERIFIED]; `total_borrowings.2025-03-31.consolidated` not found [UNVERIFIED]; `ebit.2025-03-31.consolidated` not found [UNVERIFIED]; `interest_expense.2025-03-31.consolidated` not found [UNVERIFIED]; `revenue.2024-03-31.consolidated` not found [UNVERIFIED]; `net_profit.2024-03-31.consolidated` not found [UNVERIFIED]; `total_borrowings.2024-03-31.consolidated` not found [UNVERIFIED]; `ebit.2024-03-31.consolidated` not found [UNVERIFIED]; `interest_expense.2024-03-31.consolidated` not found [UNVERIFIED]

**Rules that could not be evaluated**

- **RI-001 Declining revenue:** not evaluable; missing `MET-01.2025-03-31 (missing_input)` [RULE: RI-001]
- **RI-002 Negative net profit:** not evaluable; missing `net_profit.2025-03-31 (not_found)` [RULE: RI-002]
- **RI-004 Increasing leverage:** not evaluable; missing `MET-04.2025-03-31 (missing_input)`, `MET-04.2024-03-31 (missing_input)` [RULE: RI-004]
- **RI-005 Weak interest coverage:** not evaluable; missing `MET-05.2025-03-31 (missing_input)` [RULE: RI-005]

**Rules evaluated and not triggered:** RI-003 Deteriorating liquidity, RI-007 Conflicting or unverified source values [RULE: RI-003] [RULE: RI-007]

## 6. Evidence and source references

**`current_assets.2025-03-31.consolidated`** — page 1, line item “Total current assets”, value as printed 1,482.30 [SOURCE: p.1]

> Total current assets 14 1,482.30 1,356.75

**`current_assets.2024-03-31.consolidated`** — page 1, line item “Total current assets”, value as printed 1,356.75 [SOURCE: p.1]

> Total current assets 14 1,482.30 1,356.75

**`current_liabilities.2025-03-31.consolidated`** — page 1, line item “Total current liabilities”, value as printed 900.00 [SOURCE: p.1]

> Total current liabilities 15 900.00 850.00

**`current_liabilities.2024-03-31.consolidated`** — page 1, line item “Total current liabilities”, value as printed 850.00 [SOURCE: p.1]

> Total current liabilities 15 900.00 850.00

**`total_equity.2025-03-31.consolidated`** — page 1, line item “Total equity”, value as printed 600.00 [SOURCE: p.1]

> Total equity 600.00 500.00

**`total_equity.2024-03-31.consolidated`** — page 1, line item “Total equity”, value as printed 500.00 [SOURCE: p.1]

> Total equity 600.00 500.00

**Derived values**

- `ebit.2025-03-31.consolidated` — method EBIT-PBT: `ebit = profit_before_tax + interest_expense`; inputs `profit_before_tax.2025-03-31.consolidated`, `interest_expense.2025-03-31.consolidated` [CALCULATED: ebit.2025-03-31.consolidated]
- `ebit.2024-03-31.consolidated` — method EBIT-PBT: `ebit = profit_before_tax + interest_expense`; inputs `profit_before_tax.2024-03-31.consolidated`, `interest_expense.2024-03-31.consolidated` [CALCULATED: ebit.2024-03-31.consolidated]
- `total_borrowings.2025-03-31.consolidated` — method BORR-SUM: `total_borrowings = borrowings_non_current + borrowings_current`; inputs `borrowings_non_current.2025-03-31.consolidated`, `borrowings_current.2025-03-31.consolidated` [CALCULATED: total_borrowings.2025-03-31.consolidated]
- `total_borrowings.2024-03-31.consolidated` — method BORR-SUM: `total_borrowings = borrowings_non_current + borrowings_current`; inputs `borrowings_non_current.2024-03-31.consolidated`, `borrowings_current.2024-03-31.consolidated` [CALCULATED: total_borrowings.2024-03-31.consolidated]

## 7. Missing information and conflicts

**Not found** (20)

- `revenue.2025-03-31.consolidated` [UNVERIFIED]
- `revenue.2024-03-31.consolidated` [UNVERIFIED]
- `net_profit.2025-03-31.consolidated` [UNVERIFIED]
- `net_profit.2024-03-31.consolidated` [UNVERIFIED]
- `operating_profit.2025-03-31.consolidated` [UNVERIFIED]
- `operating_profit.2024-03-31.consolidated` [UNVERIFIED]
- `profit_before_tax.2025-03-31.consolidated` [UNVERIFIED]
- `profit_before_tax.2024-03-31.consolidated` [UNVERIFIED]
- `interest_expense.2025-03-31.consolidated` [UNVERIFIED]
- `interest_expense.2024-03-31.consolidated` [UNVERIFIED]
- `borrowings_non_current.2025-03-31.consolidated` [UNVERIFIED]
- `borrowings_non_current.2024-03-31.consolidated` [UNVERIFIED]
- `borrowings_current.2025-03-31.consolidated` [UNVERIFIED]
- `borrowings_current.2024-03-31.consolidated` [UNVERIFIED]
- `current_maturities_long_term_borrowings.2025-03-31.consolidated` [UNVERIFIED]
- `current_maturities_long_term_borrowings.2024-03-31.consolidated` [UNVERIFIED]
- `ebit.2025-03-31.consolidated` — missing input [UNVERIFIED]
- `ebit.2024-03-31.consolidated` — missing input [UNVERIFIED]
- `total_borrowings.2025-03-31.consolidated` — missing input [UNVERIFIED]
- `total_borrowings.2024-03-31.consolidated` — missing input [UNVERIFIED]

## 8. Questions for the credit analyst

1. Revenue for the period ending 2025-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
2. Revenue for the period ending 2024-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
3. Net profit for the period ending 2025-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
4. Net profit for the period ending 2024-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
5. Profit before tax for the period ending 2025-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
6. Profit before tax for the period ending 2024-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
7. Interest expense for the period ending 2025-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
8. Interest expense for the period ending 2024-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
9. Non-current borrowings for the period ending 2025-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
10. Non-current borrowings for the period ending 2024-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
11. Current borrowings for the period ending 2025-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
12. Current borrowings for the period ending 2024-03-31 was not found on page 1 — confirm the figure from the audited statements. [UNVERIFIED]
13. RI-001 Declining revenue could not be evaluated because of missing inputs (`MET-01.2025-03-31 (missing_input)`). Can they be provided? [RULE: RI-001]
14. RI-002 Negative net profit could not be evaluated because of missing inputs (`net_profit.2025-03-31 (not_found)`). Can they be provided? [RULE: RI-002]
15. RI-004 Increasing leverage could not be evaluated because of missing inputs (`MET-04.2025-03-31 (missing_input)`, `MET-04.2024-03-31 (missing_input)`). Can they be provided? [RULE: RI-004]
16. RI-005 Weak interest coverage could not be evaluated because of missing inputs (`MET-05.2025-03-31 (missing_input)`). Can they be provided? [RULE: RI-005]

## 9. Limitations and human-review requirements

**This memo is a draft. A qualified human must review it, verify every figure against the cited source pages, and make any credit decision. It is not a credit decision, a rating or a score.**

**Scope**

- Only text-based PDF files are read. There is no OCR, so a scanned page cannot be read.
- One document is reviewed per run. Documents are not compared with each other.
- Two consecutive annual periods are read: the current period and the comparative period. 52/53-week reporting years, quarterly and interim periods are out of scope.
- No currency conversion is done. If the figures a ratio needs are in different currencies, the ratio is not defined.
- Figures are read from one statement basis, consolidated unless the analyst chose another. The basis is never switched automatically, and pages whose basis could not be determined are not sent for extraction.
- Lease liabilities are excluded from borrowings, so a borrower with large leases shows a lower debt-to-equity ratio than a definition that includes them (D-07).
- A dash or the word nil in place of a figure is read as a zero reported by the document, and its original text is kept. A dash is never read as a sign (FR-004.3).

**Ratios**

- Revenue growth does not separate acquisitions, disposals, currency effects or changes in accounting policy. A single-year change may be noisy.
- Net profit margin is distorted by one-off items, discontinued operations and minority interests, and is not comparable across industries.
- The current ratio is a point-in-time measure that is sensitive to working-capital timing and to window dressing. It ignores the liquidity quality of inventory and receivables.
- Debt-to-equity uses interest-bearing borrowings excluding lease liabilities. Where no total of borrowings is reported, it is the sum of non-current and current borrowings, which may exclude current maturities shown under another caption.
- Finance costs may include lease interest, unwinding of discounts and foreign-exchange differences, so interest expense may not equal cash interest. EBIT derived from profit before tax inherits any one-off items.

**Risk indicators**

- Indicators are prompts for human investigation. Severity says how urgently to look, not how creditworthy the borrower is.
- The thresholds are illustrative placeholders chosen for demonstration and testing. They are not universal banking standards, regulatory requirements or the policy of any institution. Real thresholds vary by institution, industry, borrower size and product, and must be set by the institution's credit policy. [CALCULATED: provisional_notice]

**Extraction and automation**

- An AI model proposes the figures. Each is accepted only if its quote is found on the cited page and passes the checks for value, label, period column, sign, scale and currency. The model can miss an item or misread a page, so a field reported as not found is not proof that it is absent from the document.
- Non-current borrowings, current borrowings, current maturities of long-term borrowings and operating profit have often not been found when the system was tried on real annual reports. Without a reported total of borrowings or its components, debt-to-equity is not defined, and without operating profit EBIT comes from profit before tax plus interest expense.
- All arithmetic, the risk rules and the text of this memo are produced by fixed programs, not by the model. This memo contains no AI-generated commentary.
- Values supplied by the analyst in a profile are shown as given. They are not checked against the document and are not used in any calculation or rule.
