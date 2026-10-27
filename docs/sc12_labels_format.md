# SC-12 labels file: format for the tuning documents

The SC-12 counting report (`python -m credit_intel.evaluation.recall`) compares the locator's candidate pages with a list of ground-truth statement pages that **you** write for each tuning document. The real files stay in `private/eval/` and are never committed. This note is the format only; it holds no real page list.

```json
{
  "document_id": "R1",
  "sha256": "<64 lowercase hex characters, the document's SHA-256>",
  "statement_pages": {
    "income_statement": [2, 3],
    "balance_sheet": [4, 5]
  }
}
```

Rules (checked by `--check-labels`, which prints only the document id and a page count):

- Exactly these keys, in this order. `statement_pages` holds `income_statement` then `balance_sheet`.
- Each list is non-empty, ascending, whole numbers of 1 or more, no repeats. **Continuation pages are listed too** (PRD SC-12). A page that carries both statements is listed in both.
- Page numbers are physical page numbers (1 = first page of the PDF), as everywhere else in the project.
- `document_id` and `sha256` must match the document's line in `tests/eval/assignments.jsonl`. A mismatch is refused. A held-out document is refused before any page is read (PRD O.2).

Run on tuning documents only, offline (no model, no key):

```
uv run --locked python -m credit_intel.evaluation.recall --check-labels private/eval/R1_sc12_labels.json
uv run --locked python -m credit_intel.evaluation.recall --report private/scans_or_reports/R1.pdf private/eval/R1_sc12_labels.json
```

The report prints counts and page numbers only: per document the labelled pages, candidate pages, found, **missed page numbers**, qualifying pages before the cap, `cap_limited`, and `passed`; then "N of M documents passed". A document passes only if no labelled page is missed **and** it is not cap-limited (PRD v0.4.49). It uses the locator's initial settings (OD-3 option (a)) and changes none.
