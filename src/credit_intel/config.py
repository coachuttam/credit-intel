"""Application settings with PRD defaults.

Settings are plain frozen dataclasses so tests (and, later, a TOML loader)
can override individual values without touching code.
"""

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
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
    extra_period_columns: int = 2  # older year-columns accepted beyond the comparative (PRD FR-005.9, v0.4.29)


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
            # Added 2026-10-25 from tuning-set evidence (PRD O.2): the income statement and balance sheet of tuning document
            # R2 (sha256 dfc1ed6c9bcd..., physical pages 36 and 38) print "Total revenue", "Operating income", "Income before
            # income taxes", "Net income" and "Total stockholders' equity". The owner approved the five phrases ("yes to all four").
            "revenue": FieldLabelRule(("revenue from operations", "revenue", "turnover", "total revenue")),
            "net_profit": FieldLabelRule(
                (
                    "profit/(loss) for the year",
                    "profit for the year",
                    "profit/(loss) for the period",
                    "profit for the period",
                    "net income",
                )
            ),
            "operating_profit": FieldLabelRule(("operating profit", "ebit", "operating income")),
            "profit_before_tax": FieldLabelRule(
                ("profit/(loss) before tax", "profit before tax", "income before income taxes")
            ),
            # "finance cost" (singular) added 2026-10-22 from tuning-set evidence (PRD O.2, AC-E-7): the
            # consolidated statement of profit and loss of tuning document R1 (sha256 a2b9acdfbe79...,
            # physical page 276) prints the row as "Finance cost". The owner approved it ("b yes").
            "interest_expense": FieldLabelRule(("finance costs", "finance cost", "interest expense")),
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
            "total_equity": FieldLabelRule(("total equity", "total stockholders' equity")),
        }
    )
    # A currency symbol standing alone as the last word before the first figure is not part of the row label
    # (PRD FR-005.10 criterion 10, v0.4.29): the non-alphabetic entries of the currency tokens, never a name or a code.
    currency_symbols: tuple[str, ...] = field(
        default_factory=lambda: tuple(t for tokens in DeclarationSettings().currency_tokens.values() for t in tokens if not t[0].isalpha())
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
class BorrowingSettings:
    """Phrases that classify current maturities of long-term borrowings (PRD H.5 rule 5, D-12).

    An inclusion phrase in the ``borrowings_current`` row label means current maturities are
    already inside it; an exclusion phrase in that label or in the current-maturities row label
    means they are a separate component. The initial values are the PRD's examples. They are
    provisional and may be extended only from tuning-set evidence (PRD O.2, AC-E-7).
    """

    inclusion_phrases: tuple[str, ...] = ("including current maturities",)
    exclusion_phrases: tuple[str, ...] = ("excluding current maturities",)


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
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"  # SEC-02, SEC-03: read from the process environment only
ENV_PRICE_INPUT = "CREDIT_INTEL_PRICE_INPUT_PER_MILLION"
ENV_PRICE_OUTPUT = "CREDIT_INTEL_PRICE_OUTPUT_PER_MILLION"
ENV_LIVE = "CREDIT_INTEL_LIVE"  # opt in to the live tests (value "1")
ENV_PRIVATE_APPROVED = "CREDIT_INTEL_PRIVATE_APPROVED"  # "1" is the owner's approval of one run on a document under private/ (v0.4.31)


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


@dataclass(frozen=True)
class PricingSettings:
    """Price of the configured model, in USD per million tokens (PRD D-02, NFR-09).

    There are no defaults: a price is a fact about the provider that is verified and then
    entered (D-02), never assumed. Without a ``[pricing]`` table no cost is estimated.
    """

    input_per_million: Decimal
    output_per_million: Decimal


def _price(file_value: object, env_value: str | None, setting: str) -> Decimal:
    """A non-negative finite decimal: a TOML integer or float, or a decimal string from the environment."""
    if env_value is not None:
        if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", env_value):
            raise _invalid(setting)
        return Decimal(env_value)
    if isinstance(file_value, bool) or not isinstance(file_value, (int, float)):
        raise _invalid(setting)
    value = Decimal(str(file_value))  # a float's shortest text, so 0.15 stays 0.15
    if not value.is_finite() or value < 0:
        raise _invalid(setting)
    return value


def load_pricing(
    path: Path = DEFAULT_SETTINGS_PATH, env: Mapping[str, str] | None = None
) -> PricingSettings | None:
    """The ``[pricing]`` table of the settings file, or ``None`` if it has none.

    Environment variables override the file. A table with a missing, negative, boolean or
    otherwise invalid price fails with ``E-CONFIG-INVALID`` naming the setting.
    """
    env = os.environ if env is None else env
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise _invalid("settings file") from exc
    table = data.get("pricing")
    if table is None and ENV_PRICE_INPUT not in env and ENV_PRICE_OUTPUT not in env:
        return None
    if table is None:
        table = {}
    if not isinstance(table, dict):
        raise _invalid("pricing")
    for name in table:
        if name not in ("input_per_million", "output_per_million"):
            raise _invalid(f"pricing.{name}")
    return PricingSettings(
        input_per_million=_price(table.get("input_per_million"), env.get(ENV_PRICE_INPUT), "pricing.input_per_million"),
        output_per_million=_price(table.get("output_per_million"), env.get(ENV_PRICE_OUTPUT), "pricing.output_per_million"),
    )


# --- Page classification with Jev (PRD v0.4.31) ------------------------------------------------

ENV_USE_JEV = "USE_JEV"  # "true" or "false"; absent or empty is false
ENV_TYPESAFE_API_KEY = "TYPESAFE_API_KEY"  # SEC-02, SEC-03: read from the process environment only
ENV_JEV_API_KEY = "JEV_API_KEY"  # accepted as an alternative name for the same key; TYPESAFE_API_KEY wins if both are set
ENV_JEV_PRICE_INPUT = "CREDIT_INTEL_JEV_PRICE_INPUT_PER_MILLION"
STEP_PROVIDERS = {"classify": ("jev",), "extract": LLM_PROVIDERS}
JEV_SETTING_NAMES = (
    "model",
    "threshold",
    "timeout_seconds",
    "time_budget_seconds",
    "state_lines",
    "max_consecutive_failures",
    "price_input_per_million",
)


@dataclass(frozen=True)
class StepSettings:
    """The provider that does each step (v0.4.31): ``classify`` runs only when ``USE_JEV`` is true; ``extract`` is the ``[llm]`` provider."""

    classify: str = "jev"
    extract: str = "openai"


@dataclass(frozen=True)
class JevSettings:
    """Settings of the optional page-classification step. Provisional: tuned on the tuning set only (PRD O.2).

    ``enabled`` is ``USE_JEV``. ``threshold`` is the confidence (0 to 1) a label needs before a page may be dropped.
    ``timeout_seconds`` bounds each call; ``time_budget_seconds`` bounds all calls of one document; after
    ``max_consecutive_failures`` failures in a row Jev is skipped for the rest of the run. ``state_lines`` is how many lines
    from the top of a page Jev reads. ``price_input_per_million`` (USD) has no default (D-02): without it no Jev cost is estimated.
    """

    enabled: bool = False
    model: str = "jev-latest"
    threshold: float = 0.85
    timeout_seconds: float = 10.0
    time_budget_seconds: float = 60.0
    state_lines: int = 40
    max_consecutive_failures: int = 3
    price_input_per_million: Decimal | None = None


def typesafe_api_key(env: Mapping[str, str]) -> str | None:
    """The Jev API key from ``TYPESAFE_API_KEY`` or, failing that, ``JEV_API_KEY``; ``None`` if neither is set. Never logged or stored."""
    for name in (ENV_TYPESAFE_API_KEY, ENV_JEV_API_KEY):
        value = env.get(name, "").strip()
        if value:
            return value
    return None


def _switch(value: str | None, setting: str) -> bool:
    if value is None or value == "":
        return False
    folded = value.strip().casefold()
    if folded not in ("true", "false"):
        raise _invalid(setting)
    return folded == "true"


def _fraction(value: object, setting: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1:
        raise _invalid(setting)
    return float(value)


def _positive_number(value: object, setting: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) < 100_000:
        raise _invalid(setting)
    return float(value)


def _small_int(value: object, setting: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10_000:
        raise _invalid(setting)
    return value


def _settings_table(path: Path, name: str) -> dict:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise _invalid("settings file") from exc
    table = data.get(name, {})
    if not isinstance(table, dict):
        raise _invalid(name)
    return table


def load_step_settings(
    path: Path = DEFAULT_SETTINGS_PATH, llm_provider: str = "openai"
) -> StepSettings:
    """The ``[steps]`` table: which provider does each step. ``extract`` must be the ``[llm]`` provider.

    Raises ``IngestionError`` with ``E-CONFIG-INVALID`` (detail: the setting's name) for an unknown step or provider.
    """
    table = _settings_table(path, "steps")
    for name in table:
        if name not in STEP_PROVIDERS:
            raise _invalid(f"steps.{name}")
    classify = _text(table.get("classify", "jev"), "steps.classify")
    extract = _text(table.get("extract", llm_provider), "steps.extract")
    if classify not in STEP_PROVIDERS["classify"]:
        raise _invalid("steps.classify")
    if extract not in STEP_PROVIDERS["extract"] or extract != llm_provider:
        raise _invalid("steps.extract")
    return StepSettings(classify, extract)


def load_jev_settings(
    path: Path = DEFAULT_SETTINGS_PATH, env: Mapping[str, str] | None = None
) -> JevSettings:
    """The ``[jev]`` table of the settings file and ``USE_JEV``; with neither, Jev is off (v0.4.31).

    The switch is read from ``USE_JEV`` only (``true`` or ``false``; absent or empty is false). The API key is never read
    here (it is read from ``TYPESAFE_API_KEY`` when a client is built). An unknown or invalid setting fails with
    ``E-CONFIG-INVALID`` naming the setting and never its value.
    """
    env = os.environ if env is None else env
    if not _switch(env.get(ENV_USE_JEV), ENV_USE_JEV):
        return JevSettings()  # off: the [jev] table is not even read, so a run without the step is exactly as before
    table = _settings_table(path, "jev")
    for name in table:
        if name not in JEV_SETTING_NAMES:
            raise _invalid(f"jev.{name}")
    defaults = JevSettings()
    price: Decimal | None = None
    if ENV_JEV_PRICE_INPUT in env or "price_input_per_million" in table:
        price = _price(table.get("price_input_per_million"), env.get(ENV_JEV_PRICE_INPUT), "jev.price_input_per_million")
    return JevSettings(
        enabled=True,
        model=_text(table.get("model", defaults.model), "jev.model"),
        threshold=_fraction(table.get("threshold", defaults.threshold), "jev.threshold"),
        timeout_seconds=_positive_number(table.get("timeout_seconds", defaults.timeout_seconds), "jev.timeout_seconds"),
        time_budget_seconds=_positive_number(table.get("time_budget_seconds", defaults.time_budget_seconds), "jev.time_budget_seconds"),
        state_lines=_small_int(table.get("state_lines", defaults.state_lines), "jev.state_lines"),
        max_consecutive_failures=_small_int(table.get("max_consecutive_failures", defaults.max_consecutive_failures), "jev.max_consecutive_failures"),
        price_input_per_million=price,
    )
