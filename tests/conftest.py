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
    draw_shapes: bool = False,
    page_labels: list[tuple[int, str, int]] | None = None,
) -> Path:
    """Write a PDF with one page per entry in ``page_texts``.

    Each entry may contain several lines separated by ``\\n``; an empty
    string gives a page with no text. ``draw_shapes`` adds a filled
    rectangle to every page (non-text content, like a scanned image).
    ``page_labels`` is a list of ``(page_index, style, start)`` label ranges.
    """
    pdf = canvas.Canvas(str(path), invariant=1, encrypt=encrypt)
    for page_index, style, start in page_labels or []:
        pdf.addPageLabel(page_index, style=style, start=start)
    for text in page_texts:
        if draw_shapes:
            pdf.rect(72, 72, 200, 100, fill=1)
        for line_number, line in enumerate(text.splitlines()):
            pdf.drawString(72, 720 - 14 * line_number, line)
        pdf.showPage()
    pdf.save()
    return path


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Factory: ``make_pdf(["page 1 text", "page 2 text"], name="x.pdf")``."""

    def _make(page_texts: list[str], name: str = "synthetic.pdf", **options) -> Path:
        return write_pdf(tmp_path / name, page_texts, **options)

    return _make
