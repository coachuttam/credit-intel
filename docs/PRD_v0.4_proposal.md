> **Superseded by `docs/PRD.md`.** This is the historical v0.4 proposal; the status lines below describe it as it stood in October 2026.

# PRD v0.4 Proposal — Amendments from Real-Report Validation (revision 13)

| Item | Value |
|---|---|
| Status | **Proposal only — awaiting project-owner review.** Nothing here is approved. `docs/PRD.md` v0.3 remains authoritative until v0.4 is approved. |
| Revision | 13 (2026-10-16). Changes only how candidate records behave when a reported total is selected: every candidate and its outcomes are kept, its periods are marked `not_consulted` instead of `blocked` or `accepted`, and the reported total stays authoritative. *Proposed by owner, awaiting confirmation*; v0.4 is not approved. Revision 12 (2026-10-16): Fixes only the revision-11 review items: Z′ stays prohibited when the basis rests only on `--assert-basis`; a per-candidate evidence record (`derivation.statement_candidates`, D2); case-insensitive exact normalised matching of OD-10 footnote phrases; AC-Z-46 wording and the `statement_zero_not_verified` register entry corrected. *Proposed by owner, awaiting confirmation*; v0.4 is not approved. Revision 11 (2026-10-16): Resolves only ambiguities A1–A4 of revision 10: an undetermined entity or basis blocks Z′ whether or not qualified, never `conflicting` (A1); `other` only when L3 evidence establishes a different entity or basis, otherwise `undetermined` (A2); new reason `statement_scope_undetermined` with its precedence (A3); a page of unknown basis is not basis evidence (A4). *Proposed by owner, awaiting confirmation*; v0.4 is not approved. Revision 10 (2026-10-16): Fixes only the revision-9 review findings: an explicit L4 qualifier is the only condition-6 failure that blocks (U1); a candidate whose entity or basis cannot be established blocks acceptance and gives `requires_review`, never a conflict (U2); all other candidates are recorded only; register, §9 heading and AC-Z-19 corrected. *Proposed by owner, awaiting confirmation*; v0.4 is not approved. Revision 9 (2026-10-16): Changes only the qualified-statement blocking rule: a qualified candidate blocks only when its entity and basis match the target. *Proposed by owner, awaiting confirmation*; v0.4 is not approved. Revision 8 (2026-10-16): Fixes only review findings V1–V4: a strict liability-scope fallback, exact matching of section headings and subtotals, undated statements no longer blocking, and condition 7 limited to valid candidates. *Proposed by owner, awaiting confirmation*; v0.4 is not approved. Revision 7 (2026-10-16): Fixes only review findings R1–R4: the scope of `statement_zero_not_verified`, the multiple-candidate rule for Z′, rejection of Z′ on unresolved or unclassified rows, and K2 applied to every liability section. *Proposed by owner, awaiting confirmation*; v0.4 is not approved. Revision 6 (2026-10-13): Fixes review defects D1–D5 and records the owner's **proposed** OPEN-1 policy **G1** and the memo requirement for blocked aggregation. All are *proposed by owner, awaiting confirmation*; v0.4 is not approved. Revision 5 (2026-10-13): Records the owner's **proposed** decisions as *proposed by owner, awaiting confirmation*. None is approved; v0.4 is not approved. The decisions are DEC-A, Q-A1, the validation-consistency fixes S1–S3, `value_unparsable`, DEC-D (R0), OPEN-1 (K2), OPEN-2 (M1 on E1 and E2), OPEN-3 (deterministic zero-evidence rules; disabled until the lists are approved), OPEN-4, OPEN-5 together with Q-Z6, OD-9 and Q-Z1. Revision 4 first recorded DEC-A, Q-A1, DEC-D, Q-D1, Q-D2, Q-Z1, Q-Z6 and OD-9. Revision 3 recorded the owner's decisions on revision 2: D-13, D-14a, DEC-B, DEC-C, DEC-E, OD-10 and OQ-3 **accepted in principle, subject to the acceptance criteria below**; DEC-A, DEC-D, OD-9 and D-01b **kept open**. Accepted-in-principle items become approved only when v0.4 is applied to `docs/PRD.md` and approved. |
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
| 2 | Split figures and value validation (DEC-A, Q-A1, S1–S3, `value_unparsable`) | Reconstruction **disabled**. A suspected split → `split_figure`; any other unparsable value → `value_unparsable`. Every check runs and is recorded, and one fixed order selects the reason. Proposed value and document token are parsed and recorded separately (`value_parsable`, `token_parsable`). One defined figure line per quote. New flag `split_suspected`. | **Proposed by owner (rev 5); awaiting confirmation** |
| 3 | Period dates (DEC-B) | A shared day-month fragment combined with per-column year anchors, taken only from the column-header block or title lines | **Accepted in principle**, subject to AC-B (§3.3) |
| 4 | Three-year statements (DEC-C) | Capture every supported period; use the latest two for Release 1 calculations and memo; disclose every period's disposition | **Accepted in principle**, subject to AC-C (§3.4) |
| 5 | Borrowings (DEC-D, R0, OPEN-1 = K2, OPEN-2, OPEN-4) | Aggregate only with unambiguous evidence. Reconciliation counts only with alternative groupings ruled out; exact match, no tolerance. **K2 allowlist, G1 policy:** every row (a line with a value in a period column) must be classified; generic "other …" rows are never allowlisted, so they block aggregation (M1, applied on both E1 and E2). Blocked aggregation is shown in the memo **without summing**. v0.3's missing-component rule is restored, with a fixed source priority for `total_borrowings`. A reported total is used on its own. `not_presented` current maturities only under E2 and M1. | **Proposed by owner (rev 5); awaiting confirmation**. The non-debt allowlist and the phrase lists are **OPEN until Phase 3**; until approved, component aggregation is always `requires_review`. |
| 6 | Locator (DEC-E) | Separate title-page and continuation-page rules, each testable on synthetic fixtures; page-range override kept | **Accepted in principle**, subject to AC-E (§3.6) |
| 7 | Basis (OD-10) | Explicit evidence (title or footnote), or an explicit, page-scoped, auditable analyst assertion | **Accepted in principle**, subject to AC-OD10 (§3.7) |
| 8 | D-01a / D-01b (D-14) | D-01a: keep pdfplumber provisionally. D-01b: pipeline acceptance **not met**; exact conditions listed in §4. | D-01a **accepted in principle**; D-01b **open** |
| 9 | OD-9 (Q-Z1, OPEN-3) and relative-change conditions (Q-Z6, OPEN-5) | Zero borrowings come only from a reported zero or nil, or from a statement-evidenced zero under deterministic source, period, entity and basis rules. That zero is **disabled until its lists and the subject-to-basis mapping are approved**. A relative-change condition is `not_evaluable` when the comparative value is 0 or undefined (RI-003 C2, RI-004 C1). | **Proposed by owner (rev 5); awaiting confirmation**. The lists are **OPEN until Phase 3**. |
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
> **7.4 Outcomes when a condition fails (never guessed).** In every case below, the outcome is `requires_review` (`period_not_verified`) unless stated otherwise. **When several checks fail, the reported reason is the first in the precedence order of FR-005.3 (§3.2).** Every check's result is still recorded in `validation` (§3.11).
> - **(B) fails:** the token overlaps two regions, or overlaps none while lying right of the label limit.
> - **(U) fails:** two or more numeric tokens in one region, or a non-numeric word in a region. If the tokens form a **suspected split figure** (FR-005.11), the reason is `split_figure`; otherwise it is `period_not_verified`.
> - **(N) fails:** the region holds exactly one numeric or nil token, and that **document token** cannot be parsed under FR-004.3 → `token_parsable = false`, `requires_review` (`value_unparsable`). Tokens forming a suspected split → `split_figure` (`token_parsable = null`).
> - **(R) fails:** `requires_review` (`label_not_recognised`).
> - **Blank cell** (no numeric or nil token in *C*'s region on *L*): there is no value for that period. The field is `not_found` if the LLM proposed nothing for that period; if it proposed a value, the field is `requires_review` (`period_not_verified`). **Other columns are never shifted.**
> - **Figure-only line:** a line with no label words, whose vertical gap to an adjacent labelled line is less than `figure_line_distance_pt`, can supply a token to a column that is blank on that labelled line. In that case the labelled line's value for that column is `requires_review` (`period_not_verified`).
>
> **7.5 Note column.** Numeric tokens in the note column are note references, never values.
>
> **7.6 Verification and provenance.**
> - **Figure line (D2).** The *figure line* of a quote is the line, within the verified quote, that holds at least one numeric or nil token in a period column region.
>   - Exactly one figure line → that line is used for 7.3, FR-005.11 and FR-005.10. The label is the text left of the label limit on the figure line.
>   - No figure line, or more than one → `requires_review` (`period_not_verified`).
>   - Label-only lines of a wrapped label are recorded as part of the quote, but do not change which line is validated.
> - The value the LLM proposes for a period must equal the word assigned by 7.3 on the figure line. The field records:
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
| AC-D13-10 | Split figure `88, 136` in one region (DEC-A disabled) | `requires_review` (`split_figure`); fragments and boxes recorded; no joined value |
| AC-D13-11 | Figure-only line within 6pt; subtotal line a full row away | `requires_review`; no effect |
| AC-D13-12 | Word spanning two columns | `requires_review` |
| AC-D13-13 | Label failing FR-005.10 with a correctly placed figure | `requires_review` (`label_not_recognised`); no assignment |
| AC-D13-14 | Continuation page without a header; run whose first page fails 7.1 | Regions from the first page; `requires_review` |
| AC-D13-15 | Determinism: same input twice | Identical assignments |
| AC-D13-16 | A single token `1,2345` (invalid grouping) in the claimed column | `requires_review` (`value_unparsable`); `token_parsable = false`; `split_suspected = false` |

### 3.2 FR-005.11, FR-005.3 and FR-004.3 — Split figures, parsing, and reason precedence (DEC-A, Q-A1, S1–S3, `value_unparsable`: Proposed by owner (rev 5); awaiting confirmation)

**Affected:**
- new FR-005.11;
- FR-005.3 (replaced: verification sequence and precedence);
- FR-004.3 (amended: reason for unparsable values);
- FR-005.7 7.4;
- H.1 `status_reason` (new values `split_figure` and `value_unparsable`);
- H.1 `validation` (tri-state values, new flags).

**Checked against v0.3 before revising.** v0.3 FR-004.3 makes an unparsable value `requires_review` but names neither a reason nor a position in the check order. If parsing ran first and stopped evaluation there, `split_figure` could never be reported. The fix below runs **every** check and selects the reason by one fixed order. v0.3's existing reasons keep their relative order.

**Proposed wording:**

> **FR-004.3 (amended).** Two parse checks use the same rules (formats as in v0.3, plus the grouping rule in §3.8), recorded separately (D1):
> - **`value_parsable`:** the LLM's **proposed** raw value parses. Always evaluated.
> - **`token_parsable`:** the **document token** assigned to the claimed column on the figure line (FR-005.7 7.6) parses. Evaluated only when that region holds exactly one numeric **or nil** token; a nil token parses as a reported zero (D-08). Otherwise `null`, including for a suspected split.
> - **Failure no longer ends verification:** all FR-005 checks still run (FR-005.3), and the reported reason follows FR-005.3's precedence.
> - **Reason:** if `split_suspected` is `false` and either parse check is `false`, the reason is `value_unparsable`.
>
> **FR-005.11 Split figures (DEC-A).** Reconstruction of split figures is **disabled**.
> - **11.1 Suspected split figure.** In one period column region on one line, a sequence of numeric tokens is a *suspected split figure* if **all** of the following hold:
>   - (a) they are consecutive words with only whitespace between them;
>   - (b) the first matches `^[(]?[-−–]?[0-9]{1,3}(,[0-9]{2,3})*,?$`;
>   - (c) each later token matches `^[0-9]{2,3}(,[0-9]{2,3})*([.][0-9]+)?[)]?$` or is exactly `)`;
>   - (d) every boundary between tokens falls immediately after `,` or immediately before `)`.
>
>   No gap measurement is used, and no joined value is computed or displayed.
> - **11.2 Outcome.** If the claimed period's column region on the quote's **figure line** (FR-005.7 7.6) holds a suspected split figure, `split_suspected = true` and the reason is `split_figure`. This applies whatever the LLM proposed, including one fragment or an unparsable joined string.
> - **11.3 Provenance.** The field records:
>   - the original quote, verbatim;
>   - each token's text and bounding box;
>   - the column and the line's label.
>
>   `split_repaired` is never set while this rule is disabled.
> - **11.4 Enabling reconstruction later requires all of:**
>   1. a fragment-gap rule measured on tuning-set documents, showing no overlap between the gaps inside split figures and the gaps between separate words;
>   2. the reconstruction conditions implemented as tests and passing;
>   3. a single held-out check with **no tuning**, recorded without changing the rule;
>   4. explicit owner approval.
>
>   If the gap distributions overlap, reconstruction stays disabled.
>
> **FR-005.3 (replaced). Verification sequence and precedence (S1–S3).**
> - **Every check runs.** The checks are: FR-005.1 (quote), FR-005.11 (split), FR-004.3 (`value_parsable`, `token_parsable`), FR-005.2 (value in quote), FR-005.10 (row label), FR-005.9 (period end), FR-005.7 (period column), FR-005.6 (sign), FR-005.8 (scale and currency), FR-006.5 (plausibility). Each records `true`, `false`, or `null` in `validation`. `null` means *not evaluable*: a check whose prerequisite failed, such as the sign or plausibility check on an unparsable value, or any positional check when the quote is not on the page. A `null` is never treated as a pass.
> - **Status.** A field is `extracted` only if every check is `true` and `split_suspected` is `false`.
> - **Reported reason.** Otherwise `status_reason` is the reason of the **first failing** check in this precedence order.
>   - *Failing* means `false`. For FR-005.11, it means `split_suspected = true`.
>   - A `null` result is **never** selected as the reason; it only prevents `extracted`.
>   - If no check fails but at least one is `null`, the reason is `period_not_verified`.
>   - `split_suspected` is `false` whenever the split check cannot be evaluated, for example before D-13 is implemented or when the quote is not on the page.
>
>   The precedence order:
>   1. `evidence_not_verified` (FR-005.1)
>   2. `split_figure` (FR-005.11)
>   3. `value_unparsable` (`value_parsable = false` or `token_parsable = false`)
>   4. `value_not_in_evidence` (FR-005.2)
>   5. `label_not_recognised` (FR-005.10)
>   6. `period_mismatch` (FR-005.9)
>   7. `period_not_verified` (FR-005.7)
>   8. `sign_mismatch` (FR-005.6)
>   9. `scale_not_verified` / `scale_ambiguous` / `currency_not_verified` (FR-005.8)
>   10. `implausible_value` (FR-006.5)
>
>   The relative order of the v0.3 reasons is unchanged; positions 2, 3 and 10 are insertions.
> - **The reason does not hide other failures.** The full `validation` record shows every check, so a reviewer always sees, for example, a failed label check behind a `split_figure` reason.

**Why this ordering makes both new reasons reachable:**
- A suspected split (position 2) is decided from the document's tokens, not from the proposed value. It is therefore reported even when the proposed string is unparsable (position 3) or not literally in the quote (position 4).
- An unparsable value **without** a suspected split falls through to position 3.

**Dependency.** Detecting a suspected split, and condition (N), need D-13 word positions (Phase 2). Until then the field-level checks run as in v0.3. No `split_figure` can be reported before D-13 is implemented.

**Acceptance criteria (AC-A, AC-V):**

| AC | Case | Expected |
|---|---|---|
| AC-A-1 | Each of the four R2 split patterns reproduced synthetically (`88, 136`; `72, 361`; `268, 477`; `(4,901 )`), with the LLM proposing the joined value `88,136` | `requires_review` (`split_figure`); `split_suspected = true`; `value_in_evidence = false` recorded; tokens and boxes recorded |
| AC-A-2 | The LLM proposes one fragment (`136`) | `split_figure` |
| AC-A-3 | The LLM proposes the unparsable string `88, 136` | `split_figure` (**not** `value_unparsable`); `value_parsable = false` recorded |
| AC-A-4 | Two tokens that do not match 11.1 (`12` and `345`; `1,2` and `345`) | `period_not_verified`; `split_suspected = false` |
| AC-A-5 | Any input | No joined value produced; `split_repaired` never set |
| AC-V-1 | The LLM proposes `abc` for a row whose region holds one valid token | `value_unparsable`; `split_suspected = false`; `sign_verified = null`; `plausible = null` |
| AC-V-2 | Proposed value `1,2345` (invalid grouping), no split | `value_unparsable` |
| AC-V-3 | Suspected split **and** label failure | Reason `split_figure`; `label_verified = false` recorded |
| AC-V-4 | Quote not on the page | `evidence_not_verified`; positional checks `null` |
| AC-V-5 | Valid value, wrong sign | `sign_mismatch`; every earlier check `true` |
| AC-V-6 | Every check `true` | `extracted`; `status_reason = null` |
| AC-V-7 | Determinism | The same input always gives the same reason and the same `validation` record |
| AC-V-8 | Invalid column structure (FR-005.7 7.1), no split evaluable | Reason `period_not_verified` (**not** `split_figure`); `split_suspected = false` |
| AC-V-9 (D1) | Proposed value `1,234` (valid); the document token in the claimed column is `1,2345` | `value_unparsable`; `value_parsable = true`; `token_parsable = false` |
| AC-V-10 (D1) | Proposed value `abc`; the document token is `1,234` (valid) | `value_unparsable`; `value_parsable = false`; `token_parsable = true` |
| AC-V-11 (D1) | Suspected split in the region | `token_parsable = null`; reason `split_figure` |
| AC-V-15 (D1) | Region holds a nil token `–`, and the LLM proposes `–` | `value_parsable = true`; `token_parsable = true`; `extracted` as `reported_nil` (D-08) |
| AC-V-12 (D2) | Quote spans a wrapped label line plus one figure line | The figure line is validated; the label comes from the figure line; wrapped line recorded in the quote |
| AC-V-13 (D2) | Quote spans two lines that each hold period-column tokens | `period_not_verified` |
| AC-V-14 (D2) | Quote holds no period-column token | `period_not_verified` |

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

### 3.5 Borrowings — H.3, FR-005.10, H.5 rules 4–5 (DEC-D, R0, OPEN-1 = K2, OPEN-2, OPEN-4, OD-9, Q-Z1, OPEN-3: Proposed by owner (rev 5); awaiting confirmation)

**Affected:**
- H.3 label phrases;
- the FR-005.10 section-heading check;
- H.5 rules 4 and 5;
- H.1 `value_interpretation` (new value `statement_zero`);
- MET-04.

**Unchanged [v0.3]:**
- D-07: lease liabilities are excluded.
- **Total liabilities is never a borrowing value or component.**
- H.4.7: an absent line item is `not_found`, never zero.
- D-08: nil is a reported zero.
- The H.3 definition: borrowings are interest-bearing borrowings **excluding lease liabilities**.

**Proposed now (no open decision involved):**
- **H.3 label phrases.** Add only phrases observed in tuning documents:
  - `borrowings_current`: + "short-term debt"
  - `borrowings_non_current`: + "long-term debt"
  - `current_maturities_long_term_borrowings`: + "current portion of long-term debt"
- **FR-005.10.** The section-heading check applies only to section-dependent labels (initially "borrowings"). **(V2)** The *nearest section heading* is the nearest label-only line above the row that is a section heading under the exact-equality rule in 5.2. A row such as "Other current liabilities 25,020" is never a heading. "Non-current liabilities" matches only the heading "non-current liabilities", never "current liabilities".

#### 3.5.1 H.5 rule 5 — Borrowing aggregation

**Proposed wording:**

> **5. Borrowing aggregation.**
>
> **5.1 Reported total first.** If a total-borrowings line is reported and verified, it is used **on its own**. No component is added to it, and M1 and K2 do not apply. A component and the total that contains it are never both counted.
>
> **5.2 Relevant liability section.** A *section* runs from a configured section start up to and including the next configured section-subtotal row.
> - **Exact matching (V2).** Section headings and section subtotals are matched by **exact normalised equality**, never by phrase presence. Normalisation is FR-013 rule 1, including folding, with one trailing colon removed.
>   - A **section heading** is a **label-only** line whose normalised text equals a configured heading phrase.
>   - A **section subtotal** is a row whose normalised label equals a configured subtotal phrase.
>   - Text that merely *contains* a phrase is neither. For example, "Other current liabilities" is not a heading, and "Total liabilities directly associated with assets held for sale" is not the subtotal "total liabilities".
> - **Section start:** a section heading, or the previous section-subtotal row.
> - **Initial phrases** (observed in tuning; proposed): headings "current liabilities" and "non-current liabilities"; section subtotals "total current liabilities", "total non-current liabilities" and "total liabilities".
> - **Liability scope (R4).** K2 classification (5.3) and M1 (5.4) apply to **every liability section** of the balance-sheet run, whether or not it contains a mapped borrowing row.
>   - **Start:** the first line in the run that is a liability section heading (exact match, V2).
>   - **End (V1, strict):**
>     1. **Printed total:** if **exactly one** row in the run is the subtotal "total liabilities", the scope ends there. **Two or more such rows → undeterminable.**
>     2. **Fallback:** if there is no such row, the scope ends at the **last** liability section-subtotal row **only if** the **next line on the same page** is either:
>        - a label-only line equal to a configured **equity heading** (initially "equity", "stockholders' equity", "shareholders' equity"); or
>        - a row equal to a configured **combined total** ("total equity and liabilities", "total liabilities and stockholders' equity").
>
>        Any other next line, such as a long-term liability row, or "Commitments and contingencies", makes the scope undeterminable. So does no next line on the same page.
>   - **Undeterminable scope:** if the start or end cannot be determined, component aggregation is `requires_review` (`borrowings_classification_unresolved`). Statement-evidenced zero (Z′) condition 8 also treats an undeterminable scope as failing.
>   - Equity rows outside the scope are not classified.
> - A *component section* is a liability section that contains at least one mapped borrowing row. E2 applies to component sections (5.5).
> - **Row (D3).** In rules 5.2 to 5.6, a *row* is a line of the section that holds at least one numeric or nil token assigned to a period column under FR-005.7. Rows whose tokens are 0 or nil are rows.
> - **Label-only lines** are recorded, but are **never classified, summed, or blocking**. These include sub-headings such as "Financial liabilities", lines holding only a note reference such as "Trade payables 2.14", and continuation lines of a wrapped label.
> - **Wrapped labels need no separate rule.** A row whose label is truncated by wrapping does not equal an allowlist or borrowing phrase exactly, so it is unclassified (5.4).
>
> **5.3 Row classification (K2 allowlist).** Every row of **every liability section** (R4), **including rows that are 0 or nil**, is classified in this order of precedence:
> 1. **lease row:** its label contains a configured lease phrase (initially "lease", at a word boundary). Never a component (D-07).
> 2. **mapped borrowing row:** its label matches a borrowing field (H.3, FR-005.10). A component.
> 3. **listed non-debt row:** its label equals a configured non-debt liability phrase (**list OPEN-1, G1 policy below**). Not a component.
> 4. **unclassified row:** any other row.
>
> The section's own subtotal row is the section boundary and is not classified.
>
> **G1 allowlist policy (OPEN-1).**
> - The non-debt list holds only **specific** non-debt liability labels observed in tuning-set documents.
> - **Generic labels can never be listed.** A label containing a configured generic marker (initially "other", "miscellaneous", "sundry") is generic. Configuration that lists such a label is rejected with `E-CONFIG-INVALID`. Generic rows such as "Other current liabilities" are therefore always unclassified and block aggregation.
> - **List contents** stay OPEN until Phase 3. Tuning candidates are recorded in §5, not approved.
>
> **5.4 M1 (both aggregation paths).** If **any liability section** (R4) contains **any unclassified row**, component aggregation is blocked. `total_borrowings` is `requires_review` (`borrowings_classification_unresolved`), and the unclassified labels are recorded. This applies to **both E1 and E2**.
> - **While the non-debt list (OPEN-1) is not approved,** every non-borrowing, non-lease row is unclassified. So component aggregation **always** ends in `requires_review` until the list is approved.
>
> **5.5 Non-overlap evidence.** Provided 5.4 passes, components are added only if non-overlap is established for every pair by:
> - **(E1) Explicit wording:** an inclusion or exclusion phrase (v0.3). An inclusion phrase means the included component is never added. **or**
> - **(E2) Reconciliation with alternatives ruled out.** **All** of the following must hold for **every** period used (current and comparative, DEC-C):
>   - (a) every row of each component section is read uniquely under FR-005.7;
>   - (b) **(R0)** the sum of all **rows** (as defined in 5.2) between the section start and its subtotal row equals the printed subtotal **exactly**, in printed units, with **no tolerance**. Label-only lines are not summed;
>   - (c) **no alternative grouping:**
>     - no row inside the section (other than its subtotal row) has a label containing a configured marker (initially "total", "net", and a leading "less");
>     - no row's value equals the sum of any contiguous run of two or more other rows. **Rows that are 0 or nil in that period are left out of this equality test only.** They remain in the sum in (b) and in the classification in 5.3;
>   - (d) each component is a distinct row, mapped to a distinct borrowing field;
>   - (e) where components lie in different sections, those sections reconcile into a higher printed subtotal (e.g. "total liabilities") under (b) and (c).
>
> **5.6 Current maturities.** `current_maturities_long_term_borrowings` is classified as `included_in_current` or `separate_component` (E1), or as part of an E2 reconciliation. **`not_presented`** (no separate row and no inclusion or exclusion wording) is permitted **only if** E2 holds for the current-liabilities section **and** 5.4 passes. The field is then `not_found`, the derivation records `not_presented`, and the presented borrowing lines are added. Otherwise `total_borrowings` is `requires_review`.
>
> **5.7 Outcome and recording.** If 5.1 does not apply and 5.4 or 5.5 fails, `total_borrowings` is `requires_review` (`borrowings_classification_unresolved`) and excluded from calculations. The record holds:
> - the components and their evidence;
> - every row's classification;
> - the reconciliation arithmetic (`Decimal`);
> - the condition that failed.
>
> Sibling rows, indentation, and a matching total alone are **never** sufficient.
>
> **5.8 Memo display of blocked aggregation (G1 memo requirement).** When `total_borrowings` is `requires_review` because 5.4, 5.5 or 5.6 failed, memo section 7 (Missing information and conflicts) lists:
> - each borrowing component found, with its value, period, page and verbatim quote, labelled `[SOURCE]`;
> - each blocking row (unclassified label, page, quote), or the failed E1/E2 condition;
> - the statement "Borrowing components were **not** summed: <reason>".
>
> **No sum, partial total, or D/E is shown or computed.**
>
> **5.9 Source priority for `total_borrowings` (D4).** The first applicable source is used:
> 1. **Reported total** (5.1).
> 2. **Accepted statement-evidenced zero** (Z′, §3.5.2), only when enabled and accepted.
> 3. **Component aggregation** (5.4–5.6). **v0.3 H.5 rule 4 is restored unchanged:** if `borrowings_non_current` or `borrowings_current` is `not_found`, `total_borrowings` is `not_found`, and a missing component is never assumed to be zero. If either is `conflicting` or `requires_review`, the total takes that status, using the v0.3 H.5 rule 2 order. A reported nil (D-08) is a reported zero, not a missing component.
>
> **Contradictions** across sources make `total_borrowings` `conflicting`, and RI-007 fires:
> - an accepted Z′ alongside a non-zero reported total;
> - an accepted Z′ alongside any non-zero borrowing row for that period.
>
> **Consequence (as in v0.3):** a company that presents only a non-current borrowing row, with no current row, has `total_borrowings` `not_found` unless the current row is reported as `0` or nil.

**Residual limitations (recorded, not mitigated):**
- **Generic rows (G1):** they are never allowlisted, so they block aggregation. Most real balance sheets contain one, so `total_borrowings`, and therefore D/E, will often be `requires_review` when no total line is reported. Coverage is to be measured in D-14b C4 and C5 before any change of policy.
- **Memo note:** the memo limitations section states that borrowings reflect only rows identified as borrowings.

**Tuning observation (not a result).** R2's liability sections sum exactly to their printed subtotals in both years. Conditions (c), 5.3 and 5.4 have **not** been evaluated on R2.

#### 3.5.2 H.5 rule 4 — Borrowing presence and zero evidence (OD-9, Q-Z1 = S1, OPEN-3)

**Proposed wording:**

> **4. Borrowing presence.** For each period, each borrowing field is in exactly one state:
> - **(Z) Reported zero:** a row is present, and its cell is the figure `0` or a nil token, assigned under FR-005.7 with the label passing FR-005.10. Value 0; a nil token has `value_interpretation = reported_nil`.
> - **(Z′) Statement-evidenced zero.** This applies to `total_borrowings` only, and **is disabled until the owner approves lists L1 to L4 (§5, OPEN-3)**. While disabled, a debt-free company without a borrowing row is in state (A). When enabled, a quoted statement establishes `total_borrowings = 0` for **one** period only if **all** of the following hold:
>   1. **Source (S1):** the text is on a statement page of the run (FR-013), or on a **notes page**: a page with a title line (G.0) that begins with a phrase from **L1** (notes headings). No other page is a source, whether highlights, management commentary, or anything else.
>   2. **Phrase:** deterministic local phrase search, with no LLM call, finds a phrase from **L2** (no-borrowings phrases, naming borrowings or debt explicitly).
>   3. **Subject:** the matched phrase is **immediately preceded** by a subject phrase from **L3**. Each L3 entry maps to exactly one scope: a basis, e.g. "the company" → standalone, "the group" → consolidated, or **another entity** (rev 10), e.g. a subsidiary, associate or joint-venture subject such as "Subsidiary X". **That mapping needs owner approval.**
>   4. **Basis and entity:** the subject's mapped basis **equals** the run's basis, **and** the page carries **sufficient** basis evidence for the run's basis. Both are required. Sufficient evidence is only (A4, rev 11):
>      - a basis word equal to the run's basis in the page's notes heading; or
>      - membership of the run, where the run's basis is established by the document (OD-10 `basis_evidence` = `title` or `footnote`).
>
>      A page whose basis is `unknown` is **not** sufficient evidence, nor is a basis held only by analyst assertion (`basis_evidence = analyst_assertion`, OD-10 b′), because it is not established by the document. **Z′ is therefore prohibited whenever the basis rests only on `--assert-basis`** (rev 12): such a candidate is `undetermined` and can never be accepted, whatever its other conditions.
>
>   **Scope status (U2, rev 10; revised in rev 11).** Conditions 3 and 4 also record `statement_scope`, which takes exactly one value:
>   - `target`: conditions 3 and 4 both pass.
>   - `other`: **only** when L3 evidence establishes a different entity or basis (A2), i.e. the L3 subject immediately preceding the phrase maps to:
>     - another entity; or
>     - a basis different from the run's basis.
>   - `undetermined`: every other candidate (entity or basis **cannot be established**). This includes:
>     - no L3 subject immediately precedes the matched phrase;
>     - the subject maps to the run's basis, but the page lacks sufficient basis evidence (condition 4), e.g. unknown basis, analyst assertion only, or a notes heading with no basis word on a page outside the run;
>     - the subject maps to the run's basis, but the page's own evidence names the other basis. Page evidence alone never makes a candidate `other`.
>
>   `statement_scope` is a recorded attribute, not a validation key. A candidate is `target` only when `statement_subject_verified` and `statement_basis_verified` are both `true`.
>   5. **Period:** a full date (FR-005.9 forms) **equal to the period end** is in the *statement window*. The *statement window* is the matched phrase's extracted line plus adjacent lines, up to the first sentence break in each direction. A *sentence break* is a `.` followed by whitespace and an uppercase letter. The window establishes zero for that period only.
>   6. **No qualifier, no other figures (split into two keys, U1, rev 10):**
>      - **6a, no qualifier:** the window contains no phrase from **L4** (qualifiers, e.g. "other than", "except", "excluding", "apart from", "save for").
>      - **6b, no other figures:** the window contains no figure word (G.0) other than the date.
>
>      Both are needed for acceptance. Only a failure of **6a** (an explicit L4 qualifier) can make a candidate blocking. A stray figure alone (6b) fails that candidate but never blocks another one.
>   7. **No contradiction:** no borrowing row for that period holds a non-zero value. A failure creates a conflict **only for a candidate that passes conditions 1–6** for that entity, basis and period (V4; see outcomes below).
>   8. **No unresolved rows (R3):**
>      - no borrowing row for that period is `requires_review` or `conflicting`; **and**
>      - no liability section (5.2, R4) contains an **unclassified** row (5.3) with a non-zero value in that period; **and**
>      - the liability scope is determinable (5.2, V1).
>
>      Rows that are 0 or nil do not fail this condition. While the OPEN-1 non-debt list is unapproved, every non-borrowing, non-lease row is unclassified, so any non-zero one fails this condition.
>
>   **Z′ candidates and outcomes (D5).**
>   - **Candidate:** a phrase from L2 found on a page satisfying condition 1. Matches on any other page are ignored and do not affect status.
>   - **Validation keys.** Each candidate's checks are recorded as dedicated keys, each `true` or `false`: `statement_source_verified` (1), `statement_phrase_verified` (2), `statement_subject_verified` (3), `statement_basis_verified` (4), `statement_period_verified` (5), `statement_no_qualifier` (6a), `statement_no_other_figures` (6b, rev 10), `statement_no_contradiction` (7), `statement_no_unresolved_rows` (8). That is nine keys for eight conditions. "Passes condition 6" means both 6a and 6b are `true`. Each candidate also records `statement_scope` (U2). FR-005.1–.11 are **not** applied to Z′ fields; these keys replace them.
>   - **Multiple candidates (R2).** **All** candidates for the run are evaluated and recorded, each as one **candidate evidence record** (D2, rev 12; below).
>   - **Candidate evidence record (D2, rev 12).** While Z′ is enabled, every candidate is recorded in `derivation.statement_candidates` of `total_borrowings`. The same complete list, in the same order, appears on the `total_borrowings` field of **every** period of the run, whatever that field's status, source or reason. The order is ascending page number, then extracted line index, then character offset. Each record holds:
>     - **Identity and location:**
>       - `candidate_id`: deterministic, from page number, line index and character offset;
>       - `page_number` and `page_label`;
>       - `page_kind`: `statement` or `notes`;
>       - `line_index` and `char_offset` of the matched phrase.
>     - **Text, verbatim:**
>       - `matched_phrase` (L2);
>       - `subject_phrase` (L3), or `null` if none;
>       - `qualifier_phrase` (first L4 match), or `null`;
>       - `statement_window`.
>     - **Date:**
>       - `window_date` (the full date found, or `null`);
>       - `date_status`: `dated`, `other_dated` or `undated`;
>       - `dated_period`: the period end, only when `dated`.
>     - **Scope:**
>       - `statement_scope`;
>       - `page_basis_evidence`: `notes_heading`, `title`, `footnote`, `analyst_assertion` or `none`.
>     - **Validation outcomes:** all nine keys.
>       - Keys 1 to 6b hold one value each, `true` or `false`.
>       - Keys 7 (`statement_no_contradiction`) and 8 (`statement_no_unresolved_rows`) depend on the period. Each is a map from **every** period end of the run to `true` or `false`.
>     - **Role:** `blocking_b1`, `blocking_b2` or `non_blocking`. The role classifies the candidate from its own outcomes. It does **not** by itself state that any period was blocked (rev 13).
>     - **`affected_periods`:** a list of `{period_end, effect}`, where `effect` is:
>       - `accepted`: this candidate establishes Z′ for that period;
>       - `blocked`: B1 or B2 blocks that period;
>       - `conflict`: a condition-7 conflict under V4, or a 5.9 contradiction with a non-zero reported total (below);
>       - `not_consulted` (rev 13): a reported total was selected for that period (5.9 step 1), so Z′ did not determine its value or reason.
>
>       It is empty when the candidate affects no period, e.g. when it is recorded only.
>     - **Reported total selected (rev 13).** For each period P whose `total_borrowings` comes from a reported total (5.9 step 1):
>       - the reported total stays authoritative for value, status and reason;
>       - every candidate keeps its complete record (identity, text, date status, scope, all nine outcomes, role);
>       - every candidate gets `{P, not_consulted}`. No candidate is marked `blocked` or `accepted` for P, whatever its role.
>
>       **Single exception, the 5.9 contradiction check (AC-D-24, unchanged):** if P's reported total is non-zero and Z′ would be accepted for P under the full multiple-candidate rule (B1 and B2 applied), the field is `conflicting` and RI-007 fires. The accepting candidate then gets `{P, conflict}` instead of `not_consulted`; all others keep `not_consulted`.
>
>     When Z′ is accepted, the field's own `validation` keys equal the accepting candidate's, with keys 7 and 8 taken for that period. The record never alters the field's status or reason. It preserves the evidence that the single `status_reason` cannot carry.
>     - **Date status (V3).** Each candidate records the full date found in its statement window, if any, and whether it is:
>       - *dated* — equal to a period end;
>       - *other-dated* — a full date equal to no period end;
>       - *undated* — no full date in the window.
>     - **Acceptance (V3).** Z′ is accepted for period P **only if**:
>       - at least one candidate **dated to P** passes all eight conditions; **and**
>       - no **blocking** candidate applies to P.
>     - **Blocking candidates (V3; revised in rev 9 and rev 10).** A candidate blocks **only if** one of these holds:
>       - **(B1) Qualified, same scope:** it fails **6a** (an explicit L4 qualifier) **and** `statement_scope = target`, i.e. its entity and accounting basis match the target. A 6b failure (stray figure) alone never makes a candidate blocking (U1).
>       - **(B2) Undetermined scope (U2; confirmed as A1 in rev 11):** `statement_scope = undetermined`, **whether or not** it carries a qualifier. Z′ cannot be accepted while the entity or basis of a matching statement cannot be established. A B2 candidate never creates `conflicting`.
>
>       A blocking candidate blocks:
>       - P, if dated to P;
>       - **every** period, if undated or other-dated. This is limited to the run's own entity and basis, which are the only ones Z′ is evaluated for in a run.
>
>       A block only prevents acceptance. It never creates `conflicting` by itself: the period's result comes from the "Z′ not accepted" rule below, which gives `requires_review` (`statement_scope_undetermined` or `statement_zero_not_verified`) when no reported total and no borrowing row exist for that period.
>     - **All other candidates are recorded only (rev 10).** A candidate that meets neither B1 nor B2 never blocks, whatever conditions it fails. Examples:
>       - `statement_scope = other` (another entity or basis), **whether or not** it carries a qualifier;
>       - a candidate failing only 6b (stray figure);
>       - an unqualified `target` candidate failing condition 5, 7 or 8, or any combination of them.
>
>       Such a candidate creates a conflict only under the condition-7 rule below (V4). An undated statement can never *create* a zero, because acceptance needs a dated candidate.
>   - **Accepted (`extracted`)** only under the multiple-candidate rule, for a candidate with all nine keys `true` (`statement_scope = target`):
>     - value 0; `origin = source`; `value_interpretation = statement_zero`;
>     - `raw_value` = the matched L2 phrase, verbatim;
>     - `evidence_quote` = the statement window, verbatim;
>     - `page_number` recorded;
>     - `currency` = the document-level `reporting_currency`, which must be `extracted` (H.1.2); otherwise the candidate is not accepted;
>     - `scale`, `line_item_label` and `page_label` are **not applicable** (null) for `statement_zero`. This is an exception to the v0.3 H.1 "required for source" rule, limited to `value_interpretation = statement_zero`.
>   - **Condition 7 fails (V4):** `total_borrowings` is `conflicting` **only if** that candidate passes conditions 1–6 for the period (it is valid evidence about this entity, basis and period). A candidate that fails any of conditions 1–6, including any `other` or `undetermined` candidate, is recorded only. Its condition-7 result creates no conflict, and the result comes from 5.9.
>   - **Z′ not accepted for a period for any other reason** (conditions 3–6 or 8, or the multiple-candidate rule, including a B1 or B2 block):
>     - **(R1)** if **no reported total exists and no borrowing row exists for that period** (every borrowing field in state (A)), `total_borrowings` is `requires_review`. The reason follows this **Z′ reason precedence** (A3, rev 11), first match wins:
>       1. **`statement_scope_undetermined`**, if any B2 candidate applies to that period (dated to it, undated, or other-dated);
>       2. **`statement_zero_not_verified`**, in every other case.
>
>       These two reasons are used only for `total_borrowings` under R1. They are not FR-005 check reasons and are not part of the FR-005.3 precedence order.
>     - **otherwise**, the candidates are recorded only, and the result comes from the reported total (5.9 step 1) or the component rules (5.9 step 3, including the restored v0.3 missing-component rule). Neither `statement_scope_undetermined` nor `statement_zero_not_verified` is used in this case.
>
>   Lease liabilities are unaffected (D-07).
> - **(A) Absent:** no row and no accepted statement → `not_found`. Absence is never zero.
> - **(U) Unidentifiable:** a candidate row exists but fails FR-005.7 or FR-005.10 → `requires_review`; or Z′ is not accepted while no reported total and no borrowing row exist for that period → `requires_review` (`statement_scope_undetermined` or `statement_zero_not_verified`, by the Z′ reason precedence; R1).
>
> **MET-04 (amended).** D/E = 0 only if `total_borrowings` is evidenced zero (Z, or every component Z, or Z′ when enabled) **and** `total_equity` is `extracted` and > 0. Equity ≤ 0 follows MET-04 v0.3 and RI-004 C3. From (A) or (U), MET-04 is undefined (`missing_input` or `input_requires_review`). It is never 0.

**Acceptance criteria (AC-D, AC-Z):**

In AC-Z tests, a Z′ candidate has `statement_scope = target` unless the case states otherwise (rev 11).

| AC | Case | Expected |
|---|---|---|
| AC-D-1 | Reported total-borrowings line plus components | Only the total is used; no component added; K2 and M1 not applied |
| AC-D-2 | E1 inclusion phrase, section fully classified; E1 exclusion phrase, section fully classified | Not added; added |
| AC-D-3 | E1 path with one unclassified row | `requires_review`; label recorded |
| AC-D-4 | E2 with (a)–(e) satisfied in both periods and every row classified | Components summed; arithmetic and classifications recorded |
| AC-D-5 | Section off by 1 unit (R0) | `requires_review` |
| AC-D-6 | Reconciles in one period only | `requires_review` |
| AC-D-7 | "Total …" or "Less …" row inside the section | `requires_review` |
| AC-D-8 | One row equals the sum of two contiguous others | `requires_review` |
| AC-D-9 | Three zero rows, all classified, in a reconciling section | Not blocked by (c) |
| AC-D-10 | A zero-valued **unclassified** row (e.g. "Commercial paper –") | Blocks aggregation (K2 applies to zero rows) |
| AC-D-11 | "Operating lease liabilities" row | Lease row; never a component; does not block |
| AC-D-12 | Non-debt list (OPEN-1) empty or unapproved | Component aggregation always `requires_review` |
| AC-D-13 | `not_presented` current maturities with E2 and 5.4 passing; with E2 failing | Summed, with `not_presented` recorded; `requires_review` |
| AC-D-14 | Siblings or indentation only | `requires_review` |
| AC-D-15 | Total liabilities present | Never used as borrowings |
| AC-D-16 (D3) | Section containing label-only sub-headings ("Financial liabilities", "Trade payables 2.14") whose rows are all classified and reconcile | Label-only lines neither classified nor summed; aggregation proceeds |
| AC-D-17 (D3) | Nil-only row (e.g. "Borrowings –") | Counted as a row; classified; included in the sum as 0 |
| AC-D-18 (G1) | "Other current liabilities" row in the section | Unclassified → aggregation blocked |
| AC-D-19 (G1) | Configuration lists "Other payables" in the non-debt list | Rejected with `E-CONFIG-INVALID` |
| AC-D-20 (memo) | Aggregation blocked by one unclassified row | Memo section 7 lists each component (value, page, quote, `[SOURCE]`) and the blocking row; no sum, no D/E |
| AC-D-21 (D4) | Non-current row present; no current-borrowings row; no total; no Z′ | `total_borrowings` `not_found`; MET-04 `missing_input` |
| AC-D-22 (D4) | Non-current `requires_review`; current `extracted` | `total_borrowings` `requires_review` |
| AC-D-23 (D4) | Reported total present together with components | Reported total used (priority 1); components not added |
| AC-D-24 (D4) | Accepted Z′ and non-zero reported total | `conflicting`; RI-007 fires |
| AC-D-25 (R4) | Components in the current and non-current sections; a separate liability section with **no** mapped row contains "Debentures 300" | Unclassified → aggregation blocked (`requires_review`); label recorded |
| AC-D-26 (R4) | Ind AS layout with no "total liabilities" row (sections end at "Total current liabilities", then "Total equity and liabilities") | Scope ends at "Total current liabilities"; equity rows not classified |
| AC-D-27 (R4) | Liability scope start or end cannot be determined | Component aggregation `requires_review` (`borrowings_classification_unresolved`) |
| AC-D-28 (R4) | Equity section printed before liabilities (Ind AS order) | Equity rows outside the scope; not classified, not blocking |
| AC-D-29 (V1) | US layout with no "Total liabilities": "Total current liabilities", long-term rows, "Commitments and contingencies", equity, combined total | Scope undeterminable → `requires_review` |
| AC-D-30 (V1) | Ind AS: last liability subtotal directly followed by "Total equity and liabilities" on the same page | Scope ends at that subtotal |
| AC-D-31 (V1) | Last liability subtotal directly followed by the label-only heading "Stockholders' equity" | Scope ends at that subtotal |
| AC-D-32 (V1) | Last liability subtotal followed by "Long-term debt 40,152" | Scope undeterminable → `requires_review` |
| AC-D-33 (V1) | Last liability subtotal is the last statement line on its page | Scope undeterminable → `requires_review` |
| AC-D-34 (V2) | Row "Other current liabilities 25,020" | Not a section heading; classified as a row |
| AC-D-35 (V2) | Heading "Non-current liabilities" with a "Borrowings" row under it | Matches only "non-current liabilities"; passes the heading check for `borrowings_non_current`, fails it for `borrowings_current` (`label_not_recognised`) |
| AC-D-36 (V2) | Heading "Current liabilities:" (trailing colon) | Matches "current liabilities" |
| AC-D-37 (V2) | Two rows equal to "Total liabilities" in one run | Scope undeterminable → `requires_review` |
| AC-D-38 (V2) | Row "Total liabilities directly associated with assets held for sale 120" | Not the subtotal "total liabilities"; classified as a row (unclassified unless listed) |
| AC-Z-1 | Row with `0`; row with `–` | Value 0 (Z); `reported_nil` |
| AC-Z-2 | No row, no statement | `not_found`; MET-04 `missing_input` |
| AC-Z-3 | Z′ lists **not approved**, valid-looking statement present | Z′ not used → state (A), `not_found` |
| AC-Z-4 | Z′ enabled (test configuration only): notes-heading title line naming "standalone"; "The Company has no borrowings as at March 31, 2025" on a standalone run; reporting currency `extracted` | `extracted`; value 0; `statement_zero`; all nine `statement_*` keys `true`; `statement_scope = target`; `scale` and `line_item_label` null; MET-04 = 0 when equity > 0 |
| AC-Z-5 | Same sentence in management commentary | Not a candidate (ignored); no effect on status |
| AC-Z-6 | "The Group has no borrowings…" on a standalone run; "The Company…" on a consolidated run; no borrowing rows | `statement_basis_verified = false`; `statement_scope = other`; `total_borrowings` `requires_review` (`statement_zero_not_verified`) |
| AC-Z-7 | "Subsidiary X has no borrowings…" (L3 maps "Subsidiary X" to another entity); no borrowing rows | `statement_subject_verified = false`; `statement_scope = other`; `requires_review` (`statement_zero_not_verified`) |
| AC-Z-8 | Date on a non-adjacent line, or beyond a sentence break; no borrowing rows | `statement_period_verified = false`; `requires_review` (`statement_zero_not_verified`) |
| AC-Z-9 | Date for the comparative period only | Zero for the comparative only; current unaffected |
| AC-Z-10 (revised rev 10) | Window contains "other than term loans"; no borrowing rows | `statement_no_qualifier = false`; `requires_review` (`statement_zero_not_verified`) |
| AC-Z-11 | Candidate passing conditions 1–6 for that period, plus a non-zero borrowing row for that period | `conflicting`; RI-007 fires |
| AC-Z-12 | Evidenced zero with equity −40 | MET-04 undefined (negative equity); RI-004 C3 fires |
| AC-Z-13 | Z′ with a lease row present | Lease row unaffected; still excluded |
| AC-Z-14 (D5) | Z′ candidate failing condition 4 because its L3 subject maps to the other basis (`statement_scope = other`), but components aggregate successfully | Component total used; candidate recorded with `statement_basis_verified = false`; no change of status |
| AC-Z-15 (D5) | Otherwise valid candidate, but `reporting_currency` not `extracted` | Not accepted; recorded |
| AC-Z-16 (D5) | Z′ field | FR-005.1–.11 keys absent or not applied; the nine `statement_*` keys and `statement_scope` present |
| AC-Z-17 (R1) | Candidate fails condition 4; non-current borrowing row present; no current row; no reported total | `total_borrowings` `not_found` (v0.3 missing-component rule); candidate recorded; **not** `statement_zero_not_verified` |
| AC-Z-18 (R1) | Candidate fails condition 5; reported total present | Reported total used; candidate recorded only |
| AC-Z-19 (R2, clarified rev 10) | Two candidates with matching dates on source pages: one passes all; the other contains "other than term loans" and **matches the target entity and accounting basis** (`statement_scope = target`); no borrowing rows | Z′ not accepted; `requires_review` (`statement_zero_not_verified`); both recorded |
| AC-Z-20 (R2) | Two candidates: one passes all; the other is "Subsidiary X has no borrowings" (fails condition 3 only; L3 maps "Subsidiary X" to another entity, `statement_scope = other`) | Z′ accepted; both recorded |
| AC-Z-21 (R2, revised by V3) | One candidate passes all for 2025-03-31; another is undated with **no** qualifier | Z′ **accepted** for 2025-03-31; undated candidate recorded, non-blocking |
| AC-Z-22 (R2) | One passing candidate for 2025-03-31; one passing candidate for 2024-03-31 | Z′ accepted separately for each period |
| AC-Z-23 (R3) | Valid candidate; a borrowing row for that period is `requires_review` | Z′ not accepted; `statement_no_unresolved_rows = false`; total `requires_review` from the component rules (not `statement_zero_not_verified`) |
| AC-Z-24 (R3) | Valid candidate; a borrowing row for that period is `conflicting` | Z′ not accepted; total `conflicting` |
| AC-Z-25 (R3) | Valid candidate; no borrowing rows; a non-zero "Commercial paper" row (unclassified) | Z′ not accepted; `statement_no_unresolved_rows = false`; `requires_review` (`statement_zero_not_verified`) |
| AC-Z-26 (R3) | Valid candidate; no borrowing rows; an unclassified row that is `–` | Condition 8 not failed by it; Z′ accepted if all else passes |
| AC-Z-27 (R3) | Valid candidate; OPEN-1 list unapproved; a non-zero "Trade payables" row | Unclassified → condition 8 fails; Z′ not accepted |
| AC-Z-28 (V3, rev 9) | Valid candidate dated 2025-03-31; another **undated** candidate, same entity and basis: "The Company has no borrowings other than vehicle loans" | Not accepted for any period (blocking applies to every period) |
| AC-Z-29 (V3, rev 9) | Valid candidate dated 2025-03-31; a qualified candidate dated 2024-03-31, same entity and basis | 2025-03-31 accepted; 2024-03-31 blocked |
| AC-Z-30 (V3) | Valid candidate dated 2025-03-31; an unqualified candidate dated 2024-09-30 (other-dated) | 2025-03-31 accepted; other-dated candidate recorded, non-blocking |
| AC-Z-31 (V3) | Only undated, unqualified candidates; no borrowing rows; no reported total | Z′ not accepted (no dated candidate) → `requires_review` (`statement_zero_not_verified`) |
| AC-Z-32 (rev 9) | Valid candidate dated 2025-03-31; an undated qualified candidate about "Subsidiary X" (fails condition 3; `statement_scope = other`) | **2025-03-31 accepted**; qualified candidate recorded, non-blocking |
| AC-Z-36 (rev 9) | Valid candidate dated 2025-03-31 on a standalone run; an undated qualified candidate in the **consolidated** notes ("The Group has no borrowings other than…", fails condition 4; `statement_scope = other`) | 2025-03-31 accepted; candidate recorded, non-blocking |
| AC-Z-37 (rev 9) | Qualified candidate about "Subsidiary X" (`statement_scope = other`), dated 2025-03-31, plus a non-zero borrowing row; no other candidate | No conflict; no blocking; result from the component rules |
| AC-Z-38 (rev 9) | Qualified candidate, other-dated (2024-09-30), same entity and basis; valid candidate dated 2025-03-31 | Not accepted for any period (blocks every period) |
| AC-Z-33 (V4) | "Subsidiary X has no borrowings as at March 31, 2025" (fails condition 3; `statement_scope = other`), plus a non-zero borrowing row | **Not** `conflicting`; candidate recorded; result from component rules |
| AC-Z-34 (V4, clarified rev 11) | Candidate whose L3 subject maps to the other basis ("The Group…" on a standalone run; fails condition 4; `statement_scope = other`), plus a non-zero borrowing row | **Not** `conflicting`; result from component rules |
| AC-Z-35 (V1) | Valid candidate; no borrowing rows; liability scope undeterminable | Condition 8 fails; Z′ not accepted → `statement_zero_not_verified` |
| AC-Z-39 (U1, rev 10) | Valid candidate dated 2025-03-31; another undated, unqualified candidate, same entity and basis, whose window contains the figure `12.5` | 2025-03-31 accepted; other candidate `statement_no_other_figures = false`, recorded, non-blocking |
| AC-Z-40 (U1, rev 10) | Only candidate dated 2025-03-31, unqualified, window contains `12.5`; no borrowing rows; no reported total | `statement_no_qualifier = true`; `statement_no_other_figures = false`; Z′ not accepted → `requires_review` (`statement_zero_not_verified`) |
| AC-Z-41 (U2, rev 10) | Valid candidate dated 2025-03-31; an undated candidate with **no** L3 subject: "There are no borrowings other than vehicle loans"; no borrowing rows; no reported total | `statement_scope = undetermined`; blocks every period; `requires_review` (`statement_scope_undetermined`); **not** `conflicting` |
| AC-Z-42 (U2, rev 10) | Valid candidate dated 2025-03-31; an unqualified candidate with no L3 subject, dated 2024-03-31 ("There are no borrowings as at March 31, 2024"); no borrowing rows; no reported total | 2025-03-31 accepted; 2024-03-31 blocked → `requires_review` (`statement_scope_undetermined`) |
| AC-Z-43 (U2, rev 10) | Only candidate: "The Company has no borrowings as at March 31, 2025" on a standalone run, on a notes page whose heading has no basis word and which is not in the run; no borrowing rows; no reported total | `statement_basis_verified = false`; `statement_scope = undetermined`; `requires_review` (`statement_scope_undetermined`) |
| AC-Z-44 (U2, rev 10) | Undetermined-scope candidate dated 2025-03-31, plus a non-zero borrowing row for that period | **Not** `conflicting`; candidate recorded; result from the component rules |
| AC-Z-45 (U2, rev 10) | Undetermined-scope candidate dated 2025-03-31; reported total present | Reported total used (5.9 step 1); candidate recorded; neither `statement_scope_undetermined` nor `statement_zero_not_verified` |
| AC-Z-46 (A4, rev 11; wording corrected rev 12) | "The Company has no borrowings as at March 31, 2025" on a statement page with no title or footnote basis evidence, included by `--pages` with `--assert-basis standalone`. Under OD-10 b′ the page is treated as standalone, with `basis_evidence = analyst_assertion`. No borrowing rows; no reported total | `statement_basis_verified = false`; `statement_scope = undetermined`; `requires_review` (`statement_scope_undetermined`) |
| AC-Z-47 (A4, rev 11) | Same sentence on a statement page of a standalone run whose basis is established by footnote (`basis_evidence = footnote`) | `statement_basis_verified = true`; `statement_scope = target`; accepted if all else passes |
| AC-Z-48 (A2, rev 11) | "The Company has no borrowings as at March 31, 2025" (L3 → standalone) on a standalone run, on a notes page whose heading names "consolidated" | `statement_scope = undetermined` (page evidence alone never gives `other`); B2 applies to 2025-03-31 |
| AC-Z-49 (A2, rev 11) | Undated candidate whose phrase is preceded by a subject phrase **not** in L3 (e.g. "The trust has no borrowings") | `statement_subject_verified = false`; `statement_scope = undetermined`; blocks every period |
| AC-Z-50 (A3, rev 11) | No borrowing rows; no reported total; a qualified `target` candidate dated 2025-03-31 (B1) **and** an undetermined candidate dated 2025-03-31 (B2) | `requires_review` with reason `statement_scope_undetermined` (precedence 1); not `conflicting` |
| AC-Z-51 (A3, rev 11) | No borrowing rows; no reported total; only an `other` candidate ("Subsidiary X…") and an undated `target` candidate | `requires_review` with reason `statement_zero_not_verified` (no B2 candidate) |
| AC-Z-52 (A1, rev 11) | Undetermined, **unqualified** candidate dated 2025-03-31 that otherwise passes conditions 1, 2, 5–8; a valid `target` candidate dated 2025-03-31; no borrowing rows; no reported total | Z′ not accepted for 2025-03-31; `requires_review` (`statement_scope_undetermined`) |
| AC-Z-53 (D2, rev 12) | The AC-Z-50 case: no borrowing rows; no reported total; candidate Q (qualified, `target`, dated 2025-03-31) and candidate U (no L3 subject, dated 2025-03-31) | `status_reason = statement_scope_undetermined`. `derivation.statement_candidates` of the 2025-03-31 `total_borrowings` holds **both** records, in page/line/offset order, each complete. Q: `statement_scope = target`, `statement_no_qualifier = false`, `qualifier_phrase` verbatim, role `blocking_b1`, `affected_periods = [{2025-03-31, blocked}]`. U: `statement_scope = undetermined`, `subject_phrase = null`, `statement_subject_verified = false`, role `blocking_b2`, `affected_periods = [{2025-03-31, blocked}]`. The 2024-03-31 field carries the identical list |
| AC-Z-54 (D2, rev 12; revised rev 13) | The AC-Z-45 case: undetermined candidate dated 2025-03-31; reported totals selected for 2025-03-31 and 2024-03-31 | Reported total used, with its own status and reason; candidate record present and complete: role `blocking_b2`, all nine outcomes, keys 7 and 8 mapped for every period. `affected_periods = [{2025-03-31, not_consulted}, {2024-03-31, not_consulted}]`; **no** `blocked` entry |
| AC-Z-57 (rev 13) | Non-zero reported total for 2025-03-31; one candidate dated 2025-03-31 passing all eight conditions, `target`, no block | `conflicting`; RI-007 fires (AC-D-24). Candidate `affected_periods` includes `{2025-03-31, conflict}`, not `not_consulted` |
| AC-Z-58 (rev 13) | Non-zero reported total for 2025-03-31; candidate A dated 2025-03-31 passing all eight conditions; candidate Q qualified, `target`, dated 2025-03-31 (B1) | Z′ would not be accepted, so no contradiction: reported total used. A: `{2025-03-31, not_consulted}`, role `non_blocking`. Q: `{2025-03-31, not_consulted}`, role `blocking_b1`, `statement_no_qualifier = false`. **No** `blocked` entry |
| AC-Z-59 (rev 13) | Reported total `0` for 2025-03-31; one candidate passing all eight conditions, dated 2025-03-31 | Reported total used (value 0, `origin = source` as a reported total, not `statement_zero`); candidate `{2025-03-31, not_consulted}`; not `conflicting` |
| AC-Z-55 (D2, rev 12) | The AC-Z-20 case (one accepted candidate; one "Subsidiary X" candidate) | Accepted candidate: role `non_blocking`, `affected_periods = [{2025-03-31, accepted}]`; the field's `validation` equals its keys for that period. Subsidiary candidate: `statement_scope = other`, role `non_blocking`, `affected_periods = []` |
| AC-Z-56 (D2, rev 12) | Z′ disabled (lists unapproved) | No `derivation.statement_candidates` key is produced |

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
>   - **Footnote matching (rev 12): case-insensitive, exact, normalised.**
>     - Both the extracted line and the configured phrase are normalised with FR-013 rule 1 (NFKC, case-folding, apostrophe and dash folding). Runs of whitespace are then collapsed to one space, and leading and trailing whitespace is removed.
>     - A match needs the normalised configured phrase to occur **exactly**, as a contiguous whole-word sequence, within **one** normalised extracted line. "Whole-word" means it is bounded by the line start or end, whitespace, or punctuation.
>     - No fuzzy, partial-word, singular/plural or cross-line matching.
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
| AC-OD10-6 (rev 12) | Footnote line "The accompanying notes form an integral part of the Standalone financial statements." with the configured phrase "integral part of the standalone financial statements" | Match (case differs only); run basis `standalone`; `basis_evidence = footnote` |
| AC-OD10-7 (rev 12) | Footnote lines "…INTEGRAL PART OF THE STANDALONE FINANCIAL STATEMENTS" and "…integral  part of the standalone financial statements" (double space) | Both match |
| AC-OD10-8 (rev 12) | "…integral part of the standalone financial statement" (singular); "…integral part of the standalone financials"; the phrase split across two extracted lines | No match in each case; basis not established by footnote |

### 3.8 FR-004.3 and FR-005.10 — Formats and labels

**Affected:** FR-004.3 (grouping rule added); FR-005.10 (folding and observed label phrases).

**Proposed wording:**

> **FR-004.3, added.** A figure with thousands separators is valid only if its integer part matches, **in full**, either:
> - **Western:** `d{1,3}(,ddd)+`; or
> - **Indian:** `d{1,3}(,dd)*,ddd`.
>
> R1's share counts are printed in the Indian form with a 3-digit leading group, e.g. `415,19,36,905`. Anything else (`1,2345`, `12,34,5`) fails the parse check and becomes `requires_review` (`value_unparsable`), unless it is part of a suspected split figure (§3.2). Each figure is judged on its own; one document may use both forms.
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
- **Grouping:** `1,24,936`, `162,990` and `415,19,36,905` are valid; `1,2345` and `12,34,5` → `requires_review` (`value_unparsable`).
- **Folding:** "Total stockholders’ equity" with U+2019 matches.
- **Exact matching:** "Finance cost" matches `interest_expense`; "Total equity attributable to …" does **not** match `total_equity`.
- **Sign rules unaffected:** a folded dash in a label doesn't change FR-005.6 sign handling.

### 3.9 `TextExtractor.extract_words` (L.3; D-01a replaceability preserved)

**Affected:** L.3 and L.4; the `TextExtractor` interface.

> `TextExtractor` gains `extract_words(path) -> list[PageWords]`, giving words with text, `x0`, `x1`, `top`, `bottom`, and 1-based physical page number. It is deterministic for the same file and the locked dependency versions. pdfplumber stays confined to `pdfplumber_extractor.py`. It is implemented at the **start of Phase 2**.

**Tests:** word boxes for a synthetic page; determinism across calls; physical page numbers; a fake extractor satisfies the interface.

---

### 3.10 J.1 and J.3 — Relative-change conditions (Q-Z6 and OPEN-5: Proposed by owner (rev 5); awaiting confirmation)

**Affected:**
- J.1 (new general rule);
- J.3 RI-003 C2 and RI-004 C1.

**Unchanged:** RI-003 C1, RI-004 C2 and C3, FR-008.2, and MET-03 / MET-04 rules.

**Proposed wording:**

> **J.1 (added). Relative-change conditions.** A rule condition defined as a relative change against the comparative period is `not_evaluable` when the comparative value is **0** (a relative change from zero is undefined) **or undefined**. **Absolute conditions** in the same rule are evaluated independently. The rule's overall result follows FR-008.2.
>
> **J.3 (applied).**
> - **RI-003 C2** (current ratio fell by ≥ 10%) and **RI-004 C1** (D/E rose by ≥ 20%) are relative-change conditions under J.1.
> - **RI-003 C1** (current ratio < 1.00), **RI-004 C2** (D/E > 2.00), and **RI-004 C3** (equity ≤ 0) are absolute.

RI-001 is unaffected: a zero comparative revenue already makes MET-01 undefined (`zero_denominator`), so RI-001 is `not_evaluable`.

**Consequence.** A move from zero to a high ratio is still caught by the absolute condition. A move from zero to a low ratio is not flagged by the relative condition. It shows as `not_evaluable`, never as `not_triggered`.

**Acceptance criteria (AC-Q6):**

| AC | Case | Expected |
|---|---|---|
| AC-Q6-1 | Comparative D/E 0, current 0.5 | RI-004 C1 `not_evaluable`, C2 `not_triggered` → rule `not_evaluable` |
| AC-Q6-2 | Comparative D/E 0, current 2.5 | C1 `not_evaluable`, C2 fires → `triggered` (`elevated`) |
| AC-Q6-3 | Comparative D/E 0, current equity −10 | C3 fires → `triggered` (`elevated`) |
| AC-Q6-4 | Comparative D/E undefined (borrowings `not_found`), current 0.5 | C1 `not_evaluable` → rule `not_evaluable` |
| AC-Q6-5 | Comparative current ratio 0, current 0.8 | RI-003 C2 `not_evaluable`, C1 fires → `triggered` (`elevated`) |
| AC-Q6-6 | Comparative current ratio 0, current 1.5 | C2 `not_evaluable`, C1 `not_triggered` → rule `not_evaluable` |
| AC-Q6-7 | Comparative current ratio undefined | C2 `not_evaluable`; C1 evaluated independently |

### 3.11 Schema additions (H.1) arising from revisions 4 and 5

| Attribute | Change | Source |
|---|---|---|
| `status_reason` | + `split_figure`, + `value_unparsable` | §3.2 |
| `validation` | Each check records `true`, `false`, or `null` (not evaluable, never a pass). Keys: `evidence_verified`, `value_parsable` (new; proposed value), `token_parsable` (new; document token, `null` unless the region holds exactly one numeric or nil token; a nil token is parsable), `value_in_evidence`, `label_verified`, `period_end_verified`, `period_column_verified`, `sign_verified`, `scale_verified`, `currency_verified`, `plausible` (new). Plus the Boolean **`split_suspected`** (new; always `true` or `false`). | §3.2 (S1–S3) |
| `value_interpretation` | + `statement_zero` (only when Z′ is enabled) | §3.5.2 |
| `validation` (Z′ fields only) | `statement_source_verified`, `statement_phrase_verified`, `statement_subject_verified`, `statement_basis_verified`, `statement_period_verified`, `statement_no_qualifier` (6a), `statement_no_other_figures` (6b, rev 10), `statement_no_contradiction`, `statement_no_unresolved_rows` (R3). These replace FR-005.1–.11 keys for `statement_zero`. Plus the recorded attribute `statement_scope` (`target` / `other` / `undetermined`; U2, rev 10; `other` only from L3 evidence, rev 11). | §3.5.2 (D5) |
| Source-required attributes | Exception: `scale`, `line_item_label` and `page_label` are null for `value_interpretation = statement_zero` | §3.5.2 (D5) |
| `status_reason` | + `statement_zero_not_verified` | §3.5.2 (D5; recommendation, awaiting confirmation) |
| `status_reason` | + `statement_scope_undetermined` (`total_borrowings` only, under R1; Z′ reason precedence 1, before `statement_zero_not_verified`) | §3.5.2 (A3, rev 11; proposed by owner, awaiting confirmation) |
| `derivation.statement_candidates` | Z′ enabled only: one candidate evidence record per candidate (identity and location, verbatim text, date status, `statement_scope`, `page_basis_evidence`, all nine validation outcomes with keys 7 and 8 per period, role, `affected_periods`). `effect` values: `accepted`, `blocked`, `conflict`, and `not_consulted` (rev 13: the period's reported total was selected). The identical ordered list appears on `total_borrowings` for every period | §3.5.2 (D2, rev 12; rev 13) |
| `derivation.component_classification` | Per-row classification (lease / mapped / listed non-debt / unclassified), current-maturities classification (`included_in_current`, `separate_component`, `not_presented`, `unresolved`), the reconciliation arithmetic, and the failed condition | §3.5.1 |

No new error codes (G.1) are required.

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

| ID | Status | Content | Deadline |
|---|---|---|---|
| D-13, D-14a, DEC-B, DEC-C, DEC-E, OD-10, OQ-3 | Accepted in principle (rev 3) | See §3.1, §4, §3.3, §3.4, §3.6, §3.7 | Formal approval when v0.4 is approved |
| DEC-A | **Proposed by owner (rev 5); awaiting confirmation** | Reconstruction disabled; original text and positions kept | v0.4 approval |
| Q-A1 | **Proposed by owner (rev 5); awaiting confirmation** | `split_figure` for a suspected split | v0.4 approval |
| S1–S3 | **Proposed by owner (rev 5); awaiting confirmation** | Every check runs and is recorded (`true`/`false`/`null`); one fixed precedence order; `split_suspected` flag | v0.4 approval |
| `value_unparsable` | **Proposed by owner (rev 5); awaiting confirmation** | Distinct reason for unparsable values that are not suspected splits | v0.4 approval |
| DEC-D, Q-D1 (R0) | **Proposed by owner (rev 5); awaiting confirmation** | Conservative aggregation; exact reconciliation, no tolerance | v0.4 approval |
| OPEN-1 → K2 | **Proposed by owner (rev 5); awaiting confirmation** | Allowlist; any unclassified row blocks component aggregation | v0.4 approval (rule) |
| OPEN-1 policy → G1 | **Proposed by owner (rev 6); awaiting confirmation** | Specific non-debt labels only; generic markers ("other", "miscellaneous", "sundry") can never be listed (`E-CONFIG-INVALID`) | v0.4 approval |
| Memo display of blocked aggregation (5.8) | **Proposed by owner (rev 6); awaiting confirmation** | Components and blocking rows listed with evidence; no sum, no D/E | v0.4 approval |
| D1–D5 fixes | **Proposed by owner (rev 6); awaiting confirmation** | `token_parsable`; figure line; row definition; v0.3 rule 4 restored with source priority (5.9); Z′ status, keys and schema | v0.4 approval |
| `statement_zero_not_verified` | **Recommendation from Claude; awaiting confirmation** | Reason when Z′ is not accepted **and** no reported total and no borrowing row exist for that period (R1), **and** no B2 candidate applies to that period. Otherwise `statement_scope_undetermined` takes precedence (rev 11 precedence; entry corrected in rev 12) | v0.4 approval |
| R1–R4 | **Proposed by owner (rev 7); awaiting confirmation** | R1 scope of `statement_zero_not_verified`; R2 conservative multiple-candidate rule; R3 condition 8 (unresolved borrowing rows or non-zero unclassified rows reject Z′); R4 K2 over every liability section | v0.4 approval |
| R4 scope end when there is no "total liabilities" row | **Superseded by V1** (strict fallback) | — | — |
| R2 undated-candidate clarification (rev 7) | **Superseded by V3** | — | — |
| V1–V4 | **Proposed by owner (rev 8); awaiting confirmation** | V1 strict scope fallback; V2 exact matching of headings and subtotals, duplicates → `requires_review`, applied to FR-005.10; V3 only qualified candidates block, acceptance needs a dated passing candidate; V4 conflict only from candidates passing conditions 1–6 | v0.4 approval |
| Equity-heading list | **Proposed by owner (rev 8); awaiting confirmation** | Initial "equity", "stockholders' equity", "shareholders' equity"; combined totals "total equity and liabilities", "total liabilities and stockholders' equity" | v0.4 approval |
| Page break after the last liability subtotal | **Recommendation from Claude (unresolved ambiguity, conservative default); awaiting confirmation** | "Directly followed" is judged on the same page only; a subtotal that ends its page → `requires_review` | v0.4 approval |
| Qualified candidate about another entity or basis (`statement_scope = other`) | **Proposed by owner (rev 9); awaiting confirmation: non-blocking** (supersedes the rev-8 default) | Rejected alternative: the rev-8 default, under which every qualified candidate blocks whatever its entity or basis | v0.4 approval |
| U1: which condition-6 failure blocks | **Proposed by owner (rev 10); awaiting confirmation** | Only an explicit L4 qualifier (6a) blocks; a stray figure (6b) fails only its own candidate | v0.4 approval |
| U2: entity or basis cannot be established (`statement_scope = undetermined`) | **Proposed by owner (rev 10); awaiting confirmation** | Blocks Z′ acceptance (dated period, or every period if undated or other-dated), qualified or not (A1 confirmed as the owner's choice in rev 11); `requires_review` (`statement_scope_undetermined`, rev 11) when no total and no borrowing row; never `conflicting` | v0.4 approval |
| A2: when `statement_scope = other` | **Proposed by owner (rev 11); awaiting confirmation** | Only when the L3 subject maps to another entity or to a basis different from the run's; all other non-`target` candidates are `undetermined` | v0.4 approval |
| A3: `statement_scope_undetermined` | **Proposed by owner (rev 11); awaiting confirmation** | Distinct reason under R1; precedence 1, before `statement_zero_not_verified` | v0.4 approval |
| A4: page with unknown basis | **Proposed by owner (rev 11); awaiting confirmation** | Not sufficient basis evidence for condition 4 | v0.4 approval |
| Z′ with an asserted basis | **Proposed by owner (rev 12); awaiting confirmation** | Prohibited: an `--assert-basis` basis is never sufficient for condition 4, so the candidate is `undetermined` | v0.4 approval |
| D2: candidate evidence record | **Proposed by owner (rev 12); awaiting confirmation** | `derivation.statement_candidates` on every period's `total_borrowings`, with all record contents listed in §3.5.2 | v0.4 approval |
| Candidate records under a reported total | **Proposed by owner (rev 13); awaiting confirmation** | Reported total authoritative; every candidate and its outcomes kept; periods marked `not_consulted`, never `blocked` or `accepted`; only exception is the unchanged 5.9 contradiction (`conflict`, AC-D-24) | v0.4 approval |
| OD-10 footnote matching | **Proposed by owner (rev 12); awaiting confirmation** | Case-insensitive exact normalised phrase occurrence within one extracted line; no fuzzy, plural or cross-line matching | v0.4 approval |
| Other candidates | **Proposed by owner (rev 10); awaiting confirmation** | Every candidate meeting neither B1 nor B2 is recorded only and never blocks | v0.4 approval |
| Generic markers list | **Recommendation from Claude; awaiting confirmation** | Initial "other", "miscellaneous", "sundry" | v0.4 approval |
| OPEN-2 | **Proposed by owner (rev 5); awaiting confirmation** | M1 / K2 on both E1 and E2; not when a reported total is used | v0.4 approval |
| OPEN-4 | **Proposed by owner (rev 5); awaiting confirmation** | `not_presented` only with E2 and 5.4; otherwise `requires_review` | v0.4 approval |
| OD-9, Q-Z1 (S1), OPEN-3 | **Proposed by owner (rev 5); awaiting confirmation** | Z / Z′ / A / U; Z′ deterministic rules, **disabled until L1 to L4 are approved** | v0.4 approval (rules) |
| Q-Z6 + OPEN-5 | **Proposed by owner (rev 5); awaiting confirmation** | J.1 relative-change rule for RI-003 C2 and RI-004 C1 | v0.4 approval |
| Section phrases (5.2), markers (5.5 c) | Recommendation from Claude (initial values observed in tuning); awaiting confirmation | Headings, section subtotals, "total" / "net" / leading "less" | v0.4 approval |
| **OPEN-1 list** | **OPEN** | Specific non-debt allowlist content (G1). Generic rows are excluded by policy. Tuning candidates, **not approved**: "trade payables", "accounts payable", "provisions", "income tax liabilities (net)", "deferred tax liabilities (net)", "accrued compensation", "short-term income taxes", "long-term income taxes", "short-term unearned revenue", "long-term unearned revenue", "deferred income taxes". Until approved: aggregation always `requires_review`. | **Before Phase 3** |
| **L1–L4** | **OPEN** | L1 notes headings; L2 no-borrowings phrases; L3 subject phrases **and their subject → scope mapping** (standalone, consolidated, or another entity; rev 10); L4 qualifiers. Until all four are approved: Z′ disabled. | **Before Phase 3** (otherwise Release 1 ships with Z′ disabled) |
| D-14b (D-01b) | **Open** | Conditions C1–C7 (§4) | After Phase 2 and the held-out evaluation |
| OD-3, OD-6, OD-7, OD-8, OQ-6 | Open (unchanged) | As in v0.3; OD-8 must account for DEC-C | As in v0.3 |
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
| 5 | 2 | FR-005.7 (D-13), FR-005.9 (DEC-B), FR-004.3 parse check and grouping, FR-005.3 sequence and precedence (S1–S3), FR-005.10 amendments, H.1.3 (DEC-C), OD-10 rules, FR-005.11 in **disabled** mode (after D-13) | AC-D13, AC-B, AC-C, AC-OD10, AC-A, AC-V |
| 6 | 2 | D-14b C4 (tuning re-run) and C5 (held-out evaluation, once OQ-3 documents are labelled) | D-14b decided by the owner (C7) |
| 7 | 3 | H.5 rules 4–5 (row definition, K2/G1, M1, E1/E2, `not_presented`, source priority 5.9, Z/A/U, memo display 5.8). Z′ only if L1–L4 are approved; aggregation only if the OPEN-1 list is approved. Otherwise both stay in their safe fallback. | AC-D, AC-Z |
| 8 | 4 | J.1 relative-change rule (RI-003 C2, RI-004 C1) | AC-Q6 |

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
- **Section I** metrics, apart from the MET-04 zero-evidence clarification (§3.5.2). **Section J** rules, apart from the J.1 relative-change rule (RI-003 C2, RI-004 C1; §3.10). **Section K**, apart from memo sections 2 and 7 (blocked-aggregation display, 5.8), the header, and the limitations note on hidden debt (§3.5.1).
- **Decisions:** D-02 to D-11 and D-12 (amended only as in §3.5); "absent ≠ zero"; no total-liabilities substitution; D-07 lease exclusion.
- **Security, NFR and evaluation:** SEC-01 to SEC-12, NFR-01 to NFR-09, and the O.2 tuning/held-out rules.
- **Phase boundaries:** apart from the Phase 1 exit review contents in §6.

---

## 9. Consistency review (performed on revision 13)

**Revision 13 change (reported-total interaction only):**

| Check | Result |
|---|---|
| Reported total selected | Every candidate keeps its full record; each period whose reported total is selected gets `not_consulted` for every candidate, never `blocked` or `accepted`. The reported total stays authoritative. The role field is a classification only. The rev-12 sentence "empty … when a reported total is used" is replaced. |
| Contradiction | AC-D-24 is unchanged: a non-zero reported total plus a Z′ that would be accepted gives `conflicting`, and the accepting candidate is marked `conflict`. |
| Tests | AC-Z-54 revised; AC-Z-57 to AC-Z-59 new. Schema and register updated. |
| Unchanged | Footnote matching, wrapped footnotes, mixed-basis runs, record duplication, R1 and R2, V4, 5.9 source priority, the restored v0.3 missing-component rule, and all other decisions. |

**Revision 12 changes (review items only):**

| Check | Result |
|---|---|
| Asserted basis | Condition 4 states explicitly that Z′ is prohibited when the basis rests only on `--assert-basis`. AC-Z-46 wording corrected to match OD-10 b′ (the page is treated as the asserted basis with `basis_evidence = analyst_assertion`, not `unknown`); its expected outcome is unchanged. |
| D2 | New `derivation.statement_candidates` record, on every period's `total_borrowings`, with every candidate in a deterministic order. It never changes status or reason. AC-Z-53 (the AC-Z-50 case keeps both candidates and their outcomes), AC-Z-54, AC-Z-55 and AC-Z-56 new. Schema and register updated. |
| Footnote matching | OD-10 option c phrases use FR-013 rule 1 normalisation plus whitespace collapsing, with exact whole-word occurrence in one line. AC-OD10-6 to AC-OD10-8 new. |
| Register | `statement_zero_not_verified` entry now states that `statement_scope_undetermined` takes precedence when a B2 candidate applies. A4 entry no longer calls the assertion rule Claude's reading; it is now its own owner proposal. |
| Unchanged | R1 and R2 rules, A1–A4, B1, B2, U1, V4, the condition-7 rule, 5.9 source priority, the restored v0.3 missing-component rule, A5 (table order), and all other decisions. |

**Revision 11 changes (A1–A4 only):**

| Check | Result |
|---|---|
| A1 | B2 confirmed: an `undetermined` candidate blocks whether or not qualified, and never creates `conflicting` (V4 unchanged). AC-Z-52 new. |
| A2 | `other` only from L3 evidence (subject → another entity or other basis). No subject, insufficient page evidence, or page evidence contradicting the subject → `undetermined`. AC-Z-14 and AC-Z-34 now state the L3 subject; AC-Z-48 and AC-Z-49 new. |
| A3 | `statement_scope_undetermined` added: used only under R1; Z′ reason precedence: `statement_scope_undetermined`, then `statement_zero_not_verified`; outside FR-005.3. AC-Z-41 to AC-Z-43 now expect it; AC-Z-45, AC-Z-50 and AC-Z-51 cover the boundaries. Schema and register updated. |
| A4 | Condition 4 needs a matching notes-heading basis word or a run whose basis is established by title or footnote. Unknown basis and analyst assertion are insufficient. AC-Z-4 now names the heading's basis; AC-Z-46 and AC-Z-47 new. |
| Test default | AC-Z cases are `target` unless stated, so earlier tests keep their meaning. |
| Unchanged | A5 (table order), U1, B1, V4, the condition-7 rule, R1's scope (no reported total and no borrowing row), 5.9 source priority, the restored v0.3 missing-component rule, V1, V2, R3, R4, G1, and all other decisions. |

**Revision 10 changes (review findings only):**

| Check | Result |
|---|---|
| U1 | Condition 6 split into 6a (L4 qualifier, `statement_no_qualifier`) and 6b (other figures, `statement_no_other_figures`). Acceptance needs both, so nine keys for eight conditions. Only 6a can make a candidate blocking (B1). AC-Z-10 revised; AC-Z-39 and AC-Z-40 new. |
| U2 | New recorded attribute `statement_scope` (`target` / `other` / `undetermined`). An `undetermined` candidate blocks (B2) like an undated or dated qualified one, but never creates `conflicting` (V4 unchanged: it fails condition 3 or 4). L3 now maps subjects to a scope, including "another entity". AC-Z-41 to AC-Z-45 new; the `other` scope is made explicit in AC-Z-6, 7, 14, 20, 32 to 34, 36 and 37. |
| Non-blocking | Every candidate meeting neither B1 nor B2 is recorded only. |
| Test AC-Z-19 | States that the qualified candidate matches the target entity and basis. |
| Register | Stale rev-8 wording in the qualified-candidate row corrected; U1, U2 and "other candidates" rows added. |
| Unchanged | V4, the condition-7 rule, R1 (`statement_zero_not_verified` only with no total and no borrowing row), 5.9 source priority, the restored v0.3 missing-component rule, V1, V2, R3, R4, G1, the parse rules, and all other decisions. |

**Revision 9 change (blocking rule only):**

| Check | Result |
|---|---|
| Qualified candidates | Block only when they pass conditions 3 and 4 (same entity and basis). They block the dated period, or every period if undated or other-dated. Qualified candidates about another entity or basis are recorded, never block, and never create a conflict, which is consistent with V4. AC-Z-28 and AC-Z-29 clarified; AC-Z-32 revised; AC-Z-36 to AC-Z-38 new. |
| Unchanged | The page-break fallback (`requires_review`, AC-D-33), V1, V2, V4, R1 to R4, G1, the parse rules, and all other decisions. |

**Revision 8 changes (V1–V4 only; still valid except the blocking default revised in rev 9):**

| Check | Result |
|---|---|
| V1 | The fallback end needs the next line on the same page to be an equity heading or combined total; otherwise `requires_review`. Long-term US rows can no longer fall outside the scope silently (AC-D-29 to AC-D-33). An undeterminable scope also fails Z′ condition 8 (AC-Z-35). |
| V2 | Headings and subtotals use exact normalised equality, with one trailing colon removed. Headings must be label-only lines. Duplicate "total liabilities" → `requires_review`. FR-005.10 uses the same rule (AC-D-34 to AC-D-38). |
| V3 | Only qualified candidates block (matching period, or every period if undated or other-dated). Acceptance needs a dated candidate passing all eight conditions. AC-Z-21 is revised; AC-Z-28 to AC-Z-32 are new. |
| V4 | Condition 7 creates `conflicting` only for candidates passing conditions 1–6 (AC-Z-11 clarified; AC-Z-33, AC-Z-34). |
| Unchanged | R1 scope, R3 conditions 7 and 8 (apart from V4 and the scope clause), G1, the parse rules, precedence, the row definition, source priority, the restored v0.3 missing-component rule, and the memo display. |

**Revision 7 changes (R1–R4 only; still valid except where superseded by V1–V4):**

| Check | Result |
|---|---|
| R1 | `statement_zero_not_verified` applies only with no reported total and no borrowing row for the period. It no longer overlaps `not_found` from the component rules (AC-Z-17) or a reported total (AC-Z-18). `conflicting` (condition 7) still takes precedence. |
| R2 | **Superseded by V3:** date-failing, unqualified candidates no longer block. (Rev 7 text: all candidates evaluated and recorded; acceptance needed one fully passing candidate and no date-failing or qualifier-failing candidate; date-failing candidates applied to every period.) |
| R3 | New condition 8 and key `statement_no_unresolved_rows`. Unresolved borrowing rows defer to the component rules; non-zero unclassified rows reject Z′. Source priority and conflict rules are unchanged (AC-Z-23 to AC-Z-27). |
| R4 | K2 and M1 cover every liability section from the first liability heading to the scope end; E2 still reconciles component sections (AC-D-25 to AC-D-28). |
| Unchanged | G1, the parse rules (`value_parsable`, `token_parsable`, `split_figure`, `value_unparsable`), precedence, the row definition, the restored v0.3 missing-component rule, the memo display, and all other decisions. |

**Revision 6 review (still valid):**

| Check | Result |
|---|---|
| D1 (two parse checks) | `value_parsable` (proposed value) and `token_parsable` (document token) are separate keys; both map to `value_unparsable` at precedence 3; `token_parsable` is `null` for a split and `true` for a nil token. AC-V-9 to AC-V-11, AC-V-15.<br><br>**Found and fixed during drafting:** the first rev-6 wording left `token_parsable` `null` for a nil token, which would have made a valid reported zero impossible to extract. |
| D2 (figure line) | One defined *figure line* per quote, used by 7.3, FR-005.10 and FR-005.11. Zero or several figure lines → `period_not_verified`. AC-V-12 to AC-V-14. |
| D3 (row) | A row is a line with a period-column token; label-only lines are never classified, summed or blocking. The (c) wrapped-label clause was removed as redundant: a truncated label cannot equal an allowlist phrase. AC-D-16, AC-D-17. |
| D4 (v0.3 rule 4) | Restored **unchanged** inside 5.9, with source priority reported total → Z′ → components. Cross-source contradictions → `conflicting`. AC-D-21 to AC-D-24. |
| D5 (Z′) | `extracted` only when all dedicated keys are `true` (seven in rev 6; eight from rev 7 with R3's condition 8); FR-005.1–.11 are not applied to Z′ fields; source-required exception limited to `statement_zero`; currency taken from the extracted `reporting_currency`. A failed candidate is `requires_review` only when no other source applies. AC-Z-4 to AC-Z-16. |
| G1 and memo | Generic markers make an allowlist entry invalid (`E-CONFIG-INVALID`, an existing code); blocked aggregation is displayed without any sum or D/E. AC-D-18 to AC-D-20. |
| Owner choices vs approved v0.3 | **No conflict found.**<br>• **v0.3 H.5 rules 2 and 4** are restored verbatim in effect.<br>• **The H.1 source-required exception** is narrowly scoped and explicitly listed.<br>• **D-07, H.4.7, D-08, MET-04, J.3, FR-003.1 and SEC-10** are unchanged. |
| Precedence and recording (rev 5) | Unchanged: only a failing check selects the reason; `null` never does (AC-V-8). |
| Open lists | OPEN-1 list and L1–L4 are marked OPEN, with safe fallbacks (AC-D-12, AC-Z-3). Tuning candidates are listed as **not approved**. |
| Decisions resolved implicitly | None. Two new items, `statement_zero_not_verified` and the generic-markers list, are labelled **recommendations awaiting confirmation**. v0.4 is not approved. |
| Evidence claims | No accuracy figure. R1 and R2 remain tuning documents. D-01b and Phase 1 are not claimed. |
| Residual risks (recorded) | Low D/E coverage under G1 (to be measured in C4 and C5). Debt hidden in generic rows is now always blocking rather than silently accepted. A plain four-digit value above the first figure line (rev 3). |
