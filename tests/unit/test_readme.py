"""The README says what the code does and nothing else (PRD Definition of Done item 9, FR-014, SEC-10; Phase 5 step 5l; B-271)."""

import re
import tomllib
from pathlib import Path

import pytest

from credit_intel import config as config_module
from credit_intel.cli import ENV_LOG_LEVEL, build_parser
from credit_intel.config import IngestionSettings, LocatorSettings, load_llm_settings
from credit_intel.ingestion.errors import CATALOGUE, EXIT_EXPORT, EXIT_EXTRACT, EXIT_INPUT, EXIT_LLM, EXIT_CONFIG
from credit_intel.memo import limitations

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def section(title):
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", README, re.M | re.S)
    assert match, title
    return match.group(1)


def test_the_readme_has_each_section_the_definition_of_done_asks_for():
    headings = re.findall(r"^## (.+)$", README, re.M)

    for needed in ("Status", "Quick start", "Scope and limitations", "Provisional thresholds", "The human-decision boundary", "Tests"):
        assert needed in headings


def test_it_starts_by_saying_it_is_a_draft_for_human_review_and_not_a_credit_decision():
    first = README.split("\n## ")[0]

    assert "draft credit memo for a human analyst to review" in first and "not a credit decision" in first


def test_it_says_the_held_out_evaluation_has_not_been_done_and_claims_no_measured_result():
    status = section("Status")

    assert "not been evaluated against the held-out set" in status and "none is claimed" in status
    assert not re.search(r"\d\s?%\s+(accura|precis|recall|coverage|correct)", README, re.I)


@pytest.mark.parametrize("sentence", [*limitations.SCOPE, *limitations.METRICS, *limitations.EXTRACTION])
def test_every_limitation_in_the_memo_is_in_the_readme_word_for_word(sentence):
    assert sentence in section("Scope and limitations")


def test_the_limits_it_states_are_the_ones_in_the_settings():
    text = section("Scope and limitations")
    ingestion, locator = IngestionSettings(), LocatorSettings()

    assert f"at most {ingestion.max_file_bytes // (1024 * 1024)} MB and {ingestion.max_pages} pages" in text.replace("may be ", "")
    assert f"at most {locator.max_candidates} candidate pages" in text


def test_the_provisional_notice_is_the_one_in_the_rules_file_and_the_boundary_text_is_the_memos():
    notice = tomllib.loads((ROOT / "config" / "risk_rules.toml").read_text(encoding="utf-8"))["provisional_notice"]

    assert f"> {notice}" in section("Provisional thresholds")
    assert limitations.REVIEW.strip("*") in section("The human-decision boundary")
    assert "never approves, rejects, rates, grades or scores" in section("The human-decision boundary")


def test_every_option_it_names_exists_in_the_command_and_every_option_of_the_command_is_named():
    parser = build_parser(open("/dev/null", "w"))
    real = {flag for action in parser._actions for flag in action.option_strings if flag.startswith("--")} - {"--help"}
    named = set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", README))

    assert real <= named and named <= real | {"--help", "--output"}  # --output is the option of `python -m credit_intel.report`, not of the command


def test_the_example_command_line_parses_with_the_real_parser():
    parser = build_parser(open("/dev/null", "w"))
    commands = re.findall(r"^uv run credit-intel (.+)$", README, re.M)

    assert commands
    for command in commands:
        parser.parse_args(command.split())


def test_the_exit_code_table_matches_the_catalogue():
    rows = dict(re.findall(r"^\| (\d+) \| (.+) \|$", section("Command line"), re.M))

    assert set(rows) == {"0", "1", "2", "3", "4", "5", "6", "7", "130"}
    assert {entry.exit_code for entry in CATALOGUE.values()} == {EXIT_INPUT, EXIT_EXTRACT, EXIT_LLM, EXIT_CONFIG, EXIT_EXPORT} == {3, 4, 5, 6, 7}


def test_the_settings_example_loads_and_the_defaults_it_shows_are_the_shipped_ones(tmp_path):
    block = re.search(r"```toml\n(.*?)```", README, re.S).group(1)
    path = tmp_path / "settings.toml"
    path.write_text(block, encoding="utf-8")
    shipped = tomllib.loads((ROOT / "config" / "settings.toml").read_text(encoding="utf-8"))["llm"]
    shown = tomllib.loads(block)["llm"]

    assert load_llm_settings(path, {}).token_ceiling == shown["token_ceiling"]
    assert {k: shown[k] for k in ("provider", "model_id", "max_output_tokens")} == {k: shipped[k] for k in ("provider", "model_id", "max_output_tokens")}
    assert "token_ceiling" not in shipped  # the README says it has no default


def test_every_environment_variable_it_names_exists_in_the_code():
    known = {value for name, value in vars(config_module).items() if name.startswith("ENV_") and isinstance(value, str)} | {ENV_LOG_LEVEL}
    named = set(re.findall(r"\b(?:CREDIT_INTEL_[A-Z_]+|OPENAI_API_KEY)\b", README))

    assert named and named <= known


def test_every_file_and_folder_it_points_to_exists():
    for path in re.findall(r"`((?:src|config|prompts|tests|docs)/[\w./-]*|PROGRESS\.md|CLAUDE\.md)`", README):
        assert (ROOT / path).exists(), path


def test_the_git_ignored_places_it_names_are_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for name in ("runs/", ".cache/", "private/"):
        assert name in ignore.split("\n")


def test_the_run_folder_files_it_names_are_the_ones_the_export_writes():
    from credit_intel.export import run_export

    text = section("What a run produces")
    for name in ("memo.md", "results.json", "manifest.json"):
        assert f"`{name}`" in text and name in Path(run_export.__file__).read_text(encoding="utf-8")


def test_the_nine_memo_sections_it_lists_are_the_memos():
    text = section("What a run produces")
    titles = ["borrower overview", "documents reviewed", "financial performance", "financial ratios", "potential risk indicators",
              "evidence and source references", "missing information and conflicts", "questions for the credit analyst", "limitations"]  # fmt: skip
    positions = [text.lower().index(title) for title in titles]

    assert positions == sorted(positions)
