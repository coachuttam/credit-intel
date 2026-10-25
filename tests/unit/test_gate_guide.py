"""The gate guide's example is a valid reference and its commands name real options (B-276; Phase 5 Part 2 preparation)."""

import json
import re
from pathlib import Path

from credit_intel.evaluation.gate import load_reference
from credit_intel.models import Scale

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs" / "gate_round_guide.md").read_text(encoding="utf-8")


def test_the_example_reference_is_valid(tmp_path):
    block = re.search(r"```json\n(.*?)```", GUIDE, re.S).group(1)
    path = tmp_path / "example.json"
    path.write_text(block, encoding="utf-8")

    reference = load_reference(path)

    assert len(reference.entries) == 6 and json.loads(block)["document_id"] == "R9"


def test_every_scale_the_guide_lists_is_a_real_scale():
    listed = re.search(r"`scale` is one of ([^.]+)\.", GUIDE).group(1)

    assert set(re.findall(r"`(\w+)`", listed)) == {s.value for s in Scale}


def test_the_options_in_the_guides_commands_exist_in_the_gate():
    from credit_intel.evaluation import gate

    source = Path(gate.__file__).read_text(encoding="utf-8")
    for option in set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", " ".join(re.findall(r"```\n(.*?)```", GUIDE, re.S)))):
        assert f'"{option}"' in source, option


def test_the_guide_keeps_real_figures_out_of_git_and_says_so():
    assert "private/eval/" in GUIDE and "Never commit" in GUIDE
    assert "private/" in (ROOT / ".gitignore").read_text(encoding="utf-8").split("\n")


def test_the_guide_states_the_two_open_points():
    assert "(a) R2." in GUIDE and "(b) What \"borrowings\" means." in GUIDE
