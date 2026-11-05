# OD-25: what a whole run costs in time and memory (measurements for the API limits)

| Item | Value |
|---|---|
| Status | **Measurements complete (sections 1 to 5). The values of section 7 were approved by the owner on 2026-10-30 as proposed: `max_concurrent_runs` 1, `max_queued_runs` 4, `run_timeout_seconds` 1,200.** They are set in no file yet; the Phase 6 PRD draft will carry them. |
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

## 4a. Measured: several runs at once on this machine (added 2026-10-30)

The 159-page report, the model's reply faked, the PDF report skipped, N whole runs started together in one process (as the API's thread pool would run them), the memory of the whole process tree sampled twice a second.

| Runs at once | Wall time for all | Each run | Throughput against one after another | Peak memory of the tree |
|---|---|---|---|---|
| 1 | 96.3 s | 96.3 s | 1.0x | 1,458 MB |
| 2 | 116.2 s | 116.2 s (1.21x slower) | 1.66x (2 runs in 116 s, 193 s one after another) | 2,386 MB |
| 3 | 154.6 s | 148 to 155 s (1.6x slower) | 1.87x (3 runs in 155 s, 289 s one after another) | 2,576 MB |

All runs exited 0. The peaks do not add up (three workers did not peak together), so the measured peak is below N times one run.

**A caution about these figures.** This machine was already short of memory: the swap file held 6.6 GB of its 8 GB **before** the first measurement and grew to 8.8 GB and then 10 GB during the second and third. The times above therefore include paging caused partly by other things running on the machine, and they are conservative; a dedicated host would do better. The memory peaks are the processes' own and are not affected.

**The worst case is set by the limits, not by these peaks.** The reading step may use up to 6144 MB each (the owner's limit, chosen so that a 600-page report is not rejected):

| `max_concurrent_runs` | Worst case from the limits (plus the server, about 0.3 to 0.5 GB) | Against 8 GB |
|---|---|---|
| 1 | about 6.5 GB | fits, with about 1.5 GB for everything else |
| 2 | about 12.5 GB | cannot fit: a document that reaches the limit while another run is busy exhausts memory before either limit stops it |
| 3 | about 18.5 GB | cannot fit |

**What this says, before the model timings:**
- On an 8 GB host, **1 is the only value for which the configured memory limit is itself the guarantee**; the owner's lean of 1 is consistent with the numbers.
- 2 would work for ordinary documents (a measured peak of 2.4 GB) and would raise throughput by about 1.7 times, but it leaves a hostile or very large document able to take the host past its memory, which the per-run limit alone no longer prevents. It would need a lower `parse_memory_mb` (about 3 GB for each of two runs), which would stop the legitimate 600-page report the limit was raised for.
- So the choice is between safety on this host (1) and throughput (2 with a lower limit, or a larger host later, which is a Phase 7 question).

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
cd <repo>
set -a; source .env; set +a
export CREDIT_INTEL_TOKEN_CEILING=30000
PDF=<scratch>/dl/RIL-Integrated-Annual-Report-2024-25.pdf
for i in 1 2 3; do
  d=$(mktemp -d)
  ( cd "$d" && uv run --project <repo> credit-intel "$PDF" \
      --confirm-public-document --output-dir "$d/runs" \
      --config <repo>/config/settings.toml )
  echo "run $i folder: $d/runs"
done
```

## 6. What I would propose after that (not yet)

With the three model timings, the plan's OD-25 table would get numbers for: `max_concurrent_runs` (from the host's memory and the measured peaks), `max_queued_runs`, and `run_timeout_seconds` (from the typical and worst-case times above, so that it stops a stuck run without stopping an honest slow one). None is set here.

## 7. The live measurement, and the values I propose (added 2026-10-30)

**Live runs** (the owner ran them in their terminal; the real model, `gpt-4o-mini`, prompt `extraction-v5`; three runs of the 146-page public report, each from an empty directory, so no cache hit; the timings are from the three manifests):

| Run | Whole run | Reading the text | Locating | **The model call** | Verification | Export with report | Tokens in / out | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 60.5 s | 44.5 s | 1.1 s | **11.6 s** | 1.1 s | 1.1 s | 4,276 / 1,234 | USD 0.00138 |
| 2 | 58.9 s | 43.8 s | 1.1 s | **10.8 s** | 1.1 s | 1.1 s | 4,276 / 1,234 | USD 0.00138 |
| 3 | 58.8 s | 43.8 s | 1.1 s | **10.7 s** | 1.1 s | 1.1 s | 4,276 / 1,234 | USD 0.00138 |

- One model call, no retry, no corrective call, no cache hit in any run. Three runs cost USD 0.0041 in all (my estimate was at most USD 0.007 for the three); the spend is now about USD 0.0353 of the USD 0.15 cap.
- The three whole runs are within 1.7 s of each other. The model call is 10.7 to 11.6 s for about 1,230 output tokens, roughly 100 output tokens a second. A second data point, from the owner's earlier run on the 369-page tuning report (the timing line only): reading 46.9 s, the call about 13 s for 4,797 tokens, 62 s in all.
- **A real run is therefore about one minute for a 150 to 370 page report, 44 to 47 s of it reading the text and 11 to 13 s the model.** For the heavier 159-page report, reading takes 90 s, so about 106 s.
- Everything is I/O or one core: the model wait is idle time, the reading is one core.

**What the numbers say about each limit.**

| Limit | Proposed | Reasoning |
|---|---|---|
| `max_concurrent_runs` | **1** | The owner's lean, and the measurements agree. On this 8 GB host one run at its memory limit is about 6.5 GB and fits; two are 12.5 GB and cannot (section 4a). Two runs would give 1.66 times the throughput at a measured 2.4 GB, but the memory limit would no longer be a guarantee. At 1, a run takes about one to two minutes, so the service can finish about 30 to 60 runs an hour. |
| `max_queued_runs` | **4** (runs waiting, not counting the one running) | The longest wait is then about four runs ahead: at the typical 1 to 2 minutes each, 4 to 8 minutes; I would not make the page wait longer than that. Beyond it the API answers "busy" with a retry hint instead of holding the upload. Alternatives: 2 (at most about 4 minutes of wait) or 8 (about 16 minutes). A queue of heavy 600-page reports would wait longer (each could take 6 minutes or more), which is why the count is small. |
| `run_timeout_seconds` | **1,200** (20 minutes) | It must not stop an honest run and it must free the single slot if a run is stuck. The honest worst case from the measurements and limits: reading a 600-page design-heavy report at the measured 0.57 s a page (about 340 s) or, with `--ocr`, the estimated 650 s; plus a model call of up to about 45 s at the maximum output (and a second call after a corrective retry, another 45 s); plus about 5 s for the rest and the report: roughly **745 s** at the very most. 1,200 s is 60 % above that. A tighter 900 s would clear the honest worst case by only 21 %, the kind of thin margin the owner rejected for the parse limits; 1,800 s (the sum of the component limits) would mean a stuck run holds the only slot for half an hour. Every part already has its own limit (700 s of parsing, 120 s a model attempt, 120 s for the report); this is a backstop for anything between them. |

Notes for the PRD draft that follow from this:
- With `max_concurrent_runs = 1` a whole-run timeout is the only thing that frees the slot of a stuck run, so it is not optional.
- A run stopped by `run_timeout_seconds` needs a catalogued code (it would be the 22nd) and a failure record, like any other failure.
- The limits are proposals for the owner to set; none is set in any file.
