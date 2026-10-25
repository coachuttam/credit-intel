# Held-out evaluation report: run H-20261025T174648Z (counts only)

| Item | Value |
|---|---|
| Status | **Draft for the owner's review. Not committed.** Numbers are as printed by the held-out run tool and read from its report file. Nothing has been adjusted after seeing them. |
| Drafted | 2026-10-25 |
| What this reports | The single held-out evaluation run (PRD O.2, v0.4.41) over the two documents the assignment record shows as held out, **H1** and **H2**, on the gate's three fields: profit before tax, interest expense and total borrowings, current and comparative period. |
| Not reported | Accuracy, coverage or any rate. With two documents the results are counts (O.2). No value, quote, label, page text or document hash appears here. |

## 1. Result

| Document | Entries | Match | Mismatch | Missing |
|---|---|---|---|---|
| H1 | 6 | 0 | 0 | 6 |
| H2 | 6 | 0 | 0 | 6 |
| **Total** | **12** | **0** | **0** | **12** |

**The held-out gate on these fields was not met:** none of the 12 entries matched the owner's hand-checked values. No entry was a mismatch: in every entry the pipeline produced no value, or no usable record, for the field.

### Reason codes of the missing entries (as printed)

| Entry | H1 | H2 |
|---|---|---|
| `profit_before_tax`, current | `label_not_recognised` | `no_record` |
| `profit_before_tax`, comparative | `label_not_recognised` | `no_record` |
| `interest_expense`, current | `no_record` | `no_record` |
| `interest_expense`, comparative | `no_record` | `no_record` |
| `total_borrowings`, current | `missing_input` | `evidence_not_verified` |
| `total_borrowings`, comparative | `missing_input` | `no_record` |

The codes are the comparison's own wording for why an entry had no extracted value. They are not a diagnosis. **No held-out page, label file value or model reply was opened to find the cause, and none will be** (O.2; AC-E-7).

### Model use

| Document | Model calls | Tokens in | Tokens out | Cost (USD, at the stated prices) |
|---|---|---|---|---|
| H1 | 1 | 4,412 | 1,256 | 0.0014154 |
| H2 | 2 | 5,330 | 8,980 | 0.0061875 |

The tool printed the number of calls; the reason H2 made two is not known and was not investigated.

## 2. What was frozen, and how to check it

| Fact | Value |
|---|---|
| Freeze commit | `bab1197eaff391093e6595223c99ae7e07566d85` (tag `heldout-freeze-1` points at it) |
| Working tree | clean under `src/`, `config/`, `prompts/`, `tests/eval/`, `uv.lock`, `pyproject.toml` at the start (enforced by the tool; a clean tree is a precondition) |
| Tool | `python -m credit_intel.evaluation.heldout --held-out-run` (PRD v0.4.41) |
| Prompt | `extraction_v5` (`prompts/extraction_v5.md`, SHA-256 `576399020fd0b4618312a7a98dd716b950201c9318916fc406f8cf01d3a05587`) |
| Provider and model | OpenAI `gpt-4o-mini` (`config/settings.toml`, SHA-256 `afa6e9226133cb575384867cd45ce9cb3e595ab413806574210eaf61f6d85c8c`) |
| Risk rules | `config/risk_rules.toml`, SHA-256 `e2060c56d795551e8c85174d03a62a029af3eb6e53dd712de29c2155772af8e3` |
| Lock file | `uv.lock`, SHA-256 `5abaa86cdd01cc046b670ad7f544812dd66d716b546060af0619fe8c8c777347` |
| Assignment record | `tests/eval/assignments.jsonl`, SHA-256 `5c21b144d526b1e45224f416e7d42998747b7426aaae85a62137bdfb02ae6acd`; the held-out assignments were added by commit `310e6e5b485e444933246d4785295b0eb8a2de7e` (2026-10-24, before any inspection) |
| Run environment (not covered by the freeze check) | token ceiling 30,000 per document; output limit 8,192 per call (the settings file says 4,096; the environment overrides it, as in all tuning rounds); prices 0.15 in and 0.60 out per million tokens; `USE_JEV` unset |
| Response cache | `.cache/llm_heldout`, empty at the start (enforced), kept as evidence |
| Ledger | `tests/eval/heldout_runs.jsonl`, committed as `40beb18`: a `started` and a `completed` line for each document under run id `H-20261025T174648Z` |
| Labels | `private/eval/H1_reference.json` and `H2_reference.json`, written by the owner before the run (git-ignored; not reproduced here) |

Anyone can check the freeze by confirming `git diff heldout-freeze-1 -- src config prompts uv.lock pyproject.toml` is empty at the time of reading, and that the file hashes above match.

## 3. Which numbers came from where

| Set | Run | Result |
|---|---|---|
| **Tuning** (R1, R2) | the gate, live, 2026-10-25, `extraction_v5` | `GATE: PASS`; R1 6/0/0 and R2 6/0/0 |
| **Held-out** (H1, H2) | this run, once | 0/0/12 |

The tuning numbers were obtained on documents the pipeline's phrase lists, scans and sign rules were adjusted on; they say nothing about unseen reports. The held-out numbers are the first evidence on unseen reports.

## 4. What this does and does not support

- **Supports:** the pipeline, as frozen, extracted none of the three gate fields on either of two unseen reports. The tuning-set gate did not predict held-out behaviour.
- **Does not support:** any statement about why, about other fields, about other reports or about a rate. Two documents are not a sample.
- **Does not change:** the safeguards. Every missing entry is a "no value", never a wrong value; no entry is a mismatch.

## 5. Procedure notes (disclosed for completeness)

- An earlier attempt to launch the run, using placeholder file names, stopped at the first reference check and sent nothing.
- The tool's pre-flight checks and the freeze held at the start of the run (the run header records the commit and file hashes above).
- No setting, prompt, phrase list or code was changed after the run. This report was written afterwards.

## 6. What happens next (for the owner's decision)

The one shot for each document is used; the tool refuses a second run (`already_used`).

If the owner chooses to learn from H1 and/or H2, O.2 requires, **in this order**: (1) a `moved` line for each in `tests/eval/assignments.jsonl` (held out to tuning, with a reason), committed **before** any inspection; (2) the next report states the move, its date and reason, and that these results were obtained before it; (3) the held-out set is restored only by assigning new documents, recorded before they are inspected. Until then there is no held-out set.
