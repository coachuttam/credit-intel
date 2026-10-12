"""Placeholder test confirming the pytest workflow runs under uv.

Remove once the first real behaviour test exists.
"""

import sys


def test_python_version_is_312():
    assert sys.version_info[:2] == (3, 12)
