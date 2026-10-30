"""The report check (PRD FR-015 criterion 5, v0.4.56): is the PDF the memo, and nothing else? Deterministic, no model.

``problems(pdf, memo)`` reads the PDF back and returns a list of what is wrong, empty when it is sound. A report that has any problem is
not written (criterion 7). The messages are about counts and places only: they never quote the memo or the PDF, because the text could
be a document's.

What it checks, on the text of each page (the body above the footer, and the footer, read separately by their place on the page):

* **Labels.** The origin labels of the PDF are exactly the labels of the memo, the same number of each: none missing, none added.
* **The draft statement** is on the first page and in the footer of every page, in the memo's words; each footer also has the run ID and
  ``Page n of N`` with the right numbers.
* **The text.** Every word of the memo is in the body of the PDF the same number of times, and no other word is: no value is dropped,
  repeated, altered (a swapped digit is a different word) or invented. The one allowed addition is the words of a table's header row, which
  is repeated at the top of each page that the table continues onto, at most once per page. A "word" is a run of characters between spaces,
  with the punctuation at its ends removed and words without a letter or digit (bullets, dashes) dropped, so layout does not matter. The
  check proves that the same words are present, not their order: the order is the memo's, because the typesetter walks the memo in order. Section 9 (limitations and human-review requirements) is compared again on its own, so a dropped limitation is named.
* **OCR.** For a memo that has OCR labels, every OCR label and the OCR legend line are in the PDF.
* **Nothing is loaded or linked.** The PDF holds no image, link, annotation, script, launch action or embedded file.

* **Charts** (when the report has them): each plotted slot has a row in the memo's tables with the same ID, displayed string and label, and
  its height is the stored value (``charts.traceability``); the words and labels the charts print are expected in the PDF, so a chart
  cannot carry a number or a label that is not in the data list that was checked against the memo.
"""

import io
import re
from collections import Counter

import pdfplumber
from reportlab.lib.units import mm

from credit_intel.memo.sections import DRAFT_STATEMENT
from credit_intel.memo.trace import FORMS
from credit_intel.report import charts as chart_module
from credit_intel.report.mdparse import parser

FOOTER_HEIGHT = 29 * mm  # the page's bottom margin: the footer sits in it (see typeset.py)
LABEL = re.compile(r"\[([^\]]*)\]")
FORBIDDEN = (b"/URI", b"/Annots", b"/Subtype /Image", b"/JavaScript", b"/JS ", b"/Launch", b"/OpenAction", b"/AA ", b"/EmbeddedFile", b"/XFA", b"/GoTo")
SECTION_9 = "9. Limitations and human-review requirements"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()  # \s covers the non-breaking spaces inside labels


def _labels(text: str) -> Counter:
    return Counter(m.group(0) for m in LABEL.finditer(_flat(text)) if any(form.fullmatch(m.group(1)) for form in FORMS))


def _memo_text(memo: str) -> str:
    """Everything the memo prints, from its own tokens: text, code, image alt text, raw HTML as text, code blocks and list numbers."""
    parts: list[str] = []
    for token in parser().parse(memo):
        if token.type == "inline":
            parts.append("".join(" " if child.type in ("softbreak", "hardbreak") else child.content for child in token.children or []))
        elif token.type in ("fence", "code_block", "html_block"):
            parts.append(token.content)
        elif token.type == "list_item_open" and token.info:
            parts.append(token.info)  # an ordered list's number
    return "\n".join(parts)


def _header_bag(memo: str) -> Counter:
    """The words of the header rows of every table of the memo, once each."""
    bag: Counter = Counter()
    inside = False
    for token in parser().parse(memo):
        if token.type == "thead_open":
            inside = True
        elif token.type == "thead_close":
            inside = False
        elif inside and token.type == "inline":
            bag += _bag("".join(child.content for child in token.children or []))
    return bag


def _bag(text: str) -> Counter:
    """The words of ``text``: split on whitespace, punctuation at the ends removed, words with no letter or digit dropped."""
    words = (re.sub(r"^[^\w(]+|[^\w)]+$", "", word) for word in text.split())
    return Counter(word for word in words if any(ch.isalnum() for ch in word))


def _difference(expected: Counter, found: Counter, allowance: Counter | None = None) -> tuple[int, int]:
    """Words missing from ``found``, and words added beyond ``expected`` and the ``allowance``."""
    return sum((expected - found).values()), sum(((found - expected) - (allowance or Counter())).values())


def read_pages(pdf: bytes) -> tuple[list[str], list[str]]:
    """The body text and the footer text of each page, split by their place on the page."""
    bodies, footers = [], []
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for page in doc.pages:
            cut = page.height - FOOTER_HEIGHT
            bodies.append(page.crop((0, 0, page.width, cut)).extract_text() or "")
            footers.append(page.crop((0, cut, page.width, page.height)).extract_text() or "")
    return bodies, footers


def problems(pdf: bytes, memo: str, charts: list | None = None, results: dict | None = None) -> list[str]:
    found: list[str] = []
    chart_text = ""
    if charts:
        if results is None:
            return ["the charts cannot be checked without the results"]
        found += chart_module.traceability(charts, memo, results, parser().parse)
        chart_text = chart_module.charts_text(charts)
    for name in FORBIDDEN:
        if name in pdf:
            found.append("the PDF contains a feature that loads or links something")
            break
    try:
        bodies, footers = read_pages(pdf)
    except Exception:
        return [*found, "the PDF cannot be read back"]
    if not bodies:
        return [*found, "the PDF has no pages"]

    body = "\n".join(bodies)
    run = re.search(r"\*\*Run ID:\*\* `([^`]+)`", memo)

    # labels
    expected_labels, found_labels = _labels(memo) + _labels(chart_text), _labels(body)
    if expected_labels != found_labels:
        missing, added = sum((expected_labels - found_labels).values()), sum((found_labels - expected_labels).values())
        found.append(f"origin labels differ: {missing} missing, {added} added")

    # the draft statement and the footers
    if DRAFT_STATEMENT not in _flat(bodies[0]):
        found.append("the draft statement is not on the first page")
    total = len(bodies)
    for number, footer in enumerate(footers, start=1):
        text = _flat(footer)
        if DRAFT_STATEMENT not in text:
            found.append(f"the draft statement is not in the footer of page {number}")
        if run is None or f"Run ID {run.group(1)}" not in text or f"Page {number} of {total}" not in text:
            found.append(f"the footer of page {number} lacks the run ID or the page numbers")

    # the text
    repeats = Counter({word: n * (total - 1) for word, n in _header_bag(memo).items()})  # a table header may repeat on each later page
    missing, added = _difference(_bag(_memo_text(memo) + "\n" + chart_text), _bag(body), repeats)
    if missing or added:
        found.append(f"the text differs from the memo: {missing} words missing, {added} added")

    # section 9 on its own
    start = memo.find("\n## 9. ")
    flat_body = _flat(body)
    at = flat_body.rfind(SECTION_9)
    if start == -1 or at == -1:
        found.append("section 9 is not in the report")
    else:
        missing, added = _difference(_bag(_memo_text(memo[start:])), _bag(flat_body[at:]), repeats)
        if missing or added:
            found.append(f"section 9 differs from the memo: {missing} words missing, {added} added")

    # OCR
    ocr_labels = [label for label in expected_labels if label.startswith("[OCR")]
    if ocr_labels and not all(found_labels[label] >= expected_labels[label] for label in ocr_labels):
        found.append("an OCR label is missing")
    if "Text read by OCR" in memo and "Text read by OCR" not in flat_body:
        found.append("the line that says which pages were read by OCR is missing")
    return found
