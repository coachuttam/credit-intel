# PRD v0.4.21 — draft amendment: do not send pages whose basis is unknown (OD-10 Option 5)

| Item | Value |
|---|---|
| Status | **Approved by the owner on 2026-10-20 ("yes to all four") and applied to `docs/PRD.md` as v0.4.21.** Kept as the record of the reasoning. Example numbers 28 to 34 here are 27 to 33 in the PRD. |
| Drafted | 2026-10-20 |
| Owner decisions this draft rests on | OD-10 options note (`docs/OD-10_options_note.md`): Option 5 adopted ("1 yes"); Options 2 and 3 kept for Phase 5; Option 4 rejected; R2's basis confirmed by the owner as consolidated ("2 consolidated"); this draft requested ("3 yes"), 2026-10-20. |
| Changes | FR-013 (a new exclusion reason and its recording), H.4.6 (the order of the basis gate and the exclusion), Appendix B (examples), Revision History. No other requirement. |
| Evidence | The G5 run on tuning document R1 and its replays (`PROGRESS.md`), counts only. Tuning set only (O.2). |

## 1. Why

On R1 the basis gate passes, because the consolidated pages 274–277 are titled "consolidated". But the standalone pages 194–197 name no basis, so they are also sent, and the model drew all 12 of its proposals from three of them. Every field was then `basis_unknown`, and under the configured basis `consolidated` nothing was extracted. Deciding the basis of those pages (OD-10 Options 2 and 3) would not help: they would become `standalone` and be ignored. What helps is not sending pages whose basis cannot be established, when other pages establish the configured basis.

The change only narrows what is sent. A statement that really is of the configured basis but whose title names none is not read, so the result has fewer fields, never a wrong field. Pages naming the *other* basis are left as they are today (still sent, their fields ignored afterwards).

## 2. Current text (v0.4.20)

H.4.6, "Configured basis absent" (unchanged by this draft):

> if no candidate page has a statement title of the configured basis, the run stops **before any LLM call** with `E-EXTRACT-BASIS-UNAVAILABLE`, which lists the bases found. …

FR-013, recording: `excluded_candidates` holds one entry per excluded (page, statement type) pair, with `reason` either `"cap"` or `"chain_cut"`.

## 3. Proposed wording

### H.4.6 — add after "Configured basis absent"

> - **Pages of unknown basis are not sent (v0.4.21).** When the gate above passes, a candidate page whose basis is `unknown` is removed from the candidate pages before any model call, and is recorded in `excluded_candidates` with reason `basis_unknown`. A page's basis is the basis of its own title block (H.4.6); if it has none, that of the first page of its statement run, as for a field (the run start of FR-013 rule 6). A page that qualifies for several statement types is removed only if its basis is `unknown` for every one of them. A removed page frees no place under the candidate cap (no refill), as for the chain rule.
> - **Not applied to a `--pages` run:** the analyst chose those pages, so none is removed, and a field read from an unknown-basis page is `requires_review` (`basis_unknown`) as before.
> - **Unchanged:** pages whose title names the other basis are still sent and their fields are ignored (D-06); the gate is evaluated on all candidates before any removal, so `E-EXTRACT-BASIS-UNAVAILABLE` and the list of bases found are as before; the memo's note of other bases present is unchanged. The removed pages' count is reported in the manifest (Phase 5) and in the run's counts.

### FR-013 — recording

> `reason` is `"cap"`, `"chain_cut"` or `"basis_unknown"` (v0.4.21). For `basis_unknown`, `chain_start_page` is the original first page of the chain for that type, as for the other reasons, and `score` is the page's rule-4 score.

## 4. Effects

- **R1 (consolidated):** the model would see pages 274–277 (and any other page of the consolidated run) and not 194–197 (unknown basis) nor, if its title block names no basis, page 242 (not examined). Fewer tokens, and the proposals come from statements of the configured basis.
- **R2:** unchanged; the gate fails first and nothing is sent (the owner confirmed R2 is consolidated, which is why `E-EXTRACT-BASIS-UNAVAILABLE` is the recorded finding until Option 3 exists).
- **A document with one untitled statement type and titled others:** the untitled statement is not read. For example, if only the balance sheet is titled "consolidated", the income-statement fields come back `not_found`, not guessed. This is the cost of the rule and the reason it stays out of `--pages` runs.
- **Response cache:** the candidate pages are part of the cache key (FR-003.5), so a changed page set is a new call, not a replay.
- **Code affected when approved:** `locator.py` (a function to apply the exclusion after the gate and record it), `models.py` (the reason value), `pipeline.py` (call it between the gate and `extract_fields`), summary and counts.

## 5. New acceptance examples (Appendix B.6 or the FR-013 table, to be added)

| # | Case | Expected |
|---|---|---|
| 28 | Configured `consolidated`. Pages 10–11 titled with no basis word; pages 20–21 titled "Consolidated …" | Gate passes. Candidates sent: 20–21. `excluded_candidates` holds entries for 10 and 11 with reason `basis_unknown` |
| 29 | Only untitled-basis pages | The gate fails first: `E-EXTRACT-BASIS-UNAVAILABLE` ("bases found: unknown"); nothing excluded, nothing sent |
| 30 | A continuation page with no title, following a consolidated-titled first page | Kept (basis inherited from the run start) |
| 31 | A continuation page with no title, following an untitled first page | Removed (`basis_unknown`) |
| 32 | `--pages` run on an untitled page | Nothing removed; the page is sent; its fields `requires_review` (`basis_unknown`) |
| 33 | A page titled "Standalone …" while the configured basis is `consolidated` | Still sent, as today; its fields are ignored later (D-06) |
| 34 | A page that qualifies as balance sheet and income statement, basis known for one type chain only | Kept (removed only if unknown for every type) |

## 6. Tests, when approved (synthetic PDFs generated at test time)

One test per row 28 to 34; a property test that no page of unknown basis is ever among the pages sent when the gate passes and the run is not `--pages`; a check that the removed set plus the sent set equals the candidates before removal; a pipeline test with a fake provider asserting the prompt's page numbers; a replay-free check that the cache key changes with the page set.

## 7. Revision History row (draft)

| 0.4.21 | (date of approval) | **Specification change to H.4.6 and FR-013, authorised by the project owner on (date).** Resolves the part of OD-10 that decides what is sent, not what a no-title statement's basis is: when the basis gate passes, candidate pages whose basis is `unknown` are removed before the model call and recorded in `excluded_candidates` with the new reason `basis_unknown`; not applied to `--pages` runs; pages naming the other basis are unchanged. OD-10 options 2 and 3 (footnote evidence, page-scoped analyst assertion) are accepted for Phase 5 and are not applied here; option 4 (automatic basis for a no-title statement) is rejected. Evidence: the G5 run on tuning document R1, counts only. Appendix A.2/A.3 OD-10 rows updated. |

## 8. Decisions needed from the owner

1. Adopt the H.4.6 wording as drafted, change it, or reject it.
2. The `--pages` exception: keep, or apply the exclusion there too.
3. Whether a page qualifying for several types is removed only if unknown for every type (as drafted).
4. Whether I apply it to `docs/PRD.md` as v0.4.21 on your word, then implement.
