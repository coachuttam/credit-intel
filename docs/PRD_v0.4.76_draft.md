# PRD v0.4.76 — draft (a factual correction to v0.4.75); approved by the owner on 2026-11-05 and applied to `docs/PRD.md`, with one clarification added at the owner's instruction: the memo's fixed sentence about a row not recognised is shown only when at least one field has that reason

While building v0.4.75 I found that two sentences I wrote in it are wrong about what the code does today, and the code is right. This is a correction of my own wording, not a change of behaviour. On your word I apply it as written, run the suite and commit.

## The error
v0.4.75 says, in H.2, that "A `not_found` record that exists for another reason (a derived value whose input is `not_found`, H.5) keeps `status_reason` null", and in the H.1 row of `status_reason` that "a derived `not_found` and a `conflicting` field may omit it". In the code and in the reviewed golden file (`results_golden.json`), a derived `not_found` (for instance `ebit` and `total_borrowings` when their inputs are `not_found`) carries the reason **`missing_input`** (H.5; examples 14, 16, 42). It has done so since Phase 3; v0.4.75 neither changes it nor should.

## The two edits
- **H.2:** replace "keeps `status_reason` null" with "keeps its own reason, `missing_input` (H.5)".
- **H.1, the `status_reason` row:** replace "a derived `not_found` and a `conflicting` field may omit it" with "a derived `not_found` carries `missing_input` (H.5); a `conflicting` field may omit it".

## Header, revision row
Version 0.4.75 → 0.4.76; Status: "**v0.4.76 (2026-11-05)** corrects two sentences of v0.4.75 about the reason of a derived `not_found`; it changes no behaviour and no requirement." Revision row 0.4.76: "**Status correction.** v0.4.75 said a derived `not_found` keeps `status_reason` null; it carries `missing_input` (H.5), as the code and the reviewed golden file have always had it. Two sentences corrected (H.1, H.2). **Not changed:** any behaviour, status or requirement. **Found while building v0.4.75; my error in the draft.**"
