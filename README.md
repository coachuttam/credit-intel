# AI Credit Intelligence Platform

A command-line tool that reads the financial statements in a text-based annual-report PDF and writes a **draft credit memo for a human analyst to review**. It is not a credit decision, and it does not rate, score, approve or reject anyone.

An AI model proposes the figures. Everything after that is checked or calculated by fixed, tested programs: each figure must be found, word for word, on the page it cites, in the right row and period column, with the right sign, scale and currency. Ratios and risk indicators are computed in plain Python with exact decimals. The memo is produced by a template, not written by a model.

## Status

The code for Release 1 is in place and tested **offline**; the owner has not yet approved the release. It has **not been evaluated against the held-out set** (PRD section O.2), so **no accuracy, coverage or cost figure for real reports has been measured, and none is claimed here**. The held-out evaluation, the owner's labels and the release approval are the remaining gated steps; see `PROGRESS.md`.

## Quick start

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
```

Settings live in `config/settings.toml`. The **token ceiling has no default** (PRD NFR-09, OD-8): set it in the file or with `CREDIT_INTEL_TOKEN_CEILING`, or every run stops with `E-CONFIG-INVALID`. A minimal `[llm]` table:

```toml
[llm]
provider = "openai"
model_id = "gpt-4o-mini"
token_ceiling = 100000
max_output_tokens = 4096
```

The API key is read from the environment variable `OPENAI_API_KEY` only. It is never read from a file, logged or stored. Other settings can be overridden with `CREDIT_INTEL_LLM_PROVIDER`, `CREDIT_INTEL_LLM_MODEL_ID`, `CREDIT_INTEL_MAX_OUTPUT_TOKENS`, `CREDIT_INTEL_PRICE_INPUT_PER_MILLION` and `CREDIT_INTEL_PRICE_OUTPUT_PER_MILLION`.

Run it on a document:

```
uv run credit-intel report.pdf --confirm-public-document
```

`python -m credit_intel` is the same command.

## What it sends, and what it must not

The candidate statement pages of the PDF are sent to the hosted model API. **Only public or synthetic documents may be sent** (PRD SEC-10). Real borrower, customer or confidential documents must never be used with the hosted provider.

The command line enforces this as follows when the provider sends data off the machine:

- a document recorded as **held out** in `tests/eval/assignments.jsonl` is never sent, whatever the options;
- a document recorded as **tuning** is sent;
- any other document is sent only if you pass `--confirm-public-document`, which says that you have checked that it is public;
- if the record file exists but cannot be read, every document is refused;
- a document in the project's `private/` folder is refused (`private_path`) unless it is recorded as tuning **and** you approved that run with `CREDIT_INTEL_PRIVATE_APPROVED=1` in its environment;
- the same rule covers the optional page classifier below, when it sends pages.

A refusal is a catalogued failure: `E-INPUT-SEND-REFUSED`, exit code 3, before any provider is built or any file is written. It names the reason (`held_out`, `not_recorded`, `record_unreadable` or `private_path`) and never the document's hash, path or ID.

A notice is printed whenever pages may be sent. Run folders (`runs/`), the response cache (`.cache/`) and `private/` are ignored by git.

## Optional page classification (Jev)

Off by default. With `USE_JEV=true` in the environment, a hosted classifier (Jev, TypeSafe AI) labels each candidate page (balance sheet, profit and loss, cash flow, notes, other, and consolidated, standalone or unclear) before the extraction model runs, and pages it is confident are not needed are not sent. It can only remove pages: the extraction model still reads every value and every value is still verified against its page. Any doubt, error or timeout sends the page exactly as without it, and a failure of the classifier never fails a run. Pages you name with `--pages` are never filtered, and notes pages are never removed.

- The key is read from `TYPESAFE_API_KEY` (or `JEV_API_KEY`) in the environment, never from a file. `USE_JEV` is read from the environment too; the settings are in the `[jev]` and `[steps]` tables of `config/settings.toml`.
- It sends page text to a second hosted service, so the send rule above applies to it. TypeSafe's data-retention terms are not stated in its public documentation; read them before using it on anything.
- With it on, `results.json` gains `extraction.page_filter` and `manifest.json` gains `page_filter` (per-page labels, confidence, fallback, latency, cost). With it off neither file mentions it.
- To see what it would cost and whether it helps on a tuning report: `uv run python -m credit_intel.evaluation.jev_eval <pdf> [--pages R]` prints an estimate and calls nothing; its live option, which needs a maximum spend that covers the worst case, runs both ways and prints counts only.

## Command line

```
credit-intel <pdf_path> [--pages RANGE] [--basis consolidated|standalone] [--assert-basis consolidated|standalone]
             [--profile PROFILE_JSON] [--output-dir DIR] [--config SETTINGS_TOML] [--ocr] [--confirm-public-document]
```

| Option | Meaning |
|---|---|
| `--pages RANGE` | Statement pages such as `110-115,120`. Replaces the automatic page locator. |
| `--basis` | Statement basis, `consolidated` (default) or `standalone`. The basis is never switched automatically. |
| `--assert-basis` | Requires `--pages`. States the basis (`consolidated` or `standalone`) of the pages of that range whose titles name none, for a document that never names it. It never overrides a page whose title names a basis: a page naming the other basis stops the run with `E-EXTRACT-BASIS-UNAVAILABLE`. The assertion is disclosed in the results and the memo and is not evidence. *(PRD v0.4.24; being implemented in steps: it is checked, counted by the basis gate, fields on asserted pages are accepted and marked `analyst_assertion`, and it is recorded in `results.json` and `manifest.json` and disclosed in the memo.)* |
| `--profile PROFILE_JSON` | An optional JSON object with the keys `borrower_name`, `industry`, `facility_requested` and `notes`, each a string of at most 500 characters. The values appear in the memo labelled `[ANALYST-PROVIDED]` and are never used as evidence, in calculations or in rules. |
| `--output-dir DIR` | Where run folders are written. Default `runs`. |
| `--config SETTINGS_TOML` | The settings file. Default `config/settings.toml`. |
| `--ocr` | Turns on OCR of scanned pages (specified in PRD v0.4.44, built in steps). **Not built yet:** the `[ocr]` settings are checked and the run reads the text layer only. |
| `--confirm-public-document` | Confirms that a document that is not on the assignment record is public, so its pages may be sent. |

On success the command prints the run folder path and exits 0. On a failure it prints one line with an error code (`E-...`), the reason and what to do, and exits with the code in this table. A run that failed after its input was read also leaves a folder with only `manifest.json`, which records the failed state and the error code.

| Exit code | Meaning |
|---|---|
| 0 | Success. |
| 1 | An unexpected error. The message gives the run ID and no stack trace. |
| 2 | A bad argument. |
| 3 | The input is not acceptable: missing or unreadable file, not a PDF, too large, encrypted, bad page range, bad profile, or the document may not be sent (`E-INPUT-SEND-REFUSED`, with one reason word: `held_out`, `not_recorded`, `record_unreadable` or `private_path`). |
| 4 | The statements could not be located or the requested basis is not in the document. |
| 5 | The model step failed: authentication, an unavailable provider, invalid output, or the token ceiling. |
| 6 | The settings or rules file is invalid. |
| 7 | The output could not be written, or the run folder already exists. |
| 130 | Interrupted. |

## What a run produces

Each run writes `<output_dir>/<run_id>/`, where the run ID is the UTC start time to the microsecond and the first 8 hex characters of the document's SHA-256. An existing run folder is never overwritten, and a failed write leaves no folder that looks complete.

- `memo.md`: the draft memo, in nine sections: borrower overview, documents reviewed, financial performance, financial ratios, potential risk indicators, evidence and source references, missing information and conflicts, questions for the credit analyst, and limitations. Every statement carries an origin label: `[SOURCE: p.N]`, `[CALCULATED: ...]`, `[RULE: RI-xxx]`, `[ANALYST-PROVIDED]` or `[UNVERIFIED]`. Before anything is written, the memo is checked against the run's own results (every label, ID and value); a memo that fails the check is an internal error (exit 1) that reports only the number of problems, and the run leaves a manifest-only record, no memo.
- `results.json`: every field with its page, quote and status, the derived values, the five ratios, the seven risk indicators and the profile. It holds no timestamp or run ID, so the same input, configuration, code and cached model replies give a byte-identical file (and an identical memo apart from the run ID and the times in its header).
- `manifest.json`: the run ID, timestamps, every processing state, input hash and page counts, code version, package versions, model and prompt versions, rules-file hash, cache hits, tokens and estimated cost, the final state and any error code.

## How it works

1. **Ingest:** the PDF is validated and its text is read page by page.
2. **Locate:** a deterministic locator finds the candidate income-statement and balance-sheet pages, and the basis (consolidated or standalone) of each.
3. **Extract:** the model proposes values for a fixed list of line items, each with a verbatim quote and a page number. Replies are cached. The temperature is 0.
4. **Verify:** each proposed value is checked against the page: quote found, value in the quote, row label, period column, sign, scale and currency. A value that fails is marked `requires_review`, never accepted. A value the model does not find is `not_found`, never assumed to be zero.
5. **Calculate:** EBIT and total borrowings are derived where the statements allow, then five ratios (revenue growth, net profit margin, current ratio, debt-to-equity, interest coverage) with exact decimals and a stated reason when one cannot be defined.
6. **Evaluate:** seven risk indicators are evaluated from rules and thresholds in `config/risk_rules.toml`. Each condition is evaluated on its own, and a missing input makes only the conditions that need it not evaluable.
7. **Write:** the memo, the results and the manifest are written.

## Scope and limitations

These are the limits of Release 1. The memo's last section states them too, and a test keeps this list and that section the same.

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

**Extraction and automation**

- An AI model proposes the figures. Each is accepted only if its quote is found on the cited page and passes the checks for value, label, period column, sign, scale and currency. The model can miss an item or misread a page, so a field reported as not found is not proof that it is absent from the document.
- All arithmetic, the risk rules and the text of this memo are produced by fixed programs, not by the model. This memo contains no AI-generated commentary.
- Values supplied by the analyst in a profile are shown as given. They are not checked against the document and are not used in any calculation or rule.

Other limits: the PDF may be at most 100 MB and 600 pages; at most 15 candidate pages are sent in one run; the line-item phrases are English; a page range (`--pages`) may be needed when the locator cannot place the statements. A field that is not found, conflicting or in need of review is listed in the memo and is never silently used in a calculation.

## Provisional thresholds

> The thresholds are illustrative placeholders chosen for demonstration and testing. They are not universal banking standards, regulatory requirements or the policy of any institution. Real thresholds vary by institution, industry, borrower size and product, and must be set by the institution's credit policy.

The thresholds are in `config/risk_rules.toml`. Changing one needs no code change. Severity (`info`, `watch`, `elevated`) says how urgently a human should look. It does not say how creditworthy the borrower is.

## The human-decision boundary

This memo is a draft. A qualified human must review it, verify every figure against the cited source pages, and make any credit decision. It is not a credit decision, a rating or a score. The system produces drafts only: no credit decision, filing or external action is taken automatically, and it never approves, rejects, rates, grades or scores a borrower.

## Tests

```
uv run pytest tests/ -q
```

The suite needs no network and no API key; a test that tries to open a network connection fails. Tests that call the real API are skipped unless `CREDIT_INTEL_LIVE=1` and an API key are set, because they cost money and must only use public documents. Test PDFs are generated at test time; no real document is in the repository.

## Repository map

- `src/credit_intel/` is the package: `ingestion/`, `extraction/`, `calculations/`, `risk/`, `memo/`, `export/`, `llm/`, `evaluation/`, plus `run.py` (one run), `cli.py` (the command) and `send_rule.py`.
- `config/` holds `settings.toml` and `risk_rules.toml`; `prompts/` holds the versioned extraction prompts.
- `tests/` holds the tests, `tests/BEHAVIOURS.md` lists the expected behaviours and their status, and `tests/fixtures/` holds recorded replies and golden files.
- `docs/PRD.md` is the product specification; `PROGRESS.md` records what has been done, every decision and what is next; `CLAUDE.md` holds the project rules.
