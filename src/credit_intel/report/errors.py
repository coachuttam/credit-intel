"""The reasons a PDF report is not written (PRD FR-015 criterion 7, v0.4.56). A report failure never fails a run."""

REASONS = ("render_error", "check_failed", "glyph_missing", "timeout")


class ReportError(Exception):
    """The report could not be built. ``reason`` is one of ``REASONS``; the message is the reason alone and never holds document text."""

    def __init__(self, reason: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"unknown report failure reason {reason!r}")
        self.reason = reason
        super().__init__(reason)
