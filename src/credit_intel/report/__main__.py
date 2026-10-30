"""Build a PDF report from a finished run, offline (PRD FR-015 criterion 11, v0.4.56).

    python -m credit_intel.report <run-folder> --output FILE

It reads ``memo.md`` and ``results.json`` of the folder and nothing else: no model is called and the document is not read. It builds and
checks the report as a run does (criteria 3 to 7) and writes it to ``FILE``, which must not exist and must not be inside a run folder:
**no run folder is ever changed after it is written** (FR-010 criterion 4). Unlike a run, where a failed report is a warning, here the report
is the whole job, so a failure is exit code 1 with the reason word and no file. Exit codes: 0 written, 1 not written, 2 bad arguments.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from credit_intel.memo.trace import problems
from credit_intel.report.build import make_report


def _inside_a_run_folder(output: Path, folder: Path) -> bool:
    target = output.resolve()
    parent = target.parent
    return target.is_relative_to(folder.resolve()) or (parent / "manifest.json").exists() or (parent / "memo.md").exists()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m credit_intel.report", description="Build report.pdf from a finished run's memo.md and results.json, offline.")
    parser.add_argument("run_folder", type=Path, help="a run folder written by credit-intel")
    parser.add_argument("--output", type=Path, required=True, metavar="FILE", help="the PDF to write; it must not exist and must not be inside a run folder")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s", stream=sys.stderr)

    if _inside_a_run_folder(args.output, args.run_folder):
        print("report: the output must not be inside a run folder", file=sys.stderr)
        return 1
    if args.output.exists() or args.output.is_symlink():
        print("report: the output file already exists and is not overwritten", file=sys.stderr)
        return 1
    try:
        memo = (args.run_folder / "memo.md").read_text(encoding="utf-8")
        results = json.loads((args.run_folder / "results.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        print("report: memo.md and results.json cannot be read from the run folder", file=sys.stderr)
        return 1
    try:
        found = problems(memo, results)
    except Exception:
        found = ["unusable"]
    if found:  # a memo that is not the memo of these results is not presented
        print("report: memo.md does not match results.json (check_failed)", file=sys.stderr)
        return 1
    outcome = make_report(memo, results)
    if outcome.status != "written" or outcome.pdf is None:
        print(f"report: not written ({outcome.reason})", file=sys.stderr)
        return 1
    try:
        with open(args.output, "xb") as handle:  # exclusive: never overwrites, even if the file appeared since the check above
            handle.write(outcome.pdf)
    except OSError:
        print("report: the output file could not be written", file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
