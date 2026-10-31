# Phase 7 security review against Section M (developer review) — for the owner's review

| Item | Value |
|---|---|
| Status | **Written 2026-10-31 against PRD v0.4.66 and commit `9cb72d7`. Owner decisions recorded 2026-10-31:** F-10 (the lock-out line names the client address) stays; SEC-15 (b) (one shared token, OD-34 (a)) and (c) (a token holder reads every run) stay as accepted limits, to be revisited at a real deployment decision (OD-28). The review is otherwise a draft: the tool runs and the owner's steps in section 6 are not done, and Phase 7 is not finished. |
| Kind of review | **A developer review by the person who wrote the code. It is not an independent review** (OD-39: options (a) and (b) chosen, (c) not supplied). It finds what I thought to look for. |
| Method | (a) Each requirement of Section M, and each finding F-1 to F-9 of `docs/PHASE7_plan.md` section 3, re-read against the finished code and tests. (b) Tool runs: **not run**; the commands and what I need from you are in section 4. |
| Suite at this point | 5040 passed, 5 skipped (run before the `9cb72d7` commit; that commit changed documents only). |
| What was not done | The image was **not built or run** (Docker is not installed on the development machine). The proxy files were **not run**. No tool in section 4 was run. Nothing here was tested in a browser. |

## 1. The findings of the plan (F-1 to F-9)

"Fixed" means the code or file exists, has tests, and the tests were mutation-checked when written. "Fixed in files" means the same for files that only a build can exercise, so the fix is checked as text and with stand-in commands, **not** by running the image.

| ID | Finding | State | Commit | Evidence | Limit, stated plainly |
|---|---|---|---|---|---|
| F-1 | Child processes inherited the whole environment (key and token) | **Fixed** | `bd65fe8` | `ingestion/child_env.py` (20 names); `tests/unit/test_child_environment.py`; B-337. Every worker, Tesseract and the report worker are started with it. | `HOME` is on the list (the OCR engine and the PDF libraries want it). It holds no secret by itself, but a deployment must not put one in a file under it. |
| F-2 | A container build would copy `.env`, `private/`, runs, cache, PDFs | **Fixed in files** | `f152357` | `.dockerignore` allows named paths only; the Dockerfile copies named paths, never `COPY .`; `tests/unit/test_container_files.py` (109) fails if `.env`, `private/`, `*.pdf`, `runs/` or `.cache/` could enter the context; B-338. | Read as text. No build was made, so no image was inspected. |
| F-3 | A wheel would not find prompts, rules, send-rule record | **Fixed in files** (OD-29 (a): the source tree is in the image at `/app`) | `f152357` | Dockerfile test and B-338. | Not run in an image. |
| F-4 | The resident-memory check failed open without `ps`; a small container limit would kill everything | **Fixed** (check) and **fixed in files** (sizing) | `bd65fe8`, `f152357` | `/proc` reading, fail closed after 3 unreadable checks, launcher self-check (`test_memory_reading.py`); `api/sizing.py` refuses to start below `max_concurrent × parse_memory_mb + uploads + 1,536 MB` (8,180 MB with the shipped values; `test_container_sizing.py`). | `/proc` reading is tested against stand-in files on macOS; **it has not been run on Linux**. The sizing figure is a rule, not a measurement inside a container (criterion 12 is yours). |
| F-5 | Uploads read to the end before the queue was asked; stalled uploads held connections | **Fixed** | `bd65fe8` | Place reserved before the first byte (`JobManager.reserve/release`); 30 s idle → `408`; `test_api_capacity.py`; B-337. | A trickle of 1 byte every 29 s still holds a place until the run limit or the proxy cuts it. The proxy's own timeouts (OD-37 (c)) are the second control and are **not run**. |
| F-6 | A restart loses queued and running runs, caller sees `404` | **Fixed** | `b686214` | `.pending/<run_id>.json` before `202`; `recover_interrupted` → `E-RUN-INTERRUPTED`; `test_api_pending.py`, `test_pending.py`; B-339. | A run interrupted is recorded as failed, never resumed. Exactly one server process is still required (compose sets it; a second worker would split the in-memory state). |
| F-7 | Run folders, cache and uploads kept indefinitely | **Fixed** (command) / **runbook requirement** (encryption) | `b686214` | `prune --older-than DAYS [--dry-run]`; whole run folders, `.partial` staging folders, cache entries, upload directories; `test_retention.py`. | Nothing runs `prune` by itself; the operator or a scheduler must. Encryption at rest is a deployment requirement the service cannot check (SEC-18). |
| F-8 | The commit was recorded as unknown inside an image | **Fixed** | `bd65fe8`, `f152357` | `CREDIT_INTEL_BUILD_COMMIT` fallback (`test_build_commit.py`); the build refuses a missing or non-commit argument. | The build guard is read as text; not run. |
| F-9 | Results across platforms (Mac against Linux image) | **Open** | — | The tests that would answer it (golden and reproducibility tests inside the image, with the OCR engine version recorded) are the default command of the Dockerfile's `test` stage (`deploy/build.sh test`), read as text; **never executed**. | **Not shown.** Same inputs and outputs are promised within one environment only. This is the owner's run (section 6). |

## 2. The requirements of Section M

| ID | Requirement | Reachable from outside: state | Evidence | Limit |
|---|---|---|---|---|
| SEC-01 | Public and synthetic data only | **Weaker, no technical control** | The notice and confirmation (B-334). | The confirmation is the caller's word. Only known callers (OD-34 (a)); the runbook says so. |
| SEC-02 | Keys from environment, never logged | Holds; F-1 fixed | `test_child_environment.py`; token never in a response or log (`test_api_security.py`). | `HOME` on the child list (F-1). Environment variables are visible to anyone who can inspect the container (OD-31 (a)). |
| SEC-03 | `.env` out of Git and of the image | Holds in files | F-2. | Not built. |
| SEC-04 | Type and size validation | Holds | Signature at the first bytes, size while streaming (`test_api.py`). | — |
| SEC-05 | Safe errors | Holds | Fixed transport bodies; 24 catalogue codes each through the API (`test_api_catalogue.py`). | — |
| SEC-06 | No execution of document content | Holds; blast radius reduced | F-1; image: non-root 10001, read-only root, `cap_drop`, `no-new-privileges` (`compose.yaml`, `test_container_files.py`). | Hardening is read as text. **Read-only root file system was never exercised**; a write the code makes outside `/data` and the tmpfs would show only when the container runs. No egress restriction (OD-38 (a)): a compromised parser can still reach the network. |
| SEC-07 | Prompt-injection containment | Holds | Unchanged. | — |
| SEC-08 | No document text in logs | Holds | Log is method, path shape and status; run ID and state. | **New, F-10 below:** a lock-out warning names the client address. |
| SEC-09 | Drafts only | Holds | — | — |
| SEC-10 | Send rule | Holds in files (F-3) | The record file is in the image (B-338). | Not run in an image. |
| SEC-11 | Dependency hygiene | **Partly** | Base image by digest (build refuses without one), `uv sync --frozen`, uv pinned 0.12.6, image tagged with the commit. | **No scan has been run** (section 4). |
| SEC-12 | Parse limits | Holds on Linux by design | F-4. | Not run on Linux. |
| SEC-13 | Untrusted text in the PDF report | Holds | — | — |
| SEC-14 | Uploads | Holds; F-5 fixed | `test_api.py`, `test_api_security.py`, `test_api_capacity.py`; tmpfs for uploads; start-up sweep. | Trickle (F-5). |
| SEC-15 | Access control | **Improved; not fully closed** | Token ≥ 32 chars, constant-time check; refusal to start off loopback without token **and** one of two statements (`behind_tls`, `loopback_only_publication`); 5 wrong credentials in 300 s lock the client address for 900 s (`test_api_lockout.py`); `trusted_proxies` and `public_hosts` (`test_client_address.py`, `test_api_proxy.py` 30, `test_api_settings.py` 114); rotation procedure (runbook 5a). | (b) **One shared secret remains**: no attribution, no revoking one person (OD-34 (a), your decision; identity-aware proxy once more than one person uses it). (c) **Any token holder lists and reads every run.** (f) **The pages are unusable in a browser with a token set** (decided in Phase 6). The two statements are the operator's word; the service cannot check them. Without `trusted_proxies` behind a proxy, all clients share one lock-out count (a 5-attempt lock then hits everyone). The lock-out is in memory and resets on restart; an attacker with many addresses is not slowed. |
| SEC-16 | Page and file policy | Holds; HSTS with `behind_tls` | Four headers on every response; HSTS `max-age=31536000` only with `behind_tls`, no `includeSubDomains`. | A year-long HSTS cannot be undone quickly if a domain is later served without TLS. |
| SEC-17 | Container hardening | **Fixed in files, never run** | Dockerfile, `compose.yaml`, `test_container_files.py`. | The whole of it. |
| SEC-18 | Data at rest, retention | **Partly** | `prune` (F-7). | Encryption is a requirement on the operator. |
| NFR-10 | Capacity | Rule only | `api/sizing.py`; OD-25 values 1 / 4 / 1,200. | **Not measured inside a container's memory limit** (criterion 12, yours). |

## 3. New findings from this re-read (not in the plan)

| ID | Finding | Action |
|---|---|---|
| F-10 | The plan said the service logs no client address (SEC-08 row). Step 4 added a `WARNING` that names the address when it is locked out (`api/security.py`, tested: `test_the_lock_is_logged_with_the_address_and_never_with_what_was_guessed`). | **Accepted by the owner, 2026-10-31, with a reason:** an operator who sees a lock-out needs to know whom it concerns; the line holds no document data and nothing the caller presented. Behind a proxy without `trusted_proxies` it names the proxy. Say if you prefer the address left out. |
| F-11 | The four Caddy and Compose facts are recalled, not read from documentation or run (FR-018 criterion 11). | **Open, yours:** runbook section 8 gives each a command and what to see. If any is false the proxy file or the Compose file needs a correction and its test changes. |
| F-12 | Proxy `request_body max_size 110MB` against the service's own limit: the proxy limit is only a first line. | Covered by the 105 MB / 115 MB check in section 8 of the runbook. Not run. |

I found nothing else to change. That is weak evidence: it is the same author reading the same code.

## 4. Tool runs (OD-39 (b)) — not run; for your machine

SEC-11 requires each tool to have a documented reason, and a new development dependency needs your word (`uv add --dev`) — **I have added none and run none.** Nothing needs network access from me. Command forms below are from memory, not checked against each tool's current documentation; correct them if a tool says otherwise.

| Tool | Reason | What it checks | Form (unverified) |
|---|---|---|---|
| pip-audit | Known-vulnerable Python packages in `uv.lock` | Locked runtime set against the PyPI advisory database | `uv export --frozen --no-dev --no-hashes > req.txt`, then `uvx pip-audit -r req.txt` |
| bandit | Insecure Python patterns (shell use, `eval`, temp files, asserts for control) | `src/` | `uvx bandit -r src -q` |
| trivy (or grype) | Known-vulnerable packages and OS layers in the built image, secrets in layers | The image from `deploy/build.sh` | `trivy image <tag>` |

**What I need from you:** run them, paste the output (counts and finding titles are enough), and I will put each finding into this table as fixed, accepted with a reason, or deferred by you. A finding in a package I cannot upgrade is yours to accept or reject.

## 5. What this review does not show

- Nothing about a built or running image: user, read-only root, capabilities, `/proc` reading, memory limit, health check, Tesseract version.
- Nothing about the proxy or TLS: the four recalled facts, certificate issue, HSTS in a browser.
- No test under load, no penetration test, no browser test, no test of any hosting platform.
- It was written by the author of the code (OD-39).

## 6. What is left before Phase 7 is finished (all yours unless stated)

1. Build the image (`deploy/build.sh`), start it, confirm user 10001, read-only root, `/health`.
2. Run the golden and reproducibility tests in the image; record the OCR engine version (F-9).
3. Run the section 8 checks of the runbook (the four recalled facts, F-11).
4. Repeat the OD-25 measurements inside the container's real memory limit (FR-018 criterion 12).
5. Run the section 4 tools and give me the output.
6. Decide on the open items in section 2 (SEC-15 (b), (c); the F-10 log line).

After 1 to 5 I will update this document and the PRD status cells, and write the Phase 7 exit summary. The expanded evaluation is row 7b, not started.
