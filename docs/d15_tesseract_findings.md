# D-15 Tesseract Verification Findings (OCR, PRD v0.4.44)

**Purpose:** the "verification required" part of decision D-15 (Tesseract behind the `OcrExtractor` interface, PRD v0.4.44): synthetic scans, error rate, time per page, and the licences read from the installed files. Evidence for the owner's decision whether Tesseract stays the default engine. **It records observations. It decides nothing.**

**Status:** collected 2026-10-26 on the owner's machine. **Not committed.** Nothing in `src/` was changed to produce it except that the adapter was written first (step 3); the experiments below monkey-patched the page-segmentation argument in throw-away scripts that are not in the repository. No setting, prompt or phrase list was changed.

**Provenance and limits (read these first):**
- **All pages are synthetic**: statements generated here with reportlab, invented figures, four layouts (Helvetica 10 pt, 12 rows; Times 9 pt, 24 rows; Courier 8 pt, 30 rows; Helvetica 12 pt, 10 rows), rasterised, degraded in the ways stated, and wrapped as image-only PDFs. They were created in a temporary directory and are not in the repository. **No real scan was read.** Error rates measured here say nothing certain about real scanned reports (stamps, bleed-through, fax artefacts, multi-column notes, handwriting, tinted tables, other fonts).
- **Ground truth** is the text layer of the generated page. Tokens are compared as multisets, so the comparison does not depend on boxes (skew and rotation do not need geometry).
- **"Figure"** below means any token with a digit (including the two year-end dates and note numbers), 193 per variant across the four layouts. **"Misread"** means an expected token with no exact match whose closest unmatched OCR token is at least 50 % similar; **"missed"** means no such token; **"spurious"** means an extra OCR token with a digit. These are counts of tokens, not of the fields a memo needs.
- The confidence is Tesseract's own word confidence (0 to 100). It is not a probability.

## 1. The engine, as installed

| Item | Reading |
|---|---|
| Installed by | `brew install tesseract` (Homebrew 4.1.19), 2026-10-26 |
| Tesseract | 5.5.3 (`tesseract --version`), Leptonica 1.87.0 |
| Languages | `tesseract --list-langs`: `eng`, `osd` |
| English data | `eng.traineddata`, 4,113,088 bytes, SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`; `combine_tessdata -d` reports `Version:4.00.00alpha:eng:synth20170629` and an integer (`int_mode=1`) LSTM network, i.e. a small "fast" model |
| Call made by the adapter | When the measurements below were taken: `tesseract stdin stdout -l eng --dpi N tsv`, one thread (`OMP_THREAD_LIMIT=1`), **no page-segmentation argument, so Tesseract's default (PSM 3, fully automatic)**. **Changed afterwards, on the owner's instruction (2026-10-26): the adapter now also passes `--psm 6`.** The "PSM 3 (current)" columns below are therefore the earlier behaviour. |

## 2. Licences, read from the installed files

| Item | What the installed files say |
|---|---|
| Tesseract | `/opt/homebrew/Cellar/tesseract/5.5.3_1/LICENSE` is the full text of the **Apache License, Version 2.0** (202 lines). Homebrew's `brew info` says `License: Apache-2.0`, and the installed `sbom.spdx.json` lists `tesseract 5.5.3_1 Apache-2.0`. |
| English language data | **No licence file is installed with `eng.traineddata`** (the data directory holds `configs`, `eng.traineddata`, `osd.traineddata`, `pdf.ttf`, `tessconfigs`; no LICENSE or COPYING anywhere under the tesseract install besides the one above). The installed SBOM does not list the language data as a package. The file's embedded strings contain no licence or copyright text. **So the installed files do not state the licence of the English data.** Recorded as the owner directed (2026-10-26): *external reference only, not from the installed files and not verified here:* Tesseract and its English trained data are typically described as Apache-2.0 upstream. **This is not settled; it is flagged for the owner's confirmation** (for example from the upstream repositories' own licence files), and nothing in the platform relies on it. |
| Dependencies of the Homebrew build | The installed SBOM lists, among others, **GPL and LGPL components** (libunistring GPL-2.0-or-later OR LGPL-3.0-or-later; gettext GPL-3.0-or-later AND LGPL-2.1-or-later; glib, pango, cairo, libdatrie, libthai LGPL; lzo and fribidi GPL-2.0-or-later; xz 0BSD AND GPL-2.0-or-later), and permissive ones (Leptonica BSD-2-Clause, libpng, FreeType FTL, libtiff, libjpeg-turbo and others). The platform runs Tesseract as a **separate command-line process**; it does not link to them. |
| This project | Nothing from Tesseract is vendored or distributed by the repository; the engine is a system install (FR-001A.5). Pillow and pypdfium2, now declared direct dependencies, were already locked as pdfplumber's dependencies (no new package). their licences are in the dependency table in `PROGRESS.md` (pypdfium2 Apache-2.0 / BSD-3-Clause with a note on its bundled libraries; Pillow MIT-CMU), read earlier from installed metadata and not re-read here. |

## 3. Time per page

Wall-clock seconds for one page through the adapter (render in memory, Tesseract, parse), 56 page-readings per page-segmentation mode, on this machine (Apple silicon). Mean over the four layouts.

| OCR dpi (clean scan at 300 dpi) | PSM 3 (current) | PSM 6 |
|---|---|---|
| 150 | 0.83 s | 0.84 s |
| 200 | 1.10 s | 1.20 s |
| 300 | 1.59 s | 1.61 s |
| 400 | 2.34 s | 2.25 s |

Other observations: min 0.41 s, max 4.13 s over all runs; the noisy variant took about 3.4 s at 300 dpi; a 20-page scan in one call took 30.6 s (1.53 s a page, all 20 readings identical). The end-to-end command-line run (OCR, locate, model reply from a fake provider, checks, memo) took 1.2 to 2.1 s for one page at 300 dpi.

**Time limit.** With a 0.05 s limit the adapter raised `E-INPUT-OCR-FAILED` after 0.26 s (page rendering is not interruptible); limits of 0.3 s and 0.8 s failed at the limit; 5 s succeeded. A 20-page call with a 10 s and a 25 s limit failed at 10.0 s and 25.0 s. **The `--version` and `--list-langs` checks that run before the deadline starts are not covered by it** (each has its own 30 s guard).

**Determinism.** Five repeated reads of one page gave identical results (text, boxes, confidences).

## 4. Accuracy on the synthetic scans

### 4.1 Page-segmentation mode matters more than anything else seen

The adapter as written uses Tesseract's default segmentation. For a table, that default splits the page into separate blocks, so a row's label and its figures can come out as separate "lines". Rows of the generated pages (label and two figures) that appeared **whole on one OCR line**, over 12 page-readings (4 layouts × clean, 1° skew, JPEG q30) at 300 dpi:

| Mode | Rows whole on one line |
|---|---|
| PSM 3 (default, current) | 36 of 228; **0 of 24, 0 of 30 and 0 of 10 rows for the Times, Courier and 12 pt layouts**; all 12 for the Helvetica 10 pt layout |
| PSM 4 (single column of variable sizes) | 213 of 228 |
| PSM 6 (single uniform block) | 220 of 228 |

Consequence seen end to end (a fake model that quotes the OCR line, real Tesseract, the whole command line): with the current default, only the Helvetica 10 pt layout reached the checks with its rows intact; for the Times 9 pt and the Helvetica 12 pt layouts **no field was produced at all** (the quoted line never held a label and its figures; the Courier layout was not run in that pass). With PSM 6 every layout produced six fields. The stub-based unit tests of step 3 could not show this.

### 4.2 Figure tokens read exactly (193 per variant), by mode

| Variant (OCR dpi 300 unless stated) | PSM 3 exact / misread / missed / spurious | PSM 6 exact / misread / missed / spurious |
|---|---|---|
| Clean, 150 dpi | 164 / 25 / 4 / 26 | 190 / 3 / 0 / 2 |
| Clean, 200 dpi | 161 / 30 / 2 / 24 | 191 / 2 / 0 / 1 |
| **Clean, 300 dpi** | **186 / 5 / 2 / 5** | **190 / 3 / 0 / 2** |
| Clean, 400 dpi | 178 / 10 / 5 / 12 | 184 / 8 / 1 / 7 |
| Scan made at 150 dpi, read at 300 | 161 / 24 / 8 / 24 | 192 / 1 / 0 / 1 |
| Scan made at 100 dpi, read at 300 | 76 / 28 / 89 / 1 | 140 / 47 / 6 / 8 |
| JPEG quality 30 | 185 / 7 / 1 / 2 | 186 / 5 / 2 / 1 |
| Blur (radius 1.5) | 192 / 1 / 0 / 1 | 193 / 0 / 0 / 0 |
| Gaussian noise (σ 30) | 165 / 26 / 2 / 6 | 164 / 28 / 1 / 13 |
| Skew 1° | 187 / 5 / 1 / 2 | 184 / 8 / 1 / 3 |
| Skew 3° | 188 / 5 / 0 / 1 | 186 / 7 / 0 / 2 |
| **Skew 7°** | 98 / 92 / 3 / 46 | 69 / 120 / 4 / 87 |
| **Rotated 90°** | 1 / 24 / 168 / 179 | 1 / 28 / 164 / 104 |
| Low contrast | 159 / 26 / 8 / 21 | 162 / 23 / 8 / 18 |

Ordinary words (240 per variant) were read exactly 240 of 240 on the clean 300 dpi scan in both modes, and 237 to 240 in the JPEG, blur, noise, low-contrast and 1° to 3° skew variants; they fail at 100 dpi (179 and 213 of 240), at 7° skew (209) and at 90° rotation (0).

**Error rate on the clean 300 dpi scans:** figures misread, missed or spurious: PSM 3 12 of 193 tokens (6.2 %, counting the three kinds together), PSM 6 5 of 193 (2.6 %). All of it is in the Courier 8 pt layout at PSM 6 (the three Helvetica and Times layouts read every figure exactly at 300 dpi). Resolution is not monotonic: 400 dpi read worse than 300 dpi in both modes.

### 4.3 Misreads and their confidence ("silent" errors)

What the misreads look like (truth → read, engine confidence): a changed digit (`17,621.72` → `47,621.72`, 92; `71,336.56` → `71,836.56`, 74; `25,142.91` → `95,142.91`, 84), a lost leading or trailing part (`90,533.25` → `533.25`, 25; `81,654.32` → `81,654.`, 93), a lost or changed bracket (`(30,949.38)` → `30,949.38)`, 48), a lost comma or point (`61,513.33` → `61,51333`, 34), and letter-for-digit (`82,107.35` → `S20735`, 14).

Misreads that carry a confidence of **80 or more** (the engine was confident and wrong) among the misreads of each clean variant:

| | PSM 3 | PSM 6 |
|---|---|---|
| Clean 150 dpi | 22 of 25 | 3 of 3 |
| Clean 200 dpi | 26 of 30 | 0 of 2 |
| Clean 300 dpi | 0 of 5 | 0 of 3 |
| Clean 400 dpi | 0 of 10 | 0 of 8 |
| Scan made at 150 dpi, read at 300 | 23 of 24 | 1 of 1 |
| JPEG q30 | 0 of 7 | 1 of 5 |
| Skew 3° | 3 of 5 | 2 of 7 |
| Skew 7° | 28 of 92 | not counted |

So a wrong digit that still parses as a figure (`47,621.72`) was seen at confidence 92. The confidences of wrong and right readings **overlapped in this sample**: correctly read figures went as low as 0 (the lowest in a run, over all runs), and the middle value of those per-run lowest confidences was about 71 to 73.

### 4.4 Through the platform's checks (real Tesseract, PSM 6, fake model quoting the OCR lines)

Six fields per page (current assets, current liabilities, total equity, both periods). Result of the pipeline's checks, counted per page-reading:

| Scan | All six reach `ocr_unconfirmed` only (every other check passed) | Other outcome |
|---|---|---|
| Clean 300, JPEG q30, scan made at 150, noise σ30 | Helvetica 10 pt, Times 9 pt, Courier 8 pt (clean and 150): yes | Courier with JPEG or noise: `period_mismatch` (the period header was misread) |
| Helvetica 12 pt (all those variants) | 3 of 6 | the other 3: `period_not_verified` (the period-column check failed on the OCR boxes for one of the two columns) |
| Skew 1° and 3° | none | all six `period_not_verified`, in all four layouts (except one field at 1° for the 12 pt layout) |

No metric was defined in any of these runs and all fields were `requires_review`, as the platform's rule requires.

## 5. Failure modes observed

1. **Page segmentation splits tables** (4.1): decisive with the default mode; the adapter as written does not set a mode.
2. **Skew**: 1° and 3° read well as text (4.2) but the period-column check, with the text-layer margin of 3 pt applied to OCR boxes, failed for nearly every field (4.4). 7° skew degraded the reading itself (92 or 120 misreads of 193).
3. **Rotation**: a page rotated 90° was unreadable (mean word confidence about 28 to 38; 1 of 193 figures read). Nothing in the adapter detects or corrects orientation. Tesseract's `osd` data is installed but is not used.
4. **Low resolution**: a scan made at 100 dpi lost 89 of 193 figures at PSM 3 and had 47 misreads at PSM 6.
5. **Silent misreads at confidence 80 or more** (4.3), mostly at small point sizes or low resolution.
6. **Small type** (Courier 8 pt) was the weakest layout at every resolution.
7. **Time-outs** behave as designed (`E-INPUT-OCR-FAILED`), with the unbounded pre-checks noted in section 3.
8. **Not seen / not tried**: stamps, tinted rows, dot leaders, multi-page tables, two-column pages, mixed-orientation pages, non-Latin text, a scan with a real bracket-like glyph confusion beyond those listed, memory use, parallel runs.

## 6. What this does not establish

- That Tesseract reads real scanned annual reports at any particular rate. These are four invented layouts in four fonts.
- Whether another engine would do better. No other engine was run.
- A threshold, a DPI, a column margin or a page-segmentation mode for the platform: none was chosen or set; nothing in the repository was tuned (AC-E-7: OCR settings are tuned only on an owner-assigned scan).
- The licence of the English language data (section 2): the installed files do not state it.

## 7. Decisions taken on this evidence (owner, 2026-10-26) and options still open

**Decided:**
- **Skew and rotation:** skewed pages are to be refused for now; there is **no de-skew or orientation handling in this step**; it is documented as a limitation (README, memo section 9 for runs that used OCR, and here). What is built today is not a refusal: a skewed or rotated page is read as it is, and the checks send it to review (`period_not_verified`, or an unreadable page), never to `extracted` (an OCR value is never extracted). A refusal at the door (detecting skew and stopping the page with a catalogued error) would need a skew measure, a new error code and a PRD change, and has not been built.
- **English data licence:** the installed files do not state it (section 2); the Apache-2.0-upstream statement is external, unverified and flagged for the owner's confirmation.
- **Page segmentation:** mode 6 (done, step 3).
- **Step 4 (OCR column settings) is on hold** until the owner has real scanned documents to assign (OD-17).

**Still open (the owner's):**
- Whether Tesseract stays the default engine (not yet said).
- Whether the adapter should build its text lines from word boxes by vertical position (as the text-layer lines are formed) instead of Tesseract's line numbers (mode 6 is in; about 8 of 228 rows still split in the experiment).
- Whether `ocr.dpi` should be higher than 300 (400 was worse here) and what resolution of input the platform should require.
- Whether the OCR period-column margin (`ocr.column_margin_pt`, step 4) should be tuned on an owner-assigned scan, given 1° skew failed the check at 3 pt.
