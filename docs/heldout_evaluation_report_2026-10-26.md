# Held-out evaluation report: run H-20261026T092850Z (counts only)

| Item | Value |
|---|---|
| Status | **Draft for the owner's review. Not committed.** Numbers are as printed by the held-out run tool. Nothing has been adjusted after seeing them. |
| Drafted | 2026-10-26 |
| What this reports | The held-out evaluation run (PRD O.2, v0.4.41, v0.4.42) over the two held-out documents no earlier run had used, **H3** and **H4**, on the gate's three fields: profit before tax, interest expense and total borrowings, current and comparative period. |
| Reported separately | This is its own run, identified by run id. It is **not merged** with run `H-20261025T174648Z` (H1, H2; report `docs/heldout_evaluation_report_2026-10-25.md`), and no pass rate across runs is given (PRD v0.4.42). |
| Not reported | Accuracy, coverage or any rate. With two documents the results are counts (O.2). No value, quote, label, page text or company name appears here. |

## 1. Result

| Document | Entries | Match | Mismatch | Missing | Outcome |
|---|---|---|---|---|---|
| H3 | 6 | 0 | 0 | 6 | **stopped: `E-INPUT-TOO-LARGE`. The document was never read.** |
| H4 | 6 | 0 | 0 | 6 | completed |
| **Total** | **12** | **0** | **0** | **12** | |

### H3 was an input-size stop, not an extraction miss

The file is 107,357,551 bytes. The ingest size limit (PRD FR-001.2) is 25 MB, and validation rejects a larger file before any page is read. The pipeline never saw H3: no page was located, no model call was made, no tokens were used and the cost is zero. The six "missing" entries for H3 are the evaluation's way of counting entries that have no extracted value. **They are not evidence about how the extraction behaves on that report.** The counts above include them only because the tool counts every labelled entry of a document that produced no value; for any statement about extraction, H3 contributes nothing.

### H4 (the only document of this run that reached extraction)

| Entry | Reason code (as printed) |
|---|---|
| `profit_before_tax`, current | `label_not_recognised` |
| `profit_before_tax`, comparative | `label_not_recognised` |
| `interest_expense`, current | `not_found` |
| `interest_expense`, comparative | `not_found` |
| `total_borrowings`, current | `missing_input` |
| `total_borrowings`, comparative | `missing_input` |

None of the six entries matched the owner's hand-checked values. None was a mismatch: in every entry the pipeline produced no value, or no usable record, for the field. The codes are the comparison's own wording for why an entry had no extracted value. They are not a diagnosis. **No held-out page, label value or model reply was opened to find the cause, and none will be** (O.2; AC-E-7).

### Model use

| Document | Model calls | Tokens in | Tokens out | Cost (USD, at the stated prices) |
|---|---|---|---|---|
| H3 | 0 | 0 | 0 | 0 |
| H4 | 1 | 3,536 | 1,054 | 0.0011628 |

## 2. What was frozen, and how to check it

| Fact | Value |
|---|---|
| Freeze commit | `3179a081611c3a88500ed66fd8e4a3b2afad59e1` (tag `heldout-freeze-2` points at it) |
| Working tree | clean under `src/`, `config/`, `prompts/`, `tests/eval/`, `uv.lock`, `pyproject.toml` at the start (enforced by the tool) |
| Tool | `python -m credit_intel.evaluation.heldout --held-out-run` (PRD v0.4.42: the run covers the held-out documents with no ledger line) |
| Prompt | `extraction_v5` (`prompts/extraction_v5.md`, SHA-256 `576399020fd0b4618312a7a98dd716b950201c9318916fc406f8cf01d3a05587`) |
| Provider and model | OpenAI `gpt-4o-mini` (`config/settings.toml`, SHA-256 `afa6e9226133cb575384867cd45ce9cb3e595ab413806574210eaf61f6d85c8c`) |
| Risk rules | `config/risk_rules.toml`, SHA-256 `e2060c56d795551e8c85174d03a62a029af3eb6e53dd712de29c2155772af8e3` |
| Lock file | `uv.lock`, SHA-256 `5abaa86cdd01cc046b670ad7f544812dd66d716b546060af0619fe8c8c777347` |
| Assignment record | `tests/eval/assignments.jsonl`, SHA-256 `5561cfd1bf0aa6fa8c66fc54fed92e5d0896500173a762fb2947c71b91d38d8d`; the H3 and H4 held-out assignments were added by commit `f1e26c9` (2026-10-26) |
| Run environment (not covered by the freeze check) | token ceiling 30,000 per document; output limit as in the settings file (4,096; the environment did not override it this time, unlike run 1); prices 0.15 in and 0.60 out per million tokens; `USE_JEV` unset |
| Response cache | `.cache/llm_heldout`, empty at the start (enforced; run 1's cache was moved to `.cache/llm_heldout_run1`), now holding H4's reply, kept as evidence |
| Ledger | `tests/eval/heldout_runs.jsonl`, committed as `9197457`: a `started` and a `completed` line for each of H3 and H4 under run id `H-20261026T092850Z` |
| Labels | `private/eval/H3_reference.json` and `H4_reference.json`, written by the owner before the run (git-ignored; not reproduced here) |

Anyone can check the freeze by confirming `git diff heldout-freeze-2 -- src config prompts uv.lock pyproject.toml` is empty at the time of reading, and that the file hashes above match.

## 3. Which numbers came from where

| Set | Run id | Result |
|---|---|---|
| **Tuning** (R1, R2) | the gate, live, 2026-10-25, `extraction_v5` | `GATE: PASS`; R1 6/0/0 and R2 6/0/0 |
| **Held-out** (H1, H2) | `H-20261025T174648Z` | 0/0/12 (reported in its own report) |
| **Held-out** (H3, H4) | `H-20261026T092850Z` (this run) | H3: size stop, never read; H4: 0/0/6 |

The tuning numbers were obtained on documents the pipeline's phrase lists, scans and sign rules were adjusted on. The held-out numbers are evidence on unseen reports. Of the three documents that have been read by the pipeline in held-out runs (H1, H2, H4), none produced a matching entry; H3 has produced no evidence either way. Three documents are not a sample, and no rate is stated.

## 4. What this does and does not support

- **Supports:** on H4, the one unseen report this run reached, the pipeline as frozen extracted none of the three gate fields.
- **Does not support:** any statement about H3's content, about why H4 failed, about other fields or reports, or about a rate.
- **Does not change:** the safeguards. Every missing entry is a "no value", never a wrong value; no entry is a mismatch.

## 5. Procedure notes (disclosed for completeness)

- **First launch attempt.** The first attempt had an empty approval value, because the command used a variable that had not been set. The tool refused `no_approval` before the ledger and before any send.
- **Cache.** The tool requires an empty held-out cache. Run 1's cache was moved aside, not deleted.
- **Statement-page restriction lifted, for the label check only.** Before the run, at the owner's explicit instruction (2026-10-26), the H3 and H4 statement pages were opened to check the owner's reference files against the printed pages. The assistant that did this is the one that built the pipeline, so it saw those pages. It reported pass or fail per field with no figures, and made no change to code, prompts, settings or phrase lists afterwards. The restriction is otherwise in force.
- **Labels were revised before the run.** After the first comparison, the owner changed H4's scale value to the allowed `millions`, and changed `interest_expense` in both references to the whole finance-cost line (H3 on its note, H4 on the face of the income statement). These revisions were made against the printed pages, before the run, and not in response to any pipeline output. The final references passed `--check-reference` and a full per-entry comparison before the freeze.
- **H3 total borrowings.** The H3 reference value is the sum of the balance sheet's non-current and current borrowings lines, not a single printed figure. This does not affect the result, since H3 was not read.
- No setting, prompt, phrase list or code was changed after the run. This report was written afterwards.

## 6. What happens next (for the owner's decision)

The one shot for each of H3 and H4 is used; the ledger records both as `completed`, so the tool refuses a second run of either (`already_used`). There is no unused held-out document.

- **The H3 stop.** H3 never tested the extraction. If the owner wants a held-out result in its place, a new held-out document must be assigned, recorded before it is inspected, and must be within the 25 MB ingest limit; the next freeze would follow the same steps. Whether 25 MB is right for annual reports is a separate PRD question. Changing it now would be a pipeline change made after seeing a held-out result, so it is parked until the owner decides.
- **Learning from H1, H2 or H4.** O.2 requires, in this order: (1) a `moved` line for each in `tests/eval/assignments.jsonl` (held out to tuning, with a reason), committed **before** any inspection; (2) the next report states the move, its date and reason, and that these results were obtained before it; (3) the held-out set is restored only by assigning new documents, recorded before they are inspected.
