"""The application package is installed by uv and importable from tests."""

import importlib


def test_credit_intel_package_imports():
    module = importlib.import_module("credit_intel")
    assert module.__name__ == "credit_intel"


def test_ingestion_subpackage_imports():
    module = importlib.import_module("credit_intel.ingestion")
    assert module.__name__ == "credit_intel.ingestion"
