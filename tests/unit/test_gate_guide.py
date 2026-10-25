"""The gate guide's example is a valid reference and its commands name real options (B-276; Phase 5 Part 2 preparation)."""

import json
import re
from pathlib import Path

from credit_intel.evaluation.gate import load_reference
from credit_intel.models import Scale

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs" / "gate_round_guide.md").read_text(encoding="utf-8")


def command_blocks():
    """The text of the fenced blocks that have no language (the shell commands), found by walking the fences."""
    blocks, current, language = [], None, None
    for line in GUIDE.split("\n"):
        if line.startswith("```"):
            if current is None:
                current, language = [], line[3:].strip()
            else:
                if language == "":
                    blocks.append("\n".join(current))
                current = None
        elif current is not None:
            current.append(line)
    return blocks


def test_the_example_reference_is_valid(tmp_path):
    block = re.search(r"```json\n(.*?)```", GUIDE, re.S).group(1)
    path = tmp_path / "example.json"
    path.write_text(block, encoding="utf-8")

    reference = load_reference(path)

    assert len(reference.entries) == 6 and json.loads(block)["document_id"] == "R9"


def test_the_guides_second_example_with_pages_and_an_assertion_is_valid(tmp_path):
    blocks = re.findall(r"```json\n(.*?)```", GUIDE, re.S)
    second = json.loads(blocks[1].replace("[ ... the six entries as above ... ]", json.dumps(json.loads(blocks[0])["entries"])))
    path = tmp_path / "r2.json"
    path.write_text(json.dumps(second), encoding="utf-8")

    reference = load_reference(path)

    assert (reference.pages, reference.assert_basis.value, reference.document_id) == ("36-38", "consolidated", "R2")


def test_every_scale_the_guide_lists_is_a_real_scale():
    listed = re.search(r"`scale` is one of ([^.]+)\.", GUIDE).group(1)

    assert set(re.findall(r"`(\w+)`", listed)) == {s.value for s in Scale}


def test_the_options_in_the_guides_commands_exist_in_the_gate():
    from credit_intel.evaluation import gate

    source = Path(gate.__file__).read_text(encoding="utf-8")
    for option in set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", " ".join(command_blocks()))) - {"--locked"}:  # uv's own flag
        assert f'"{option}"' in source, option


def test_the_guide_keeps_real_figures_out_of_git_and_says_so():
    assert "private/eval/" in GUIDE and "Never commit" in GUIDE
    assert "private/" in (ROOT / ".gitignore").read_text(encoding="utf-8").split("\n")


def test_the_guide_records_how_the_two_points_were_settled():
    assert "(a) R2 — settled 2026-10-25: option 3" in GUIDE and "(b) What \"borrowings\" means." in GUIDE
    assert "`basis_evidence`" in GUIDE and "--assert-basis consolidated" in GUIDE
