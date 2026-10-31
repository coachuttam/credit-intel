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

Settings come from `config/settings.toml` mounted read-only at `/config/settings.toml` (point `CREDIT_INTEL_SETTINGS` at another file to use your own). The run folders and the response cache are named volumes (`runs`, `cache`). **They are plain files** (SEC-18): keep the volumes on an encrypted disk (FileVault on a Mac, LUKS or the provider's disk encryption on Linux). The service cannot check this.

**Clearing old runs (SEC-18).** The service never removes a run by itself and there is no delete endpoint. `prune` removes **whole** run folders, the hidden staging folders that a crash while a run folder was being written leaves (`.<run ID>.<random>.partial`), response-cache entries and upload directories at least DAYS days old, and nothing else. DAYS is required and has no default; list first, then remove:

```
docker compose run --rm credit-intel prune --config /config/settings.toml --older-than 30 --dry-run
docker compose run --rm credit-intel prune --config /config/settings.toml --older-than 30
```

(A one-off container with the same volumes and limits; `--config` must be repeated because the command replaces the default one.) A run folder's and a staging folder's age is the time in the run ID in its name. A removed run folder can no longer be checked against its stored files (the SHA-256 in a kept manifest still names the input), and without its cache entries a run cannot be reproduced without calling the model again. The upload directories live in the container's `tmpfs` and disappear when it stops, so inside a container `prune` finds none. Schedule it yourself if you want it regular.

**A restart.** Each accepted run leaves a marker file in `.pending` on the `runs` volume before the `202` is sent and removes it when the run ends. After `docker compose down` or a crash, the next start records the runs that were waiting or going as failed with `E-RUN-INTERRUPTED` (a status request then says so; it does not say `404`). Their `manifest.json` has `started_at` as the time they were accepted and `finished_at` equal to it (the service does not know when it stopped), and `failed_stage` `validated` (the first stage after `received`: the stage reached is not recorded). Runs are not resumed: submit the document again. `docker compose down` waits up to the stop grace period for runs that are going to finish.

## 5a. Rotating the token (SEC-15)

There is one token, so rotation is a restart with a new value: **every client stops working at the same moment**, and there is no overlap period (several named tokens are OD-34 (b), not built).

**When.** At once if the token may have leaked (it was pasted somewhere, a device was lost, someone who had it has left); otherwise on whatever schedule you set. The service imposes none.

**Steps.**

1. **Make a new token.** `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` prints one of 64 characters; the service accepts anything of 32 to any number of printable characters without spaces. Do not reuse an old one. Do not put it on a command line you will keep in shell history: copy it into the env file in your editor.
2. **Let the work finish, or accept the interruption.** `curl -s http://127.0.0.1:8000/health` is open and shows `"queued"` and `"running"`. At 0 and 0 nothing is lost. Otherwise the stop waits up to the stop grace period for runs that are going to finish, and anything still waiting is recorded at the next start as `E-RUN-INTERRUPTED` (section 5).
3. **Replace the value** of `CREDIT_INTEL_API_TOKEN` in the env file named by `CREDIT_INTEL_ENV_FILE` (outside the repository, mode 600). Keep the old value nowhere.
4. **Recreate the container.** `docker compose up -d --force-recreate`. **Not `docker compose restart`:** a restart keeps the environment the container was created with, so the old token would still be in force. Outside a container: set the variable and restart the process.
5. **Check, once each.** The old token must be refused and the new one accepted:
   ```
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $OLD" http://127.0.0.1:8000/runs     # 401
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $NEW" http://127.0.0.1:8000/runs     # 200
   ```
   Each wrong attempt counts towards the limit below, so do not repeat the first one more than a few times.
6. **Give the new token to every client** by a channel that is not kept (not chat or e-mail history), and update every script that has the old one.
7. **If it was a leak:** read `docker compose logs credit-intel` for `too many failed token attempts` lines (they name the address), look at the list of runs for any you did not make, and rotate the `OPENAI_API_KEY` at the provider (it is in the same env file; the provider, not this service, can show what was spent with it).

**The limit on failed attempts.** After 5 requests that presented a wrong credential within 5 minutes, the client address is locked out for 15 minutes: every request that needs the token is answered `429` with `Retry-After`, **even one with the right token**, and `GET /health` still answers. Requests that present no credential at all are answered `401` and are not counted. The count is in memory and restarting the service clears it. Behind a published port the service sees one address for every client of that host (and behind a proxy, the proxy's), so the limit is shared by all of them; telling clients apart behind a proxy is part of the proxy step.

## 5b. Reaching the service from another machine: the TLS proxy (OD-35, OD-36)

**Decide first whether you need this.** On one machine, `docker compose up` (section 5) publishes the service on the host's loopback address only and nothing else is needed. For a private network that already encrypts the path (a VPN or tunnel), keep that: point the tunnel at `127.0.0.1:8000` on the host; no proxy and no certificate. **Use the proxy only for a service that is reached over the internet**, and read the warning in section 8: a standing public endpoint spends model money and parses hostile files behind one token (OD-28 decided against one until there is a person to demo to).

**What the service insists on.** The service listens on `0.0.0.0` inside the container; it starts there only if a token is set **and** you have made one of two statements, which it cannot check and which are not the same thing:

- `api.behind_tls = true`: TLS ends in front of the service, or the path to it is encrypted by a private network. This is the only one that makes the service send `Strict-Transport-Security`.
- `api.loopback_only_publication = true`: the only path to the service does not leave the machine. `compose.yaml` makes this one, because it publishes the service on the host's loopback address only; there is no TLS there and the file does not pretend there is.

`compose.proxy.yaml` makes the first and sets the second to `false` (the service is then reached through the proxy, which the internet reaches). The other two settings, which the proxy file sets for you:

- `api.public_hosts`: the name browsers use. A `POST` is accepted only from a page of that name (the proxy keeps the name in `Host`, but a proxy that rewrites it would otherwise make every form post fail with `403`).
- `api.trusted_proxies`: the compose network. Only a connection from it is believed about the client's address (`X-Forwarded-For`, read from the right), so the lock-out of section 5a now counts the real client and one person cannot lock out the rest. A connection from anywhere else cannot name itself. The server's own reading of forwarded addresses is switched off.

**Steps.**

1. Point a public name at this host; open ports 80 and 443 to it (Caddy uses them to get the certificate and to redirect to HTTPS).
2. Pin the proxy image by digest, as in section 2: `docker pull caddy:2` then `export CREDIT_INTEL_PROXY_IMAGE=$(docker inspect --format '{{index .RepoDigests 0}}' caddy:2)`.
3. Choose a network that nothing else on the host uses, for example `export CREDIT_INTEL_PROXY_SUBNET=172.30.60.0/24`, and `export CREDIT_INTEL_PUBLIC_HOST=memos.example.com`. (The subnet must not be `0.0.0.0/0` or any network that includes clients: the service refuses a network that is every address.)
4. `docker compose -f compose.yaml -f compose.proxy.yaml up -d` (Docker Compose 2.24 or later).
5. Check from another machine: `curl -si https://$CREDIT_INTEL_PUBLIC_HOST/health` shows `200`, `strict-transport-security: max-age=31536000` and the headers of SEC-16; `http://` redirects to `https://`; `curl -s -o /dev/null -w '%{http_code}\n' https://$CREDIT_INTEL_PUBLIC_HOST/runs` is `401`.
6. Check the client address: five wrong tokens from one machine lock that machine out (`429`) and a second machine still gets `200` with the right token. If a second machine is locked out too, the proxy's address is being counted: look at the trusted network.

**Pages and the token.** A browser cannot send the bearer token, so with a token set the pages answer `401` (decided in Phase 6): the web page is not usable through this proxy. Use the API with `curl` or a program, or put an identity-aware proxy in front when more than one person needs access (OD-34 (c)).

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

**The proxy files (`compose.proxy.yaml`, `deploy/Caddyfile`) are written, not run, and four facts in them are from memory.** The first real start must **verify each of the four**, with these checks (set the variables of section 5b first; `$PROXY` is the proxy image):

| Recalled fact | Check | What you should see; if not, the file is wrong |
|---|---|---|
| **`!reset` works and needs Compose 2.24 or later** | `docker compose version` then `docker compose -f compose.yaml -f compose.proxy.yaml config \| grep -n 'published'` | A version of 2.24 or later. The merged configuration lists exactly two published ports, `"80"` and `"443"`, and **no `8000`**. An older Compose stops with a YAML error on `!reset`; a `8000` in the list means the reset did not apply and the service is still published on the host. |
| **`admin off` is a valid Caddy global option and takes effect** | `docker run --rm -v "$PWD/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" -e CREDIT_INTEL_PUBLIC_HOST=memos.example.com "$PROXY" caddy validate --config /etc/caddy/Caddyfile`, then, with the proxy running, `docker compose -f compose.yaml -f compose.proxy.yaml exec proxy sh -c 'wget -qO- http://127.0.0.1:2019/config/ \|\| echo "admin endpoint closed"'` | `Valid configuration`; and `admin endpoint closed` (nothing answers on port 2019). A configuration error naming `admin` means the directive is wrong; a JSON configuration printed means the admin endpoint is open. |
| **`request_body { max_size 110MB }` is valid and limits the body** | The same `caddy validate`; then through the running proxy, with the token: `{ printf '%%PDF-1.4\n'; head -c 105000000 /dev/zero; } > /tmp/big105.pdf` and `{ printf '%%PDF-1.4\n'; head -c 115000000 /dev/zero; } > /tmp/big115.pdf`, and `curl -s -w '\n%{http_code}\n' -H "Authorization: Bearer $CREDIT_INTEL_API_TOKEN" -F file=@/tmp/big105.pdf https://$CREDIT_INTEL_PUBLIC_HOST/runs` and the same with `big115` | For 105 MB: the service's own refusal, `413` with `"code":"E-INPUT-TOO-LARGE"` (under the proxy's limit, over the service's 100 MB). For 115 MB: `413` from the proxy with **no** `E-INPUT-TOO-LARGE` in the body (the proxy stopped it). If both show the service's code, the proxy limit is not in force; if the first is stopped by the proxy, its limit is too low. |
| **Caddy replaces a client's `X-Forwarded-For` when no trusted proxy is set** | From your own machine, five times: `curl -s -o /dev/null -H 'X-Forwarded-For: 1.2.3.4' -H 'Authorization: Bearer wrong' https://$CREDIT_INTEL_PUBLIC_HOST/runs`; then `curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $CREDIT_INTEL_API_TOKEN" https://$CREDIT_INTEL_PUBLIC_HOST/runs` from your machine and from a second one | `429` from your machine, `200` from the second; and `docker compose logs credit-intel` shows your own address in `address ... is locked out`, **not `1.2.3.4`**. If it shows `1.2.3.4`, the proxy passes a client's header on and the lock-out can be dodged: do not use the proxy until the Caddyfile is fixed. |

Other things to watch: a subnet that clashes with a network of the host stops the network from being created; the proxy runs with all capabilities dropped except `NET_BIND_SERVICE` and a read-only root, and Caddy may need another writable place than `/data`, `/config` and `/tmp`.

## 9. If something goes wrong

| Symptom | Cause and action |
|---|---|
| `compose` stops with "set CREDIT_INTEL_..." | A required value is missing on purpose (no defaults for limits or secrets). Set it. |
| The build stops with "PYTHON_IMAGE must be pinned by digest" | Use the value from `docker inspect` in section 2. |
| `E-CONFIG-INVALID` naming `api.token` | The token is missing, shorter than 32 characters or has a space. |
| `E-CONFIG-INVALID` naming `api.behind_tls or api.loopback_only_publication` | The service was told to listen on a non-loopback address with a token but without either statement (section 5b). `compose.yaml` makes the loopback-only one and `compose.proxy.yaml` the TLS one; a different way of starting the container must make one. |
| `E-CONFIG-INVALID` naming `api.public_hosts` or `api.trusted_proxies` | A malformed name or address, a list of more than 32, or a network that is every address. |
| Every form post is `403` behind the proxy | `api.public_hosts` does not name the host a browser uses (case does not matter; a port that is not the default must be included). |
| `E-CONFIG-INVALID` naming container memory | Section 4: give the container more memory (it names both numbers) or change a limit with a measurement. |
| `E-CONFIG-INVALID` "resident memory cannot be measured" | The container has no `/proc` entry for itself: do not run it this way. |
| The container is killed with no message | The kernel's out-of-memory kill (`docker inspect` shows `OOMKilled`): the limit is below what the pool used. Section 7. |
