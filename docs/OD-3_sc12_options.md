# OD-3: the SC-12 target. Options for the owner to choose from

| Item | Value |
|---|---|
| Status | **For decision. Nothing is chosen, and no recommendation is made here.** `docs/PRD.md` is unchanged (0.4.48). |
| Drafted | 2026-10-27, at the owner's request ("lay out the actual SC-12 target options and tradeoffs ... don't pick one yourself") |
| Where it stands in the PRD | OD-3 is open ("Validation of the FR-013 initial settings and an SC-12 target"; options (a) keep the initial values and set a target after measuring on the tuning set, (b) adjust the values first, then set the target). SC-12 is reported "as counts only until a target is approved". |

## 1. What SC-12 is, and what exists today

**SC-12, statement-page recall** (PRD E.2): the share of ground-truth primary-statement pages (the income statement and the balance sheet, continuation pages included) that the locator (FR-013) includes among its candidate pages.

- The locator caps its candidates (`max_candidates`, 15 today; "matches the SC-10 assumption"). A document with more qualifying pages than the cap cannot reach full recall.
- **A page the locator leaves out is a page no field can be read from.** The fields that rest on it come back `not_found`, so a low recall loses data without any visible error. This is why it is measured separately from SC-01.
- **No SC-12 figure is recorded** in the PRD or in `PROGRESS.md` for any document. The PRD says so for the held-out set (Section T.1: SC-12 has no measurement), and the first report is still unbuilt.
- **Before any target can be proposed, two things are needed**, whichever option is chosen: (i) a report that compares candidate pages with ground-truth statement pages, per document, counts only (not built; Definition of Done item 8 was accepted as not met); (ii) the ground-truth page labels for the tuning documents, which sit in `private/eval/`, so I would need your authorisation to read them, with counts-only output.
- **Rules that bind every option:** targets are proposed from a **tuning-set baseline** and approved by the owner (O.3); a held-out result is never used to change a setting (AC-E-7); each held-out run is reported separately by run id (v0.4.42).
- The existing held-out documents (H1 to H4, and S3 for OCR only) have already been run or closed. A target set now would apply to **future** held-out documents; it cannot be tuned on the past ones.

## 2. The options

Each option answers one question: **what does a pass look like?**

### Option 1: counts only, with no numeric target

SC-12 stays "reported as counts". Each report lists, per document, the ground-truth pages, the candidate pages and every page that was missed (by page number). A miss is explained, not judged against a number.

| For | Against |
|---|---|
| Honest at the sample size: the tuning set has two text documents and the held-out set a handful, so any percentage is a few pages. | No pass or fail, so SC-12 can never be "met" or "missed". |
| No arbitrary number to defend; fits "no performance claim without a recorded report". | E.2 shows a target column; this means the row says "none" for good. |
| Costs nothing to adopt. | Gives a reviewer or an investor nothing to hold the locator to. |

**Needs:** the counting report (1 (i) above). No baseline is needed to set a value.

### Option 2: no primary page missed, per document (100%)

A document passes SC-12 only if **every** ground-truth primary-statement page is a candidate. Any miss fails that document and is explained in the report.

| For | Against |
|---|---|
| Matches the consequence: a missed page means missing fields. | One missed page fails a document; with 5 documents that is 20 percentage points of the result. |
| Simple, per document, no pooling. | A document with more qualifying pages than the cap (15) cannot pass, whatever the locator does. |
| A target that is easy to state and to check. | Continuation pages are the hardest to label and to find, so they dominate the failures. |

**Needs:** the counting report, a baseline on the tuning documents to see whether 100% is realistic, and a decision on documents that exceed the cap.

### Option 3: a pooled percentage threshold, X% of ground-truth pages

A pass is X% or more of all ground-truth primary-statement pages in a held-out run. X is set from the tuning baseline and approved by you.

| For | Against |
|---|---|
| Tolerates the occasional miss; a familiar form of target. | X comes from two tuning documents, so it is close to arbitrary. |
| One number for the whole run. | One page is a large share (at about ten pages per document, one page is about two points of a five-document run). |
| | Pooling hides a concentrated failure: one document missing most of its pages can still pass. |

**Needs:** the counting report, the tuning baseline, and your choice of X (I would not propose X before the baseline exists).

### Option 4: two tiers, the first page of each statement against the continuation pages

Two measures. **Primary pages** (the first page of each statement) must all be found (100%). **Continuation pages** are reported as counts only.

| For | Against |
|---|---|
| Separates the pages the whole read depends on from the hardest ones. | Needs a new definition of "primary" and "continuation" in the labels, which the current labels may not carry. |
| Keeps a firm target where it matters. | Two numbers to explain; continuation pages stay unmeasured against a target. |
| A miss of a continuation page is visible and not fatal. | The PRD's SC-12 wording includes continuation pages, so this changes the definition. |

**Needs:** the counting report with page roles, a labelling rule for the roles (owner), and a PRD change to the SC-12 definition.

## 3. A separate question under any option: the locator settings

OD-3 also covers whether to change the FR-013 initial values before measuring.

| | Text |
|---|---|
| (a) | Keep the initial values, measure on the tuning set, then set the target (the PRD's present option (a)). |
| (b) | Adjust the values first, from tuning-set evidence only, then measure and set the target (the PRD's present option (b)). |

Adjusting first (b) may improve the baseline but means the target is set for tuned values, and every adjustment must come from tuning documents only (AC-E-7). Keeping them (a) gives a cleaner first baseline and a possible defect list afterwards.

## 4. What I need from you

1. Which option (1 to 4), or a combination (for example Option 4's tiers with Option 3's threshold on the primary tier).
2. (a) or (b) for the locator settings.
3. Whether I may read the tuning documents' ground-truth page labels in `private/eval/`, counts only, to build the baseline report. Nothing is read until you say.

Whatever you choose, I would draft the PRD change (E.2, the OD-3 row, a version bump) and wait for your approval before applying it, as before.
