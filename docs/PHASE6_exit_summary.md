# Phase 6 exit summary (offline), against Section Q of the PRD — for the owner's review

| Item | Value |
|---|---|
| Status | **Approved by the project owner on 2026-10-30** (PRD v0.4.61). Built and tested offline; the owner confirmed the three build decisions (section 3), had the criterion-5 gap closed, accepted the no-load-measurement and no-browser-test items as documented limitations, and ran one live submission through the service (section 5). |
| Written | 2026-10-30 |
| PRD | v0.4.60 (specification v0.4.59, status v0.4.60) |
| Commits | `671071c` service layer, `0ddc84d` API core, `d411bb7` access control and headers, `93164d6` web page, `e6dd3a4` README and end-to-end tests, `3ca77f4` PRD status |
| Suite | 4611 passed, 5 skipped (4350 passed before Phase 6 began) |
| Size | about 1,270 lines of source and static files; about 260 new tests (below) |

## 1. The Phase 6 row, criterion by criterion

The row (Section Q, as updated in v0.4.59): *The five endpoints work for submission, status and every file. The same pipeline is reused and the API's files equal the command line's. Every catalogued code has an HTTP mapping and a test. The controls of SEC-14 to SEC-16 are tested. The `[api]` limits are enforced. No new behaviour bypasses the evidence and labelling rules. Phase 7 is not changed and stays deferred.*

| # | Criterion | State | Evidence | Limit, stated plainly |
|---|---|---|---|---|
| 1 | The five endpoints work for submission, status and every file | **Met** | `test_api.py` (64), `test_api_end_to_end.py` (7, real sockets), B-332, B-335 | Run with the fake model provider only. No run has gone through the service with the real model. |
| 2 | The same pipeline is reused | **Met** | `service.execute_run` is the one function the command line and the API call (`test_service.py`, 10); the earlier suite passed unchanged apart from five places that patched names that moved | — |
| 3 | The API's files equal the command line's | **Met for `memo.md` and `results.json`** | `test_api.py` and `test_api_end_to_end.py` compare both byte for byte against a command-line run of the same input | `manifest.json` and `report.pdf` carry run IDs and times and were not compared byte for byte; the report is built by the same code from the same memo and results. |
| 4 | Every catalogued code has an HTTP mapping | **Met** | `test_every_catalogued_code_has_an_http_mapping_and_the_status_follows_it` (all 23 codes; a code with no row fails the suite) | — |
| 5 | …and a test | **Met** (gap closed 2026-10-30, at the owner's request) | `test_api_catalogue.py` (25 tests): one scenario through the application for each of the 23 codes (a test fails if a code has none). Eight codes raised in the request answer with the status of the PRD's table and a fixed `{code, message}` body and make no run and no upload residue; sixteen raised inside a run (`E-INPUT-PAGE-RANGE` appears in both groups, for a malformed range and for a range outside the document) leave the request `202` and show in the run's status with the catalogue's message, and the folder holds only the failure record with the right final state, code and stage. `E-INPUT-NOT-FOUND` is provoked by deleting a queued run's upload, and `E-EXPORT-FAILED` by a service that has forgotten an earlier run of the same document at the same moment; the earlier folder is left whole. | **One mismatch with the PRD text, found by the test:** `E-INPUT-NOT-FOUND` is never raised in the request (the server hashes the file as it streams it); it appears only in a run's status. The mapping table of the code lists `500` for it, as a defence, and FR-016 criterion 5 says the same; the PRD wording would be corrected on your word. |
| 6 | The controls of SEC-14 to SEC-16 are tested | **Met** | SEC-14: streaming size limit (header and mid-stream), signature at first bytes, safe name, private directory, removal on success, failure, refusal, disconnect and shutdown (`test_api.py`, `test_api_security.py`). SEC-15: token (missing, wrong, right, in URL/form/cookie, constant-time, never in a response or log), refusal to start on a public address without a token, short token, launcher exit code. SEC-16: the four headers on every response, the memo as text, no inline script or style, the script run under Node. | See section 3: the pages cannot be used with a token set. |
| 7 | The `[api]` limits are enforced | **Met** | Pool of one with a gate (two runs never at once), queue of one (`429` with `Retry-After`), `E-RUN-TIMEOUT` with a stalled stage (`test_api.py`); required settings, absolute folders, bounds (`test_api_settings.py`, 49) | **The time limit is cooperative** (named in FR-016 criterion 10a and Section R): a run can end later than the limit and holds its slot until it does. Memory under the approved 1 / 4 / 1,200 was measured for the pipeline (`docs/OD-25_run_timing_2026-10-30.md`), not for the service. |
| 8 | No new behaviour bypasses the evidence and labelling rules | **Met** | The API and the page call the unchanged pipeline and serve its files; no memo, label or number is produced in `api/`; the memo on the page has every label of `memo.md` in place and none added (`test_api_pages.py`) | — |
| 9 | Phase 7 not changed | **Met** | No Docker, deployment, persistence, accounts or TLS was added | — |

## 2. What was built

- **`service.py`:** `execute_run`, `record_failure`, `check_send_rule`; the command line now calls it. No change in behaviour.
- **`api/`:** `app.py` (five endpoints, shared by the page), `jobs.py` (bounded pool, in-memory state, cooperative deadline), `uploads.py` (streaming multipart reader), `security.py` (token, origin check, headers, request log), `errors.py` (HTTP mapping), `pages.py` and `static/` (the page), `__main__.py` (the launcher, also `credit-intel-api`).
- **Settings and catalogue:** the `[api]` table (1 / 4 / 1,200; folders required and absolute), `CREDIT_INTEL_API_TOKEN`, and the 22nd and 23rd catalogue codes, which have no exit code.
- **New dependencies** (reason: FR-016, licences read from package metadata): fastapi (MIT), uvicorn (BSD-3-Clause), python-multipart (Apache-2.0), httpx (BSD-3-Clause, dev only).

## 3. Decisions taken in the build (all three confirmed by the owner on 2026-10-30)

Three things are in the code and the PRD status notes that were **not in v0.4.59**. **The owner confirmed all three as built on 2026-10-30.**

1. **Client file name.** It is reduced to a safe base name and used as the name of the file inside the random private directory, so that the manifest records it as the command line does. SEC-14 says it is "never used as a path"; I read that as "never joined to a path the client controls". The alternative is a name override carried through `run_pipeline` and ingestion.
2. **Cross-origin `POST`.** A `POST` whose `Origin` names another host is refused with `403`. Without it, a form on any website open in your browser could start a paid run on a loopback service that has no token.
3. **The pages with a token set.** A browser cannot send a bearer header, so with a token set the pages answer `401`. **Decided by the owner, 2026-10-30: keep as is.** The page is for the loopback default or behind a reverse proxy that adds the header. A cookie login would be a second authentication mechanism outside SEC-15 and needs its own proposal if it is ever wanted.

Smaller choices are listed in the PROGRESS entries for steps 2 to 4 (the run ID fixed at upload completion, the transport answers with `"code": null`, `memo_generated` shown until the files are written, a duplicate submission refused, the profile as a JSON text area, the docs pages switched off).

## 4. How it was checked

| Group | Tests | Notes |
|---|---|---|
| Service layer | 10 | Same files as the command line; works from explicit folders; prints nothing |
| API core | 64 | Every endpoint, every refusal, the pool, the queue, the deadline, cleanup |
| `[api]` settings | 49 | Required, absolute, bounds, environment overrides |
| Access control and headers | 59 | Token, start-up refusal, origin, headers, logging, disconnect, launcher |
| Web page | 33 | Form, list, run view, hostile text, no inline script or style |
| The page's script | 8 | Run under Node; skipped where Node is not installed |
| End to end | 7 | Real uvicorn on `127.0.0.1`; the launcher as a separate process |
| Every code through the API | 25 | One scenario per catalogued code; status, body, folder and upload residue |
| README | 4 (added) | The README matches the application |

Mutation checks were run on the guards of each step (about 100 mutants of the upload reader, the pool and deadline, the token, origin and headers, the settings loader, the page and its script). Every one was caught after tests were added for the survivors, except two equivalent mutants in the page (removing either raw-HTML rule alone, which the other rule and `html: False` cover). A wheel built from the tree holds the page's files.

## 5. What has not been done

- **One live submission, run by the owner on 2026-10-30, succeeded.** Run `20261030T153537.172558Z-a2b9acdf`: the real model (`gpt-4o-mini`), one call of 3,805 input and 992 output tokens, no retry, 66 seconds end to end, all four files exported (`report.pdf` 83,501 bytes), no problem with the deadline or the pool under real latency. These are the owner's figures; the manifest was not pasted into this repository. At the list prices used earlier the call cost about USD 0.0012 (calculated here, not read from the manifest), so spend is about USD 0.037 of the USD 0.15 cap. One run is a single observation, not a load or accuracy measurement.
- **No measurement of the service under load.** The 1 / 4 / 1,200 values come from pipeline measurements (OD-25). Memory of the whole service process with a queue was not measured.
- **No browser test.** The page was checked by reading its HTML, by parsing it, and by running its script under Node. It has not been opened in a browser.
- **Phase 7** (Docker, deployment, persistence, accounts, TLS, the full security review) is untouched and deferred.

## 6. What I need from you

1. ~~The decision on the pages with a token set, and the two other additions~~ — decided (section 3).
2. ~~Whether to close the gap in criterion 5~~ — closed (above).
3. ~~The live submission~~ — done (section 5).
4. ~~Your approval of Phase 6~~ — given on 2026-10-30.
