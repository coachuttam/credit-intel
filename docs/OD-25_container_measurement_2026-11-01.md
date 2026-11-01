# OD-25 repeated inside the container (FR-018 criterion 12) — the owner's measurement, recorded

| Item | Value |
|---|---|
| Status | **Recorded 2026-11-01 from the owner's report. I did not run it, and I have not seen the manifest or the script's output; the figures below are the owner's, as reported.** |
| What it answers | Criterion 12: do the OD-25 limits (`max_concurrent_runs` 1, `max_queued_runs` 4, `run_timeout_seconds` 1,200; `parse_memory_mb` 6,144) hold when the service runs inside the container under its real memory limit? |
| Image | The product image built after commit `5f719fb`, started with `deploy/measure_container.sh`'s compose file. |
| Container memory limit | **9 GB** (`CREDIT_INTEL_CONTAINER_MEMORY=9g`, 9,216 MB). The sizing rule of `api/sizing.py` asks for 8,180 MB with the shipped values, so the start-up check was met. |
| Document | Tuning document **R1**, **369 pages**, a public annual report kept in `private/` (not opened by me). **Not the document of the original OD-25 measurement:** that was a 146-page report that no longer exists on the owner's machine. R1 has more than twice the pages, so the comparison is conservative on page count. Page count is only part of the cost (OD-25 section 1: reading time follows how the report is designed, 0.30 to 0.57 s a page), so it is not proof of a worse case on every document. |
| Model | The real model (`gpt-4o-mini`), one live run through the container. Spend: one more call of the order of the earlier one (about USD 0.001); the earlier estimate was about USD 0.037 of the USD 0.15 cap, and I have not recomputed it. |

## Result (the owner's figures)

| Measure | Value |
|---|---|
| Final state | `exported`; all stages completed; 12 fields extracted; `memo.md` and `report.pdf` written |
| Seconds, first submission to last end | **113** (limit `run_timeout_seconds` 1,200) |
| Container peak memory | **2,601 MB** (worker limit `parse_memory_mb` 6,144; container 9,216) |
| Kernel memory events | `oom` 0, `oom_kill` 0, `oom_group_kill` 0 |

## What it shows and what it does not

- **Shows:** one 369-page document is parsed, extracted, and exported inside the 9 GB container with about 2.6 GB at peak and 113 s, far inside the limits. On this evidence there is no reason to lower `api.max_concurrent_runs` or raise `api.run_timeout_seconds`, so by criterion 12 the shipped settings stay.
- **Does not show:** more than one document. The shipped pool runs one run at a time (queue of 4), so peak memory of one run is what the pool can produce for parsing; but **the full queue (five submissions at once, four waiting) was not reported**, and neither was the `429` path or a document with the slowest page design. A scanned document with `--ocr` through the container was not measured.
- It also shows the first real parse through the product image only after the `.pth` fix (`5f719fb`): before it, no document could be parsed in the container (finding F-13 of the review).
- The number of submissions in the script's run was not stated in the report; I have treated it as one.

## Proposal for the PRD (not applied; needs your word and a version bump)

FR-018 criterion 12 status: "measured by the owner on 2026-11-01 inside a 9 GB container with one 369-page public document: 113 s, 2,601 MB peak, no kernel memory event; the shipped values stand; the queue-full and OCR cases were not measured". The PRD text of the criterion needs no change.
