"""Row-label check (PRD FR-005.10, D-10; H.3).

The row's label is the text before its first figure, where a note reference counts
as a figure (and so does a nil dash or the word nil). It is normalised as in FR-013
rule 1, leading item markers are removed, and the result must equal a configured
phrase of the field (H.3). A bare "borrowings" is accepted only under the matching
liabilities heading (the nearest preceding heading line on the page; a total of
liabilities met first ends the section, and no heading found is a failure).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from credit_intel.config import LabelSettings
from credit_intel.ingestion.locator import fold_phrase, is_nil_token, is_numeric_token

# A leading item marker: Roman numerals, one letter or digits, bare or in brackets or
# followed by "." or ")" (applied after casefolding).
_ROMAN = r"m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
_MARKER = re.compile(
    rf"(?:\(\s*(?:[0-9]+|[a-z]|{_ROMAN})\s*\)|(?:[0-9]+|[a-z]|{_ROMAN})\s*[.)]|(?:[0-9]+|[a-z]|{_ROMAN}))(?=\s|$)"
)


def _is_figure(word: str) -> bool:
    return is_numeric_token(word) or is_nil_token(word)


def row_label(line_text: str) -> str:
    """The text before the line's first figure (a note reference or nil dash counts)."""
    words: list[str] = []
    for word in line_text.split():
        if _is_figure(word):
            break
        words.append(word)
    return " ".join(words)


def strip_item_markers(folded: str) -> str:
    """Remove leading item markers from a casefolded label (repeatedly)."""
    text = folded.strip()
    while True:
        match = _MARKER.match(text)
        if match is None or not match.group():
            return text
        remainder = text[match.end() :].strip()
        if not remainder:  # a label that is only a marker has no text left to match
            return ""
        text = remainder


def normalise_label(label: str) -> str:
    return strip_item_markers(fold_phrase(label))


def _heading_text(line: str) -> str:
    return normalise_label(row_label(line)).rstrip(":").strip()


def section_heading(
    lines: Sequence[str], index: int, settings: LabelSettings | None = None
) -> str | None:
    """The liabilities section a row at ``lines[index]`` belongs to, or ``None``.

    Scans upward for the nearest line that is a heading (its normalised text equals
    a configured heading). A line starting with "total" and naming liabilities ends
    the section, so a row after a total is never placed in the section above it.
    """
    settings = settings or LabelSettings()
    headings = {
        fold_phrase(phrase): section
        for section, phrases in settings.section_headings.items()
        for phrase in phrases
    }
    for line in reversed(lines[:index]):
        text = _heading_text(line)
        if text in headings:
            return headings[text]
        if text.startswith("total") and "liabilities" in text:
            return None
    return None


@dataclass(frozen=True)
class LabelCheck:
    ok: bool
    label: str  # the text before the first figure, as printed
    normalised: str
    matched_phrase: str | None
    section: str | None  # the heading found, for a sectioned phrase


def check_label(
    field_name: str,
    figure_line: str,
    page_lines: Sequence[str] | None = None,
    line_index: int | None = None,
    settings: LabelSettings | None = None,
) -> LabelCheck:
    """FR-005.10 for one field on one figure line.

    ``page_lines`` and ``line_index`` locate the figure line on its page; they are
    needed only for a phrase that is accepted under a section heading.
    """
    settings = settings or LabelSettings()
    label = row_label(figure_line)
    normalised = normalise_label(label)
    rule = settings.rules.get(field_name)
    if rule is None:
        return LabelCheck(False, label, normalised, None, None)
    for phrase in rule.phrases:
        if normalised == fold_phrase(phrase):
            return LabelCheck(True, label, normalised, phrase, None)
    for phrase in rule.sectioned_phrases:
        if normalised == fold_phrase(phrase):
            heading = (
                section_heading(page_lines, line_index, settings)
                if page_lines is not None and line_index is not None
                else None
            )
            return LabelCheck(heading == rule.section, label, normalised, phrase, heading)
    return LabelCheck(False, label, normalised, None, None)
