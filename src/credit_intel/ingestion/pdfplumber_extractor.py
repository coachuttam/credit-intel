"""TextExtractor implementation backed by pdfplumber.

This is the only module that imports pdfplumber or pdfminer (PRD D-01).
"""

from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import PdfInspection

_ENCRYPTION_ERRORS = (PDFPasswordIncorrect, PDFEncryptionError)


def _is_encryption_error(exc: BaseException) -> bool:
    """True if ``exc`` or anything it wraps is a pdfminer encryption error.

    pdfplumber wraps pdfminer errors in ``PdfminerException``, so the
    original error may be in the exception chain or in ``args``.
    """
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, _ENCRYPTION_ERRORS):
            return True
        pending.extend(e for e in (current.__cause__, current.__context__) if e is not None)
        pending.extend(a for a in current.args if isinstance(a, BaseException))
    return False


class PdfplumberExtractor:
    def inspect(self, path: Path) -> PdfInspection:
        # The input is untrusted, so any failure inside the PDF library while
        # *parsing* it means the file cannot be processed. Each try block
        # wraps exactly one parsing call; everything else (e.g. our own
        # attribute access) is outside, so programming errors are not
        # disguised as corrupt input. The original exception is kept as
        # __cause__.
        try:
            pdf = pdfplumber.open(path)
        except Exception as exc:
            code = ErrorCode.ENCRYPTED if _is_encryption_error(exc) else ErrorCode.CORRUPT
            raise IngestionError(code) from exc

        with pdf:
            # Encrypted PDFs with an empty user password open without
            # error; the trailer's /Encrypt entry is the only signal.
            is_encrypted = pdf.doc.encryption is not None
            try:
                page_count = len(pdf.pages)  # parses the page tree
            except Exception as exc:
                raise IngestionError(ErrorCode.CORRUPT) from exc
        return PdfInspection(page_count=page_count, is_encrypted=is_encrypted)
