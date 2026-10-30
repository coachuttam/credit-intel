# Phase 6 plan: Interface and API (FastAPI service and a simple web UI)

| Item | Value |
|---|---|
| Status | **Plan for the owner's review. Nothing is built, and `docs/PRD.md` is unchanged (0.4.57).** The owner lifted the deferral of Phase 6 for planning on 2026-10-30. A PRD draft follows only after the owner chooses on the open decisions (section 6). |
| Drafted | 2026-10-30 |
| What the PRD says now | Section Q: Phase 6 is "FastAPI service and simple web UI". Entry: "Release 1 complete. SEC-12 parsing limits implemented" (both are true). Exit: "API exposes run submission and status/results. The same pipeline is reused. API tests pass. No new behaviour bypasses the evidence and labelling rules." Section S and L.2 list the web interface, REST API, database, Docker and cloud as later. |
| What the PRD does not have | Any requirement for an API, an upload, a job, a status, access control or a web page. FR-001 accepts a local path "supplied by the CLI or by a direct call". So Phase 6 starts with requirements (a PRD draft), not code. |

## 1. What Phase 6 is, and is not

**In Phase 6:** a FastAPI service that accepts a PDF, runs the existing pipeline on it, and serves the result files; and one simple web page on top of it. The pipeline, the evidence checks, the labels, the memo and the PDF report are reused and not changed.

**Not in Phase 6** (Phase 7, per Section Q): Docker, cloud deployment, a database, user accounts, TLS (a reverse proxy does that), expanded evaluation and the full security review against Section M.

## 2. What is already there to build on

| Need | Already built |
|---|---|
| Run the pipeline | `run_pipeline` and `export_run`; the command line (`cli._execute`) wires them with settings, the send rule, the OCR engine and the parse worker |
| Live progress | The `Recorder` holds the processing states (FR-011) as they happen |
| The result | A run folder: `memo.md`, `results.json`, `manifest.json`, `report.pdf` (all already atomic and checked) |
| Input safety | Size, page, signature, encryption checks (FR-001); parse limits in a worker process (SEC-12); the send rule (SEC-10); a catalogue of 21 error codes with exit codes |
| Output safety | The memo check (K.10) and the report check (FR-015) |

The one thing in the way: the wiring lives inside the command line module. Step 1 below moves it into a service function that both the command line and the API call, with no change in behaviour.

## 3. Proposed design

**3.1 A service layer (step 1, no behaviour change).** `execute_run(request) -> outcome` takes what the command line takes (a path, basis, pages, assertion, profile, OCR on or off, public-document confirmation, report on or off, settings, environment) and does what `_execute` does. The command line becomes a thin caller. The existing 4,334 tests are the proof that nothing changed. Two things must stop being relative to the current directory: the response cache and the output folder (both default to relative paths today).

**3.2 The API.**

| Endpoint | What it does |
|---|---|
| `POST /runs` (multipart) | One PDF and the options of the command line (`basis`, `pages`, `assert_basis`, `profile`, `ocr`, `no_report`, `confirm_public_document`). Streams the upload to a private temporary file under the size limit, then queues the run. Returns `202` with the run ID. |
| `GET /runs/{run_id}` | The status: the processing states reached so far with their counts, then `exported` or `failed` with the catalogued error code and its fixed message, and which files exist. |
| `GET /runs/{run_id}/memo`, `/results`, `/manifest`, `/report` | The files of the run folder, byte for byte (`text/markdown`, `application/json`, `application/pdf`). |
| `GET /runs` | The run IDs on disk with their final state (read from the manifests). |
| `GET /health` | Alive, and the queue length. |

No delete and no edit endpoint: a run folder is never modified after it is written (FR-010.4).

**3.3 Run IDs.** The run ID is already `<UTC start time>-<first 8 hex of the SHA-256>`. The API computes it as soon as the upload is complete, so that the `202` carries the ID the folder will have. A run ID in a URL must match its fixed form (no path can be smuggled in).

**3.4 Errors.** The same catalogue, shown as a fixed JSON body (`code`, `message`; nothing from the document, no trace). A mapping from the 21 codes to HTTP statuses, for example: input errors `4xx` (`E-INPUT-TOO-LARGE` `413`, `E-INPUT-NOT-PDF`, `E-INPUT-CORRUPT`, `E-INPUT-ENCRYPTED`, page range `422`), `E-INPUT-SEND-REFUSED` `403`, `E-INPUT-PARSE-LIMIT` `422`, config `500`, model `502` or `503`, export `500`, internal `500` with the run ID. A test checks that every catalogued code has a mapping.

**3.5 Uploads (the new attack surface).**
- The size limit (FR-001.2) is enforced **while streaming**, and early from `Content-Length`; a request is cut off when it passes the limit.
- The upload is written to a private temporary directory (mode 0700) outside the output folder, under a random name; **the client's file name is never used as a path** (it is kept only as the recorded input name, escaped as today).
- It is removed when the run ends or fails (see OD-23).
- Signature, encryption, page count and parse limits are already enforced by the pipeline; the worker process is what protects the server from a hostile PDF.
- A cap on concurrent runs and on the queue length (`429` or `503` beyond it).

**3.6 The send rule (SEC-10) for uploads.** An upload is hashed, so the **held-out guard works on it as it does on a file**: a held-out document is refused (`403`, `E-INPUT-SEND-REFUSED`). The command line's `--confirm-public-document` becomes a required field, `confirm_public_document=true`, whenever the provider is external; the web page shows the notice ("only public or synthetic documents may be sent") next to a checkbox. SEC-01 stands: the service is for public and synthetic documents only, and the plan says so on the page and in the README.

**3.7 Access control.** The service binds to `127.0.0.1` by default. It **refuses to start on any other address unless a bearer token is set** (`CREDIT_INTEL_API_TOKEN`, compared in constant time, never logged). No accounts. See OD-21.

**3.8 Job execution.** A bounded pool runs the pipeline in the server process, one run per worker thread; the parts that touch hostile bytes already run in worker processes (the parse worker, the OCR render, Tesseract, the report), under their own limits. Live status comes from each run's `Recorder`. See OD-19.

**3.9 The web page.** One server-rendered page and a small script, no framework: an upload form (options and the public-document confirmation), a list of runs, and a run view that polls the status and then shows the memo, with links to `report.pdf`, `results.json` and `manifest.json`. The memo is shown through the same CommonMark parser as the report with **raw HTML switched off**, every origin label visible, and a strict content security policy (`default-src 'none'`; own styles only; no inline script). See OD-22.

**3.10 Settings.** A new `[api]` table. Following the project's rule that limits have no default: `max_concurrent_runs`, `max_queued_runs` and `run_timeout_seconds` (one limit for a whole run, which has none today beyond the retries) are **required**; host and port may default to `127.0.0.1` and a fixed port. The upload size limit is the existing `ingestion.max_file_bytes`. The memory of a busy server is roughly `max_concurrent_runs` times the parse worker's memory limit, so the values have to be chosen together (with `parse_memory_mb` at 6144 MB, two concurrent runs can already hold 12 GB).

**3.11 Dependencies** (SEC-11, each with its reason): `fastapi`, `uvicorn` (the server), `python-multipart` (uploads), and `httpx` for the tests (dev only).

## 4. What must not change (the exit criterion)

No change to extraction, validation, evidence, calculation, rules, labelling or the memo and report text. The API serves the files as the run wrote them, so a test compares every file of an API run with the same input run through the command line (byte-identical apart from the run ID and times). The API adds no text of its own beyond the catalogued messages.

## 5. How it would be tested (all synthetic, offline)

FastAPI's test client with the fake provider; synthetic PDFs. Submission to result for a good run; every error in the catalogue through the API with its status and fixed body; a non-PDF, an encrypted, a too-large and a mid-stream oversize upload; a held-out document refused; `confirm_public_document` required with an external provider; the concurrency and queue limits; traversal and malformed run IDs; the token (missing, wrong, right) and the refusal to start on a public address without one; the memo page with injected markup (`<script>`, `<img>`, links) printed as text under the policy; temporary files removed on success, failure and client disconnect; no orphan process after a timeout; API files equal to command line files; mutation checks on each guard.

## 6. Decisions for the owner (same format as the OD table; proposals marked, none applied)

| # | Decision | Options | Trade-offs | My proposal |
|---|---|---|---|---|
| OD-19 | How a run is executed | (a) A bounded thread pool in the server process. (b) A subprocess per run that calls the command line. (c) An external queue and workers. | (a) simple, live status from the `Recorder`, shares one process (a defect in a run is the server's). (b) strong isolation and reuse of the command line, but status comes only from log lines and each run pays a start-up. (c) the most robust, and a new component (Phase 7). | (a) |
| OD-20 | Where job state lives | (a) In memory while a run is going, and the run folder afterwards. (b) A SQLite file. | (a) no database (Section S keeps it for later), but a restart loses the runs in flight (their folders, if written, remain). (b) survives restarts and adds a store to secure and migrate. | (a) |
| OD-21 | Who may call the service | (a) Loopback only, no authentication. (b) Loopback by default, a bearer token required to bind elsewhere. (c) Accounts and roles. | (a) cannot be exposed by mistake but cannot be shared. (b) shareable on a trusted network with one secret. (c) is Phase 7 work. | (b) |
| OD-22 | What the page shows | (a) The memo rendered as HTML (raw HTML off, strict policy) with links to the files. (b) Only links to download `report.pdf`, `memo.md` and the JSON. (c) A single-page application. | (a) the best reading experience, a small rendering surface to test. (b) the least surface. (c) more code and a build step. | (a) |
| OD-23 | What happens to the uploaded copy | (a) Deleted when the run ends. (b) Kept beside the run folder. | (a) nothing but the run folder remains; the evidence still traces to the document by its hash and page. (b) lets a run be repeated, and holds a copy of the document. | (a) |
| OD-24 | Which endpoints | (a) The five of section 3.2. (b) Also delete and re-run. | (b) breaks "a run folder is never modified". | (a) |
| OD-25 | The values of the new limits | A pair of numbers for `max_concurrent_runs` and `max_queued_runs`, and a `run_timeout_seconds`. | Memory scales with concurrency (section 3.10); a timeout shorter than a slow model call fails honest runs. | Yours to set, as for the parse limits; I would bring measured timings first (a run with the fake provider takes a second or two on a small synthetic document, including the report; a real run takes as long as the model calls, which I have not timed for a full document). |
| OD-26 | Option parity with the command line | (a) All options (`basis`, `pages`, `assert_basis`, `profile`, `ocr`, `no_report`, `confirm_public_document`). (b) A smaller set. | OCR is off by default and needs `pages`; a profile is analyst-supplied text. All carry the same rules as the command line. | (a) |

## 7. Order of work if approved (each step on the owner's word)

| Step | What | Size (rough) |
|---|---|---|
| 0 | The PRD draft: new requirements (the API, the web page, upload handling, access control, job limits), their error mapping and examples, the `[api]` settings, the new dependencies, the Section S, L.2 and Phase 6 row updates, a version bump | a document |
| 1 | The service layer: move the wiring out of the command line; the same tests pass; no behaviour change | small |
| 2 | The API core: submission, the run queue and limits, status, the files, the error mapping, the `[api]` settings, the tests | medium |
| 3 | Upload and exposure security: streaming limits, temporary files, the token and the start-up refusal, the send-rule confirmation, response headers, the tests and mutation checks | medium |
| 4 | The web page: the form, the list, the run view, the memo rendering and its policy, the injection tests | medium |
| 5 | README, how to start it, the OpenAPI document checked, an end-to-end test of the whole path | small |

About five to six sessions of the size of the report build. Phase 7 (Docker, deployment, persistence, accounts, the security review) comes after, and the owner's earlier decision to defer it stands unless it is lifted too.

## 8. Risks to settle in the PRD draft

- **Memory under concurrency** (section 3.10): the right `max_concurrent_runs` depends on `parse_memory_mb`; the draft states the relation.
- **A run has no whole-run time limit today**; `run_timeout_seconds` is new behaviour, and the point where a stuck run is stopped (and its folder recorded as failed) needs a rule.
- **The process restarts** (OD-20 (a)): runs in flight are lost; a folder is only ever complete or absent, so nothing half-written is served.
- **Public exposure of a tool whose rule is "public and synthetic documents only"** (SEC-01): the confirmation, the notice and the token are the controls; there is no way for the server to know a document is public.
- **Held-out documents:** an upload that matches a held-out hash is refused, as on the command line; no API path may read or serve anything under `private/`.

## 9. What I need from you

1. Choose on OD-19 to OD-26 (or say "as proposed").
2. Say "draft the Phase 6 PRD change" to start step 0, after which I would bring it for your approval before building.
