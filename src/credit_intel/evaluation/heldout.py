"""The held-out evaluation run (PRD O.2, v0.4.41): the one place a held-out document may be sent.

``python -m credit_intel.evaluation.heldout --held-out-run --document PDF REFERENCE [--document ...]``

It runs the pipeline once over **every** document the assignment record shows as held out and the ledger shows as not yet used
(PRD v0.4.42: a document used by an earlier run is neither required nor allowed), compares each with the owner's
reference (the gate's format and comparison, three fields) and prints counts only: no value, quote, label, path or hash.
It refuses, before anything is sent, unless the configuration is frozen (a clean tree at the commit the owner named), the
documents are exactly the held-out set, none has been used before (the ledger), the response cache is empty, no second
provider is on and the owner approved. Every line it prints says ``"set": "held_out"``; the gate's and the tuning runner's say
``"set": "tuning"``. The ordinary command line, the gate, the dry run and the tuning runner keep refusing a held-out document.
"""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from credit_intel.config import (
    DEFAULT_SETTINGS_PATH,
    ENV_PRIVATE_APPROVED,
    ENV_USE_JEV,
    load_llm_settings,
    load_pricing,
)
from credit_intel.evaluation.gate import GateReferenceError, compare, load_reference
from credit_intel.evaluation.guard import (
    ASSIGNMENTS_PATH,
    PROJECT_ROOT,
    SendRefused,
    allow_held_out_send,
    check_private_path,
    file_sha256,
    load_current_sets,
)
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import DEFAULT_PROMPT, load_prompt
from credit_intel.ingestion.errors import IngestionError
from credit_intel.llm.factory import build_provider

ENV_HELD_OUT_APPROVED = "CREDIT_INTEL_HELD_OUT_APPROVED"  # the freeze commit (12 or more characters) the owner typed for this run
LEDGER_PATH = PROJECT_ROOT / "tests" / "eval" / "heldout_runs.jsonl"
CACHE_DIR = PROJECT_ROOT / ".cache" / "llm_heldout"  # separate from the tuning cache; must be empty at the start
REPORT_DIR = PROJECT_ROOT / "private" / "eval"
LEDGER_MEMBERS = ("document_id", "sha256", "run_id", "event", "at", "freeze_commit", "assignments_sha256")
FROZEN_PATHS = ("src", "config", "prompts", "tests/eval", "uv.lock", "pyproject.toml")  # a change under any of them means not frozen
HASHED_FILES = ("uv.lock", "config/settings.toml", "config/risk_rules.toml")
MIN_COMMIT_CHARACTERS = 12
REFUSALS = (
    "no_flag", "no_approval", "not_frozen", "not_held_out", "not_the_held_out_set", "already_used",
    "ledger_unreadable", "record_unreadable", "cache_not_empty", "reference_invalid", "second_provider",
)  # fmt: skip


class HeldOutRefused(Exception):
    """The run may not start. ``reason`` is one of ``REFUSALS``; the message holds no document identifier."""

    def __init__(self, reason: str) -> None:
        assert reason in REFUSALS
        super().__init__(reason)
        self.reason = reason


def load_ledger(path: Path) -> list[dict]:
    """The ledger's lines; a missing file is an empty ledger (the first run). Anything malformed refuses everything."""
    if not path.exists():
        return []
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise HeldOutRefused("ledger_unreadable") from None
    if "\r" in text or (text and not text.endswith("\n")):
        raise HeldOutRefused("ledger_unreadable")
    records = []
    for line in text.split("\n")[:-1] if text else []:
        try:
            record = json.loads(line)
        except ValueError:
            raise HeldOutRefused("ledger_unreadable") from None
        if (
            not isinstance(record, dict)
            or tuple(record) != LEDGER_MEMBERS
            or not all(isinstance(value, str) for value in record.values())
            or record["event"] not in ("started", "completed")
        ):
            raise HeldOutRefused("ledger_unreadable")
        records.append(record)
    return records


def append_ledger(path: Path, record: dict) -> None:
    """Append one line and make it durable before the caller goes on (a ``started`` line must outlive a crash)."""
    assert tuple(record) == LEDGER_MEMBERS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), ensure_ascii=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def git_state(root: Path) -> tuple[str, list[str]]:
    """The commit at ``HEAD`` and the changed or untracked files under the frozen paths. Raises ``HeldOutRefused`` if git cannot say."""
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--", *FROZEN_PATHS],
            capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        raise HeldOutRefused("not_frozen") from None
    return head, [line for line in status.splitlines() if line.strip()]


def _hash_or_absent(path: Path) -> str:
    return file_sha256(path) if path.is_file() else "absent"


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def run_held_out(
    documents: Sequence[tuple[Path, Path]],
    *,
    flag: bool,
    env: Mapping[str, str],
    root: Path = PROJECT_ROOT,
    assignments: Path = ASSIGNMENTS_PATH,
    ledger: Path = LEDGER_PATH,
    config: Path = DEFAULT_SETTINGS_PATH,
    cache_dir: Path = CACHE_DIR,
    report_dir: Path = REPORT_DIR,
    provider_factory: Callable = build_provider,
    repo: Callable[[Path], tuple[str, list[str]]] = git_state,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    out: Callable[[str], None] = print,
) -> int:
    """Run the held-out set once. Returns 0 when every document completed, 1 when the run stopped part-way.

    Raises ``HeldOutRefused`` before anything is sent or written if any precondition fails.
    """
    # 1. The flag and the owner's approval.
    if not flag:
        raise HeldOutRefused("no_flag")
    approved = env.get(ENV_HELD_OUT_APPROVED, "").strip()
    if len(approved) < MIN_COMMIT_CHARACTERS:
        raise HeldOutRefused("no_approval")
    if _is_true(env.get(ENV_USE_JEV)):
        raise HeldOutRefused("second_provider")
    # 2. The freeze: the commit the owner named is HEAD, and nothing under the frozen paths differs from it.
    head, changed = repo(root)
    if not head.startswith(approved):
        raise HeldOutRefused("no_approval")
    if changed:
        raise HeldOutRefused("not_frozen")
    # 3. Exactly the held-out documents that no earlier run has used, and nothing else (v0.4.42).
    shas = []
    try:
        for pdf, _ in documents:
            if env.get(ENV_PRIVATE_APPROVED) != "1":
                check_private_path(pdf, env)
            sha = file_sha256(pdf)
            allow_held_out_send(sha, assignments)  # the one use of the held-out exception
            shas.append(sha)
        held_out = {sha for sha, (_, kind) in load_current_sets(assignments).items() if kind == "held_out"}
    except SendRefused as error:
        unreadable = "cannot be read" in str(error) or "malformed" in str(error)  # the guard's two fixed wordings for a bad record
        raise HeldOutRefused("record_unreadable" if unreadable else "not_held_out") from None
    except OSError:
        raise HeldOutRefused("not_held_out") from None
    # 4. One shot per document: a used document is refused, and nothing left to run is refused too.
    used = {record["sha256"] for record in load_ledger(ledger)}
    if set(shas) & used or not held_out - used:
        raise HeldOutRefused("already_used")
    if len(set(shas)) != len(shas) or set(shas) != held_out - used:
        raise HeldOutRefused("not_the_held_out_set")
    # 5. An empty response cache, so no earlier reply answers a held-out page.
    if cache_dir.exists() and any(cache_dir.iterdir()):
        raise HeldOutRefused("cache_not_empty")
    # 6. The owner's labels.
    references = []
    try:
        for (_, reference_path), sha in zip(documents, shas, strict=True):
            reference = load_reference(reference_path)
            if reference.sha256 != sha:
                raise GateReferenceError("the reference was not written for this document")
            references.append(reference)
    except GateReferenceError:
        raise HeldOutRefused("reference_invalid") from None
    # 7. Settings, the owner's spend limits and the provider; only now is anything built.
    try:
        llm = load_llm_settings(config, env)
        pricing = load_pricing(config, env)
        prompt = load_prompt(env.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT))
        provider = provider_factory(llm)
    except IngestionError:
        raise HeldOutRefused("no_approval") from None

    run_id = "H-" + now().strftime("%Y%m%dT%H%M%SZ")
    assignments_sha = file_sha256(assignments)
    hashes = {name: _hash_or_absent(root / name) for name in HASHED_FILES}
    hashes[f"prompts/{prompt.version.replace('-', '_')}.md"] = _hash_or_absent(root / "prompts" / f"{prompt.version.replace('-', '_')}.md")
    hashes["assignments"] = assignments_sha
    header = {"run_id": run_id, "set": "held_out", "freeze_commit": head, "documents": len(documents), "prompt_version": prompt.version, "sha256": hashes}
    out("HELD-OUT RUN: " + json.dumps(header, sort_keys=True, ensure_ascii=True))

    def entry(sha: str, document_id: str, event: str) -> dict:
        return dict(zip(LEDGER_MEMBERS, (document_id, sha, run_id, event, now().strftime("%Y-%m-%dT%H:%M:%SZ"), head, assignments_sha), strict=True))

    lines, completed = [], 0
    try:
        for (pdf, _), sha, reference in zip(documents, shas, references, strict=True):
            append_ledger(ledger, entry(sha, reference.document_id, "started"))  # before the first page of it is sent
            try:
                run = run_extraction(
                    pdf, provider, llm, basis=reference.basis, cache_dir=cache_dir, pricing=pricing, prompt=prompt,
                    page_range=reference.pages, assert_basis=reference.assert_basis,
                )  # fmt: skip
            except IngestionError as error:
                report = {"set": "held_out", "document_id": reference.document_id, "outcome": "stopped", "error_code": error.code.value,
                          "counts": {"match": 0, "mismatch": 0, "missing": len(reference.entries)}}  # fmt: skip
            else:
                stats = run.stats
                result = compare(reference, run.field_set)
                report = {"set": "held_out", "document_id": reference.document_id, "outcome": "completed", "counts": result["counts"], "entries": result["entries"],
                          "llm_calls": stats.llm_calls, "tokens_in": stats.input_tokens, "tokens_out": stats.output_tokens,
                          "cost_usd": None if stats.estimated_cost is None else str(stats.estimated_cost)}  # fmt: skip
            lines.append(report)
            out("heldout: " + json.dumps(report, sort_keys=True, ensure_ascii=True))
            append_ledger(ledger, entry(sha, reference.document_id, "completed"))
            completed += 1
    except Exception as error:  # the document in hand stays "started" in the ledger: its one shot is used
        print(f"heldout: stopped {type(error).__name__}", file=sys.stderr)
    finished = completed == len(documents)
    out("HELD-OUT RUN COMPLETE" if finished else f"HELD-OUT RUN INCOMPLETE {completed} of {len(documents)} documents")
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"heldout_{run_id}.json").write_text(
        json.dumps({**header, "complete": finished, "reports": lines}, sort_keys=True, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if finished else 1


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None, **overrides) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--held-out-run", action="store_true", help="required: this command sends held-out documents")
    parser.add_argument("--document", nargs=2, action="append", metavar=("PDF", "REFERENCE"), default=[])
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML")
    args = parser.parse_args(argv)
    try:
        return run_held_out(
            [(Path(pdf), Path(reference)) for pdf, reference in args.document],
            flag=args.held_out_run, env=os.environ if env is None else env, config=args.config, **overrides,
        )  # fmt: skip
    except HeldOutRefused as refused:
        print(f"heldout: refused: {refused.reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
