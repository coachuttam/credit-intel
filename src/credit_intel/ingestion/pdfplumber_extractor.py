"""TextExtractor implementation backed by pdfplumber.

This is the only module that imports pdfplumber or pdfminer (PRD D-01).
"""

from collections.abc import Sequence
from itertools import islice
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError, PDFPasswordIncorrect
from pdfplumber.page import Page

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import PageText, PageWords, PdfInspection, Word

_ENCRYPTION_ERRORS = (PDFPasswordIncorrect, PDFEncryptionError)

# Pinned explicitly, equal to the values extract_text uses, so a library default
# change cannot silently move the word grouping away from the page text (AC-OD1-25).
WORD_X_TOLERANCE = 3
WORD_Y_TOLERANCE = 3


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


# The input is untrusted, so any failure inside the PDF library while
# *parsing* it means the file cannot be processed. Each try block below wraps
# exactly one parsing call; everything else (e.g. our own attribute access)
# is outside, so programming errors are not disguised as corrupt input. The
# original exception is kept as __cause__.


def _open(path: Path) -> pdfplumber.PDF:
    try:
        return pdfplumber.open(path)
    except Exception as exc:
        code = ErrorCode.ENCRYPTED if _is_encryption_error(exc) else ErrorCode.CORRUPT
        raise IngestionError(code) from exc


def _load_pages(pdf: pdfplumber.PDF) -> list[Page]:
    try:
        return list(pdf.pages)  # parses the page tree
    except Exception as exc:
        raise IngestionError(ErrorCode.CORRUPT) from exc


def _page_labels(doc: PDFDocument, page_count: int) -> list[str | None]:
    """The document's page-label metadata, or ``None`` for every page.

    Labels are optional (FR-002.2): a missing or unreadable label tree
    never rejects the document.
    """
    try:
        # get_page_labels() yields indefinitely; take one per page.
        labels = list(islice(doc.get_page_labels(), page_count))
    except Exception:  # PDFNoPageLabels, or a malformed label tree
        return [None] * page_count
    return labels + [None] * (page_count - len(labels))


class PdfplumberExtractor:
    def inspect(self, path: Path) -> PdfInspection:
        with _open(path) as pdf:
            # Encrypted PDFs with an empty user password open without
            # error; the trailer's /Encrypt entry is the only signal.
            is_encrypted = pdf.doc.encryption is not None
            page_count = len(_load_pages(pdf))
        return PdfInspection(page_count=page_count, is_encrypted=is_encrypted)

    def extract_pages(self, path: Path) -> list[PageText]:
        with _open(path) as pdf:
            pages = _load_pages(pdf)
            labels = _page_labels(pdf.doc, len(pages))
            result = []
            for page_number, (page, label) in enumerate(zip(pages, labels), start=1):
                try:
                    text = page.extract_text()
                except Exception as exc:
                    raise IngestionError(ErrorCode.CORRUPT) from exc
                result.append(PageText(page_number=page_number, text=text or "", page_label=label))
        return result

    def extract_words(self, path: Path, page_numbers: Sequence[int]) -> list[PageWords]:
        requested = list(page_numbers)
        if not requested or len(set(requested)) != len(requested):
            raise IngestionError(ErrorCode.PAGE_RANGE)
        with _open(path) as pdf:
            pages = _load_pages(pdf)
            if any(isinstance(n, bool) or not isinstance(n, int) for n in requested) or not all(
                1 <= n <= len(pages) for n in requested
            ):
                raise IngestionError(ErrorCode.PAGE_RANGE)
            result = []
            for page_number in sorted(requested):
                page = pages[page_number - 1]
                try:
                    raw_words = page.extract_words(
                        x_tolerance=WORD_X_TOLERANCE,
                        y_tolerance=WORD_Y_TOLERANCE,
                        keep_blank_chars=False,
                        use_text_flow=False,
                    )
                except Exception as exc:
                    raise IngestionError(ErrorCode.CORRUPT) from exc
                words = sorted(
                    (
                        Word(
                            text=w["text"],
                            x0=float(w["x0"]),
                            x1=float(w["x1"]),
                            top=float(w["top"]),
                            bottom=float(w["bottom"]),
                        )
                        for w in raw_words
                    ),
                    key=lambda w: (w.top, w.x0, w.text),
                )
                result.append(
                    PageWords(
                        page_number=page_number,
                        width=float(page.width),
                        height=float(page.height),
                        rotation=int(page.rotation) % 360,
                        words=tuple(words),
                    )
                )
        return result
