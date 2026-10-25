"""Sign, scale and currency checks (PRD FR-005.6 and FR-005.8).

Pure functions on text. Page texts are searched after the locator's folding (NFKC,
casefold, one space between words). A scale declaration is "in" followed by a scale
word, with an optional currency token between ("₹ in crore", "(Rs. in lakh)"), or a
thousands mark ('000). Phrase lists are settings (``DeclarationSettings``).
"""

import re
from dataclasses import dataclass

from credit_intel.config import DeclarationSettings
from credit_intel.extraction.normalise import ParsedValue
from credit_intel.ingestion.locator import fold_phrase
from credit_intel.models import Scale, StatusReason, ValueInterpretation

CITED_PAGE = "cited_page"
RUN_START = "run_start"


# --- sign (FR-005.6) ---------------------------------------------------------------


@dataclass(frozen=True)
class SignCheck:
    ok: bool
    marker_present: bool  # the occurrence on the page carries a negative marker
    negative: bool  # the parsed raw value is negative


def check_sign(raw: ParsedValue, token: ParsedValue) -> SignCheck:
    """The occurrence on the page and the parsed raw value must agree on the sign.

    ``token`` is the word the column check assigned (it includes enclosing brackets
    or an attached minus); ``raw`` is the model's raw value. A reported nil is never
    a sign and passes.
    """
    if raw.interpretation is ValueInterpretation.REPORTED_NIL and (
        token.interpretation is ValueInterpretation.REPORTED_NIL
    ):
        return SignCheck(True, False, False)
    return SignCheck(token.negative_marker == raw.negative_marker, token.negative_marker, raw.negative_marker)


# --- scale (FR-005.8) -----------------------------------------------------------------


def _alternation(words: tuple[str, ...]) -> str:
    return "|".join(re.escape(fold_phrase(w)) for w in sorted(words, key=len, reverse=True))


def _scale_patterns(settings: DeclarationSettings) -> tuple[tuple[Scale, re.Pattern[str]], ...]:
    connectors = tuple(t for tokens in settings.currency_tokens.values() for t in tokens) + tuple(
        code.lower() for code in settings.currency_tokens
    )
    optional_currency = rf"(?:(?:{_alternation(connectors)})\s+)?"
    all_scale_words = tuple(
        w for name, words in settings.scale_words.items() if name != "units" for w in words
    )
    patterns: list[tuple[Scale, re.Pattern[str]]] = []
    for name, words in settings.scale_words.items():
        scale = Scale(name)
        if scale is Scale.UNITS:
            names = words + settings.unit_currency_words
            # "in rupees crore" is a crore declaration, not a units one.
            body = rf"(?<![a-z])in\s+{optional_currency}(?:{_alternation(names)})(?![a-z])(?!\s+(?:{_alternation(all_scale_words)})(?![a-z]))"
        else:
            body = rf"(?<![a-z])in\s+{optional_currency}(?:{_alternation(words)})(?![a-z])"
        patterns.append((scale, re.compile(body)))
        if scale is Scale.THOUSANDS:
            marks = (
                r"(?<![0-9,.])'000s?(?![0-9])|\(000s?\)|(?<![0-9,.])000s(?![a-z0-9])"
                r"|(?<![a-z])in\s+000s?(?![0-9,.a-z])"
            )
            patterns.append((scale, re.compile(marks)))
    return tuple(patterns)


def find_scales(page_text: str, settings: DeclarationSettings | None = None) -> frozenset[Scale]:
    """The distinct scales declared in ``page_text``."""
    folded = fold_phrase(page_text)
    return frozenset(
        scale for scale, pattern in _scale_patterns(settings or DeclarationSettings()) if pattern.search(folded)
    )


@dataclass(frozen=True)
class ScaleCheck:
    ok: bool
    reason: StatusReason | None  # scale_not_verified or scale_ambiguous when not ok
    declared_on_cited_page: frozenset[Scale]
    declared_on_run_start: frozenset[Scale]
    supported_by: str | None  # CITED_PAGE or RUN_START


def check_scale(
    claimed: Scale,
    cited_page_text: str,
    run_start_text: str | None = None,
    settings: DeclarationSettings | None = None,
) -> ScaleCheck:
    """The claimed scale must be the one declared on the cited page.

    Two different scales on the cited page are ambiguous. If the cited page declares
    none, the first page of its statement run is used the same way. No declaration
    gives ``scale_not_verified``; a different one does too.
    """
    on_cited = find_scales(cited_page_text, settings)
    on_start = find_scales(run_start_text, settings) if run_start_text is not None else frozenset()
    if len(on_cited) > 1:
        return ScaleCheck(False, StatusReason.SCALE_AMBIGUOUS, on_cited, on_start, None)
    if on_cited:
        declared, source = on_cited, CITED_PAGE
    elif len(on_start) > 1:
        return ScaleCheck(False, StatusReason.SCALE_AMBIGUOUS, on_cited, on_start, None)
    elif on_start:
        declared, source = on_start, RUN_START
    else:
        return ScaleCheck(False, StatusReason.SCALE_NOT_VERIFIED, on_cited, on_start, None)
    if claimed in declared:
        return ScaleCheck(True, None, on_cited, on_start, source)
    return ScaleCheck(False, StatusReason.SCALE_NOT_VERIFIED, on_cited, on_start, None)


# --- currency (FR-005.8) ---------------------------------------------------------------


@dataclass(frozen=True)
class CurrencyCheck:
    ok: bool
    supported_by: str | None  # CITED_PAGE or RUN_START


def _has_currency(code: str, text: str, settings: DeclarationSettings) -> bool:
    # The ISO code is matched in capitals only, so "ALL" or "TRY" in prose is not a code.
    if re.search(rf"(?<![A-Za-z]){re.escape(code)}(?![A-Za-z])", text):
        return True
    folded = fold_phrase(text)
    for token in settings.currency_tokens.get(code, ()):
        pattern = re.escape(fold_phrase(token))
        if token[0].isalpha():
            pattern = rf"(?<![a-z]){pattern}"
        if token[-1].isalpha():
            pattern = rf"{pattern}(?![a-z])"
        if re.search(pattern, folded):
            return True
    return False


def find_currencies(text: str, settings: DeclarationSettings | None = None) -> frozenset[str]:
    """The distinct currency codes ``text`` declares by an ISO code, or by a symbol or name configured for one (PRD v0.4.36)."""
    settings = settings or DeclarationSettings()
    return frozenset(code for code in settings.currency_tokens if _has_currency(code, text, settings))


def check_currency(
    code: str,
    cited_page_text: str,
    run_start_text: str | None = None,
    settings: DeclarationSettings | None = None,
) -> CurrencyCheck:
    """The currency is supported by its ISO code, a symbol or a name on the cited page,
    or on the first page of its statement run."""
    settings = settings or DeclarationSettings()
    if _has_currency(code, cited_page_text, settings):
        return CurrencyCheck(True, CITED_PAGE)
    if run_start_text is not None and _has_currency(code, run_start_text, settings):
        return CurrencyCheck(True, RUN_START)
    return CurrencyCheck(False, None)
