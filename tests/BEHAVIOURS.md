# Expected Behaviours

Each behaviour the system must exhibit, the test that verifies it, and its status.
Add a row before (or alongside) implementing a behaviour.

Status: `planned` · `in progress` · `passing` · `failing`

| ID | Behaviour | Test | Status |
|----|-----------|------|--------|
| B-000 | Test suite runs on Python 3.12 via uv | `tests/test_placeholder.py::test_python_version_is_312` | passing |
| B-100 | `credit_intel` package (src layout) is built by uv and importable, including `credit_intel.ingestion` | `tests/test_package.py` | passing |
