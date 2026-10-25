"""The held-out run tool and its narrow send exception (PRD v0.4.41; B-314). Synthetic PDFs, synthetic assignment records, a fake provider: no real document."""

import ast
import json
from pathlib import Path

import pytest

import pipeline_fixture as fx
import test_gate_run as g
from credit_intel.evaluation import heldout
from credit_intel.evaluation.gate import replay
from credit_intel.evaluation.guard import MEMBERS, SendRefused, file_sha256
from credit_intel.evaluation.heldout import ENV_HELD_OUT_APPROVED, HeldOutRefused, run_held_out
from credit_intel.extraction.prompt import load_prompt
from credit_intel.llm.provider import FakeProvider

HEAD = "0123456789abcdef0123456789abcdef01234567"
ENV = {ENV_HELD_OUT_APPROVED: HEAD[:12]}


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf", rows=g.ROWS)


class Setup:
    """One held-out document, its record, its reference, an empty ledger and cache, and a frozen repository."""

    def __init__(self, tmp_path, pdf, group="held_out", extra_rows=()):
        self.tmp_path, self.pdf = tmp_path, pdf
        self.assignments = tmp_path / "assignments.jsonl"
        rows = [("H9", file_sha256(pdf), group), *extra_rows]
        self.assignments.write_text(
            "\n".join(json.dumps(dict(zip(MEMBERS, (d, s, k, "2026-10-24", "assigned", None, None), strict=True))) for d, s, k in rows) + "\n", encoding="utf-8"
        )
        self.reference = tmp_path / "ref.json"
        self.reference.write_text(json.dumps(g.reference_data(pdf, document_id="H9")), encoding="utf-8")
        self.config = g.config.__wrapped__(tmp_path) if hasattr(g.config, "__wrapped__") else tmp_path / "settings.toml"
        self.config.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n', encoding="utf-8")
        self.ledger, self.cache, self.reports = tmp_path / "ledger.jsonl", tmp_path / "cache", tmp_path / "reports"
        self.provider = FakeProvider(script=[g.reply(pdf)])
        self.output: list[str] = []
        self.changed: list[str] = []

    def run(self, documents=None, flag=True, env=None, **over):
        kw = dict(root=self.tmp_path, assignments=self.assignments, ledger=self.ledger, config=self.config, cache_dir=self.cache, report_dir=self.reports,
                  provider_factory=lambda llm: self.provider, repo=lambda root: (HEAD, self.changed), out=self.output.append)  # fmt: skip
        kw.update(over)
        return run_held_out(documents if documents is not None else [(self.pdf, self.reference)], flag=flag, env=ENV if env is None else env, **kw)

    def refused(self, reason, **kw):
        with pytest.raises(HeldOutRefused) as raised:
            self.run(**kw)
        assert raised.value.reason == reason
        assert self.provider.calls == [] and self.output == []  # nothing sent, nothing printed
        return raised.value

    def ledger_lines(self):
        return [json.loads(line) for line in self.ledger.read_text(encoding="utf-8").splitlines()] if self.ledger.exists() else []


@pytest.fixture
def setup(tmp_path, pdf):
    return Setup(tmp_path, pdf)


def test_b6_128_without_the_flag_nothing_is_read(setup):
    setup.refused("no_flag", flag=False)


def test_b6_129_without_the_approval_or_with_another_commit_the_run_is_refused(setup):
    setup.refused("no_approval", env={})
    setup.refused("no_approval", env={ENV_HELD_OUT_APPROVED: "0123456789ab"[:11]})
    setup.refused("no_approval", env={ENV_HELD_OUT_APPROVED: "fedcba987654"})


def test_b6_130_a_changed_file_under_a_frozen_path_refuses_the_run(setup):
    setup.changed = [" M src/credit_intel/config.py"]

    setup.refused("not_frozen")


def test_b6_131_a_tuning_document_is_refused(tmp_path, pdf):
    setup = Setup(tmp_path, pdf, group="tuning")

    setup.refused("not_held_out")


def test_b6_132_a_missing_or_duplicated_held_out_document_refuses_the_run(tmp_path, pdf):
    other = fx.balance_sheet_pdf(tmp_path / "other.pdf", rows=[*g.ROWS, ("Total borrowings", "", "1.00", "2.00")])
    setup = Setup(tmp_path, pdf, extra_rows=[("H8", file_sha256(other), "held_out")])

    setup.refused("not_the_held_out_set")  # H8 left out
    setup.refused("not_the_held_out_set", documents=[(pdf, setup.reference), (pdf, setup.reference)])  # one given twice


def test_b6_133_a_document_in_the_ledger_refuses_the_whole_run_and_nothing_is_sent(setup):
    setup.ledger.write_text(json.dumps(dict(zip(heldout.LEDGER_MEMBERS, ("H9", file_sha256(setup.pdf), "H-old", "completed", "2026-10-25T00:00:00Z", HEAD, "x"), strict=True)), separators=(",", ":")) + "\n", encoding="utf-8")

    setup.refused("already_used")


def test_b6_134_a_run_that_dies_after_the_first_send_has_used_its_shot(setup):
    setup.provider = FakeProvider(script=[])  # the first request fails

    code = setup.run()

    assert code == 1 and [r["event"] for r in setup.ledger_lines()] == ["started"]
    assert "HELD-OUT RUN INCOMPLETE 0 of 1 documents" in setup.output
    again = Setup(setup.tmp_path, setup.pdf)
    again.cache = setup.tmp_path / "cache2"
    with pytest.raises(HeldOutRefused) as raised:
        again.run()
    assert raised.value.reason == "already_used" and again.provider.calls == []


@pytest.mark.parametrize("content", ["not json\n", '{"document_id":"H9"}\n', "{}", '﻿{"a":1}\n'])
def test_b6_135_a_malformed_ledger_refuses_everything(setup, content):
    setup.ledger.write_bytes(content.encode("utf-8"))

    setup.refused("ledger_unreadable")


def test_b6_136_a_second_provider_refuses_the_run(setup):
    setup.refused("second_provider", env={**ENV, "USE_JEV": "true"})


def test_b6_137_a_non_empty_response_cache_refuses_the_run(setup):
    setup.cache.mkdir()
    (setup.cache / "x.json").write_text("{}", encoding="utf-8")

    setup.refused("cache_not_empty")


def test_a_reference_written_for_another_document_is_refused(setup):
    data = json.loads(setup.reference.read_text(encoding="utf-8"))
    data["sha256"] = "0" * 64
    setup.reference.write_text(json.dumps(data), encoding="utf-8")

    setup.refused("reference_invalid")


def test_an_unreadable_assignment_record_is_refused(setup):
    setup.assignments.write_text("not json\n", encoding="utf-8")

    setup.refused("record_unreadable")


def test_b6_138_a_good_run_prints_counts_labelled_held_out_and_keeps_a_ledger(setup):
    code = setup.run()

    assert code == 0
    first, line, last = setup.output[0], setup.output[1], setup.output[-1]
    assert first.startswith("HELD-OUT RUN: ") and last == "HELD-OUT RUN COMPLETE"
    report = json.loads(line.removeprefix("heldout: "))
    assert report["set"] == "held_out" and report["document_id"] == "H9" and report["counts"] == {"match": 6, "mismatch": 0, "missing": 0}
    header = json.loads(first.removeprefix("HELD-OUT RUN: "))
    assert header["set"] == "held_out" and header["freeze_commit"] == HEAD and header["documents"] == 1
    assert [r["event"] for r in setup.ledger_lines()] == ["started", "completed"]
    assert {r["freeze_commit"] for r in setup.ledger_lines()} == {HEAD} and {r["run_id"] for r in setup.ledger_lines()} == {header["run_id"]}
    text = "\n".join(setup.output)
    for secret in ("352.70", "300.10", "Profit before tax", file_sha256(setup.pdf), str(setup.pdf)):
        assert secret not in text  # counts only: no value, label, hash or path
    saved = json.loads(next(setup.reports.glob("heldout_*.json")).read_text(encoding="utf-8"))
    assert saved["complete"] is True and saved["run_id"] == header["run_id"]


def test_a_second_run_of_the_same_document_is_refused_after_a_good_run(setup):
    setup.run()
    again = Setup(setup.tmp_path, setup.pdf)
    again.ledger, again.cache = setup.ledger, setup.tmp_path / "cache3"

    with pytest.raises(HeldOutRefused) as raised:
        again.run()

    assert raised.value.reason == "already_used"


def test_the_command_refuses_with_a_fixed_word_and_exit_code_two(setup, capsys):
    code = heldout.main(["--document", str(setup.pdf), str(setup.reference)], env={}, root=setup.tmp_path)

    assert code == 2 and capsys.readouterr().err.strip() == "heldout: refused: no_flag"


def test_b6_140_the_gate_still_refuses_a_held_out_document(setup):
    from credit_intel.evaluation.gate import load_reference

    with pytest.raises(SendRefused):
        replay(setup.pdf, load_reference(setup.reference), assignments=setup.assignments, cache_dir=setup.tmp_path / "c", config=setup.config, prompt=load_prompt())


def test_b6_141_a_tuning_gate_line_says_tuning(tmp_path, pdf):
    from credit_intel.evaluation.gate import load_reference

    setup = Setup(tmp_path, pdf, group="tuning")
    g.fill_cache(pdf, tmp_path)
    data = json.loads(setup.reference.read_text(encoding="utf-8"))
    data["document_id"] = "H9"
    setup.reference.write_text(json.dumps(data), encoding="utf-8")

    report = replay(pdf, load_reference(setup.reference), assignments=setup.assignments, cache_dir=tmp_path / ".cache" / "llm", config=setup.config, prompt=load_prompt())

    assert report["set"] == "tuning"


def test_only_the_held_out_tool_uses_the_held_out_exception():
    root = Path(heldout.__file__).resolve().parents[1]
    users = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.Name) and n.id == "allow_held_out_send" or isinstance(n, ast.Attribute) and n.attr == "allow_held_out_send" or isinstance(n, ast.alias) and n.name == "allow_held_out_send" for n in ast.walk(tree)):
            users.append(path.name)
    assert sorted(set(users)) == ["heldout.py"]  # guard.py only defines it


def test_no_other_module_imports_the_held_out_tool():
    root = Path(heldout.__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        if path.name == "heldout.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import | ast.ImportFrom) else []
            module = node.module if isinstance(node, ast.ImportFrom) else ""
            assert "heldout" not in [*names, module or ""] and not any(n.endswith("heldout") for n in names), path.name


def test_one_held_out_document_given_twice_is_refused(setup):
    setup.refused("not_the_held_out_set", documents=[(setup.pdf, setup.reference), (setup.pdf, setup.reference)])


def test_a_ledger_line_with_an_unknown_event_is_refused(setup):
    record = dict(zip(heldout.LEDGER_MEMBERS, ("H9", "0" * 64, "H-x", "finished", "2026-10-25T00:00:00Z", HEAD, "x"), strict=True))
    setup.ledger.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")

    setup.refused("ledger_unreadable")


def _git(root, *args):
    import subprocess

    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args], check=True, capture_output=True)


def test_git_state_reports_the_head_and_every_change_under_the_frozen_paths(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "prompts").mkdir()
    (root / "other").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "other" / "b.txt").write_text("b\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "freeze")

    head, clean = heldout.git_state(root)
    assert len(head) == 40 and clean == []

    (root / "other" / "b.txt").write_text("changed\n", encoding="utf-8")  # outside the frozen paths: not a change to the freeze
    assert heldout.git_state(root)[1] == []
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert len(heldout.git_state(root)[1]) == 1
    _git(root, "checkout", "--", "src/a.py")
    (root / "prompts" / "new.md").write_text("untracked\n", encoding="utf-8")  # an untracked file counts
    assert len(heldout.git_state(root)[1]) == 1


def test_a_directory_that_is_not_a_repository_is_not_frozen(tmp_path):
    with pytest.raises(HeldOutRefused) as raised:
        heldout.git_state(tmp_path)

    assert raised.value.reason == "not_frozen"
