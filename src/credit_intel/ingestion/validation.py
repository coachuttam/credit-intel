"""Input PDF validation (PRD FR-001).

Checks run cheapest-first, so the PDF parser only sees files that have
already passed the existence, size, and signature checks:

1. exists and readable     -> E-INPUT-NOT-FOUND
2. size within limit       -> E-INPUT-TOO-LARGE
3. starts with ``%PDF-``    -> E-INPUT-NOT-PDF
4. SHA-256 computed (read-only)
5. parseable               -> E-INPUT-CORRUPT
6. not encrypted           -> E-INPUT-ENCRYPTED
7. page count within limit -> E-INPUT-TOO-MANY-PAGES

The input file is only ever opened read-only.

Limitation: the file is opened several times (signature, hash, parse, and
later extraction). The SHA-256 identifies the bytes at hashing time; if the
file is replaced or edited during a run, later steps may read different
bytes. Inputs are assumed stable for the duration of a run. If that ever
needs enforcing, read the file once and parse from those in-memory bytes.
"""

import hashlib
from pathlib import Path

from credit_intel.config import IngestionSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.extractor import TextExtractor
from credit_intel.ingestion.models import FileInfo

PDF_SIGNATURE = b"%PDF-"


def validate_pdf(
    path: Path,
    settings: IngestionSettings | None = None,
    extractor: TextExtractor | None = None,
) -> FileInfo:
    """Validate ``path`` as a supported PDF, or raise ``IngestionError``."""
    settings = settings or IngestionSettings()
    if extractor is None:
        from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

        extractor = PdfplumberExtractor()
    path = Path(path)

    try:
        with path.open("rb") as fh:
            head = fh.read(len(PDF_SIGNATURE))
        size_bytes = path.stat().st_size
    except OSError as exc:  # missing, directory, permission denied, ...
        raise IngestionError(ErrorCode.NOT_FOUND, detail=path.name) from exc

    if size_bytes > settings.max_file_bytes:
        raise IngestionError(
            ErrorCode.TOO_LARGE,
            detail=f"{size_bytes} bytes; limit {settings.max_file_bytes} bytes",
        )

    if head != PDF_SIGNATURE:
        raise IngestionError(ErrorCode.NOT_PDF, detail=path.name)

    try:
        with path.open("rb") as fh:
            sha256 = hashlib.file_digest(fh, "sha256").hexdigest()
    except OSError as exc:  # removed or made unreadable since the first check
        raise IngestionError(ErrorCode.NOT_FOUND, detail=path.name) from exc

    inspection = extractor.inspect(path)
    if inspection.is_encrypted:
        raise IngestionError(ErrorCode.ENCRYPTED)
    if inspection.page_count > settings.max_pages:
        raise IngestionError(
            ErrorCode.TOO_MANY_PAGES,
            detail=f"{inspection.page_count} pages; limit {settings.max_pages}",
        )

    return FileInfo(
        path=path,
        file_name=path.name,
        size_bytes=size_bytes,
        sha256=sha256,
        page_count=inspection.page_count,
    )
