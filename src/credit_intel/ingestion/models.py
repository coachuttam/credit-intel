"""Data passed between ingestion steps."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfInspection:
    """Structural facts about a PDF, reported by a TextExtractor."""

    page_count: int
    is_encrypted: bool


@dataclass(frozen=True)
class FileInfo:
    """A validated input file (FR-001)."""

    path: Path
    file_name: str
    size_bytes: int
    sha256: str
    page_count: int
