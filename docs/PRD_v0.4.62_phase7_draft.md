# PRD v0.4.62 draft: Phase 7, deployment and security (specification only)

| Item | Value |
|---|---|
| Status | **Applied as v0.4.62 on 2026-10-30** (the owner: "Disclosure: apply as written. Keep bd65fe8 as built, PRD catches up to match it."; OD-32, OD-34, OD-35, OD-40 "as proposed"; **OD-28 changed:** image and compose only, no standing demo, with the OD-25 measurements repeated inside the container's real memory limit before Phase 7 is done). This file is the record of the draft; where it differs from `docs/PRD.md`, the PRD (0.4.62) governs. The text below is the draft as it stood: section 2.1 recommended option A **and** C for a demo; the owner chose A only. **Nothing of this draft is built except step 1 (section 0).** |
| Drafted | 2026-10-30 |
| Source | `docs/PHASE7_plan.md` (committed `7eea165`); the owner's answers of 2026-10-30: "as proposed on all of OD-27 to OD-39, start step 1"; then "write the Phase 7 PRD draft now … real options with trade-offs" for OD-28, OD-32, OD-34, OD-35 and a retention/cleanup decision. |
| Version | 0.4.62 |
| Kind | New requirements (a deployment image; data at rest), changes to SEC-02, -03, -06, -11, -12, -14, -15, -16, FR-001, FR-012, FR-016, G.1, and settings; one new catalogue code if OD-32 (b). **No change** to extraction, validation, evidence, calculation, rules, labelling, the memo or the report. |

## 0. Disclosure: step 1 was built and committed before this draft existed

The usual order in this project is: the owner approves a PRD change, then the code follows (Phase 6 went that way). **Phase 7 step 1 did not.** The facts:

- `docs/PHASE7_plan.md` said that step 1 "could also start earlier, on its own word, since it does not depend on any decision". The owner then wrote "as proposed on all of OD-27 to OD-39, start step 1". I built it and, on the owner's "commit it", committed it as **`bd65fe8`** (suite 4663 passed, 5 skipped). The PRD text for it did not exist, and still does not: **`docs/PRD.md` at 0.4.61 describes behaviour that the code no longer has, in the places listed below.** That is a gap I should have raised before building, and did not; I raised it only in the report after the build ("the PRD text for these changes is not written yet").
- What step 1 built, and where the PRD is now out of date or silent:

| Built in `bd65fe8` | PRD place that is now stale or silent | This draft |
|---|---|---|
| **F-1.** Every process that reads a document (parse worker, page-render worker, Tesseract, report worker) starts with only 20 listed environment variables (`ingestion/child_env.py`). | SEC-02 says keys are never logged or written; it says nothing about child processes. | SEC-02, SEC-06 (section 3.2) |
| **F-4.** Resident memory is read from `/proc` on Linux and from `ps` elsewhere. A worker that is running but cannot be measured in 3 checks in a row is stopped with `E-INPUT-PARSE-LIMIT` (detail: "memory could not be measured; the run was stopped"). `credit-intel-api` refuses to start on a host where its own process cannot be measured (exit 6). | SEC-12 says the parent "watches the worker's resident memory"; G.1 says `E-INPUT-PARSE-LIMIT` is "the time limit or the memory limit". Neither says what happens when the memory cannot be read, and the third reason is new. | SEC-12, G.1 (3.2, 3.4) |
| **F-8.** When the code is not a git checkout, the manifest's commit comes from `CREDIT_INTEL_BUILD_COMMIT` (a full lower-case SHA-1), the tree state is unknown. | FR-012 criterion 1 lists the code version without saying where it comes from. | FR-012 (3.3) |
| **F-5 / OD-37.** A place is held before the body of an upload is read; a full service answers `429` without reading the file, a closing one `503`; uploads arriving count against `max_concurrent_runs + max_queued_runs`; an upload quiet for 30 seconds (a fixed value) is cancelled with `408`. | FR-016 criterion 4 and the v0.4.60 status note ("the checks run in this order: the upload is received, then …") are stale: the place is taken first. SEC-14 does not mention the idle time or the early refusal. `408` is not in the answers listed. | FR-016, SEC-14 (3.2, 3.3) |

- **Existing tests I changed, deliberately:** in `tests/unit/test_parse_limits.py` the test that said a memory reader that cannot read "does not stop the worker" was replaced by its opposite (fail closed) and a second test added; in `tests/unit/test_parse_limits_engine.py` the test that said the whole environment given to the supervised engine reaches it now says only listed variables do; the Tesseract and engine-watch tests that configure their stub through `STUB_*` variables now ask (`engine_stub_variables` in `tests/conftest.py`) for those names to pass the list. The README gained one sentence. None of these tests expressed a requirement in the PRD text.
- **Residual risks in what was built:** an upload that sends a byte every 29 seconds still holds a place (no total upload time); `HOME` is on the list of inherited variables; the start-up check is in the launcher only, so the command line fails closed at run time instead.
- **If the owner rejects any part:** each of the four is in separate files and separable (`child_env.py` and five call sites; `sandbox.py`'s memory functions and the launcher check; `manifest.py`; `jobs.py`, `uploads.py`, `app.py`). Reverting `bd65fe8` removes all four; a partial revert is a small job. Approving this draft is what makes the PRD say what the code does.

## 1. What is decided and what is reopened

The owner answered "as proposed" on OD-27 to OD-39 on 2026-10-30. This draft keeps those answers for eight of them and **reopens five**, because the owner asked to see real options (section 2). OD-33 (retention) is **withdrawn and replaced by OD-40**, which adds the points the plan did not: nothing is encrypted at rest, the response cache holds page quotes, and an orphaned upload can outlive a crash.

| OD | Subject | State |
|---|---|---|
| OD-27 | Expanded evaluation | **Decided (a): out of Phase 7.** The Phase 7 row of Section Q is split so that evaluation is its own later item. |
| OD-29 | How the image finds its files | **Decided (a):** the source tree is copied into the image and run from it; the send-rule record is included; the image is never pushed to a public registry. |
| OD-30 | Tesseract in the image | **Decided (a):** included, with the English data. |
| OD-31 | Settings and secrets | **Decided (a):** a read-only mounted `settings.toml`; the two secrets as environment variables from the platform or a root-only env file outside the repository; no `_FILE` variants. |
| OD-36 | Behaviour behind a proxy | **Decided (a):** settings `api.behind_tls`, `api.public_hosts`, `api.trusted_proxies` (3.5). |
| OD-37 | Upload capacity | **Decided (c) and built** (section 0). |
| OD-38 | Outbound network | **Decided (a):** no restriction; documented. |
| OD-39 | Review method | **Decided (a) and (b):** a written review and tool runs on the owner's machine; it is a developer review, not an independent one. |
| **OD-28** | Deployment target | **Reopened (2.1)** |
| **OD-32** | Persistence | **Reopened (2.2)** |
| **OD-34** | Authentication | **Reopened (2.3)** |
| **OD-35** | TLS | **Reopened (2.4)** |
| **OD-40** | Retention, cleanup and data at rest | **New, replaces OD-33 (2.5)** |

## 2. The open decisions, with real options

For each: what the facts are, the options with what each costs and risks, how it links to the others, and my proposal. A proposal is marked as such; none is applied.

### 2.1 OD-28 — Deployment target (and whether to deploy at all)

**Facts.** The PRD says only "optional cloud demo deployed with secrets managed securely". The service spends model money, parses hostile PDFs and holds one shared token. The limits 1 / 4 / 1,200 were measured for a machine with 8 GB. Docker is not installed on the machine I work on, so any option needs the owner to build and run. Docker on a Mac runs Linux containers inside a virtual machine with its **own** memory allowance, which is less than the Mac's 8 GB; the OD-25 numbers were for processes on the host.

| Option | What it is | For | Against and risks | What it needs from the owner |
|---|---|---|---|---|
| **A. Image and compose file only** | The deliverable is the Dockerfile, the compose file and a runbook; no hosting is chosen. | Nothing is exposed; no cost; every other decision still applies; the image can be tested on the owner's Mac. | The exit criterion "optional cloud demo" is not met (it is optional). Memory behaviour is tested on a Mac VM, not on the target. | Docker on a machine of theirs. |
| **B. The owner's own always-on machine, private network** | Compose on a machine the owner already has, reached through a VPN or tunnel that signs people in. | No cloud account; no hosting bill; small attack surface. | A laptop sleeps and is also the development machine; Docker's VM memory limit (above); availability is the owner's. | A machine that stays on; a VPN client on each device that uses it. |
| **C. One cloud VM (Linux), private network only** | A small Linux VM with Docker and compose; reachable only through a VPN or tunnel; no public port. | Always on; native Linux (no VM layer), which also gives the Linux run needed to show results across platforms (finding F-9); small attack surface; sizing is exact (8 GB). | A recurring bill I have not priced; an account to secure; **operating system patching, backups and disk encryption are the owner's**; a VPN to run. | A provider, a rough monthly budget, and who patches it. |
| **D. The same VM, public internet** | Reverse proxy with a public certificate, the token as the only gate. | Anyone with the link and the token can use it from anywhere. | The highest exposure: spends model money, parses hostile files, one leaked token is the whole defence, no attribution (OD-34). Every finding of section 3 of the plan applies at full weight. | Same as C, plus a public name. |
| **E. A managed container service (PaaS)** | The platform runs the image and handles TLS and restarts. | No operating system to patch; managed certificates; easy restarts. | Local disk is usually temporary, so the run folders need a volume or an object store (code changes); front ends often limit the request size (some at 32 MB, against our 100 MB; I have not verified any provider); memory is capped and billed, and a recycled instance loses in-memory runs (OD-32); the parse limit and the platform's own out-of-memory kill interact. | A provider and a budget; acceptance of those limits. |
| **F. Kubernetes** | Orchestrated containers. | Scale and rolling updates. | Far more machinery than one process with in-memory state needs; the service must run as exactly one worker. | — |

**Links.** C and B make OD-34 (a) and OD-35 (d) enough; D and E make OD-34 (c) or stronger and OD-35 (a) or (b) necessary. E changes OD-32 and OD-40.

**Proposal.** **A as the deliverable of the phase, and C for the optional demo if the owner wants one.** D only after OD-34 goes beyond one shared token. E only after the persistence and request-size questions are answered for a named provider. I cannot recommend a provider; I have priced none.

### 2.2 OD-32 — Persistence beyond "memory plus run folders"

**Facts.** Run folders are durable and are the evidence. Job state (queued, running, who is waiting) is in memory. A restart or a crash loses queued and running runs; the caller then gets `404` for a run ID the service gave it. The upload copy sits in a temporary directory that a restart wipes (and the planned read-only image has a `tmpfs` there), so a run cannot be resumed unless uploads move onto the volume, which keeps documents on disk across a crash. The service must run as one process (a second would split the in-memory state). On `SIGTERM` the service cancels queued runs and removes their uploads, and a container's default stop time (10 seconds) is shorter than a run.

| Option | What it is | For | Against and risks | Size |
|---|---|---|---|---|
| **A. None** | Keep as is; document that a restart loses queued and running runs; give the container a stop grace period equal to the run limit so a planned restart lets running runs finish. | No new code or store; honest. | A crash or an out-of-memory kill still gives a caller `404` and no explanation. Fine for one owner who sees the restart; poor for anyone else. | none |
| **B. Marker files** | At acceptance write a small `pending` record on the volume and remove it when the run ends. On start, a leftover record becomes a manifest-only failure `E-RUN-INTERRUPTED` (a 24th catalogue code, API only, no exit code). The caller sees "failed: interrupted". Runs are reported, not resumed. | Removes the confusing `404` without a database; the failure record is the same kind as every other; small. | Not resumed (the upload is gone); a crash between accepting and writing the marker still loses that run (the window is tiny and the order is fixed: marker first, then `202`); one more thing on the volume to keep consistent. | small |
| **C. SQLite on the volume** | A job table (run ID, state, timestamps, error code, submitter). Can re-queue after a restart if uploads are kept on the volume. | Survives restarts; can hold who submitted a run (needed for per-user visibility, OD-34); can resume. | A store to secure, back up and migrate; SQLite must not sit on a network file system; the manifest stays immutable so ownership must live in the table, not in the run folder; keeping uploads on the volume means documents persist across a crash (see OD-40). | medium |
| **D. A database server** | PostgreSQL. | Multi-process, backups, queries. | The largest change; the PRD reserves a database for the Phase 8 RAG assistant; far more than one process needs. | large |

**Links.** C is the natural choice if OD-34 chooses per-user visibility. B is enough if it does not. A is consistent with D-deployment option A or B.

**Proposal.** **B**, with the stop grace period of A included. Take C if OD-34 chooses (c) to (e) with separate visibility. If the owner would rather not add a catalogue code, A with the grace period is acceptable and stated plainly in the runbook.

### 2.3 OD-34 — Authentication beyond one shared token

**Facts.** Today: one bearer token from the environment, compared in constant time, never logged; every holder can list and read every run; no failed-attempt limit; no attribution; rotation needs a restart; a browser cannot use the pages with a token (decided in Phase 6; a cookie login "needs its own proposal"). A token sent over plain HTTP is readable on the path; OD-35 deals with that. SEC-01 (public and synthetic documents only) is enforced only by a confirmation the caller makes; knowing who made it needs identity.

| Option | What it is | Who can use it | For | Against and risks |
|---|---|---|---|---|
| **A. One token, hardened** | Keep the token; add a limit on failed attempts (needs the client address, so `api.trusted_proxies`), a written rotation procedure, and the `408`/`429` guards already built. | One owner or a small group sharing a secret | No new mechanism; right for a private network where the network is the sign-in. | No attribution, no revocation of one person, everyone sees every run, a browser cannot use the pages. A leaked token is a full compromise until restart. |
| **B. Several named tokens** | A file of labelled tokens, stored hashed; the label is logged with each request and each run (in a sidecar, not in the immutable manifest). | A few known people or programs | Attribution; revoking one token; rotation per person; no passwords to handle. | Still one secret per person to hand out; the pages still not usable in a browser; per-user visibility needs the label stored (OD-32 (c)). |
| **C. Delegate to an identity-aware proxy or the private network's login** | The proxy (or VPN with identity) signs people in and passes a trusted user header; the application trusts that header only from `api.trusted_proxies`. | Anyone the identity system knows, including in a browser | Accounts, passwords, multi-factor and revocation live in a system built for it; the pages work; attribution comes free. | The application trusts a header: if it can be reached around the proxy, anyone can claim any identity, so it must listen only to the proxy (compose network) and the start-up rule must say so; adds a component to run and keep patched; the token for programs stays. |
| **D. Accounts built into the application** | Users, hashed passwords, sessions and cookies, CSRF protection, lockout, reset. | Any number of users | Self-contained. | The largest and riskiest item in the plan: password storage, session fixation, CSRF on every form, brute-force limits, reset flows, all new code to review by me alone. You said in Phase 6 that a second mechanism needs its own proposal; this would be one. |
| **E. Sign-in through an external identity provider (OIDC)** | The application redirects to a provider and keeps a session cookie. | Users of that provider | No password storage. | Still sessions, cookies and CSRF; a client secret and a callback to protect; a new dependency; needs a provider. |

**What each does not solve.** None can make SEC-01 true: the server cannot know a document is public. B to E only record who said it was.

**Links.** With OD-28 B or C (private network) option A is enough; with D or E, C or stronger. Per-user visibility of runs (who may read whose) arises only with B to E and is a further decision; sharing everything among known users is acceptable for a demo of public documents.

**Proposal.** **A now**, with the written conditions that make it insufficient: more than one person, a public address, or a need for attribution. At that point **C** (not D). I do not recommend D. If the owner wants attribution without a proxy, **B** is the smallest step.

### 2.4 OD-35 — How TLS is added

**Facts.** The service speaks plain HTTP. The launcher allows a public address with a token and no TLS; nothing refuses that. Section 0's start-up rule (3.5) makes `api.behind_tls` an explicit statement by the operator. That statement **cannot be verified** by the service: an operator who sets it without TLS defeats it.

| Option | What it is | For | Against and risks |
|---|---|---|---|
| **A. Reverse proxy in the compose stack, automatic public certificates** | Caddy or nginx in a second container terminates TLS and talks plain HTTP to the service on a private compose network. | Works anywhere Docker does; automatic issue and renewal; HSTS and request limits at the proxy. | Needs a public name and open ports 80/443 (for the certificate authority's check); another container to patch; a misconfigured proxy that rewrites `Host` breaks the origin check (OD-36). |
| **B. Reverse proxy with certificates the owner supplies** | The same proxy with a certificate from a private authority or a self-signed one. | No public name or open port; fits a private network. | Browsers warn until the authority is trusted on each device; renewal is manual; a private authority is something to protect. |
| **C. The platform's own front end** | A managed load balancer or the PaaS terminates TLS. | Nothing to run. | Only with OD-28 E (or a cloud load balancer in front of a VM); the service must trust forwarded headers from the platform's addresses (OD-36); the platform sees the traffic in clear. |
| **D. A private network that encrypts the path** | A VPN or tunnel (WireGuard-based) carries the traffic; the service listens on the tunnel's interface over plain HTTP. | No certificates; the network is also the sign-in; small surface. | Every user installs a client; only members can reach it; `api.behind_tls` then means "the path is encrypted by the private network". |
| **E. TLS inside the application** | uvicorn with a certificate file. | One fewer container. | Certificate issue and renewal become application operations; the key sits in the application's container; I advise against it. |

**Links.** OD-28 C goes with D (or B); OD-28 D goes with A; OD-28 E goes with C.

**Proposal.** **D for a private demo (OD-28 C), A for anything reached over the internet, never E.** In both cases the start-up rule of 3.5.

### 2.5 OD-40 — Retention, cleanup and data at rest (replaces OD-33)

**Facts.** Every run leaves `memo.md`, `results.json`, `manifest.json` and `report.pdf` in `output_dir`, **indefinitely, as plain files**. They hold figures, quotes and page references from the uploaded document. The response cache (`cache_dir`) holds the model's replies, which also contain quotes and figures from page text, in plain JSON; the cache is also what makes a re-run byte-identical without calling the model (FR-012.2). An upload is deleted when its run ends, but a crash or kill leaves its temporary directory until the machine restarts (or for ever if the temporary directory is on the volume). Container logs carry run IDs and counts, not document text. A backup of the volume copies all of it. There is no delete endpoint (a Phase 6 decision, OD-24) and no clean-up of any kind. **There is a tension to settle:** the project rule is to preserve financial evidence and keep every figure traceable to its source; deleting a run folder ends that traceability for that run. The documents are meant to be public or synthetic (SEC-01), which lowers the confidentiality risk but does not remove it (SEC-01 rests on a confirmation).

Two separate questions: **how long data is kept** (retention) and **whether it is encrypted where it lies** (at rest).

| Retention option | What it is | For | Against and risks |
|---|---|---|---|
| **A. None; operator by hand** | Document where the data is and how to clear it. | Nothing to build; nothing is ever deleted by surprise. | Data grows without bound; nothing makes anyone do it; an orphaned upload stays. |
| **B. A `prune` command** | `python -m credit_intel.api prune --older-than DAYS` removes run folders (and cache entries, and stale upload directories) older than the given days; a dry-run mode lists what it would remove; **no default for DAYS** (like every limit in this project); the operator or a scheduler runs it. | Bounded, explicit, no change to the endpoints; the owner picks the period; also sweeps orphaned uploads. | Someone must schedule it; pruning the cache means an old run can no longer be reproduced without a model call; a pruned run's evidence is gone, by the owner's choice. |
| **C. Automatic retention in the service** | A required setting `api.retention_days` and a background sweeper. | Nothing to remember. | The service deletes evidence on its own timer; a bug deletes the wrong thing; a destructive code path inside a service that is reachable from outside. |
| **D. A delete endpoint** | `DELETE /runs/{id}` for an authorised caller. | Immediate removal on request. | Contradicts OD-24 and "a run folder is never modified" (FR-010.4); a destructive call on the API; needs per-user rights (OD-34) to be safe. |

| At-rest option | What it is | For | Against and risks |
|---|---|---|---|
| **E1. None** | Rely on the host. | Nothing to do. | A stolen disk, a snapshot or a backup exposes everything in clear. |
| **E2. Disk or volume encryption by the operating system or platform** | FileVault, LUKS, or the provider's encrypted disks; a deployment requirement checked at deployment and written in the runbook. | Protects against lost disks and snapshots with no application change; the key stays with the platform. | Protects nothing while the machine is running and mounted; the service cannot check it; depends on the owner's setup. |
| **E3. Encryption by the application** | Encrypt each run file with a key from the environment; decrypt when serving. | Protects files on a mounted disk from other local users. | A key to manage and rotate; `GET /runs/{id}/memo` is no longer the file byte for byte unless decrypted on the way out; the offline report command and the cache change; large, easy to get wrong. |

**Links.** OD-32 (c) with uploads on the volume increases what is on disk. OD-28 E (PaaS) makes E2 the platform's. OD-34 (c) to (e) with separate visibility makes D possible.

**Proposal.** **Retention B and at-rest E2.** The period is the owner's to set; I propose no number. The sweep of stale uploads also runs once at start-up. Not C, D or E3. The runbook states the traceability trade: a pruned run cannot be re-checked against the stored files (the document's SHA-256 in the manifest still identifies the input, if the manifest is kept; **I propose that `prune` removes whole folders only, never part of one**).

## 3. Exact text changes if approved

Text that depends on a reopened decision is marked **[OD-xx]** and is written for my proposal; the alternatives change it as the tables above say.

### 3.1 New requirement FR-018 — Deployment image (Should; specified in v0.4.62; not implemented)

> **Behaviour:** a container image runs `credit-intel-api` with the same pipeline and the same limits, configured from outside, holding no secret and no data.
>
> **Acceptance criteria:**
> 1. **Contents.** A multi-stage build on a base image pinned by digest. The final image holds only: the environment built from `uv.lock` (`--frozen`, no dev dependencies), the package and the source tree it resolves its files from (`prompts/`, `config/`, the send-rule record: D-29), the system packages the pipeline needs, and Tesseract with the English data (OD-30). **Named paths are copied; the build never copies the whole context.**
> 2. **A `.dockerignore`** that allows only what criterion 1 names. A test fails if `.env`, `.env.*`, `private/`, `runs/`, `.cache/`, `*.pdf`, `*.pem`, `*.key` or `secrets/` could enter the build context.
> 3. **Run as a non-root user**; a read-only root file system; a small writable `tmpfs` for uploads; no added capabilities; `no-new-privileges`; one server process (the service keeps run state in memory).
> 4. **Settings and secrets.** `settings.toml` is mounted read-only; `OPENAI_API_KEY` and `CREDIT_INTEL_API_TOKEN` arrive as environment variables from the platform's secret store or a root-only env file outside the repository, never in the image, the compose file or the build arguments. `output_dir` and `cache_dir` are volume mounts.
> 5. **The commit.** The image is built with the commit as a build argument and sets `CREDIT_INTEL_BUILD_COMMIT`; the manifest records it (FR-012 criterion 1).
> 6. **Health.** A health check on `GET /health`.
> 7. **Memory sizing (a requirement, tested).** The container's memory limit is at least `api.max_concurrent_runs` times `ingestion.parse_memory_mb` plus the server's own use (about 1.5 GB for one run, `docs/OD-25_run_timing_2026-10-30.md`). A container started with less ends a run that passes the parse limit with `E-INPUT-PARSE-LIMIT` and does not die with it.
> 8. **Logs** go to standard output with a size limit set in the compose file; they hold what SEC-08 allows and nothing else.
> 9. **Never public.** The image holds the send-rule record (hashes of held-out documents) and is never pushed to a public registry.
> 10. **Shown in the image** (run by the owner, Docker being absent from the development machine): the image builds; it starts as non-root with a read-only root; `/health` answers; one fake-provider run writes the same `memo.md` and `results.json` as the command line; the golden and reproducibility tests pass inside the image; the image contains no `.env`, `private/` or PDF (listed from the built image).
> 11. **Compose.** A compose file runs the service and, **[OD-35]**, an optional reverse proxy on a private network; the service is published to the proxy only. A stop grace period at least as long as `api.run_timeout_seconds` (**[OD-32]**).

### 3.2 Security requirements (Section M)

- **SEC-02** gains: *"Every process that reads a document (the parse worker, the page-render worker, the OCR engine and the report worker) is started with only the environment variables on a fixed list in `ingestion/child_env.py` (the search path, locale, temporary and home folders, the Python path, library paths, `TESSDATA_PREFIX`, `OMP_THREAD_LIMIT`); a key, token, proxy or other credential variable never reaches one, whatever its name (v0.4.62; built in `bd65fe8`)."* **SEC-06** gains a pointer to it.
- **SEC-03** gains: *"A container build copies named paths only and has a `.dockerignore` that keeps the files SEC-03 names, `private/`, run folders, the cache and every PDF out of the build context (FR-018 criterion 2)."*
- **SEC-11** gains: *"An image pins its base by digest, is built from `uv.lock` with `--frozen`, is tagged with the commit, and is scanned with the tools of OD-39 on the owner's machine; each tool has a documented reason."*
- **SEC-12** gains: *"On Linux the resident memory of a worker is read from `/proc`; elsewhere from `ps`. **A worker that is still running and cannot be measured in three checks in a row is stopped and the run ends with `E-INPUT-PARSE-LIMIT`** (the limit fails closed). The service refuses to start on a host where its own resident memory cannot be read (`E-CONFIG-INVALID`, exit 6). A container's memory limit is sized by FR-018 criterion 7. (v0.4.62; built in `bd65fe8`)."*
- **SEC-14** gains: *"A place is held before the first byte of an upload is read: running runs, waiting runs and uploads arriving together never exceed `api.max_concurrent_runs + api.max_queued_runs`, and a full service answers `429` without reading the file. An upload that sends nothing for 30 seconds (a fixed value) is cancelled with `408` and its temporary directory removed. A directory left by a crash is removed at the next start. (v0.4.62; built in `bd65fe8` except the start-up sweep.)"*
- **SEC-15** **[OD-34, OD-35, OD-36]** gains: *"The service starts on a non-loopback address only if a token is set **and** `api.behind_tls` is true, the operator's statement that TLS ends in front of it or that the path is encrypted by a private network. Failed attempts are limited per client address. A `POST` is refused when its `Origin` is not one of `api.public_hosts` (or, with none set, the request's own host). Forwarded headers are trusted only from `api.trusted_proxies`."* The alternatives of OD-34 replace the middle sentence.
- **SEC-16** gains: *"With `api.behind_tls` true the service sends `Strict-Transport-Security`."*
- **SEC-17 (new) Container hardening.** *"FR-018 criteria 3 to 7."*
- **SEC-18 (new) Data at rest and retention [OD-40].** *"Run folders, the response cache and any upload are plain files. A deployment keeps them on an encrypted volume (a requirement of the runbook, not checkable by the service). `prune --older-than DAYS` (DAYS required, no default; `--dry-run`) removes whole run folders, cache entries and stale upload directories older than DAYS, and nothing else. The service never deletes a run on its own."*

### 3.3 Functional requirements

- **FR-016** criterion 4 gains: *"Uploads arriving count against the same two limits (SEC-14)."* Criterion 5 gains the answers `408` (an upload that went quiet) and states that `429` is given before the body is read. The v0.4.60 status note "the checks of criterion 6 run in this order: the upload is received …" is replaced by *"A place is held first (SEC-14), then the upload is received, then …"*. Criterion 10 gains **[OD-32 B]**: *"a run found interrupted at start is recorded as `E-RUN-INTERRUPTED`."*
- **FR-012** criterion 1: the code version is the git commit and tree state when the code is a git checkout, otherwise the commit named by `CREDIT_INTEL_BUILD_COMMIT` (a full lower-case SHA-1) with the tree state unknown, otherwise unknown.
- **FR-001** criterion 10 gains a pointer to the SEC-12 sentence on measurement.

### 3.4 Error catalogue (G.1)

- `E-INPUT-PARSE-LIMIT` meaning: *"Parsing the PDF exceeded the time limit or the memory limit, **or the memory of the parse could not be measured** (SEC-12); the message names which."*
- **[OD-32 B]** one new row, the 24th code: `E-RUN-INTERRUPTED` · stage: any, after `received` · meaning: *the service stopped while the run was queued or running* · what the user should do: *submit the document again* · exit code: none (API only) · retried: No.
- `408` is a transport answer (`{"code": null, "message": fixed}`), not a code, like `429`.

### 3.5 Settings

A new part of the `[api]` table, from OD-36: `behind_tls` (boolean, default `false`), `public_hosts` (a list of host names, default empty), `trusted_proxies` (a list of addresses, default empty). Not limits, so they may default. Rules: a non-loopback `host` needs the token and `behind_tls = true`; `public_hosts` and `trusted_proxies` are checked at start (a malformed entry is `E-CONFIG-INVALID`). Each can be set by `CREDIT_INTEL_API_<NAME>` (a comma-separated list for the two lists). **[OD-34 A]** a failed-attempt limit needs `trusted_proxies` behind a proxy to see the client. No other setting is added; the 30-second idle time is a constant.

### 3.6 Other changes

1. **Section L.2:** the `Docker` row becomes *"Yes, from v0.4.62 (FR-018)"*; the `Cloud hosting` row *"Optional demo (OD-28)"*; a row for the base image and the system packages; scanning tools **[OD-39 b]** as dev-only, each named when chosen with its licence read at install (SEC-11); I name none here.
2. **Section L.2.1:** decisions **D-18** (the image runs from the source tree: OD-29), **D-19** (the deployment target: OD-28), **D-20** (persistence: OD-32), **D-21** (authentication: OD-34), **D-22** (TLS: OD-35), **D-23** (retention: OD-40), each with the owner's date.
3. **Section Q, Phase 7 row:** goal *"Hardening, a container image and an optional demo deployment"*; entry unchanged; exit *"The Section M review is written (an evidence table: each finding fixed and tested, accepted with a reason, or deferred by the owner); FR-018 is shown in the image; the choices of OD-28, -32, -34, -35 and -40 are built or recorded as not needed; no change to extraction, evidence, calculation, rules, labelling or the memo and report text."* **Expanded evaluation is moved to a new row 7b, not started (OD-27).**
4. **Section S:** the Docker and cloud bullet is replaced by *"Orchestrators (Kubernetes), a database server, built-in user accounts and in-application TLS (unless the owner chooses otherwise at OD-34 and OD-35)."*
5. **Section R (risks):** rows for container out-of-memory kills, results across platforms (OCR and native library versions), a public endpoint that spends model money, and data left on disk.
6. **Appendix A.2:** OD-27, -29, -30, -31, -36, -37, -38, -39 as decided; OD-28, -32, -34, -35, -40 with the owner's choice; OD-33 marked "replaced by OD-40".
7. **Appendix B.6:** examples 179 to 192: (179) a secret in the parent's environment is absent from every child process; (180) a worker whose memory cannot be measured is stopped with `E-INPUT-PARSE-LIMIT`; (181) the launcher on a host where memory cannot be read exits 6; (182) a full service answers `429` before reading the file; (183) an upload quiet for the idle time → `408`, nothing left; (184) a manifest in an image records `CREDIT_INTEL_BUILD_COMMIT`; (185) a start on a public host with a token but without `behind_tls` → `E-CONFIG-INVALID`; (186) a form post behind a proxy that keeps `Host` is accepted and from another origin `403`; (187) the build context holds no `.env` or PDF; (188) the container as non-root with a read-only root; (189) a container with too little memory ends a run with `E-INPUT-PARSE-LIMIT`; (190) a restart with a leftover marker **[OD-32 B]** → `E-RUN-INTERRUPTED`; (191) `prune --older-than 30 --dry-run` lists and removes nothing; (192) `prune` removes whole folders only.
8. **Revision history:** a 0.4.62 row, which repeats the disclosure of section 0. **Version and Status cells** in Section A.

## 4. What is not changed

Extraction, validation, evidence, calculation, rules, labelling, the memo and report text and their checks, the 21 command-line codes and exit codes, the `[api]` limits and their values (1 / 4 / 1,200), the Phase 6 decisions (OD-19 to OD-26, including no delete endpoint unless OD-40 D is chosen), Phase 8.

## 5. Order of work if approved (each step on the owner's word)

1. Apply this draft as v0.4.62 (documents only). After that the PRD matches `bd65fe8`.
2. **Step 2, the image:** Dockerfile, `.dockerignore`, entry point, compose, static tests (criteria 1 to 9), the commands for the owner to build and run, and the in-image test list (criterion 10).
3. **Step 3:** persistence **[OD-32]** and the start-up sweep of uploads; `prune` and the volume requirement **[OD-40]**.
4. **Step 4:** authentication **[OD-34]**.
5. **Step 5:** the proxy settings, the start-up rule, HSTS and the compose proxy **[OD-35, OD-36]**.
6. **Step 6:** the review write-up and the owner's tool runs **[OD-39]**.
7. **Step 7:** the runbook and, if chosen, the demo deployment **[OD-28]**.

## 6. What I need from you

1. **The disclosure (section 0):** keep `bd65fe8` as built and apply this draft so the PRD matches it, or tell me which part to revert or change first.
2. **Your choice on each of the five reopened decisions** (letters from 2.1 to 2.5; for OD-40 one retention letter and one at-rest letter), or "as proposed" if, having seen the options, you agree.
3. For OD-28: whether you want a demo at all, and if so where and what monthly budget.
4. "Apply" to apply the draft as v0.4.62 (or "apply with changes: …"). I will not start step 2 or anything else until you have decided.
