# SEC-12 / OD-6 proposal: time and memory limits for parsing untrusted PDFs

| Item | Value |
|---|---|
| Status | **Proposal for the owner's review. Nothing is built, and `docs/PRD.md` is unchanged (0.4.48).** A PRD draft follows only if you approve a direction. |
| Drafted | 2026-10-27 |
| What it answers | SEC-12 (resource limits when parsing untrusted PDFs; mandatory before Phase 6) and OD-6 (how, and whether earlier). |
| Kind | New behaviour: two settings, one new catalogued error, a worker process around the PDF libraries. No change to any extracted value, check, calculation or memo text. |

## 1. The gap, in the PRD's own words

File size and page count are limited (FR-001.2 and .3: 100 MB and 600 pages since v0.4.43), "but compressed PDF content can expand well beyond the file size, and the PDF library has no built-in time limit." SEC-12 requires a **per-document time limit and a memory limit**, failing with a catalogued error, before any multi-user or network-exposed use (Phase 6 onward). For Release 1 it is a documented limitation. Two things since Release 1 make the limitation larger: the file limit is four times higher, and OCR renders pages.

## 2. Where untrusted bytes are parsed today (read from the code)

| Operation | Library | Where | Limit today |
|---|---|---|---|
| Open, encryption check, page count | pdfplumber (pdfminer) | `ingestion/validation.py` (`inspect`) | none |
| Text of every page | pdfplumber | `ingestion/ingest.py:39` (`extract_pages`) | none |
| Word boxes of the pages used | pdfplumber | `extraction/pipeline.py:291` (`extract_words`) | none |
| Image coverage of every page (OCR runs) | pdfplumber | `extraction/pipeline.py:152` (`image_coverage`) | none |
| Page rendering for OCR | pypdfium2 (in process) | `ingestion/tesseract_ocr.py`, `_render` | the call's deadline is checked only between pages |
| OCR reading | Tesseract, a subprocess | `ingestion/tesseract_ocr.py` | whole-call time limit (`ocr.timeout_seconds`); no memory limit |

Each operation opens the file again, in the same process as the rest of the program. A hostile or merely very large file can therefore hang the run or exhaust its memory, and nothing stops it.

## 3. What it costs today (measured on synthetic pages, this machine)

Dense synthetic pages (70 lines of figures each), generated for the test and never kept. A real report differs, so these show scale, not a forecast.

| Pages | Text of all pages | Word boxes (15 pages) | Image coverage (all pages) | Peak memory |
|---|---|---|---|---|
| 50 | 6.5 s | 2.3 s | 5.7 s | about 477 MB |
| 600 | 98.7 s | 1.7 s | 96.9 s | about 1,965 MB |

At the 600-page limit, reading the text alone takes about 99 s, and a run that uses OCR adds about 97 s for image coverage: over three minutes before the model is called, and close to 2 GB of memory for a file of only 0.6 MB. (The memory figure is the peak of all four operations run in one process, which is how the program runs them today.) Parse cost is driven by page content, not file size, so a file limit does not bound it. A time limit set too low would stop honest documents; one set too high protects nothing. The values have to come from measurement on public reports, which is why this proposal gives none.

## 4. What the owner can choose from (the PRD's OD-6 options, with what I found)

| Option | Text | Finding |
|---|---|---|
| (a) | Keep the limitation, document it (Release 1 as is). | Not allowed past Phase 6; leaves a local run hangable. |
| (b) **Proposed** | Run the PDF libraries in a **separate worker process** that the parent can stop. | Works for time on every platform. For memory it needs a parent-side check on macOS, see below. |
| (c) | Signal-based timeout in the same process. | Unix only and main thread only; cannot bound memory; a C library stuck in a call may never reach the signal handler. |

**A finding that shapes (b).** On this machine (macOS) the operating system's memory limits **cannot be set**: `setrlimit` for `RLIMIT_AS` and `RLIMIT_DATA` both fail ("current limit exceeds maximum limit"), and a 1.5 GB allocation went through with a 512 MB limit requested. A limit set that way on macOS would do nothing, and I will not claim a memory limit that is not enforced. So the memory limit has to be enforced by the **parent watching the worker's memory use and killing it** when it passes the limit. On Linux the same limit can also be set in the worker with `RLIMIT_AS`, as an extra layer. Windows is not tested here and has no `resource` module; the parent-side check is the only mechanism there.

## 5. Proposed design

**Worker.** A small module, `ingestion/parse_worker.py`, started as `python -m credit_intel.ingestion.parse_worker <operation> <path> [arguments]`. It runs one operation (`inspect`, `extract_pages`, `extract_words`, `image_coverage`) with the existing pdfplumber code and writes the result as JSON to its standard output. The file is opened read-only. It writes nothing else.

**Parent.** A `SandboxedExtractor` implements the same `TextExtractor` and `WordExtractor` interfaces the rest of the program already uses, so no other module changes. It starts the worker for each operation, and:
- enforces **one time budget for all parsing in the run** (a deadline for the whole run, as the OCR limit covers the whole call, not each page);
- polls the worker's resident memory while it runs and **kills the process group** when it passes the memory limit or the deadline;
- turns an exit that is not clean into the same catalogued errors as today (`E-INPUT-CORRUPT` for a file the worker cannot parse), and a limit stop into the new error below;
- never puts document text in an error or a log.

**Settings.** A new `[ingestion]` pair, `parse_timeout_seconds` and `parse_memory_mb`, **required and with no default**, like the token ceiling and the OCR limits: a missing one is `E-CONFIG-INVALID`. They go in `config/settings.toml`, set by you.

**Error.** One new code, `E-INPUT-PARSE-LIMIT` (exit 3, like the other input errors), whose message names the limit that was hit (time or memory) and the setting to raise, and nothing from the document. It would be the twenty-first code and needs its own SC-09 scenario. A two-code alternative (`E-INPUT-PARSE-TIMEOUT` and `E-INPUT-PARSE-MEMORY`) is possible if you prefer them distinct.

**OCR.** Step 1 leaves the OCR path as it is. Step 2 would move the page rendering (`_render`, pypdfium2) behind the same boundary, so a page that hangs the renderer is also stopped. Tesseract already has a whole-call time limit and runs as its own process; the parent-side memory check would extend to it.

**Output.** Results are the same data as today. A test compares the worker's output with the in-process output on the fixture PDFs, field by field, so the goldens and every downstream result stay byte for byte as they are.

## 6. Cost and risk of the design

- **Start-up cost.** One process start per operation, each importing pdfplumber; the proposal measures this on the fixtures before choosing between one worker per operation and one worker for several operations in a run. I have not measured it yet.
- **Data transfer.** The text and word boxes of up to 600 pages cross as JSON; at the sizes measured above that is small next to the parse itself.
- **Memory polling is sampled, not exact.** A burst between two samples can pass the limit briefly; the poll interval is a design choice (proposed 100 ms), and the limit is a bound, not an exact figure.
- **A bomb inside a native library** (pypdfium2, Tesseract) is bounded only by the same watch, not prevented.
- **Not covered:** the LLM call, the memo writer, and anything after parsing. The inputs to those are already limited in size.

## 7. How I would test it (all synthetic, generated at test time, nothing real)

- A stub worker command (as the Tesseract adapter's tests use a stub) that **sleeps** past the deadline: the run stops with `E-INPUT-PARSE-LIMIT` and the time message, within the limit plus a small margin, and the worker is gone.
- A stub that **allocates** past the memory limit: the same, with the memory message.
- A generated **decompression bomb** (a small compressed stream that expands to a large size) with a small limit, so the test cannot harm the machine: the parent kills the worker, not the test run.
- **Equality** of worker output and in-process output on the fixture PDFs.
- **No document text** in any error, log or manifest line; a worker that dies leaves no orphan process; a missing or invalid setting is `E-CONFIG-INVALID` naming it.
- **Mutation checks** on the limit comparison, the process-group kill and the time budget.

## 8. Order of work if approved

1. A PRD draft (SEC-12 text, the OD-6 decision, a new FR-001 criterion, the error catalogue, a version bump), for your approval before anything is built.
2. Step 1: worker, `SandboxedExtractor`, the two settings, the error code and its tests.
3. Step 2: the OCR render behind the same boundary.
4. Measurement on public reports (your authorisation and approval as before) to propose the two values; you set them.

## 9. What I need from you

1. OD-6: option (b), or another.
2. One error code or two.
3. Whether the two settings are required with no default (proposed), or have a default.
4. Whether memory limiting by polling is acceptable as the enforcement mechanism, given the finding in section 4.
5. Whether Step 2 (OCR render) is part of the first approval or comes later.
