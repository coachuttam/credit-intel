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
| `revenue.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `revenue.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `net_profit.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `net_profit.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `operating_profit.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `operating_profit.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `profit_before_tax.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `profit_before_tax.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `interest_expense.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `interest_expense.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | statement not in pages sent |
| `current_assets.2025-03-31.consolidated` | 1,482.30 (INR crore) | extracted | [SOURCE: p.1] | — |
| `current_assets.2024-03-31.consolidated` | 1,356.75 (INR crore) | extracted | [SOURCE: p.1] | — |
| `current_liabilities.2025-03-31.consolidated` | 900.00 (INR crore) | extracted | [SOURCE: p.1] | — |
| `current_liabilities.2024-03-31.consolidated` | 850.00 (INR crore) | extracted | [SOURCE: p.1] | — |
| `borrowings_non_current.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | no recognised row |
| `borrowings_non_current.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | no recognised row |
| `borrowings_current.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | no recognised row |
| `borrowings_current.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | no recognised row |
| `current_maturities_long_term_borrowings.2025-03-31.consolidated` | — | not found | [UNVERIFIED] | no recognised row |
| `current_maturities_long_term_borrowings.2024-03-31.consolidated` | — | not found | [UNVERIFIED] | no recognised row |
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
