"""The application package is installed by uv and importable from tests."""

import importlib
import sys


def test_python_version_is_312():
    assert sys.version_info[:2] == (3, 12)


def test_credit_intel_package_imports():
    module = importlib.import_module("credit_intel")
    assert module.__name__ == "credit_intel"


def test_ingestion_subpackage_imports():
    module = importlib.import_module("credit_intel.ingestion")
    assert module.__name__ == "credit_intel.ingestion"
