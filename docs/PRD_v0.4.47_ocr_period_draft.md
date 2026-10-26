# PRD v0.4.47 draft: period-end validation for OCR pages (specification only)

| Item | Value |
|---|---|
| Status | **Draft. Not applied.** `docs/PRD.md` is unchanged (0.4.46). Needs the owner's choice of option and a version bump. |
| Drafted | 2026-10-27 |
| Source | The OCR step 4 tuning run on S1 and S2 and its re-run on the v0.4.46 rule (`PROGRESS.md`, `671dded`, `457888d`), and the owner's choice of follow-up (b). |
| Kind | A change to FR-005.9 and FR-005.7 for pages read by OCR, plus one new command-line option under one of the options below. |
| Version | 0.4.47. The OD-17 disclosed-exception wording and the K.9 "no OCR" line are still separate, unapproved amendments and would take a later number. |

## 1. What the tuning scans show

On the six tuning pages (S1 four, S2 two), a valid period-column structure was found on 1 of 6. Every other page failed at the **period anchors**, not at the column margin. A page passes FR-005.9 only if its year-only header (`2025`) is matched by exactly one full date (`31 March 2025`) in the title or column-header block of the same page. Counts, with shapes only (digits and letters masked; no figure or name was kept):

| Pages | Cause seen | Count |
|---|---|---|
| S1 pages 1 and 3 | The statement prints the date as a stem, `As at March 31,`, in a title line, and the years only as bare column headers (`2025`, `2024`). No full date exists in an accepted form. One anchor was read on each page. On page 3 the stem is also garbled by OCR. | 2 of 6 |
| S1 page 2 | No year anchor read in the header block; the years are outside it. | 1 of 6 |
| S2 pages 1 and 2 | The date text is in a line above or below the detected header block, with OCR noise in the digits (a day number read as a digit and a symbol). No year anchor was read at all. | 2 of 6 |
| S1 page 4 | A full date and two year anchors were read; the structure is valid. | 1 of 6 (passes) |

Two points follow.

1. **Part of this is a layout problem, not an OCR problem.** The stem-plus-year layout (`As at March 31,` over bare year columns) is common in annual reports. A text-layer PDF with that layout also fails FR-005.9 today. OCR only makes it more frequent, because OCR garbles the stem more often.
2. **A failed period check is safe, and on OCR pages it is not what stops a value being trusted.** An OCR field is never `extracted` (FR-005 criterion 11); it is `requires_review` whatever the period check says. What a valid period structure adds is a verified cell assignment for the analyst and the reason `ocr_unconfirmed` in place of `period_mismatch`. This is the value being bought, and it is modest.

The evidence is six pages from two documents and says nothing about how often these layouts occur.

## 2. Options

| Option | Text | Effect on the six tuning pages (an upper bound, from the anchors that were read) |
|---|---|---|
| (a) | **No change.** OCR pages with an unvalidated period stay `requires_review`; the README and memo state that OCR runs often cannot verify the period. | None. |
| (b) **Recommended** | **Analyst-asserted period end for OCR runs.** A new option `--ocr-period-end YYYY-MM-DD` (and the setting `ocr.period_end`) gives the current period end for the pages read by OCR. See 3. | At most 3 of 6 pages (S1 pages 1, 3, 4) have a year anchor to attach it to. S2 has none, so it gains nothing. |
| (c) | **Stem date plus year header.** A written `Month day,` stem in the title or column-header block, with exactly one bare-year header, validates the year header. Applies to OCR pages only, or to every page. | At most S1 page 1; page 3's stem is garbled and an exact match fails. |
| Rejected | **Fuzzy matching of months or digits** to repair OCR noise. OD-15 decided exact matching on OCR text, a misread digit would then change a period silently (2025 as 2026), and the engine's confidence does not show a figure is right (D-15 findings). | |

Option (b) does not depend on the engine reading the date text correctly, which is the thing OCR does worst. Option (c) still does. Option (c) applied to text-layer pages would change Release 1 behaviour and the frozen held-out configuration's reading of the same documents; this draft does not propose that.

## 3. Specification changes under option (b) (what would be applied)

### 3.1 FR-001A: new item, "Period asserted by the analyst"

> 10. **Period end asserted by the analyst (v0.4.47).** With `--ocr`, the analyst may give the current period end of the statement pages read by OCR with `--ocr-period-end` (an ISO date) or `ocr.period_end`. It applies only to pages read by OCR; a page with a text layer is validated as before. It is refused without OCR (see 3.4). The date is recorded in the manifest `ocr` block and shown in the memo's section 2 with the analyst label, as the basis assertion is.

### 3.2 FR-005.9: a new accepted source for OCR pages

> - **Asserted current period (v0.4.47).** On a page read by OCR, a year-only or financial-year header whose year (the later year, for `2024-25`) equals the year of the asserted period end is valid as the current period, with the asserted date as its period end. The conditions of the earlier bullets for the comparative, the code-derived comparative and the older year-columns then apply with that period as the validated current period (including the 28 and 29 February exclusion). The page must still print the matching year header: the assertion supplies the day and month, never the column. The period evidence records the method `analyst_assertion`, the header as printed, and the asserted date; it has no page quote, and this is the one exception to "a quote from a statement title or column header" in this criterion. A page with no matching year header stays unverifiable (`period_mismatch`).

### 3.3 Memo

Section 2 gains one line when an assertion was used. A field on such a page carries the analyst label for its period in section 7, beside its OCR label. The traceability check accepts the analyst label for a period under this method and for no other.

### 3.4 Error and exit code

`--ocr-period-end` without `--ocr`, or a value that is not an ISO date, is a usage error. The draft proposes reusing the existing usage error with a new message rather than adding a code. If a distinct code is wanted it would be a twenty-first, with its own SC-09 case.

### 3.5 Not changed

Text-layer period validation, OCR evidence rules (an OCR field is still never `extracted`), the image-only test, `ocr.dpi` (v0.4.46), the column margin and split-gap settings, exact matching of labels (OD-15), and any held-out configuration.

## 4. Risks

* The assertion is only as good as the analyst who gives it. A wrong date makes a wrong period look verified on the page, though the field is still `requires_review` and still asks for a check against the page image. The memo labels the period as analyst-supplied.
* A year header the engine misreads (for example `2025` as `2026`) is matched against the asserted year and fails safe, as it does now.
* One run covers one asserted date. A document whose OCR pages belong to different periods needs separate runs.
* The benefit is bounded by how many pages print year headers the engine reads (3 of 6 here, from 2 documents).

## 5. What the owner is asked to decide

1. Option (a), (b) or (c), or none for now.
2. Under (b): whether to reuse the usage error (3.4) or add a code.
3. Whether more tuning scans (follow-up (c) of the earlier list) should come first, since six pages from two documents is a thin basis for any rule.

## 6. Implementation if approved

A small step with tests and a mutation check: the option and setting, the resolver branch for OCR pages, the period-evidence method, the manifest and memo lines with their traceability check, and synthetic scans through the fake engine for a matching year, a non-matching year, a February end, a text-layer page in the same run, and no OCR. Real scans stay out of the repository; a re-run on S1 and S2 would be counts only.
