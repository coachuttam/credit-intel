# OD-1 Proposal — Period-Column Mapping (FR-005.7)

> **Status pointer, 2026-10-19:** B-133 was closed 2026-10-18 and D-14a recorded the same day, so OD-1 may now be put forward for decision. Nothing else in this note is changed or approved.
>
> **Approval pointer, 2026-10-19 (later):** the owner approved the FR-005.7 text in §4.1. It is applied in PRD v0.4.14 and **OD-1 is decided**. §3 is the supporting detailed design. The items deferred in §0.3 stay open, and nothing is implemented.

| Item | Value |
|---|---|
| Status | **Design direction approved in principle on 2026-10-17, with the conditions in §0. OD-1 is NOT decided and stays open. Nothing is implemented, no PRD acceptance criterion is changed (this file's own §6 expected outcomes were corrected and remain proposed and unapproved), and `docs/PRD.md` FR-005.7 is not amended.** Updated 2026-10-17 to record the owner's decisions on Q1–Q8, and corrected the same day after a read-only consistency audit. **Provisional owner preferences (2026-10-17) are recorded in §0.1; none is formally approved.** **The algorithm in §3 is not approved and is not implementation-ready** (open items in §0). |
| Date | 2026-10-17 |
| Builds on | D-13 in `docs/PRD_v0.4_proposal.md` §3.1 (accepted in principle, never applied to the PRD). This file keeps D-13's core (boundary, row-label separation, numeric validation, uniqueness) and leaves out everything that depends on unapproved items: split-figure handling (DEC-A), new reason codes, and the figure-only-line merge (deferred, §0). |
| Not decided here | B-133, the D-01 acceptance outcome, D-14a, any waiver, OD-3, OD-8 to OD-10, Phase 1 completion. |
| Evidence | Synthetic fixtures (B-131, B-132) and the two-document probe summarised in `PROGRESS.md` (R1, R2: both tuning documents). Two documents show that failure modes occur, **not how often**. No accuracy figure is claimed. Every setting below is a provisional value to be checked on tuning documents only. I did not read `private/`. |

---

## 0. Owner decisions of 2026-10-17 and what is still open

**Approved design direction (not final, not implemented):**

| # | Decision |
|---|---|
| A-1 | Add `extract_words` to the PDF extractor interface, **subject to a compatibility review and tests**. Not implemented. The exact change is shown in §9. |
| A-2 | Wrapped-label lines: automatic joining stays **disabled** for OD-1; ambiguous or split rows must fail safely. |
| A-3 | Rotated pages are **unverifiable** and require review; no guessing. |
| A-4 | Figure-only-line merging is **deferred**; it is not part of OD-1. |

**Provisional assumptions (may change):**

| # | Assumption |
|---|---|
| P-1 | Unparsable tokens give `period_not_verified`. The reason-code policy is not final until the split-figure requirement (DEC-A) is separately decided. |
| P-2 | `column_margin_pt = 3` and `line_tolerance_pt = 3`, for this proposal and the synthetic tests only. **Not validated against a sufficient real-report sample; not optimised; not production-validated.** |
| P-3 | The date-adjacency test in 3.3 (words of a full date count as adjacent when each gap is no larger than the average character width of the words either side) is an **unvalidated provisional assumption**. It is separate from the deferred Q9 guard. No evidence supports its threshold, and it is not listed among the settings in 3.10. |

**Unresolved requirements and questions (recorded separately; not part of OD-1):**

| # | Item |
|---|---|
| U-1 | Reason-code policy for unparsable and split figures (DEC-A). |
| U-2 | Final reason code for an unparsable single token (depends on U-1). |
| U-3 | Grouping validity (the stricter rule in `docs/PRD_v0.4_proposal.md` §3.8): not decided, not in OD-1. |
| U-4 | Three-year statements (DEC-C): not decided, not in OD-1. Column structure here tolerates an extra period column, nothing more. |
| U-5 | Hazard H1 (§13.1) is a **known residual risk** of the approved direction. The Q9 label-contiguity guard is **deferred, not adopted and not approved**; it is not part of the proposed algorithm. Evidence gap in §13.6. |
| U-6 | Whether `extract_words` lines agree with `extract_text` lines on real reports: unmeasured. Partly measured on ten pages on 2026-10-19: see §14. |
| U-7 | The reason code for a field blocked by a non-`extracted` document-level attribute (H.1.2): unspecified. |
| U-8 | How FR-005.10 recognises a note reference when the page has no recognised "Note" header. G.0 treats a plain integer as a numeric token and FR-005.10 says a note reference counts as a figure, but neither says how a note reference is recognised. The PRD is unchanged; this stays an owner/PRD clarification (Q12). |
| U-9 | How FR-005.9 validates a year-only **comparative** header (it requires a full date on the page whose year equals the header's year). AC-OD1-4 and AC-OD1-5 fixtures therefore carry full dates; behaviour on real reports is unmeasured. **Owner decision 2026-10-19: option B (derive the comparative from the validated current period); see §0.2. Applied in PRD v0.4.13 (FR-005.9); resolved.** |
| U-10 | Attached currency symbols (`$1,234`, `₹1,234`) are not numeric tokens under G.0, so the position rule cannot assign them. FR-004.3 normalisation is **not** changed. Owner decision requested (Q10). |
| U-11 | Headerless continuation pages: the fail-safe rule in 3.9 is narrower than the current FR-005.7 text. Owner decision requested (Q11). |
| U-12 | **Multi-line quotes.** FR-005.10 defines the label as the text before the quoted row's first figure but does not say which line's text that is when a quote spans lines. A quote that includes a label-only line could reintroduce label joining, which A-2 disables. The PRD is unchanged; PRD clarification needed. No outcome is proposed here. |
| U-13 | **Narrow tokens.** A short figure or a nil dash right-aligned under a centred header may not overlap its ±3 pt region. It would then be a stray token and the line would fail safe (B fails), losing the row. No scenario or evidence covers this; it matters for the FR-004.3 nil convention. Untested assumption; evidence gap (§13.6-style real-report inspection needs separate authorisation). Partly measured on ten pages on 2026-10-19: see §14. |
| U-14 | **Reason code for the two cases in 3.3 (no usable anchor; claimed period with no column).** The proposal uses `period_not_verified`, which the current FR-005.7 wording supports ("if the column order cannot be determined, or the value is in a different column"). Whether the PRD intends a more specific reason for a period that is absent from the page is **unresolved** and needs PRD clarification. |
| U-15 | **Note-region margin (new, 2026-10-19).** A region of the "Note" header word ±3 pt missed two real note references (`2.3` and `2.21`, 7.3 pt and 4.9 pt outside it) on two of the ten inspected R1 pages (§14). Under 3.7 a stray token makes the whole line unverified, so those two rows would be lost. A wider margin, an alignment rule or another definition of the note region is needed; this is a design decision for the owner, related to U-8 and Q2. Not decided. **Owner decision 2026-10-19: option C (note span); see §0.2. Applied in §3.3, §3.6/3.7 and AC-OD1-1.** |

**Not changed by this update:** OD-1 is open and undecided; B-133 is open; D-01 is not marked met or not met (the pdfplumber / MIT choice is decided and not reopened); D-14a is unrecorded and unapproved; Phase 1 is incomplete; no checklist waiver is approved; no acceptance criterion outside this proposal is changed; the PRD is not amended beyond a factual status pointer. Several expected outcomes **inside this proposal's §6** were corrected on 2026-10-17 (AC-OD1-4 to 11, 13, 14, 16 to 18 and 21 to 23) to remove contradictions found by audits, and AC-OD1-6 was corrected again in a second pass; they remain proposed and unapproved. This is a proposal, not an approval: nothing here makes OD-1 ready for implementation.

---

### 0.1 Provisional owner preferences (recorded 2026-10-17; proposal only)

These five preferences are **provisional**. None is a formal approval. **Update 2026-10-19: the owner confirmed Q2, Q10, Q11, the separate `WordExtractor` form and the Q7/P-2 settings (still provisional) in §0.3; the algorithm in §3 is still not approved.** None changes `docs/PRD.md`, and none implements or tests anything. They are recorded so the design can be refined; the formal OD-1 decision is a separate step (Q8). The 3 pt margin and tolerance (P-2) remain unvalidated on real reports.

#### Q2: anchor extent
- **Question:** "Anchor extent. Is a column's region built from the period-carrying tokens only (the year or date words, as 3.3 assumes), or from the whole header phrase (for example "As at 31 March 2025")?"
- **Provisional preference:** period tokens only (`period_tokens`).
- **Status:** provisional preference; unapproved. 3.3 already uses period tokens only as its working assumption.
- **Consequences and limitations:** a region built from the period token alone is narrower than the header phrase, so a figure that overlaps no region is a stray token and the line fails safe (B fails), which can lose rows (U-13). The proposal describes this choice as the one that fits a layout where the header phrase and the year are far apart (the R2 pattern in 3.3); the underlying observation is private and not independently verified.
- **Not defined here (left unresolved on purpose):** what counts as a valid anchor beyond the list already in 3.3; how duplicate or ambiguous anchors are treated beyond what 3.3 and FR-005.9 already state; what happens with missing anchors or a claimed period with no matching column (U-14). No new definition is introduced by this preference.
- **Affected PRD sections:** FR-005.7 and FR-005.9 (no change now).
- **Dependencies and evidence:** U-9, U-13, U-14, P-2, P-3. Real-report header layouts need separately authorised inspection of `private/`.

#### Q10: attached currency symbols
- **Question:** "Should the numeric-token definition be extended so an attached currency symbol (`$1,234`) can be assigned?"
- **Provisional preference:** defer. OD-1 is not expanded now to support attached symbols.
- **Status:** provisional preference; unapproved.
- **Deferral is not a change to FR-004.3 or G.0.** FR-004.3 still normalises currency symbols, and G.0 still says a currency symbol is a separate word and not a numeric token. Both texts stay exactly as they are.
- **Consequences and limitations:** under 3.8 a token with an attached symbol is not a numeric token, so the position rule cannot assign it and the period is `requires_review`, `period_not_verified`. Such rows are lost to review. `PROGRESS.md` records `₹` as extracted in R1 but does not say whether it came as a separate word or attached to the digits.
- **Affected PRD sections:** none changed (FR-004.3, G.0 as they stand).
- **Dependencies and evidence:** U-10. How symbols are tokenised in real reports needs separately authorised inspection of `private/`.

#### Q11: headerless continuation pages
- **Question:** "Is the fail-safe rule for headerless continuation pages (3.9) acceptable, given it is narrower than the current FR-005.7 text?"
- **Provisional preference:** accept the fail-safe approach provisionally, subject to PRD reconciliation.
- **Status:** provisional preference; unapproved. The current FR-005.7 text stays in force.
- **The phrase "unless alignment can be independently verified" is undefined** until a verification method is specified. The proposal does not specify one and does not invent one here. **While no approved verification method exists, the proposed fail-safe behaviour is review:** every field on such a page is `requires_review`, `period_not_verified` (3.9). Matching page dimensions alone never establish alignment.
- **Conflict to reconcile:** FR-005.7 says the system uses the cited page "or, if that page has no column header and the locator selected it, the first page of the same statement run (FR-013 rule 6)". 3.9 does not reuse the first page's regions. If the rule is ever approved, that clause of FR-005.7 must change; this is not done here.
- **Consequences and limitations:** continuation pages that have no header of their own are lost to review. FR-005.8 scale and currency lookup on the first page of the run is unaffected.
- **Affected PRD sections:** FR-005.7 and FR-013 rule 6 (no change now).
- **Dependencies and evidence:** U-11, U-14. How often real reports have headerless continuation pages needs separately authorised inspection of `private/`.

#### Extraction interface: separate `WordExtractor`
- **Design choice:** how `extract_words` is added to the PDF extractor interface (Q1 approved the addition in principle; this concerns its form).
- **Provisional preference:** a separate `WordExtractor` protocol alongside `TextExtractor`, subject to compatibility review and tests.
- **Status:** the addition of `extract_words` is approved in principle (recorded earlier). The separate-protocol form is a provisional preference; unapproved. Nothing is implemented and no test exists.
- **Existing interface preserved:** `TextExtractor`, `PageText`, `ingest()`, `validate_pdf()` and the existing tests and fakes are unchanged under this form (§9, a paper review).
- **Consequences and limitations:** the PRD's wording describes one extraction interface (see below); adopting this form would need that wording updated at adoption.
- **Affected PRD sections:** the Appendix OD-1 row ("requires `TextExtractor` to return word positions"); the replaceability line in L.2.1 ("all PDF access goes through the `TextExtractor` interface"); possibly FR-002. No change now.
- **Compatibility questions, all unresolved:** coordinate origin and crop-box or media-box offsets; whether `rotation` represents rotated pages and rotated text; handling of duplicate, unsorted, empty and out-of-range page lists; which `extract_words` parameters are pinned and how they relate to `extract_text`; how the verifier obtains both extractors for the same PDF; determinism of word output; cost (SEC-12); and the fact that page width and height are carried but unused by any rule. No behaviour of pdfplumber is assumed.
- **Dependencies and evidence:** the compatibility review in §9; U-6. Real-report word and line agreement needs separately authorised inspection of `private/`.

#### Q8: timing of the OD-1 decision
- **Question:** "Timing of the OD-1 decision" (recorded in §8 as a requirement).
- **Provisional preference:** formal OD-1 consideration only after the B-133 review.
- **Status:** provisional preference; consistent with existing project gates. Those gates are the Appendix A.3 B-133 row ("OD-1 is not put forward for decision"), the final item of `docs/d01_public_report_checklist.md` §7, and Section Q (step 3 "B-133 recorded"; the Phase 2 entry "OD-1 decided").
- **Consequences and limitations:** the proposal can be analysed and refined before the review, but OD-1 cannot be put forward or decided until the owner's B-133 review is complete. Nothing in this file closes B-133.
- **Affected PRD sections:** none changed.
- **Dependencies and evidence:** the owner's B-133 review (outstanding), the D-01 outcome, D-14a and the other Phase 1 exit items.

**What §0.1 does not do:** it approves nothing, answers no open question (U-1 to U-14 are unchanged), changes no PRD text, implements nothing, claims no test result, and does not claim real-report validation of the 3 pt margin or tolerance.

### 0.2 Owner decisions of 2026-10-19: U-9 and U-15 (recorded; wording not yet applied)

- **U-9 (FR-005.9, year-only comparative header): option B chosen.** A year-only or financial-year header is valid as the comparative period when the current period is validated by a full date and the header's year (the later year, for `2024-25`) is exactly one year before the current year. Its period-end is the same month and day one year earlier (D-11). Both the raw header text and the derived ISO date are stored. **Status:** owner decision, **applied in PRD v0.4.13 (2026-10-19)**: FR-005.9 gains the derived-comparative bullet. The owner chose to fail safe on the 29 February case; the PRD wording extends this to a current period ending on 28 or 29 February, because H.1.1 counts the two as the same day and the comparative's own period-end then cannot be derived (the owner may narrow it). The fixtures for AC-OD1-4 and AC-OD1-5 are updated below.
- **U-15 (note region): option C chosen.** The note region becomes a **span** from the "Note" header word's left edge minus `column_margin_pt` to just before the first period region. A numeric token in the span is a note reference and never a value, and it does not fail condition B. With no "Note" header there is no span (U-8 is unchanged). **Status:** owner decision, **applied to §3.3, §3.6/§3.7 and AC-OD1-1 on 2026-10-19**. The algorithm in §3 remains unapproved.
- **What these decisions do not do:** they do not decide OD-1, do not approve the algorithm and change no PRD text.

### 0.3 Owner decisions of 2026-10-19: the remaining question-sheet rows (recorded)

The owner answered **yes to all** twelve positions below. These are owner decisions about the design; they are not an approval of the algorithm and they change no PRD text.

| # | Item | Decision recorded |
|---|---|---|
| 1 | Q2, anchor extent | Confirmed: a column region is built from the period tokens only |
| 2 | Q10, attached currency symbols | Confirmed: defer; an attached symbol is not assignable and fails safe. G.0 and FR-004.3 are unchanged |
| 3 | Q11, headerless continuation pages | Confirmed: every field on such a page is `requires_review`; the FR-005.7 clause about the first page of the run is to be changed at adoption |
| 4 | Interface form | Confirmed: a separate `WordExtractor` protocol; `TextExtractor` is unchanged (still subject to the compatibility review and tests) |
| 5 | Q7 / P-2, settings | Confirmed: `column_margin_pt` = 3 and `line_tolerance_pt` = 3, still provisional and not validated beyond two documents |
| 6 | U-8 / Q12, note reference without a "Note" header | Deferred: no rule now; with no "Note" header there is no note span |
| 7 | U-14 | `period_not_verified` for a page with no usable anchor and for a claimed period with no column |
| 8 | U-12, multi-line quotes | The row label is taken from the figure line only (no joining) |
| 9 | U-1 / U-2, split figures and the unparsable-token reason | Deferred and scheduled for Phase 2 (DEC-A); until then they fail safe |
| 10 | U-3 / U-4, grouping validity and three-year statements | Outside OD-1 and scheduled for Phase 2 |
| 11 | U-7, reason code for a field blocked by a non-`extracted` document-level attribute (H.1.2) | A separate decision, not part of OD-1 |
| 12 | H1 / Q9 | The residual risk is accepted as documented (not observed in 34 rows); the label-contiguity guard stays deferred |
| 13 | Formal OD-1 | The owner asked for the proposed FR-005.7 replacement text to be drafted for approval. It is saved as §4.1, **approved on 2026-10-19 and applied in PRD v0.4.14; OD-1 is decided** |

---

## 1. The proposed rule in six lines

1. Extract **word positions** for the cited page. Group them into lines by vertical position.
2. Each **period anchor** in the column-header block (a year, fiscal-year token, or adjacent full date, validated by FR-005.9) defines a **column region**: its horizontal extent ± `column_margin_pt`. A "Note" header defines a note region.
3. The **label limit** is the left edge of the leftmost region. Every word wholly left of it is **label text and can never be a value**, even if numeric (this is the Microsoft `7,434` case).
4. A word is the value of a period column **only if all four hold**: it overlaps that region and no other (B); it lies right of the label limit on a line whose label passes FR-005.10 (R); it is one numeric or nil token that parses (N); and it is the only token in that region on the line (U). Proximity, "nearest column" and text order never assign.
5. The column's **period comes from its anchor's validated period-end**, not from left-to-right position.
6. Anything that fails a condition is `requires_review` — never guessed, never shifted to another column.

---

## 2. Why this rule (evidence and limits)

| Observation | Source | Consequence for the design |
|---|---|---|
| Text-order matching fails when a cell is blank or a dash, or a figure sits off its row | B-132 (synthetic) | Option (a) of OD-1 is not enough on its own |
| Word positions placed every probed figure under the right header, including the cases that defeat text order | `PROGRESS.md` (B-133 summary) | Option (b) is promising — on two documents |
| A **nearest-column** rule assigned the label's `7,434` (x1 ≈ 105, far left of the figure columns) to 2025; the real values are `109,095` (2025) and `100,923` (2024). Owner-confirmed | `PROGRESS.md`, R2 p38 row 8 | Distance alone must never assign; a label limit and a containment test are needed |
| 4 of 34 rows were SPLIT (e.g. `88, 136`, `(4,901 )`) | `PROGRESS.md` | This design fails these safely (`requires_review`); making them usable is DEC-A, not proposed here |
| 0 of 34 rows were OFF-ROW | `PROGRESS.md` | Figure-only-line merging is **deferred** (owner decision, §0); ambiguous or split rows fail safely. Two documents do not show that OFF-ROW never occurs |

**Limits:** two tuning documents; geometry values in this file (margins, tolerances) are **provisional defaults, not validated against a sufficient real-report sample, not optimised and not production-validated**; whether `extract_words` lines agree with `extract_text` lines on real reports is **unmeasured** (see AC-OD1-25).

---

## 3. Detailed rule

### 3.1 Prerequisite: word positions (architecture change — needs approval)
- **Approved in principle (owner, 2026-10-17), subject to a compatibility review and tests; not implemented.** The exact interface change and its compatibility analysis are in §9. The word-position capability is added to the PDF extractor interface as `extract_words(path, page_numbers) -> list[PageWords]`. Each `PageWords` carries the page number, the page **width, height and rotation**, and its words `Word = {text, x0, x1, top, bottom}` in PDF points, top-left origin. Rotation is used by the rotation rule below and by 3.3. Width and height are carried at the owner's request, but **no rule in this proposal uses them now** (3.9 no longer compares page dimensions); they are reserved for a future cross-page decision. The proposed form is a separate `WordExtractor` protocol (§9); that form is a design proposal subject to compatibility review, not an approved decision. Only `pdfplumber_extractor.py` imports pdfplumber (D-01 replaceability is kept). No new dependency.
- Words are extracted **only for candidate pages** (FR-003.1), which limits cost (SEC-12).
- FR-002.1's `PageText` shape is unchanged; FR-013 and G.0 stay text-only (G.0: "no word positions").
- Determinism (FR-002.3) extends to words: same file and `uv.lock` give identical word lists.
- A page whose rotation is not 0 is **unverifiable and requires review (owner decision)**: every field cited on it is `requires_review` (`period_not_verified`); the design does not guess a rotated layout.

### 3.2 Lines
Sort words by `(cy, x0, text)` with `cy = (top + bottom) / 2`. Start a new line when a word's `cy` exceeds the previous word's `cy` by more than `line_tolerance_pt`. Within a line, order by `(x0, text)`. A word's text is NFKC-normalised. Figure-only lines are **never** merged with neighbouring lines (merging is deferred, §0).

### 3.3 Anchors, header block, columns
- **Header block:** the lines above the page's first figure line (a line holding a figure word, G.0) and below the last title line (G.0, evaluated on the line's text). Anchors outside it are ignored, so a date inside the statement title ("… as at March 31, 2025") is not a column.
- **Period anchor:** the words that carry a period in an FR-005.9 accepted form: a four-digit year; a financial-year token (`2024-25`, `FY2025`); or a full date whose words are adjacent (each gap ≤ the average character width of the words either side; this adjacency test is an **unvalidated provisional assumption (P-3)**, separate from the deferred Q9 guard, and no evidence supports its threshold). If the day-month part is separate from the year (R2: "Year Ended June 30," at the left, `2025` far right), the **year token alone** is the anchor.
- **Region:** `[anchor.x0 − column_margin_pt, anchor.x1 + column_margin_pt]`. A header word "Note" or "Notes" defines the **note span** (owner decision, 2026-10-19, U-15 option C): from its left edge minus `column_margin_pt` to the left edge of the first period region (exclusive), so the note span and the period regions never overlap. A numeric token inside the note span is a note reference and never a value. With no such header word there is no note span.
- **Period of a column:** the period-end that FR-005.9 validates for that anchor. Column order on the page plays no role (a comparative-first layout works).
- **Structure is valid (S) only if all hold:** no two regions overlap; each validated period-end has exactly one column (stacked header anchors with overlapping extent and the same validated period count as one); every anchor has a validated period-end; the page rotation is 0. Otherwise every field on the page is `requires_review` (`period_not_verified`). For the fields of an unvalidated period the reason is `period_mismatch`, because FR-005.3 orders it before `period_not_verified`; other fields on the page get `period_not_verified`.
- Extra period columns (for example a third year) are structurally valid and simply unused; **three-year statements are kept out of OD-1** (owner decision) and recorded as an unresolved requirement (§0, U-4).
- **No usable anchor (proposed fail-safe).** A *usable anchor* is a period anchor whose period-end FR-005.9 validates and that lies in the header block. If a page has **no usable anchor**, no column regions exist and **no label limit is computed** (it is never taken from an empty set). Every field cited on that page is `requires_review`, `period_not_verified`. This applies whatever the reason the page was selected (a page-range override, a titled page whose header sits elsewhere, a continuation page). Anchors that exist but are not validated keep their FR-005.9 outcome (`period_mismatch`) for the fields of that period. Reason code: see U-14.
- **Claimed period with no column (proposed fail-safe).** If a field claims a period whose validated period-end matches no column on the page (for example a one-column page, or a third year present while an earlier year is claimed), the field is `requires_review`, `period_not_verified`. No value is assigned, no column is invented, and alignment is never inferred from page dimensions or from the position of other columns. If nothing was proposed for that period the outcome is `not_found` (FR-004.3). Reason code: see U-14.

### 3.4 Label limit and label text
- **Label limit** = the smallest left edge among all regions (period and note).
- Words with `x1 ≤ label limit` are **label words**. Label words are never values.
- **Two different things, not one definition.** (1) *Value eligibility* (this proposal): words with `x1 ≤ label limit` can never be values. (2) *The row label* (FR-005.10, **unchanged**): the quoted row's label is the text before its first figure, where a note reference counts as a figure, and it is checked against the configured phrases. The position rule never redefines the FR-005.10 label. Where the two interact: a number inside a row label is a figure, so it ends the FR-005.10 label (the text before it is checked, and usually fails to equal a configured phrase, which is safe); the same number, if wholly left of the label limit, can never be a value.
- **Unresolved (U-8):** how a note reference is recognised when no "Note" header gives a note region. With a "Note" header the note region identifies it. Without one the PRD does not say; the proposal does not guess. The fixtures for AC-OD1-1 and Appendix B.6 row 11 include a "Note" header.
- **Wrapped labels (owner decision: automatic joining stays disabled for OD-1):** only the figure line's own label words are used. Label-only lines above it are not joined, so a row whose recognisable label sits on an earlier line fails FR-005.10 (`label_not_recognised`). Ambiguous or split rows must fail safely. This is safe but loses such rows.

### 3.5 Linking the evidence quote to one line
FR-005.1 verifies the quote on the page text. To find the figure line:
1. Normalise as in FR-005.1 (NFKC, whitespace runs to one space; no case folding).
2. The quote's **value line** is the quote line holding the proposed raw value. If it appears on more than one quote line, the quote is ambiguous → fail.
3. The **figure line** is the word-line whose normalised text contains the value line. Exactly one such line must exist on the page. None, or several (for example two identical rows in side-by-side statements) → fail.
4. Failure here is `requires_review` (`period_not_verified`).

### 3.6 Assignment conditions
On the figure line, a word *w* is the value of period column *C* only if **all** hold:

| Cond. | Requirement |
|---|---|
| **B** boundary | *w* overlaps *C*'s region and **no other** region |
| **R** row label | *w* lies right of the label limit, and the line's label passes FR-005.10 for the field |
| **N** number | *w* is a nil token, or a numeric token (G.0) that parses under FR-004.3 |
| **U** uniqueness | *C*'s region on this line holds exactly one numeric or nil token and no other non-label word, except a currency symbol that is its own word |
| **S** structure | the page structure is valid (3.3) |

Then the proposed value must equal the token's value (digits and decimals; enclosing brackets or a minus are ignored here, because the sign is FR-005.6's check). The assigned token is **the occurrence** that FR-005.6 inspects for its sign.

### 3.7 Outcomes (reason codes are existing ones only)

| Situation | Outcome |
|---|---|
| Structure invalid (S), rotation ≠ 0, quote cannot be linked to one line | every affected field `requires_review`, `period_not_verified` |
| No usable anchor on the page (3.3) | every field on the page `requires_review`, `period_not_verified`; no label limit computed (U-14) |
| Claimed period has no column on the page (3.3) | that field `requires_review`, `period_not_verified`; `not_found` if nothing was proposed (U-14) |
| B fails: token overlaps two regions, or lies right of the label limit overlapping no region and outside the note span (stray numeric or nil token between or beyond the period regions) | the **line** is unverified: all its fields `requires_review`, `period_not_verified` |
| U fails: two or more numeric or nil tokens in a region, or another non-label word in it (includes a label word that reaches a period region, a detached minus, a `(4,901` + `)` split) | that period `requires_review`, `period_not_verified` |
| N fails: the single token does not parse (for example decimal-comma `1.234,56`, which is not a numeric token) | `requires_review`, `period_not_verified` — **provisional**; the reason-code policy is not final until the split-figure requirement is separately decided (§0, U-2) |
| R fails | `requires_review`, `label_not_recognised` |
| Proposed value differs from the assigned token (Example 1: the comparative figure returned for the current period) | `requires_review`, `period_not_verified` |
| Blank cell: region holds no token, and nothing was proposed | `not_found` for that period; the other period is unaffected |
| Blank cell, but a value was proposed | `requires_review`, `period_not_verified` |
| Token in the note span | a note reference; never a value; not a stray token, so it does not make the line unverified |
| All conditions pass | the period-column check (FR-005.3 item 7) passes |

When several checks fail, FR-005.3's existing order picks the reason. Every condition's result is recorded in `validation` together with the column, the anchor quote and the token and anchor boxes.

### 3.8 Number forms
- **Negative:** `(245.10)` and an attached `−`, `–` or `-` are one token each and assign normally; the sign then follows FR-005.6. A **detached** minus is its own word and makes U fail (safe).
- **Nil:** a word that is exactly `-`, `–`, `—` or `nil` in a period region, alone, is a nil token (FR-004.3: `reported_nil`, subject to the period and label checks). A dash in the note region or the label is never a value.
- **Grouping:** Indian (`1,23,456.70`) and Western (`1,234,567.89`) tokens are both numeric tokens. Whether a malformed grouping parses is FR-004.3's rule; **grouping validity is kept out of OD-1** (owner decision) and recorded as an unresolved requirement (§0, U-3).
- **Currency:** `₹` or `$` as a separate word next to a figure is allowed in U. A symbol attached to the digits (`$1,234`) is not a numeric token (G.0), so the position rule cannot assign it and the period is `requires_review`, `period_not_verified`. This is a **documented OD-1 limitation**, not a change to FR-004.3, which still normalises currency symbols wherever it applies. Whether to extend the numeric-token definition for position assignment is an owner decision (Q10; U-10).

### 3.9 Continuation pages (proposed fail-safe rule; Q11)
A page with no header block that FR-013 selected as a continuation (rule 3b) has no column regions of its own. **Equal page width and height do not establish that its columns line up with the first page's**, so this proposal does not reuse the first page's regions: every field cited on such a page is `requires_review` with `period_not_verified`. A continuation page that has its own valid header block (3.3) is evaluated like any other page. The same fail-safe covers any page with no usable anchor (3.3). Cross-page column alignment (verifying that a continuation page's figures align before reusing regions) is not proposed and not implemented; it would need its own decision.

This is narrower than the **current** FR-005.7 text, which lets a headerless continuation page use the first page of its statement run (FR-013 rule 6). The current PRD text stays in force until the owner decides (Q11; U-11). FR-005.8 scale and currency lookup on the first page of the run is unaffected.

### 3.10 Provisional settings (tuning set only)
`column_margin_pt = 3`; `line_tolerance_pt = 3` (the value pdfplumber's text extraction also uses; this proposal groups lines by word centre, so its lines can still differ from `extract_text` lines, which AC-OD1-25 checks on synthetic PDFs only). **Retained as provisional defaults for this proposal and the synthetic tests only (owner decision). They are not validated against a sufficient real-report sample, not optimised, and not production-validated.**

---

## 4. Proposed FR-005.7 text (not applied)

> **7. Period column (OD-1) — draft, not applied, incomplete until the §0 open items are resolved.** Period columns are located from word positions and page metadata (width, height, rotation) as follows: each period anchor in the column-header block defines a column region, and the column's period is the period-end validated for that anchor under criterion 9. A numeric or nil token is the value of a period column only if its horizontal extent overlaps that column's region and no other, it lies right of the label limit on a line whose row label passes criterion 10 (unchanged), it parses under FR-004.3, and it is the only such token in that region on that line. Words wholly left of the label limit are never values. Words in the note region are note references. Distance, "nearest column" and text order never establish an assignment. Label-only lines are not joined to a figure line. A page with a non-zero rotation, an invalid column structure, or no header block of its own (a continuation page) is unverifiable, and its fields are `requires_review`. If any condition fails the reason is `period_not_verified`, except that a failing row-label check gives `label_not_recognised` and an unvalidated period gives `period_mismatch`, in the order of criterion 3. A page with no usable anchor, or a claimed period with no column on the page, is `requires_review` (reason code unresolved, U-14). A blank cell with nothing proposed is `not_found`. The method is deterministic and is tested on fixtures that include a note-reference column (Appendix B, Example 1).

### 4.1 Updated draft after the 2026-10-19 decisions (approved 2026-10-19; applied in PRD v0.4.14)

This draft supersedes the text above. It builds in the owner's decisions of 2026-10-19 (§0.2, §0.3): the note span (U-15), the derived comparative in FR-005.9 (U-9, already in PRD v0.4.13), the figure-line-only row label, the headerless-continuation fail-safe and the separate `WordExtractor`. **The owner approved this text on 2026-10-19 and it is applied as FR-005.7 in PRD v0.4.14. OD-1 is decided. Nothing is implemented.**

> **7. Period column (OD-1).** Period columns are located from word positions and page rotation. Each period anchor in the column-header block, a year, financial-year token or full date whose period-end is validated under criterion 9, defines a column region: its horizontal extent ± `column_margin_pt`. A header word "Note" or "Notes" defines the note span, from its left edge − `column_margin_pt` to the left edge of the first period region. The label limit is the leftmost left edge among the note span and the period regions. A word is the value of a period column only if (B) its horizontal extent overlaps that column's region and no other; (R) it lies right of the label limit on a line whose row label passes criterion 10 (unchanged); (N) it is a numeric or nil token that parses under FR-004.3; and (U) it is the only numeric or nil token in that region on that line, any other word there being only a separate currency symbol. Words wholly left of the label limit are never values, and a numeric token in the note span is a note reference, never a value. Distance, "nearest column" and text order never establish an assignment. Label-only lines are not joined to a figure line, and the row label is taken from the figure line only. A page with a non-zero rotation, an invalid column structure (overlapping regions, two columns for one validated period-end, an anchor with no validated period-end), no usable anchor, or no header block of its own (a headerless continuation page) is unverifiable, and its fields are `requires_review`. If a condition fails, the reason is `period_not_verified`, except that a failing row-label check gives `label_not_recognised` and an unvalidated period gives `period_mismatch`, in the order of criterion 3. A claimed period with no column on the page is `requires_review` (`period_not_verified`), or `not_found` if nothing was proposed. A blank cell with nothing proposed is `not_found`. An attached currency symbol, a split figure or a detached minus makes the token not assignable, and the period is `requires_review` (`period_not_verified`). `column_margin_pt` is initially 3 pt (provisional, tuned only on tuning-set documents). The method is deterministic, reads words through a separate `WordExtractor` interface, and is tested on fixtures that include a note-reference column (Appendix B, Example 1).

**What the approval changed in the PRD (applied in v0.4.14):**
- FR-005.7 replaced, with its clause about the first page of the statement run removed.
- FR-002 and L.2.1: the word-position output and the `WordExtractor` interface (the replaceability line currently names only `TextExtractor`).
- Appendix A.3 and the OD-1 row: OD-1 marked decided. Section Q: the Phase 2 gate "OD-1 decided" becomes satisfied.
- A new acceptance-criteria table for FR-005.7 (the AC-OD1 cases), a settings entry for the 3 pt margin, and an updated Example 1.
- The deferred items (U-1 to U-4, U-7, U-8) listed as open requirements.

---

## 5. How this interacts with the PRD

| Area | Effect |
|---|---|
| FR-005.7, OD-1 | Replaced and resolved — **only after owner approval** |
| FR-005.1, .3, .8, .9, FR-004.3 | Unchanged. FR-005.6's "occurrence used for criterion 7" becomes the assigned token |
| FR-005.10 | **Unchanged.** The row label stays the text before the first figure (3.4). The position rule only decides which words may be values; it does not redefine the label. Open: how a note reference is recognised without a "Note" header (U-8) |
| FR-002 | Adds a separate word output; `PageText` and FR-002.1 unchanged; FR-002.3 determinism test extended |
| FR-013, G.0, H.4.6 (Stage A) | Unchanged; they remain text-only |
| L.1 to L.3, D-01 | a separate `WordExtractor` Protocol is added (§9); `TextExtractor` is unchanged; pdfplumber stays behind the interfaces; no new dependency |
| Appendix B Example 1, B.6 rows 11 and 12 | Same outcomes **provided the fixture has a recognised "Note" header** (row 11's note reference `14`); without one the outcome depends on U-8. Only the mechanism wording changes at adoption |
| Hazard H1 | **Known residual risk** (§13.1): a label number overlapping a period region could be misassigned if the proposed value supplied for that period is that label number. Not observed in the 34 reviewed rows. Open (U-5) |
| Section Q | Phase 2 entry "OD-1 decided" is satisfied by approval; the Phase 1 exit is unaffected, and **OD-1 should be put forward only after the owner's B-133 review** (`docs/d01_public_report_checklist.md`) |
| Release scope | No change: option (b) is already listed in OD-1; no OCR, no table APIs, no new feature |
| Not included | Split-figure reconstruction and its reason codes (DEC-A), three-year statements (DEC-C), the grouping-validity rule (proposal §3.8), wrapped-label joining |

**Expected effect on the tuning documents (design expectation, not a result):**
- **End to end:** the R2 `7,434` row is a wrapped label that is not a configured field. Its row label (FR-005.10) is not a configured phrase, so the complete pipeline is expected to give `requires_review`, `label_not_recognised` and to accept **no value**. The complete pipeline is not expected to assign `109,095` or `100,923`.
- **Isolated assignment experiment (not an acceptance outcome):** with label validation supplied as passing, the assignment step alone would not return the label's `7,434` words as values and would find `109,095` under 2025 and `100,923` under 2024. This shows what the label limit does; it does not say the field is accepted.
- The 4 SPLIT rows are expected to fail safe (`requires_review`) rather than be assigned.

These are targets for implementation tests, not measurements.

---

## 6. Acceptance criteria and regression tests (all synthetic; generated at test time)

Unit tests take `Word` lists directly; integration tests build PDFs with reportlab and call `extract_words`. New behaviour IDs would be added to `tests/BEHAVIOURS.md` when approved and implemented.

| AC | Case | Expected |
|---|---|---|
| AC-OD1-1 | Aligned two period columns, with and without a note column; note reference `14` in the note region | Each value in its column; `14` never a value. Variant (U-15): note references 5 to 8 pt right of the "Note" header word still lie in the note span, are note references and do not make the line unverified |
| AC-OD1-2 | Comparative-first layout (2024 left, 2025 right) | Mapping by validated period, not by order |
| AC-OD1-3 | Header centred over wider right-aligned figures | Correct assignment by overlap |
| AC-OD1-4 | Two-line header: "As at March 31," over `2025  2024`; the fixture carries a full date for the current year only; under PRD v0.4.13 the comparative year is derived from the validated current period (U-9, resolved) | Anchors are the years; correct assignment. Without such full dates the unvalidated period keeps its FR-005.9 outcome (`period_mismatch`) |
| AC-OD1-5 | "Year Ended June 30," far left, `2025` far right (R2 pattern); a full date for the current year present (FR-005.9, v0.4.13) | The year token alone is the anchor; correct assignment |
| AC-OD1-6 | **Microsoft LABEL-WRAP pattern, synthetic fixture.** *Recorded* (`PROGRESS.md`, owner-confirmed): the full label reads "Common stock and paid-in capital – shares authorized 24,000; outstanding 7,434 and 7,434"; the label's `7,434` sits at x1 ≈ 105, far left of the figure columns; the values are `109,095` (2025) and `100,923` (2024). *Not recorded:* how the label wraps across lines and which text sits on the figure line. *Inferred for the fixture only:* the figure line carries a label fragment that ends with the label's numbers (for example `outstanding 7,434 and 7,434`), then `109,095` and `100,923`. **(a) End to end:** the FR-005.10 label of the figure line (text before its first figure) is a fragment that is not a configured phrase → `requires_review`, `label_not_recognised` (first failing check, FR-005.3 order), for any configured field proposed. No value is accepted, including when `7,434` is the proposed value for 2025. The result depends on the fragment not being a configured phrase, which holds for the inferred fragment and is not recorded for the real page. **(b) Component level only:** with the label check supplied as passing in a unit test, the assignment step does not return the `7,434` label words as values and finds `109,095` under 2025 and `100,923` under 2024. This tests the label limit only; it is not an end-to-end acceptance outcome and does not mean the field is accepted |
| AC-OD1-7 | Label-only line above the figure line holding (i) a plain integer, or (ii) a figure word such as `24,000` wholly left of the label limit | Lines are not joined (A-2). (i) is not a figure line (G.0). (ii) is a figure line by G.0, but none of its words is in a period region, so it supplies no value. The figure line below is evaluated on its own row label (FR-005.10) |
| AC-OD1-8 | A label word long enough to overlap a period region | `requires_review`, `period_not_verified` (U fails) |
| AC-OD1-9 | Token overlapping two regions; numeric token in a gutter or right of the last region | `requires_review`, `period_not_verified`; the line is unverified |
| AC-OD1-10 | Sub-cases: (a) overlapping regions; (b) two columns for one validated period-end; (c) an anchor with no validated period; (d) rotated page | (a), (b), (d): whole page `requires_review`, `period_not_verified`. (c): fields of the unvalidated period `period_mismatch` (FR-005.3 orders it first); other fields on the page `period_not_verified` |
| AC-OD1-11 | Blank cell, with and without a proposal | Nothing proposed: `not_found` (FR-004.3). A value proposed: `requires_review`, `period_not_verified`. The other period is unchanged and not shifted |
| AC-OD1-12 | Nil dash in a region; dash in the note region; dash inside a label | `reported_nil`; ignored; ignored |
| AC-OD1-13 | `(245.10)` with the proposal `245.10`; attached `−1,234` and `–1,234` with a negative proposal, and with a positive proposal | Column check passes in every case. Sign check (FR-005.6): `245.10` against the bracketed token → `sign_mismatch` (Appendix B, Example 2); a negative proposal for an attached minus passes; a positive proposal for an attached minus → `sign_mismatch` |
| AC-OD1-14 | Detached minus `-` `1,234` | U fails → `requires_review`, `period_not_verified` |
| AC-OD1-15 | `1,23,456.70` and `1,234,567.89` in different columns of one line | Both assigned and parsed |
| AC-OD1-16 | Decimal comma `1.234,56` in a region | Not a numeric token (G.0) → `requires_review`, `period_not_verified` (provisional, P-1) |
| AC-OD1-17 | Split `(4,901` + `)` in one region (R2 SPLIT pattern; G.0 counts a lone `)` as a numeric token) | Two tokens → U fails → `requires_review`, `period_not_verified`; no joined value (provisional, U-1) |
| AC-OD1-18 | `$1,234` attached; `$` as a separate word | Attached: not a numeric token (G.0), so the position rule cannot assign it → `requires_review`, `period_not_verified`; a documented limitation (Q10); FR-004.3 normalisation unchanged. Separate: allowed |
| AC-OD1-19 | Quote linkage: raw value on two quote lines; two identical rows on the page; no matching word-line | Each → `requires_review` (`period_not_verified`) |
| AC-OD1-20 | Label failing FR-005.10 with a correctly placed figure | `requires_review` (`label_not_recognised`); no assignment |
| AC-OD1-21 | Headerless continuation page (FR-013 rule 3b): (a) same size as the first page, columns aligned; (b) same size, columns shifted by one column width; (c) different size; (d) first-page structure invalid; (e) a continuation page that has its own valid header block | (a) to (d): every field on the page `requires_review`, `period_not_verified`; same page size never establishes alignment (3.9). (e): evaluated like any page with a header |
| AC-OD1-22 | Side-by-side statements (four anchors, two period-ends) | Whole page `requires_review`, `period_not_verified` |
| AC-OD1-23 | Third period column present | Assignments for the periods the field claims are unchanged. Which periods Release 1 may claim stays unresolved (U-4) |
| AC-OD1-24 | Determinism: shuffled word order, repeated runs, a fresh process; golden `extract_words` output (as B-120) | Identical results |
| AC-OD1-25 | On every synthetic PDF used above, the word-line text of each tested row equals the `extract_text` line | Equal (guards assumption 3.5; says nothing about real reports) |
| AC-OD1-26 | Property tests with a fixed seed: shifting all x by a constant changes nothing; no token wholly left of the label limit is ever returned as a value | Hold |

Existing tests (B-131, B-132, B-120 and all locator tests) must pass unchanged.

**Notes on the table (not acceptance criteria):**
- AC-OD1-22 duplicates the outcome of AC-OD1-10(b) (two columns for one validated period-end); it differs only in fixture.
- **Non-normative characterisation (formerly AC-OD1-6(c)):** a test-only nearest-column helper on the AC-OD1-6 fixture would return the label's `7,434` for 2025. It documents why the label limit exists. It is a known-limitation characterisation (like B-132), **not a product requirement** and not an acceptance outcome.

**Proposed gap scenarios (unnumbered; not acceptance criteria; not approved):**

| ID | Case | Expected |
|---|---|---|
| ZA-1 | Page with no usable anchor (no header words, or only unvalidated ones), including a page selected by page-range override | Every field `requires_review`, `period_not_verified`; no label limit computed (U-14) |
| NC-1 | Field claims a period whose column is absent (one-column page; third year present, earlier year claimed) | That field `requires_review`, `period_not_verified`; `not_found` if nothing was proposed; no assignment, no invented column (U-14) |
| NT-1 | Short figure or nil dash right-aligned under a centred header so it overlaps no region | Documents the current expected result (stray token, line unverified, `period_not_verified`); a known loss of rows, not a requirement (U-13) |
| MQ-1 | Quote spanning a label-only line and the figure line | **No outcome proposed:** unresolved PRD semantics (U-12) |
| NH-1 | Note reference with no "Note" header | **No outcome proposed:** unresolved PRD semantics (U-8, Q12) |

---

## 7. Options considered

| Option | Verdict |
|---|---|
| (a) Order of numbers in the quoted row vs header order | Rejected as the only method: fails on blank cells and off-row figures (B-132) |
| Nearest column, with or without a maximum distance | Rejected: assigns by proximity; the R2 `7,434` failure shows why. A distance cap still guesses. (`PROGRESS.md` says a position-based method "would need a maximum-distance rule"; this proposal uses a label limit and containment instead, and the difference is noted for the owner) |
| (b) Word positions with containment and uniqueness (this proposal) | Proposed |
| pdfplumber table-extraction APIs | Not evaluated; no evidence in the project supports them |

---

## 8. Owner decisions and open questions (2026-10-17)

| # | Question | Status |
|---|---|---|
| Q1 | Add `extract_words` to the extractor interface? | **Approved in principle**, subject to compatibility review and tests; not implemented (§9). The separate-protocol form is a **provisional owner preference** (§0.1) and the page-metadata fields are proposals; neither is approved |
| **Q2** | **Anchor extent.** Is a column's region built from the period-carrying tokens only (the year or date words, as 3.3 assumes), or from the whole header phrase (for example "As at 31 March 2025")? | **Provisional owner preference: period tokens only (§0.1); not approved.** 3.3 uses "period tokens only" as a working assumption; nothing depends on it being right until the owner answers. It changes where regions start and end, so it changes which tokens overlap them |
| Q3 | Join label-only lines above a figure line? | **No**; joining disabled for OD-1 |
| Q4 | Reason code for an unparsable token | **Provisional** `period_not_verified`; final policy waits for the split-figure decision |
| Q5 | Rotated pages | **Unverifiable; require review** |
| Q6 | Figure-only-line merge | **Deferred**; not part of OD-1 |
| Q7 | `column_margin_pt`, `line_tolerance_pt` | 3 and 3, **provisional**, not validated on a sufficient sample |
| Q8 | Timing of the OD-1 decision | **Requirement, not a question:** the owner decides OD-1 only after the B-133 review (`docs/d01_public_report_checklist.md` §7). This proposal is not to be put forward for decision before that review. Provisional owner preference recorded (§0.1), consistent with the existing gates |
| Three-year statements | — | Kept out of OD-1 (U-4) |
| Grouping validity | — | Kept out of OD-1 (U-3) |
| Q9 | Label-contiguity guard for hazard H1 | **Deferred**: not adopted, not approved, not in the algorithm; H1 is a known residual risk (§13.1); no AC-OD1-27 |
| **Q10** | Should the numeric-token definition be extended so an attached currency symbol (`$1,234`) can be assigned? | **Provisional owner preference: defer (§0.1); not approved.** It fails safe (3.8); FR-004.3 and G.0 are unchanged |
| **Q11** | Is the fail-safe rule for headerless continuation pages (3.9) acceptable, given it is narrower than the current FR-005.7 text? | **Provisional owner preference: accept the fail-safe, subject to PRD reconciliation (§0.1); not approved.** "Unless alignment can be independently verified" is undefined until a method is specified; no method is proposed |
| **Q12** | How should FR-005.10 recognise a note reference when there is no "Note" header (U-8)? | **Open**, needs an owner or PRD clarification |

---

## 9. Proposed `extract_words` interface change (not implemented; for compatibility review)

Form under review: a **separate Protocol**, so that `TextExtractor` is not modified. This form is a proposal; the owner approved only the idea of adding `extract_words` to the extractor interface, in principle. (Adding the method to `TextExtractor` itself would break every existing fake and is not recommended.)

```diff
--- a/src/credit_intel/ingestion/models.py
+++ b/src/credit_intel/ingestion/models.py
+@dataclass(frozen=True)
+class Word:
+    """One word, in PDF points, top-left origin."""
+    text: str
+    x0: float
+    x1: float
+    top: float
+    bottom: float
+
+@dataclass(frozen=True)
+class PageWords:
+    page_number: int        # 1-based physical page number
+    width: float            # points; pdfplumber reports the UNROTATED page size, not the displayed size (see §15)
+    height: float
+    rotation: int           # degrees: 0, 90, 180 or 270
+    words: tuple[Word, ...]

--- a/src/credit_intel/ingestion/extractor.py
+++ b/src/credit_intel/ingestion/extractor.py
 class TextExtractor(Protocol):          # UNCHANGED
     def inspect(self, path: Path) -> PdfInspection: ...
     def extract_pages(self, path: Path) -> list[PageText]: ...
+
+class WordExtractor(Protocol):          # NEW, separate
+    def extract_words(self, path: Path, page_numbers: Sequence[int]) -> list[PageWords]:
+        """One PageWords per requested page, ascending by page number, words sorted
+        by (top, x0, text). Raises IngestionError, never a library exception."""

--- a/src/credit_intel/ingestion/pdfplumber_extractor.py
+++ b/src/credit_intel/ingestion/pdfplumber_extractor.py
 class PdfplumberExtractor:               # would satisfy both Protocols
+    def extract_words(self, path, page_numbers) -> list[PageWords]:
+        # same _open / _load_pages error mapping as extract_pages
```

**Compatibility with existing callers and tests**

| Item | Effect |
|---|---|
| `TextExtractor`, `PageText`, `ingest()`, `validate_pdf()` | Unchanged; their parameters stay typed `TextExtractor` |
| `tests/unit/test_validation.py` fake (has `inspect` only) | Still valid; it never needs `extract_words` |
| `tests/unit/test_page_extraction.py` fakes (`inspect`, `extract_pages`) and real `PdfplumberExtractor()` | Still valid; unchanged |
| `tests/integration/test_table_extraction.py` (`PdfplumberExtractor().extract_pages(path)[0].text`) | Unchanged |
| `tests/unit/test_fresh_process_golden.py` (B-120) and its golden file | Unchanged; page text must stay byte-identical |
| No `runtime_checkable` Protocol is used anywhere | A fake without `extract_words` cannot be rejected at runtime |
| New requirement | Only the future period-column verifier needs a `WordExtractor` |

**Open compatibility questions (not decided here)**
- Whether pdfplumber's page width and height already reflect rotation, and which attribute gives rotation, is **unverified** and must be checked in the review. **Answered on synthetic PDFs on 2026-10-19 (§15):** they do not reflect rotation; `page.rotation` gives it.
- How duplicate, unsorted, empty or out-of-range `page_numbers` are handled (reject with `IngestionError`, or ignore) is unspecified.
- Which `extract_words` parameters are pinned (for example `x_tolerance`, `y_tolerance`), and how they relate to `extract_text`, is unspecified; AC-OD1-25 depends on it.
- Whether crop-box or media-box offsets and `UserUnit` change coordinates is unchecked. **Partly answered on 2026-10-19 (§15):** a crop box changed no coordinate; `UserUnit` is inconclusive.

**Planned tests (when approved; none written):** the full existing suite passes unchanged (147 tests at the last check on 2026-10-17; 362 passed at `3be8acd`); a golden `extract_words` result in a fresh process (as B-120); `PdfplumberExtractor` satisfies both protocols; page number, width, height and rotation on synthetic pages, including a rotated page (reportlab can set page rotation); errors map to `IngestionError`; empty, duplicate and out-of-range page lists behave as specified; `extract_words` and `extract_pages` agree on page numbering. This review is on paper; no code was changed and no test was run for it.

---

## 10. Mapping of AC-OD1-1 to AC-OD1-26 (for review before implementation)

"Existing" means behaviour already in `tests/BEHAVIOURS.md`; every AC-OD1 test itself is **new and unwritten**.

| AC | Requirement(s) it checks | Existing behaviour it relies on or extends |
|---|---|---|
| 1 | FR-005.7 (B, R, N, U); note region | B-131 (aligned columns, note reference) |
| 2 | FR-005.7, FR-005.9 (period from validated anchor) | None for order independence (new) |
| 3 | FR-005.7 (overlap, B) | B-131 layouts |
| 4 | FR-005.9 (D-11), 3.3 header block | Appendix B Example 1 header; current-period full date (FR-005.9, v0.4.13) |
| 5 | FR-005.9 (D-11) (year token alone) | None (R2 pattern; new); current-period full date (FR-005.9, v0.4.13) |
| 6 | FR-005.10 (D-10) and FR-005.3 order for part (a); FR-005.7 label limit for part (b) | B-133 R2 p38 finding (no test exists); B-132 characterises text order only |
| 7 | G.0 figure line; 3.4 | None (new) |
| 8 | FR-005.7 (U) | None (new) |
| 9 | FR-005.7 (B); 3.7 | None (new) |
| 10 | 3.3 structure S; rotation (A-3) | None (new) |
| 11 | FR-004.3 (D-08: a blank cell is `not_found` if nothing was proposed); FR-005.7; B.6 rows 11–14 | B-132 (blank cell leaves no placeholder) |
| 12 | FR-004.3 nil convention (D-08) | B-131 (nil dashes kept) |
| 13 | FR-004.3; FR-005.6; Appendix B Example 2 | B-131 (bracketed negatives) |
| 14 | FR-005.7 (U); FR-005.6 | B-132 (split figures); fails safely |
| 15 | FR-004.3 | B-131 (Indian grouping); grouping validity excluded (U-3) |
| 16 | FR-004.3 | None (new) |
| 17 | FR-005.7 (U); P-1 | B-132 / B-133 SPLIT rows; fail safe only (U-1) |
| 18 | G.0 numeric token; 3.8 | None (new) |
| 19 | FR-005.1 quote; 3.5 | None (new) |
| 20 | FR-005.10 (D-10) | None for word positions (new) |
| 21 | FR-013 rule 3b (continuation), rule 6 (statement runs); 3.9 fail-safe (Q11) | B-121, B-126 (selection and runs only) |
| 22 | 3.3 structure S | None (new) |
| 23 | 3.3 extra columns; U-4 | None (new) |
| 24 | FR-002.3 determinism | B-115, B-120 (extended to words) |
| 25 | Assumption U-6 (synthetic only) | None (new) |
| 26 | FR-005.7 label-limit invariant | None (new) |

Locator tests B-121 to B-130 are unaffected: FR-013 and G.0 stay text-only.

---

## 11. Can the Microsoft `7,434` be assigned to a financial column?

**Under the proposed rule, with the geometry recorded in `PROGRESS.md` (`7,434` at x1 ≈ 105, left of every period region): no, for two independent reasons.**
1. The `7,434` words are label words (x1 ≤ label limit). They are never value candidates, so they are not tested against conditions B, R, N or U at all.
2. The wrapped row fails the row-label check on its own. For the inferred fragment (the real line split is not recorded), the text before the figure line's first figure is not a configured phrase, so the reason is `label_not_recognised` (FR-005.3 order), and no value is accepted. AC-OD1-6(a) states this outcome; AC-OD1-6(b) tests the label limit separately.

**What this does and does not show:**
- I did not read `private/`. The real geometry of R2 p38 was **not** re-verified, and the positions of the period columns on that page are not recorded here. The statement rests on the recorded x1 value only.
- **The recorded failure and H1 are different things.** The recorded failure was a nearest-column heuristic assigning a number wholly left of the figure columns to 2025; the label limit removes it. H1 is a synthetic variant (a label number *overlapping* a period region, with that period's cell blank) that I constructed on a throwaway layout; it was **not** observed in the 34 reviewed rows, and the label limit does not stop it. It is a known residual risk (§13.1).
- The four-layout probe was my own reimplementation of the rule in a script outside the repository. It was not retained, so these results are not reproducible from the repository and are illustrations only. One layout showed my probe merging words; that is a probe artefact and is not relied on.

H1 is handled in §13: the Q9 guard is **deferred, not adopted and not part of the algorithm**.

---

## 12. Remaining ambiguities

Listed in §0 (U-1 to U-14, with P-1 to P-3). Nothing in this file decides OD-1, B-133, D-01 or D-14a.

---

## 13. H1 residual risk and the DEFERRED Q9 label-contiguity guard

**Status:** Q9 is **deferred, not adopted and not approved**. The guard in §13.4 is **not part of the proposed OD-1 algorithm** (§3) and is kept only as a record of a draft that was reviewed on 2026-10-17. **AC-OD1-27 is not added** to §6. Nothing here is implemented. OD-1 stays open.

### 13.1 H1: known residual risk of the approved direction
- **What it is:** a number that belongs to a row label may overlap a period-column region. If that period's cell is blank, the label number is the only numeric token in the region, so conditions B, R, N and U can all pass. It is then misassigned **if the upstream proposed-value selection supplies that label number as the period's value.**
- **Not observed in the reviewed data:** H1 has **not** been observed in the 34 rows reviewed in B-133 (0 of 34). The recorded Microsoft failure was a nearest-column assignment of a number wholly left of the figure columns, which the label limit (3.4) excludes. H1 was produced only on a synthetic layout built for this proposal. No frequency or likelihood is claimed.
- **Why it is residual:** the rule cannot tell from position alone whether a numeric token inside a region is a value or part of a label that extends that far. Any such distinction needs another signal (spacing, or alignment with other rows) that is not validated.

### 13.2 How the existing checks interact with H1
| Check | Effect on H1 |
|---|---|
| **Proposed-value check** (3.6, last paragraph) | The main protection. If the proposed value is not equal to the assigned token, the period is `requires_review` / `period_not_verified`. If the model proposes the true value or nothing, H1 is not misassigned. It does **not** protect when the model proposes exactly the label number (the token then matches) |
| **Condition U** | Protects when the cell is populated: the label number and the real value are two numeric tokens in one region, so U fails (`requires_review`, `period_not_verified`) |
| **FR-005.10 label check (R)** | Protects only if the label words on that figure line fail the label check (`label_not_recognised`, ordered by FR-005.3). It does **not** protect if the label fragment on the figure line is recognisable |
| **Label limit** (3.4) | Protects only for numbers wholly left of the label limit; not for numbers that overlap a region |
| **No proposal** | If nothing is proposed for the period, there is nothing to verify and the outcome is `not_found` |

Residual exposure: blank cell, a label number overlapping the region, a recognisable label fragment on the figure line, and the model proposing that label number.

### 13.3 Scenarios that test the CURRENT rule and document the residual (proposed only; not approved)
Named H1-a to H1-d. They need no guard.

| ID | Case | Expected under the current rule | Coverage |
|---|---|---|---|
| H1-a | Label ends with a number overlapping the 2025 region; 2025 cell blank; 2024 populated; the model proposes that label number for 2025 | 2025 **assigned** (known residual: the value check passes); 2024 assigned. A **characterisation of a known limitation, not a requirement** (to be named like B-132's "known limitation" tests); it must be revisited if a guard is ever adopted | New |
| H1-b | As H1-a, but the model proposes nothing for 2025 | 2025 `not_found`; 2024 unaffected | Largely duplicates AC-OD1-11 |
| H1-c | As H1-a, but the model proposes a different number for 2025 | 2025 `requires_review`, `period_not_verified` (value differs) | Duplicates the value-mismatch outcome in 3.7 |
| H1-d | Label number overlaps the 2025 region **and** the 2025 cell is populated | 2025 `requires_review`, `period_not_verified` (condition U: two numeric tokens in the region); 2024 assigned | Extends AC-OD1-8 with a numeric label token; little new coverage |

**Correction of the earlier G-3:** G-3 expected both periods to be assigned while the label number still overlapped the populated 2025 region. That contradicts condition U. It is replaced by H1-d, which has the same purpose (a populated cell must not silently take the label number) and is consistent with U.

### 13.4 The deferred guard (draft; NOT part of the algorithm)
Let *T* be the single numeric or nil token in region *C*. Let *P* be the nearest word left of *T* on the line that is not a region word, not a separate currency symbol and not a detached minus. Draft: if the gap `T.x0 − P.x1` is no larger than an "average character width" of *P* and *T*, *T* is treated as label and the period is `requires_review`, `period_not_verified`.

**Not validated; no suitability claim.** The threshold is an unvalidated constant (a multiplier of 1.0 on an average width) that is not defined precisely (per-word or pooled average; letters and digits weighted alike or not). The synthetic geometry in this file does not establish that it suits real reports, and the guard has not been run, even on synthetic geometry.

**Known weaknesses of the draft:**
- Whether ordinary word gaps fall inside the threshold depends on how each PDF encodes spaces and on pdfplumber's `x_tolerance`; this is unmeasured.
- It rejects legitimate figures that abut a label (narrow tables, tight tracking) and rows with dot leaders.
- It does not fire when a gap is wider than the threshold, so it does not close H1.
- The order of evaluation against B and U is unspecified.

### 13.5 Review of the draft scenarios G-1 to G-7 (apply only if the guard were adopted; proposed only)
| ID | Case | Expected with the guard | Coverage |
|---|---|---|---|
| G-1 | H1-a geometry with a gap to the label word within the threshold; model proposes the label number | 2025 `requires_review`, `period_not_verified`; 2024 assigned | **New**: the only case where the guard changes an outcome |
| G-2 | As G-1, no proposal for 2025 | 2025 `not_found` (guard changes nothing) | Duplicates H1-b |
| G-3 | *Replaced by H1-d (§13.3)* | — | — |
| G-4 | Large gap, populated cell | Assigned as in AC-OD1-1 | Duplicates AC-OD1-1 |
| G-4b | Large gap (above the threshold), blank cell, model proposes the label number | 2025 **assigned** (guard silent). A **characterisation of a known limitation, not a requirement**: documents that H1 stays open | New |
| G-5 | AC-OD1-3 layout (header centred over wider figures), with an explicit gap above the threshold | Same result as AC-OD1-3 | Duplicates AC-OD1-3 with the guard enabled; checks only that nothing changes |
| G-6 | Figure abutting the label (gap within the threshold), populated cell | 2025 `requires_review`, `period_not_verified` | New: documents the lost-row trade-off |
| G-7 | **Withdrawn.** Its scale-invariance expectation contradicted the absolute 3 pt settings (a scaled page changes which words overlap a ±3 pt margin). The shift and shuffle properties duplicate AC-OD1-24 and AC-OD1-26 | — | Duplicate |
| G-8 | Gap exactly equal to, just below and just above the threshold | Fires at equal and below ("no larger than"); silent above | New; floating-point comparison must be specified |
| G-9 | Dot-leader word between label and figure | `requires_review`, `period_not_verified` | New: documents a false rejection |

Interaction with AC-OD1-1 to AC-OD1-26 if the guard were adopted: no existing expected result would change except where it converts a wrong assignment into `requires_review`. This analysis is on paper only.

### 13.6 Remaining evidence gap
- Real-report **gap distributions** between label words and first values, how real PDFs encode spaces, how often dot leaders occur, and whether H1 occurs at all are all unmeasured.
- The two tuning documents have not been examined for this question. Doing so would require **separate, explicit owner authorisation to access `private/`**; that authorisation has not been given and `private/` was not accessed. **Update 2026-10-19:** a narrow check of the ten inspected pages has since been made with the owner's authorisation (§14); H1 frequency, gap distributions between label words and first values, and dot leaders remain unmeasured.
- Two documents would show whether the pattern occurs, not how often. If H1 or a close variant is found, a cross-row alignment check may be a better candidate than a spacing threshold; that is a note, not a proposal.
- Adopting any guard would need a separate owner decision and an approved amendment to §6.


---

## 14. Evidence from the narrow tuning-document check (2026-10-19)

**Status:** evidence note only. It decides nothing, changes no algorithm or setting, and claims no accuracy. OD-1 stays open.

- **Authorisation and scope:** the owner authorised, on 2026-10-19, a narrow read-only check of `private/` for U-6 and U-13 only. Only the two tuning PDFs were opened (R1 physical pages 194–197 and 274–277; R2 physical pages 36 and 38), read-only. No page, statement or text was copied; only counts and a few short tokens were recorded.
- **Method and its limits:** an approximation of this proposal's rules, not an implementation of it. Word-lines were grouped as in 3.2 (tolerance 3). Anchors were the year tokens on the lowest header line above the first figure line; the note region was the "Note" header word; regions were the header extent ±3 pt; the label limit was the leftmost region edge. Figure words were detected by the G.0 pattern. These heuristics may differ from a real implementation.
- **U-6 (word-lines versus `extract_text` lines):** on all ten pages the word-lines were identical to the lines of `extract_text` (the text the pipeline stores): **347 of 347 lines**, no mismatch. This supports the assumption behind 3.5 on these two documents. It does not show agreement on other layouts.
- **U-13 (narrow tokens), 539 numeric or nil tokens classified:** 419 fell in exactly one period region; 92 in the note region; 25 left of the label limit (label text); **3 in no region (stray)**; none in two regions. Nil dashes: two found; one was in a period region and one was left of the label limit (inside a label); none was lost. No short figure was lost.
- **The three stray tokens:** two were **note references** (`2.3` on R1 p196, 7.3 pt outside the note region; `2.21` on R1 p276, 4.9 pt outside it); one was an 8-digit number on R1 p195 that is not in a financial column (2.5 pt from a region). Under the 3.7 rule each stray token makes its whole line unverified, so each of the three lines would be lost. R2 has no note column, and all 62 and 72 numeric tokens on its two pages fell in period regions.
- **What this shows:** the narrow-dash hazard in U-13 did not occur in this sample. A different hazard did: a ±3 pt note region is narrower than the real alignment of note references (U-15). That affects Q2 and U-8. The period-column margin was not stressed in this sample (no token fell in two regions), but it remains unvalidated for other layouts.
- **Not covered:** H1 frequency, gap distributions, dot leaders, currency tokenisation on the real pages (the earlier log records `$` as a separate token in R2), headerless continuation pages, and any document other than R1 and R2.

---

## 15. Compatibility review of `extract_words` on synthetic PDFs (2026-10-19)

**Status:** evidence note only. It decides nothing, changes no algorithm or setting, and implements nothing. OD-1 stays open. The owner authorised this read-only review on 2026-10-19 (item 14 of the OD-1 question sheet). `private/` was not used for it.

- **Method:** scratch scripts outside the repository, with synthetic reportlab PDFs (default A4 page size). Versions: pdfplumber 0.11.10, pdfminer 20260107, reportlab 5.0.1. Nothing was added to the repository.
- **Rotation:** `width` and `height` stayed 595.3 × 841.9 at page rotations 0, 90, 180 and 270, so they are the **unrotated** page size. Rotation is available as `page.rotation` (and the page's `/Rotate` entry). Word coordinates fell in the rotated frame (x up to 697.5 on a page reported 595.3 wide at 90°), the word text came out reversed at 180° and 270° (`olleH`, `432,1`), and x was negative at 270°. Geometry on a rotated page is not usable, which supports the decision that rotated pages are unverifiable (A-3). The comment in the §9 diff ("as the page is displayed") was wrong for pdfplumber and has been annotated.
- **Crop box:** setting a crop box changed `cropbox` but not `bbox`, and no word coordinate moved.
- **`UserUnit`:** inconclusive. The test PDF was hand-edited with stale cross-reference offsets; pdfplumber reported unchanged dimensions and coordinates.
- **Parameters:** `extract_words` defaults use a 3 pt tolerance. Pinning `x_tolerance` and `y_tolerance` explicitly at 3 would not change these results.
- **Word-line versus `extract_text` agreement (AC-OD1-25, synthetic):** the 3.2 grouping (tolerance 3) gave lines equal to `extract_text` on six layouts: aligned rows, a 2 pt offset, a 5 pt offset, a blank cell, an R1-type wrapped label tail and an R2-type wrapped label number. (Real pages: §14.)
- **Tokenisation:** a currency symbol within about 3 pt of its figure merged into one word (`$1,234`); a 4 pt gap made `$` a separate word. Nil dashes (`-`, `–`) and a detached minus were separate words; `-1,234` and `(4,901)` were single words. So "attached" versus "separate" depends on the gap (Q10, U-10).
- **Determinism:** `extract_words` output was identical when repeated in one process and in a fresh process, and words came back ordered by (top, x0).
- **Page access:** an out-of-range page index raises `IndexError`; page slicing works. How duplicate, unsorted or empty page lists are handled is the new interface's own decision and remains open.
- **Narrow tokens, synthetic sweep (U-13):** with a header centred a distance d to the left of the column's right edge (Helvetica 9, region = header extent ±3 pt), a right-aligned nil dash missed its region from d ≈ 20 pt, a two-digit figure from d ≈ 24 pt, and a long figure was unaffected up to d = 40 pt. This is geometry on synthetic pages, not evidence about real reports.
- **Not covered:** a proper `UserUnit` test, scanned or unusual page boxes, real fonts and Type 3 fonts, other pdfplumber versions, and any real-report claim.
