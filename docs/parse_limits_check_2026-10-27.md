# Parse limits checked against public reports (2026-10-27)

| Item | Value |
|---|---|
| What was checked | The limits you set on 2026-10-27, **300 s** (one budget for all parsing in a run) and **4096 MB** (the worker's resident memory), against four public annual reports, parsed through the worker (`SandboxedExtractor`). |
| Authorised | By you, 2026-10-27 ("run the parse-limits check (300s / 4096MB) against a few public reports"). |
| What was read | Nothing from any document. The check measures time and the worker's peak resident memory only. Each file's hash was compared with the assignment record first, and a held-out document would have been refused (none was). |
| Files | R1 and R2 (the two tuning reports, already under `private/`), and two public integrated annual reports downloaded from the company's own site into the scratchpad (not in the repository). |

## Results (this machine; one worker per operation; peak memory as the parent saw it)

| Report | Size, pages | Text of all pages | Word positions (15 pages) | Image coverage (only with `--ocr`) | Inspect + text + coverage in one 300 s budget |
|---|---|---|---|---|---|
| R1 (tuning) | 7.0 MB, 369 | 49.6 s / 1,099 MB | 3.9 s / 163 MB | 42.9 s / 1,293 MB | 87.2 s |
| R2 (tuning) | 1.5 MB, 80 | 11.8 s / 485 MB | 1.8 s / 132 MB | 11.2 s / 472 MB | 23.4 s |
| Public report A | 15.5 MB, 159 | 91.7 s / 1,466 MB | 26.5 s / 955 MB | 80.0 s / 1,499 MB | 171.1 s |
| Public report B | 11.8 MB, 146 | 67.1 s / 1,256 MB | 7.1 s / 237 MB | 46.0 s / 1,184 MB | 84.0 s |

No limit was hit in any run.

## What this shows

- **All four fit** inside 300 s and 4096 MB, but the margin depends on the design of the report, not its page count. The plain-layout 369-page report used 87 s; the design-heavy 159-page report used 171 s, which is **57 % of the budget** (and with OCR coverage on).
- **Seconds per page** (inspect + text + coverage): R1 0.24, R2 0.29, report A 1.08, report B 0.58. At report A's density a **600-page** report would need about 650 s and, on the text step alone, roughly 5 GB, so **300 s and 4096 MB would stop it** with `E-INPUT-PARSE-LIMIT`, which is the limit doing its job. At R1's density 600 pages needs about 140 s.
- A run without `--ocr` does not run the image-coverage step, so it uses about 30 to 50 % less time.
- The measurements are on one machine. Time and memory on another will differ.

## Options for you (no recommendation made)

| Option | Effect |
|---|---|
| Keep 300 s / 4096 MB | Safe for reports up to roughly 250 to 450 pages depending on design; a 600-page design-heavy report is stopped, and you raise the limits deliberately. |
| Raise to about 600 s / 6144 MB | Covers a 600-page design-heavy report at report A's density. A hostile file can then hold a worker for ten minutes and 6 GB before it is stopped. |
| Leave the values and revisit when a report is stopped | The stop is catalogued and names the setting, so the cost of being too low is one re-run. |

## Decision (owner, 2026-10-27, after this check)

The limits are raised to **700 s and 6144 MB** (`config/settings.toml`). The reason given: at report A's density a genuine 600-page report, within the approved 100 MB and 600-page ceiling, needs about 650 s and about 5 GB, so 300 s and 4096 MB would reject a legitimate document and not only a malicious one. (600 s was set first and replaced by 700 s the same day, because 600 s was about 8 % short of the 650 s estimate for exactly the workload with `--ocr`.)

What the new values cover, from the same measurements (estimates, one machine):

| Case at report A's density (the heaviest seen) | Estimated need for 600 pages | Fits 700 s / 6144 MB |
|---|---|---|
| Run without `--ocr` (inspect + text + word positions) | about 380 s, about 5.5 GB for the text step | Yes, on both |
| Run with `--ocr` (adds image coverage over every page) | about 650 s, about 5.5 GB | Yes: about 8 % of time margin, about 10 % of memory margin |
| Plain layouts like R1 (0.24 s a page) | about 140 s | Yes, with wide margin |

Note for the record: 700 s clears the estimate by about 8 %, the same size of gap that 600 s missed by, now on the safe side. The estimate is an extrapolation from a 159-page report, not a measurement of a 600-page one, so a heavier report could still be stopped (which is catalogued and names the setting). A first measured 600-page design-heavy report would settle it. The PRD's SEC-12 status text is updated to these values in v0.4.55.
