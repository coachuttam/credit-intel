# PRD v0.4.48 draft: a disclosed exception to OD-17, and the memo's scope sentence for runs without OCR (specification only)

| Item | Value |
|---|---|
| Status | **Draft. Not applied.** `docs/PRD.md` is unchanged (0.4.46). Each of the two parts can be approved on its own; each needs the owner's word and a version bump. |
| Drafted | 2026-10-27 |
| Source | The owner's assignment of the scans S1, S2 and S3 on 2026-10-26 (`docs/ocr_assignment_disclosure.md`), and the owner's choice of next step on 2026-10-27. |
| Version | 0.4.48. The number 0.4.47 belongs to `docs/PRD_v0.4.47_ocr_period_draft.md`, which was declined and never applied; this draft takes the next number so that the two files are never confused. |
| Kind | Part A changes an evaluation rule (OD-17, FR-001A.12, O.2). Part B changes fixed memo text (K.9) and so a golden file, a README sentence and tests. No part changes a calculation, a check or an OCR setting. |

## Part A. OD-17: a held-out scan seen before assignment

### A.1 The case

OD-17 and FR-001A.12 say the owner assigns a tuning scan and, separately, a held-out scan "before anyone inspects them". S3 was a photograph of a computer monitor, taken by the owner, and the assistant that prepared the file looked at the rotated image to confirm it was upright. The owner saw the page while taking the photograph. So S3 could not meet the rule as written, and the owner chose to proceed and asked that this be on the record, not hidden. It is recorded today in `docs/ocr_assignment_disclosure.md`, outside the PRD, because the assignment line has seven fixed members (O.2) and `reason` must be null on a first line.

The case will recur: a photograph, a screenshot or a file the owner prepares for the system is seen by its preparer. The PRD should say what that costs, not leave it to be bent each time.

### A.2 Options

| Option | Text |
|---|---|
| (a) **Recommended** | A **disclosed exception**, below: a scan that was seen only in the course of preparing it may be assigned held-out, with a committed disclosure, and every result on it is labelled and reported apart. |
| (b) | No exception: such a document can only be a tuning document. Simple, but then no held-out scan can ever be a photograph or a file the owner prepared, and an accuracy claim for scans needs a scan the owner never saw. |
| (c) | No change: the rule stays as written and each case is handled by the owner's say-so in a document outside the PRD. This is the position today. |

### A.3 Specification changes under option (a) (what would be applied)

**FR-001A.12 (add after the present text):**

> **Disclosed exception (v0.4.48).** The owner may assign a scan as held-out although it was seen before assignment, only when it was seen **in the course of preparing it** (photographing, scanning, converting, checking that it is upright and legible) and **not** to read, label or debug its content for the platform. The exception has these conditions, all of them:
> 1. A **disclosure** is committed no later than the assignment line. It names the document ID, who saw it, when and why, and what kind of document it is (for example a scan of paper, or a photograph of a screen). The disclosure file is `docs/ocr_assignment_disclosure.md`, append-only; the assignment record (O.2) is unchanged.
> 2. **No run, check or inspection by the platform or by the assistant that builds it** has happened on the document before the assignment line is committed. The preparer's sight is the only sight.
> 3. Every result on the document is labelled **"seen before assignment"** and **"reduced weight"** in the report and in the manifest of the run, and cites the disclosure. It is reported **apart** from held-out documents assigned under the plain rule and is **never pooled** with them in a rate or count. The report also states the kind of document, because a photograph of a screen (glare, moire) does not stand for a scan of paper (skew, shadow).
> 4. The exception applies to scans assigned for the OCR evaluation only. A text-layer held-out document keeps O.2 unchanged.
> 5. The held-out rules are otherwise unchanged. A document inspected **to debug a failure** still moves to the tuning set (O.2), and the preparer's sight is not such an inspection. AC-E-7 applies in full: no setting, prompt or phrase list changes in response to the result.

**O.2, "Held-out to tuning" bullet (add one sentence):** "Sight in the course of preparing a scan under the disclosed exception of FR-001A.12 is not an inspection to debug a failure."

**OD-17 table row:** append "A scan seen only while it was prepared may be held-out under the disclosed exception of FR-001A.12 (v0.4.48)."

### A.4 What this does to S3

S3 would be held-out under the exception, with the disclosure already committed (`671dded`). Conditions 1 and 2 hold today: the disclosure is committed with the assignment, and no platform run or inspection has touched S3 (it was hashed, never opened). Condition 3 would apply to any result.

### A.5 Weight, stated plainly

A result on S3 would support a statement about **photographs of monitors showing a statement page**, not about scans of paper, and it rests on one document. It would not support an accuracy claim for scanned reports. A held-out result that could support that claim needs a paper scan the owner never saw. The exception makes the record honest; it does not make S3 equal to a plain held-out document.

### A.6 Implementation if approved

Documents only, plus one small check: the manifest of a run on such a document records the disclosure (a flag and the disclosure's path), and the report prints the two labels. The held-out run itself stays under the existing procedure and needs the owner's separate approval; this draft does not authorise a run.

## Part B. K.9: the scope sentence for a run that did not use OCR

### B.1 The problem

K.9's fixed text for a run without OCR says: *"Only text-based PDF files are read. There is no OCR, so a scanned page cannot be read."* (K.9 names "text-based PDF, single document, no OCR".) Since v0.4.44 and the build that followed, OCR exists. A memo from a run that did not use it still says there is none. That is untrue of the platform, and it is contradicted by the README and by the memo of a run that did use OCR. It is not untrue of the run: OCR was not used, so no scanned page was read.

### B.2 Options

| Option | Text |
|---|---|
| (a) **Recommended** | Change the sentence to say what is true of the run: OCR is available and was not used. |
| (b) | Leave the sentence; accept that it describes Release 1, not the platform. |

### B.3 Specification changes under option (a) (what would be applied)

**K.9 table row, scope limits:** replace "text-based PDF, single document, no OCR (or, when the run used OCR, the fixed OCR limitation sentence of FR-005.11)" with "text-based PDF, single document, OCR not used (or, when the run used OCR, the fixed OCR limitation sentence of FR-005.11)".

**The fixed sentence, for a run that did not use OCR:**

| | Text |
|---|---|
| Now | Only text-based PDF files are read. There is no OCR, so a scanned page cannot be read. |
| Proposed | Only text-based PDF files are read in this run. OCR of scanned pages is available but was not used, so a scanned page cannot be read here. |

"Text-based PDF" and "single document" stay as required phrases; "no OCR" becomes "OCR ... was not used". The sentence for a run that did use OCR (FR-005.11) is unchanged. A run with `--ocr` on a document whose pages all have text layers has no `ocr` block, so it gets the new sentence, which is true of it.

### B.4 Effects

* `src/credit_intel/memo/limitations.py`: `SCOPE[0]`.
* `tests/fixtures/memo_golden.md`: that one line.
* `tests/unit/test_memo_sections_8_9.py`: the required-phrase list loses "no OCR" and gains "OCR of scanned pages is available but was not used".
* `tests/unit/test_memo_ocr.py` and `test_ocr_end_to_end.py`: their "There is no OCR is not in the memo" checks stay valid (an OCR run never had it).
* `README.md`: the Scope bullet no longer needs to keep the old sentence word for word; it can simply say what the memo says.
* `docs/PRD.md`: K.9 row; a version-history row; the status line.

### B.5 Not changed

OCR scope sentence of FR-005.11, any check, calculation, rule, setting, prompt or held-out record; the text-layer behaviour; Release 1's approval record (T.1 describes Release 1 as it was).

## What the owner is asked to decide

1. Part A: option (a), (b) or (c).
2. Part B: option (a) or (b).
3. Whether the two parts take one version bump (0.4.48) or two (0.4.48 and 0.4.49).
4. Separately: whether the S3 held-out run should wait until Part A is applied. I recommend it should.
