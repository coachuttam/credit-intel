# PRD v0.4.59 draft: Phase 6, an HTTP API and a web page (specification only)

| Item | Value |
|---|---|
| Status | **Applied as v0.4.59 on 2026-10-30** (the owner: "Apply the draft as v0.4.59", after "as recommended on all six: 1a, 2a, 3a, 4a, 5a, 6a"; the whole-run timeout approved as designed and named as a limitation; `E-API-REQUEST` a catalogued 23rd code). This file is the record of the draft. Earlier status text follows: `docs/PRD.md` was 0.4.58. It needs the owner's word and a version bump before anything is edited, and nothing is built until then. |
| Drafted | 2026-10-30 |
| Source | `docs/PHASE6_plan.md` (2026-10-30); the owner's decisions of 2026-10-30: OD-19, 20, 21, 22, 23, 24 and 26 "approved as proposed"; **OD-25 approved as proposed: `max_concurrent_runs = 1`, `max_queued_runs = 4`, `run_timeout_seconds = 1,200`** on the 8 GB host, measured in `docs/OD-25_run_timing_2026-10-30.md`; "draft the Phase 6 PRD change". |
| Version | 0.4.59 |
| Kind | New requirements (FR-016, FR-017, SEC-14 to SEC-16), two new catalogued error codes (`E-RUN-TIMEOUT`, `E-API-REQUEST`), one new settings table, new dependencies, and the changes they need elsewhere (Sections F, G.1, L, M, P, Q, S, Appendices A and B). **No change** to extraction, validation, evidence, calculation, rules, labelling, the text of the memo or of the report, or any existing error code or exit code. Built in steps after approval, each separately approved. |

## 1. Points the approvals leave open (my proposals, for you to confirm or change)

| # | Point | Proposal |
|---|---|---|
| 1 | **Which failures return an HTTP error and which appear in the run's status.** A run is accepted with `202` and runs later, so most catalogued failures happen after the reply. | The checks that need no parsing run **in the request**, with the same functions the command line uses, and reject with a catalogued 4xx **before any run exists** (no folder, no run ID, as for failures before `received`): size (while streaming), the `%PDF-` signature, the option values and `--pages` syntax, the profile, the confirmation and the send rule, and queue capacity. Every other failure is reported **in the run's status** (`GET /runs/{id}` answers `200` with state `failed`, the code and its fixed message). The mapping table in FR-016 criterion 5 gives both columns. |
| 2 | **The new whole-run time limit.** `run_timeout_seconds` is new behaviour and needs a code (the 22nd) and a rule. **Owner, 2026-10-30: approved as designed, and the limitation is to be named in the PRD itself** (FR-016 criterion 10a, Section R). A thread cannot be killed safely. | A **cooperative deadline**: the run checks the clock at each state transition and before each model call and stops with the new code `E-RUN-TIMEOUT` (a manifest-only failure record, as for any failure after `received`). The parts that handle hostile bytes already end themselves under their own limits (parse worker, OCR engine, report: 120 s). A run past the deadline holds its pool slot until its thread returns, and the status says so; the slot is not given away early. Exit code: **none for the command line**, which has no whole-run limit (the limit is an `[api]` setting); the catalogue records it as "API only". |
| 3 | **The output and cache folders.** Both default to paths relative to the current directory, which a server must not rely on. | Two required `[api]` settings with no default, `output_dir` and `cache_dir`, each an absolute path, checked at start-up. The command line keeps its own defaults. |
| 4 | **The port.** | `8000` as the default, with the host default `127.0.0.1`. Both overridable; neither is a limit. |
| 5 | **The run ID in a URL, and listing.** | The run ID keeps its form `<UTC start>-<8 hex>`; anything else is `404` before the disk is touched. `GET /runs` reads the manifests on disk (newest first, at most 100), so it also lists runs from before a restart. A run still in flight shows from memory. |
| 6 | **Queue and `429`/`503`.** | A full queue (`max_queued_runs` waiting) answers `429` with a fixed body and `Retry-After`; a server shutting down answers `503`. |
| 7 | **Page script.** The OD-22 policy allows "own styles only; no inline script". | One small script file served from the service itself, with `script-src 'self'`; the page works for reading without it (polling is its only use). |

## 2. Exact text changes if approved

### 2.1 New requirement FR-016, after FR-015

> ### FR-016 — HTTP API (Should; specified in v0.4.59, implemented after Release 1; Phase 6)
>
> **Behaviour:** a FastAPI service accepts one PDF with the options of the command line, runs the **same pipeline** on it, and serves the files of the run folder. The API is a **transport**: it adds no extraction, validation, calculation, rule, label or sentence of analysis. The command line and the API both call one service function (`execute_run`), so the wiring is not duplicated.
>
> **Acceptance criteria:**
>
> 1. **Endpoints.** Exactly these five, and no delete, edit or re-run (a run folder is never modified after it is written, FR-010.4):
>    - `POST /runs` (multipart): one `file` and the fields `basis`, `pages`, `assert_basis`, `profile` (the JSON of FR-014.7, as text), `ocr`, `no_report` and `confirm_public_document`, with the meaning, defaults and rules of the same options of FR-014 (OD-26: all of them). Returns `202` with `{"run_id", "state": "queued"}` after criterion 6's checks pass.
>    - `GET /runs/{run_id}`: the state (`queued`, the states of FR-011 as reached, `exported` or `failed`), the counts the recorder holds for them, for `failed` the code and its fixed message and the stage, and the names of the files that exist.
>    - `GET /runs/{run_id}/memo`, `/results`, `/manifest`, `/report`: the file of the run folder **byte for byte** (`text/markdown; charset=utf-8`, `application/json`, `application/json`, `application/pdf`), `404` if the run or the file does not exist (a run without `report.pdf`, FR-015 criterion 7, has no `/report`).
>    - `GET /runs`: run IDs with their final state, from the manifests on disk and the runs in flight (point 5).
>    - `GET /health`: `{"status": "ok", "queued": n, "running": n}`; needs no token and shows nothing else.
> 2. **Same pipeline, same files.** For the same input and options the API writes the same files as the command line: a test runs both and compares every file byte for byte, apart from the run ID and the times the files themselves carry. The API adds no text beyond the catalogued messages.
> 3. **Run IDs.** The ID is computed when the upload is complete, in the existing form `<UTC start>-<first 8 hex of the SHA-256>`, so the `202` carries the ID the folder will have. A run ID in a path that does not match that form is `404`; no path component of a request is ever joined to a folder name unchecked.
> 4. **Execution (OD-19, option a).** A bounded pool of worker threads in the server process runs the pipeline, one run per thread. `api.max_concurrent_runs` runs at once; at most `api.max_queued_runs` wait. The parts that handle hostile bytes keep running in their own processes under their own limits (SEC-12). State is held in memory while a run is going and in the run folder afterwards (OD-20, option a); a restart loses runs in flight, and because a folder is only ever complete or absent (FR-010.3) nothing half-written is ever served. A run that was queued or running at a restart is simply unknown after it (`404`).
> 5. **Errors.** The same catalogue (G.1), shown as a fixed JSON body `{"code", "message"}` (and the run ID for an internal error): nothing from the document, no stack trace, no path (FR-011.4). The status mapping is below; a test requires that **every catalogued code has a row**.
>
>    | Code | At submission (HTTP) | After acceptance |
>    |---|---|---|
>    | `E-INPUT-TOO-LARGE` | `413` | (not reachable) |
>    | `E-INPUT-NOT-PDF` | `422` | in the status |
>    | `E-INPUT-SEND-REFUSED` | `403` | (not reachable) |
>    | `E-INPUT-PROFILE-INVALID`, `E-INPUT-PAGE-RANGE` (syntax) | `422` | `E-INPUT-PAGE-RANGE` for a range outside the document: in the status |
>    | `E-API-REQUEST` | `422` | (not reachable) |
>    | `E-CONFIG-INVALID` | `500` (also at start-up: the service does not start) | in the status |
>    | `E-INPUT-NOT-FOUND` | `500` (the server's own temporary copy is missing) | in the status |
>    | `E-INPUT-CORRUPT`, `E-INPUT-ENCRYPTED`, `E-INPUT-TOO-MANY-PAGES`, `E-INPUT-NO-TEXT-LAYER`, `E-INPUT-OCR-FAILED`, `E-INPUT-PARSE-LIMIT`, `E-EXTRACT-NO-STATEMENT-PAGES`, `E-EXTRACT-BASIS-UNAVAILABLE`, `E-LLM-BUDGET-EXCEEDED` | not raised at submission | in the status (`failed`, the code, the fixed message) |
>    | `E-INPUT-OCR-UNAVAILABLE` | `503` when `ocr` is requested and the engine is not installed | in the status |
>    | `E-LLM-INVALID-OUTPUT`, `E-LLM-UNAVAILABLE`, `E-LLM-AUTH`, `E-EXPORT-FAILED`, `E-RUN-TIMEOUT` | not raised at submission | in the status |
>
>    A full queue is `429`. A malformed request (a missing file, an unknown field, a bad value) is `422` with the catalogued code `E-API-REQUEST` (the 23rd, G.1; owner, 2026-10-30), which has no command-line equivalent.
> 6. **Checks before acceptance.** In the request, before a run exists: the upload is streamed to a private temporary file under `ingestion.max_file_bytes` (criterion 7); the `%PDF-` signature; the option values; the profile; `confirm_public_document` and the send rule (SEC-10, criterion 8); and queue capacity. A rejection creates no run folder and no run ID.
> 7. **Uploads (SEC-14).** See SEC-14.
> 8. **The send rule for uploads.** The upload is hashed and the held-out guard works on it exactly as on a file (FR-014 criterion 8): a held-out document is refused (`403`, `E-INPUT-SEND-REFUSED`, reason word `held_out`). When the provider sends data off the machine, `confirm_public_document=true` is **required** for a document not on the assignment record (reason word `not_recorded`); a record file that cannot be read refuses every document. The `private/` approval variable is **not** honoured by the API: an upload is never "in `private/`", and the service never reads a path under `private/`.
> 9. **Settings (new `[api]` table).** `max_concurrent_runs`, `max_queued_runs` and `run_timeout_seconds` are **required with no default** (like the parse limits); `output_dir` and `cache_dir` are required absolute paths; `host` (default `127.0.0.1`) and `port` (default `8000`) may default. Each can be set by an environment variable (`CREDIT_INTEL_API_...`). A missing, non-numeric, zero or negative limit, or a relative path, fails start-up with `E-CONFIG-INVALID`. **Values (OD-25, owner, 2026-10-30), for the 8 GB host: `max_concurrent_runs = 1`, `max_queued_runs = 4`, `run_timeout_seconds = 1200`.** The reasoning is in `docs/OD-25_run_timing_2026-10-30.md`: the worst-case memory is `max_concurrent_runs` times `ingestion.parse_memory_mb` (6144 MB), which one run fits in 8 GB and two do not; a real 146-page run took about 60 s and a document near the input ceiling is estimated at 650 s for parsing alone. A different host is a Phase 7 question.
> 10. **Whole-run time limit (new behaviour).** `api.run_timeout_seconds` bounds one API run. The run checks the deadline at each state transition and before each model call; past it the run ends with the catalogued failure `E-RUN-TIMEOUT` (G.1), a manifest-only failure record, no output that looks complete. The limit does not apply to the command line. A document near the input ceiling may legitimately need more than 1,200 s; the message says to narrow the pages or raise the limit deliberately.
>     - **Named limitation (10a).** The deadline is **cooperative**: it is checked only at state transitions and before each model call, so a stage that is already running is not interrupted by it. A run can therefore end later than `run_timeout_seconds`, bounded by the limits of that stage (the parse budget of SEC-12, the OCR limits of FR-001A, the model's own timeout and retries, and the report's 120 s). A run past its deadline keeps its pool slot until its thread returns; the slot is not given away early, so the memory bound of criterion 9 holds. The status of such a run says that the deadline has passed and that it is stopping. This is a limitation of the in-process pool (OD-19 (a)); a stronger guarantee, a process per run that can be killed, is OD-19 (b) and was not chosen.
> 11. **Start-up and access (SEC-15).** See SEC-15.
> 12. **Logging.** The API logs the request line, the run ID, the state changes and the final result at INFO, with no document text, file name, quote, value, token or key (SEC-08).
> 13. **Tests (all synthetic, offline).** The fake provider and FastAPI's test client: a good run from submission to every file; every row of the mapping table; a non-PDF, an encrypted, an over-size (by `Content-Length` and mid-stream) and an empty upload; a held-out document refused; `confirm_public_document` required with an external provider; the concurrency and queue limits and `429`; the deadline (`E-RUN-TIMEOUT`) with a stalled stage; run-ID forms and traversal strings; the token cases (SEC-15); temporary files removed on success, failure and client disconnect; no process left after a timeout; the API's files equal the command line's; the OpenAPI document lists exactly the five endpoints; mutation checks on each guard.

### 2.2 New requirement FR-017, after FR-016

> ### FR-017 — Web page (Should; specified in v0.4.59, implemented after Release 1; Phase 6)
>
> **Behaviour:** one server-rendered page on top of FR-016: an upload form, the list of runs and a run view. It is a **presentation of the files the run wrote**; it computes and rewrites nothing.
>
> **Acceptance criteria:**
>
> 1. **Pages.** `GET /` (the form and the list), `GET /ui/runs/{run_id}` (the run view). No framework and no build step; one stylesheet and one small script file served by the service.
> 2. **The form** has every option of FR-016 criterion 1. The notice of SEC-01 and SEC-10 ("only public or synthetic documents may be sent to the hosted model") is printed beside the **confirmation checkbox**, and the page does not send the form without it when the provider is external.
> 3. **The run view** polls `GET /runs/{id}` while the run is going and shows its state and the catalogued message on failure. For an `exported` run it shows the memo and links to `report.pdf`, `results.json` and `manifest.json` (OD-22, option a).
> 4. **The memo as HTML** is made from the same `memo.md` the run wrote, parsed as CommonMark with markdown-it-py **with raw HTML switched off**, as the report is (FR-015). Every origin label is visible as text, in its place and in its words; the draft statement of K.0 is on the page and in a fixed footer; section 9 is shown whole. The page adds no number, label or sentence of its own beyond the form's text and the catalogued messages.
> 5. **Untrusted text (SEC-16).** Document, analyst and profile text reaches the page only as escaped text.
> 6. **Tests:** the page for a good run, a failed run and a run in flight; the form with and without the confirmation; every label of the memo present on the page and no label added; injected `<script>`, `<img>`, `<a href>`, `javascript:` and entity sequences in a borrower name, a quote and a note printed as text; the response headers of SEC-16; the page works with the script file unavailable.

### 2.3 Other changes

1. **Error catalogue (G.1):** two new rows, the 22nd and 23rd codes, both for the API only. (a) `E-RUN-TIMEOUT` · stage: any, after `received` · meaning: *the run passed `api.run_timeout_seconds` (FR-016 criterion 10)* · what the user should do: *narrow the pages, or raise the limit deliberately* · exit code: *none (API only)* · retried: No · status: Specified. (b) `E-API-REQUEST` · stage: before `received` (no run exists) · meaning: *the request is malformed: a missing file, an unknown field or a value of the wrong form (FR-016 criterion 5)* · what the user should do: *correct the request to the documented fields* · exit code: *none (API only; HTTP `422`)* · retried: No · status: Specified. The text above G.1's table is unchanged; the sentence about exit codes gains *"`E-RUN-TIMEOUT` and `E-API-REQUEST` have none because only the API raises them."* The 21 existing codes and their exit codes do not change. A test requires that every code has an HTTP mapping (FR-016 criterion 5) and that the two API-only codes are never raised by the command line.
2. **FR-014 (command line):** a sentence: *"From v0.4.59 the command line and the API call the same service function; the command line's behaviour, options, exit codes and files are unchanged."*
3. **FR-011 (states):** a sentence: *"`queued` (v0.4.59) is a state of an API run before `received` and is not a pipeline state; the manifest never records it."*
4. **FR-001 criterion 2 (input limits):** *"The API applies the same limits to an upload (FR-016)."*
5. **Section F.2 (future releases), the row "Web interface and REST API (FastAPI)":** to *"Specified in v0.4.59 (FR-016, FR-017); implemented in steps after approval."*
6. **Section L.2 (dependencies):**
   - `FastAPI` row: from "No" to *"Yes, from v0.4.59 (Phase 6). The HTTP API and the web page (FR-016, FR-017)."*
   - New rows: `uvicorn` (the server process), `python-multipart` (multipart uploads, which FastAPI needs for `POST /runs`), and `httpx` (dev only: FastAPI's test client). Each with its licence recorded at install, pinned in `uv.lock`; SEC-11's documented reason is FR-016.
   - The `Docker`, `Cloud hosting` and `PostgreSQL + pgvector` rows are unchanged.
7. **Section L.2.1:** add **D-17** *"The HTTP API is FastAPI, run by a bounded thread pool in the server process, with state in memory and the run folders on disk (OD-19 (a), OD-20 (a)); decided by the owner, 2026-10-30."*
8. **Section L.3:** two rows: `service` (the one function that runs the pipeline with settings, the send rule, the OCR engine, the parse worker and the report; called by `cli` and `api`) and `api` (the endpoints, the job pool, upload handling, the page).
9. **Section M (security):** the three rows in 2.4 below. **SEC-01** gains: *"The service is for public and synthetic documents only; the page and the README say so."*
10. **Section N:** **NFR-06** unchanged. A new **NFR-10 (Capacity)**: *"The number of runs at once and waiting is limited by required settings. The worst-case memory is `api.max_concurrent_runs` times `ingestion.parse_memory_mb`; the values are chosen together and recorded with their measurements."*
11. **Section P (repository structure):** `src/credit_intel/service.py` and `src/credit_intel/api/` (`app.py`, `jobs.py`, `uploads.py`, `pages.py`, `static/`).
12. **Section Q, Phase 6 row.** Goal: *"HTTP API (FR-016) and web page (FR-017) over the unchanged pipeline"*. Entry: unchanged (both conditions are met). Exit: *"The five endpoints work for submission, status and every file. The same pipeline is reused and the API's files equal the command line's. Every catalogued code has a mapping and a test. The upload, access and page controls of SEC-14 to SEC-16 are tested. The `[api]` limits are enforced. No new behaviour bypasses the evidence and labelling rules."* A note that Phase 7 (Docker, deployment, persistence, accounts, TLS, the full security review) is **not** changed and stays deferred.
13. **Section R (risks):** four rows: memory under concurrency (the relation in FR-016 criterion 9); a run's loss at restart (OD-20); public exposure of a tool whose rule is public and synthetic data only (SEC-01, SEC-15); and a legitimate large document exceeding `run_timeout_seconds`; and the **named limitation** that the whole-run deadline is cooperative (FR-016 criterion 10a): a run can end later than the limit, and holds its slot until it does.
14. **Section S:** the bullet *"Web UI, REST API, database, Docker, and cloud deployment (planned for later phases)"* becomes *"Database, Docker, cloud deployment, TLS, user accounts and roles (Phase 7 or later). A web UI and REST API are specified in FR-016 and FR-017 (v0.4.59)."* Also added: *"Delete, edit or re-run endpoints (a run folder is never modified)."*
15. **Appendix A.2:** rows **OD-19 to OD-26**, each *"Decided 2026-10-30: option (a)"* (OD-21: *option (b)*; OD-25: *the values 1, 4 and 1,200*) with its consequence as in the plan.
16. **Appendix B.6:** examples 161 to 178, below.
17. **Revision history:** a 0.4.59 row. **Version and Status cells** in Section A.

### 2.4 New security requirements (Section M)

> | SEC-14 | **Uploads (v0.4.59).** The size limit is enforced while streaming and early from `Content-Length`; the request is cut off when it passes `ingestion.max_file_bytes`. The upload is written to a private temporary directory (mode 0700) outside the output folder under a random name; the client's file name is never used as a path (it is kept only as the recorded input name, escaped as today). The temporary copy is removed when the run ends, fails or the client disconnects (OD-23, option a), so only the run folder remains and the evidence still traces to the document by its hash and page. The signature, encryption, page count and parse limits of FR-001 and SEC-12 apply unchanged. A cap on concurrent and queued runs applies (FR-016 criterion 4). |
> | SEC-15 | **Access control (v0.4.59, OD-21 option b).** The service binds to `127.0.0.1` by default. It **refuses to start on any other address unless a bearer token is set** in `CREDIT_INTEL_API_TOKEN` (non-empty, at least 32 characters). When a token is set, every endpoint except `GET /health` requires `Authorization: Bearer <token>`; the comparison is in constant time; the token is never logged, never put in a URL, never in an error body. A missing or wrong token is `401` with a fixed body. No accounts or roles (Phase 7). TLS is not provided by the service; off the machine it needs a reverse proxy (Phase 7). The service never reads, lists or serves anything outside its `output_dir`, and nothing under `private/`. |
> | SEC-16 | **Untrusted text on the web page (v0.4.59, OD-22 option a).** The memo is shown through the CommonMark parser with raw HTML off and all text escaped; document, analyst and profile text is never interpreted as markup, a link, a script or a request to load anything. Every page and file response carries `Content-Security-Policy: default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `Cache-Control: no-store`. Served files carry the content types of FR-016 criterion 1, and `results.json`, `manifest.json` and `memo.md` are never served as `text/html`. |

### 2.5 Examples for Appendix B.6

| # | Case | Expected |
|---|---|---|
| 161 | A good PDF posted with `confirm_public_document=true` and the fake provider | `202` with a run ID; the status moves through the FR-011 states to `exported`; the four files are served byte for byte |
| 162 | The same input and options through the API and through the command line | Every file identical, apart from the run ID and the times the files carry |
| 163 | A file without the `%PDF-` signature | `422`, `E-INPUT-NOT-PDF`, fixed body; no run folder, no run ID |
| 164 | An upload larger than `ingestion.max_file_bytes`, sent with a lying small `Content-Length` | Cut off while streaming; `413`, `E-INPUT-TOO-LARGE`; the temporary file is removed |
| 165 | A held-out document | `403`, `E-INPUT-SEND-REFUSED`, reason word `held_out`; no provider built |
| 166 | An external provider and `confirm_public_document` missing, for a document not on the assignment record | `403`, `E-INPUT-SEND-REFUSED`, reason word `not_recorded` |
| 167 | A corrupt PDF that passes the signature | `202`; the status becomes `failed` with `E-INPUT-CORRUPT` and its fixed message; the response of the status is `200` |
| 168 | A fifth waiting run when `max_queued_runs = 4` and one is running | `429`, `Retry-After`; no run created |
| 169 | A run still going after `run_timeout_seconds` | The next deadline check ends it with `E-RUN-TIMEOUT`; a manifest-only failure record; the slot is freed when the thread returns |
| 170 | `GET /runs/..%2f..%2fprivate` and other strings that are not run IDs | `404`; nothing outside `output_dir` is touched |
| 171 | A start with `host = 0.0.0.0` and no token | The service does not start (`E-CONFIG-INVALID`); with a token, every endpoint but `/health` answers `401` without the right bearer token |
| 172 | A borrower name containing `<img src=...>` and `<script>` in the profile | The page shows the characters as text; the response headers of SEC-16 are present; nothing is loaded |
| 173 | A client disconnects during an upload | The temporary file is removed; no run is created |
| 174 | A run for a document with no `report.pdf` (`no_report=true`) | `GET /runs/{id}/report` is `404`; the status lists the three files that exist |
| 175 | The service restarts while a run is going | The run is unknown afterwards (`404`); a folder is either complete or absent; nothing half-written is served |
| 176 | A start with `output_dir` relative, or `max_concurrent_runs = 0` | The service does not start, `E-CONFIG-INVALID`, naming the setting |
| 177 | A request with no `file`, or an unknown field, or `ocr=maybe` | `422`, `E-API-REQUEST`, fixed body; no run folder, no run ID |
| 178 | A stage that outlasts the deadline (a stalled stage in a test) | The status says the deadline has passed; the run ends at the next check with `E-RUN-TIMEOUT`; the slot is held until the thread returns and the queue does not start another run into it |

## 3. What is not changed

Extraction, validation, evidence, calculation, rules, the text of the memo and of the report and their checks (K.10, FR-015), FR-001 to FR-015 other than the sentences above, the 21 existing error codes and every exit code, the parse limits and their values, Release 1's approval, the held-out record, and Phase 7 and Phase 8 (Docker, deployment, persistence, accounts, TLS and the security review stay deferred).

## 4. Implementation order if approved (each step separately approved)

1. Apply this draft as v0.4.59 (documents only).
2. **Service layer:** move the wiring out of `cli._execute` into `service.execute_run`; absolute paths for the cache and output folders; no behaviour change; the existing tests are the proof.
3. **API core:** submission and the job pool, status, the files, the error mapping, the `[api]` settings, `E-RUN-TIMEOUT` and the deadline, the tests.
4. **Upload and exposure security:** streaming limits, temporary files, the token and the start-up refusal, the confirmation and send rule, headers, tests and mutation checks.
5. **Web page:** form, list, run view, the memo as HTML and its policy, the injection tests.
6. **README**, how to start it, the OpenAPI check and an end-to-end test of the whole path.

About five to six sessions of the size of the report build.

## 5. What I need from you

1. Confirm or change the remaining six points in section 1 (1, 3, 4, 5, 6 and 7; point 2 and the `E-API-REQUEST` code are settled).
2. "Apply" to apply this as v0.4.59 (or "apply with changes: ...").
