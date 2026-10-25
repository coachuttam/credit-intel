# PRD v0.4.31 — draft proposal: Jev (TypeSafe AI) classifies pages before OpenAI extracts

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-25 ("approve"), applied to `docs/PRD.md` as v0.4.31 (FR-013.1) and implemented with mocked clients only. Kept as the record of the reasoning.** Differences from this draft are listed in `PROGRESS.md`: a note is never dropped for its basis either; `JEV_API_KEY` is accepted as another name for the key; the private-folder approval is `CREDIT_INTEL_PRIVATE_APPROVED=1`. |
| Drafted | 2026-10-25 |
| Source of the API facts | `docs.typesafe.ai`, read on 2026-10-25 through a fetch agent (so second-hand: I have not seen the page text myself). Before building I would re-read three pages and check the exact field names: the System One API, Confidence, and the Python basic usage. Anything the docs do not say is marked "not stated". |
| Touches | FR-013 (page selection, one new optional filter), SEC-10 (a second hosted provider), NFR cost and logging, FR-011 (log fields), the manifest, the evaluation guard, Section U. No new error code. |

## 1. Roles

| Step | Provider | Does | Never does |
|---|---|---|---|
| Classify | **Jev** (`jev-latest`, `typesafe-sdk`) | For a page: `page_type` (`balance_sheet`, `profit_loss`, `cash_flow`, `notes`, `other`) and `basis` (`standalone`, `consolidated`, `unclear`), each with a confidence | Read or return a figure, a quote, a period or a currency; set the basis used for verification; add a page |
| Extract | **OpenAI** (unchanged) | Proposes every field value, as today | — |
| Verify | Deterministic Python (unchanged) | Checks every proposal against the page text | — |

Jev is a labeller of pages. Every number in the results still comes from OpenAI and is verified against the page by the existing checks. A Jev label is **never evidence**: it does not appear in `results.json` fields, the memo's origin labels, or any verification record.

## 2. Flow and fallbacks

1. The deterministic locator picks the candidate pages and the basis gate runs, exactly as today (before any Jev call).
2. With `USE_JEV=true`, each locator candidate page is sent to Jev, one page per call.
3. A page is **kept** (sent to OpenAI) unless Jev says, with confidence at or above the threshold, that it is not needed: `page_type` of `cash_flow` or `other`, or a `basis` that is the other configured basis. `notes` pages are never dropped (interest expense and borrowings often sit in a note). `unclear` is never a reason to drop.
4. **Fallback to today's path, for that page:** confidence below the threshold, label `unclear`, an error or timeout, a missing key, an over-length page, an invalid reply, or the circuit breaker (below). The page is then sent to OpenAI exactly as without Jev.
5. Pages named by `--pages` are never filtered: an analyst's choice is not overridden.
6. **The pipeline never fails because of Jev.** Every exception from the Jev step is caught at the step boundary, logged by type only (no text), and treated as a fallback. After 3 consecutive failures in a run, Jev is skipped for the rest of the run (circuit breaker); a per-document time budget (provisional 60 s) does the same. With `USE_JEV` off or absent the code path is not entered and behaviour is byte-identical to today (a test proves it).

## 3. Why a filter and not a selector

The locator is deterministic, free and already narrows a document to a few pages (R2: 2 to 3, R1: 4). Letting a model choose pages would put a model judgement ahead of the evidence rules (H.4.6 reads the basis from the title only) and make page selection non-reproducible. So Jev can only **remove** pages from the locator's candidates, can never add one, and a wrongly dropped page can only cost a `not_found`, never a wrong value.

## 4. Threshold and model version

- Jev's Choice confidence is a number from 0 to 1, computed from its option probabilities as (p_max − 1/n) ÷ (1 − 1/n). The threshold is **provisional (default 0.85)** and is tuned on the two tuning reports only (O.2), never on H1 or H2.
- `jev-latest` is an alias that "moves when a new release ships" (currently `jev-1.14.0`), so answers can change with no change to our code. The docs advise pinning if a threshold was tuned on one version. I would use `jev-latest` as instructed, **log the versioned ID from every response**, record it in the manifest, and use a pinned ID (`jev-1.14.0`) for any tuning or evaluation run.
- The docs' known-weak-spots page is for jev-1.13 (last reviewed 2026-10-02); none is listed for 1.14.

## 5. Weak spots that shape the design (from the docs' jaggedness page)

| Weak spot | What we do |
|---|---|
| Poor at numeric precision, counting, dates | Jev is never asked for a number or date; those stay with OpenAI and the verifier |
| Context rot (accuracy falls with irrelevant detail) | State = the page's title block plus its first lines (provisional 40), not the whole page; to be checked against whole-page in the evaluation |
| Option-order bias | Page-type options are tested in two orders in the evaluation; a disagreement lowers the confidence used (treated as a fallback) |
| "None of the above" options work poorly | `other` is a real option with a description; `unclear` for basis is a real option |
| Literal reading | Each question states one condition; page type and basis are two separate questions in one call (evaluated in parallel) |
| 64k per request / 32k per question | One page per call; a page over the limit gets HTTP 400 (`max_tokens_exceeded`) and falls back. The long-context header is **not** used (docs: slower and less accurate) |

## 6. Data flow and the guard (SEC-10)

- **Jev is hosted only** (`api.typesafe.ai`). Page text of a document leaves the machine to a **second** third party. The docs say Jev is "not trained on customer requests or responses". **Not stated** in the docs I read: retention periods, region, compliance certifications, whether confidential financial documents are suitable. Zero data retention is an enterprise option. The Data Processing Agreement and Privacy Policy are on another host and were not read. **Owner action: review TypeSafe's terms before any live call** (as was required for OpenAI under SEC-10).
- The key is read from `TYPESAFE_API_KEY` in the environment only, never from a file, never logged. A placeholder name goes in `.env.example`.
- **The send rule applies to each provider separately.** `held_out` is never sent to either; a tuning document may be; any other document only with `--confirm-public-document`; an unreadable record refuses both. The evaluation guard (`evaluation.guard`, used by the dry run, the live tuning test and the new evaluation script) is extended to name the provider in its refusal.
- **`private/` is refused by default for both models.** The two tuning reports live in `private/`, so a live evaluation on them is possible only with your explicit approval for that run (a tuning document, recorded as such, plus your approval of spend and pages). Unit tests use only mocked clients and synthetic data, and never touch `private/`. H1 and H2 are never opened, hashed or run.

## 7. Configuration

- `USE_JEV=true|false` (default false) as asked. Note the existing settings use the `CREDIT_INTEL_` prefix; I would keep your name and also read nothing else for this switch.
- `config/settings.toml` gains a `[steps]` table that names the provider of each step (`classify = "jev"`, `extract = "openai"`) and a `[jev]` table: model, threshold, timeout (provisional 10 s per call, the SDK's default per HTTP operation), time budget, state size. The OpenAI settings and the token ceiling are untouched.

## 8. Records

- **Log, per page, at INFO (counts and identifiers only, no document text):** Jev label, confidence, fallback yes/no and the reason code, latency, Jev input tokens and cost (input tokens × $0.042 per million; output is free per the docs), and the OpenAI tokens and cost for the run.
- **`results.json` stays deterministic:** it gains only `extraction.page_filter` (enabled, threshold, pages sent, pages dropped, versioned Jev model ID). Latency is non-deterministic and goes only in `manifest.json`, with the per-page records.
- A Jev response cache (like the OpenAI cache) keeps replays free and identical. A `USE_JEV` run and an OpenAI-only run of the same document differ only in the page list and the cache key.

## 9. Cost: what to expect

Measured from the earlier R2 round: 3 pages, 3,047 OpenAI input tokens (about $0.00046), 1,166 output tokens (about $0.0007), the rest of the cost. A page is about 800 to 1,000 tokens. Classifying R2's 3 candidate pages with Jev would cost about $0.00005. Dropping one of three pages saves at most about $0.00004 of OpenAI input. **So on documents the locator has already narrowed, Jev costs about what it saves, and output tokens (which Jev does not touch) dominate the OpenAI bill.** If Jev classified every page of a document instead (R2 has 80 pages; R1 several hundred), Jev would cost more than the whole OpenAI call. The honest expectation is no meaningful saving on R1 and R2; the case for Jev rests on documents with many candidate pages, or on finding pages the locator misses. The evaluation is designed to say which, with counts, before anything is adopted.

## 10. Success criteria (measured on R1 and R2, Jev+OpenAI against OpenAI-only, same pages, assertion, prompt and limits)

1. **Fields:** every (field, period) extracted by OpenAI-only is also extracted by Jev+OpenAI, and where the owner's reference exists no value that matched becomes a mismatch or missing. Reported for profit before tax, interest expense and borrowings first.
2. **OpenAI cost:** input tokens lower on at least one report and higher on none; and the combined Jev + OpenAI cost reported next to it, whether lower or not.
3. **Page accuracy:** agreement of Jev's labels with the locator's statement types on every page the locator selects (counts), and, if the owner labels a sample of pages, accuracy against those labels. Agreement with the locator is not ground truth and is reported as such.
4. **Reliability:** with the mocked client failing (timeout, 5xx, invalid reply, no key), the output is identical to OpenAI-only; with `USE_JEV` off it is byte-identical.
5. **Latency:** added seconds per document, reported.

Adoption (making `USE_JEV` true anywhere by default) is your decision after the report, and is not part of this proposal.

## 11. Out of scope

Using Jev for extraction or arithmetic; letting Jev select pages the locator did not; images (Jev's image support is dated after today in the docs and not needed); a second held-out evaluation.

## 12. What I need from you

1. Approve, change or reject the roles and fallback rules (sections 1 to 3, 8).
2. The `private/` rule in section 6: refuse by default, with your per-run approval for the R1 and R2 evaluation. Confirm this is what you meant by "never run on `private/`".
3. Review TypeSafe's terms (retention, region, suitability) before any live call; I have not read them.
4. Whether you accept the cost expectation in section 9, or want the evaluation limited to the offline dry-run estimate first (free).
5. After approval I would, in order: add `typesafe-sdk` (checking its version, licence and release date on the package index first, and recording them in the dependency table), extend the guard, add the settings and the Jev step behind `USE_JEV`, write mocked tests for every fallback, build the evaluation script, then stop and ask before any live run with a cost estimate. `PROGRESS.md` updated and files staged for your review, nothing committed.
