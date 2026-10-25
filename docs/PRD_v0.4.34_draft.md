# PRD v0.4.34 — draft amendment: Jev as a second-opinion verifier, shadow mode first (new FR-005.11)

| Item | Value |
|---|---|
| Status | **A draft for the owner's approval. It changes nothing in `docs/PRD.md`, no code, no configuration and makes no call.** Nothing is built and no live call is made until the owner approves this text. |
| Drafted | 2026-10-25 |
| Evidence | Jev's documentation (`docs.typesafe.ai`, read 2026-10-25): typed questions about a supplied "state"; Choice and Noul answers with probabilities and a confidence; weak at numbers, counting and dates; hosted only. The gate round on R1 and R2 (`PROGRESS.md`). |
| Builds on | FR-013.1 (the optional classifier of v0.4.31, parked as a page filter): its client, cache, fallbacks, send rule and `private/` guard are reused. This amendment is a different use of the same service. |
| Changes | New FR-005.11; Section F.2; the settings; the manifest (a block, only when on); the evaluation tools; Appendix B.6 examples 80 to 85; Revision History. |
| Not changed | Extraction, every deterministic check, every status and value, `results.json`, the memo. **Jev never changes a value, a field name, a page or a period.** |

## 1. Purpose

The deterministic checks (FR-005) prove that a value is on the cited page, in the right column, with the right sign, scale and currency, and that its row label is on a list. They cannot prove that the row **means** the field it was filed under: a label list is exact-match, so a wrong row with an accepted label (or an unlisted synonym) is the remaining kind of error. A second reader of the **meaning** of the row is a cheap, independent check of exactly that. Jev answers typed questions with probabilities, which fits a yes/no or pick-one check. The amendment uses it as a **witness**: it can raise a flag; it cannot alter the result.

## 2. What is asked (FR-005.11, proposed)

Both checks send only the **row label and the few heading lines above it**. **No figure, date or currency leaves the machine**, which is also where Jev is documented to be weak.

1. **Row-to-field check.** For each field that reached `extracted` (and, in the report, each `requires_review` one), Jev is shown the row label and the lines of the heading above it, and picks, in one Choice question, **one field name or `none`** from the H.3 list (each option described in words, in a fixed order; a second order is tried in evaluation because the documentation warns of a bias toward the first option). Verdict: **agree** if its pick equals the field's name; **disagree** if it picks another field or `none` at or above the confidence threshold; **abstain** below the threshold.
2. **Yes/no second opinion** for the three gate fields (`profit_before_tax`, `interest_expense`, `total_borrowings`; for a total built from parts, each part). One Noul question per row: "Is this row the *[the field's description]*?" with the same context. Verdict: **yes** at or above a threshold, **no** at or below one minus it, **abstain** between.
3. A field is **flagged** when check 1 disagrees, or check 2 says no. A flag is a record; see the modes.

## 3. Modes and the setting

`JEV_VERIFY=off|shadow|enforce` (default `off`; absent or empty is off; anything else is `E-CONFIG-INVALID`).

- **off:** nothing runs and nothing is imported; the run is byte-identical to today.
- **shadow (the only mode this amendment enables):** the checks run after the field set is built and **change nothing**. `results.json`, `memo.md` and every status are byte-identical to the run without it. The verdicts go to the log (INFO: field ID, page, Jev's pick or answer, confidence, verdict, latency, cost; no text) and to `manifest.json` (a block present only when the mode is on).
- **enforce (specified, not enabled):** a flagged field would become `requires_review` with a new reason `second_opinion_disagrees` (the evidence kept, the value cleared, as FR-006.5 does). It stays **disabled in code** until the owner has read the shadow report and approves a further amendment.

## 4. Safety and data flow (SEC-10)

- **Which documents.** Only documents recorded as **tuning** in `tests/eval/assignments.jsonl`: R1 and R2. The send rule applies to Jev as to the extraction model: a held-out document is refused, whatever the flags; **H1 and H2 are never opened, hashed or run**. The two tuning reports live in `private/`, so a run needs the owner's per-run approval (`CREDIT_INTEL_PRIVATE_APPROVED=1`) and the document's tuning record; no other file in `private/` is touched. The unit tests use mocked clients and synthetic data only.
- **What leaves the machine.** Labels and heading lines of rows of public tuning reports: less than the page text the extraction model already receives. TypeSafe's retention terms are not stated in the documentation read; **the owner reviews them before the first live run** (this is a public document, but the review is the standing condition for this service).
- **Never fails a run.** Every error, timeout, invalid reply or missing key becomes a fixed reason word, the field simply has no verdict, and the run is unaffected (as in FR-013.1: breaker after 3 failures, a time budget per document).
- **Model version.** The versioned ID of every response is logged and recorded; tuning and evaluation runs pin it (`jev-1.14.0`), because a moving alias can change a verdict with no change to our code.

## 5. The shadow report (the evaluation tool)

One counts-only line per report and a combined one, from `python -m credit_intel.evaluation.jev_verify_report` (estimate by default, offline and free; `--live` needs a maximum spend that covers the worst case):

- **Coverage:** rows checked, verdicts obtained, abstentions, failures.
- **Agreements and disagreements**, by field and by check, and the **flags that shadow mode would have raised**.
- **Was a disagreement a real error?** For the gate fields, a flag is a **real error** if the pipeline's value or presence mismatches the owner's reference for that report, and a **false alarm** if the reference matches. For every other field the tool lists the flagged field IDs for **the owner to judge** (counts and IDs only; it does not guess).
- **Detection power on a challenge set.** Because the gate passes, there may be no real error to find. So the tool also builds, offline, **seeded faults** from the tuning pages' own rows: the same row filed under a wrong field, or under a field it resembles. It reports how many Jev would flag. This uses labels only and is the only way to learn whether a quiet shadow run means "no errors" or "a check that cannot see them".
- Cost (tokens and USD of Jev, which is billed per input token) and added latency.

**What would justify enforce (for the owner to decide, not automatic):** at least one real error flagged or most seeded faults flagged, with few or no false alarms on rows the reference confirms. If shadow shows false alarms or no detection power, the idea is parked, as the page filter was.

## 6. Effects and risks

- **Cost:** a row label with its heading is about 100 tokens; a run checks about 15 to 30 rows twice: well under a thousandth of a cent at the documented price. The expected cost is not the issue; the value of the signal is.
- **A false disagreement** in enforce mode would hide a correct value as `requires_review`. That is the reason enforce is not enabled and is judged on the report.
- **Jev is documented to read literally and to lean toward the first option**: the fixed option descriptions, two orders in evaluation and a threshold are the mitigations; the report shows whether they suffice.
- The check is as independent as a second model reading labels can be; it is not a ground truth. The owner's reference remains the only one.

## 7. Acceptance examples (Appendix B.6, to be added as 80 to 85)

| # | Case (synthetic) | Expected |
|---|---|---|
| 80 | `JEV_VERIFY` absent, empty or `off` | nothing runs, the SDK is not imported, the run is byte-identical |
| 81 | Shadow, Jev picks the field the model used for every row | all `agree`; `results.json` and `memo.md` byte-identical to the run without it; the manifest has the block |
| 82 | Shadow, Jev picks another field for one row, above the threshold | that row is `disagree` and listed as a would-be flag; its status in `results.json` is unchanged |
| 83 | Shadow, the yes/no answer for `profit_before_tax` is "no" above the threshold | listed as a would-be flag; unchanged |
| 84 | Shadow, Jev errors, times out, returns an invalid reply, or there is no key | no verdicts for those rows, a reason word logged, exit 0, results unchanged |
| 85 | Any mode on a document recorded as held out, or on one under `private/` without the owner's approval | refused before any call, as for the extraction model |

## 8. What I need from the owner

1. Approve, change or reject sections 2 to 5, including that `enforce` stays disabled in code.
2. Confirm the scope of "tuning reports only, never private/ held-out": I read it as **R1 and R2 only, with your per-run approval for their `private/` location, and never H1, H2 or any other file in `private/`**.
3. Confirm the seeded-fault challenge set (section 5), or strike it.
4. Review TypeSafe's retention terms before the first live run; I have not read them.
5. After approval I would, in order: apply the PRD as v0.4.34; build the verifier behind `JEV_VERIFY` with mocked clients and every fallback tested; build the report tool; give you a free estimate; and stop for your approval of the live run with its cost.
