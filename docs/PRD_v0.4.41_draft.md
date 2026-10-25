# PRD v0.4.41 — draft amendment: the held-out run tool and its narrow send exception (O.2, SEC-10, FR-014 rule 8)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("approve v0.4.41, ledger committed, gate fields only"); applied to `docs/PRD.md` as v0.4.41 and implemented. Kept as the record of the reasoning. Differences are listed in the Revision History row.** |
| Drafted | 2026-10-25 |
| Evidence | The gate passed on both tuning reports on 2026-10-25 (6/0/0 each, live, `extraction_v5`). O.2 already requires one held-out evaluation run after a frozen configuration, and `PROGRESS.md` records that no tool exists to run it (Phase 5 Part 2, item 8 "not met"). No held-out document, ID-to-hash line, label or page was opened to write this draft. |
| Changes | O.2 (the held-out procedure names the tool and the ledger), SEC-10 and FR-014 rule 8 (one sentence: the ordinary path is unchanged), a new section for the tool, Appendix B.6 examples 128 to 141, the Revision History. Output lines of the tuning runner and the gate gain a `set` member. |
| Not changed | `check_may_send` and the command line's rule 8: a held-out document is still **never** sent by them, whatever the options or environment. The gate, the dry run and the tuning runner still refuse held-out documents. Every extraction, verification and scan rule. |

## 1. What is built, and why it needs a PRD change

O.2 says: freeze the configuration, then run the pipeline **once** over every document the assignment record shows as held out, and report counts. Today every send path refuses a held-out document (rightly), and there is no tool that runs the held-out set. So the one run that matters cannot be made, and the only way to make it would be to weaken a guard that protects the tuning/held-out wall everywhere else. This draft adds **one separate tool** with its own preconditions, and leaves every other guard exactly as it is.

## 2. The exception: narrow by construction

1. **A separate command only.** `python -m credit_intel.evaluation.heldout`. It is the only code that can send a held-out document. The ordinary command line, the tuning runner, the gate, the dry run and the Jev experiment are untouched: they keep refusing `held_out` whatever options or environment they are given. The new environment variable and flag are read **only** by the tool; a test sets them and shows the ordinary command line still refuses with `held_out`.
2. **An explicit flag and an explicit approval.** The tool does nothing without `--held-out-run` **and** `CREDIT_INTEL_HELD_OUT_APPROVED=<freeze commit>` (the commit hash the owner typed, 12 or more characters, which must be the current `HEAD`), plus `CREDIT_INTEL_PRIVATE_APPROVED=1`, the token ceiling and the prices, as for a tuning round. Missing any of them is a refusal before anything is read or sent.
3. **One import site.** The permission to send a held-out document is a function in the guard module (`allow_held_out_send`) that only the tool calls. A test parses the source tree and fails if any other module imports it.
4. **Held-out documents only.** The tool refuses a document that is recorded as `tuning`, or is not on the record (a held-out run on a tuning document would mislabel its numbers).
5. **The whole held-out set, no more, no less.** O.2: the run covers every document the record shows as held out at the start. The tool compares the documents it is given with the record: any held-out document missing, any extra document, or a duplicate refuses the run (`not_the_held_out_set`).
6. **Nothing else goes off the machine.** `USE_JEV` (or any second provider) set to true refuses the run: no held-out page is sent to the page classifier.

## 3. The freeze, enforced

Before it reads a single held-out page the tool checks, and refuses (`not_frozen`) unless all hold:
- the working tree is clean (`git status` has no change, including no untracked file in `src/`, `config/`, `prompts/`, `tests/eval/`), and `HEAD` equals the commit named in `CREDIT_INTEL_HELD_OUT_APPROVED`;
- the SHA-256 of `uv.lock`, `config/settings.toml`, `config/risk_rules.toml`, the prompt file in use, and `tests/eval/assignments.jsonl` are computed and recorded (the locator settings and phrase lists, and the verification phrase lists, are in `src/`, so the clean-tree check and the commit cover them);
- the response cache directory for the run (`.cache/llm_heldout`, separate from the tuning cache) is empty, so no earlier reply can answer a held-out page, and it is kept untouched afterwards as evidence;
- the label files (the reference files, in the gate's format) exist for each document, pass the gate's own `load_reference` checks, and name the document's hash.

## 4. One shot per document: the ledger

- A new append-only file, `tests/eval/heldout_runs.jsonl`, committed like the assignment record. One line per document per run: `document_id`, `sha256`, `run_id`, `event` (`started` or `completed`), `at` (ISO timestamp), `freeze_commit`, `assignments_sha256`.
- **Before the first page of a document is sent**, the tool appends and flushes a `started` line for it. After the document's comparison is printed it appends `completed`.
- **Refusal:** if any requested document already has a line in the ledger, whatever its event, the whole run is refused (`already_used`), before anything is sent. A run that dies after its first send has therefore used its shot; that is deliberate, because a retry on a document the model has already seen would be a second look. The tool has **no** override. Giving a document another run is an owner decision recorded in this PRD, not an option.
- An unreadable ledger, or one that fails its validator test (UTF-8, LF only, exact members, append-only against `HEAD`, as for the assignment record) refuses everything (`ledger_unreadable`).
- A held-out document later moved to tuning (O.2) keeps its ledger line, and the next report states both facts.

## 5. What the tool compares and prints (counts only)

It reuses the gate's code: `load_reference`, `compare`, the send-guard helpers and the counts-only line. For each document it prints one line of counts: match, mismatch, missing for the gate's three fields (both periods), plus the field-status counts of the tuning summary, tokens and cost. It prints **no value, quote, label, page text, path or hash**. It then writes the same counts, the freeze facts and the ledger run id to a git-ignored report file under `private/eval/`; the owner chooses what, if anything, to commit.

**Which numbers came from where, with no ambiguity.**
- Every line carries a `set` member: `"set": "held_out"` from this tool, `"set": "tuning"` from the gate and the tuning runner (their lines gain that member, taken from the assignment record at the time of the run; the golden test fixtures are updated for it).
- The first line of a held-out run is `HELD-OUT RUN` with the run id, the freeze commit, the SHA-256 of `assignments.jsonl`, and the number of documents; the last is `HELD-OUT RUN COMPLETE` or `HELD-OUT RUN INCOMPLETE <n of m documents>`. Nothing the tool prints can be mistaken for a tuning line, and the gate refuses any line it did not produce.
- A held-out run does not decide the gate: `evaluate_gate` is unchanged and still requires the tuning documents.

## 6. Refusal words (fixed text, exit code 2, no document identifier)

`no_flag`, `no_approval`, `not_frozen`, `not_held_out`, `not_the_held_out_set`, `already_used`, `ledger_unreadable`, `record_unreadable`, `cache_not_empty`, `reference_invalid`, `second_provider`. They are evaluation-tool refusals like the gate's (exit 2), not entries of the command-line error catalogue.

## 7. Tests (all synthetic; no real document, no network)

The tests build their own assignment record, ledger and reference files in a temporary directory with **synthetic** PDFs and a fake provider; the default suite never needs `private/`. They cover examples 128 to 141 below, plus: the ordinary command line, the gate, the dry run and the tuning runner still refuse a document recorded as held out with every new variable set; the `allow_held_out_send` import is found only in the tool; the ledger validator.

## 8. Acceptance examples (Appendix B.6, to be added as 128 to 141; synthetic records)

| # | Case | Expected |
|---|---|---|
| 128 | `--held-out-run` is absent | refused, `no_flag`; nothing read |
| 129 | The approval variable is absent, or names a commit that is not `HEAD` | refused, `no_approval` |
| 130 | A tracked or untracked file in `src/`, `config/`, `prompts/` or `tests/eval/` differs from `HEAD` | refused, `not_frozen` |
| 131 | A document is recorded as `tuning` | refused, `not_held_out` |
| 132 | One held-out document is left out, or an extra one is given | refused, `not_the_held_out_set` |
| 133 | The ledger already holds a line for one of the documents | refused for the run, `already_used`; nothing sent |
| 134 | The run dies after the first document's first send | its `started` line stays; a second run is refused, `already_used` |
| 135 | The ledger is malformed or unreadable | refused, `ledger_unreadable` |
| 136 | `USE_JEV=true` | refused, `second_provider` |
| 137 | The held-out response cache directory holds a file | refused, `cache_not_empty` |
| 138 | A good run | one counts line per document, `"set": "held_out"`, `HELD-OUT RUN` and `HELD-OUT RUN COMPLETE` lines, `started` then `completed` ledger lines, no value or quote printed |
| 139 | The ordinary command line, with the flag and the approval variable set, is given a held-out document | still refused, `held_out` |
| 140 | The gate, given a held-out document | still refused, as before |
| 141 | A tuning gate line | carries `"set": "tuning"` |

## 9. What this does **not** settle (decisions for the owner)

1. **Approve, change or reject sections 2 to 6**, in particular: no override for a second run (section 4), the whole-set rule (section 2.5), and the freeze check requiring a clean tree.
2. **The evaluation report's scope.** I have not mapped SC-01 to SC-12 to this tool's output. The tool as drafted prints the gate's three-field counts, the field-status counts, tokens and cost. Say which other success criteria the report must cover (for example the memo and the risk rules on the held-out reports), and I will add them, or leave them to a separate report step.
3. **Where the label files live.** I propose the gate's reference format in `private/eval/`, one per held-out document, written by you before the freeze.
4. **The ledger is committed** and holds neutral IDs and hashes, like the assignment record. If you would rather keep it out of the repository, the one-shot rule would then rest on a local file only.
5. **Order after approval:** I implement the tool with tests and mutation checks, offline, with synthetic documents only. I do not open, hash or run a held-out document. The single held-out run happens only on your command, in your terminal, after the freeze.
