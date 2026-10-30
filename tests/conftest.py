"""Shared fixtures: synthetic PDFs built at test time.

PDFs are written to pytest's per-test ``tmp_path`` and never into the
repository. ``invariant=1`` makes reportlab output byte-identical across runs.
"""

import os
import socket
from collections.abc import Callable, Mapping
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


# --- No network by default; live tests are opt-in (PRD O.1, D-02, SEC-10) -----------------------


def live_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Live tests run only with CREDIT_INTEL_LIVE=1 and an OPENAI_API_KEY set."""
    env = os.environ if env is None else env
    return env.get("CREDIT_INTEL_LIVE") == "1" and bool(env.get("OPENAI_API_KEY", "").strip())


def pytest_collection_modifyitems(config, items):
    if live_enabled():
        return
    skip = pytest.mark.skip(reason="live tests need CREDIT_INTEL_LIVE=1 and OPENAI_API_KEY (they cost money)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    """Every test except a live one fails if it tries to open a network connection."""
    if request.node.get_closest_marker("live"):
        return

    def blocked(self, *args, **kwargs):
        raise RuntimeError("network access is blocked in the default test suite")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture(autouse=True)
def in_process_parsing(monkeypatch):
    """The command line parses in a worker process under required limits (SEC-12); tests that are not about that parse in process.

    The worker, the limits and the command line's wiring are tested in ``test_parse_limits.py`` and ``test_parse_limits_cli.py``,
    which pass the real factory explicitly.
    """
    import credit_intel.service as service
    from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

    monkeypatch.setattr(service, "sandboxed_extractor", lambda config, env: PdfplumberExtractor())


@pytest.fixture(autouse=True)
def no_pdf_report_by_default(monkeypatch):
    """A run builds its PDF report in a worker process (about a second); tests that are not about the report do not wait for it.

    The report, its check, its failure paths and the command line's behaviour are tested in the ``test_report_*`` files, which put the
    real ``make_report`` back (``real_report``).
    """
    import credit_intel.export.run_export as run_export
    from credit_intel.report import ReportOutcome

    monkeypatch.setattr(run_export, "make_report", lambda memo, results=None, **kwargs: ReportOutcome.skipped())


@pytest.fixture
def real_report(monkeypatch):
    """Put the real report maker back for a test about the report."""
    import credit_intel.export.run_export as run_export
    from credit_intel.report import build

    monkeypatch.setattr(run_export, "make_report", build.make_report)
    return build.make_report


STUB_VARIABLES = ("STUB_LANGS", "STUB_LOG", "STUB_META", "STUB_MODE", "STUB_PIDS", "STUB_SLEEP", "STUB_TSV", "STUB_VERSION_ON_STDERR")


@pytest.fixture
def engine_stub_variables(monkeypatch):
    """The OCR-engine stubs of some tests are configured through ``STUB_*`` variables, which the real child environment drops (Phase 7 step 1, F-1).

    Only these tests add those names to the list of variables a child process may inherit; the list in the code is unchanged.
    """
    from credit_intel.ingestion import child_env

    monkeypatch.setattr(child_env, "ALLOWED", (*child_env.ALLOWED, *STUB_VARIABLES))
