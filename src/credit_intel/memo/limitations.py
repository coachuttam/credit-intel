"""Memo section 9: limitations and human-review requirements (PRD K.1-K.9 row 9; Phase 5 step 5h).

Fixed text (written as plain Markdown, with none of the characters that need escaping; a test checks that), the same in every memo, except that the provisional-threshold notice is the one in the results.
Each statement restates a limit the PRD sets (the section named in brackets in the source comment).
"""

from typing import Any

from credit_intel.memo.text import calculated, esc  # esc is used for the configured notice only

SCOPE = [
    "Only text-based PDF files are read in this run. OCR of scanned pages is available but was not used, so a scanned page cannot be read here.",  # FR-001, D-03
    "One document is reviewed per run. Documents are not compared with each other.",
    "Two consecutive annual periods are read: the current period and the comparative period. 52/53-week reporting years, quarterly and interim periods are out of scope.",  # H.1.1
    "No currency conversion is done. If the figures a ratio needs are in different currencies, the ratio is not defined.",  # I.1
    "Figures are read from one statement basis, consolidated unless the analyst chose another. The basis is never switched automatically, and pages whose basis could not be determined are not sent for extraction.",  # H.4.6
    "Lease liabilities are excluded from borrowings, so a borrower with large leases shows a lower debt-to-equity ratio than a definition that includes them (D-07).",
    "A dash or the word nil in place of a figure is read as a zero reported by the document, and its original text is kept. A dash is never read as a sign (FR-004.3).",
]
METRICS = [
    "Revenue growth does not separate acquisitions, disposals, currency effects or changes in accounting policy. A single-year change may be noisy.",
    "Net profit margin is distorted by one-off items, discontinued operations and minority interests, and is not comparable across industries.",
    "The current ratio is a point-in-time measure that is sensitive to working-capital timing and to window dressing. It ignores the liquidity quality of inventory and receivables.",
    "Debt-to-equity uses interest-bearing borrowings excluding lease liabilities. Where no total of borrowings is reported, it is the sum of non-current and current borrowings, which may exclude current maturities shown under another caption.",
    "Finance costs may include lease interest, unwinding of discounts and foreign-exchange differences, so interest expense may not equal cash interest. EBIT derived from profit before tax inherits any one-off items.",
]
EXTRACTION = [
    "An AI model proposes the figures. Each is accepted only if its quote is found on the cited page and passes the checks for value, label, period column, sign, scale and currency. The model can miss an item or misread a page, so a field reported as not found is not proof that it is absent from the document.",
    "Non-current borrowings, current borrowings, current maturities of long-term borrowings and operating profit have often not been found when the system was tried on real annual reports. Without a reported total of borrowings or its components, debt-to-equity is not defined, and without operating profit EBIT comes from profit before tax plus interest expense.",
    "All arithmetic, the risk rules and the text of this memo are produced by fixed programs, not by the model. This memo contains no AI-generated commentary.",
    "Values supplied by the analyst in a profile are shown as given. They are not checked against the document and are not used in any calculation or rule.",
]
OCR_SCOPE = (
    "Pages without a text layer were read by OCR, an engine's reading of a page image, and the other pages from the text layer. "
    "A figure read by OCR is never accepted as extracted, is not used in any ratio or risk indicator, and must be checked against the page image. "
    "OCR reads English only, and its confidence is the engine's own figure, not a measure of correctness. "
    "Skewed or rotated pages are not corrected, so they may be read wrongly or fail the period column check, and a rotated page may not be readable at all. "
    "The period of an OCR page is often not verified, because the engine often does not read a full period-end date; the fields then stay under review for that reason too. "
    "OCR has been tried on a few real scanned pages and has not been measured on real scanned reports."
)
REVIEW = (
    "**This memo is a draft. A qualified human must review it, verify every figure against the cited source pages, and make any credit "
    "decision. It is not a credit decision, a rating or a score.**"
)


def section_9(results: dict[str, Any]) -> list[str]:
    lines = ["## 9. Limitations and human-review requirements", "", REVIEW, "", "**Scope**", ""]
    scope = [OCR_SCOPE if results["extraction"].get("ocr") and text is SCOPE[0] else text for text in SCOPE]
    lines += [f"- {text}" for text in scope]
    lines += ["", "**Ratios**", "", *(f"- {text}" for text in METRICS)]
    lines += ["", "**Risk indicators**", "",
              "- Indicators are prompts for human investigation. Severity says how urgently to look, not how creditworthy the borrower is.",
              f"- {esc(results['provisional_notice'])} {calculated('provisional_notice')}"]  # fmt: skip
    lines += ["", "**Extraction and automation**", "", *(f"- {text}" for text in EXTRACTION), ""]
    return lines
