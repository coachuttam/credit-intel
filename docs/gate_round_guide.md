# Gate round guide — writing the reference values and reading the result

The gate is your condition of 2026-10-24: **no held-out run until profit before tax, interest expense and borrowings all extract on both tuning reports, and each matches a value you checked by hand.** This guide says what to write, where to keep it, and how the comparison reports. Nothing in it needs the assistant to open a real document.

## 1. What the gate compares

For each tuning report (R1 and R2), six values on the **consolidated** statements (or the basis you choose for that report):

| Field | Current period | Comparative period |
|---|---|---|
| Profit before tax | yes | yes |
| Interest expense (finance costs) | yes | yes |
| Total borrowings | yes | yes |

"Total borrowings" is what the debt-to-equity ratio uses: the **reported total** if the balance sheet prints one, otherwise the sum of the parts the specification adds (H.5, D-12): non-current borrowings plus current borrowings, plus current maturities of long-term borrowings **only** if they are a separate row that is not already inside current borrowings. Lease liabilities are not included. For a report with no total line, list the parts (section 3) and the gate expects their sum. *This is decision (b) below; it is the reading I built.*

The comparison is **counts only**: per value `match`, `mismatch` or `missing`. An extracted value that differs from your reference **fails** the gate. A value that is not extracted (not found, or held back for review) is `missing` and also fails it. A value read from the right place but another page is still a match, and the page is flagged for you to look at.

## 2. Where the files go

Keep one file per report in **`private/eval/`**, for example `private/eval/R1_reference.json` and `private/eval/R2_reference.json`. `private/` is ignored by git. **Never commit these files**: they hold figures from real reports.

## 3. The file format

Write the figures **exactly as printed on the page**, with the scale the page declares, and give the **physical PDF page number** (the number your viewer shows, not the number printed in the page footer).

```json
{
  "document_id": "R9",
  "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "basis": "consolidated",
  "entries": [
    {"field": "profit_before_tax", "period": "current", "period_end": "2025-03-31", "page": 3, "printed": "352.70", "scale": "crore"},
    {"field": "profit_before_tax", "period": "comparative", "period_end": "2024-03-31", "page": 3, "printed": "300.10", "scale": "crore"},
    {"field": "interest_expense", "period": "current", "period_end": "2025-03-31", "page": 3, "printed": "38.50", "scale": "crore"},
    {"field": "interest_expense", "period": "comparative", "period_end": "2024-03-31", "page": 3, "printed": "(35.00)", "scale": "crore"},
    {"field": "total_borrowings", "period": "current", "period_end": "2025-03-31", "page": 4, "printed": "550.00", "scale": "crore"},
    {"field": "total_borrowings", "period": "comparative", "period_end": "2024-03-31",
     "parts": [{"printed": "350.00", "scale": "crore", "page": 4}, {"printed": "120.00", "scale": "crore", "page": 4}]}
  ]
}
```

(The numbers above are invented. The example parses with the real checker, and a test keeps it that way.)

Rules:

- The keys are exactly `document_id`, `sha256`, `basis`, `entries`, in that order. `document_id` is the neutral ID in `tests/eval/assignments.jsonl` (`R1` or `R2`) and `sha256` is that record's hash for the report. The gate refuses a reference whose hash is not the document's.
- All six entries are required, once each. `field` is `profit_before_tax`, `interest_expense` or `total_borrowings`; `period` is `current` or `comparative`; `period_end` is the ISO date of that column.
- `printed` is the figure as it appears: thousands separators are fine, brackets mean negative, and a dash or `nil` means a reported zero. `scale` is one of `units`, `thousands`, `lakh`, `millions`, `crore`, `billions`.
- `parts` (for `total_borrowings` only) replaces `printed`, `scale` and `page`, and lists at least two components, each with its own `printed`, `scale` and `page`.
- There is no free-text field. Put no quote, label or note in the file.

## 4. Check a file before using it

```
uv run --locked python -m credit_intel.evaluation.gate --check-reference private/eval/R1_reference.json
```

This reads only the reference file, no PDF and no model. It prints `reference_ok`, the document ID and the number of entries, or the name of the problem (never a figure).

## 5. Run the comparison

The comparison **replays the model's reply from the response cache**, so it sends nothing and costs nothing. It needs a cached run of the same pages, prompt, model and output limit, which a live round produces (separately approved, run by you in your own terminal; I write the exact command when we reach that step).

```
uv run --locked python -m credit_intel.evaluation.gate \
  --report private/R1_infosys_2024_25.pdf private/eval/R1_reference.json \
  --report private/R2_microsoft_2025.pdf private/eval/R2_reference.json
```

It prints one counts-only line per report and then `GATE: PASS` or `GATE: FAIL` (exit 0 or 1; exit 2 if a reference or a refusal stops it). The gate passes only if **every tuning document on the assignment record** was replayed and matched on all six values. A held-out document is refused. A cache miss counts as a failure to replay, not as a pass.

## 6. Two points that are yours to settle

**(a) R2.** R2's statement titles name no basis, so it stops at the basis gate (`E-EXTRACT-BASIS-UNAVAILABLE`) and extracts nothing. The routes, from `docs/OD-10_options_note.md`:

1. **Build option 3 (the page-scoped analyst assertion)**, which you accepted in principle on 2026-10-13: the analyst states the basis for named pages, and the run records it as analyst-provided and not as evidence. It needs a PRD amendment (v0.4.24) that I would draft first, then code and tests. This is my recommendation.
2. **Build option 2 (basis from a footnote)**, also accepted in principle: the page's own footnote establishes the basis. It also needs an amendment.
3. **Replace R2** with another public report that you assign to the tuning set before anyone inspects it.
4. **Gate on R1 only**: this changes your first condition, so it is yours to decide and record.

**(b) What "borrowings" means.** The gate compares the total the metrics use (a reported total, or the sum of non-current and current borrowings, plus a separate current-maturities row where the specification adds it). If you prefer the gate to compare each component too, the reference file would grow by two entries per period and the tool by a few lines.
