# PRD v0.4.50 draft: SEC-12 parse limits, OD-6 decided (specification only)

| Item | Value |
|---|---|
| Status | **Draft. Not applied.** `docs/PRD.md` is unchanged (0.4.49). It needs the owner's word and a version bump before anything is edited, and nothing is built until then. |
| Drafted | 2026-10-27 |
| Source | The owner's answers of 2026-10-27 to `docs/SEC-12_parse_limits_proposal.md`: "Option (b), one code, required settings, polling OK, OCR render later". |
| Version | 0.4.50 |
| Kind | New behaviour: a worker process around the PDF libraries, two required settings, one new catalogued error. No change to any extracted value, check, calculation or memo text. |

## 1. What the owner decided

| Question | Answer |
|---|---|
| OD-6 | **(b)** Run the PDF libraries in a separate worker process the parent can stop. |
| Error codes | **One:** `E-INPUT-PARSE-LIMIT` (exit 3). The message names which limit was hit. |
| Settings | **Required, no default.** `ingestion.parse_timeout_seconds` and `ingestion.parse_memory_mb`. A missing or invalid one is `E-CONFIG-INVALID`. |
| Memory enforcement | **Parent-side polling accepted.** The parent watches the worker's resident memory and kills it past the limit. |
| OCR page rendering | **Later.** Not in the first approval; a separate step with its own word. |

## 2. Points the decision leaves open (my proposals, for you to confirm or change)

| # | Point | Proposal |
|---|---|---|
| 1 | **The two values.** Required with no default means every run fails with `E-CONFIG-INVALID` until `config/settings.toml` holds them, so they must be set when the code lands. | I set **no value myself**. When step 1 is ready I bring a measured pair for you to set. For reference only: the measured cost of a 600-page dense synthetic file was about 99 s and about 2 GB. A value near those would stop nothing honest; a value far above them protects nothing. Real-report timings need your authorisation (public reports only) before I propose a final pair. |
| 2 | **What the time limit covers.** | One budget for **all parsing in a run** (validation, text of all pages, word boxes, image coverage), not per operation. The LLM call, OCR reading (already limited by `ocr.timeout_seconds`) and everything after parsing are outside it. |
| 3 | **Poll interval.** | 100 ms, a design choice, not a setting. The memory limit is a bound, not an exact figure; a burst between two samples can pass it briefly. |
| 4 | **Linux.** | Where `RLIMIT_AS` can be set, the worker also sets it, as an extra layer. The polling check stays the stated mechanism on every platform, because macOS cannot enforce an `RLIMIT` (measured 2026-10-27). Windows is untested. |
| 5 | **Phase 6 gate.** | The Phase 6 row of Section Q ("SEC-12 parsing limits implemented") is met by step 1 for the PDF libraries. The OCR render (pypdfium2) stays inside the process until the later step; that step must be done before an OCR-enabled network deployment, and the PRD says so. |

## 3. Exact text changes if approved

1. **SEC-12** (line 1373): replace the "documented limitation" tail with: the limits are **implemented in the worker process (OD-6 option (b), v0.4.50)**; a PDF parse that passes the time or memory limit ends the run with `E-INPUT-PARSE-LIMIT`; the limits are the required settings `ingestion.parse_timeout_seconds` and `ingestion.parse_memory_mb`; the page rendering for OCR is outside them until a later step.
2. **FR-001, new criterion 10:** *"All PDF parsing (validation, text, word positions, image coverage) runs in a separate worker process under one per-run time limit and a memory limit (`ingestion.parse_timeout_seconds`, `ingestion.parse_memory_mb`, both required, no default). A run that exceeds either ends with `E-INPUT-PARSE-LIMIT`, the worker is stopped and leaves no process behind, and no document text appears in the error, a log or the manifest. The result is the same data as an in-process parse."*
3. **Error catalogue G.1:** add `E-INPUT-PARSE-LIMIT` — stage `validated / text_extracted`; meaning: *parsing the PDF exceeded the time or memory limit*; user action: *supply a smaller or simpler file, or raise the limit deliberately*; exit 3; not retried; status *Specified (v0.4.50); not implemented*. This is the twenty-first code.
4. **Appendix B.6:** a new example: a PDF whose parse exceeds the time limit → `E-INPUT-PARSE-LIMIT`, naming the time limit, no document text.
5. **Decisions table A.1, OD-6 row** (line 1756) and **A.2 row** (line 1785): *Decided 2026-10-27, option (b)*, with the five answers above.
6. **Risk row** (line 1646): the mitigation now reads: file and page limits (FR-001) and the parse limits (SEC-12); the remaining risk is the OCR render until its step.
7. **Revision history:** a 0.4.50 row; the version and Status cells in Section A.

## 4. What is not changed

Every extracted value, check, calculation, rule and memo text; the existing error codes and their exit codes; the OCR limits (`ocr.max_pages`, `ocr.timeout_seconds`); the file and page limits; Release 1's approval; the held-out record.

## 5. Implementation order if approved

1. Apply this draft as v0.4.50 (documents only).
2. **Step 1 (build):** the worker module, the parent extractor behind the existing text and word interfaces, the two settings in `config/settings.toml` (values from you), the error code, tests (stub worker that sleeps, stub that allocates, a generated small-limit bomb, equality with in-process output on the fixture PDFs, no document text in any message, no orphan process, missing settings) and mutation checks. The catalogue test's count moves from 20 to 21 with it.
3. **Step 2 (later, own approval):** the OCR render behind the same boundary.
4. Measurement on public reports (your authorisation) to propose the two values.

## 6. What I need from you

1. Confirm or change the five proposals in section 2 (point 1, the values, matters most).
2. "Apply" to apply this as v0.4.50.
