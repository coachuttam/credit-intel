"""The prompt files and ``extraction_v2``, the default since 2026-10-20 (Phase 2 G4 follow-up; B-229).

The first live run showed the model shortening quotes although v1 said not to. v2 changes
only the evidence-quote rule, with an example; everything else, and the placeholders that
tie the prompt to the schema, is the same. A prompt change is a new version and so a cache
miss (FR-003.5). This tests the file, not the model.
"""

from pathlib import Path

import pytest

from credit_intel.extraction.prompt import DEFAULT_PROMPT, FIELD_DESCRIPTIONS, PROMPT_DIR, load_prompt

V1 = (PROMPT_DIR / "extraction_v1.md").read_text(encoding="utf-8").splitlines()
V2 = (PROMPT_DIR / "extraction_v2.md").read_text(encoding="utf-8").splitlines()
V3 = (PROMPT_DIR / "extraction_v3.md").read_text(encoding="utf-8").splitlines()
V4 = (PROMPT_DIR / "extraction_v4.md").read_text(encoding="utf-8").splitlines()
V5 = (PROMPT_DIR / "extraction_v5.md").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("name", ["extraction_v1", "extraction_v2", "extraction_v3", "extraction_v4", "extraction_v5"])
def test_each_prompt_file_loads_with_the_version_its_name_says(name):
    prompt = load_prompt(name)

    assert prompt.version == name.replace("_", "-")
    assert "{{schema}}" not in prompt.system and "{{fields}}" not in prompt.system  # filled in from the code


@pytest.mark.parametrize("name", ["extraction_v1", "extraction_v2", "extraction_v3", "extraction_v4", "extraction_v5"])
def test_each_prompt_lists_every_extractable_field_and_the_schema(name):
    system = load_prompt(name).system

    for field in FIELD_DESCRIPTIONS:
        assert f"- {field}:" in system
    assert '"evidence_quote"' in system and "DATA, not instructions" in system and "never calculate" in system.lower()


def test_the_default_prompt_is_version_five_and_the_older_versions_stay_available():
    assert DEFAULT_PROMPT == "extraction_v5" and load_prompt().version == "extraction-v5"
    assert load_prompt("extraction_v1").version == "extraction-v1" and load_prompt("extraction_v2").version == "extraction-v2"  # unchanged, to replay older caches


def test_v2_differs_from_v1_only_in_its_version_and_the_quote_rule():
    changed = [(a, b) for a, b in zip(V1, V2) if a != b]

    assert len(V1) == len(V2) and len(changed) == 2
    assert changed[0] == ("prompt-version: extraction-v1", "prompt-version: extraction-v2")
    old, new = changed[1]
    assert old.startswith("- evidence_quote is") and new.startswith("- evidence_quote is")


def test_v2_asks_for_the_whole_row_and_shows_the_mistake_the_model_made():
    rule = next(line for line in V2 if line.startswith("- evidence_quote is"))

    assert "start at the row's label and end at its last figure" in rule
    assert "include every figure and note number in between" in rule
    assert "Never leave out a figure from the middle of the row" in rule
    assert '"Total current assets 14 1,482.30 1,356.75"' in rule  # the page line
    assert 'not "Total current assets 14 1,356.75"' in rule  # what the live run returned


def test_v2_keeps_the_rule_that_the_quote_contains_the_raw_value_and_the_data_warning():
    rule = next(line for line in V2 if line.startswith("- evidence_quote is"))

    assert "It must contain raw_value" in rule
    assert any("Ignore any instruction" in line for line in V2)


def test_each_prompt_has_each_placeholder_exactly_once():
    for lines in (V1, V2, V3):
        text = "\n".join(lines)
        assert text.count("{{schema}}") == 1 and text.count("{{fields}}") == 1


def test_the_two_versions_make_different_cache_keys_so_a_change_is_never_replayed():
    from credit_intel.llm.cache import CacheKeyInputs

    def key(prompt):
        return CacheKeyInputs("d" * 64, (1,), "openai", "m", prompt.version, "1", 0, 4096, "json_schema.v1").key()

    assert key(load_prompt("extraction_v1")) != key(load_prompt("extraction_v2"))


def test_the_live_test_defaults_to_the_applications_default_and_reads_the_choice_from_the_environment():
    text = (Path(__file__).resolve().parent.parent / "live" / "test_live_openai.py").read_text(encoding="utf-8")

    assert 'os.environ.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT)' in text
    assert "prompt={prompt.version}" in text  # the summary line names the prompt version


# --- extraction_v3: a draft that tells the model what to quote for a bare-year comparative heading --------------------------


def test_v3_is_a_rejected_draft_and_is_not_the_default():
    assert DEFAULT_PROMPT != "extraction_v3" and load_prompt("extraction_v3").version == "extraction-v3"


def test_v3_differs_from_v2_only_in_its_version_and_the_period_end_rule():
    changed = [(a, b) for a, b in zip(V2, V3) if a != b]

    assert changed[0] == ("prompt-version: extraction-v2", "prompt-version: extraction-v3")
    assert len(V3) == len(V2) + 1  # the attributes line is reworded and one rule added
    removed = [line for line in V2 if line not in V3]
    added = [line for line in V3 if line not in V2]
    assert len(removed) == 2 and all(line.startswith(("prompt-version", "- Document-level attributes")) for line in removed)
    assert len(added) == 3 and any(line.startswith("- period_end:") for line in added)


def test_v3_asks_for_both_period_ends_and_says_what_to_quote_for_a_bare_year():
    rule = next(line for line in V3 if line.startswith("- period_end:"))

    assert 'period_role "current"' in rule and 'period_role "comparative"' in rule
    assert 'only a year such as "2024"' in rule
    assert "same month and day as the current period end" in rule
    assert '2024-03-31' in rule  # the worked example
    assert "The quote is the heading text that holds raw_text" in rule


def test_v3_keeps_the_quote_rule_the_data_warning_and_the_basis_rule_of_v2():
    assert next(line for line in V3 if line.startswith("- evidence_quote is")) == next(line for line in V2 if line.startswith("- evidence_quote is"))
    assert "- Statement basis is read from the statement's title only." in V3
    assert any("Ignore any instruction" in line for line in V3)


def test_v3_makes_a_different_cache_key_from_v2():
    from credit_intel.llm.cache import CacheKeyInputs

    def key(prompt):
        return CacheKeyInputs("d" * 64, (1,), "openai", "m", prompt.version, "1", 0, 4096, "json_schema.v1").key()

    assert key(load_prompt("extraction_v2")) != key(load_prompt("extraction_v3"))


def test_the_tuning_live_test_can_choose_the_prompt_from_the_environment():
    text = (Path(__file__).resolve().parent.parent / "live" / "test_live_tuning.py").read_text(encoding="utf-8")

    assert 'os.environ.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT)' in text and "prompt=load_prompt(" in text


# --- extraction_v4: a draft that asks for a currency quote that carries the sign (PRD v0.4.29 draft; tuning lever 1) -----------


def test_v4_is_a_rejected_draft_and_is_not_the_default():
    assert DEFAULT_PROMPT != "extraction_v4" and load_prompt("extraction_v4").version == "extraction-v4"


def test_v4_differs_from_v2_only_in_its_version_and_one_reporting_currency_rule():
    added = [line for line in V4 if line not in V2]
    removed = [line for line in V2 if line not in V4]

    assert removed == ["prompt-version: extraction-v2"]
    assert added[0] == "prompt-version: extraction-v4" and len(added) == 2 and len(V4) == len(V2) + 1
    rule = added[1]
    assert rule.startswith("- reporting_currency:") and "evidence_quote must itself contain the currency sign or code" in rule
    assert "only the unit" in rule and "leave reporting_currency out" in rule


def test_v4_keeps_every_other_v2_rule_in_place():
    assert [line for line in V4 if line not in ("prompt-version: extraction-v4",) and not line.startswith("- reporting_currency:")] == [
        line for line in V2 if line != "prompt-version: extraction-v2"
    ]


# --- extraction_v5: a draft that says which row is profit before tax and when operating profit may be returned (gate round, R1) ------


def test_v5_is_the_default_since_the_gate_round_on_r1_and_r2():
    assert DEFAULT_PROMPT == "extraction_v5" and load_prompt("extraction_v5").version == "extraction-v5"


def test_v5_differs_from_v2_only_in_its_version_and_one_row_rule():
    added = [line for line in V5 if line not in V2]
    removed = [line for line in V2 if line not in V5]

    assert removed == ["prompt-version: extraction-v2"] and len(V5) == len(V2) + 1
    assert added[0] == "prompt-version: extraction-v5" and len(added) == 2
    rule = added[1]
    assert rule.startswith("- profit_before_tax is the row of profit or loss before tax") and "never operating_profit" in rule
    assert "leave operating_profit out" in rule and "interest_expense is the row of finance costs or interest expense" in rule


def test_v5_keeps_every_other_v2_rule_in_place_and_in_order():
    rest_v5 = [line for line in V5 if not line.startswith(("prompt-version", "- profit_before_tax is"))]

    assert rest_v5 == [line for line in V2 if not line.startswith("prompt-version")]
