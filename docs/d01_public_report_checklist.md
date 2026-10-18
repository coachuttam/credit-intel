# D-01 Public-Report Validation Checklist (B-133)

**Purpose:** complete the public-report half of decision D-01 (PRD L.2.1), record the evidence needed to decide OD-1 (how values are matched to period columns), and collect tuning evidence for OD-3 and OD-7.

**Status:** prepared 2026-10-13. Evidence was collected on 2026-10-13 and the findings summary is in `PROGRESS.md` (B-133 entry). Checklist verification and owner review are **outstanding** (see §7 and "Known gaps" below). D-01 is **not** marked met or not met, B-133 is not closed, OD-1 is open, and the Phase 1 exit remains incomplete.

**This is an observation exercise.** It does not change extraction logic, dependencies, or locator settings, and it does not decide OD-1.

---

## 1. Documents required

| # | Requirement |
|---|---|
| R1 | Annual report of an **Indian listed non-financial company**: Ind AS statements in **₹ crore or ₹ lakh**, containing **both standalone and consolidated** statements |
| R2 | Annual report of a **second non-financial company with a different layout**, e.g. an IFRS report in another currency (USD, GBP, EUR) in thousands or millions, ideally with year-only column headers (`2025`, `2024`) and/or minus-sign negatives |
| Both | Official source (company website or stock exchange); text-based PDF with selectable text, not a scan; not a bank, insurer, or NBFC (PRD F.1) |

**Handling rules:**
- Store the PDFs in `private/` (git-ignored). **Never commit them**, and never copy whole pages, statements, or reports into the repository.
- Both documents are **tuning-set** documents from the moment they are inspected (PRD O.2). Record that assignment with the date when the documents are chosen. They must **never** later be presented as held-out evaluation data.
- Do not adjust phrase lists, settings, or code during this exercise. Record proposals only.

## 2. Where observations go

| Record | Location | Committed? |
|---|---|---|
| Document metadata (§3) and per-row observation log (§5), including actual extracted text | `private/d01/<document-id>.md` | **No** (git-ignored) |
| Findings summary (§7): counts, failure categories, page numbers, short figure strings only | `PROGRESS.md` (commit 5 entry) | Yes, after review |
| Tuning-set assignment | `tests/eval/` (PRD O.2), when the evaluation dataset is created | Yes |
| New reproducible behaviour | A **synthetic** test in `tests/integration/test_table_extraction.py` that reproduces it without the real PDF | Yes |

Use Markdown or JSON for any recorded table. CSV and XLSX files are ignored by `.gitignore`.

## 3. Per-document metadata

Record the following for each document:
- **Document ID:** `R1` or `R2`.
- **Company and reporting year.**
- **Source URL and retrieval date.**
- **File SHA-256 and physical page count:** from `ingest()` (`FileInfo`).
- **Whether ingestion succeeded:** if not, the G.1 error code. Note any bytes before `%PDF-` (OD-7).
- **Tuning-set assignment and date.**

## 4. Pages to inspect

For R1: standalone balance sheet, standalone statement of profit and loss, consolidated balance sheet, and consolidated statement of profit and loss, including every continuation page. For R2: its balance sheet (statement of financial position) and income statement.

For each statement page, record:
- **Page numbers:** the physical page number (1-based, as used by the code), the number printed in the footer, and the PDF page label (`PageText.page_label`, or `None`).
- **Statement:** type, and the title exactly as printed.
- **Basis:** the basis as printed, and whether `check_statement_basis` would establish it from the title block (H.4.6). For example, a basis word on a separate line.
- **Locator:** did `locate_statements()` select the page, with what score and matched phrases? Also record false positives (contents pages, notes) and missed pages (OD-3, SC-12).
- **Column headers:** as printed, the extracted header line(s), and whether each period date is in a form accepted by FR-005.9.
- **Scale and currency declaration:** as printed, and as extracted. Record exactly how `₹` (or `Rs.`, `INR`) comes out, since the synthetic tests could not cover it.
- **Layout notes:** multiple columns on one page, a table split across pages, rotated pages, landscape pages, and extraction time per page.

## 5. Rows to check on each statement page

**Fields:** check every row that is present for these fields:
- revenue from operations;
- finance costs;
- profit before tax;
- profit for the year;
- total current assets;
- total current liabilities;
- non-current borrowings;
- current borrowings;
- current maturities of long-term borrowings (if presented separately);
- total equity.

**Special rows:** also check up to five rows that contain a blank cell, a nil dash, a bracketed negative, a wrapped label, or a note reference.

For each row, record in the private log:

| Item | What to record |
|---|---|
| Row ID | e.g. `R1-p112-r05` |
| Expected | Label, note reference, current figure, and comparative figure, **read by eye from the rendered PDF page** |
| Extracted | The exact line(s) produced by `ingest()` for that row |
| Section heading | The nearest heading above, as extracted (FR-005.10) |
| Result | One category below |
| Label check | Would the label match the FR-005.10 / H.3 label phrases? If not, the proposed phrase (a proposal only) |
| Word positions | **Helps / Does not help / Not needed / Unclear.** Probe with pdfplumber's `extract_words()` in a scratch script outside the repository: does each figure's horizontal position fall under the correct period header? |

**Result categories:**
- `OK`: the row is on one line, its figures are in column order, and every character is kept.
- `MERGED`: two figures are joined into one token.
- `SPLIT`: one figure is broken by inserted spaces.
- `OFF-ROW`: a figure is on a different line from its label.
- `REORDERED`: figures are not in column order.
- `LOST`: a figure or character is missing or altered (including `₹`, a sign, or a dash).
- `LABEL-WRAP`: the label spans lines and the figures sit on a line without the full label.
- `OTHER`: describe it.

## 6. Questions this evidence must answer

| Question | Informs |
|---|---|
| Does default pdfplumber text keep statement rows and column order on real reports? How many rows fall into each failure category? | D-01 |
| Where text order fails (blank cells, `OFF-ROW`, `REORDERED`), do word positions place each figure under the right period header? Where do word positions fail too? | OD-1 |
| Do the FR-013 initial settings select every statement page, without contents or notes pages? | OD-3 (tuning evidence only) |
| Do real column headers and scale declarations fit FR-005.9 and FR-005.8? | FR-005.8–.9 phrase and format lists (tuning proposals only) |
| Does every page reference stay a correct physical page number? | FR-002.2, FR-005 |
| Do the PDFs start with `%PDF-`? | OD-7 |

## 7. Completion criteria for B-133

- [ ] Both documents meet §1, are stored in `private/`, and are recorded as tuning-set documents. *[not ticked: verified retrieval dates and exact-source confirmation outstanding; the assignment file does not exist yet]*
- [ ] Every statement page in §4 is inspected, with all §4 fields recorded. *[not ticked: the page set matches the summary, but the per-page fields are in the private log and were not independently verified]*
- [ ] Every row in §5 is classified, with a word-position result for each non-`OK` row. *[not ticked: 34 rows are recorded as classified in the private log (arithmetic reconciled; classifications not independently verified). The log records a word-position result for each LABEL-WRAP row (R1 `R1-p195-r03` "Not needed"; R2 `R2-p38-r08` "Mixed"), and the owner spot-checked both (see `PROGRESS.md`, 2026-10-17). The owner review is not complete and no waiver is approved]*
- [ ] The §6 questions are answered in a findings summary in `PROGRESS.md`. The summary gives counts per category and failure examples using short figure strings only, and states what the two-document sample cannot show. *[not ticked: the physical-to-printed mapping is confirmed for all ten inspected pages, but whether pipeline citations use physical page numbers is unverified, so the §6 question is only partly answered (see Known gaps)]*
- [ ] Any reproducible failure is added as a synthetic test, without the real PDF. *[not ticked: the SPLIT mechanism is covered by B-132, and the LABEL-WRAP extraction layout is pinned by B-136 (two synthetic characterisation tests of extracted text, added 2026-10-18); neither tests a column-mapping method, and the box is left for the owner review]*
- [x] `tests/BEHAVIOURS.md` B-133 is updated to reflect what was actually evaluated. *[ticked: the B-133 row records the evaluation and its open status]*
- [ ] The project owner reviews the findings. **Only then** is D-01 marked met or not met, and OD-1 put forward for decision. *[not ticked: owner review has not been recorded]*

### Known gaps (recorded in the latest documentation review)

- **Source metadata:** the owner states (2026-10-18) that the source URLs for R1 and R2 are unavailable; none is recorded. The owner also states (2026-10-18) that the retrieval dates are unavailable; none is recorded or inferred (file system dates, the assignment date and the hash-verification date are not retrieval dates). The exact source file for each report is unconfirmed, especially for R2 (the log calls it an annual-report extract).
- **Private evidence:** a later review read `private/d01/R1.md`, `R2.md` and `wordpos_probe.txt`; the row counts reconcile arithmetically, but the per-page and row-level evidence is not independently verified except for the owner's two LABEL-WRAP spot-checks (reported for 2026-10-17). The logs carry no in-file timestamps (file-system times are described in the next item).
- **Original inspection-time hashes and page counts:** the private logs record SHA-256 values equal to the owner-confirmed current hashes and page counts of 369 and 80, but without in-file timestamps and without labelling the hashes as `ingest()` output. File-system times for the three files are on 2026-10-13 (`R1.md` created and last modified 12:02:27 +0530; `R2.md` created 12:02:27, last modified 12:03:26; `wordpos_probe.txt` created 12:01:05, last modified 12:03:15), and the owner confirms the files were not copied, restored or re-synced after 13 October (recorded 2026-10-17). This supports, but does not conclusively prove, that the lines were written in the 13 October session; it does not show they were copied from `ingest()` output or when the inspection began. They are therefore not conclusively verified. The log date 2026-10-13 is the assignment date, not a recorded inspection date. The explicit physical-page-number answer, source URLs and retrieval dates also remain unresolved, and the two LABEL-WRAP spot-checks do not validate the other 32 classified rows.
- **Provenance disposition (owner decision, 2026-10-18, Option A):** the findings are retained with an explicit provenance limitation instead of rerunning the inspection (Option C). This is not an acceptance of the findings, a D-01 outcome or a closure of B-133, and no checklist box is ticked or waived. The limitation text is in the B-133 entry of `PROGRESS.md`. Source URLs and retrieval dates remain unavailable unless the owner supplies them.
- **Physical page numbers:** the §6 question "does every page reference stay a correct physical page number?" is only partly answered. Owner checks (2026-10-17 and 2026-10-18) confirm the physical-to-printed mapping for all ten inspected statement pages (R1 194–197 and 274–277; R2 36 and 38; the footers for R2 36 and 38 were reported as matching, not itemised). Whether pipeline-generated citations use physical page numbers is not verified (no pipeline output has been examined). See `PROGRESS.md`.
- **R1 pages 194–195 owner check (reported 2026-10-17):** the owner visually confirmed 194 → printed 222 and 195 → printed 223 and that p195 carries a separate `Total equity and liabilities` row (`1,24,936`, `1,14,950`) alongside p194's `Total assets` row. The probe entry for it is therefore consistent with the PDF, was omitted from the R1 row log, and is an **unlogged candidate** row (not added, not classified; the reported counts of 34 classified rows are unchanged until it is formally added and classified). This confirms the physical-to-printed mapping (question A) for these two pages only; whether pipeline citations use physical or printed page numbers (question B) remains unverified. See the `PROGRESS.md` B-133 entry. B-133 is not closed.
- **LABEL-WRAP rows:** the private log records a word-position result for each (R1 `R1-p195-r03` "Not needed"; R2 `R2-p38-r08` "Mixed"). The owner's spot-check found no contradiction for R1 and confirmed the R2 nearest-column failure (the label's `7,434` assigned to 2025). The column-boundary/distance constraint is not implemented or tested. Two synthetic characterisation tests of the extracted text (B-136, 2026-10-18) now exist; they test no column-mapping method. No waiver is approved.
- **Tuning-set assignment:** `tests/eval/assignments.jsonl` does not exist yet; the assignment is recorded only in `PROGRESS.md` (2026-10-13).
- **Open decisions, unchanged:** D-01 is not marked met or not met; OD-1, OD-3 and OD-10 are open; OD-7 keeps strict `%PDF-` handling; the four specification gaps in `PROGRESS.md` are later-phase inputs; D-14a is not recorded; the Phase 1 exit criterion is incomplete.

**What this sample cannot show:** two reports are not a representative sample. The findings show whether failure modes occur, not how often they occur across annual reports. They are not evaluation results, and must not be reported as extraction accuracy.
