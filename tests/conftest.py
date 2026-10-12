"""Shared fixtures: synthetic PDFs built at test time.

PDFs are written to pytest's per-test ``tmp_path`` and never into the
repository. ``invariant=1`` makes reportlab output byte-identical across runs.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas


def write_pdf(
    path: Path,
    page_texts: list[str],
    encrypt: StandardEncryption | None = None,
) -> Path:
    """Write a PDF with one page per entry in ``page_texts``."""
    pdf = canvas.Canvas(str(path), invariant=1, encrypt=encrypt)
    for text in page_texts:
        if text:
            pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return path


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Factory: ``make_pdf(["page 1 text", "page 2 text"], name="x.pdf")``."""

    def _make(
        page_texts: list[str],
        name: str = "synthetic.pdf",
        encrypt: StandardEncryption | None = None,
    ) -> Path:
        return write_pdf(tmp_path / name, page_texts, encrypt=encrypt)

    return _make
