# Runbook: the container image (PRD FR-018, v0.4.62; Phase 7 step 2)

| Item | Value |
|---|---|
| Status | **Written, not run.** Docker is not installed on the development machine, so none of these commands has been run by me. The owner builds and runs them; the first run is the test of this runbook. |
| Covers | Building the image, running it with compose, sizing its memory, the checks inside the image (FR-018 criterion 10), and the measurement inside the container's real memory limit (criterion 12, which must be done before Phase 7 is called finished). |
| Does not cover | A reverse proxy and TLS (step 5), `prune` and the start-up sweep (step 3), a standing demo (not planned: OD-28). The service is published on the host's loopback address only. |
| Rules | Public and synthetic documents only (SEC-01). **Never push the image to a public registry:** it holds the send-rule record (D-18). Never put the key or the token in the image, a compose file, a build argument or the repository. |

## 1. What you need

- Docker (Docker Desktop on a Mac) with compose v2.
- The repository at a commit. The files that go into the image must equal `HEAD` (`deploy/build.sh` checks; other changes in the tree, such as a document under review, do not matter).
- A key for the hosted model and a token for the service, in an env file **outside the repository** (section 3).

## 2. Build

The base image must be pinned by digest. The build stops with a message if it is not.

```
docker pull python:3.12-slim
export PYTHON_IMAGE=$(docker inspect --format '{{index .RepoDigests 0}}' python:3.12-slim)
echo "$PYTHON_IMAGE"        # python@sha256:<64 hex>: keep this value; it is what makes the build repeatable
deploy/build.sh              # builds credit-intel:<commit> and prints CREDIT_INTEL_BUILD_COMMIT=<commit>
```

The image holds: the environment from `uv.lock` (no dev tools), the source tree, `prompts/`, `config/`, the send-rule record, Tesseract with the English data. It runs as user 10001 with a read-only root file system. It holds no secret, no document, no `.env`, no test.

Raising the base image later is a deliberate act: pull, read the new digest, set `PYTHON_IMAGE`, rebuild, run the checks of section 6.

## 3. Secrets

```
mkdir -p ~/credit-intel-secrets && chmod 700 ~/credit-intel-secrets
cp deploy/credit-intel.env.example ~/credit-intel-secrets/credit-intel.env
chmod 600 ~/credit-intel-secrets/credit-intel.env
$EDITOR ~/credit-intel-secrets/credit-intel.env        # OPENAI_API_KEY=...   CREDIT_INTEL_API_TOKEN=...   (token: python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
export CREDIT_INTEL_ENV_FILE=$HOME/credit-intel-secrets/credit-intel.env
```

A token shorter than 32 characters, or an empty one, stops the service at start. The service listens on `0.0.0.0` inside the container, which needs a token (SEC-15); the compose file publishes it on `127.0.0.1` of the host only.

## 4. Memory: the rule, and why the service may refuse to start

Three things share the container's memory:

- the workers: one run can hold up to `ingestion.parse_memory_mb` (6,144 MB in `config/settings.toml`), and the pool can run `api.max_concurrent_runs` of them at once;
- the uploads: the upload folder is a `tmpfs`, which **is memory**. The service can hold `api.max_concurrent_runs + api.max_queued_runs` uploads at once, each up to 100 MB: 500 MB with the shipped values. (`CREDIT_INTEL_UPLOAD_TMPFS`, default 512m, is only a cap on the folder; what is counted is what the service can put in it.)
- the server itself: about 1.5 GB with one run (1,536 MB; OD-25 measured 1,458 MB for a 159-page run).

If the container's limit is below the sum, the kernel would end the **whole container** (every run, the queue and the server) before the parse limit could end one run. So **the service reads the container's limit when it starts and refuses to start below the sum**, saying both numbers (`E-CONFIG-INVALID`, exit 6).

With the shipped values (1 run, 4 waiting, 6,144 MB) the container needs **at least 8,180 MB** (6,144 + 500 + 1,536). `CREDIT_INTEL_CONTAINER_MEMORY` has no default; set it (for example `9g`; `8g` is 8,192 MB and passes by 12 MB, with no headroom).

**Docker Desktop on a Mac gives the container less than the Mac has** (its virtual machine has its own memory setting). If the machine cannot give about 8 GB to Docker, the service will refuse to start with the numbers. Then either give Docker more memory, or change a limit **deliberately and with a measurement** (section 7): that is the owner's decision, not one to make by default.

## 5. Run

```
export CREDIT_INTEL_BUILD_COMMIT=<the commit deploy/build.sh printed>
export CREDIT_INTEL_CONTAINER_MEMORY=8g
export CREDIT_INTEL_TOKEN_CEILING=30000          # the per-run token ceiling has no default
docker compose up -d
docker compose ps                                # healthy after about 20 seconds
curl -s http://127.0.0.1:8000/health             # {"status":"ok","queued":0,"running":0}
docker compose logs credit-intel                 # request lines and stage lines: counts and identifiers only
docker compose down                              # waits for running runs, up to the stop grace period (1300 s by default, longer than api.run_timeout_seconds)
```

Settings come from `config/settings.toml` mounted read-only at `/config/settings.toml` (point `CREDIT_INTEL_SETTINGS` at another file to use your own). The run folders and the response cache are named volumes (`runs`, `cache`). **They are plain files** (SEC-18): keep the volumes on an encrypted disk (FileVault on a Mac, LUKS or the provider's disk encryption on Linux). The service cannot check this. Nothing removes old runs yet (`prune` is step 3): remove a volume by hand with `docker volume rm` when you are done.

## 6. Checks inside the image (criterion 10)

```
deploy/build.sh test                                                       # credit-intel-test:<commit>
docker run --rm --read-only --tmpfs /tmp:size=512m --network none \
  credit-intel-test:$CREDIT_INTEL_BUILD_COMMIT                             # the golden, reproducibility, service, API, parse-limit and OCR-engine tests
```

Expected: all pass (some tests that need Node are skipped). The image is not the product. Then, on the product image:

```
docker run --rm --entrypoint id credit-intel:$CREDIT_INTEL_BUILD_COMMIT                       # uid=10001, not root
docker run --rm --entrypoint sh credit-intel:$CREDIT_INTEL_BUILD_COMMIT -c 'ls -A /app /config; ls /app/tests /app/.env /app/private 2>&1'   # no .env, no private/, only tests/eval
docker run --rm --entrypoint sh credit-intel:$CREDIT_INTEL_BUILD_COMMIT -c 'find / -xdev -name "*.pdf" -not -path "/usr/*" -not -path "/opt/venv/*" 2>/dev/null | head'   # no document
docker run --rm --read-only credit-intel:$CREDIT_INTEL_BUILD_COMMIT --help               # starts as non-root on a read-only root
```

A run of the whole path with a fake provider is in the test image (`tests/integration/test_api_end_to_end.py`). A run with the real model is the measurement of section 7.

## 7. The measurement inside the container (criterion 12; required before Phase 7 is finished)

The numbers 1 / 4 / 1,200 were measured on the bare machine (`docs/OD-25_run_timing_2026-10-30.md`). Repeat them **under the container's real limit**:

1. Start the service as in section 5 with the container memory you intend to use. If it refuses to start, that is the first result: write down the two numbers it names.
2. One run: `export CREDIT_INTEL_API_TOKEN=<the token>` and `deploy/measure_container.sh <public.pdf>`. Use the same public 146-page report as OD-25, so the numbers compare. It prints each run's final status, the seconds, the container's peak memory and the kernel's memory events (`oom_kill` must stay 0).
3. If you want to test a pool of 2 or more, set `api.max_concurrent_runs` in your own settings file (`CREDIT_INTEL_SETTINGS`), restart, and run `deploy/measure_container.sh <public.pdf> 2`. The service will refuse to start unless the container memory covers that pool (section 4).
4. Compare with OD-25: whole-run seconds, peak memory. **If the numbers do not hold under the container's limit** (a run is killed, `oom_kill` is not 0, the whole-run time approaches `api.run_timeout_seconds`, or the service will not start with the limit the machine can give), lower `api.max_concurrent_runs` or raise `api.run_timeout_seconds` in `config/settings.toml`, **and show the old and the new numbers against the new measurement**, as OD-25 did. Send me the outputs of the script (they hold no document text) and I will propose the values; the decision is yours.
5. Each submission costs a few thousandths of a dollar and sends statement pages to the hosted model: a public document only, within the cap of $0.15 (about $0.037 spent so far).

## 8. To watch on the first real build

The first build and run is the real test of this runbook, and in particular of one thing nobody has been able to test: **the read-only root file system.** The container's root is read-only; only `/tmp` (a `tmpfs`) and the two data volumes are writable. A library that tries to write anywhere else (a cache in a home folder, a font cache, a file next to its code) will fail. Look for it explicitly:

- Run the checks of section 6, and then **one full run with the real model** (section 7). Read `docker compose logs credit-intel` for `Read-only file system`, `PermissionError` or `OSError`.
- **Open the finished run's `manifest.json` and look at `report.status`.** A report that cannot be built does not fail the run (FR-015): the run completes and only `report` shows `failed` with `render_error`, so a read-only problem in the report worker would be silent unless you look. The same goes for OCR: run once with OCR on a scanned page if you can.
- If something fails for this reason, the fix is a writable path for that one thing (an environment variable or another `tmpfs`), not turning the root file system writable. Tell me what failed.

## 9. If something goes wrong

| Symptom | Cause and action |
|---|---|
| `compose` stops with "set CREDIT_INTEL_..." | A required value is missing on purpose (no defaults for limits or secrets). Set it. |
| The build stops with "PYTHON_IMAGE must be pinned by digest" | Use the value from `docker inspect` in section 2. |
| `E-CONFIG-INVALID` naming `api.token` | The token is missing, shorter than 32 characters or has a space. |
| `E-CONFIG-INVALID` naming container memory | Section 4: give the container more memory (it names both numbers) or change a limit with a measurement. |
| `E-CONFIG-INVALID` "resident memory cannot be measured" | The container has no `/proc` entry for itself: do not run it this way. |
| The container is killed with no message | The kernel's out-of-memory kill (`docker inspect` shows `OOMKilled`): the limit is below what the pool used. Section 7. |
