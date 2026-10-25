"""The traceability checker lives in the package now (``credit_intel.memo.trace``, PRD v0.4.27 step S3); the tests keep importing it by this name."""

from credit_intel.memo.trace import ASSERTED_INPUTS, problems  # noqa: F401
