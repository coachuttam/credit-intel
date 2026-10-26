# PRD v0.4.44 draft: OCR for scanned reports (specification only)

| Item | Value |
|---|---|
| Status | **Adopted on 2026-10-26** ("approve v0.4.44, implement after Release 1, OD-18 option b") and applied to `docs/PRD.md` as v0.4.44. Kept as the record. Nothing is built; implementation is after Release 1. |
| Drafted | 2026-10-26 |
| Source | `docs/PRD_ocr_proposal_draft.md` (`ce2a759`) and the owner's decisions of 2026-10-26 below. |
| Kind | A new capability, specified but not implemented. It changes the "no OCR" limitation, so it needs the owner's word and a version bump (0.4.43 to 0.4.44). |

## 1. Owner decisions recorded by this draft (2026-10-26)

The owner chose **OD-12 option (a)** and **OD-14 option (a)**, and "rest as recommended".

| OD | Decision | Text |
|---|---|---|
| OD-11 | (a) | Tesseract behind a replaceable `OcrExtractor` interface. |
| OD-12 | (a) | An OCR-derived value is never `extracted`: `requires_review`, reason `ocr_unconfirmed`, not used by any metric, derived value or rule. |
| OD-13 | (a) | Only the pages named with `--pages` are OCR'd; a scanned document requires `--pages`. |
| OD-14 | (a) | OCR is off by default; `--ocr` or `ocr.enabled` turns it on; otherwise the existing refusal, with a hint. |
| OD-15 | (a) | Labels and phrases are matched exactly on OCR text; no fuzzy matching. |
| OD-16 | (a) | No second reading of a figure in this version. |
| OD-17 | (a) | The owner assigns a tuning scan and, separately, a held-out scan in `assignments.jsonl` before anyone inspects them; real scans are never committed; results are counts only. Synthetic scans test the code. |
| OD-18 | (b), decided later the same day | An OCR page cap and a time limit, both required settings with no default when OCR is enabled; the values are set at implementation. (At first drafting this was open: the proposal gave no recommendation.) |

## 2. Specification changes (what would be applied)

### 2.1 FR-001.6 (replace the criterion)

> 6. A PDF in which no page has extractable text is rejected with `E-INPUT-NO-TEXT-LAYER`, unless OCR is enabled (FR-001A). The message states that the document appears to be scanned and, when OCR is not enabled, that OCR can be turned on with `--ocr` and `--pages`. A page has extractable text if its extracted text contains at least one non-whitespace character.

### 2.2 New FR-001A: OCR of image-only pages (Should; specified, not implemented)

1. **Off by default.** OCR runs only when `--ocr` is given or the setting `ocr.enabled` is true. Otherwise behaviour is exactly as before.
2. **Image-only page.** A page is image-only if its extracted text has no non-whitespace character and an image covers at least `ocr.min_image_area_share` of the page area (provisional setting). A page with a text layer is never OCR'd. A blank page is not image-only.
3. **Only named pages.** When OCR is enabled and the document has no text layer, `--pages` is required; the locator does not run (FR-013 rule 8, the page-range case). A scanned document without `--pages` is refused with `E-INPUT-PAGE-RANGE` and a message that names `--pages`.
4. **Mixed documents.** Only image-only pages among the pages the run uses are OCR'd. The run records, for each page, whether its text came from the text layer or from OCR.
5. **Engine and interface.** OCR is read through a replaceable `OcrExtractor` interface in the `ingestion` module, which supplies text, word boxes and per-word confidence. Tesseract is the first implementation. No other module imports the engine, and the engine is a system install, not a Python dependency alone.
6. **Rendering.** Pages are rendered to images in memory at `ocr.dpi` (provisional 300) and discarded. No page image is written to the repository or to a run folder.
7. **Outcomes.** OCR text for the pages that is empty gives `E-INPUT-NO-TEXT-LAYER`. An engine that is not installed or configured gives `E-INPUT-OCR-UNAVAILABLE`. An engine error gives `E-INPUT-OCR-FAILED`. No error prints document text.
8. **Determinism and record.** The manifest gains an `ocr` block only when OCR was used: engine name and version, DPI, language, the pages OCR'd, and each page's mean word confidence.
9. **Language.** English only, as for the line-item phrases.
10. **Offline tests** use a fake `OcrExtractor`. A real-engine test is marked opt-in.

### 2.3 FR-005: a new criterion 11 (evidence from OCR)

> 11. **Evidence source (OCR).** Each field records `evidence_source`, `text_layer` or `ocr`. For an `ocr` field the checks of criteria 1 to 10 run unchanged on the OCR text and word boxes, and the field also records the engine, DPI, the minimum and mean confidence of the words of its quote, and the page's mean confidence. **Passing criteria 1 to 10 on OCR text shows consistency with the OCR reading, not that the page was read correctly.** A field whose evidence source is `ocr` is never `extracted`: its status is `requires_review` with the reason `ocr_unconfirmed`, whatever the other checks give (a field that fails an earlier check keeps that earlier reason; `ocr_unconfirmed` is the last reason in the order of criterion 3). It is not used in any metric, derived value or risk rule, and a test checks that no `ocr` field is reachable from a metric input.

Matching is exact on OCR text. No fuzzy matching, confusable-character normalisation or label correction is added. A label, scale declaration, date or figure that the engine misreads gives the existing reason (`label_not_recognised`, `scale_not_verified`, `period_not_verified`, or an unparsable figure, which is `requires_review`). A bracket-like character that is not `(` or `)` next to a figure is ambiguous for the sign check (criterion 6) and is never read as positive.

**OCR column settings.** `column_margin_pt` and the split-figure join gap have separate OCR settings (`ocr.column_margin_pt`, `ocr.split_figure_gap_pt`), provisional and set only on a scan tuning document (AC-E-7). The text-layer settings are not changed.

### 2.4 Memo and results

- Each OCR field appears in the memo's missing-and-review section with its quote, page and confidence, labelled `[OCR p.N, confidence …]`, never `[SOURCE: p.N]`.
- Section 2 (documents reviewed) states that OCR was used, on which pages, with which engine and settings. Section 9's fixed text states the OCR limitation in place of "no OCR" when OCR was used.
- A fixed analyst question is added: "Check this value against the page image."
- `results.json` carries `evidence_source` and the confidence figures for each field.

### 2.5 Other places that change

- **Scope and limits:** the scope table, the release-boundary list and the glossary now say OCR is specified, off by default, and not part of what the owner has accepted as built. The README limitation changes when it is implemented, not now.
- **Error catalogue:** two new codes (`E-INPUT-OCR-UNAVAILABLE`, `E-INPUT-OCR-FAILED`) with fixed messages, actions and exit codes; the text of `E-INPUT-NO-TEXT-LAYER` changes as in 2.1. Worked example 19 (image-only PDF) is rewritten for both the OCR-off and OCR-on cases.
- **SEC-10:** unchanged in rule, because OCR is local. A note that no page image leaves the machine.
- **D-xx:** a new decision record for Tesseract, in the form of D-01 (choice, why, trade-offs, replaceability, verification required: synthetic scans, error rate and time per page, licences confirmed at install time).
- **Evaluation:** a scanned document is not scored with the text-layer documents. Its tuning and held-out assignment and its report are separate, by run id.
- **Appendix A.3:** OD-11 to OD-17 recorded as decided; OD-18 as open.
- **Appendix B.6:** examples for OCR off with a scan, OCR on with `--pages`, a mixed document, an image-only blank page, a misread label, a misread figure, and a bracket-like character.

## 3. What this draft does not do

It does not build anything, set a threshold, a DPI or a margin, or pick a scanned report. It does not change a document that has a text layer, the frozen configuration, the gate or the held-out record. Tests and steps are as in the proposal's section 7 (fake engine first, real engine later).

## 4. Questions that were open when this was drafted (answered 2026-10-26: after Release 1; OD-18 option b; approved)

1. **Release.** The PRD lists OCR as a candidate for later releases and Phase 8 as optional extensions. Do you want this specification applied now but implemented **after Release 1** (as a Phase 8 item), or implemented before the release approval? I recommend after Release 1: the release approval is waiting on the held-out decision, and OCR adds a system dependency and new failure modes.
2. **OD-18.** Keep the limits as they are, or add an OCR page cap and time limit? I suggest (b) at implementation time, since OCR is a heavier workload than text extraction and SEC-12 is already open.
3. **Approval.** Say "approve v0.4.44" (with any answers above) and I will apply it to `docs/PRD.md` with the version bump, then stop. Nothing is implemented until you say so.
