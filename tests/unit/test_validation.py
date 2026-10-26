"""PDF input validation (PRD FR-001)."""

import hashlib
from pathlib import Path

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption

from credit_intel.config import IngestionSettings
from credit_intel.ingestion.errors import MESSAGES, ErrorCode, IngestionError
from credit_intel.ingestion.models import PdfInspection
from credit_intel.ingestion.validation import validate_pdf


class FakeExtractor:
    """Stands in for the PDF library; records whether it was called."""

    def __init__(self, page_count: int = 1, is_encrypted: bool = False) -> None:
        self.inspection = PdfInspection(page_count=page_count, is_encrypted=is_encrypted)
        self.calls: list[Path] = []

    def inspect(self, path: Path) -> PdfInspection:
        self.calls.append(path)
        return self.inspection


def assert_rejected(code: ErrorCode, path: Path, **kwargs) -> IngestionError:
    with pytest.raises(IngestionError) as excinfo:
        validate_pdf(path, **kwargs)
    assert excinfo.value.code is code
    return excinfo.value


# --- Valid input ---------------------------------------------------------


def test_valid_pdf_returns_file_info(make_pdf):
    path = make_pdf(["Page one", "Page two", "Page three"], name="report.pdf")

    info = validate_pdf(path)

    assert info.path == path
    assert info.file_name == "report.pdf"
    assert info.size_bytes == path.stat().st_size
    assert info.page_count == 3


def test_sha256_matches_file_bytes(make_pdf):
    path = make_pdf(["Page one"])

    info = validate_pdf(path)

    assert info.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_sha256_matches_independently_computed_value(tmp_path):
    # Expected value computed with the system tool: printf '%PDF-1.7\n' | shasum -a 256
    path = tmp_path / "input.pdf"
    path.write_bytes(b"%PDF-1.7\n")

    info = validate_pdf(path, extractor=FakeExtractor())

    assert info.sha256 == "0716f9264c9fe19f5d7455276107f3ddcc1d3497f63d60689a73558ae8a1bf5e"


def test_validation_does_not_modify_the_file(make_pdf):
    path = make_pdf(["Page one"])
    before_bytes = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    validate_pdf(path)

    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime


# --- E-INPUT-NOT-FOUND ---------------------------------------------------


def test_missing_file_is_not_found(tmp_path):
    assert_rejected(ErrorCode.NOT_FOUND, tmp_path / "missing.pdf")


def test_directory_is_not_found(tmp_path):
    assert_rejected(ErrorCode.NOT_FOUND, tmp_path)


def deny_reads_of(monkeypatch, target: Path) -> None:
    """Make opening ``target`` raise PermissionError.

    Simulated rather than using chmod, which root and some containers bypass.
    """
    real_open = Path.open

    def guarded_open(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def test_unreadable_file_is_not_found(make_pdf, monkeypatch):
    path = make_pdf(["Page one"])
    deny_reads_of(monkeypatch, path)

    assert_rejected(ErrorCode.NOT_FOUND, path)


# --- E-INPUT-TOO-LARGE ---------------------------------------------------


def test_file_over_size_limit_is_too_large(make_pdf):
    path = make_pdf(["Page one"])
    size = path.stat().st_size

    assert_rejected(
        ErrorCode.TOO_LARGE, path, settings=IngestionSettings(max_file_bytes=size - 1)
    )


def test_file_exactly_at_size_limit_is_accepted(make_pdf):
    path = make_pdf(["Page one"])
    size = path.stat().st_size

    info = validate_pdf(path, settings=IngestionSettings(max_file_bytes=size))

    assert info.size_bytes == size


def test_default_size_limit_is_100_mb():
    assert IngestionSettings().max_file_bytes == 100 * 1024 * 1024


# --- E-INPUT-NOT-PDF -----------------------------------------------------


def test_text_file_with_pdf_extension_is_not_pdf(tmp_path):
    path = tmp_path / "statement.pdf"
    path.write_text("Revenue 1,000\n")

    assert_rejected(ErrorCode.NOT_PDF, path)


def test_empty_file_is_not_pdf(tmp_path):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    assert_rejected(ErrorCode.NOT_PDF, path)


def test_pdf_content_with_other_extension_is_accepted(make_pdf):
    path = make_pdf(["Page one"], name="statement.bin")

    assert validate_pdf(path).page_count == 1


# --- E-INPUT-CORRUPT -----------------------------------------------------


def test_header_followed_by_garbage_is_corrupt(tmp_path):
    path = tmp_path / "garbage.pdf"
    path.write_bytes(b"%PDF-1.4\nthis is not a pdf body\n")

    assert_rejected(ErrorCode.CORRUPT, path)


def test_truncated_pdf_is_corrupt(make_pdf, tmp_path):
    data = make_pdf(["Page one", "Page two"]).read_bytes()
    path = tmp_path / "truncated.pdf"
    path.write_bytes(data[: len(data) // 2])

    assert_rejected(ErrorCode.CORRUPT, path)


def test_corrupt_error_keeps_library_cause_but_not_its_message(tmp_path):
    path = tmp_path / "garbage.pdf"
    path.write_bytes(b"%PDF-1.4\nthis is not a pdf body\n")

    error = assert_rejected(ErrorCode.CORRUPT, path)

    assert error.__cause__ is not None
    assert str(error) == f"{ErrorCode.CORRUPT}: {MESSAGES[ErrorCode.CORRUPT]}"


def test_programming_errors_are_not_reported_as_corrupt(make_pdf, monkeypatch):
    # If our code misuses the library (here: pdfplumber object without the
    # expected attribute), the bug must surface, not become E-INPUT-CORRUPT.
    from credit_intel.ingestion import pdfplumber_extractor

    class OpenedPdfWithoutDoc:
        pages = [object()]

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr(pdfplumber_extractor.pdfplumber, "open", lambda path: OpenedPdfWithoutDoc())

    with pytest.raises(AttributeError):
        validate_pdf(make_pdf(["Page one"]))


# --- E-INPUT-ENCRYPTED ---------------------------------------------------


def test_password_protected_pdf_is_encrypted(make_pdf):
    path = make_pdf(["Secret"], encrypt=StandardEncryption("user-pw", "owner-pw"))

    assert_rejected(ErrorCode.ENCRYPTED, path)


def test_owner_password_only_pdf_is_encrypted(make_pdf):
    # Opens without a password, but is still encrypted.
    path = make_pdf(["Restricted"], encrypt=StandardEncryption("", "owner-pw", canPrint=0))

    assert_rejected(ErrorCode.ENCRYPTED, path)


# --- E-INPUT-TOO-MANY-PAGES ----------------------------------------------


def test_pdf_over_page_limit_is_too_many_pages(make_pdf):
    path = make_pdf(["1", "2", "3"])

    assert_rejected(ErrorCode.TOO_MANY_PAGES, path, settings=IngestionSettings(max_pages=2))


def test_pdf_exactly_at_page_limit_is_accepted(make_pdf):
    path = make_pdf(["1", "2", "3"])

    assert validate_pdf(path, settings=IngestionSettings(max_pages=3)).page_count == 3


def test_default_page_limit_is_600():
    assert IngestionSettings().max_pages == 600


# --- Check order and extractor boundary ----------------------------------


def test_size_is_checked_before_signature(tmp_path):
    path = tmp_path / "big.txt"
    path.write_bytes(b"not a pdf" * 10)

    assert_rejected(ErrorCode.TOO_LARGE, path, settings=IngestionSettings(max_file_bytes=10))


@pytest.mark.parametrize(
    ("content", "settings", "expected"),
    [
        (b"%PDF-1.4 big" * 10, IngestionSettings(max_file_bytes=10), ErrorCode.TOO_LARGE),
        (b"plain text", IngestionSettings(), ErrorCode.NOT_PDF),
    ],
)
def test_parser_is_not_called_when_cheap_checks_fail(tmp_path, content, settings, expected):
    path = tmp_path / "input.pdf"
    path.write_bytes(content)
    fake = FakeExtractor()

    assert_rejected(expected, path, settings=settings, extractor=fake)

    assert fake.calls == []


def test_any_text_extractor_can_be_used(tmp_path):
    path = tmp_path / "input.pdf"
    path.write_bytes(b"%PDF-1.7\n")
    fake = FakeExtractor(page_count=7)

    info = validate_pdf(path, extractor=fake)

    assert fake.calls == [path]
    assert info.page_count == 7


def test_encryption_reported_by_extractor_is_rejected(tmp_path):
    path = tmp_path / "input.pdf"
    path.write_bytes(b"%PDF-1.7\n")

    assert_rejected(ErrorCode.ENCRYPTED, path, extractor=FakeExtractor(is_encrypted=True))


# --- Error messages ------------------------------------------------------


def test_every_error_code_has_a_message():
    assert set(MESSAGES) == set(ErrorCode)


def test_no_text_layer_message_states_ocr_is_not_supported():
    assert "OCR is not supported" in MESSAGES[ErrorCode.NO_TEXT_LAYER]


def test_not_found_message_names_file_but_not_its_directory(tmp_path):
    error = assert_rejected(ErrorCode.NOT_FOUND, tmp_path / "missing.pdf")

    assert "missing.pdf" in str(error)
    assert str(tmp_path) not in str(error)
