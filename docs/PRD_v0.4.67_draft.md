# PRD v0.4.67 — draft for the owner's final read (status corrections only; not applied)

Nothing below is applied to `docs/PRD.md`. On your word I apply it as written (or as you change it), set the version, run the suite and commit. No requirement changes; every edit records something that was measured or scanned on 2026-11-01. The figures are the owner's, as reported; I have not seen the raw output.

## 1. Header cells

- **Version** 0.4.66 → 0.4.67.
- **Status:** v0.4.66 → v0.4.67, and the sentence: "**v0.4.67 (2026-11-01)** records, as status only, the owner's first builds and runs of the container image (FR-018 criteria 10 and 12), the Section M review write-up (`docs/PHASE7_security_review.md`) and the dependency scans of SEC-11; no requirement changes."
- **Implementation status:** append "The image was built and run by the owner on 2026-11-01 (status v0.4.67): the in-image tests and one real document through the product image pass, and the OD-25 measurement is repeated inside the container's memory limit; the proxy and the image's other runtime checks (runbook sections 6 and 8) are not yet reported."

## 2. FR-018 criterion 12 (replace the last sentence's status; add a status paragraph after it)

Keep the criterion text. Add: "**(Measured by the owner on 2026-11-01, status v0.4.67; `docs/OD-25_container_measurement_2026-11-01.md`.)** One public 369-page annual report, not the 146-page document of the original OD-25 measurement (that file no longer exists), run through the container under a 9 GB limit with the real model: state `exported`, all stages complete, **113 s** from first submission to last end, container peak memory **2,601 MB**, no kernel memory event (`oom`, `oom_kill`, `oom_group_kill` all 0). The shipped values (`api.max_concurrent_runs` 1, `api.max_queued_runs` 4, `api.run_timeout_seconds` 1,200, `ingestion.parse_memory_mb` 6,144) stand. **Not measured:** the full queue (five submissions at once), the `429` path inside the container, a scanned document with OCR, and a document with a slower page design than this one."

## 3. FR-018 status note (the paragraph that begins "**Status (v0.4.63):**")

Append: "**(v0.4.67)** The image was built and run by the owner on 2026-11-01. The first runs found and fixed four faults, none in extraction, evidence or calculation: the test command's `/tmp` mounted `noexec` and without an init process (`938df2f`, `076331a`; test-only), and, in the product, **the parse, render and report workers could not import the package** because they start as `python -I`, which ignores `PYTHONPATH`, and the project is not installed; every document failed with `E-INPUT-CORRUPT` until a `.pth` file was added to the environments (`5f719fb`). The image's tests then passed (263 passed, 3 skipped), including after the Pillow bump. Criterion 11 (the proxy) is still written and not run: the four recalled facts of runbook section 8 are not yet reported."

## 4. SEC-11 (replace "(v0.4.62, specified, not implemented)")

→ "(v0.4.62; met in Phase 7, status v0.4.67). The owner ran the three tools on 2026-11-01, each for a documented reason: **pip-audit** (known-vulnerable Python packages in `uv.lock`), **trivy** (known-vulnerable packages and operating-system layers in the image, secrets in layers) and **bandit** (insecure Python patterns). pip-audit found 39 advisories, all in Pillow 12.3.0; the lock now holds Pillow 13.0.0 (`pyproject.toml` `pillow>=13.0.0`), and a re-run finds none. trivy confirmed the Pillow findings and advisories in the base image's `pip`; Pillow is clean after the bump and `pip` is removed from the product image (a static test keeps it removed). bandit found 38 low and no medium or high findings, reviewed by the owner with no action. **Accepted residual risk (the owner, 2026-11-01):** the remaining 353 findings are operating-system packages of the base image with no fixed version published (1 critical, in libxml2; 70 high; 120 medium; 158 low; 4 unknown), to be looked at again at the next base-image digest bump. This is a developer review with tools, not an independent review (OD-39)."

## 5. Dependencies table, Docker row

"Yes, from v0.4.62 (FR-018; **built and run by the owner from 2026-11-01**)" and delete "Docker is not installed on the development machine; the owner builds and runs it." only if you want it gone; I would keep it, since it is still true of the development machine.

## 6. Section Q, Phase 7 row

No change to the exit text. Add the note: "*(v0.4.67)* Done: the Section M review is written (`docs/PHASE7_security_review.md`, findings F-1 to F-15), SEC-11 is met, criterion 12 is measured. Still to do, all the owner's: the runbook section 8 checks of the proxy (F-11, F-12), the image user and `/health` checks, and the owner's approval of Phase 7; I then write the Phase 7 exit summary."

## 7. Revision row 0.4.67 (2026-11-01)

"**Status corrections, authorised by the project owner on 2026-11-01** ('draft v0.4.67 with the criterion-12 and SEC-11 status-cell updates plus F-13–F-15 in the revision note'). Records the Section M review write-up, the owner's first builds and runs of the image, FR-018 criterion 12 as measured (369-page document, 9 GB limit, 113 s, 2,601 MB, no kernel memory event; shipped limits stand; queue-full and OCR not measured) and SEC-11 as met after the owner's pip-audit, trivy and bandit runs (the Pillow bump to 13.0.0, `pip` removed from the image, the base-image residual accepted). **Three findings from the first real runs are recorded here because they were not in the plan:** **F-13**, a production-breaking fault found only by the first real-document run in the image: the workers could not import the package under `python -I`, so no document could be parsed in the container; my first fix (`076331a`) corrected the test environment only and left the product broken, and the in-image tests could not have found it; fixed in `5f719fb`. **F-14**, two test-command faults (`noexec` `/tmp`, no init process), not product defects. **F-15**, 39 advisories in Pillow 12.3.0 and in the base image's `pip`, fixed in `8b743bc`. **Not changed:** any requirement. **Not done:** the proxy and TLS checks, the image user and `/health` checks, the full-queue and OCR measurements."
