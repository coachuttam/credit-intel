# PRD v0.4.56 draft: a PDF report with charts alongside every memo (specification only)

| Item | Value |
|---|---|
| Status | **Draft. Not applied.** `docs/PRD.md` is unchanged (0.4.55). It needs the owner's word and a version bump before anything is edited, and nothing is built until then. |
| Drafted | 2026-10-27 |
| Source | The owner's approval of `docs/PDF_report_proposal.md` on 2026-10-27, with these answers: reportlab graphics (not matplotlib); OCR and unverified values excluded from charts; on by default with `--no-report`; **a report failure never fails the run** (warn, record, complete with the memo); the footer banner on every page; "write the PRD draft for this". |
| Version | 0.4.56 |
| Kind | A new requirement (FR-015) and the changes it needs elsewhere (FR-010, FR-012, FR-014, dependencies, security, tests). **No change** to extraction, validation, evidence, calculation, rules, labelling or the text of the memo. Implemented after Release 1, in steps, each approved. |

## 1. Points the approval leaves open (my proposals, for you to confirm or change)

| # | Point | Proposal |
|---|---|---|
| 1 | **The two dependency rows** that now conflict. The PRD says reportlab is "never a runtime dependency" and markdown-it-py is "dev only". | Both become runtime dependencies (SEC-11: a documented reason, pinned in `uv.lock`). Rows changed below. |
| 2 | **Render time limit.** "Never fail the run" must include "never hang the run". | A fixed limit of 120 s in the code (not a setting), after which the report is abandoned as `timeout`. |
| 3 | **Offline re-render command.** In the proposal as a small extra. | Included as criterion 11, writing to a **named file outside the run folder** and refusing to overwrite, so no run folder is ever changed after it is written (FR-010.4). Drop it if you prefer. |
| 4 | **The manifest of a run without a report.** | `report` entry with `status` and a closed-list `reason` (criterion 7), so a folder without `report.pdf` says why. |
| 5 | **Where it sits in the processing states (FR-011).** | No new state. The report is built between `memo_generated` and `exported`; a failure there does not enter `failed`. |

## 2. Exact text changes if approved

### 2.1 New requirement, after FR-014 (before Section H)

> ### FR-015 — PDF report (Should; specified in v0.4.56, implemented after Release 1)
>
> **Behaviour:** every run also writes `report.pdf`, the memo typeset for reading, with two charts. The report is a **presentation layer**: `memo.md` stays the authoritative output, and nothing about extraction, validation, evidence, calculation, rules or labelling changes.
>
> **Acceptance criteria:**
>
> 1. **Input and place.** The report is built after the memo is generated and has passed the check of FR-010 criterion 5, from the memo text that is also written as `memo.md` and the data that is written as `results.json`. It reads nothing else: not the document, the model's replies or the evidence directly. It adds no value, no label and no sentence of analysis.
> 2. **On by default; opt-out.** It is built for every run, whether the fields were read from the text layer or by OCR. `--no-report` skips it, and the manifest records `skipped`.
> 3. **What it preserves.** Every origin label (`[SOURCE: p.N]`, `[CALCULATED: id]`, `[RULE: RI-xxx]`, `[ANALYST-PROVIDED]`, `[UNVERIFIED]`, and `[OCR p.N, confidence c]`), in the memo's order and words; the draft statement of K.0, on the first page and in the footer of **every** page, in the same words; the legend of labels; section 9 (limitations and human-review requirements) **word for word**; for a run with OCR, the OCR label, the `ocr_unconfirmed` review reason, the OCR legend line and the disclosure sentences of K.0; and every value as the memo shows it (the same rounding, scale and currency text). The only additions are a cover block (run ID, time and basis as in the memo header), page numbers and the running footer.
> 4. **Charts.** Two panels, drawn from `results.json`: (a) revenue and net profit, current period against comparative period; (b) the current ratio (MET-03) and interest coverage (MET-05), comparative to current, each on its own scale. Rules:
>    - Each plotted point is the stored value of one field or metric, and the number printed on it is **the memo's displayed string** for that field or metric. The chart computes no number.
>    - A source line under each chart gives the origin labels and IDs of what it plots (`[SOURCE: p.N]` for fields, `[CALCULATED: id]` for ratios).
>    - **Not plotted:** a field whose status is not `extracted`, **any field read by OCR**, a metric that is not defined, and any value that rests on a field excluded by these rules. The slot shows "not plotted" with the memo's own words for the reason. This is the rule that an OCR value never feeds a derived metric, extended to visualisation.
>    - **No number in a chart that is not also in the memo text** with the same label (checked by criterion 5).
> 5. **Report check.** Before `report.pdf` is written, a deterministic check (no model) extracts the report's text and verifies: every label of the memo is present in the report and no label is added; the draft statement is on the first page and in every page's footer; section 9 equals the memo's; for an OCR run the OCR items of criterion 3 are present; every number printed in a chart appears in the memo text with the same label; every character is in the embedded font. A failure is handled by criterion 7.
> 6. **Untrusted text.** Text from the document, the analyst or the model-free template is **never interpreted as markup** by the PDF library: the renderer builds its elements from the parsed memo, escapes all text, and passes no document text to any facility that loads images, links or files. Tests inject markup, tag sequences and control characters in field values, quotes, borrower names and notes.
> 7. **A report failure never fails the run.** If the report cannot be built, or does not pass criterion 5, or takes longer than a fixed 120 s, then: the run **completes normally** (exit code 0; `memo.md`, `results.json`, `manifest.json` written as without a report); **no `report.pdf`** is written (never a partial or unchecked file); a **warning** goes to standard error and the log with a fixed reason word and nothing from the document, for example `WARNING report not written (check_failed); memo.md is complete`; and the manifest records `report: {"status": "failed", "reason": ...}`. The reasons are a closed list: `render_error`, `check_failed`, `glyph_missing`, `timeout`. There is no new error code and no change to any exit code. The memo check (FR-010 criterion 5) is unchanged: a memo that fails it is still an internal error.
> 8. **Files and manifest.** `report.pdf` is published in the same atomic step as the other files; a run folder without it is complete. `manifest.json` records `report`: `status` (`written`, `failed` or `skipped`), `reason` for `failed`, and for `written` the file name, size, SHA-256 and the versions of the packages that built it.
> 9. **Reproducibility.** The same memo and results give a byte-identical `report.pdf` (the library's fixed-date mode), apart from the run ID and times the memo itself carries. A test runs two fresh processes.
> 10. **Format and library.** PDF, built with reportlab (page layout, tables, vector charts) from the memo parsed as CommonMark with markdown-it-py, with an embedded font that covers the rupee sign and typographic quotes (D-16). DOCX is out of scope here (Section S); it may be specified later from the same parsed memo.
> 11. **Offline re-render (Could).** `python -m credit_intel.report <run-folder> --output FILE` builds a report from an existing folder's `memo.md` and `results.json`, with no model call and no document read, under criteria 3 to 7. It writes to the named file, never inside a run folder, and refuses to overwrite an existing file.

### 2.2 Other changes

1. **FR-010 criterion 1:** add *"`report.pdf` (FR-015) is a fourth file, written with the others when it is built; it is not part of the authoritative output, and a run without it is complete."* Criterion 3 (atomic writes) and 4 (never overwritten) apply to it.
2. **FR-012 criterion 1:** add `report` to what `manifest.json` records (FR-015 criterion 8). Criterion 2: *"`report.pdf` is byte-identical under the same conditions, excluding the run ID and times"* (FR-015 criterion 9).
3. **FR-014 criterion 1:** add `[--no-report]` to the command and one line: *"`--no-report` skips the PDF report (FR-015); the manifest records `skipped`."*
4. **Dependencies table (Section L):** the `reportlab` row changes from "Yes (dev only) ... Never a runtime dependency" to *"Yes. PDF report layout and vector charts (FR-015, D-16); also generates synthetic test PDFs. Runtime from v0.4.56."* The `markdown-it-py` row from "Yes (dev only)" to *"Yes. Parses the memo in tests and, from v0.4.56, for the PDF report (FR-015)."* Add the embedded font (DejaVu Sans or Noto Sans, a free licence, committed with its licence file). SEC-11: the documented reason is FR-015.
5. **Decisions (Section L):** add **D-16** *"The PDF report is built with reportlab from the parsed memo; charts use reportlab's own graphics, not matplotlib (no numpy or image stack, vector output whose numbers are extractable text, deterministic). Decided by the owner, 2026-10-27."*
6. **Section M:** add **SEC-13** *"Untrusted text in the PDF report: document, analyst and profile text is escaped and never interpreted as markup or as a request to load a file or link (FR-015 criterion 6)."*
7. **NFR-06 (Reproducibility):** add the report to the byte-identical outputs.
8. **Section S (Out of scope):** add *"DOCX or other report formats (a PDF report is specified in FR-015; DOCX may follow)."*
9. **Section Q:** a note that FR-015 is a post-Release-1 addition, independent of Phase 6; no phase table row changes.
10. **Section K:** a sentence that the PDF report presents the memo and changes none of K.0 to K.10. K.10's rules still apply to the memo; the report check is FR-015 criterion 5.
11. **Appendix B.6:** examples 155 to 160: (155) a normal run → `report.pdf` with the banner on every page, all labels, two charts; (156) a run with OCR fields → the OCR labels and `ocr_unconfirmed` shown, the OCR values not plotted; (157) `--no-report` → no file, manifest `skipped`; (158) the renderer raises an error → exit 0, memo complete, warning `render_error`, no `report.pdf`, manifest `failed`; (159) a report whose text differs from the memo → the same, `check_failed`; (160) a borrower name containing markup → printed as text, nothing loaded.
12. **Revision history:** a 0.4.56 row. **Version and Status cells** in Section A.

## 3. What is not changed

Extraction, validation, evidence, calculations, risk rules, the memo text and its labelling rules, K.10, the error catalogue (no new code) and every exit code, Release 1's approval, the parse limits, and Phases 6 to 8.

## 4. Implementation order if approved (each step separately approved)

1. Apply this draft as v0.4.56 (documents only).
2. **Typesetting core:** parse the memo, banner and footer, headers, tables, label tags, embedded font and the glyph check, markup-injection tests. About 500 lines, 40 tests.
3. **Report check and non-fatal failure:** the check of criterion 5, the closed list of reasons, the 120 s limit, the warning, the manifest entry, mutation checks. About 250 lines, 40 tests.
4. **Charts:** the data list, the not-plotted rule, the source lines and the chart-to-memo number check. About 250 lines, 25 tests.
5. **Export integration:** bytes path in the writer, `report.pdf` in the atomic publish, `--no-report`, the offline command, the reproducibility test, README. About 150 lines, 20 tests.

About four to five sessions of the size of SEC-12 steps 1 to 3, as in the proposal.

## 5. What I need from you

1. Confirm or change the five points in section 1.
2. "Apply" to apply this as v0.4.56 (or "apply with changes: ...").
