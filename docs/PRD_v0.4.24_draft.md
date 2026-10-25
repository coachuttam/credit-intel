# PRD v0.4.24 — draft amendment: the page-scoped analyst assertion of the statement basis (OD-10, option 3)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("yes to all four") and applied to `docs/PRD.md` as v0.4.24.** Kept as the record of the reasoning. The owner adopted the wording, the three readings in section 8 (a to c) as drafted, the recording of the send rule, and the application as v0.4.24. |
| Drafted | 2026-10-25 |
| Owner decision this rests on | "option 3" (2026-10-25), from `docs/OD-10_options_note.md` and `docs/gate_round_guide.md` section 6 (a): build the page-scoped analyst assertion, accepted in principle on 2026-10-13 ("c together with b′") and again for Phase 5 in v0.4.21. |
| Changes | H.4.6 (new bullet block), FR-014 criterion 8 and SEC-10 (the command line's send rule and the `--confirm-public-document` flag, added at decision 3), H.1 (new field attribute `basis_evidence`), H.1.2 (the `statement_basis` attribute), FR-014 criterion 1 (new flag), G.1 (the `E-EXTRACT-BASIS-UNAVAILABLE` row), FR-010 and FR-012.1 (what is recorded), K.0 and sections 1 to 5 of the memo (disclosure), Appendix A.3 (OD-10 row), Appendix B.6 (examples), Revision History. No other requirement. |
| Not in this amendment | **Option 2 (basis from a footnote)** stays accepted in principle and unspecified. Options 1 and 5 are as decided in v0.4.21. Option 4 (an automatic basis for a no-title statement) stays rejected. |
| Blocks | The gate round for tuning document R2 (`docs/gate_round_guide.md`). R1 is not affected. |

## 1. Why

A statement whose title block names no basis has the basis `unknown` (H.4.6). If no candidate page names the configured basis, the run stops at the basis gate with `E-EXTRACT-BASIS-UNAVAILABLE` before any model call; if some do, the unknown pages are not sent (v0.4.21, except for a `--pages` run). Tuning document R2 (the owner confirmed it is consolidated) has titles that name no basis anywhere, so it extracts nothing, and the owner's gate (all three gate fields on both tuning reports) cannot be met. The owner chose to let the analyst state the basis, for named pages, in a way that is explicit, recorded and visible.

Two things this amendment settles that the 2026-10-13 text did not:

1. **The document-level `statement_basis` attribute.** Today a field cannot be `extracted` unless the document-level attribute `statement_basis` is `extracted` (H.1.2), and that attribute is verified only against a title block. For a document like R2 it can never verify, so an assertion that changed only the basis of pages would still leave every field `requires_review` (`basis_unknown`). The amendment says how the assertion satisfies the attribute.
2. **Which evidence wins.** The assertion fills a gap; it never replaces a page's own evidence.

## 2. Current text (v0.4.23)

**H.4.6 (the last bullets under "Which basis a run uses" and "Configured basis absent"):** the basis comes only from title blocks (and, for a page with no title line, from the first page of its statement run). "Treating a statement with no basis wording as standalone remains open decision OD-10". A `--pages` run removes no page, and a field read from an unknown-basis page is `requires_review` (`basis_unknown`). "**Still open under OD-10:** the footnote evidence and the page-scoped analyst assertion (the owner accepted both for Phase 5) are not specified here."

**H.1.2:** `statement_basis` — `consolidated` / `standalone` / `unknown` — "Statement title phrase (H.4.6)". "A field may not be `extracted` if a document-level attribute it depends on (its period end, basis, currency, or scale) is not `extracted`."

**G.1:** `E-EXTRACT-BASIS-UNAVAILABLE` — "The configured statement basis is not present; the message lists the bases found" — exit 4.

**FR-014 criterion 1:** `credit-intel <pdf_path> [--pages RANGE] [--basis consolidated|standalone] [--profile PROFILE_JSON] [--output-dir DIR] [--config SETTINGS_TOML]`.

## 3. Proposed wording

### H.4.6 — replace the sentence "Treating a statement with no basis wording as standalone remains open decision OD-10, unchanged by v0.4." and the bullet "Still open under OD-10"

> - **An analyst assertion of the basis (v0.4.24; OD-10 option 3).** The analyst may state the basis of the pages of a `--pages` run with `--assert-basis consolidated|standalone`.
>   - **Scope.** The flag is valid only together with `--pages`; without it the command is a usage error (exit code 2) and nothing runs. The assertion applies to the pages of that range and to no others. `--basis` alone keeps its meaning (which basis to analyse) and never asserts one.
>   - **It fills a gap; it never overrides evidence.** For each page of the range, its basis is first decided by the rules above (its own title block, or for a page with no title line the first page of its statement run). The assertion then applies to exactly those pages whose basis is `unknown`: their basis becomes the asserted basis, with `basis_evidence = analyst_assertion`. A page whose basis comes from a title block, directly or by the run it continues, keeps it, with `basis_evidence = title`.
>   - **A conflict stops the run.** If any page of the range has a basis, by those rules, that is the other basis than the one asserted, the run stops **before any model call** with `E-EXTRACT-BASIS-UNAVAILABLE`, naming the page numbers. A conflict is never resolved in favour of the assertion.
>   - **The basis gate counts asserted pages.** The check that the configured basis is present (above) counts a page whose basis was asserted as a page of the asserted basis. An assertion of the other basis than the configured one therefore changes nothing about the gate: with no page of the configured basis the run stops as before, and its message lists the bases found with the asserted one marked.
>   - **The model is not told.** The assertion is not part of the model's input and not part of the response-cache key. A cached reply is reused whatever is asserted; only the verification changes.
>   - **It does not make a figure true.** A field read from an asserted page is verified by every other check (FR-005) and is `extracted` if they pass. It carries `basis_evidence = analyst_assertion`, and the run discloses the assertion (below). `[ANALYST-PROVIDED]` labelling applies to the statement of the basis, never to the figure.
> - **The `statement_basis` attribute under an assertion (H.1.2).** If the assertion was applied to at least one page and the asserted basis is the configured basis, the attribute `statement_basis` is `extracted` with that basis, `basis_evidence = analyst_assertion`, no page and no quote, whatever the model proposed for it; a model proposal is neither needed nor used. Otherwise the attribute is verified as before, and `basis_evidence = title`. When the attribute is verified from a title block of the configured basis, the assertion changes nothing about it.
> - **A derived value** takes `basis_evidence = analyst_assertion` if any of its inputs has it, otherwise `title`.
> - **Still open under OD-10:** footnote evidence (option 2) is accepted for a later phase and is not specified here; an automatic basis for a no-title statement is rejected.

### H.1 — new field attribute (after `statement_basis`)

> | `basis_evidence` | enum | Always | How the basis was established: `title` (a title block of its own page, or of the first page of its statement run) or `analyst_assertion` (v0.4.24). For a field of `unknown` basis it is `title`, there being no evidence. |

### H.1.2 — the `statement_basis` row

> | `statement_basis` | `consolidated` / `standalone` / `unknown` | Statement title phrase (H.4.6), or, under an analyst assertion, the assertion (H.4.6). Its record carries `basis_evidence`. |

### FR-014 criterion 1 — the command

> `credit-intel <pdf_path> [--pages RANGE] [--basis consolidated|standalone] [--assert-basis consolidated|standalone] [--profile PROFILE_JSON] [--output-dir DIR] [--config SETTINGS_TOML]`
>   - **Assert basis:** `--assert-basis` states the basis of the pages of `--pages` that have none (H.4.6). It requires `--pages`.

### G.1 — the `E-EXTRACT-BASIS-UNAVAILABLE` row

> Meaning: "The configured statement basis is not present, counting pages whose basis the analyst asserted (the message lists the bases found), **or** a page's title names the other basis than the one asserted (the message names the pages)."  What the user should do: "Review the document; to analyse another basis, re-run with `--basis`; correct or remove `--assert-basis`."  Exit code and the other columns unchanged.

### FR-010.1 and FR-012.1 — what is recorded

> - `results.json` records, under `extraction`, `basis_assertion`: `null`, or `{"basis", "pages", "applied_pages"}` (the pages of the range, and the pages the assertion was applied to, possibly none), and every field and the `statement_basis` attribute record `basis_evidence`. It holds no timestamp.
> - `manifest.json` records the same `basis_assertion` object (FR-012.1).

### K.0 and K.1 to K.5 — disclosure in the memo

> - **Header:** when `--assert-basis` was given, after the draft statement: "**Basis asserted by the analyst** for pages … ({basis}); not established by the document." `[ANALYST-PROVIDED]`. If the assertion was applied to no page: "An analyst assertion of the basis was given for pages … and was not needed." `[ANALYST-PROVIDED]`.
> - **Section 1 (Borrower overview):** the line "Statement basis used" is followed by the same sentence when the assertion was applied.
> - **Section 2 (Documents reviewed):** lists the asserted pages and the pages it was applied to.
> - **Section 3 (Financial performance):** the notes of a field with `basis_evidence = analyst_assertion` say "basis asserted by the analyst".
> - **Sections 4 and 5 (Financial ratios, Potential risk indicators):** a sentence under the heading, when any input field of the run has `basis_evidence = analyst_assertion`: "These figures rest on a statement basis that was asserted by the analyst, not established by the document." `[ANALYST-PROVIDED]`.
> - The traceability rule (K.10) is unchanged: the sentence is labelled `[ANALYST-PROVIDED]` and resolves to `extraction.basis_assertion` in `results.json`.

### Appendix A.3 — the OD-10 row

> Partly decided (v0.4.21, v0.4.24). A statement whose title names no basis stays `unknown`. When the gate passes, pages of unknown basis are not sent, except in a `--pages` run (v0.4.21). The page-scoped analyst assertion (`--assert-basis`) is specified in v0.4.24. Footnote evidence is accepted for a later phase and not yet specified. An automatic basis for a no-title statement is rejected.

### FR-014 criterion 8 and SEC-10 — the send rule (added at decision 3)

> Criterion 1 lists `[--confirm-public-document]`. Criterion 8, **Sending a document to the hosted API (SEC-10)**: when the configured provider sends data off the machine, a document recorded as held out (O.2) is never sent, whatever the options; a document recorded as tuning is sent; a document not on the assignment record, or any document when there is no record file, is sent only with `--confirm-public-document`; a record file that exists but cannot be read refuses every document; a refusal exits with code 2 before any provider is built or any file is written, and its message names the neutral document ID for a held-out document and never the hash or a path; a notice is printed to standard error whenever pages may be sent. The rule does not apply to a provider that sends nothing off the machine. A refusal is not a catalogued failure; a catalogue code for it is a later decision. SEC-10 gains: "The command line enforces this with the send rule of FR-014 criterion 8." Examples 54 and 55 are added to Appendix B.6. This records what step 5k implemented; nothing changes in the code.

## 4. Effects

- **R2 becomes analysable**, for example with `--pages 36-38 --assert-basis consolidated`. Its fields can be `extracted`, carry `basis_evidence = analyst_assertion`, and are disclosed everywhere they are used.
- **R1 is not affected.** Its titled pages keep `basis_evidence = title`. An assertion on a run whose pages all name the basis is recorded as not needed.
- **No automatic behaviour is added.** Nothing is asserted unless the analyst passes the flag with a page range. Missing wording never implies a basis (Option 4 stays rejected).
- **No new error code.** A conflict uses `E-EXTRACT-BASIS-UNAVAILABLE`, a missing `--pages` is a usage error (exit 2).
- **The response cache and the model input are unchanged,** so a cached reply can be replayed under a different assertion. This is what lets the gate round replay R2 without a new model call.
- **Code affected when approved:**
  - `cli.py` (the flag and its check), `run.py` and `extraction/pipeline.py` (the option passed through);
  - `extraction/bases.py` (`field_basis` returns the evidence with the basis) and `extraction/verify.py` (a field's `basis_evidence`);
  - `extraction/attributes.py` (the `statement_basis` attribute under an assertion);
  - `ingestion/locator.py` (`check_statement_basis` counts asserted pages);
  - `models.py` (`basis_evidence` on a field and a derived value);
  - `export/results.py`, `export/manifest.py`, `memo/sections.py` (record and disclose);
  - `evaluation/gate.py`, `docs/gate_round_guide.md` and the tuning runner (an optional `pages` and `assert_basis` in the reference, so the replay uses the same pages as the live run);
  - `README.md` and the README test (the new flag).
- **Also noticed, not part of option 3:** the command line has one flag the PRD's FR-014 does not list, `--confirm-public-document`, and a send rule that is recorded only in `README.md` and `PROGRESS.md` (step 5k, applied as proposed). See decision 3.

## 5. New acceptance examples (Appendix B.6, added as 45 to 53; 54 and 55 record the send rule)

| # | Case | Expected |
|---|---|---|
| 45 | Configured `consolidated`; `--pages 36-38 --assert-basis consolidated`; the three pages are statements whose titles name no basis | The gate passes (asserted pages count). The pages are sent. The `statement_basis` attribute is `extracted` by assertion. A field that passes every other check is `extracted` with `basis_evidence = analyst_assertion`; the memo header and sections 1 to 5 disclose it |
| 46 | `--assert-basis consolidated` without `--pages` | Usage error, exit code 2; nothing runs and nothing is written |
| 47 | `--pages 10-12 --assert-basis consolidated`; page 11 is titled "Standalone Balance Sheet" | The run stops before any model call: `E-EXTRACT-BASIS-UNAVAILABLE`, naming page 11 |
| 48 | `--pages 10-12 --assert-basis consolidated`; page 10 titled "Consolidated …", page 11 a continuation of it with no title, page 12 the start of a new statement with no title | Pages 10 and 11 keep `basis_evidence = title`; page 12 takes the asserted basis with `basis_evidence = analyst_assertion` |
| 49 | Configured `consolidated`; `--pages 36-38 --assert-basis standalone`; pages untitled | The gate stops the run: `E-EXTRACT-BASIS-UNAVAILABLE`, bases found: standalone (asserted); to analyse it, the analyst re-runs with `--basis standalone` |
| 50 | `--pages 274-277 --assert-basis consolidated`; all four pages are titled consolidated | The assertion is recorded with `applied_pages` empty; every field has `basis_evidence = title`; the memo header says the assertion was not needed |
| 51 | As example 45, and the model proposed a `statement_basis` attribute `consolidated` with a quote that is not in any title block | The attribute is `extracted` by the assertion; the proposal is not used |
| 52 | A document run once with `--assert-basis consolidated`, then with the same pages and no assertion | The second run reuses the cached reply (no model call); its fields are `requires_review` (`basis_unknown`), because nothing asserts the basis |
| 53 | As example 45; EBIT is derived from asserted-basis profit before tax and interest expense | The derived record has `basis_evidence = analyst_assertion`; its memo row is noted |

## 6. Tests, when approved

One test per example 45 to 53, run through the command line with the fake provider; unit tests for the flag (valid values, `--pages` required, a basis other than the two refused), for `field_basis` and the attribute under every combination of title, continuation and assertion, and for the conflict rule at the edges (one conflicting page among many, a title naming both bases, a continuation inheriting the other basis); a check that the assertion is not in the cache key and not in the request; the recorded `basis_assertion` and `basis_evidence` in `results.json` and `manifest.json`, with the golden files updated and the reproducibility tests still byte-identical; the memo disclosure in the header and sections 1 to 5, with the traceability checker; the catalogue test for the changed G.1 row; the README test for the flag; and mutation checks on each rule above.

## 7. Revision History row (draft)

| 0.4.24 | (date of approval) | **Specification change to H.4.6, H.1, H.1.2, FR-014 criterion 1, G.1, FR-010.1, FR-012.1 and memo sections K.0 and 1 to 5, authorised by the project owner on (date)** ("option 3", 2026-10-25; resolves OD-10 in part). The analyst may state the basis of the pages of a `--pages` run with `--assert-basis`. The assertion fills only pages whose basis is `unknown`, never overrides a page whose own evidence names a basis (a conflict stops the run with `E-EXTRACT-BASIS-UNAVAILABLE`), counts toward the basis gate, satisfies the document-level `statement_basis` attribute when it asserts the configured basis, is not part of the model input or the cache key, and is disclosed in `results.json`, `manifest.json` and the memo. Fields gain `basis_evidence` (`title` or `analyst_assertion`). Footnote evidence remains accepted and unspecified; an automatic basis remains rejected. Appendix A.3 (OD-10 row) and Appendix B.6 examples 45 to 53 are updated or added. Nothing else changes. |

## 8. Decisions needed from the owner

1. Adopt the wording as drafted, change it, or reject it.
2. Three readings in it that I chose and you may want otherwise:
   - **(a)** the assertion applies to every page whose basis is `unknown`, which includes a title block that names **both** bases; the alternative is to leave such a page `unknown` because it is ambiguous, not unmarked (this needs a small change to how the locator reports the two cases);
   - **(b)** a conflict stops the whole run, rather than ignoring the conflicting page and continuing;
   - **(c)** the document-level attribute is satisfied by the assertion only when the asserted basis is the configured basis.
3. Whether the same amendment should also record `--confirm-public-document` and the send rule (the command line's rule for sending a document to the hosted API, step 5k) in FR-014 and SEC-10, which today are only in `README.md` and `PROGRESS.md`.
4. Whether I apply it to `docs/PRD.md` as v0.4.24 on your word, then implement it in separate small steps (the flag and the basis evidence first, then the attribute, the records and the memo).
