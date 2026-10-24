"""The risk rules file and its loader (PRD FR-008.1, J.1, J.2, J.3; Phase 4 step 4a; B-247)."""

from decimal import Decimal
from pathlib import Path

import pytest

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.risk.config import DEFAULT_RULES_PATH, RiskRulesConfig, load_risk_rules
from credit_intel.risk.spec import RULE_ORDER, RULE_SPECS, Severity

SHIPPED = DEFAULT_RULES_PATH.read_text(encoding="utf-8")


def load_text(tmp_path, text: str | bytes) -> RiskRulesConfig:
    path = tmp_path / "risk_rules.toml"
    path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    return load_risk_rules(path)


def fails(tmp_path, text: str | bytes) -> str:
    with pytest.raises(IngestionError) as excinfo:
        load_text(tmp_path, text)
    assert excinfo.value.code is ErrorCode.CONFIG_INVALID
    return str(excinfo.value.detail)


def edit(old: str, new: str, count: int = 1) -> str:
    assert SHIPPED.count(old) >= 1, old
    return SHIPPED.replace(old, new, count)


# --- the shipped file is the J.3 table -------------------------------------------------------------------------------------------

J3 = {
    "RI-001": [("C1", "watch", "0"), ("C2", "elevated", "-10")],
    "RI-002": [("C1", "elevated", "0")],
    "RI-003": [("C1", "elevated", "1.00"), ("C2", "watch", "10")],
    "RI-004": [("C1", "watch", "20"), ("C2", "elevated", "2.00"), ("C3", "elevated", "0")],
    "RI-005": [("C1", "watch", "1.50"), ("C2", "elevated", "1.00")],
    "RI-006": [("C1", "info", None)],
    "RI-007": [("C1", "watch", None)],
}


def test_the_shipped_file_loads_the_seven_rules_in_order():
    config = load_risk_rules()

    assert [r.id for r in config.rules] == list(RULE_ORDER) == list(J3)
    assert all(r.enabled for r in config.rules)


def test_the_shipped_conditions_severities_and_thresholds_are_the_j3_defaults():
    config = load_risk_rules()

    for rule in config.rules:
        got = [(c.id, c.severity.value, None if c.threshold is None else str(c.threshold)) for c in rule.conditions]
        assert got == J3[rule.id], rule.id


def test_thresholds_are_exact_decimals_never_floats():
    config = load_risk_rules()

    for rule in config.rules:
        for condition in rule.conditions:
            assert condition.threshold is None or isinstance(condition.threshold, Decimal)
    assert str(config.rule("RI-005").condition("C1").threshold) == "1.50"  # the written precision survives


def test_a_decimal_that_a_float_cannot_hold_is_read_exactly(tmp_path):
    config = load_text(tmp_path, edit("threshold = 1.50", "threshold = 0.1"))

    assert config.rule("RI-005").condition("C1").threshold == Decimal("0.1")


def test_the_provisional_notice_is_carried_for_the_memo():
    notice = load_risk_rules().provisional_notice

    assert "illustrative placeholders" in notice and "not universal banking standards" in notice


def test_each_rule_names_its_inputs_and_has_a_name_and_description():
    config = load_risk_rules()

    assert config.rule("RI-006").inputs == ("MET-01", "MET-02", "MET-03", "MET-04", "MET-05")
    assert config.rule("RI-004").inputs == ("MET-04", "total_equity")
    for rule in config.rules:
        assert rule.name and rule.description and rule.inputs


def test_the_specifications_match_the_j3_condition_counts():
    assert [len(RULE_SPECS[r].conditions) for r in RULE_ORDER] == [2, 1, 2, 3, 2, 1, 1]
    assert [c.id for c in RULE_SPECS["RI-004"].conditions] == ["C1", "C2", "C3"]
    assert not any(c.takes_threshold for c in RULE_SPECS["RI-006"].conditions + RULE_SPECS["RI-007"].conditions)


def test_severities_are_ordered_info_watch_elevated():
    assert Severity.INFO.rank < Severity.WATCH.rank < Severity.ELEVATED.rank
    assert max([Severity.WATCH, Severity.ELEVATED, Severity.INFO], key=lambda s: s.rank) is Severity.ELEVATED


# --- changing a threshold needs no code change (FR-008.1) ------------------------------------------------------------------------------


def test_changing_a_threshold_in_the_file_changes_the_loaded_value(tmp_path):
    config = load_text(tmp_path, edit("threshold = 2.00", "threshold = 3.50"))

    assert config.rule("RI-004").condition("C2").threshold == Decimal("3.50")


def test_a_rule_can_be_switched_off_and_a_severity_changed(tmp_path):
    text = edit('id = "RI-002"\nname = "Negative net profit"\ndescription = "Net profit for the current period is below zero."\nenabled = true', 'id = "RI-002"\nname = "Negative net profit"\ndescription = "Net profit for the current period is below zero."\nenabled = false')
    config = load_text(tmp_path, text.replace('id = "C1"          # fires when current-period net profit is below the threshold\n  severity = "elevated"', 'id = "C1"          # fires when current-period net profit is below the threshold\n  severity = "watch"'))

    assert config.rule("RI-002").enabled is False and config.rule("RI-002").condition("C1").severity is Severity.WATCH
    assert all(r.enabled for r in config.rules if r.id != "RI-002")


def test_loading_twice_gives_equal_results():
    assert load_risk_rules() == load_risk_rules()


# --- the file as a whole -----------------------------------------------------------------------------------------------------------------


def test_a_missing_file_is_invalid(tmp_path):
    with pytest.raises(IngestionError) as excinfo:
        load_risk_rules(tmp_path / "absent.toml")
    assert excinfo.value.code is ErrorCode.CONFIG_INVALID and excinfo.value.detail == "risk rules file"


def test_a_file_that_is_not_toml_or_not_utf8_is_invalid(tmp_path):
    assert fails(tmp_path, "[[rule\nid = ") == "risk rules file"
    assert fails(tmp_path, b"provisional_notice = \xff\n") == "risk rules file"


def test_an_unknown_top_level_key_is_invalid_and_named(tmp_path):
    first_rule = SHIPPED.index("[[rule]]")

    assert fails(tmp_path, SHIPPED[:first_rule] + "score = 3\n\n" + SHIPPED[first_rule:]) == "score"


@pytest.mark.parametrize("notice", ['""', '"   "', "3"])
def test_the_provisional_notice_must_be_text(tmp_path, notice):
    start = SHIPPED.index("provisional_notice")
    end = SHIPPED.index("\n", start)

    assert fails(tmp_path, SHIPPED[:start] + f"provisional_notice = {notice}" + SHIPPED[end:]) == "provisional_notice"


def test_a_missing_notice_is_invalid(tmp_path):
    start = SHIPPED.index("provisional_notice")
    end = SHIPPED.index("\n", start)

    assert fails(tmp_path, SHIPPED[:start] + SHIPPED[end:]) == "provisional_notice"


def test_a_file_with_no_rules_is_invalid(tmp_path):
    assert fails(tmp_path, SHIPPED[: SHIPPED.index("[[rule]]")]) == "rule"


# --- the rules ---------------------------------------------------------------------------------------------------------------------------


def test_a_rule_with_an_unknown_id_is_invalid(tmp_path):
    assert fails(tmp_path, edit('id = "RI-007"', 'id = "RI-008"')) == "rule[6].id"


def test_a_rule_given_twice_or_left_out_is_invalid(tmp_path):
    assert fails(tmp_path, edit('id = "RI-007"', 'id = "RI-006"')) == "rule"
    assert fails(tmp_path, SHIPPED[: SHIPPED.index('[[rule]]\nid = "RI-007"')]) == "rule"


def test_an_unknown_key_in_a_rule_is_invalid_and_named(tmp_path):
    assert fails(tmp_path, edit('id = "RI-002"', 'id = "RI-002"\nweight = 3')) == "rule[1].weight"


@pytest.mark.parametrize("enabled", ['"yes"', "1", '"true"'])
def test_enabled_must_be_a_boolean(tmp_path, enabled):
    assert fails(tmp_path, edit("enabled = true", f"enabled = {enabled}")) == "rule[0].enabled"


def test_a_missing_enabled_flag_is_invalid(tmp_path):
    assert fails(tmp_path, edit("enabled = true\n", "", 1)) == "rule[0].enabled"


@pytest.mark.parametrize("inputs", ["[]", '"MET-01"', "[1]", '[""]'])
def test_inputs_must_be_a_non_empty_list_of_text(tmp_path, inputs):
    assert fails(tmp_path, edit('inputs = ["MET-01"]', f"inputs = {inputs}")) == "rule[0].inputs"


@pytest.mark.parametrize("key", ["name", "description"])
def test_name_and_description_must_be_text(tmp_path, key):
    start = SHIPPED.index(f"{key} = ")
    end = SHIPPED.index("\n", start)

    assert fails(tmp_path, SHIPPED[:start] + f'{key} = ""' + SHIPPED[end:]) == f"rule[0].{key}"


# --- the conditions ------------------------------------------------------------------------------------------------------------------------


def test_a_condition_with_an_unknown_id_is_invalid(tmp_path):
    assert fails(tmp_path, edit('id = "C2"          # fires when revenue growth is at or below', 'id = "C9"          # fires when revenue growth is at or below')) == "rule[0].condition[1].id"


def test_a_missing_or_repeated_condition_is_invalid(tmp_path):
    repeated = edit('id = "C2"          # fires when revenue growth is at or below', 'id = "C1"          # fires when revenue growth is at or below')
    assert fails(tmp_path, repeated) == "rule[0].condition"
    first_two = SHIPPED.index('  [[rule.condition]]\n  id = "C2"')
    next_rule = SHIPPED.index("[[rule]]", first_two)
    assert fails(tmp_path, SHIPPED[:first_two] + "\n" + SHIPPED[next_rule:]) == "rule[0].condition"


@pytest.mark.parametrize("severity", ['"critical"', '"ELEVATED"', "2", '""'])
def test_a_severity_outside_info_watch_elevated_is_invalid(tmp_path, severity):
    assert fails(tmp_path, edit('severity = "watch"\n  threshold = 0', f"severity = {severity}\n  threshold = 0")) == "rule[0].condition[0].severity"


def test_a_missing_severity_is_invalid(tmp_path):
    assert fails(tmp_path, edit('severity = "watch"\n  threshold = 0', "threshold = 0")) == "rule[0].condition[0].severity"


def test_a_missing_threshold_where_one_is_needed_is_invalid(tmp_path):
    assert fails(tmp_path, edit('severity = "watch"\n  threshold = 0', 'severity = "watch"')) == "rule[0].condition[0].threshold"


@pytest.mark.parametrize("threshold", ['"1.5"', "true", "false", "nan", "inf", "-inf", "[1]"])
def test_a_threshold_must_be_a_finite_number(tmp_path, threshold):
    assert fails(tmp_path, edit("threshold = 1.50", f"threshold = {threshold}")) == "rule[4].condition[0].threshold"


def test_a_threshold_on_a_condition_that_takes_none_is_invalid(tmp_path):
    assert fails(tmp_path, edit('severity = "info"', 'severity = "info"\n  threshold = 5')) == "rule[5].condition[0].threshold"


def test_an_unknown_key_in_a_condition_is_invalid_and_named(tmp_path):
    assert fails(tmp_path, edit('severity = "info"', 'severity = "info"\n  operator = "<"')) == "rule[5].condition[0].operator"


def test_the_operator_cannot_be_set_in_the_file(tmp_path):
    assert fails(tmp_path, edit('severity = "watch"\n  threshold = 0', 'severity = "watch"\n  threshold = 0\n  operator = ">"')) == "rule[0].condition[0].operator"


def test_the_error_names_the_setting_and_never_echoes_its_value(tmp_path):
    with pytest.raises(IngestionError) as excinfo:
        load_text(tmp_path, edit("threshold = 1.50", 'threshold = "secret-value-12345"'))

    assert "secret-value-12345" not in str(excinfo.value) and "secret-value-12345" not in str(excinfo.value.detail)
    with pytest.raises(IngestionError) as excinfo:
        load_text(tmp_path, edit('severity = "info"', 'severity = "secret-value-98765"'))
    assert "secret-value-98765" not in str(excinfo.value)
