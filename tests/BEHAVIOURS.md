# Expected Behaviours

Each behaviour the system must exhibit, the test that verifies it, and its status.
Add a row before (or alongside) implementing a behaviour.

Status: `planned` · `in progress` · `passing` · `failing`

| ID | Behaviour | Test | Status |
|----|-----------|------|--------|
| B-000 | Test suite runs on Python 3.12 via uv | `tests/test_placeholder.py::test_python_version_is_312` | passing |
| B-100 | `credit_intel` package (src layout) is built by uv and importable, including `credit_intel.ingestion` | `tests/test_package.py` | passing |
| B-101 | A valid PDF returns file name, size, page count, and SHA-256 of its exact bytes (FR-001.8) | `tests/unit/test_validation.py::test_valid_pdf_returns_file_info`, `::test_sha256_matches_file_bytes`, `::test_sha256_matches_independently_computed_value` | passing |
| B-102 | Validation never modifies the input file — bytes and mtime unchanged (FR-001.9) | `tests/unit/test_validation.py::test_validation_does_not_modify_the_file` | passing |
| B-103 | Missing path, directory, or unreadable file → `E-INPUT-NOT-FOUND` (FR-001.7) | `tests/unit/test_validation.py::test_missing_file_is_not_found`, `::test_directory_is_not_found`, `::test_unreadable_file_is_not_found` | passing |
| B-104 | File larger than `max_file_bytes` (default 25 MB) → `E-INPUT-TOO-LARGE`; exactly at limit accepted (FR-001.2) | `tests/unit/test_validation.py::test_file_over_size_limit_is_too_large`, `::test_file_exactly_at_size_limit_is_accepted`, `::test_default_size_limit_is_25_mb` | passing |
| B-105 | Content without `%PDF-` signature → `E-INPUT-NOT-PDF`, regardless of extension; PDF content with another extension accepted (FR-001.1) | `tests/unit/test_validation.py::test_text_file_with_pdf_extension_is_not_pdf`, `::test_empty_file_is_not_pdf`, `::test_pdf_content_with_other_extension_is_accepted` | passing |
| B-106 | Unparsable or truncated PDF → `E-INPUT-CORRUPT`; library error kept as `__cause__`, not shown in message; programming errors are not disguised as corrupt input (FR-001.5, FR-011.4) | `tests/unit/test_validation.py::test_header_followed_by_garbage_is_corrupt`, `::test_truncated_pdf_is_corrupt`, `::test_corrupt_error_keeps_library_cause_but_not_its_message`, `::test_programming_errors_are_not_reported_as_corrupt` | passing |
| B-107 | Password-protected **and** owner-password-only encrypted PDFs → `E-INPUT-ENCRYPTED` (FR-001.4) | `tests/unit/test_validation.py::test_password_protected_pdf_is_encrypted`, `::test_owner_password_only_pdf_is_encrypted`, `::test_encryption_reported_by_extractor_is_rejected` | passing |
| B-108 | More pages than `max_pages` (default 400) → `E-INPUT-TOO-MANY-PAGES`; exactly at limit accepted (FR-001.3) | `tests/unit/test_validation.py::test_pdf_over_page_limit_is_too_many_pages`, `::test_pdf_exactly_at_page_limit_is_accepted`, `::test_default_page_limit_is_400` | passing |
| B-109 | Cheap checks run before the PDF parser; parser never sees a too-large or non-PDF file | `tests/unit/test_validation.py::test_size_is_checked_before_signature`, `::test_parser_is_not_called_when_cheap_checks_fail` | passing |
| B-110 | Validation works with any `TextExtractor` implementation (D-01 replaceability) | `tests/unit/test_validation.py::test_any_text_extractor_can_be_used` | passing |
| B-111 | Every error code has a fixed safe message; no-text message states OCR is not supported; messages name the file but not its directory | `tests/unit/test_validation.py::test_every_error_code_has_a_message`, `::test_no_text_layer_message_states_ocr_is_not_supported`, `::test_not_found_message_names_file_but_not_its_directory` | passing |
| B-112 | PDF with no extractable text on any page → `E-INPUT-NO-TEXT-LAYER` (FR-001.6) | — (commit 3, needs page extraction) | planned |
