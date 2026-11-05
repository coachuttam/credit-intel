"""What a tuning document scores without the phrases that were added from tuning documents (Phase 7c, controlled variant: ablation).

The closed phrase lists were extended from tuning documents (``phrase_provenance.json``, S-5). This tool replays a tuning document from the
response cache (nothing is sent) with some of those phrases taken out of the row-label check, and optionally out of the statement locator,
and scores it against the owner's labels as the scorer does. It answers, on tuning evidence alone and at no cost: how much of a tuning
score rests on phrases fitted to tuning documents, and at which stage the entries fail without them (S-1).

Modes: ``own`` drops the phrases added from the document being replayed (a document before its own additions, the nearest tuning-only
stand-in for an unseen document of the same kind); ``added`` drops every phrase added from any tuning document (the PRD's initial phrases
and the rule-defined ones remain). A phrase recorded as added but unsupported counts as added. With ``--locator`` the locator lists are
cut too; the locator chooses the pages and the cache key covers them, so a document that is run by the locator may then be a cache miss
(reported, not retried), while a document run on a given page range is not.

    uv run --locked python -m credit_intel.evaluation.ablation --mode own|added [--locator] --report <pdf> <labels.json> [--report ...]

Counts only: no phrase, label or value is printed. A held-out document is refused, as for the scorer.
"""

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from credit_intel.config import DEFAULT_SETTINGS_PATH, BorrowingSettings, LabelSettings, LocatorSettings
from credit_intel.evaluation.guard import SendRefused
from credit_intel.evaluation.provenance import PROVENANCE_PATH, ProvenanceError, load_provenance
from credit_intel.evaluation.score import LabelsError, load_labels, replay
from credit_intel.extraction.prompt import DEFAULT_PROMPT, load_prompt
from credit_intel.ingestion.errors import IngestionError

MODES = ("own", "added")
ADDED = ("tuning_added", "tuning_added_unverified")


def dropped(table: dict[tuple[str, str], dict], document_id: str, mode: str) -> set[tuple[str, str]]:
    """The (list, phrase) keys to take out: those added from the document (``own``) or from any tuning document (``added``)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    return {key for key, row in table.items() if row["origin"] in ADDED and (mode == "added" or document_id in row["documents"])}


def label_settings_without(drop: set[tuple[str, str]]) -> LabelSettings:
    base = LabelSettings()
    rules = {
        field: replace(
            rule,
            phrases=tuple(p for p in rule.phrases if (f"label.{field}", p) not in drop),
            sectioned_phrases=tuple(p for p in rule.sectioned_phrases if (f"label.{field}.sectioned", p) not in drop),
        )
        for field, rule in base.rules.items()
    }
    return replace(base, rules=rules)


def locator_settings_without(drop: set[tuple[str, str]]) -> LocatorSettings:
    base = LocatorSettings()
    return replace(
        base,
        title_phrases={k: tuple(p for p in v if (f"locator.title.{k}", p) not in drop) for k, v in base.title_phrases.items()},
        line_item_phrases={k: tuple(p for p in v if (f"locator.line_item.{k}", p) not in drop) for k, v in base.line_item_phrases.items()},
        title_prefix_words=tuple(p for p in base.title_prefix_words if ("locator.title_prefix", p) not in drop),
        other_statement_title_phrases=tuple(p for p in base.other_statement_title_phrases if ("locator.other_statement_title", p) not in drop),
    )


def counts_of(report: dict) -> dict:
    """The comparable counts of a replayed report (or why it did not replay)."""
    if not report.get("replayed"):
        return {"replayed": False, "reason": report.get("reason")}
    c = report["counts"]
    return {"replayed": True, "sc01": f"{c['sc01']['match']}/{c['sc01']['of']}", "sc03": f"{c['sc03']['correct']}/{c['sc03']['of']}",
            "sc02_candidates": c["sc02"], "stages": report["stages"], "statuses": report["statuses"], "reasons": report["reasons"]}  # fmt: skip


def run(pdf: Path, labels_path: Path, *, mode: str, locator: bool, table: dict | None = None, **replay_args) -> dict:
    labels = load_labels(labels_path)
    table = table if table is not None else load_provenance(PROVENANCE_PATH)
    drop = dropped(table, labels.document_id, mode)
    baseline = replay(pdf, labels, **replay_args)
    ablated = replay(pdf, labels, label_settings=label_settings_without(drop), locator_settings=locator_settings_without(drop) if locator else None, **replay_args)
    return {
        "set": "tuning",
        "document_id": labels.document_id,
        "mode": mode,
        "locator_cut": locator,
        "phrases_removed": len(drop),
        "baseline": counts_of(baseline),
        "without": counts_of(ablated),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--locator", action="store_true", help="also take the phrases out of the statement locator")
    parser.add_argument("--report", nargs=2, action="append", metavar=("PDF", "LABELS"), required=True)
    parser.add_argument("--assignments", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML")
    args = parser.parse_args(argv)
    extra = {"config": args.config, "prompt": load_prompt(os.environ.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT))}
    if args.assignments is not None:
        extra["assignments"] = args.assignments
    try:
        reports = [run(Path(pdf), Path(labels), mode=args.mode, locator=args.locator, **extra) for pdf, labels in args.report]
    except (LabelsError, SendRefused, ProvenanceError) as error:
        print(f"ablation: refused: {error}", file=sys.stderr)
        return 2
    except IngestionError as error:
        print(f"ablation: stopped {error.code.value}", file=sys.stderr)
        return 2
    for report in reports:
        print("ablation: " + json.dumps(report, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
