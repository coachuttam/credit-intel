# Live-round plan for the gate, tuning reports R1 and R2

| Item | Value |
|---|---|
| Status | **A plan for the owner's review. It approves nothing.** No live call, no spend and no read of any real document is authorised by this file. Every live step still needs the owner's separate approvals (maximum spend, pages to send, token ceiling, output limit), and every read of `private/` needs explicit authorisation. |
| Drafted | 2026-10-25 |
| Goal | The gate of 2026-10-24: profit before tax, interest expense and total borrowings extract, and match the owner's hand-checked values, for both periods on **both** tuning reports (`docs/gate_round_guide.md`). |
| Method | Small live rounds on the tuning reports only. One change at a time. Counts only come back to the session. |
| Not in this plan | Anything about H1 or H2 (held-out). No held-out document is opened, hashed, read or run. |

## 1. Before any live round: three things I cannot settle from the code

The gate asks for six values per report. Whether each can be met depends on what each report prints on the pages that would be sent. I have not read either report, so these are **checks for you, from the rendered pages**, and general-knowledge cautions, not findings.

| Check | Why it matters | If the answer is "not printed" |
|---|---|---|
| **R1: does the consolidated balance sheet print a borrowings line (or its parts)?** Some large groups have no borrowings at all. | The gate needs a value to match. A report that states no borrowings has none, and an absent field is `not_found`, never zero (H.5 rule 4). | The gate cannot be met by a value. It needs a decision: for example let the reference say "none presented" and expect `not_found`, or specify a statement-evidenced nil (the unapproved proposal has one, AC-Z-46). A PRD amendment, yours to decide. |
| **R2 (a US-style filing): is interest expense on the face of the income statement?** US filings often show interest only in a note. | The pipeline reads the statement pages it is given. A value in a note is not on them. | Add the note page to `--pages` for that report (allowed: you choose the pages), or settle that the value is out of reach. |
| **R2: how is debt laid out?** US balance sheets often show short-term debt, long-term debt and a separate "current portion of long-term debt" row. | A separate current-maturities row with no inclusion or exclusion phrase is `unresolved` (`borrowings_classification_unresolved`), so total borrowings is `requires_review`, not a value. | Tune the inclusion and exclusion phrase lists (D-12) from R2's own wording. That is allowed: R2 is a tuning report. |

Please fill the first column for each of the six values per report as you write the reference files. Where a value is not printed on the pages, tell me before any live round, because no amount of tuning can produce it.

## 2. What the live tooling can and cannot do today

- **Runs on a real report:** `tests/live/test_live_tuning.py` (the same harness as G5 runs 1 to 3). It is skipped unless `CREDIT_INTEL_LIVE=1`, refuses any document not recorded as tuning, prints **one line of counts**, and keeps the model's reply in the git-ignored cache `.cache/llm`.
- **Offline, free:** `evaluation.dry_run` (which pages would be sent, estimated tokens and worst-case cost), `evaluation.diagnose` (why each check passed or failed, by counts, from a cached reply), and `evaluation.gate` (the comparison with your references).
- **Gap: `--assert-basis`.** The live test, the tuning runner and the dry run take `--pages` but not the assertion, so R2 cannot be run live under v0.4.24 through them. The product command `credit-intel` can, but it writes a full memo and results into `runs/` (figures and quotes on your disk, never shown to me), which is not the counts-only route.
- **Step L0 closes the gap (built 2026-10-25 at the owner's word; offline, tested):** `assert_basis` now goes through the runner, the live test (`CREDIT_INTEL_ASSERT_BASIS`, which needs `CREDIT_INTEL_PAGES`) and the dry run (`--assert-basis`, which needs `--pages`), and the counts-only line shows the assertion (basis, pages, pages it was applied to) and how many records rest on it (`basis_evidence`). The command templates in section 6 work as written.

## 3. The rounds

Each round is one live call per report (about $0.001 to $0.002; the five calls so far cost $0.005 in total). A round has four parts: a free offline look first, your approvals, the live call in your terminal, then a free offline replay and comparison.

| Step | Who | What | Cost | Needs |
|---|---|---|---|---|
| **L0** | me | `assert_basis` through the runner, live test and dry run; counts line shows the assertion and evidence counts | none | **built 2026-10-25** |
| **G1** | you | the two reference files in `private/eval/`, checked with `--check-reference` | none | section 1 answers |
| **Token ceiling** | you | set it for the run, in your terminal (for example `CREDIT_INTEL_TOKEN_CEILING=30000`, as in runs 2 and 3) | none | OD-8 stays "no default" |
| **L1 (optional)** | me, your authorisation | baseline replay of R1 from the cache that run 2 left: `gate --report` on R1 | none | authorisation to read the R1 PDF, counts only |
| **L2** | me | dry run of R2 with its pages and assertion: pages, tokens, worst-case cost | none | authorisation to read the R2 PDF, counts only |
| **R2-1** | you | first live round on R2 (pages from the reference, `--assert-basis consolidated`, prompt v2) | about $0.001 to $0.003 | approvals (below) |
| **R1-n / R2-n** | you | one targeted change per round, then a live round | about $0.001 to $0.003 each | approvals each time |
| **Gate check** | me | `gate --report` on both, counts only | none | both references, both cached runs |

**The levers allowed in a tuning round** (one per round, with the evidence from the tuning report, recorded in `PROGRESS.md` as counts):

1. the wording of a field's description in the prompt (a new prompt version, never edited in place; `extraction-v2` stays the default until you adopt another);
2. the row-label phrase list for a field (`LabelSettings`), for example the wording a US filing uses for income before tax;
3. the inclusion and exclusion phrases for current maturities (D-12);
4. which pages are sent (`--pages`), including a note page.

Not allowed: anything learned from H1 or H2; changing a verification rule to make a value pass; lowering a check; reading a figure into a reference from the model's output.

**Reading a round.** The counts come back as one line: candidate pages, statuses and reasons, tokens, cost, and with L0 the assertion and evidence counts. If a value is `requires_review`, the reason code says which check stopped it. The offline `diagnose` run explains it further, by counts. Whether a value is *right* is decided only by your reference through the gate, never by me.

## 4. Approvals and limits, proposed

These are proposals. The terms of runs 2 and 3 were: maximum spend $0.03, the named pages, ceiling 30,000, output limit 8,192.

| Item | Proposal |
|---|---|
| Per round | maximum spend $0.03 (about 15 times a typical call), the stated pages only, ceiling 30,000, output limit 8,192 |
| Whole gate round | a total cap of $0.15 across all rounds, then stop and report |
| Stop rule | three rounds in a row with no new matched value on a report: stop and bring you the counts, rather than keep changing things |
| Pages | R1: the four consolidated pages the locator chose (274 to 277) unless the reference says otherwise; R2: the pages named in its reference, with its assertion |
| Prices | `CREDIT_INTEL_PRICE_INPUT_PER_MILLION=0.15`, `CREDIT_INTEL_PRICE_OUTPUT_PER_MILLION=0.60` (the verified `gpt-4o-mini` prices), as before |
| Who runs it | you, in your own terminal, with your key; I write the exact command each time and never see the key |
| What comes back | the one counts line, pasted. Nothing else |

## 5. The cache has to match, or the replay is a miss

The gate replays the reply from the cache, so it must ask for exactly what the live run asked for. The cache key covers: the document's SHA-256, the page set, provider, model ID, prompt version, schema version, temperature (0), the output limit and the structured-output mode. In practice:

| Must be the same in the live run and in the gate replay | How |
|---|---|
| prompt | `CREDIT_INTEL_PROMPT` (default `extraction-v2`) |
| output limit | `CREDIT_INTEL_MAX_OUTPUT_TOKENS` (8192 in the earlier runs; the shipped file says 4096) |
| model and provider | `config/settings.toml` or its overrides |
| pages and assertion | `CREDIT_INTEL_PAGES` and `CREDIT_INTEL_ASSERT_BASIS` in the live run; `pages` and `assert_basis` in the reference file |

A mismatch shows up as `cache_miss` (a failure to replay, not a pass), never as a wrong answer.

## 6. Command templates (for your terminal; nothing is run by this plan)

R1, one live round (the harness of runs 2 and 3; the key is already exported in your shell):

```
CREDIT_INTEL_DOCUMENT=private/R1_infosys_2024_25.pdf CREDIT_INTEL_LIVE=1 \
CREDIT_INTEL_TOKEN_CEILING=30000 CREDIT_INTEL_MAX_OUTPUT_TOKENS=8192 \
CREDIT_INTEL_PRICE_INPUT_PER_MILLION=0.15 CREDIT_INTEL_PRICE_OUTPUT_PER_MILLION=0.60 \
CREDIT_INTEL_PAGES=274-277 CREDIT_INTEL_PROMPT=extraction-v2 \
uv run --locked pytest tests/live/test_live_tuning.py -q -s
```

R2, one live round (the pages are an example and must match the reference file):

```
CREDIT_INTEL_DOCUMENT=private/R2_microsoft_2025.pdf CREDIT_INTEL_LIVE=1 \
CREDIT_INTEL_TOKEN_CEILING=30000 CREDIT_INTEL_MAX_OUTPUT_TOKENS=8192 \
CREDIT_INTEL_PRICE_INPUT_PER_MILLION=0.15 CREDIT_INTEL_PRICE_OUTPUT_PER_MILLION=0.60 \
CREDIT_INTEL_PAGES=36-38 CREDIT_INTEL_ASSERT_BASIS=consolidated CREDIT_INTEL_PROMPT=extraction-v2 \
uv run --locked pytest tests/live/test_live_tuning.py -q -s
```

The gate check, with the same prompt and output limit exported:

```
CREDIT_INTEL_MAX_OUTPUT_TOKENS=8192 CREDIT_INTEL_PROMPT=extraction-v2 \
uv run --locked python -m credit_intel.evaluation.gate \
  --report private/R1_infosys_2024_25.pdf private/eval/R1_reference.json \
  --report private/R2_microsoft_2025.pdf private/eval/R2_reference.json
```

Before each live round I would also give you the dry-run line for that exact configuration, so the estimate is known before you approve.

## 7. What I do at each step

- **Before:** the free offline look (dry run, or a replay of the last cached reply), the estimated cost, the exact command, and the approvals asked for in one place.
- **After a live round:** the offline replay and, if useful, the diagnosis, as counts. One short report: what changed, what moved, the reason codes, the cost, the running total against the $0.15 cap.
- **Always:** record the round in `PROGRESS.md` (approvals, counts, cost, what was changed and the tuning evidence for it), keep the status page current, and say plainly when a round made things worse.

## 8. Risks I can already see

1. **A value that is not printed** (section 1). The most likely way the gate cannot be met by tuning alone.
2. **Interest expense and debt on a US layout.** Wording and layout differ from the Indian layout the phrase lists were first tuned on.
3. **Over-fitting two reports.** The gate shows the tuned configuration works on R1 and R2, not that it works in general. That is what the held-out run measures, and it is why nothing may be tuned after the freeze.
4. **Page text on disk.** The cache keeps the sent pages' text in `.cache/llm` (the accepted G2 risk). Delete the directory to clear it.
5. **Assertion share.** If most of R2 rests on the basis assertion, the gate passes on your word about the basis. The report shows how many values do.

## 9. Decisions needed from the owner

1. ~~Build step **L0**~~ Done at your word on 2026-10-25. It was the only code this plan needs.
2. Your answers to the section 1 checks, as you write the reference files, especially R1's borrowings and R2's interest expense and debt layout.
3. The limits: per round $0.03, a total of $0.15, ceiling 30,000, output limit 8,192, the three-rounds stop rule. Keep or change.
4. Whether to start with the free steps (L1 baseline replay of R1, L2 dry run of R2). Each needs your explicit authorisation to read that report, counts only.
5. The token ceiling you will use (OD-8 stays "no default").
