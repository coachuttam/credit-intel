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
