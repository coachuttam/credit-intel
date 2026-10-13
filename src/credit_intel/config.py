"""Application settings with PRD defaults.

Settings are plain frozen dataclasses so tests (and, later, a TOML loader)
can override individual values without touching code.
"""

from dataclasses import dataclass, field

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
            ),
            BALANCE_SHEET: ("balance sheet", "statement of financial position"),
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
            ),
        }
    )
    min_line_items_with_title: int = 2
    min_line_items_without_title: int = 4
    title_weight: int = 3
    max_candidates: int = 15  # FR-013; matches the SC-10 assumption
    # Words in a statement title that establish its basis (H.4.6).
    basis_phrases: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            CONSOLIDATED: ("consolidated",),
            STANDALONE: ("standalone", "separate"),
        }
    )
