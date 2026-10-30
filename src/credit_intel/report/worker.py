"""The report worker (PRD FR-015 criteria 5 and 7): builds the PDF and checks it, in a process the parent can stop.

    python -I -m credit_intel.report.worker      (standard input: JSON {"memo": ..., "results": ... or null}, UTF-8)

With ``results`` the two charts are built from them (``charts.build_charts``) and checked against the memo. Standard output is ``OK`` and a line break and the PDF, only if the PDF was built **and passed the report check**; otherwise
``FAIL <reason>`` with a reason from the closed list. Nothing else is written, so no document text can reach a log. The parent treats
anything else, a non-zero exit or a missing answer as ``render_error``.
"""

import json
import sys

from credit_intel.report import charts as chart_module
from credit_intel.report import check
from credit_intel.report.errors import ReportError
from credit_intel.report.typeset import build_pdf


def main() -> int:
    out = sys.stdout.buffer
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        memo, results = request["memo"], request["results"]
        charts = chart_module.build_charts(results) if results is not None else None
        pdf = build_pdf(memo, charts)
        if check.problems(pdf, memo, charts, results):
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
