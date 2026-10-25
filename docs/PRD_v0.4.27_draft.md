# PRD v0.4.27 — draft amendment: attribute IDs, a catalogue code for send refusals, and a traceability check before export

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("adopt all, apply it as v0.4.27") and applied to `docs/PRD.md` as v0.4.27.** Kept as the record of the reasoning. The owner adopted all seven decisions as drafted. |
| Drafted | 2026-10-25 |
| Owner decision this rests on | "yes to all four" (2026-10-25), on the four optional questions of step 5i to 5k: (1) a CommonMark parser as a dev-only dependency, (2) attribute IDs in `results.json`, (3) a traceability check before export, (4) a catalogue code for send refusals. |
| Changes | H.1.2 (attribute IDs), K.10 and K.0 (how a document-level label resolves), FR-010 (criterion 2 wording; new criterion 5, the check before export), FR-011.2 (the check's failure is an internal error), FR-014 criterion 8 (the refusal is catalogued), G.1 (new row, `E-INPUT-SEND-REFUSED`), SEC-10, L.2 (one dev-only tool), Appendix B.6 (examples 56 to 61), Revision History. No other requirement. |
| Not in this amendment | Anything about the held-out set, the gate, or any new model behaviour. |
| Blocks | Nothing on the gate path. These are quality and safety steps, taken in the order S1 (this amendment), S2 (parser and round-trip test), S3 (the check before export). |

## 1. Why

1. **Attribute IDs.** K.10 says every label resolves to an ID in `results.json`. Fields, metrics, derived values, indicators and the top-level sections have IDs. The document-level attributes (entity name, the two period ends, basis, currency, scale) have none, so a `[SOURCE: p.N]` label in memo section 1 resolves only by page number, which is weaker than every other label.
2. **A catalogue code for send refusals.** A refusal to send a document to the hosted API (SEC-10) exits 2, the same as a bad argument, and is not in G.1. A script that runs the command cannot tell "you passed a wrong option" from "this document may not be sent" except by reading text. FR-014.3 says a catalogued failure prints its code and exits with the catalogue's exit code; a refusal is a failure with a defined cause and a defined remedy.
3. **A check before export.** The traceability rules of K.10 are checked by tests on synthetic memos. A real document could produce text or shapes the tests never saw. A memo that breaks K.10 must not reach an analyst as a trusted draft. Running the same check on every memo, before anything is written, turns a silent defect into a visible one.
4. **A parser.** The memo is checked today by this project's own structural rules. A real Markdown parser is the only independent proof that headings, tables, block quotes and escaped text render as intended. The PRD's "renders correctly as CommonMark: … tables" is also loose: tables are a GitHub-flavoured extension, not part of CommonMark.

## 2. Current text (v0.4.26)

- **H.1.2:** "Each record holds: `attribute`, `raw_text`, `normalised_value`, `page_number`, `evidence_quote`, `status` …, and `status_reason`."
- **K.10:** "Each one must carry a `[SOURCE]`, `[CALCULATED]`, `[RULE]`, or `[ANALYST-PROVIDED]` label that resolves to an ID in `results.json`. … Automated tests check that every label in a generated memo resolves to an existing ID."
- **FR-010.2:** "`memo.md` renders correctly as CommonMark: headings, tables, and block quotes for evidence."
- **FR-014 criterion 8:** "A refusal is not a catalogued failure (G.1); adding a catalogue code for it is a later decision", and a refusal "exits with code 2 before any provider is built or any file is written".
- **G.1:** seventeen codes; "Messages … may append only the file name or numeric limits".
- **L.2:** reportlab is the only dev-only tool listed besides pytest.

## 3. Proposed wording

### H.1.2 — attribute IDs

> Each record also holds an `id`, stable and unique within the file: `entity_name`, `period_end.current`, `period_end.comparative`, `statement_basis`, `reporting_currency`, `scale`. The memo and the traceability check (K.10) refer to an attribute by this ID.

### K.0 and K.10 — how a document-level label resolves

> A `[SOURCE: p.N]` label on a line of memo section 1, or on the **Borrower** line of the header, names the attribute that line shows. Section 1 prints that attribute's ID in a code span beside its value, and N must be the attribute's page in `results.json`. An attribute with no page (a basis asserted by the analyst, H.4.6) carries `[ANALYST-PROVIDED]` and the ID, and no `[SOURCE]` label. The line "Statement basis used" describes the run, not an attribute, and keeps its `[CALCULATED: extraction]` label.

### FR-010.2 — what "renders correctly" means

> `memo.md` renders correctly as CommonMark with GitHub-flavoured tables: headings, tables, and block quotes for evidence. A test parses every memo it generates and checks the parsed structure: the title and nine section headings in order, rectangular tables, no raw HTML and no link, and that text from a document, the analyst or the rules renders as the text it was (it cannot become a heading, a table cell, a link or an origin label).

### FR-010 — new criterion 5, the check before export

> 5. **Check before export.** After the memo is generated and before anything is written, the system checks it against the results it was made from, with the rules of K.10 applied to every label, ID and value:
>    - every origin label is one of the five forms, and every unescaped bracket is a label;
>    - every `[CALCULATED]`, `[RULE]` and `[SOURCE]` label names something in `results.json`, and a `[SOURCE: p.N]` names a page the field or attribute beside it was read on;
>    - every field, metric and rule ID written exists;
>    - a field or metric row is labelled `[UNVERIFIED]` exactly when the field is not `extracted`, and the value shown is the value held (as printed, in whole units, or rounded half to even);
>    - the headings, tables and code spans are well formed, and the disclosure sentences of K.0 appear exactly where K.0 requires them.
>
>    The check is deterministic and uses no model. If it finds a problem, the run **fails as an internal error** (FR-011.2): exit code 1, the message gives the run ID, and nothing but a manifest-only failure record is written (state `failed`, stage `memo_generated`, no error code). The message and the INFO log give the **number** of problems and never their text.

### FR-011.2 — one clause

> A memo that fails the check of FR-010 criterion 5 is such a failure: it indicates a defect in the template or in the data, not a user error, so it has no catalogue code.

### FR-014 criterion 8 — the refusal is catalogued

> Replace the sentence "A refusal is not a catalogued failure (G.1); adding a catalogue code for it is a later decision." and the exit code of the refusal bullet with: "A refusal is the catalogued failure `E-INPUT-SEND-REFUSED`: it exits with code 3 **before any provider is built or any file is written**, and, like the other failures before `received`, leaves no failure record. Its message appends one fixed reason word: `held_out` (the document is recorded as held out), `not_recorded` (it is not on the assignment record and `--confirm-public-document` was not given) or `record_unreadable` (the record file exists but cannot be read). It never names the document's hash, its path or its neutral ID."

### G.1 — new row, and the appending rule

> | `E-INPUT-SEND-REFUSED` | received | The document may not be sent to the hosted API (SEC-10): it is recorded as held out, or it is not on the assignment record and `--confirm-public-document` was not given, or the record cannot be read | If the document is public and is not recorded as held out, re-run with `--confirm-public-document`; a held-out document cannot be sent | 3 | No | Specified; implemented as an uncatalogued refusal with exit code 2 (step 5k) |
>
> The sentence under the heading becomes: "They may append only the file name, numeric limits or, for `E-INPUT-SEND-REFUSED`, one fixed reason word."

### SEC-10 — one clause

> The command line enforces this with the send rule of FR-014 criterion 8; a refusal is the catalogued failure `E-INPUT-SEND-REFUSED`.

### L.2 — one row

> | markdown-it-py (MIT), with mdurl (MIT) | Yes (dev only) | Parses `memo.md` in tests (FR-010.2, K.10): structure, tables, no raw HTML, and the round trip of escaped text. Never a runtime dependency. | Added in the step that adds it, with its reason and licences recorded in `PROGRESS.md` (SEC-11). |

## 4. Effects

- **Scripts can tell a refusal from a usage error:** exit 3 with a code, not exit 2 with prose. A bad argument is still exit 2.
- **The catalogue grows to eighteen codes.** Every catalogued failure scenario has a test (SC-09), so the all-codes test gains a scenario; the README exit table says exit 3 includes a refusal.
- **A refusal still writes nothing** (it happens before `received`), so no failure record, as for a missing file or a bad profile.
- **`results.json` gains `attributes[].id`.** The memo's section 1 shows each ID; the checker verifies the page against the attribute with that ID, not against the set of all attribute pages.
- **Every memo is checked before it is written.** A faulty memo is an exit 1 with a run ID; it cannot be mistaken for a finished draft. The check is the one the tests already use, promoted into the package.
- **Evidence for SC-08 without a model call.** The check gives a counts-only figure ("memos checked: N, problems: 0") that can be reported for replayed tuning documents and for the held-out run. It covers the machine-checkable part only. SC-08 as defined also needs the manual review of claims, and this amendment does not change that.
- **A dev-only parser.** No runtime dependency is added.
- **Code affected when approved:**
  - S2: `pyproject.toml` and `uv.lock` (the parser), a new test file; `FR-010.2` test.
  - S1 follow-on: `models.py` (attribute `id`), `export/results.py`, `memo/sections.py`, the traceability checker, `ingestion/errors.py` (the new code), `cli.py` (map a refusal to it), `send_rule.py`, README and its test, the golden files.
  - S3: `memo/trace.py` (the checker moved from `tests/unit/memo_trace.py`), `export/run_export.py`, `states.py` use, the failure path in `cli.py`.

## 5. New acceptance examples (Appendix B.6, to be added as 56 to 61)

| # | Case | Expected |
|---|---|---|
| 56 | A document recorded as held out, provider `openai`, with or without `--confirm-public-document` | `E-INPUT-SEND-REFUSED (held_out)`, exit code 3, before any provider is built; nothing written; the message has no hash, path or ID |
| 57 | A document not on the record, provider `openai`, no `--confirm-public-document` | `E-INPUT-SEND-REFUSED (not_recorded)`, exit code 3; with the flag the run proceeds and a notice is printed |
| 58 | The assignment record exists but cannot be read; any document | `E-INPUT-SEND-REFUSED (record_unreadable)`, exit code 3 (the rule fails closed) |
| 59 | A run with an entity name verified on page 1 | `results.json` has an attribute `entity_name` with that page; memo section 1 prints `entity_name` beside the value with `[SOURCE: p.1]`; a memo whose label said `p.2` fails the check |
| 60 | A memo that breaks K.10 (for example, an unknown label injected into the template) | Exit code 1, "Internal error. Run ID: …"; only a manifest-only record is written, `failed` in `memo_generated`, no error code; no `memo.md`, no `results.json` |
| 61 | A profile value, an entity name and a line-item label that look like origin labels, headings, table cells or links | All render as the text they were; the check passes; the parsed memo has no extra heading, cell, link or label |

## 6. Tests, when approved

One test per example 56 to 61 through the command line; the catalogue test for the eighteenth code and its exit code; the all-codes SC-09 test with its new scenario; unit tests for the refusal reasons (including that nothing is built or written before the refusal); attribute IDs in `results.json` and the memo, with the golden files updated and the reproducibility tests still byte-identical; the parser tests of FR-010.2 on every memo the suite generates, including the hostile cases, with a round trip of the visible text; the export check on a faulty memo and on a clean one, and that the failure message gives a count and no text; the README test for the exit table; and mutation checks on each rule above.

## 7. Revision History row (draft)

| 0.4.27 | (date of approval) | **Specification change to H.1.2, K.0, K.10, FR-010, FR-011.2, FR-014 criterion 8, G.1, SEC-10 and L.2, authorised by the project owner on (date)** ("yes to all four", 2026-10-25). Document-level attributes carry stable IDs and the memo's section 1 shows them, so a document-level label resolves to an ID like every other. Every memo is checked against its results (K.10) before anything is written; a memo that fails is an internal error (exit 1) with a manifest-only failure record. A refusal to send a document is the catalogued failure `E-INPUT-SEND-REFUSED` (exit 3, fixed reason word, no record, before any provider is built), the eighteenth code. FR-010.2 now says CommonMark with GitHub-flavoured tables and requires a parse test; the parser is a dev-only dependency. Appendix B.6 examples 56 to 61 are added. Nothing else changes. |

## 8. Decisions needed from the owner

1. Adopt the wording as drafted, change it, or reject it.
2. **The reason word in the refusal message.** Drafted: one fixed word (`held_out`, `not_recorded`, `record_unreadable`), which G.1's appending rule is extended to allow. The alternative is a bare message with no reason, which is simpler but gives the analyst less to act on.
3. **Exit code 3 for the refusal** (the input class). The alternative is a new exit class for policy refusals, which is more invasive.
4. **How a failed check is reported.** Drafted: an internal error (exit 1, no catalogue code), because it signals a defect and FR-011.2 already says a failure not in the catalogue is a bug. The alternative is a catalogue code such as `E-EXPORT-MEMO-INVALID` with exit 7, which would make it testable like the others and callable from scripts, at the price of calling a template defect an anticipated failure.
5. **Whether the header's Borrower line should also show the `entity_name` ID.** Drafted: it resolves to the attribute without printing the ID, since the header is a title block.
6. **FR-010.2's new wording** (CommonMark with GitHub-flavoured tables, plus the parse test).
7. Whether I apply it to `docs/PRD.md` as v0.4.27 on your word, then implement S2 (parser and round trip), then the attribute IDs and the refusal code (S1 follow-on), then S3 (the check before export), each as a small step.
