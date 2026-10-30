"""The PDF report (PRD FR-015, v0.4.56): the memo typeset for reading. A presentation layer that never changes the memo or fails a run."""

from credit_intel.report.build import RENDER_TIME_LIMIT, ReportOutcome, make_report
from credit_intel.report.errors import REASONS, ReportError
from credit_intel.report.typeset import build_pdf

__all__ = ["REASONS", "RENDER_TIME_LIMIT", "ReportError", "ReportOutcome", "build_pdf", "make_report"]
