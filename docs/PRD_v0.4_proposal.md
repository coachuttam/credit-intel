# PRD v0.4 Proposal — Amendments from Real-Report Validation (revision 3)

| Item | Value |
|---|---|
| Status | **Proposal only — awaiting project-owner review.** Nothing here is approved. `docs/PRD.md` v0.3 remains authoritative until v0.4 is approved. |
| Revision | 3 (2026-10-13). Incorporates the owner's decisions on revision 2: D-13, D-14a, DEC-B, DEC-C, DEC-E, OD-10 and OQ-3 **accepted in principle, subject to the acceptance criteria below**; DEC-A, DEC-D, OD-9 and D-01b **kept open**. Accepted-in-principle items become approved only when v0.4 is applied to `docs/PRD.md` and approved. |
| Based on | `docs/PRD.md` v0.3; B-133 findings committed in `e031a10` (`PROGRESS.md`); `docs/d01_public_report_checklist.md`; code at `e031a10` |
| Evidence | Two **tuning-set** reports (R1 Infosys 2024-25, R2 Microsoft FY2025): 10 statement pages, 34 rows checked by eye. It shows that failure modes occur, **not how often**. **No general extraction-accuracy figure is claimed.** Source URLs and retrieval dates for R1 and R2 are **still outstanding** and must be supplied by the owner. |

**Rules for this document:**
- Every *provisional* setting is derived from these two tuning documents. It may change only with further tuning-set evidence, never with held-out documents (PRD O.2).
- Expected effects on R1 and R2 are **targets for implementation tests on tuning documents**, not achieved or release results.

---

## 1. Summary and decision status

| # | Topic | Proposal | Owner status (rev 3) |
|---|---|---|---|
| 1 | OD-1 (D-13) | A value is assigned to a period column only when column boundaries, row-label separation, numeric validation, and uniqueness **all** hold. Proximity alone never assigns. | **Accepted in principle**, subject to AC-D13 (§3.1) |
| 2 | Split figures (DEC-A) | Automatic reconstruction stays **disabled**. Split fragments are `requires_review`, with the original text and provenance kept. | **Open** |
| 3 | Period dates (DEC-B) | A shared day-month fragment combined with per-column year anchors, taken only from the column-header block or title lines | **Accepted in principle**, subject to AC-B (§3.3) |
| 4 | Three-year statements (DEC-C) | Capture every supported period; use the latest two for Release 1 calculations and memo; disclose every period's disposition | **Accepted in principle**, subject to AC-C (§3.4) |
| 5 | Borrowings (DEC-D) | Evidence needed to prove components do not overlap is specified. A matching total alone is **not** conclusive. | **Open** |
| 6 | Locator (DEC-E) | Separate title-page and continuation-page rules, each testable on synthetic fixtures; page-range override kept | **Accepted in principle**, subject to AC-E (§3.6) |
| 7 | Basis (OD-10) | Explicit evidence (title or footnote), or an explicit, page-scoped, auditable analyst assertion | **Accepted in principle**, subject to AC-OD10 (§3.7) |
| 8 | D-01a / D-01b (D-14) | D-01a: keep pdfplumber provisionally. D-01b: pipeline acceptance **not met**; exact conditions listed in §4. | D-01a **accepted in principle**; D-01b **open** |
| 9 | OD-9 | Reported zero, absent line, and unidentifiable line are distinguished. A zero D/E is never computed from missing evidence. | **Open** |
| 10 | OQ-3 | Held-out documents come from companies other than those in the tuning set | **Accepted in principle** |
| 11 | Phase 1 exit | Open until every existing exit criterion, B-120, and the D-01a decision are met | Proposed |

## 2. Shared definitions (new section G.0)

These are stated once and used by FR-005.7, FR-005.9, FR-005.11, FR-013 and H.5. Each is defined only from extracted words and lines, so **no definition depends on another rule's output**. That avoids circular rules.

| Term | Definition |
|---|---|
| **Word** | A word from `TextExtractor.extract_words` (§3.9): text, `x0`, `x1`, `top`, `bottom`, and 1-based physical page number |
| **Line** | Words grouped by vertical position using the extractor's line tolerance (pdfplumber default 3pt), ordered by `x0` |
| **Numeric token** | A word matching `^[(]?[-−–]?[0-9][0-9,]*([.][0-9]+)?[)]?$`, or a lone `)`. A currency symbol (`$`, `₹`) is a separate word and is not a numeric token. |
| **Nil token** | A word that is exactly `-`, `–`, `—`, or `nil` (case-insensitive) |
| **Figure word** | A numeric token containing a thousands separator followed by digits, a decimal point, or enclosing brackets. **Not** figure words: four-digit years, day-month fragments such as `31,`, and plain integers. |
| **Figure line** | A line containing at least one figure word |
| **Title line** | A line whose normalised text (FR-013 rule 1) **begins with** zero or more configured *title-prefix words*, followed immediately by a configured title phrase, and which appears **above the page's first figure line**. Any text may follow the phrase, e.g. "(contd.)" or "as at March 31, 2025". |
| **Column-header block** | The lines below the last title line (or the top of the page, if there is no title line) and above the first figure line |
| **Period anchor** | In the column-header block: a four-digit year `YYYY`, a financial-year token (`YYYY-YY`, or `FY` followed by `YYYY-YY` or `YYYY`), or a full date (FR-005.9). A full date is an anchor **only if its words are adjacent**: each gap is no larger than the average character width of the words either side. Otherwise its day-month words form a *day-month fragment* and its year is a separate year anchor. For example, R2's "Year Ended June 30," sits at the left with `2025` far to the right. |

Initial title-prefix words (configurable): "consolidated", "standalone", "separate", "comprehensive". The first two were observed in R1 and the fourth in R2; "standalone" and "separate" come from the existing basis phrases.

---

## 3. Proposed amendments

Each subsection gives the affected requirement, proposed wording, rationale, and required regression tests. IDs are preserved. The new IDs are G.0, FR-005.11, H.1.3, D-13, D-14 (with D-01a and D-01b), and the FR-013 rule 3 sub-rules 3a and 3b.

### 3.1 FR-005.7 — Period column mapping (OD-1, D-13: accepted in principle)

**Affected:** FR-005.7 (replaced). OD-1 is resolved when v0.4 is approved.

**Proposed wording:**

> **7. Period column (D-13).**
>
> **7.1 Columns.**
> - Each period anchor (G.0) defines a **period column**. A header word "Note" or "Notes" in the column-header block defines a **note column**.
> - Each column's **region** is `[anchor.x0 − column_margin_pt, anchor.x1 + column_margin_pt]`.
> - The page's column structure is **valid** only if **all** of these hold:
>   - no two regions overlap;
>   - each period anchor produces exactly one region;
>   - the number of period columns equals the number of period ends validated under FR-005.9.
>
>   If the structure is invalid, every field on the page is `requires_review` (`period_not_verified`).
>
> **7.2 Row-label separation.**
> - The **label limit** is the left edge of the leftmost region.
> - On each line, the words lying wholly left of the label limit form the line's **label**.
> - Words in the label are never values, even if numeric. This covers numbers inside wrapped labels.
>
> **7.3 Assignment (all conditions required; proximity alone never assigns).** A word *w* on line *L* is the value of period column *C* **only if all** of the following hold:
> - **(B) Boundary:** *w*'s horizontal extent overlaps *C*'s region and **no other** region.
> - **(R) Row-label separation:** *w* lies wholly right of the label limit, and *L*'s label passes FR-005.10 for the field being verified.
> - **(N) Numeric validation:** *w* is a nil token, or a numeric token that parses under FR-004.3 (including the grouping rule, §3.8).
> - **(U) Uniqueness:** *C*'s region on *L* contains no other numeric or nil token, and no non-numeric word other than a currency symbol.
> - **(S) Structure:** the page's column structure is valid (7.1).
>
> Distance to a column, "nearest column", text order, and alignment with neighbouring rows **never** establish an assignment by themselves.
>
> **7.4 Outcomes when a condition fails (never guessed).** In every case below, the outcome is `requires_review` (`period_not_verified`) unless stated otherwise.
> - **(B) fails:** the token overlaps two regions, or overlaps none while lying right of the label limit.
> - **(U) fails:** two or more numeric tokens in one region (split fragments included while DEC-A is disabled), or a non-numeric word in a region.
> - **(N) fails:** for example the fragment `88,` → `requires_review` (`value_not_in_evidence`).
> - **(R) fails:** `requires_review` (`label_not_recognised`).
> - **Blank cell** (no numeric or nil token in *C*'s region on *L*): there is no value for that period. The field is `not_found` if the LLM proposed nothing for that period; if it proposed a value, the field is `requires_review` (`period_not_verified`). **Other columns are never shifted.**
> - **Figure-only line:** a line with no label words, whose vertical gap to an adjacent labelled line is less than `figure_line_distance_pt`, can supply a token to a column that is blank on that labelled line. In that case the labelled line's value for that column is `requires_review` (`period_not_verified`).
>
> **7.5 Note column.** Numeric tokens in the note column are note references, never values.
>
> **7.6 Verification and provenance.** The value the LLM proposes for a period must equal the word assigned by 7.3. The field records:
> - the column;
> - the anchor's quote;
> - the bounding boxes of the token and the anchor;
> - the line's label.
>
> **7.7 Continuation pages.** If a page has no column-header block and was selected as a continuation (FR-013 rule 3b), the regions come from the first page of its statement run. 7.1 applies to that page.
>
> **7.8 Provisional settings** (tuning-derived, re-checked in D-01b C4):
> - `column_margin_pt = 3`;
> - `figure_line_distance_pt = 6`.

**Rationale.** Requiring boundary, label, numeric, and uniqueness conditions together closes the failure the probe exposed, where a nearest-column rule took a number from a label. It also means that every case that cannot be assigned uniquely has a defined, safe outcome.

**Acceptance criteria (AC-D13).** All on synthetic PDFs, Phase 2:

| AC | Case | Expected |
|---|---|---|
| AC-D13-1 | Aligned two-column page, with and without a note column | Each value is assigned to the correct column; note references to the note column only |
| AC-D13-2 | Header centred over wider right-aligned figures | Correct assignment |
| AC-D13-3 | Number inside the first line of a wrapped label | Never a value |
| AC-D13-4 | Number inside a wrapped label whose figures are on the same line (the R2 `7,434` pattern) | Never a value; the line's figures are assigned correctly |
| AC-D13-5 | Label word long enough to overlap a period region | `requires_review` |
| AC-D13-6 | Token overlapping two regions; token right of the label limit overlapping none | `requires_review` |
| AC-D13-7 | Overlapping regions; anchor count ≠ validated period count | Whole page `requires_review` |
| AC-D13-8 | Blank cell, no proposal / with proposal | `not_found` / `requires_review`; the other column unchanged |
| AC-D13-9 | Nil dash in a region | `reported_nil` |
| AC-D13-10 | Split figure `88, 136` in one region (DEC-A disabled) | `requires_review`; fragments and boxes recorded |
| AC-D13-11 | Figure-only line within 6pt; subtotal line a full row away | `requires_review`; no effect |
| AC-D13-12 | Word spanning two columns | `requires_review` |
| AC-D13-13 | Label failing FR-005.10 with a correctly placed figure | `requires_review` (`label_not_recognised`); no assignment |
| AC-D13-14 | Continuation page without a header; run whose first page fails 7.1 | Regions from the first page; `requires_review` |
| AC-D13-15 | Determinism: same input twice | Identical assignments |

### 3.2 FR-005.11 — Split-figure reconstruction (DEC-A: open; disabled)

**Affected:** new FR-005.11 (reserved).

**Proposed wording:**

> **11. Split figures (DEC-A, open).** Automatic reconstruction of split figures is **disabled in Release 1**.
> - While disabled, two or more numeric tokens in one period column region on a line (for example `88,` and `136`) are handled by FR-005.7 7.4. The outcome is `requires_review` (`period_not_verified`, or `value_not_in_evidence` where (N) fails).
> - The field records the original quote verbatim, together with each fragment's text and bounding box, so a reviewer can see exactly what was extracted.
> - No value is produced, and no joined value is ever displayed as extracted.
>
> **Conditions for enabling it later (all required, each by a separate owner decision):**
> 1. A **fragment-gap rule** with a measured basis: gaps between split fragments, and between genuine separate words, measured on tuning-set documents. The measurement must show a threshold that separates the two without overlap. If the distributions overlap, no defensible rule exists and reconstruction stays disabled.
> 2. The **candidate conditions** below are specified as tests and passing on synthetic cases built from the measured gaps.
> 3. The owner approves enabling it.
>
> **Candidate conditions (not adopted; recorded for the future decision):**
> - same single period region;
> - consecutive words with nothing between them except whitespace;
> - split only after a thousands separator or before a closing bracket;
> - fragment patterns `^[(]?[-−–]?[0-9]{1,3}(,[0-9]{2,3})*,?$` and `^[0-9]{2,3}(,[0-9]{2,3})*([.][0-9]+)?[)]?$` or `)`;
> - the joined value passes FR-004.3 with balanced brackets;
> - the line's label passes FR-005.10;
> - exactly one fragment group in the region;
> - a gap within the measured rule.
>
> Provenance if ever enabled: the original quote stays verbatim; `validation.split_repaired = true`, with the fragments, boxes, gaps, and rule version; the memo notes "figure rejoined from split extraction".

**Consequence.** R2's net income (2024, 2023), total stockholders' equity (2024), and the two bracketed figures stay `requires_review` in Release 1 unless DEC-A is later enabled.

**Regression tests (while disabled):**
- each of the four R2 split patterns, reproduced synthetically → `requires_review`, with the quote and fragments recorded;
- no test may produce a joined value.

### 3.3 FR-005.9 — Period-end dates (DEC-B: accepted in principle)

**Affected:** FR-005.9 (replaced); H.1.2 `period_end` evidence.

**Proposed wording:**

> **9. Period-end evidence (D-11, amended).**
> - **Sources.** Period ends are derived **only** from:
>   - (i) the column-header block (G.0); and
>   - (ii) the page's title lines (G.0).
>
>   No other text may supply a date component. That includes dates below the first figure line, such as audit-signature dates, report-approval dates and note text, and dates in any other part of the page.
> - **Tokens.**
>   - *Full date:* a written date, an ISO date, or an unambiguous numeric date (as in v0.3).
>   - *Day-month fragment:* a day and month name with no year, e.g. `March 31,`, `31 March`, `June 30,`, optionally preceded by "as at", "as of", "year ended" or "for the year ended".
>   - *Year anchor:* `YYYY`; `YYYY-YY` or `FY YYYY-YY`, taken as the later year; or `FY YYYY`.
> - **Combination, per period anchor:**
>   - **Full-date anchor:** the period end is that date.
>   - **Year anchor:** the period end is the anchor's year plus the **day-month** of the source fragment. The fragment comes from the column-header block. If the block contains none, it comes from the title lines. The source must contain **exactly one distinct** day-month.
>   - The combination must be a valid calendar date.
> - **Evidence.** Each period end records:
>   - the anchor's quote;
>   - the fragment's quote (or the full date's quote) and where it came from (header block or title line);
>   - the page number and the normalised ISO date.
> - **Rejection.** Never guessed. All fields of an affected period are `requires_review` (`period_mismatch`) if:
>   - a year anchor has no day-month source;
>   - the source has two or more distinct day-months;
>   - a full-date anchor's day-month differs from a day-month fragment in the same column-header block;
>   - a combination is not a valid date;
>   - a numeric date is ambiguous;
>   - two anchors yield the same period end.
> - **Ordering.** Periods are ordered by date, latest first. The latest is the current period. H.1.1 and H.1.3 govern the rest.

**Rationale.**
- **The common header:** a shared day-month with one year per column (R1 "As at March 31," over `2025 2024`; R2 "Year Ended June 30," with `2025 2024 2023`) is a standard layout, which v0.3 rejected.
- **Unrelated dates:** limiting sources to the header block and title lines excludes them structurally. R1's signature date "April 17, 2025" lies below the first figure line, so it can never be a source.

**Regression tests:**
- **Positive:**
  - "As at March 31," over `2025 2024` → 2025-03-31 and 2024-03-31;
  - "Year Ended June 30, 2025 2024 2023" on one line → three dates;
  - `2024-25` and `2023-24` anchors with the title "… for the year ended March 31, 2025" → 2025-03-31 and 2024-03-31;
  - full-date anchors `31 March 2025` and `31 March 2024` → both;
  - `2024-02-29` with a `2023` anchor and fragment "February 29" → 2023-02-29 is invalid → `period_mismatch`. The leap-year handling is explicit, not silently corrected.
- **Negative (`period_mismatch`):**
  - year anchors with no fragment in the header block or title;
  - the only full date on the page is a signature date below the table → **not used**;
  - two fragments, "March 31" and "December 31", in the header block;
  - full-date anchor `31 March 2025` with fragment "June 30" → conflict;
  - `03/04/2025`;
  - a date above the title line, such as a running page header "Annual Report 2024-25 | March 31, 2025" → not used;
  - "June 30," at the far left and `2025` far to the right on one line → treated as a fragment plus a year anchor, **not** as a full-date anchor; the column region comes from `2025` alone.

**Acceptance criteria (AC-B).** Every positive and negative case listed above must pass. In addition:

| AC | Requirement |
|---|---|
| AC-B-1 | Every validated period end records the anchor quote, the fragment or full-date quote, the source (`header_block` or `title_line`), the page, and the ISO date |
| AC-B-2 | No test fixture with a date only below the first figure line, or only above the title line, yields a period end |
| AC-B-3 | Every rejection case gives `period_mismatch` for exactly the affected period's fields, and leaves other validated periods unchanged |

### 3.4 H.1.1 and H.1.3 — More than two periods (DEC-C: accepted in principle)

**Affected:** H.1 `period_role` enum; new H.1.3; F.1; FR-009 / K.2; FR-012.1.

**Proposed wording:**

> **H.1.3 Additional periods (DEC-C).**
> - **Supported periods.** Every validated period (FR-005.9) that forms an unbroken chain of consecutive years back from the current period (H.1.1 rule, applied pairwise) is a *supported period*. Fields are extracted for every supported period. Each keeps its ISO period-end identifier, with `period_role` = `current`, `comparative`, or the new value `prior`.
> - **Release 1 use.** Calculations, risk rules, and memo sections 3–8 use **only** `current` and `comparative`. `prior` fields are validated like any other field and appear in `results.json`, but feed no metric and no rule.
> - **Disclosure.**
>   - Memo section 2 lists every period found on the statements, marked:
>     - "used" (current and comparative);
>     - "extracted, not used in Release 1" (prior);
>     - "not extracted: <reason>" (an unvalidated date, a break in the consecutive chain, or a non-12-month period).
>   - The manifest records the same list (`periods`).
> - **Ordering.** No period is ever re-labelled to fill a gap. If the current and comparative periods are not consecutive, the v0.3 rule applies (comparative fields `requires_review`), and `prior` is not used as a substitute.

**Rationale.** Capturing every supported period, rather than dropping columns, keeps the evidence complete and every identifier correct. Limiting calculations to two periods keeps Release 1's metric and rule definitions unchanged.

**Consequence.** More fields are extracted per three-year statement, which affects token cost (OD-8 sizing).

**Regression tests:**
- three consecutive columns → current, comparative and prior fields, with correct ISO IDs; metrics use only the latest two; memo section 2 lists all three correctly;
- columns 2025, 2024 and 2022 → the 2022 column is "not extracted: not consecutive";
- an unvalidated third column → "not extracted: period date not validated";
- a prior field never feeds MET-01 to MET-05 or RI-001 to RI-007.

**Acceptance criteria (AC-C).**

| AC | Requirement |
|---|---|
| AC-C-1 | Every extracted field, of every role, has an ISO period-end ID; no two periods share an ID |
| AC-C-2 | MET-01 to MET-05, RI-001 to RI-007, and memo sections 3–8 read only `current` and `comparative` fields (a test passes `prior` fields with extreme values and asserts no output changes) |
| AC-C-3 | Memo section 2 and the manifest list every period found, with exactly one of `used`, `extracted, not used in Release 1`, or `not extracted: <reason>` |
| AC-C-4 | No period is relabelled to fill a gap in the consecutive chain |

### 3.5 Borrowings — H.3, FR-005.10, H.5 rules 4–5 (DEC-D and OD-9: open)

**Affected:** H.3 label phrases; the FR-005.10 section-heading check; H.5 rules 4 and 5.

**Unchanged:**
- D-07: lease liabilities are excluded.
- **Total liabilities is never a borrowing value or component.** It may appear in a reconciliation only as a reported subtotal.

**Proposed now (no open decision involved):**
- **H.3 label phrases.** Add only phrases observed in tuning documents:
  - `borrowings_current`: + "short-term debt"
  - `borrowings_non_current`: + "long-term debt"
  - `current_maturities_long_term_borrowings`: + "current portion of long-term debt"
- **FR-005.10.** The section-heading check applies only to section-dependent labels (initially "borrowings"). Self-identifying labels need no heading.

**DEC-D (open): evidence required before any aggregation.** Proposed wording for H.5 rule 5, for the owner's decision:

> **5. Borrowing aggregation.**
> - If a total-borrowings line is reported, it is used. Otherwise `BORR-SUM` may add components **only if non-overlap is established for every pair**, by one of the following:
>   - **(E1) Explicit wording:** an inclusion or exclusion phrase (v0.3). An inclusion phrase means the included component is never added.
>   - **(E2) Reconciliation with alternatives excluded.** **All** of the following must hold, for **every** period used:
>     - (a) every row of the balance-sheet section containing the components is read uniquely under FR-005.7;
>     - (b) the sum of **all** rows between the section start (its heading or the previous subtotal row) and the section subtotal equals the reported subtotal **exactly**, in printed units;
>     - (c) **no alternative grouping exists:**
>       - no row in the section is labelled with a configured subtotal phrase (e.g. "total …", "net …");
>       - no row's value equals the sum of any contiguous run of two or more other rows in the section;
>       - no row is a continuation of a wrapped label;
>     - (d) each borrowing component is a distinct row of that sum, mapped to a distinct borrowing field;
>     - (e) across sections, the component sections themselves reconcile into a higher reported subtotal (e.g. total liabilities) under (b) and (c).
> - **A matching total on its own is never conclusive.** If (c) finds any alternative grouping, E2 fails.
> - If neither E1 nor E2 holds, `total_borrowings` is `requires_review` (`borrowings_classification_unresolved`) and excluded from calculations. The components, evidence, arithmetic, and the failed condition are all recorded.
> - Sibling rows and indentation are never evidence.
> - Each component is added at most once.
> - All arithmetic uses `Decimal`.

**Tuning observation (not a decision, not a result).** R2's current-liabilities rows sum exactly to the printed subtotal, as do total current liabilities plus the following rows to total liabilities, in both years. Condition (c) has **not** been evaluated on R2. E2 therefore remains unproven even for R2.

**Still to decide under DEC-D:**
- whether E2 is acceptable evidence at all;
- whether its condition (c) is sufficient;
- whether any rounding tolerance is admissible (none is proposed).

**OD-9 (open): reported zero versus absent versus unidentifiable.** Proposed wording for H.5 rule 4, for the owner's decision:

> **4. Borrowing presence.** Each borrowing field for a period is in exactly one state:
> - **(Z) Reported zero:** a borrowing row is present and its cell is the figure `0`, or a nil token, assigned under FR-005.7 with the label passing FR-005.10. Its value is 0, with evidence; a nil token is `value_interpretation = reported_nil`. A reported zero is a valid component.
> - **(A) Absent:** no row for that field is found on the balance-sheet candidate pages. The field is `not_found` (absent ≠ zero).
> - **(U) Unidentifiable:** a candidate row exists, but it fails FR-005.7 or FR-005.10. The field is `requires_review`.
>
> `total_borrowings` and MET-04 are computed only from fields in state (Z) or `extracted`. A **zero D/E is computed only when every component used is state (Z), or a reported total-borrowings line shows a zero or nil.** From (A) or (U), MET-04 is undefined (`missing_input` or `input_requires_review`). It is never 0.

**OD-9 options for a debt-free company with no borrowing line (R1 pattern), for the owner:**
1. Keep (A): D/E undefined, with a memo note "no borrowing line presented on the balance sheet".
2. Accept an explicit document statement, quoted, that the entity has no borrowings, as evidence equivalent to (Z). The statement must name borrowings or debt explicitly; silence never counts.

**Not proposed:** treating a complete balance sheet without a borrowing line as zero, which would be inference from absence.

**Regression tests:**
- **Labels and headings:** observed labels match; the heading check applies only to "borrowings".
- **(Z), (A), (U):**
  - row with `0` → value 0;
  - row with `–` → `reported_nil`;
  - no row → `not_found`, MET-04 undefined (`missing_input`);
  - unreadable row → `requires_review`, MET-04 undefined.
- **Zero D/E:** computed only when every component is (Z), and **never** from (A).
- **DEC-D, if adopted:**
  - E1 inclusion → not added;
  - E2 with all of (a)–(e) → summed;
  - exact sum but a "total …" row inside the section → `requires_review`;
  - exact sum but one row equal to the sum of two others → `requires_review`;
  - off by 1 → `requires_review`;
  - reconciles in one period only → `requires_review`;
  - siblings or indentation alone → `requires_review`.
- **Always:** lease rows never components; total liabilities never used as borrowings.

### 3.6 FR-013 — Statement locator (DEC-E: accepted in principle)

**Affected:** FR-013 rules 1 and 3; G.0 title-line definition; phrase lists.

**Proposed wording:**

> **Rule 1 (amended).** After NFKC and case-folding:
> - typographic apostrophes (U+2018, U+2019, U+02BC) fold to `'`;
> - dash characters (U+2010–U+2015, U+2212) fold to `-`.
>
> This is **for phrase and label matching only**. Figure parsing and sign rules use the unfolded text.
>
> **Rule 3 (replaced), two sub-rules evaluated in ascending page order.**
> - **3a. Statement title page.** A page has a statement title for a type if it contains a **title line** (G.0) for that type. It qualifies if it also has at least `min_line_items_with_title` line-item phrases of that type.
> - **3b. Continuation page.** A page that **immediately follows** a page qualifying for a type, and has **no title line for a different statement type**, qualifies as a continuation if either:
>   - it has a title line for the same type (any number of line items, e.g. "… (contd.)"); or
>   - it has at least `min_line_items_without_title` line-item phrases.
>
>   Continuations chain: a qualifying continuation can be followed by another.
> - **Untitled pages.** A page with no title line that does not follow a qualifying page **never** qualifies.
>
> **Rule 2 unchanged** (word boundaries, distinct phrases). **Rules 4–8 unchanged.** That covers scoring, ranking, tie-breaking, `max_candidates`, statement runs, the page-range override and text in a range.

**Rationale.**
- **Why not a fixed line count:** the title-line rule is structural. A title is a line that *starts* with an optional configured prefix and a title phrase, and sits above the first figure line.
- **What it excludes:**
  - numbered notes such as "2.28 Function-wise classification of Statement of Profit and Loss", because "2.28 …" doesn't start with a prefix or title phrase;
  - prose mentioning a statement ("recognised in the Statement of Profit and Loss");
  - a title appearing below a page's figures.
- **Summary pages:** untitled summary pages (R1 p30) qualify only as continuations, so they're excluded unless they directly follow a statement.
- **Every element is configurable:** prefix words, title phrases and thresholds.

**Phrase lists.** Add only phrases observed in R1 and R2:
- **Titles:** "balance sheets", "income statements".
- **Income-statement items:** "finance cost", "total revenue", "operating income", "income before income taxes", "net income".
- **Balance-sheet items:** "total liabilities", "total stockholders' equity", "total liabilities and stockholders' equity", "long-term debt", "short-term debt".

Unobserved terms ("statements of operations", "shareholders' equity", "statement of financial condition") are **candidates only**, until they appear in tuning documents.

**Page range.** It remains the **explicit fallback** for layouts these rules don't cover.

**Targets for the tuning documents.** These are not achieved results:
- **R1:** pages 194–197 and 274–277 selected; pages 30, 263 and 346 not selected.
- **R2:** pages 36, 37 ("COMPREHENSIVE INCOME STATEMENTS" begins with prefix "comprehensive", followed by a title phrase) and 38 selected.

**Regression tests:**
- **Title lines:**
  - plural titles qualify;
  - "Consolidated Balance Sheet", "Comprehensive income statements" and "Statement of Profit and Loss (contd.)" are title lines;
  - "2.28 Function-wise classification of Statement of Profit and Loss" is not;
  - a prose sentence containing a title phrase is not;
  - a title phrase below the first figure line is not.
- **Continuations:**
  - an untitled summary page with 5 line items, not following a statement → rejected;
  - a titled continuation with no line items → selected;
  - an untitled continuation with 4 or more items → selected;
  - a continuation chain of three pages → all selected;
  - a following page titled as a different statement type → not a continuation of the first.
- **Matching:** curly-apostrophe phrases match.
- **Unchanged:** ties and `max_candidates`; PRD Appendix B Example 5 still selects 112–114.
- **Intentional change (§7.3):** `test_page_qualifying_for_both_types_scores_both`. Its profit-and-loss title lies below the balance-sheet figure lines.

**Acceptance criteria (AC-E).** All are on synthetic fixtures. Results on R1 and R2 are **recorded as tuning observations, not acceptance criteria**, and imply nothing about general performance.

| AC | Requirement |
|---|---|
| AC-E-1 | Title-line rule: each listed title-line case (positive and negative) behaves as specified |
| AC-E-2 | Rule 3a and rule 3b are tested separately. A titled page never needs 3b. An untitled page qualifies **only** through 3b. |
| AC-E-3 | A 3b continuation needs an immediately preceding qualifying page of the same type; a gap of one page breaks the chain |
| AC-E-4 | A page titled as a different statement type is never a continuation |
| AC-E-5 | Ranking, ties, `max_candidates`, and statement runs are unchanged (existing FR-013 tests pass, except the one intentional change in §7.3) |
| AC-E-6 | **Page-range override:** with `--pages`, rules 3a and 3b are not applied; the candidates are exactly the requested pages (FR-013 rule 7), and rule 8 (text in a range) applies. The basis still requires evidence or an explicit assertion (§3.7). |
| AC-E-7 | **Process control, not an automated test:** every phrase-list change records the tuning-set document and page that motivated it (in `PROGRESS.md` or the commit message). Held-out document IDs never appear in configuration or its change records. |

### 3.7 OD-10 — Reporting basis (accepted in principle: options c and b′)

**Affected:** H.4.6 basis rules; H.1 (new attribute `basis_evidence`); FR-014 (new flag); FR-012.1 manifest; K.0 memo header.

**Proposed wording (offered as options; the owner chooses):**

> - **Evidence-only basis.** A statement run's basis is `consolidated` or `standalone` **only** if established by explicit evidence:
>   - (1) a title line (H.4.6, unchanged); or
>   - (2) **(OD-10 option c)** a configured footnote reference on a page of that run, initially "integral part of the standalone financial statements" or "integral part of the consolidated financial statements", quoted as evidence.
>
>   A footnote applies to every page of its statement run **unless** another page in the run has a title line naming a different basis. In that case the run's basis is `unknown`.
> - **Never inferred from absence.** Missing consolidated wording never implies standalone, and the reverse.
> - **Analyst assertion (OD-10 option b′).** Only if `--assert-basis BASIS` is given **together with** `--pages`:
>   - pages in that range with no basis evidence are treated as BASIS;
>   - it **never** overrides a page whose title or footnote names a different basis; such a conflict stops the run with `E-EXTRACT-BASIS-UNAVAILABLE`;
>   - the manifest records `basis_assertion: {basis, pages, asserted_at}`;
>   - every affected field records `basis_evidence = analyst_assertion`;
>   - the memo header states "Basis asserted by the analyst for pages …; not established by the document".
>
>   `--basis` alone keeps its v0.3 meaning (choose which basis to analyse) and **never** asserts one.
> - **New H.1 attribute.** `basis_evidence`: `title` / `footnote` / `analyst_assertion`.

**Options and consequences.**
- **(a)**, v0.3: R1's standalone statements and all of R2 cannot be analysed.
- **(c)**: R1's standalone statements are established from the document; pages 195 and 197 carry the footnote. R2 has no such footnote.
- **(b′)**: makes R2 analysable, e.g. `--pages 36-38 --assert-basis consolidated`, with the assertion disclosed.

**Recommendation:** (c) together with (b′).

**Regression tests:**
- **Footnote:** the footnote establishes the basis for its whole run; a footnote conflicting with a title in the same run → `unknown`.
- **Assertion:**
  - `--assert-basis` without `--pages` → usage error (exit code 2);
  - with `--pages` → only those pages affected;
  - on a page titled with the other basis → `E-EXTRACT-BASIS-UNAVAILABLE`;
  - recorded in the manifest, the fields and the memo header.
- **`--basis` alone** never asserts.
- **No inference:** absence of basis wording never establishes a basis.

**Acceptance criteria (AC-OD10).**

| AC | Requirement |
|---|---|
| AC-OD10-1 | A basis is set only from a title line, a configured footnote reference, or an explicit assertion; each field records `basis_evidence` |
| AC-OD10-2 | No fixture without basis evidence and without an assertion yields `consolidated` or `standalone` |
| AC-OD10-3 | `--assert-basis` without `--pages` is rejected (exit code 2); an assertion never applies outside the given pages, and never over contrary evidence |
| AC-OD10-4 | Every assertion appears in the manifest, in each affected field, and in the memo header |
| AC-OD10-5 | A footnote and title naming different bases within one run → `unknown` |

### 3.8 FR-004.3 and FR-005.10 — Formats and labels

**Affected:** FR-004.3 (grouping rule added); FR-005.10 (folding and observed label phrases).

**Proposed wording:**

> **FR-004.3, added.** A figure with thousands separators is valid only if its integer part matches, **in full**, either:
> - **Western:** `d{1,3}(,ddd)+`; or
> - **Indian:** `d{1,3}(,dd)*,ddd`.
>
> R1's share counts are printed in the Indian form with a 3-digit leading group, e.g. `415,19,36,905`. Anything else (`1,2345`, `12,34,5`) is unparsable and becomes `requires_review`. Each figure is judged on its own; one document may use both forms.
>
> **FR-005.10, amended.** Labels are normalised with the rule-1 folding of §3.6. Add only the observed label phrases:
> - `interest_expense`: "finance cost"
> - `revenue`: "total revenue"
> - `operating_profit`: "operating income"
> - `profit_before_tax`: "income before income taxes"
> - `net_profit`: "net income"
> - `total_equity`: "total stockholders' equity"
>
> **No stemming or fuzzy matching. Wrapped labels are not joined in Release 1:** no target-field label wrapped in the tuning sample.

**Rationale.** The rules are deterministic and testable, and they don't change meaning. Folding only affects matching, never values.

**Regression tests:**
- **Grouping:** `1,24,936`, `162,990` and `415,19,36,905` are valid; `1,2345` and `12,34,5` → `requires_review`.
- **Folding:** "Total stockholders’ equity" with U+2019 matches.
- **Exact matching:** "Finance cost" matches `interest_expense`; "Total equity attributable to …" does **not** match `total_equity`.
- **Sign rules unaffected:** a folded dash in a label doesn't change FR-005.6 sign handling.

### 3.9 `TextExtractor.extract_words` (L.3; D-01a replaceability preserved)

**Affected:** L.3 and L.4; the `TextExtractor` interface.

> `TextExtractor` gains `extract_words(path) -> list[PageWords]`, giving words with text, `x0`, `x1`, `top`, `bottom`, and 1-based physical page number. It is deterministic for the same file and the locked dependency versions. pdfplumber stays confined to `pdfplumber_extractor.py`. It is implemented at the **start of Phase 2**.

**Tests:** word boxes for a synthetic page; determinism across calls; physical page numbers; a fake extractor satisfies the interface.

---

## 4. Decisions

**D-13 — OD-1: word-position mapping (§3.1).**
- **Accepted in principle**, subject to AC-D13.
- Becomes approved when v0.4 is applied to `docs/PRD.md` and approved.

**D-14a — keep pdfplumber, provisionally.**
- **Accepted in principle.**
- Revisit if D-01b fails for a reason the library cannot address.

**D-14b (D-01b) — extraction-pipeline acceptance: OPEN, not met.** Safe failures alone are not sufficient. Acceptance can be decided only when **all** of the following conditions are satisfied, with the stated tests:

| # | Condition | Required test or evidence |
|---|---|---|
| C1 | FR-005.7 (D-13) implemented | AC-D13-1 to AC-D13-15 pass |
| C2 | FR-005.9 (DEC-B) implemented | All §3.3 cases and AC-B-1 to AC-B-3 pass |
| C3 | DEC-A has a final status (disabled is acceptable) | Disabled-mode tests in §3.2 pass; no joined value produced |
| C4 | **Tuning re-run:** every one of the 34 B-133 rows (R1, R2) processed by the implemented pipeline | For each row, either the correct value in the correct row and period, or a recorded `requires_review` / `not_found`. **Zero rows with a value attributed to the wrong row, period, sign, or scale.** Counts per outcome recorded. |
| C5 | **Held-out evaluation:** OQ-3 documents (companies other than R1 and R2), labelled before running, run once | Same zero-wrong-value criterion as C4. Counts per outcome and per failure category reported. **No tuning on these documents.** |
| C6 | B-120 (fresh-process determinism) | Passes |
| C7 | Owner review of C4 and C5 | Owner records D-01b as met or not met |

- **Not specified here:** an acceptable rate of `requires_review` outcomes. Any threshold for it is an owner decision informed by C4 and C5. It is not proposed without evidence.
- **Failure:** if C4 or C5 shows any wrong-value attribution, D-01b is not met. The cause is analysed before any change to D-14a.

## 5. Decisions and open questions

| ID | Status | Remaining question | Deadline |
|---|---|---|---|
| D-13 | Accepted in principle | AC-D13 acceptance when v0.4 is applied | v0.4 approval |
| D-14a | Accepted in principle | — | v0.4 approval; required for Phase 1 exit |
| D-14b (D-01b) | **Open** | Conditions C1–C7 (§4); an acceptable `requires_review` rate, if any | After Phase 2 and the held-out evaluation |
| DEC-A | **Open (disabled)** | Whether a measured fragment-gap rule exists, and whether to enable it | Not before the gap measurement; no Release 1 dependency |
| DEC-B | Accepted in principle | AC-B | v0.4 approval |
| DEC-C | Accepted in principle | AC-C; OD-8 sizing impact | v0.4 approval |
| DEC-D | **Open** | Whether E2 is acceptable, whether condition (c) is sufficient, and the rounding policy | Before Phase 3 |
| DEC-E | Accepted in principle | AC-E | v0.4 approval (Phase 1 scope) |
| OD-9 | **Open** | Option 1 or 2 for debt-free companies; the `not_presented` current-maturities case | Before Phase 3 |
| OD-10 | Accepted in principle | AC-OD10 | v0.4 approval (before Phase 2) |
| OQ-3 | Accepted in principle | Which documents; labelling before running | Before D-14b C5 |
| OD-3 | Open (unchanged) | SC-12 target; R1 and R2 results are tuning observations | First evaluation report |
| OD-6, OD-7, OD-8, OQ-6 | Open (unchanged) | As in v0.3 (OD-8 must account for DEC-C) | As in v0.3 |
| — | **Outstanding input** | Source URLs and retrieval dates for R1 and R2 | Before any committed evaluation record cites them |
| — | Provisional settings | `column_margin_pt`, `figure_line_distance_pt` | Re-checked in D-14b C4 |

## 6. Implementation sequence

| Step | Phase | Content | Exit evidence |
|---|---|---|---|
| 0 | — | Owner review; approved items applied to `docs/PRD.md` as v0.4 | v0.4 approved |
| 1 | 1 | FR-013 amendments (DEC-E): rule 1 folding, the G.0 title-line definition, rules 3a and 3b, phrase lists | §3.6 tests pass; one intentional test change reviewed |
| 2 | 1 | B-120: fresh-process golden-output test (FR-002.3) | Test passes |
| 3 | 1 | **Phase 1 exit review:** every v0.3 Phase 1 exit criterion verified, B-120 passing, D-01a decided, B-133 recorded | Owner approval |
| 4 | 2 | `extract_words` (§3.9) | §3.9 tests |
| 5 | 2 | FR-005.7 (D-13), FR-005.9 (DEC-B), FR-004.3 grouping, FR-005.10 amendments, H.1.3 (DEC-C), OD-10 rules, FR-005.11 in **disabled** mode (DEC-A open), H.5 rule 4 states (Z)/(A)/(U) only once OD-9 is decided | AC-D13, AC-B, AC-C, AC-OD10; §3.2 disabled-mode tests |
| 6 | 2 | D-14b C4 (tuning re-run) and C5 (held-out evaluation, once OQ-3 documents are labelled) | D-14b decided by the owner (C7) |
| 7 | 3 | H.5 rules 4–5, **only after** OD-9 and DEC-D are decided | §3.5 tests |

Phase 2 still requires all its v0.3 entry conditions: OD-8, OD-10, the D-02 checks, and the data-terms review.

---

## 7. Regression-test plan

### 7.1 Principles
- **Test data:** synthetic PDFs or `PageText` generated at test time. No real report is ever committed.
- **Safe failure:** every ambiguous case must end in `requires_review` or `not_found`, **never** a value. Each subsection of §3 lists its positive cases and its negative (safe-failure) cases.

### 7.2 New tests by area
These are the test lists in §3.1 to §3.9. Each new test is recorded in `tests/BEHAVIOURS.md` when implemented.

### 7.3 Existing tests
- **Must pass unchanged:** all 145 current tests, except one. That includes the 4 B-132 `known_limitation` tests, which keep characterising *text* extraction.
- **One intentional change:** `tests/unit/test_locator.py::test_page_qualifying_for_both_types_scores_both`. Under the G.0 title-line definition, its profit-and-loss title lies below the balance-sheet figure lines, so the page qualifies only as a balance sheet. The test is updated in the same commit as the rule, with the change named in the commit message. **No other existing test may be edited to pass.**
- **Re-checked against the proposed rules, and unaffected:**
  - PRD Appendix B Example 5;
  - `test_locator_works_on_ingested_synthetic_pdf`;
  - `test_continuation_pages_without_titles_do_not_count_as_a_basis` (page 113 doesn't follow a qualifying page, so "bases found: none" still holds);
  - the tie, cap and boundary tests;
  - the B-130 basis tests (their titles start their lines and sit above the first figure line).

---

## 8. Requirements that remain unchanged
- **FR-001, FR-002:** ingestion and page text. B-120 is still required.
- **FR-003:** extraction. DEC-C only increases the number of fields.
- **FR-006, FR-007, FR-008:** metrics and rules use current and comparative periods only.
- **FR-009 to FR-012, FR-014, G.1:** apart from the disclosures listed in §3.4 and §3.7 and the `--assert-basis` flag; no new error codes; existing reason codes reused.
- **FR-004:** apart from the grouping rule.
- **FR-005:** criteria 1–6 and 8 unchanged. Criterion 8 already accepts a currency symbol on the page, which covers R2's `$`.
- **H.2, H.4,** and the H.5 EBIT methods.
- **Section I** metrics, **Section J** rules, and **Section K**, apart from memo sections 2 and the header.
- **Decisions:** D-02 to D-11 and D-12 (amended only as in §3.5); "absent ≠ zero"; no total-liabilities substitution; D-07 lease exclusion.
- **Security, NFR and evaluation:** SEC-01 to SEC-12, NFR-01 to NFR-09, and the O.2 tuning/held-out rules.
- **Phase boundaries:** apart from the Phase 1 exit review contents in §6.

---

## 9. Consistency review (performed on revision 3)

| Check | Result |
|---|---|
| Circular definitions | **None found.** G.0 terms are lexical. The chain of dependencies runs one way only: anchors → regions → label limit → label → FR-005.10 → assignment (7.3). FR-005.10 uses the label from 7.2, which needs no assignment. FR-005.9 uses the header block and title lines, which need no regions. |
| Contradictory acceptance criteria | **Checked:** AC-D13-10 (split → `requires_review`) agrees with §3.2 (disabled); AC-E-6 (page range bypasses 3a/3b) agrees with FR-013 rule 7; AC-C-2 agrees with H.1.3; the §3.5 (Z) rule agrees with D-08 nil handling and "absent ≠ zero". |
| Proximity-only assignment | Excluded explicitly in 7.3; AC-D13-4 and AC-D13-6 test it |
| Unsupported assumptions | Removed: sibling or indentation evidence (DEC-D); reconciliation alone as conclusive (DEC-D); a glyph-width gap rule (DEC-A). The R2 reconciliation is labelled a tuning observation, with condition (c) **not evaluated**. |
| Decisions resolved implicitly | None. DEC-A, DEC-D, OD-9, and D-14b are open, with explicit "not decided" text and safe defaults. |
| Evidence claims | No accuracy figure. R1 and R2 are tuning documents; their outcomes are observations or targets. Source URLs and retrieval dates are outstanding. |
| Dependencies on future work | FR-005.7, FR-005.9, H.5 rules 4–5 and D-14b depend on Phase 2 (`extract_words`), OD-9, DEC-D, and OQ-3, as stated. FR-013 amendments depend only on page text (Phase 1). |
| Residual risk (recorded, **not** mitigated) | A plain four-digit value printed without separators (e.g. `1995`) in a data row above the first figure line would be read as a year anchor. Combined with the shared day-month fragment, it **would validate** as a period end (FR-005.9), so the 7.1 period-count check would **not** catch it. H.1.3 would mark that period "not extracted: not consecutive", but it would still create a column region that can make neighbouring tokens ambiguous (`requires_review`). It is safe, but unresolved. Not observed in R1 or R2; to be checked in D-14b C4. A mitigation, such as requiring anchor lines to contain no label words, would need its own rule and tests. |
