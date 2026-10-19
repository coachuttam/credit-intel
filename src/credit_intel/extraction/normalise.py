"""Deterministic normalisation of a raw printed value (PRD FR-004.3, FR-004.4, H.1).

``parse_value`` turns the value string exactly as printed (``raw_value``) into a
``Decimal``. It is a pure function: no I/O, no randomness, no floats. Anything it
cannot read with certainty is unparsable and returns ``None``; the caller then marks
the field ``requires_review``. It never guesses.

What it accepts
- digits with an optional decimal part; thousands separators are optional, and when
  present must follow Western grouping (``1,234,567``) or Indian grouping
  (``12,34,567``). Malformed grouping (``1,2345``) is unparsable;
- negative as enclosing parentheses ``(1,234)`` or one attached minus
  (``-``, U+2212 or U+2013), never both;
- one currency symbol before the digits (``$ ₹ € £ ¥``), optionally followed by spaces;
- the nil convention (D-08): a value that is only a dash (``-``, ``–``, ``—``) or the
  word ``nil`` (any case) is a document-reported zero.

What it rejects (fail safe): a decimal comma, exponents, percent signs, a leading
plus, internal spaces (a split figure such as ``(4,901 )``), a leading or trailing
decimal point, non-ASCII digits after NFKC, and anything longer than 64 characters.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from credit_intel.models import Scale, StatusReason, ValueInterpretation

# FR-004.3 gives no reason code for an unparsable value, and the OD-1 proposal defers
# the reason-code policy (U-1, U-2). ``period_not_verified`` is the provisional
# placeholder named there, to be replaced when the owner decides.
UNPARSABLE_REASON = StatusReason.PERIOD_NOT_VERIFIED

MAX_LENGTH = 64

_MINUS = "-−–"  # FR-005.6: hyphen-minus, U+2212, U+2013
_NIL_DASHES = {"-", "–", "—"}  # FR-004.3: -, – or —
_SYMBOLS = "$₹€£¥"  # $ ₹ € £ ¥
CURRENCY_SYMBOLS = frozenset(_SYMBOLS)

_WESTERN = r"[0-9]{1,3}(?:,[0-9]{3})+"
_INDIAN = r"[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3}"
_PLAIN = r"[0-9]+"
_NUMBER = re.compile(rf"(?:{_PLAIN}|{_WESTERN}|{_INDIAN})(?:\.[0-9]+)?")
_VALUE = re.compile(
    rf"(?P<open>\()?(?P<minus>[{_MINUS}])?(?:(?P<symbol>[{re.escape(_SYMBOLS)}])[ ]*)?"
    rf"(?P<number>[0-9][0-9,.]*)(?P<close>\))?"
)

# Scale multipliers as powers of ten (H.1 ``scale``).
_SCALE_EXPONENT = {
    Scale.UNITS: 0,
    Scale.THOUSANDS: 3,
    Scale.LAKH: 5,
    Scale.MILLIONS: 6,
    Scale.CRORE: 7,
    Scale.BILLIONS: 9,
}


@dataclass(frozen=True)
class ParsedValue:
    """The result of reading a raw value.

    ``negative_marker`` is True when the raw value itself carries a negative marker
    (enclosing parentheses or an attached minus). The sign check (FR-005.6) also
    looks at the quote around the value; that is not done here.
    """

    value: Decimal
    interpretation: ValueInterpretation
    negative_marker: bool


def parse_value(raw: str) -> ParsedValue | None:
    """Read ``raw`` as printed, or return ``None`` if it cannot be read with certainty."""
    if not isinstance(raw, str):
        raise TypeError("raw value must be a string")
    text = unicodedata.normalize("NFKC", raw).strip()
    if not text or len(text) > MAX_LENGTH:
        return None

    if text.casefold() == "nil" or text in _NIL_DASHES:
        return ParsedValue(Decimal(0), ValueInterpretation.REPORTED_NIL, False)

    match = _VALUE.fullmatch(text)
    if match is None:
        return None
    parenthesised = (match["open"] is not None) + (match["close"] is not None)
    if parenthesised == 1:
        return None  # unbalanced parentheses
    if parenthesised == 2 and match["minus"] is not None:
        return None  # a double negative is not guessed
    if not _NUMBER.fullmatch(match["number"]):
        return None

    value = Decimal(match["number"].replace(",", ""))
    negative = parenthesised == 2 or match["minus"] is not None
    if negative:
        value = -value  # unary minus on zero stays +0, so there is no negative zero
    return ParsedValue(value, ValueInterpretation.NUMBER, negative)


def apply_scale(value: Decimal, scale: Scale) -> Decimal:
    """The value in base currency units (H.1): an exact shift of the decimal point.

    The result is written in positional form (``14823000000``, not ``1.4823E+10``).
    """
    return Decimal(format(value.scaleb(_SCALE_EXPONENT[Scale(scale)]), "f"))
