"""Markdown-safe text, tables and origin labels for the memo (PRD K.0, K.10, FR-010.2).

Anything that came from a document or from the analyst (an entity name, a line-item label, a profile value,
an evidence quote) is escaped before it is written, so it cannot start a heading, add a table column, open a
link or look like an origin label such as ``[SOURCE: p.9]``. Labels are produced only by the functions here, from
data the run holds, and written unescaped; because escaping turns every ``[`` into ``\\[``, a label that is
written by this module is the only text in a memo that starts with an unescaped bracket (the traceability
test, K.10, relies on that).
"""

import re
from decimal import ROUND_HALF_EVEN, Decimal

SOURCE, CALCULATED, RULE, ANALYST, UNVERIFIED = "SOURCE", "CALCULATED", "RULE", "ANALYST-PROVIDED", "UNVERIFIED"
_SPECIAL = "\\`*_{}[]<>()#+!|~&"
_CONTROL = re.compile(r"[\x00-\x1f\x7f\u0085  ]+")
DASH = "—"  # nothing to show


def esc(value: object) -> str:
    """Text safe to place in a paragraph, list item or table cell: one line, punctuation escaped."""
    text = _CONTROL.sub(" ", str(value)).strip()
    return "".join("\\" + ch if ch in _SPECIAL else ch for ch in text)


def code(value: object) -> str:
    """An identifier in a code span. The ID formats contain no backtick, and one that did is refused."""
    text = str(value)
    if "`" in text or _CONTROL.search(text):
        raise ValueError("an identifier cannot contain a backtick or a control character")
    return f"`{text}`"


def source(page: int) -> str:
    return f"[SOURCE: p.{page}]"


def calculated(identifier: str) -> str:
    return f"[CALCULATED: {identifier}]"


def rule(identifier: str) -> str:
    return f"[RULE: {identifier}]"


ANALYST_LABEL = f"[{ANALYST}]"
UNVERIFIED_LABEL = f"[{UNVERIFIED}]"


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """A pipe table. Every cell must already be safe (see ``esc``); a row of the wrong width is a bug."""
    for row in rows:
        if len(row) != len(headers):
            raise ValueError("a table row must have one cell per header")
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(cell if cell else DASH for cell in row) + " |" for row in rows]
    return lines


def grouped(amount: str) -> str:
    """An exact decimal string with thousands separators and no change of value."""
    return format(Decimal(amount), ",f")


def rounded(value: str, places: int) -> str:
    """Display rounding, half to even (FR-007.4). The exact value stays in ``results.json``."""
    return format(Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN), "f")
