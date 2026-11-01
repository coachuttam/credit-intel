# Phase 7 exit summary (security hardening and a container image), against Section Q of the PRD — for the owner's review

| Item | Value |
|---|---|
| Status | **Draft for the owner's approval.** Not approved. Written 2026-11-01 against PRD v0.4.67 and commit `742dd2e`. |
| Scope | The Phase 7 row as narrowed on 2026-10-30 (PRD v0.4.62): hardening, a container image and a compose file; no standing demo (OD-28). The expanded evaluation is row 7b and **was not started**. |
| Commits | Plan `7eea165`; step 1 `bd65fe8`; PRD v0.4.62 `d9e782c`; step 2 `f152357` (status `379bcd7`); step 3 `b686214` (`a0e2c1e`); step 4 `f6dd1d2` (`d40a86f`); step 5 `c3c4427` (`9cb72d7`); review `8c20f91`; fixes from the first runs in the image `938df2f`, `076331a`, `5f719fb`; Pillow, pip and the measurement note `8b743bc`; SEC-11 `fa24fcf`; PRD v0.4.67 `742dd2e` |
| Suite | 5043 passed, 5 skipped on the development machine (4611 at the end of Phase 6). In the test image: 263 passed, 3 skipped (the owner's run on `8b743bc`). |

## 1. The Phase 7 row, item by item

The row's exit (Section Q): *The Section M review is written as an evidence table: each finding fixed and tested, accepted with a reason, or deferred by the owner. FR-018 is shown in the built image by the owner. The OD-25 measurements are repeated inside the container's real memory limit and the shipped limits adjusted if they do not hold (criterion 12). Marker files and `E-RUN-INTERRUPTED`, `prune`, the token hardening and the proxy settings with the start-up rule are built and tested. No change to extraction, validation, evidence, calculation, rules, labelling or the memo and report text.*

| # | Item | State | Evidence | Limit, stated plainly |
|---|---|---|---|---|
| 1 | The Section M review as an evidence table | **Met, as a developer review** | `docs/PHASE7_security_review.md`: F-1 to F-15, every SEC row and NFR-10, tool results. | Written by the author of the code (OD-39); F-13, which broke the product, was in the code throughout my own review and was found by the owner's first real run. |
| 2 | FR-018 shown in the built image by the owner | **Met for what was run** | The owner built both images, ran the test image (263 passed, 3 skipped), ran one real document through the product image to `exported`, and on `8b743bc` confirmed `docker compose ps` healthy and `id` = uid 10001 (`app`). | See section 3: the read-only root, the proxy and a few image checks are not independently confirmed. |
| 3 | OD-25 repeated inside the container's memory limit (criterion 12) | **Met for the case measured** | 369-page document, 9 GB limit, 113 s, 2,601 MB peak, no kernel memory event; shipped limits stand (`docs/OD-25_container_measurement_2026-11-01.md`). | One document, one submission. The full queue, the `429` path, OCR through the container and a slower-designed document were not measured. |
| 4 | Marker files and `E-RUN-INTERRUPTED` | **Met** | B-339; `test_api_pending.py`, `test_pending.py`. | A run interrupted is recorded as failed, never resumed. |
| 5 | `prune` | **Met** | B-339; `test_retention.py`. | Nothing runs it by itself. |
| 6 | Token hardening | **Met** | B-340; `test_api_lockout.py`; runbook 5a. | One shared secret (OD-34 (a)); the lock-out is in memory and per client address. |
| 7 | Proxy settings with the start-up rule | **Built and tested as code; the proxy itself was not run** | B-341; `test_api_settings.py`, `test_api_proxy.py`, `test_client_address.py`. | `compose.proxy.yaml` and `deploy/Caddyfile` are written and statically tested only. The four recalled facts of runbook section 8 (`!reset`, `admin off`, `request_body max_size`, Caddy replacing a client's `X-Forwarded-For`) and the body-limit check are **not run** (F-11, F-12). |
| 8 | No change to extraction, validation, evidence, calculation, rules, labelling, memo or report text | **Met** | Golden, reproducibility and fresh-process tests pass unchanged on the development machine and in the image. | The only existing tests changed were deliberate and are listed in PROGRESS (memory reader fail-closed, child-environment and stub-variable fixtures, 24 catalogue codes, public-host launcher tests, `proxy_headers=False`). |

## 2. What Phase 7 built

- **Hardening (step 1):** a minimal environment for every child process that reads a document (F-1); resident memory read from `/proc`, failing closed (F-4); the build commit in the manifest (F-8); an upload's place reserved before the body is read, and idle uploads ended (F-5).
- **Image (step 2):** `Dockerfile` (base by digest, pinned uv, non-root 10001, one process), `.dockerignore`, `compose.yaml` (read-only root, no capabilities, `no-new-privileges`, tmpfs for uploads, loopback publication, `init`), build and measure scripts, the runbook, and a start-up refusal if the container's memory cannot hold the pool, the uploads and the server.
- **Persistence and retention (step 3):** marker files, `E-RUN-INTERRUPTED`, the sweep of orphaned uploads, `prune`.
- **Token (step 4):** the failed-attempt lock-out and the rotation procedure.
- **Proxy and TLS (step 5):** `behind_tls`, `loopback_only_publication` (two separate statements, as you ordered), `public_hosts`, `trusted_proxies`, the start-up rule, address trust, HSTS, and the proxy compose files.
- **Fixes the first runs forced:** the test command (`,exec`, `--init`); the package made importable to `python -I` workers in both environments (F-13); Pillow 13.0.0 and pip removed from the product image (F-15).

## 3. What was not shown or not done

- **Read-only root file system.** It is set in `compose.yaml` (`read_only: true`), not in the Dockerfile, and its runtime effect was the thing the runbook said nobody had tested. The service ran a real document to export under the compose settings, which is good evidence that nothing the service needs writes outside `/data` and `/tmp`; but the setting itself was **not read back** from the running container. A one-line check closes it: `docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' <container>` should print `true`, and `docker compose exec credit-intel sh -c 'touch /x'` should fail. I have marked it as not independently confirmed, not as met.
- **The proxy and TLS** (F-11, F-12): written, not run. By your decision these are skipped for now, since OD-28 plans no standing demo. They are not hidden: criterion 11 stays "written and statically tested, not run" in the PRD, and the proxy must not be used before the runbook section 8 checks are done.
- **Not measured:** the full queue and the `429` path inside the container, OCR through the container, load, a browser test, any hosting platform.
- **Limits that remain (accepted by the owner):** one shared token, any token holder reads every run (SEC-15 (b), (c)); the pages are unusable in a browser with a token set; the lock-out line logs the client address (F-10); a slow-trickle upload can hold a place; HSTS is year-long without `includeSubDomains`; the 353 base-image findings with no upstream fix, one critical (libxml2), revisited at the next digest bump; `HOME` is on the child-environment list; encryption at rest is a requirement on the operator.
- **Expanded evaluation (row 7b)** is not started. It needs documents the owner assigns and money, and S3 and the OD-17 labels remain untouched.

## 4. Mistakes of mine that the record should keep

- Step 1 was built before the PRD text for it existed (disclosed in v0.4.62).
- The first sizing check left out the tmpfs uploads; you caught it (v0.4.63).
- The first compose file stated `behind_tls` for a loopback-only publication, a false statement; you caught it and the separate setting was added.
- My `076331a` fixed the importability for the test environment only, so the tests went green and the product still could not parse a document (F-13). The in-image test stage is not the product environment, so a green test image is not a working product.

## 5. What I need from you

1. Your approval of Phase 7, or the items you want closed first (the read-only root read-back is one command; the proxy checks are yours to schedule or defer).
2. Whether to record the read-only root read-back in a v0.4.68 status note when you have it.
3. What comes next: row 7b (the expanded evaluation), which needs your document assignments and a spending decision; or a stop here.
