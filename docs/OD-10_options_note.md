# OD-10 options note — a statement whose title names no basis

| Item | Value |
|---|---|
| Status | **For the project owner's decision. Nothing here is approved or applied.** `docs/PRD.md` v0.4.20 is unchanged: such a statement stays `unknown` (H.4.6) and its fields are `requires_review` (`basis_unknown`). |
| Drafted | 2026-10-20 |
| Sources | `docs/PRD.md` (H.4.6, Appendix A.2, the OD-10 row); `docs/PRD_v0.4_proposal.md` §3.7 (options c and b′, accepted in principle on 2026-10-13, not applied in v0.4); the G5 runs on tuning documents R1 and R2 (`PROGRESS.md`, counts only). |

## 1. What the tuning runs showed

| | R1 (Infosys, 369 pp.) | R2 (Microsoft, 80 pp.) |
|---|---|---|
| Titles that name a basis | consolidated pages 274–277 | none |
| Titles that name no basis | standalone pages 194–197 | pages 36 and 38 |
| Configured basis | consolidated | consolidated |
| Result | The basis gate passed. All 12 proposals the model made came from pages 194–196, so every field was `basis_unknown` | The basis gate failed: `E-EXTRACT-BASIS-UNAVAILABLE` ("bases found: unknown"). Nothing was sent |

Two consequences matter for the choice:

1. **The two documents point in opposite directions.** R1's untitled pages are the *standalone* statements of a group that also reports consolidated ones. R2's untitled pages are a group's only statements (the owner can confirm which basis they are; I have not read the document). So any automatic rule for "no basis word" is wrong on one of them.
2. **For R1 under the configured basis `consolidated`, resolving the standalone pages' basis would not produce a single extracted field.** They would become `standalone`, which is not the configured basis, and be ignored. What would produce fields on R1 is the model using the consolidated pages 274–277, or a run configured for `standalone`.

## 2. Options

### Option 1 — keep the specification as it is (PRD option a)
A no-title statement stays `unknown`.
- R1: no change. R1 standalone cannot be analysed at all; R1 consolidated is analysable only if the model uses pages 274–277.
- R2: stops at the gate. Companies whose titles never name a basis are unprocessable (the PRD's own stated consequence).
- Risk: none added. Cost: coverage.

### Option 2 — basis from a footnote (proposal option c)
A configured footnote phrase on a page of the run ("integral part of the standalone financial statements" or the consolidated equivalent), quoted as evidence, establishes the run's basis; a title naming a different basis in the same run makes it `unknown`. Exact, normalised, single-line matching, as the proposal words it.
- R1: the standalone run's basis becomes `standalone` from the document's own words (the proposal records that pages 195 and 197 carry the footnote). Under `consolidated` those fields are ignored; under `--basis standalone` they become extractable.
- R2: no footnote, so no change.
- Risk: low. The basis is still evidence, quoted and verifiable. Needs the phrase list and the matching tests of the proposal.

### Option 3 — analyst assertion for given pages (proposal option b′)
`--assert-basis BASIS` together with `--pages`: pages in that range with no basis evidence are treated as BASIS; it never overrides a page that names another basis (that stops the run with `E-EXTRACT-BASIS-UNAVAILABLE`); the manifest, each affected field (`basis_evidence = analyst_assertion`) and the memo header all disclose it.
- R1: not needed.
- R2: makes it analysable, for example `--pages 36-38 --assert-basis consolidated`, with the assertion disclosed.
- Risk: a wrong assertion mislabels figures, but it is explicit, page-scoped, recorded and visible to the reader, never automatic. It needs a CLI flag (FR-014, Phase 5), so it cannot be used for G5 until then.

### Option 4 — treat a no-title statement as the configured basis, or as standalone, automatically
**Not recommended; shown because the evidence rules it out.** Treating it as the configured basis (`consolidated`) would take R1's standalone pages 194–197 as consolidated, which is the worst failure the platform has: two bases mixed under one label. Treating it as standalone (the PRD's option b without the flag) mislabels R2. Missing wording never implies a basis.

### Option 5 — do not send pages whose basis is unknown (new; not in the proposal)
Not an answer to OD-10 itself but the thing that would unblock R1 now. When the gate passes because other candidate pages establish the configured basis, pages whose title names no basis would be excluded from the pages sent to the model, using the locator's existing record of excluded pages (`excluded_candidates`, today only for the cap and chain rules; pages that name the *other* basis are still sent and only their fields are ignored afterwards, which this option would leave as it is). On R1 the model would see only 274–277, titled consolidated, which is the configured basis.
- R1: the next run would be about the consolidated statements. The cost of a small run was $0.0015, so a re-run costs similar and needs your approvals again.
- R2: unaffected (the gate fails first).
- Risk: it fails safe. A statement that really is the configured basis but is untitled is not read, so fewer fields appear, never wrong ones. It changes FR-013 and the locator, so it is a specification decision and would be written up like v0.4.20.
- Interaction: with Option 2, a footnote-established standalone run would be excluded under `consolidated` and kept under `standalone`, which is consistent.

## 3. Recommendation

- **Adopt Options 2 and 3** (the owner's accepted-in-principle choice of 2026-10-13: "c together with b′"), applied in a later phase when the CLI exists. Neither is needed to move R1 now.
- **Decide Option 5 now**, since it is what gets R1 to extracted fields in the next tuning run, and it only narrows what is sent.
- **Reject Option 4** in writing, with the R1 and R2 evidence above.
- Leave R2 as the recorded finding until Option 3 exists: it is the right outcome for a document the specification cannot yet read.

## 4. Decisions needed

1. Option 1, 2, 3 and 5: adopt, change, or reject each. Option 4: confirm rejection.
2. Whether I draft the PRD wording (v0.4.21) for the options adopted, as for v0.4.20, with examples and tests.
3. Whether R2's basis can be confirmed by you (consolidated or not), for the record.
