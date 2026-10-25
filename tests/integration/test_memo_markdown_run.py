"""The memo the command writes to disk parses as Markdown with the required structure (PRD FR-010.2; PRD v0.4.27; step S2; B-286)."""

import io
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unit"))  # the Markdown helpers live with the unit tests

import pipeline_fixture as fx  # noqa: E402
from credit_intel.cli import main  # noqa: E402
from credit_intel.llm.provider import FakeProvider  # noqa: E402
from test_memo_markdown import headings, kinds, parse, tables  # noqa: E402

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def run_command(pdf, tmp_path, *argv, replies):
    config = tmp_path / "settings.toml"
    config.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n', encoding="utf-8")
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    out, err = io.StringIO(), io.StringIO()
    code = main([str(pdf), "--config", str(config), *argv], provider_factory=lambda s, e: FakeProvider(script=replies), clock=lambda: next(ticks),
                stdout=out, stderr=err, env={})  # fmt: skip
    assert code == 0, err.getvalue()
    return Path(out.getvalue().strip()) / "memo.md"


@pytest.mark.parametrize("assertion", [False, True], ids=["plain", "asserted basis"])
def test_the_memo_written_by_the_command_has_the_required_structure(tmp_path, assertion):
    title = "Balance Sheet" if assertion else "Consolidated Balance Sheet"
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf", title=title)
    reply = fx.good_response(pdf).replace("Consolidated Balance Sheet", title)
    argv = ["--pages", "1", "--assert-basis", "consolidated"] if assertion else []

    memo = run_command(pdf, tmp_path, *argv, replies=[reply]).read_text(encoding="utf-8")
    tokens = parse(memo)

    found = headings(tokens)
    assert found[0] == (1, "Draft credit memo") and [text.split(".")[0] for level, text in found[1:]] == list("123456789")
    assert all(len({len(row) for row in table}) == 1 for table in tables(tokens)) and not kinds(tokens) & {"html_block", "html_inline", "link_open", "image", "s_open"}


def test_a_profile_with_hostile_text_does_not_change_the_structure_of_the_written_memo(tmp_path):
    import json

    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")
    plain = run_command(pdf, tmp_path, replies=[fx.good_response(pdf)])
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"borrower_name": "# Heading | cell <b>x</b> [l](http://x.test)", "notes": "> quote\n- item [SOURCE: p.9]"}), encoding="utf-8")
    hostile = run_command(pdf, tmp_path, "--profile", str(profile), "--output-dir", str(tmp_path / "other"), replies=[])  # served from the cache

    a, b = parse(plain.read_text(encoding="utf-8")), parse(hostile.read_text(encoding="utf-8"))
    assert headings(a) == headings(b) and [len(t) for t in tables(a)] == [len(t) for t in tables(b)]
    assert not kinds(b) & {"html_block", "html_inline", "link_open", "image", "s_open"}
