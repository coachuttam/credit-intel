# Proposal: a polished PDF report with charts alongside every memo

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-27, with the answers in section 10. Nothing is built, and `docs/PRD.md` is unchanged (0.4.55).** The PRD draft is `docs/PRD_v0.4.56_report_draft.md`; code follows only after the owner applies it. |
| Drafted | 2026-10-27, at the owner's request ("every run ... produce a polished, professional-looking report alongside the current plain memo.md") |
| Kind | A new presentation step after the memo. No change to extraction, validation, evidence, calculation, rules, labelling or the memo text. |

## 1. What is proposed

Every run writes **`report.pdf`** next to `memo.md`, `results.json` and `manifest.json`. It is the same memo, typeset: a cover block, running headers and page numbers, readable tables, and **two small charts**. It is produced for every run, whether the fields are read from the text layer or by OCR.

## 2. Where it fits in the pipeline

```
... rules_evaluated -> memo_generated (memo.md text, checked by problems()) -> [ report rendered ] -> exported
```

- **After the memo, before the files are written.** The renderer takes the **same memo text that `render_memo` returns** (the string that is also written as `memo.md`) and the **same `results.json` data**. It never reads the document, the model's replies or the evidence directly.
- **It consumes the memo, it does not re-create it.** The memo is parsed (CommonMark, with `markdown-it-py`, already a dev dependency) and each element is typeset. A second renderer that rebuilt the sections from `results.json` would be a second copy of the labelling rules and could drift from the first; consuming `memo.md` makes the PDF text equal to the memo text by construction.
- **Charts come from `results.json`** (section 5), not from the memo's Markdown.
- **Offline re-render (small extra):** `python -m credit_intel.report <run-folder>` rebuilds `report.pdf` from an existing folder's `memo.md` and `results.json`, with no model call and no document read.

## 3. Format

- **PDF is the priority.** Library: **reportlab** (page layout, tables, vector graphics). It is already used in the test suite, is pure Python, needs no system libraries, and with its fixed-date mode (`invariant`) gives **byte-identical PDFs** for the same input, in step with the reproducibility rule for the other files.
- **Not WeasyPrint** (needs Pango and other system libraries) **and not Pandoc** (an external program): both are harder to install and to make deterministic.
- **DOCX is realistic, but second.** `python-docx` (pure Python) could walk the same parsed memo and the same chart data. It would need charts as raster images (reportlab alone cannot make them; matplotlib could, see section 5) and a different way to check the output. I estimate it at about 60 % of the PDF's effort once the PDF exists, and I would not start it with the PDF.

## 4. What it must preserve (and how that is checked)

| Must keep | How the PDF keeps it | How it is checked |
|---|---|---|
| Every origin label: `[SOURCE: p.N]`, `[CALCULATED: id]`, `[RULE: RI-xxx]`, `[ANALYST-PROVIDED]`, `[UNVERIFIED]` (and `[OCR p.N, confidence c]`) | Printed as text exactly as in the memo, in a distinguishing style (a coloured tag), never replaced by an icon or dropped | Extract the PDF's text and compare: every label in the memo is in the PDF, in the same order, and no label is in the PDF that is not in the memo |
| The draft banner "DRAFT — generated for human review. Not a credit decision. Verify all figures against the cited sources." | On the first page in the same words, **and** repeated in the footer of every page (an addition to the memo, in the same words) | The text check, plus a check that the footer is on every page |
| The full limitations section (section 9), word for word | Typeset as the memo has it; never shortened or summarised | The text check (section 9 equals the memo's) |
| OCR fields' visibility: the `ocr_unconfirmed` review reason, the OCR label with its confidence, the OCR legend line and the section 2 disclosure | Same text, same places; a page that is read by OCR is marked in the cover block ("OCR was used on pages ...") using the section 2 line | The text check; a test on a run with OCR fields |
| Every value as shown, with its rounding and scale | Strings are copied from the memo, never reformatted | The text check on every number in the memo's tables |
| The legend of origin labels | A key printed once near the start | The text check |

**Presentation only:** no label is added to a value, none removed, and no value is shown that the memo does not show. A **report check** (the analogue of the memo check, K.10) runs on every report before it is written. A report that fails it is an internal error like a memo that fails K.10: exit code 1, and no folder that looks complete.

## 5. Charts

**Which charts** (two panels, drawn from `results.json` only):

1. **Revenue and net profit, current period against comparative period** (paired bars, one pair per period), when the fields are extracted for both periods.
2. **Current ratio (MET-03) and interest coverage (MET-05), comparative to current** (two small panels, each on its own scale, because the two ratios differ by a factor of ten or more). Two points per ratio, so a dot-and-line, not a claim of a trend beyond two periods.

**Library.** You suggested matplotlib. My recommendation is instead **reportlab's own graphics module**:

| | reportlab graphics (recommended) | matplotlib |
|---|---|---|
| New dependency | None beyond reportlab, which the PDF needs anyway | matplotlib plus numpy and about seven more packages, tens of MB |
| Output in the PDF | Vector, text is real text (so the PDF text check sees every chart number) | Embedded as an image or converted vector; its numbers are not extractable text unless drawn as text |
| Determinism | Same reportlab version gives the same bytes | Output varies with version, fonts and backend |
| Looks | Plain and clean, fewer options | Richer; easier to get a polished look |

If you prefer matplotlib's look, or want DOCX later (it needs images), it is workable: I would draw it to SVG with the labels as text, pin the version and say so. It is your call.

**Traceability of every chart value (your requirement).**
- Each bar or point is read from the **same `results.json` record that the memo's table row is built from**, by field ID or metric ID. The data behind each chart is a small list of `(ID, displayed string, origin label)`.
- The number printed on a bar is **the memo's own displayed string** for that field or metric (the same rounding, half to even; the same scale and currency text). The bar's height is drawn from the stored Decimal; no number is computed for the chart.
- Under each chart is a source line with the origin labels and IDs of what it plots, for example `[SOURCE: p.12]` for the two revenue values and `[CALCULATED: MET-03]` for the ratio. The ratio and coverage points carry `[CALCULATED: ...]`, the revenue and profit bars carry `[SOURCE: p.N]`.
- **No number appears in a chart that is not also in the memo text.** The report check extracts every number printed in each chart and requires it to appear in the memo with the same label. A chart with an unmatched number fails the check.
- **What is not plotted:** a field that is not `extracted` (including every OCR-read value, which is `requires_review` with `ocr_unconfirmed`), or a ratio that is not defined. That slot shows "not plotted: see section 7" in the same words the memo uses, so a reviewed-but-unverified value is not given visual weight. If you would rather show OCR values as hatched bars with their `[OCR ...]` label, say so; I recommend not.

## 6. A flag, or on by default? And what if the report cannot be built?

**On by default, for every run**, with one opt-out flag **`--no-report`**. There is no `--report pdf` flag, because the default is on.

**A report failure never fails the run (owner's decision).** `memo.md` is the authoritative output and the PDF is a presentation-layer addition:
- If the report cannot be built or does not pass its own check, **the run completes normally**: exit code 0, `memo.md`, `results.json` and `manifest.json` written as they are today, **no `report.pdf` in the folder** (never a partial or unchecked file).
- A **clear warning** goes to standard error and the log, with a fixed reason word and nothing from the document, for example `WARNING report not written (check_failed); memo.md is complete`. The reasons are a closed list: `render_error`, `check_failed` (the report's text does not equal the memo's), `glyph_missing` (the font lacks a character), `timeout`.
- The **manifest records** `report: {"status": "written" | "failed" | "skipped", "reason": ...}` (name, size and SHA-256 when written; the reason word when failed; `skipped` for `--no-report`), so a folder without `report.pdf` always says why.
- **No new error code, no change to any exit code.** The memo check (K.10) is unchanged: a memo that fails it is still an internal error. Only the report check is non-fatal.
- **A hang cannot hold the run either.** The render runs under a fixed time limit (a constant in the code, not a setting, proposed at 120 s), so a stuck renderer ends as `timeout` and the run completes.
- The warning is the only change a user sees on failure; tests pin every one of these.

## 7. Risks to settle in the design

- **Untrusted text in the PDF.** Document text (quotes, names) reaches the report. reportlab's paragraph mini-markup can load images and links from tags in the text, so the renderer must **never pass document text through it as markup**: it builds flowables from the parsed memo and escapes everything, and a test injects `<img src=...>`, `<a href=...>` and `&` sequences. This is the main security point.
- **Fonts and symbols.** reportlab's built-in fonts cannot print `₹` or typographic quotes. The renderer needs an **embedded font with wide coverage** (DejaVu Sans or Noto Sans, both free licences, about 1 MB for the two weights, committed with its licence file). A character the font lacks must be caught by a check, not printed as a blank box.
- **Failure handling:** see section 6. A failed report never fails the run; it is warned, recorded in the manifest and absent from the folder. (An earlier draft of this proposal had a failed render fail the run; you decided against it.)
- **Reproducibility.** Same inputs give a byte-identical `report.pdf`, apart from the run ID and times the memo itself carries. Tested in fresh processes, as for the other files.
- **Dependencies.** `reportlab` and `markdown-it-py` move from dev to runtime (`uv add`). No system library.
- **Writer change.** `write_run` writes text files only; it needs a bytes path for the PDF, and the run must still publish atomically when the PDF is absent. A small, tested change.
- **Run folder.** The folder now holds four files; tests that assert exactly three files change, and the manifest records `report.pdf` (name, size, SHA-256) and the renderer's package versions.

## 8. Build size and effort

I would split it into steps like the OCR and SEC-12 builds, each approved separately:

| Step | What | Rough size |
|---|---|---|
| 0 | A PRD draft (a new requirement for the report; FR-010 now says "Markdown export"; the run folder and manifest; examples; version bump), for your approval | a document |
| 1 | The typesetting core: parse the memo, banner, headers and footers, tables, tags, embedded font and glyph check, injection tests | about 500 lines of source, about 40 tests |
| 2 | The report check (PDF text equals memo text; labels, banner, section 9, OCR visibility; footer on every page) and mutation checks | about 200 lines, about 30 tests |
| 3 | The two charts, their data list, the not-plotted rule and the chart-to-memo number check | about 250 lines, about 25 tests |
| 4 | Export integration: `report.pdf` in the run folder, bytes writer, manifest entry, `--no-report`, the offline `report` command, reproducibility test, README | about 150 lines, about 20 tests |

**About four to five sessions of the size of SEC-12 steps 1 to 3** (roughly 1,100 lines of source and 1,500 of tests altogether). DOCX would be one further step (about 60 % of step 1 and 2 together), not started here.

## 9. Before or behind Phase 6?

It is independent of the API: it reads only the memo and `results.json`, and touches nothing in extraction. Phase 6 (and 7) are deferred, so **it can go next without waiting for anything**. If Phase 6 is built later, the API would simply serve `report.pdf` from the same run folder, so building the report first makes that easier, not harder. My view: build it before Phase 6.

## 10. Owner's answers (2026-10-27)

| Question | Answer |
|---|---|
| Direction | Approved: PDF first, consuming `memo.md`, DOCX later. |
| Chart library | **reportlab graphics**, not matplotlib. |
| OCR and unverified values in charts | **Excluded**: the same principle as OCR never feeding a derived metric, extended to visualisation. |
| Default and flag | **On by default**, `--no-report` opt-out. |
| Failure handling | **A report failure must never fail the run.** `memo.md` is authoritative; on a build failure, log a clear warning and complete normally (section 6). |
| Footer banner on every page | **Approved.** |
| Next | Write the PRD draft (`docs/PRD_v0.4.56_report_draft.md`), for approval before any code. |
