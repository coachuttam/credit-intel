# SEC-12 step 3 proposal: a memory limit for the OCR engine (Tesseract)

| Item | Value |
|---|---|
| Status | **Proposal for the owner's review. Nothing is built, and `docs/PRD.md` is unchanged (0.4.52).** A PRD draft follows only if you approve a direction. |
| Drafted | 2026-10-27 |
| What it answers | The last parser SEC-12 leaves without a memory limit. The PRD asks for parse limits before any network-exposed deployment that enables OCR (SEC-12, v0.4.50). Steps 1 and 2 covered the PDF libraries and the page render. |
| Kind | New behaviour: Tesseract is run under the same watch as the other workers. No change to any extracted value, check, calculation or memo text. |

## 1. Where Tesseract stands today

`ingestion/tesseract_ocr.py` starts `tesseract` once per page with `subprocess.run`, feeds it the PNG on standard input and reads the TSV. It has a **whole-call time limit** (`ocr.timeout_seconds`, 120 s), and `OMP_THREAD_LIMIT=1` keeps it to one thread. It has **no memory limit**. Its input is not the untrusted file itself but a PNG that our own render worker made from it (step 2), so the render worker's memory limit already bounds how large that image can be. What the PNG's pixels contain is still untrusted.

## 2. What it costs (measured on synthetic pages, this machine)

Tesseract 5.5.3, page segmentation mode 6, one thread. Synthetic pages only; nothing from a real document.

| Page | Pixels | Tesseract time | Tesseract peak memory |
|---|---|---|---|
| A4 text at 150 dpi | 2 Mpx | 2.9 s | 56 MB |
| A4 text at 300 dpi | 9 Mpx | 3.7 s | 96 MB |
| A4 text at 600 dpi | 35 Mpx | 5.1 s | 200 MB |
| A4 text at 1200 dpi | 139 Mpx | 8.4 s | 637 MB |
| **Random black-and-white noise** at 150 dpi | 2 Mpx | 11 s | 95 MB |
| **Random black-and-white noise** at 300 dpi | 9 Mpx | 68 s | 268 MB |

The render worker, for comparison (letter page): 8 Mpx 118 MB, 34 Mpx 407 MB, 135 Mpx 1,142 MB.

What this shows:
- **Clean text** costs Tesseract about 4.6 bytes per pixel at large sizes, roughly half what the render worker needs for the same pixels. An image the render worker can produce under 4,096 MB (about 480 Mpx) would cost Tesseract about 2.2 GB.
- **Noise is the bad case.** It cost about three times the memory of clean text at the same size, and the time grew from 11 s to 68 s for four times the pixels. At 9 Mpx Tesseract used more memory than the render worker did. Extrapolated, a noise page near the largest renderable size would need several GB, but it would take far longer than the 120 s OCR limit, so **the time limit stops it first**.
- The noise figures are an artificial worst case, not a forecast for real scans. I did not run a real scan for this.

So the practical exposure today is small, because time and image size are both bounded. What is missing is a stated, enforced memory bound, which the PRD requires before network-exposed use.

## 3. Options

| Option | Text | Finding |
|---|---|---|
| (a) | Keep Tesseract as it is and document that its memory is bounded only indirectly (image size, time). | Cheapest. Leaves SEC-12 with a stated gap for a network-exposed OCR deployment. |
| (b) **Proposed** | Run Tesseract under the same watch as the workers: the parent polls its resident memory and kills its process group past the memory limit. | The same mechanism and the same limit already in use; moderate work. |
| (c) | (b) plus a cap on the pixel count of a rendered page, refused before rendering. | A deterministic guard, but a new required setting, and the render limit already bounds the image. |

## 4. Proposed design for (b)

- **A supervised run in `ingestion/sandbox.py`:** a function that starts a command in its own process group, feeds standard input from a thread, drains standard output into memory (capped), polls the process's resident memory every 100 ms, and kills the group past the limit. It reuses the existing watch, kill and drain code.
- **The engine takes it as a hook**, as it took the renderer in step 2 (`use_runner`). Only the page read goes through it; the two cheap availability checks (`--version`, `--list-langs`) stay as they are. Without a runner, as in the suite's engine tests, behaviour is unchanged.
- **The limit:** the existing `ingestion.parse_memory_mb` (4096). No new required setting.
- **Time:** Tesseract keeps its own whole-call limit (`ocr.timeout_seconds`) and is **not** counted in the 300 s parse budget. Passing it stays `E-INPUT-OCR-FAILED`, as today.
- **Errors:** passing the memory limit is `E-INPUT-PARSE-LIMIT`, naming the memory limit and `ingestion.parse_memory_mb`; a crashed engine or a bad exit stays `E-INPUT-OCR-FAILED`. No new code. No document text in any error, log or file.
- **Output:** the same TSV bytes as today, so every OCR result stays as it is.

## 5. How I would test it (synthetic only)

- A stub `tesseract` that **allocates** past the limit, one that **sleeps** past the OCR time, one that **floods** standard output, one that **crashes**: each gives the stated code, within a bound, with no process left behind.
- **Equality:** the same TSV and the same page read with and without the runner; and one opt-in test (the existing `real_ocr` marker) with the real engine on a generated page.
- A stub with a child process (the group is killed), no document text or path in any error, and a spent budget starting nothing.
- **Mutation checks** on the limit comparison, the process-group kill, the error mapping and the hook wiring.

## 6. Cost and risk

- **Polling is sampled:** a burst between two samples can pass the limit briefly. The limit is a bound, not an exact figure.
- **One more process watch per page:** a `ps` call every 100 ms while Tesseract runs (1 to 70 s a page).
- **Not covered after this step:** the evaluation tools, Windows, and the Linux address-space backstop (not run on Linux).
- **Not a security boundary:** this stops runaway memory, not malicious code. Tesseract is a system install and is trusted as software.

## 7. What I need from you

1. Option (a), (b) or (c). I propose (b).
2. Reuse `ingestion.parse_memory_mb` (proposed), or a separate required `ocr.memory_mb`.
3. Tesseract time stays outside the 300 s parse budget (proposed), or counts in it.
4. Whether `E-INPUT-PARSE-LIMIT` is right for the engine's memory (proposed), or a different code.
5. Whether this is worth doing before Phase 6 (my view: yes, because the PRD requires it for network-exposed OCR) or can wait.

If you approve a direction I would draft the PRD change (SEC-12, FR-001A.7, FR-001 criterion 10, a version bump) for your approval before building.
