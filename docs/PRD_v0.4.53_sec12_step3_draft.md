# PRD v0.4.53 draft: SEC-12 step 3, a memory limit for the OCR engine (specification only)

| Item | Value |
|---|---|
| Status | **Draft. Not applied.** `docs/PRD.md` is unchanged (0.4.52). It needs the owner's word and a version bump before anything is edited, and nothing is built until then. |
| Drafted | 2026-10-27 |
| Source | The owner's answers of 2026-10-27 to `docs/SEC-12_step3_tesseract_memory_proposal.md`: "Option (b), reuse parse_memory_mb, same code, do it before Phase 6". |
| Version | 0.4.53 |
| Kind | New behaviour: the OCR engine is run under the same memory watch as the parse workers. No new setting, no new error code, no change to any extracted value, check, calculation or memo text. |

## 1. What the owner decided

| Question | Answer |
|---|---|
| Option | **(b)** The parent polls Tesseract's resident memory and kills its process group past the limit. |
| Limit | **Reuse `ingestion.parse_memory_mb`** (4096 MB today). No `ocr.memory_mb`. |
| Error code | **`E-INPUT-PARSE-LIMIT`**, no new code. |
| Timing | **Before Phase 6.** |

## 2. A point the decision leaves open (my proposal, for you to confirm or change)

| # | Point | Proposal |
|---|---|---|
| 1 | **Tesseract's time.** You chose (b) as written, which keeps Tesseract's own whole-call limit and does not count it in the 300 s parse budget. | Keep that. Passing `ocr.timeout_seconds` stays `E-INPUT-OCR-FAILED`, as today. Counting OCR reading in the parse budget would make the two limits overlap and change what `ocr.timeout_seconds` means. |
| 2 | **Where the memory error is reported.** The catalogue entry for `E-INPUT-PARSE-LIMIT` says "Parsing the PDF exceeded the time limit or the memory limit". | Keep the entry's wording. The message detail for an engine breach says `memory limit; raise ingestion.parse_memory_mb`, the same fixed text as a worker breach, so a reader is told the setting to raise. The G.1 row gains no new stage. |
| 3 | **Stale wording found on the way.** FR-001A.7 ends "These limits do not replace SEC-12 (OD-6), which stays open." OD-6 was decided on 2026-10-27 (v0.4.50). | Replace that sentence with the current statement, below. It is a status correction, not a requirement change. |

## 3. Exact text changes if approved

1. **FR-001A.7 (Limits),** the last sentence, from *"These limits do not replace SEC-12 (OD-6), which stays open."* to: *"These limits do not replace the parse limits of SEC-12 (OD-6, decided v0.4.50): while the OCR engine reads a page, its resident memory is also watched against `ingestion.parse_memory_mb`, and passing it ends the run with `E-INPUT-PARSE-LIMIT` (v0.4.53). The engine's reading time is not counted in the parse time budget; it keeps `ocr.timeout_seconds`."*
2. **FR-001 criterion 10,** after the OCR render sentence, state that the OCR engine is watched too, and delete "Not covered: the OCR engine's own memory (Tesseract keeps its whole-call time limit, `ocr.timeout_seconds`)", leaving the evaluation tools as the remaining gap. (The status text moves to v0.4.53 once built.)
3. **SEC-12,** the sentence that lists what is not covered: remove the OCR engine's memory from it. Until the code is built the cell would read "specified; not implemented" for this step, as v0.4.50 did for steps 1 and 2.
4. **Risk row (Section R):** "The OCR engine's memory and the evaluation tools stay unlimited" becomes "the evaluation tools stay unlimited".
5. **OD-6 rows (A.1 and A.2):** add that step 3 (the OCR engine's memory) is decided in v0.4.53.
6. **Appendix B.6:** a new example: *an OCR engine that passes the memory limit while reading a page → `E-INPUT-PARSE-LIMIT`, naming the memory limit, no document text.*
7. **Revision history:** a 0.4.53 row. **Version and Status cells** in Section A.

## 4. What is not changed

Every extracted value, check, calculation, rule and memo text; the OCR page cap and time limit; the two parse settings and their values; the existing error codes and exit codes; Release 1's approval; the held-out record.

## 5. Implementation order if approved

1. Apply this draft as v0.4.53 (documents only).
2. **Build:** a supervised-run function in `ingestion/sandbox.py` (own process group, standard input fed from a thread, standard output drained into memory with a cap, resident memory polled every 100 ms, the group killed past the limit); a `use_runner` hook on the Tesseract engine used for the page read only; the command line wiring, as step 2 did for the renderer. Without the hook, behaviour is unchanged.
3. **Tests (synthetic only):** stub engines that allocate, sleep, flood their output, crash and start a child; equality of the TSV and the page read with and without the runner; one opt-in real-engine test; no document text in any error; no process left behind; mutation checks on the limit comparison, the group kill, the error mapping and the hook wiring.
4. After the build, a status edit of the PRD cells (a further version bump on your word, as for steps 1 and 2).

## 6. What I need from you

1. Confirm or change the three points in section 2.
2. "Apply" to apply this as v0.4.53.
