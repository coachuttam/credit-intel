# PRD v0.4.46 draft (part): OCR rendering resolution relative to the page image (specification only)

| Item | Value |
|---|---|
| Status | **Draft. Not applied.** `docs/PRD.md` is unchanged (0.4.45). Needs the owner's word and a version bump. |
| Drafted | 2026-10-26 |
| Source | The OCR step 4 tuning run on S1 and S2 (`PROGRESS.md`, `671dded`), and the owner's choice of follow-up (d) on 2026-10-26. |
| Kind | A change to a specified and implemented behaviour (FR-001A.6). Code, tests and the manifest change with it. |
| Version | 0.4.46 if applied alone. The OD-17 disclosed-exception wording and the K.9 "no OCR" line are separate, also unapproved, amendments; they could share one bump if the owner prefers. |

## 1. The problem, from the evidence

FR-001A.6 renders a page at `ocr.dpi` (provisional 300) pixels per inch **of the page**. A scanned PDF's page size is whatever its producer set, so the same `ocr.dpi` is a different real resolution on each document:

| Tuning scan | Page size | Embedded image | Image pixels per inch of its own size |
|---|---|---|---|
| S1 | 1200 x 1600 pt | 1200 x 1600 px | 72 |
| S2 | 542 x 775 pt | 2238 x 3200 px | about 297 |

At `ocr.dpi` 300, S1 is rendered at 5000 x 6667 pixels, about four times its real pixels in each direction. That is resampling, not extra detail, and it cost about 14 s for 4 pages against about 5 s at 72. On S2, 300 is close to native. A single `ocr.dpi` therefore means different things on the two documents, and a value tuned on one would be wrong on the other.

**What the evidence does not show.** It does not show that rendering at the native resolution reads better. The structure passed on 1 of 6 pages at 72, 100 and 150 dpi and 0 of 6 at 200 and 300, which is too few pages to say more, and the limit on those pages was period-anchor validation, not resolution. The case for this change is that the setting becomes meaningful and the cost stops growing for no gain, not that accuracy improves.

## 2. Options

| Option | Text |
|---|---|
| (a) **Recommended** | `ocr.dpi` becomes a **cap**. Each page is rendered at its largest embedded image's own resolution, but never above `ocr.dpi`. A page with no embedded image information is rendered at `ocr.dpi`. |
| (b) | Render every page at its largest image's own resolution; no setting. Simplest, but there is then no way to limit time or memory on a very high-resolution scan. |
| (c) | No change: `ocr.dpi` stays a page-relative resolution. Its meaning then depends on how the producer sized the page. |

## 3. Specification changes (option a; what would be applied)

### 3.1 FR-001A.6 (replace the criterion)

> 6. **Rendering.** Each page is rendered to an image in memory and discarded. The render resolution is the pixels per inch of the page's largest embedded image (its pixel width divided by its displayed width in inches), but not more than `ocr.dpi` (provisional 300). A page with no embedded image, or one whose resolution cannot be read, is rendered at `ocr.dpi`. A page is never rendered above the resolution of its own image. No page image is written to the repository or to a run folder.

### 3.2 Manifest `ocr` block (FR-001A.8)

The block records, for each OCR'd page, the resolution used (`dpi`), beside its mean confidence. The run-level `dpi` is the configured cap and is renamed `dpi_cap`.

### 3.3 Interface

The page-coverage reading (`ImageCoverageExtractor`) also supplies each page's largest image resolution. The `OcrExtractor` receives the render resolution for each page. No other module reads the engine.

### 3.4 Not changed

The image-only page test, the page cap, the time limit, the OCR evidence rules, the English-only rule, `--psm 6`, the column settings, and every text-layer behaviour.

## 4. What the owner is asked to decide

1. Option (a), (b) or (c).
2. Whether to set a lower bound. Tesseract is known to read poorly below about 150 dpi, and S1 is native 72. A floor would mean upscaling again, which is the behaviour this change removes; the draft sets none, and the effect on S1 is that it is read at its native 72. This is the part with the least evidence.
3. Whether this shares a version bump with the OD-17 and K.9 amendments.

## 5. Implementation if approved

A small step with tests and a mutation check: image-resolution reading in the pdfplumber coverage code, the render scale in the Tesseract adapter, the manifest field and its schema, the golden and the memo line that shows the resolution, and synthetic scans of two native resolutions to prove the render size follows the image and is capped. The real tuning scans stay out of the repository; the rerun on S1 and S2 would be counts only.
