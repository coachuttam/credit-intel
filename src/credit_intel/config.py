"""Application settings with PRD defaults.

Settings are plain frozen dataclasses so tests (and, later, a TOML loader)
can override individual values without touching code.
"""

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from credit_intel.ingestion.errors import ErrorCode, IngestionError

MEGABYTE = 1024 * 1024


@dataclass(frozen=True)
class IngestionSettings:
    """Limits applied when validating an input PDF (PRD FR-001)."""

    max_file_bytes: int = 25 * MEGABYTE  # FR-001.2
    max_pages: int = 400  # FR-001.3


INCOME_STATEMENT = "income_statement"
BALANCE_SHEET = "balance_sheet"

CONSOLIDATED = "consolidated"
STANDALONE = "standalone"
STATEMENT_BASES = (CONSOLIDATED, STANDALONE)


@dataclass(frozen=True)
class LocatorSettings:
    """Statement-page locator settings (PRD FR-013, H.4.6).

    The initial values come from the PRD's FR-013 table. They are provisional:
    not yet validated on real documents (OD-3), and may be adjusted only from
    tuning-set evidence, never from held-out documents (PRD O.2).
    """

    title_phrases: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            INCOME_STATEMENT: (
                "statement of profit and loss",
                "statement of profit or loss",
                "profit and loss statement",
                "income statement",
                "statement of comprehensive income",
                "income statements",  # v0.4 addition (PRD FR-013 table)
            ),
            BALANCE_SHEET: (
                "balance sheet",
                "statement of financial position",
                "balance sheets",  # v0.4 addition (PRD FR-013 table)
            ),
        }
    )
    line_item_phrases: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            INCOME_STATEMENT: (
                "revenue from operations",
                "total income",
                "total expenses",
                "finance costs",
                "profit before tax",
                "tax expense",
                "profit for the year",
                # v0.4 additions (PRD FR-013 settings table). Provenance per
                # phrase is tracked in PROGRESS.md (AC-E-7); not asserted here.
                "finance cost",
                "total revenue",
                "operating income",
                "income before income taxes",
                "net income",
            ),
            BALANCE_SHEET: (
                "total non-current assets",
                "total current assets",
                "total assets",
                "total equity",
                "total non-current liabilities",
                "total current liabilities",
                "total equity and liabilities",
                "borrowings",
                # v0.4 additions (PRD FR-013 settings table). Provenance per
                # phrase is tracked in PROGRESS.md (AC-E-7); not asserted here.
                "total liabilities",
                "total stockholders' equity",
                "total liabilities and stockholders' equity",
                "long-term debt",
                "short-term debt",
            ),
        }
    )
    min_line_items_with_title: int = 2
    min_line_items_without_title: int = 4
    title_weight: int = 3
    max_candidates: int = 15  # FR-013; matches the SC-10 assumption
    # v0.4 (Stage A): words that may precede a title phrase in a title line,
    # and the connectors that may join two of them (G.0, LOC-4). "comprehensive"
    # is deliberately not a prefix (P1-5). Both lists are closed.
    title_prefix_words: tuple[str, ...] = ("consolidated", "standalone", "separate")
    prefix_connectors: tuple[str, ...] = ("and", "&")
    # v0.4 (rule 3c, LOC-1): statements that are not located but end a
    # continuation chain. Phrase list specified by the PRD; provenance status
    # is tracked in PROGRESS.md.
    other_statement_title_phrases: tuple[str, ...] = ("comprehensive income statements",)
    # Words in a statement title that establish its basis (H.4.6).
    basis_phrases: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            CONSOLIDATED: ("consolidated",),
            STANDALONE: ("standalone", "separate"),
        }
    )


@dataclass(frozen=True)
class ColumnSettings:
    """Period-column check settings (PRD FR-005.7, OD-1).

    Provisional: retained for the synthetic tests only, not validated against a
    sufficient real-report sample, and adjustable only from tuning-set evidence
    (PRD O.2).
    """

    column_margin_pt: float = 3  # added each side of a period anchor's extent
    line_tolerance_pt: float = 3  # words whose vertical centres differ by at most this share a line


@dataclass(frozen=True)
class FieldLabelRule:
    """The row labels accepted for one field (PRD H.3, FR-005.10).

    ``phrases`` are accepted anywhere. ``sectioned_phrases`` (for example a bare
    "borrowings") are accepted only under a ``section`` heading.
    """

    phrases: tuple[str, ...]
    sectioned_phrases: tuple[str, ...] = ()
    section: str | None = None  # a key of LabelSettings.section_headings


NON_CURRENT = "non_current"
CURRENT = "current"


@dataclass(frozen=True)
class LabelSettings:
    """Row-label phrases per field and section headings (PRD H.3, FR-005.10).

    Initial values are the H.3 table's. They may be extended only from tuning-set
    evidence, never from held-out documents (PRD O.2).
    """

    rules: dict[str, FieldLabelRule] = field(
        default_factory=lambda: {
            "revenue": FieldLabelRule(("revenue from operations", "revenue", "turnover")),
            "net_profit": FieldLabelRule(
                (
                    "profit/(loss) for the year",
                    "profit for the year",
                    "profit/(loss) for the period",
                    "profit for the period",
                )
            ),
            "operating_profit": FieldLabelRule(("operating profit", "ebit")),
            "profit_before_tax": FieldLabelRule(
                ("profit/(loss) before tax", "profit before tax")
            ),
            "interest_expense": FieldLabelRule(("finance costs", "interest expense")),
            "current_assets": FieldLabelRule(("total current assets",)),
            "current_liabilities": FieldLabelRule(("total current liabilities",)),
            "total_borrowings": FieldLabelRule(("total borrowings",)),
            "borrowings_non_current": FieldLabelRule(
                ("non-current borrowings",), ("borrowings",), NON_CURRENT
            ),
            "borrowings_current": FieldLabelRule(
                ("current borrowings",), ("borrowings",), CURRENT
            ),
            "current_maturities_long_term_borrowings": FieldLabelRule(
                (
                    "current maturities of long-term borrowings",
                    "current maturities of long-term debt",
                )
            ),
            "total_equity": FieldLabelRule(("total equity",)),
        }
    )
    section_headings: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            NON_CURRENT: ("non-current liabilities",),
            CURRENT: ("current liabilities",),
        }
    )


# The statement a field is read from (H.3), for finding the first page of its statement
# run (FR-013 rule 6, FR-005.8). The PRD does not tabulate this; it follows from the labels.
FIELD_STATEMENT_TYPES: dict[str, str] = {
    "revenue": INCOME_STATEMENT,
    "net_profit": INCOME_STATEMENT,
    "operating_profit": INCOME_STATEMENT,
    "profit_before_tax": INCOME_STATEMENT,
    "interest_expense": INCOME_STATEMENT,
    "current_assets": BALANCE_SHEET,
    "current_liabilities": BALANCE_SHEET,
    "total_borrowings": BALANCE_SHEET,
    "borrowings_non_current": BALANCE_SHEET,
    "borrowings_current": BALANCE_SHEET,
    "current_maturities_long_term_borrowings": BALANCE_SHEET,
    "total_equity": BALANCE_SHEET,
}


@dataclass(frozen=True)
class DeclarationSettings:
    """Phrases that declare a scale or a currency (PRD FR-005.8).

    FR-005.8 says the phrase lists are configurable and gives only examples
    ("₹ in crore", "(Rs. in lakh)", "USD '000", "in millions"). These initial lists
    are built from them, are provisional, and may be extended only from tuning-set
    evidence (PRD O.2). A scale is declared by "in" followed by one of its words, with
    an optional currency token between; a thousands scale may also be written '000.
    """

    scale_words: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "crore": ("crore", "crores"),
            "lakh": ("lakh", "lakhs", "lac", "lacs"),
            "millions": ("million", "millions", "mn"),
            "billions": ("billion", "billions", "bn"),
            "thousands": ("thousand", "thousands"),
            "units": ("units", "actuals", "absolute figures", "absolute numbers", "absolute amounts"),
        }
    )
    # Currency names that, after "in", declare whole units ("in rupees").
    unit_currency_words: tuple[str, ...] = ("rupees", "dollars", "euros", "pounds", "dirhams")
    # ISO code -> symbols and names that support it (the ISO code itself always does).
    currency_tokens: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "INR": ("₹", "rs.", "rs", "rupee", "rupees"),
            "USD": ("$", "us$", "dollar", "dollars", "us dollar", "us dollars"),
            "EUR": ("€", "euro", "euros"),
            "GBP": ("£", "pound", "pounds", "pound sterling"),
            "AED": ("dirham", "dirhams"),
            "JPY": ("¥", "yen"),
        }
    )


# --- LLM settings (PRD D-02, NFR-09, OD-8) -----------------------------------

DEFAULT_SETTINGS_PATH = Path("config/settings.toml")
LLM_PROVIDERS = ("openai", "fake")
LLM_SETTING_NAMES = ("provider", "model_id", "token_ceiling", "max_output_tokens")

# Environment overrides (D-02: "overridable by environment variable"). The names
# are this implementation's choice; an empty value counts as set, and is invalid.
ENV_LLM_PROVIDER = "CREDIT_INTEL_LLM_PROVIDER"
ENV_LLM_MODEL_ID = "CREDIT_INTEL_LLM_MODEL_ID"
ENV_TOKEN_CEILING = "CREDIT_INTEL_TOKEN_CEILING"
ENV_MAX_OUTPUT_TOKENS = "CREDIT_INTEL_MAX_OUTPUT_TOKENS"


@dataclass(frozen=True)
class LLMSettings:
    """Provider, model, per-run token ceiling and per-call output limit.

    There are no defaults: the token ceiling is a required setting (OD-8,
    NFR-09), and provider and model ID are configuration values, never
    hard-coded in modules (D-02). The maximum output tokens is the per-call limit
    sent to the provider, reserved against the ceiling (NFR-09) and part of the
    response-cache key (FR-003.5).
    """

    provider: str
    model_id: str
    token_ceiling: int
    max_output_tokens: int


def _invalid(setting: str) -> IngestionError:
    # The detail names the setting only, never its value.
    return IngestionError(ErrorCode.CONFIG_INVALID, setting)


def _text(value: object, setting: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(setting)
    return value.strip()


def _positive_int(file_value: object, env_value: str | None, setting: str) -> int:
    """A positive integer: ASCII digits from the environment, or a TOML integer."""
    if env_value is not None:
        if not re.fullmatch(r"[0-9]+", env_value):
            raise _invalid(setting)
        file_value = int(env_value)
    if isinstance(file_value, bool) or not isinstance(file_value, int) or file_value < 1:
        raise _invalid(setting)
    return file_value


def load_llm_settings(
    path: Path = DEFAULT_SETTINGS_PATH, env: Mapping[str, str] | None = None
) -> LLMSettings:
    """Read the ``[llm]`` table of the settings file; environment variables override it.

    Raises ``IngestionError`` with ``E-CONFIG-INVALID`` (detail: the setting's
    name) if the file is missing or unparsable, a setting is unknown, missing or
    invalid, or the token ceiling is absent. The token ceiling must be a positive
    integer; zero, negative, non-integer and boolean values are rejected.
    """
    env = os.environ if env is None else env
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise _invalid("settings file") from exc
    table = data.get("llm", {})
    if not isinstance(table, dict):
        raise _invalid("llm")
    for name in table:
        if name not in LLM_SETTING_NAMES:
            raise _invalid(f"llm.{name}")

    provider = _text(env.get(ENV_LLM_PROVIDER, table.get("provider")), "llm.provider")
    if provider not in LLM_PROVIDERS:
        raise _invalid("llm.provider")
    model_id = _text(env.get(ENV_LLM_MODEL_ID, table.get("model_id")), "llm.model_id")
    token_ceiling = _positive_int(
        table.get("token_ceiling"), env.get(ENV_TOKEN_CEILING), "llm.token_ceiling"
    )
    max_output_tokens = _positive_int(
        table.get("max_output_tokens"),
        env.get(ENV_MAX_OUTPUT_TOKENS),
        "llm.max_output_tokens",
    )
    return LLMSettings(
        provider=provider,
        model_id=model_id,
        token_ceiling=token_ceiling,
        max_output_tokens=max_output_tokens,
    )
