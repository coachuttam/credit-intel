# OD-25: what a whole run costs in time and memory (measurements for the API limits)

| Item | Value |
|---|---|
| Status | **Measurements, and a request to measure the one part that needs the live model.** No limit value is proposed yet: the owner's standard is measure first, as for SEC-12. |
| Drafted | 2026-10-30 |
| Machine | Mac14,2, 8 CPU cores, **8 GB of memory** (the only machine measured) |
| What was measured | Whole runs of the real pipeline on two public annual reports, with **the model's reply faked** (an empty one): real parsing, locating, verification, calculation, rules, memo, the PDF report and the export. The model call itself is the part not yet measured. |
| Documents | Two public integrated annual reports downloaded from the company's own site (146 and 159 pages; 11.8 and 15.5 MB), kept outside the repository, parsed for time only. Neither is on the assignment record. |

## 1. Measured: everything except the model (seconds, one machine)

| Stage | 146 pages (11.8 MB) | 159 pages (15.5 MB) |
|---|---|---|
| validate | 0.9 | 0.9 |
| **read the text of every page** | **43.4** | **90.2** |
| locate the statement pages | 1.1 | 1.2 |
| verify the fields | 1.1 | 1.3 |
| calculate, rules, memo | 0.1 | 0.1 |
| export, including the PDF report | 0.7 | 0.7 |
| **whole run** | **47.5** | **94.4** |

- Reading the text is **91 to 96 % of the run**, and it scales with how the report is designed, not with its page count (0.30 s a page against 0.57 s a page here). Everything else is about 3 to 4 seconds.
- The PDF report adds about 0.6 s (0.2 s without it).
- Candidate pages found: two in each document. Measured memory of the reading step on these and the other reports checked earlier: 0.5 to 1.5 GB (`docs/parse_limits_check_2026-10-27.md`).

## 2. A defect this found

The first run on these real documents had its report **fail** (`render_error`) in 0.2 s. The cause: when a run finds no period dates (my faked reply gave none), the metrics carry no period end and the chart builder raised `IndexError`. The run itself was unharmed (exit 0, three files, the manifest said `report: failed, render_error`, one warning), which is the never-fails path working as specified, but the report should not fail there. Fixed (a slot's caption is the role alone when there is no period end), with two tests and a mutation check; the re-run wrote the report on both documents.

## 3. What bounds a run from above (from the code and the settings, not measured)

| Part | Upper bound |
|---|---|
| Reading the text and other parsing | `ingestion.parse_timeout_seconds` = **700 s** (one budget for the run) |
| Each model call | 120 s per attempt, up to 3 attempts with 1 s and 2 s of backoff, and a second call after one corrective retry: **about 726 s** in the worst case |
| OCR reading (only with `--ocr`) | `ocr.timeout_seconds` = 120 s for the call |
| The PDF report | 120 s (a constant) |
| The optional page classifier | 60 s budget when switched on |

Added up, the worst case is roughly **1,700 s (28 minutes)** for a run in which every limit is reached; a normal run is a minute or two plus the model. There is no limit on the whole run today, which is what `run_timeout_seconds` would add.

## 4. Memory under concurrency (what the machine says)

The reading step's memory limit is 6144 MB per run, and the measured peaks are 0.5 to 1.5 GB. **This machine has 8 GB**, so even one run at its limit would nearly fill it, and two runs at the limit (12 GB) cannot fit. Two runs at the measured peaks (about 3 GB) fit. So the right `max_concurrent_runs` depends on the host that will run the service, which is not yet decided (Phase 7 covers deployment). **I need the target host's memory** to propose a value.

## 5. The part still to measure: the model call

A real run's time is the 47 to 94 s above plus the model call (and the corrective retry, if one is needed). Nothing here has timed a real call on a full document. A live run sends the candidate statement pages to the hosted API, so it needs the owner's approval; the owner runs it in their own terminal. The proposal:

| Item | Proposal |
|---|---|
| Document | The 146-page report above (SHA-256 starts `bb541a68`), public, from the company's own site |
| What is sent | Candidate pages **99 and 100** (6,402 characters), about **6,782 input tokens** by the dry run; prompt `extraction-v5`, model `gpt-4o-mini` as configured |
| Ceiling | `CREDIT_INTEL_TOKEN_CEILING=30000` (the dry run's suggestion; the reservation is 10,878 per call) |
| Runs | **Three**, each from an empty directory so that the response cache cannot answer the second and third (the cache is relative to the current directory) |
| Cost | At gpt-4o-mini list prices as I recall them (USD 0.15 and 0.60 per million input and output tokens; **not verified**, please check): about USD 0.0035 for one call at the maximum output, USD 0.007 with a corrective retry; three runs at most about USD 0.02. Spend so far USD 0.0312 of the USD 0.15 cap. |
| Document status | Not on the assignment record, so `--confirm-public-document` is needed (the notice about sending is printed) |
| What I would read back | Only each run's `manifest.json`: the stage timestamps, the tokens, the cost, whether the cache was hit. No document text is in it. |

Commands for the owner's terminal (each run in a fresh directory):

```
cd /Users/uttam/projects/ai-credit-intelligence
set -a; source .env; set +a
export CREDIT_INTEL_TOKEN_CEILING=30000
PDF=/private/tmp/claude-501/-Users-uttam-projects-ai-credit-intelligence/27d85da9-4434-4bc0-984a-fdaef87413c0/scratchpad/dl/RIL-Integrated-Annual-Report-2024-25.pdf
for i in 1 2 3; do
  d=$(mktemp -d)
  ( cd "$d" && uv run --project /Users/uttam/projects/ai-credit-intelligence credit-intel "$PDF" \
      --confirm-public-document --output-dir "$d/runs" \
      --config /Users/uttam/projects/ai-credit-intelligence/config/settings.toml )
  echo "run $i folder: $d/runs"
done
```

## 6. What I would propose after that (not yet)

With the three model timings, the plan's OD-25 table would get numbers for: `max_concurrent_runs` (from the host's memory and the measured peaks), `max_queued_runs`, and `run_timeout_seconds` (from the typical and worst-case times above, so that it stops a stuck run without stopping an honest slow one). None is set here.
