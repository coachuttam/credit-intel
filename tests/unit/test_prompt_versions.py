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
V6 = (PROMPT_DIR / "extraction_v6.md").read_text(encoding="utf-8").splitlines()
V7 = (PROMPT_DIR / "extraction_v7.md").read_text(encoding="utf-8").splitlines()
V8 = (PROMPT_DIR / "extraction_v8.md").read_text(encoding="utf-8").splitlines()
V9 = (PROMPT_DIR / "extraction_v9.md").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("name", ["extraction_v1", "extraction_v2", "extraction_v3", "extraction_v4", "extraction_v5", "extraction_v6", "extraction_v7", "extraction_v8", "extraction_v9"])
def test_each_prompt_file_loads_with_the_version_its_name_says(name):
    prompt = load_prompt(name)

    assert prompt.version == name.replace("_", "-")
    assert "{{schema}}" not in prompt.system and "{{fields}}" not in prompt.system  # filled in from the code


@pytest.mark.parametrize("name", ["extraction_v1", "extraction_v2", "extraction_v3", "extraction_v4", "extraction_v5", "extraction_v6", "extraction_v7", "extraction_v8", "extraction_v9"])
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


# --- extraction_v6: a draft that names "Finance cost(s)" as interest expense (gate round, R1 finance cost) -----------------------------


def test_v6_is_a_draft_and_the_default_stays_version_five():
    assert DEFAULT_PROMPT == "extraction_v5" and load_prompt("extraction_v6").version == "extraction-v6"


def test_v6_differs_from_v5_only_in_its_version_and_one_note_after_the_field_list():
    removed = [line for line in V5 if line not in V6]
    added = [line for line in V6 if line not in V5]

    assert removed == ["prompt-version: extraction-v5"] and added[0] == "prompt-version: extraction-v6" and len(added) == 2
    assert added[1].startswith("Note on interest_expense:") and '"Finance cost"' in added[1] and '"Finance costs"' in added[1]
    assert V6.index(added[1]) > V6.index("{{fields}}")  # after the list: the shared field descriptions are not edited


def test_v6_keeps_every_v5_line_in_order():
    assert V6[1 : len(V5)] == V5[1:] and V6[0] == "prompt-version: extraction-v6"  # the v5 text, line for line; the note is appended after it


def test_the_shared_field_descriptions_are_not_changed_by_v6():
    from credit_intel.extraction.prompt import FIELD_DESCRIPTIONS

    assert FIELD_DESCRIPTIONS["interest_expense"] == "finance costs or interest expense"  # a change here would alter v1 to v5 without a new version


# --- extraction_v7: a draft that says page_number is the page that holds the quote (gate round, R2 page 49 added) --------------------------


def test_v7_is_a_draft_and_the_default_stays_version_five():
    assert DEFAULT_PROMPT == "extraction_v5" and load_prompt("extraction_v7").version == "extraction-v7"


def test_v7_differs_from_v5_only_in_its_version_and_one_page_number_rule():
    removed = [line for line in V5 if line not in V7]
    added = [line for line in V7 if line not in V5]

    assert removed == ["prompt-version: extraction-v5"] and len(V7) == len(V5) + 1 and added[0] == "prompt-version: extraction-v7" and len(added) == 2
    assert added[1].startswith("- page_number, for a field and for an attribute alike, is the page whose text contains the evidence_quote exactly.")
    assert V7.index(added[1]) == next(i for i, line in enumerate(V7) if line.startswith("- Document-level attributes go in")) + 1


def test_v7_keeps_every_other_v5_line_in_order():
    assert [line for line in V7 if not line.startswith(("prompt-version", "- page_number, for a field"))] == [line for line in V5 if not line.startswith("prompt-version")]


# --- extraction_v8: a draft that describes debt by what a row is, not by its heading (gate round, R2 total borrowings) -------------------


def test_v8_is_a_draft_and_the_default_stays_version_five():
    assert DEFAULT_PROMPT == "extraction_v5" and load_prompt("extraction_v8").version == "extraction-v8"


def test_v8_is_v5_line_for_line_plus_one_note_after_the_field_list():
    removed = [line for line in V5 if line not in V8]
    added = [line for line in V8 if line not in V5]

    assert removed == ["prompt-version: extraction-v5"] and added[0] == "prompt-version: extraction-v8"
    assert V8[0] == "prompt-version: extraction-v8" and V8[1 : len(V5)] == V5[1:]
    note = next(line for line in V8 if line.startswith("Note on borrowings:"))
    assert V8.index(note) > V8.index("{{fields}}")


def test_the_v8_note_names_the_debt_rows_the_exclusions_and_the_rule_against_adding_rows_up():
    note = next(line for line in V8 if line.startswith("Note on borrowings:"))

    for row in ("short-term debt", "commercial paper", "the current portion of long-term debt", "long-term debt"):
        assert row in note
    for never in ("Lease liabilities", "trade payables"):
        assert never in note
    assert "borrowings_current" in note and "current_maturities_long_term_borrowings" in note and "borrowings_non_current" in note
    assert "not by the heading it sits under" in note and "Never add rows together yourself." in note


def test_the_shared_field_descriptions_are_still_not_changed_by_v8():
    from credit_intel.extraction.prompt import FIELD_DESCRIPTIONS

    assert FIELD_DESCRIPTIONS["borrowings_non_current"] == "borrowings under the non-current liabilities heading"  # the note overrides it for v8 only



# --- extraction_v9: a draft that maps debt captions to component fields and keeps the total field for a row labelled total ----------------


def test_v9_is_a_draft_and_the_default_stays_version_five():
    assert DEFAULT_PROMPT == "extraction_v5" and load_prompt("extraction_v9").version == "extraction-v9"


def test_v9_differs_from_v8_only_in_its_version_line_and_the_borrowings_note():
    changed = [(a, b) for a, b in zip(V8, V9, strict=True) if a != b]

    assert len(V8) == len(V9) and len(changed) == 2
    assert changed[0] == ("prompt-version: extraction-v8", "prompt-version: extraction-v9")
    assert changed[1][0].startswith("Note on borrowings:") and changed[1][1].startswith("Note on borrowings:")


def test_the_v9_note_maps_each_caption_to_its_field_and_limits_the_total_to_a_row_labelled_total():
    note = next(line for line in V9 if line.startswith("Note on borrowings:"))

    assert "long-term debt (or non-current borrowings) is borrowings_non_current" in note
    assert "short-term debt, commercial paper or current borrowings is borrowings_current" in note
    assert "is current_maturities_long_term_borrowings" in note
    assert "never total_borrowings merely because it is the only debt row" in note
    assert "whose own printed label says total" in note
    assert "do not require one" in note and "Lease liabilities" in note and "Never add rows together yourself." in note


def test_the_v9_note_holds_no_digits():
    note = next(line for line in V9 if line.startswith("Note on borrowings:"))

    assert not any(ch.isdigit() for ch in note)
