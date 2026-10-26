# PRD proposal: OCR for scanned annual reports (draft)

| Item | Value |
|---|---|
| Status | **Draft for the owner's review. Not applied to `docs/PRD.md`. Nothing is built.** No version number is assigned; it would be a new minor version if approved. |
| Drafted | 2026-10-26 |
| Scope | A document that is a genuine scan: pages are images of text and the PDF has no (or a useless) text layer. Not in scope: pages whose text layer exists but is merged, garbled or mis-ordered. |
| Changes if approved | FR-001.6 and its error text; a new OCR step in the ingestion module behind a new interface; FR-005 (an `ocr` source for evidence); FR-013 (page choice for a scanned document); the field `validation` record; the manifest; the memo labels and section 9; SEC-10; Appendix B.6 examples; the error catalogue; D-xx and OD-11 to OD-16 below. Every place that says "no OCR" changes: the scope table, the release-boundary list, the memo's section 9 fixed text, the glossary, and the README. |
| Evaluation | A scanned document is **not** scored with the text-layer documents. Its tuning and held-out assignment, and its report, are separate (as with held-out runs, by run id). AC-E-7 applies to any confusion table or threshold in this proposal. |

## 0. The one design point that decides the rest

Everything in FR-005 verifies the model's quote against the page's own text: the quote must occur on the page (rule 1) and the value must occur in the quote (rule 2). With a text layer, the page text is what the publisher printed, so a pass means "the model did not invent this". With OCR, **the page text is itself a machine reading**. If the model's quote is checked against OCR text from one engine, a pass shows the model agrees with the OCR engine and says nothing about whether the OCR engine read the page correctly. A misread digit passes every check.

So the proposal does not treat OCR text as a text layer. It treats OCR as a **weaker kind of evidence** that is recorded as such, can be wrong in ways the existing checks cannot see, and is therefore never silently used (section 4).

## 1. Trigger

**Today (FR-001.6):** if no page has any non-whitespace extracted text, the run is refused with `E-INPUT-NO-TEXT-LAYER` ("OCR is not supported").

**Proposed:**

1. Decide per page, not per document. A page is **image-only** if its extracted text has no non-whitespace character and the page holds an image covering most of its area (a threshold in settings; the page-area test is needed so that a blank page is not sent to OCR). A page with a text layer is never OCR'd.
2. The existing refusal stays the default. A scanned document is refused as today unless OCR is turned on, either with a new flag `--ocr` or the setting `ocr.enabled = true` (OD-14). When OCR is off, the message says the document looks scanned and names the flag. This keeps current behaviour exactly as it is for everyone who does not ask for OCR.
3. When OCR is on and a document has no text layer, OCR runs on the **pages the run needs**, not on the whole document (OD-13). The first release requires `--pages` for a scanned document, because the locator (FR-013) scores text and OCR of every page of a 400-page report is slow and, with an LLM engine, costly. The page-range case of FR-013 rule 8 already exists, so no new locator mode is needed.
4. If OCR yields no text for the pages (blank, unreadable), the run ends with `E-INPUT-NO-TEXT-LAYER` as today. Two new codes: `E-INPUT-OCR-UNAVAILABLE` (engine not installed or not configured) and `E-INPUT-OCR-FAILED` (engine error). Both exit 3 or 5 as the catalogue assigns; neither prints document text.
5. Mixed documents (some pages with text, some scanned) are handled by rule 1: only the image-only pages are OCR'd, and the run records which pages came from which source.

## 2. Library and approach (decided like D-01, with the alternatives and what each costs)

| | A. Tesseract (local) | B. Vision LLM call (hosted) | C. Hybrid: Tesseract for text, a second reader only to cross-check digits |
|---|---|---|---|
| What it gives | Text **and** per-word bounding boxes **and** per-word confidence | Text only; no boxes, no word confidence | As A, plus an independent reading of the cited figure |
| Fits the existing design | Yes. Boxes feed the `WordExtractor` interface (FR-005.7); text feeds `TextExtractor`. | No. Without boxes the period-column check (FR-005.7) cannot run, so every value would be `period_not_verified`. | Yes |
| Accuracy on financial tables | Good on clean scans at 300 dpi; weak on skew, stamps, narrow numeric columns, dot leaders and brackets. Misreads are typically **visible** (low confidence) and character-level (`0/O`, `1/l`, `5/S`, a lost comma or bracket). | Often better on layout; but it can **fabricate plausible digits** with no signal, and it has no confidence. Silent errors are the dangerous kind in credit work. | Misreads that the two engines disagree on are caught; a shared misread is not |
| Cost | No per-page fee; CPU time per page, to be measured on the tuning set (not assumed). Needs a system install of the Tesseract binary. | Per-page token cost for the image, plus the model's own extraction call; to be priced against current rates before any decision, as D-02 required. Counts against the token ceiling (NFR-09). | A plus the cost of B on the few pages only |
| Data leaving the machine | None | **Whole page images go to the hosted API.** SEC-10 already limits what may be sent (public or synthetic documents only); an image carries everything on the page, not just statement text. | The cited-figure crop only (OD-16) |
| Licence | Tesseract: Apache-2.0. Python wrapper (pytesseract): Apache-2.0. Language data: Apache-2.0. To be confirmed at install time, as D-01 required. | n/a (service terms; SEC-10) | both |
| Determinism and cache | Deterministic for a given engine version and DPI; the result is hashed and recorded. | Non-deterministic in principle; would need the FR-003.5 cache keyed on the image. | mixed |
| Offline tests | A fake OCR engine (like the fake LLM provider) for the whole offline suite; a real-Tesseract test marked opt-in. | Fake provider | both |

**Recommendation: A, behind a replaceable `OcrExtractor` interface, as D-01 did for pdfplumber.** Reasons: it is the only option that supplies boxes and confidence, which the existing checks and section 4 need; it keeps the document on the machine; it has no per-page fee. B is not suitable as the primary reader because it cannot be verified by the existing rules and its errors are silent. C is an optional later extension (OD-16), not part of the first release.

**Verification required before acceptance (as D-01):** run Tesseract on synthetic scans generated at test time (render a synthetic statement to an image, add skew and noise) and on any scanned public report the owner assigns to tuning, measure the character and figure error rate and the time per page, and record the findings. Real scanned reports are never committed; outputs for them are counts only.

**Rendering:** pages are rendered to images in memory at a configured DPI (provisional 300), passed to the engine and discarded. No page image is written to the repository, and none is written to the run folder.

## 3. How OCR quality affects the rules that assume a clean text layer

| Rule | What breaks with OCR | Proposed handling |
|---|---|---|
| **FR-005.1/2** quote on page; value in quote | Both are checked against OCR text, so they cannot catch an OCR misread (section 0). | Unchanged mechanically. The field is marked `source: ocr` and section 4 applies. A pass is recorded as "consistent with the OCR reading", never as "verified on the page". |
| **Row labels** (FR-005.10, FR-013 phrases) | A phrase misread by one letter (`Profit hefore tax`) matches nothing. FR-005.1 forbids fuzzy matching. | **No fuzzy matching is added.** A misread label gives `label_not_recognised` (fails safe, lowers recall). The cost is measured on the tuning scan; whether a small, closed confusable-character normalisation for **labels only** is worth adding is OD-15, not assumed. |
| **Period column** (FR-005.7) | OCR boxes are looser than text-layer boxes; page skew moves columns; `column_margin_pt` (3 pt) was tuned on text-layer documents only. Digit groups and brackets may be reported apart (the split-figure rule of v0.4.35 helps) or lost. | The check runs on OCR boxes unchanged. The margin and the join gap get **OCR-specific settings**, tuned only on the scan tuning set, so the text-layer settings are not touched. A page whose skew the engine reports above a limit is deskewed first; if it still cannot be placed, the check gives `period_not_verified` (fails safe). |
| **Numeric tokens** (parse, FR-005.6 sign, U-1 to U-4 deferred cases) | Likely new cases: `,`/`.` swapped, a bracket read as `{` or `[` or dropped (sign flips silently), a dash lost, `O` for `0`. | A token is accepted as a number only if it matches the existing parser **exactly**; anything else is unparsable and the field is `requires_review`. The sign check treats a bracket-like character that is not `(`/`)` as ambiguous, not as positive. Digit-confidence is applied in section 4. |
| **Scale and currency declarations** (FR-005.8) | "crore", "₹" and "in millions" misread. | Same exact phrase lists; a misread declaration gives `scale_not_verified`. No change. |
| **Period-end evidence** (FR-005.9) | A date misread by one digit validates the wrong year. | A period-end quote taken from OCR needs a digit confidence at or above the threshold of section 4, or the field is `period_not_verified`. |
| **Derived values and metrics** | They assume `extracted` fields are as trustworthy as the print. | Section 4: an OCR field never feeds a metric by default. |

None of these changes touches the text-layer path. The OCR path is selected per page by `source`, so the existing tests, the gate and the tuning results remain valid as they are.

## 4. Confidence, review flag, and the rule that OCR is never silent

1. **Every OCR-derived field carries `evidence_source: "ocr"`** (text-layer fields carry `"text_layer"`), plus: engine and version, DPI, the **minimum and mean word confidence of the words in the quote**, and the page's mean confidence. These are recorded in the field's `validation` record, in `results.json` and in the manifest. Confidence numbers are the engine's own and are stated as such.
2. **Default rule (recommended, OD-12 option a): an OCR field is never `extracted`.** It has status `requires_review` with the reason `ocr_unconfirmed`, and it is **not used in any metric, derived value or risk rule**. The memo lists it in the missing-and-review section with its quote, page and confidence, labelled `[OCR p.N, confidence …]` instead of `[SOURCE: p.N]`, so a reader cannot take it for a printed-text quote. A new analyst question is added to the fixed list ("Check this value against the page image").
3. **Optional promotion (OD-12 options b or c).** A field could be treated as usable when **all** hold: the minimum word confidence of its numeric tokens is at or above a threshold; every check of FR-005 passes; and a second reading agrees on the digits (OD-16). It would then still carry `evidence_source: "ocr"` and the `[OCR]` label, and rule RI-007 (conflicting or unverified values) would fire for it. The threshold is a provisional setting tuned only on scan tuning documents (AC-E-7), and no value is proposed here, because there is no scan on the record to tune it on.
4. **Everything downstream shows the source.** Section 2 of the memo (documents reviewed) states that OCR was used, on which pages, with which engine and settings; section 9 replaces "no OCR" by a fixed OCR limitation sentence. A run where OCR was used cannot produce a memo that reads like a text-layer run.
5. **Never mixed silently:** a run's results state, per field, which source it came from; a test checks that no `ocr` field is reachable from a metric input in the default mode.

## 5. Open questions (same form as the OD items)

| # | Decision | Options | Consequences | Evidence needed / needed by |
|---|---|---|---|---|
| OD-11 | OCR engine for the first release | (a) Tesseract behind an `OcrExtractor` interface (recommended). (b) A hosted vision model. (c) Tesseract plus a second reader later. | (a) boxes and confidence, on the machine, a system dependency. (b) no boxes, so no period-column check; silent errors; page images leave the machine. (c) is (a) now and more later. | Findings on synthetic scans and one assigned scanned report; before any OCR code. |
| OD-12 | Can an OCR-derived value feed metrics and rules? | (a) Never in Release 1: `requires_review` and listed only (recommended). (b) Yes, if confidence is above a threshold and every check passes, labelled and flagged. (c) Yes, only after a second reading agrees (needs OD-16). | (a) safest, small yield: a scanned report gets a draft memo that mostly lists values to confirm. (b) more yield, risk of a confident misread. (c) best yield, most work. | The owner's risk position; threshold evidence from scan tuning documents. |
| OD-13 | How much of a scanned document is OCR'd | (a) Only `--pages` the analyst names (recommended). (b) The whole document up to a page cap, then the locator. (c) The locator on a cheap low-resolution pass, then full OCR on candidates. | (a) simplest, bounded cost, puts the page choice on the analyst. (b) automatic, slow. (c) complex. | Time per page measured on the tuning scan. |
| OD-14 | Default and switch | (a) Off by default; `--ocr` or `ocr.enabled` turns it on; otherwise the existing refusal with a hint (recommended). (b) On by default. | (a) no behaviour change for existing users. (b) a scan is processed without asking, which makes the disclosure rules matter more. | Owner preference. |
| OD-15 | Label and phrase matching on OCR text | (a) Exact only; a misread label fails safe (recommended). (b) Add a closed set of character-confusion normalisations for labels, not for numbers. | (a) lower recall, no new false matches. (b) better recall, a new rule that must be tested and tuned (AC-E-7) and never applied to figures. | Measured recall loss on the scan tuning set. |
| OD-16 | Second reading of the cited figure | (a) None in Release 1 (recommended). (b) A second local engine. (c) A hosted vision call on a crop of the cited row only. | (a) none. (b) catches single-engine misreads, adds a dependency. (c) strongest cross-check but sends an image crop off the machine (SEC-10 applies) and the model can fabricate. | Decide only if OD-12 is (b) or (c). |
| OD-17 | Which scanned reports are used to tune and to test | (a) The owner assigns a tuning scan and, separately, a held-out scan, recorded in `assignments.jsonl` before anyone inspects them. (b) Synthetic scans only. | (a) needed for any accuracy claim; (b) tests the code, not the accuracy. Real documents are not committed and results are counts only. | A scanned public report from the owner; before any threshold is set. |
| OD-18 | The 100 MB and 600 page limits and SEC-12 | (a) Keep as they are (v0.4.43). (b) A separate OCR page cap and time limit, mandatory with OCR. | OCR makes SEC-12 (resource limits for untrusted PDFs) more pressing: rendering and OCR of a large file is a heavier workload than text extraction. | Timing data; relates to OD-6. |

## 6. What this proposal does not decide

It does not choose a threshold, a DPI, a language list beyond English (the project's line items are English-only), a particular scanned report, or a release for the feature. It does not change anything for a document that has a text layer. Nothing here is implemented, and the held-out record, the frozen configuration and the gate are untouched.

## 7. If you approve, the order I would work in (each step separate, with tests)

1. Settings, the `ocr` source on a field, the review reason `ocr_unconfirmed`, the manifest block and the memo labels, all with a fake OCR engine. No real OCR yet.
2. The page-level trigger and the `--ocr` flag, with the refusal hint.
3. The Tesseract adapter and the synthetic-scan fixtures; the findings recorded as D-01's were.
4. OCR-specific column settings, tuned only on an assigned scan tuning document.
5. Only then, and only if OD-12 allows, the confidence promotion.
