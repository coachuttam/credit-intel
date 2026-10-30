"""The report worker (PRD FR-015 criteria 5 and 7): builds the PDF and checks it, in a process the parent can stop.

    python -I -m credit_intel.report.worker      (the memo on standard input, UTF-8)

Standard output is ``OK`` and a line break and the PDF, only if the PDF was built **and passed the report check**; otherwise
``FAIL <reason>`` with a reason from the closed list. Nothing else is written, so no document text can reach a log. The parent treats
anything else, a non-zero exit or a missing answer as ``render_error``.
"""

import sys

from credit_intel.report import check
from credit_intel.report.errors import ReportError
from credit_intel.report.typeset import build_pdf


def main() -> int:
    out = sys.stdout.buffer
    try:
        memo = sys.stdin.buffer.read().decode("utf-8")
        pdf = build_pdf(memo)
        if check.problems(pdf, memo):
            out.write(b"FAIL check_failed\n")
        else:
            out.write(b"OK\n" + pdf)
    except ReportError as error:
        out.write(f"FAIL {error.reason}\n".encode())
    except Exception:
        out.write(b"FAIL render_error\n")
    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
