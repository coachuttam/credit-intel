# Known issues

Open problems in the current code. Neither has been root-caused or fixed. Both were found on 2026-11-05 by an informal manual cross-check of memo output against the source pages. They are **not** part of the formal evaluation set (PRD section O.2), have no recorded reproduction, and no count of how often they occur has been measured.

## 1. `current_assets` can show a flat placeholder value

In the memo, `current_assets` has sometimes shown the value `10000.00`, which is inconsistent with its own quoted evidence (the quote on the cited page does not contain that figure).

- **Status:** open, not yet root-caused.
- **What a reader can do:** every figure in the memo is printed with its quote and page. Check the value against the quote, and the quote against the page. A value that does not match its quote must not be used.

## 2. `current_liabilities` evidence can cite the wrong balance-sheet line

In at least one run, the `evidence_quote` for `current_liabilities` cited a different balance-sheet line from the one the figure belongs to.

- **Status:** open, not yet root-caused.
- **What a reader can do:** as above. Compare the quoted line's label with the field it is attached to.

## What these mean for use

The memo is a draft for a human analyst, who verifies every figure against the cited source pages (see "The human-decision boundary" in the README). These two issues are exactly what that review exists to catch. They are also further reasons not to read any number from this tool as verified. No accuracy figure for real reports is claimed (README, "Status").

Wider limits of the tool are in the README ("Scope and limitations") and, for the held-out miss, in `docs/PHASE7c_findings_report.md`.
