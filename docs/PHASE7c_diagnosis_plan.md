# Diagnosing the generalisation gap, on tuning documents only: scope proposal for the owner's decision

Dated 2026-11-05. **Approved by the owner on 2026-11-05 (decisions in section 6).** Nothing here is started beyond what section 6 lists, no PRD text is proposed, and no document other than the tuning set (R1, R2, S1, S2, S3) is to be touched. H1 to H6 stay closed.

## 1. What is known and what is not

Known (counts only): held-out run `H-20261104T182619Z` matched 0 of 12 values; no value was wrong; every failure was a refusal or a field the model did not return. H5: `label_not_recognised` (profit before tax), `period_mismatch` (interest expense), `no_record` (borrowings). H6: `basis_unknown` and `not_found` (profit before tax), `not_found` (interest), `missing_input` (borrowings). One model call each; H6's reply was short (465 tokens out).

Not known: why. The two documents were not opened. Treat the reasons as hints, as you said, and as such they point at several different places in the pipeline, not one:

| Reason | What it means in the code | Where a cause could sit |
|---|---|---|
| `label_not_recognised` | the row label printed on the page does not equal a configured phrase for the field (`extraction/labels.py`, FR-005.10: an exact match after normalisation against a closed list) | the phrase list, which was built from the tuning documents; a vocabulary the list lacks |
| `period_mismatch` | the value's column was not verified as the period it was claimed for | the period-column check; layouts unlike R1 and R2 |
| `basis_unknown` | the statement's basis could not be established | titles that name no basis; the assertion not given or not applied to the page |
| `not_found` (x3, H6) | the model returned nothing for the field | the model's reading of the pages it was sent, or the pages sent did not hold the lines |
| `missing_input`, `no_record` | a derived total had no components or no record | a consequence of the above for the borrowings family, not an independent cause |

There are therefore at least four candidate causes, and a fifth that cannot be excluded now: **a setup error**. The page ranges and basis assertions of H5 and H6 were written by hand before the one shot, and nothing could test them. An unlucky page range looks identical to a pipeline fault in these counts (H6's two far-apart pages, `184,267`, and its small reply make this worth stating). I do not know whether it happened; only opening the documents could say, and that is closed.

## 2. The central problem: the tuning documents have no failures to study

On R1 and R2 the pipeline scores 36/36, so there is nothing on them to diagnose directly. The causes above can only be studied if failures can be produced on documents that are free to inspect. The ways to get them, in the order I would use them:

1. **Offline analysis of what is fitted (no spend).** For each closed list the checks use (row labels, period-header forms, basis phrases, borrowings phrases), list which phrases came from which tuning document (the AC-E-7 provenance records), and count how many of the 36 matches rest on a phrase whose only source is that same document. That is a direct measure of how far the lists are fitted to R1 and R2.
2. **Controlled variants of R1 and R2 (small spend, from the cache or a few sends).** Same pages, altered conditions: run without `pages` (locator end to end), the other basis, other statement pages and periods in the 369-page R1, and the same fields read from the notes. These use real layouts and show which checks fail first.
3. **Synthetic stress documents (no spend on the model for most).** Generated with reportlab from known values, each isolating one check: label vocabulary outside the list, period headers in other forms, comparative column first, titles naming no basis, a statement split across far-apart pages, wrapped labels, a notes column. Limit: they test what I can imagine, so they confirm known gaps and cannot discover unknown ones.
4. **More tuning documents (owner's choice; spend; labelling).** The only route to failures I did not imagine. Public reports chosen for differences in layout and vocabulary, labelled in full, used freely for diagnosis and fixes. They are not held-out. Any claim about unseen documents then needs a new held-out set, later.

I recommend 1, 3 and 2 first and a decision on 4 afterwards, with the result of 1 and 2 in hand.

## 3. What I would change in the labels and the scorer (offline, synthetic tests, mutation checks, as for the scorer)

- **S-1 Stage attribution.** For every non-matching entry the scorer should say where it died, using only data the run already holds: never proposed by the model; proposed and refused (with the check and the reason); proposed under the other basis; proposed with no usable period; derived without inputs. Counts and enum names only. This turns "12 missing" into a distribution over stages.
- **S-2 Features in the labels.** An optional `features` object in each private labels file (owner-set tags, no names): statements on one page or split, title names the basis, period header style, scale in heading or column, notes column, currency, label vocabulary class. The scorer then reports counts grouped by feature, which is the only way to see which layouts fail once there are more than two documents.
- **S-3 The printed row label in the labels.** An optional `row_label` per present entry (private file), so the scorer can report, as a boolean count, whether the printed label is on the configured list for the field. Nothing printed from the label.
- **S-4 A reference self-check (for any future held-out set; not for H5 or H6).** An offline, model-free check that each labelled printed value occurs on its labelled page in the text layer and that the page range holds them, returning booleans only. It would have caught a setup error before the one shot. I should have proposed it when the references were written.
- **S-5 A provenance table for the phrase lists** (the input of step 1 above), checked by a test so it cannot drift.
- **Unchanged:** counts-only output; tuning documents only; held-out refusal; labels kept in `private/`.

## 4. A tension in the rule that you should decide

O.2 says held-out results are never used to change prompts, label or phrase lists, locator settings or thresholds. The diagnosis is directed in part by the reason codes of a held-out run. H5 and H6 are spent, so they cannot be contaminated further, and a future held-out set will be different documents. But the PRD rule is stated without that exception. My proposal: the plan records that the reasons of run `H-20261104T182619Z` are used **only to choose what to investigate**; every change must be justified by evidence from tuning documents alone; no change is made on the strength of a held-out reason alone; and the report of any later held-out round states that its fixes followed a failed held-out round. If you read the rule as barring even that, say so and the plan changes to a diagnosis that ignores the codes.

## 5. Scope, order and limits

1. Step 1 of section 2 and S-5, S-1 (offline, no spend).
2. S-2 and S-3 (needs you to add tags and row labels to R1 and R2 labels), then re-score the baseline with the new breakdowns.
3. Synthetic stress documents for each stage that S-1 and step 1 flag (offline).
4. Controlled variants of R1 and R2 (live sends only with your approval, each one; the OD-44 cap of USD 0.50 for 7b is not extended by this proposal, so a cap for the new phase is a decision for you).
5. A findings report: which causes, how many entries each explains, and proposed fixes, **none applied without your approval**, each with a test and a mutation check, and each judged against the tuning regression bar (36/36, 12/12, 34/34, 34/34).
6. A decision for you on sourcing more tuning documents (step 4 of section 2) and, separately and later, on a new held-out set.

Out of scope: opening H1 to H6; any change to a prompt, list or setting during diagnosis; any claim of improvement before a held-out round on new documents; scan and OCR work (OD-46), although S3 is now a tuning scan and available whenever that becomes its own piece of work.

## 6. The owner's decisions (2026-11-05)
1. **Scope and order approved as written, including S-4.** Start with the offline work (S-5, S-1, S-4) on synthetic data, with tests and mutation checks; nothing applied without the owner's approval.
2. **O.2 reading adopted (the middle ground).** The held-out reason codes of run `H-20261104T182619Z` decide only where to look. Every actual fix is justified from tuning evidence alone; no change is made on a held-out reason alone. **Wording for any future held-out report (to be used verbatim):** "The pipeline was changed after a failed held-out round (run H-20261104T182619Z, 0 of 12). The reasons printed by that round were used to decide where to investigate; each change was justified from tuning-document evidence alone. This round's documents were not used in any of that work."
3. **Spend cap for this phase: USD 1.00.** Every send needs the owner's approval and is run in the owner's terminal. (The 7b cap of USD 0.50 is not extended; the 7b total was not summed, and the held-out run's known cost is USD 0.0021.) A PRD decision row for this cap and for the phase follows when the owner adds the phase to Section Q.
4. **S-2 and S-3 tagging.** I extend the scorer and the blank skeletons first, offline, so that `features` and `row_label` are accepted and checked. Then the assistant the owner relays through fills in the `features` and `row_label` fields of the private label files of R1 and R2 from the B-133 observation logs it already used to build those files (same source, same documents, already authorised work) and runs `--check-labels`. I do not read or edit those private files.

## 7. Evidence gathered so far (tuning documents only; counts; filed for the "more tuning documents" decision, not a reason to act yet)

- **The feature tags are confounded (2026-11-05, S-2).** With two documents, R1 and R2 differ on nearly every tag (notes column, period header style, title naming the basis, reporting framework) and share only split statement pages and a scale declared in the heading. A feature breakdown of two documents cannot separate one cause from another, which is evidence for step 4 of section 2 (more tuning documents, chosen for differences).
- **How far the tuning matches rest on phrases taken from the same document (2026-11-05, S-5).** Of the 79 closed phrases the locator, the row-label check and the borrowings classification accept, 50 are the PRD's initial values, 22 were added from a tuning document (R1 or R2), 2 are recorded as added but not supported by the log, 3 are unverified, and 2 are defined by a rule. Of the 34 tuning matches that carry a printed row label, **18 rest on a phrase added from the same document (R2: 16 of 20; R1: 2 of 14) and 16 on the PRD's initial phrases**; none rests on an unverified phrase. Those additions were made because the pipeline failed on that document first, so this is the expected shape of tuning, and it shows plainly that the tuning score of R2 is largely a fit. It does not say that vocabulary caused the held-out misses; that is for the next steps. The PRD's initial phrases carry no record of which document informed them.
- **Not covered by the provenance record:** the expense-table headings, the section headings, the currency and scale tokens and the period-header forms (other closed lists), and the 6 borrowings-part rows (not row-labelled).

## 8. Decision on the setup check and an unused held-out document (owner, 2026-11-05)

**Decided: the setup check (S-4, `credit_intel.evaluation.setupcheck`) may be run on a held-out document that no round has used, before its one shot.** Recorded here so that it stands for any future held-out document and does not rest on a conversation.

**The owner's reasoning (verbatim in substance):** S-4 is a structural check against the reference file's own claims: the SHA-256, the page range, an exact-text match, and what the basis gate drops. It never calls the model and never surfaces a gate field value (profit before tax, interest expense, total borrowings). It validates what the person who wrote the reference already wrote, not the document's content beyond that. That is different from inspecting a held-out document for O.2 purposes, which is about not letting anyone who tunes the system see the answer before or during tuning. Running S-4 exposes no answer to anyone; it catches a setup error (a bad page range, a basis-gate drop) before the one shot is spent on it.

**What was built to carry it out (offline, tested):**
- The check may read a document that is a tuning document, or a held-out document that is **not in the held-out ledger**. A held-out document that a round has used stays closed, a document not on the assignment record is refused, and an unreadable record or ledger refuses everything (fail closed).
- Its report carries `set` and, for a held-out document, `pre_run_setup_check: true`. It holds only booleans and counts: no value, label, page text, path or hash. It prints no gate field value, which a test checks on a held-out document.
- The dry run keeps refusing a held-out document by default. The setup check is the only caller of the one new parameter (`allow_unused_held_out`) that skips that refusal, after its own guard has shown the document unused; the dry run's command line cannot set it.
- Not recorded by the tool: a held-out run's freeze covers `tests/eval`, so the tool writes no ledger or log of its own, and a setup check leaves the tree as it found it.

**A correction to the framing:** the owner wrote "whenever H3 or a future held-out document gets used". H3 is **already used** in the ledger (a `started` and a `completed` line for run `H-20261026T092850Z`: it stopped on the then-25 MB limit before any page was read, but its one shot was recorded). Under v0.4.42 a used document is neither required nor allowed, so the setup check refuses H3 like H1, H2, H4, H5 and H6. The owner then decided the same day to reclassify H3 as unused; see section 9.

**What this does not change:** the held-out tool itself, the one-shot rule, O.2's bar on using held-out answers for tuning, or the closure of H1 to H6. PRD wording (the sentence in O.2 that lists the tools that refuse a held-out document) needs a version bump to match; it is drafted in `docs/PRD_v0.4.72_draft.md` for the owner's approval.

## 9. H3 reclassified as unused (owner, 2026-11-05)

**Decided: H3 is reclassified as unused.** H3 was reclassified because its earlier attempt never read a page and never called the model, so that attempt could not have exposed any information about the document. The owner's reasoning: the run stopped before any page was read, with zero model calls and zero information extracted; that is an infrastructure failure, not an evaluation attempt, and treating the shot as spent wastes a document for no reason tied to testing the pipeline.

**What I checked (not taken on trust):** the ledger shows H3's `started` and `completed` lines one second apart (09:28:50 and 09:28:51 UTC on 2026-10-26); `PROGRESS.md` records that run `H-20261026T092850Z` stopped H3 with `E-INPUT-TOO-LARGE` and that H3 "was never read"; that error is raised in the `validated` stage (`ingestion/validation.py`), before any page is parsed and before extraction, so no model call is possible after it. I did not open the held-out report file or the document.

**How it is recorded:** an explicit, append-only ledger line, `event: "released"`, in `tests/eval/heldout_runs.jsonl`, with an eighth member `reason` that states the above in the line itself. It reverses the owner's decision of 2026-10-26 ("H3 stays recorded as held out with its shot used"), and the line says so. The ledger tool (`credit_intel.evaluation.ledger`) treats a document as used from a `started` or `completed` line until a later `released` line; a release is valid only for a document currently used, by the run that used it, with a stated reason; a later `started` line uses the document again. Nothing is edited or removed. The `at` of the line is the machine's UTC time (2026-11-04 20:06 UTC, which is 2026-11-05 01:36 in the owner's time zone).

**What follows from it (read this before relying on H3):**
- **The next held-out run must cover H3 and nothing else.** The held-out run tool runs over exactly the held-out documents that are unused, and H3 is now the only one (H1, H2, H4, H5, H6 are used). It needs a reference file for H3 (the owner's, with `pages` and `assert_basis` if needed) and a new freeze commit.
- **H3 cannot be run today.** `PROGRESS.md` records it as about 107 MB, above the current 100 MB input limit (FR-001.2). Run as it stands, the held-out tool would stop it at the same place and use the shot again. The ways out are the owner's: raise the limit (a pipeline setting changed because of a held-out document, to be recorded as such), run it through a smaller copy (a different file, hence a different SHA-256 and a new assignment), or leave H3 unused. The setup check (S-4), now allowed on an unused held-out document, would report the stop (`basis_gate_error` / a stopped run) before the shot is spent; the owner can run it with a reference once one exists.
- **What was learned from H3's attempt:** its size, and the input limits were raised because of that stop (v0.4.43, decided openly at the time). No content was learned.

The PRD wording of the ledger (the `event` values, the `reason` member, the meaning of `already_used`, and this release) is drafted in `docs/PRD_v0.4.73_draft.md` for the owner's approval; it is not applied.
