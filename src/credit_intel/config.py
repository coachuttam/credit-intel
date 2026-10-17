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
