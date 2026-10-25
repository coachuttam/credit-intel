"""The settings of the optional page classifier: USE_JEV, the [jev] and [steps] tables, the key names (PRD v0.4.31; B-297)."""

from decimal import Decimal

import pytest

from credit_intel.config import (
    DEFAULT_SETTINGS_PATH,
    JevSettings,
    StepSettings,
    load_jev_settings,
    load_step_settings,
    typesafe_api_key,
)
from credit_intel.ingestion.errors import ErrorCode, IngestionError

BASE = '[llm]\nprovider = "openai"\nmodel_id = "m"\ntoken_ceiling = 1000\nmax_output_tokens = 100\n'


def settings_file(tmp_path, extra=""):
    path = tmp_path / "settings.toml"
    path.write_text(extra + BASE if extra and not extra.startswith("[") else BASE + extra, encoding="utf-8")  # a bare key goes before the first table
    return path


def invalid(call, setting):
    with pytest.raises(IngestionError) as caught:
        call()
    assert caught.value.code is ErrorCode.CONFIG_INVALID and setting in str(caught.value)


# --- off by default, and then nothing else is read ---------------------------------------------------------------------------------


def test_without_use_jev_the_step_is_off_with_the_default_settings(tmp_path):
    assert load_jev_settings(settings_file(tmp_path), {}) == JevSettings() and not JevSettings().enabled


@pytest.mark.parametrize("value", [None, "", "false", "FALSE", " False "])
def test_use_jev_false_or_absent_or_empty_is_off(tmp_path, value):
    env = {} if value is None else {"USE_JEV": value}

    assert not load_jev_settings(settings_file(tmp_path), env).enabled


def test_when_off_the_jev_table_and_even_the_settings_file_are_not_read(tmp_path):
    broken = settings_file(tmp_path, "[jev]\nthreshold = 7\nnonsense = 1\n")

    assert load_jev_settings(broken, {}) == JevSettings()
    assert load_jev_settings(tmp_path / "absent.toml", {"USE_JEV": "false"}) == JevSettings()


@pytest.mark.parametrize("value", ["true", "TRUE", " True "])
def test_use_jev_true_turns_it_on(tmp_path, value):
    assert load_jev_settings(settings_file(tmp_path), {"USE_JEV": value}).enabled


@pytest.mark.parametrize("value", ["yes", "1", "on", "ture", "truee"])
def test_any_other_value_is_a_configuration_error_naming_the_variable_not_its_value(tmp_path, value):
    with pytest.raises(IngestionError) as caught:
        load_jev_settings(settings_file(tmp_path), {"USE_JEV": value})

    assert caught.value.code is ErrorCode.CONFIG_INVALID and str(caught.value).endswith("(USE_JEV)")  # the message names the variable and ends there: the value is not in it


# --- the table -------------------------------------------------------------------------------------------------------------------


def test_the_shipped_settings_file_has_the_documented_values():
    jev = load_jev_settings(DEFAULT_SETTINGS_PATH, {"USE_JEV": "true"})

    assert jev == JevSettings(enabled=True, model="jev-latest", threshold=0.85, timeout_seconds=10.0, time_budget_seconds=60.0, state_lines=40, max_consecutive_failures=3)
    assert jev.price_input_per_million is None  # no default price (D-02)
    assert load_step_settings(DEFAULT_SETTINGS_PATH, "openai") == StepSettings("jev", "openai")


def test_the_table_overrides_the_defaults(tmp_path):
    path = settings_file(tmp_path, '[jev]\nmodel = "jev-1.14.0"\nthreshold = 0.9\ntimeout_seconds = 5\ntime_budget_seconds = 30\nstate_lines = 12\nmax_consecutive_failures = 5\nprice_input_per_million = 0.042\n')

    jev = load_jev_settings(path, {"USE_JEV": "true"})

    assert (jev.model, jev.threshold, jev.timeout_seconds, jev.time_budget_seconds, jev.state_lines, jev.max_consecutive_failures) == ("jev-1.14.0", 0.9, 5.0, 30.0, 12, 5)
    assert jev.price_input_per_million == Decimal("0.042")


def test_the_price_can_come_from_the_environment_and_wins(tmp_path):
    path = settings_file(tmp_path, "[jev]\nprice_input_per_million = 0.5\n")

    jev = load_jev_settings(path, {"USE_JEV": "true", "CREDIT_INTEL_JEV_PRICE_INPUT_PER_MILLION": "0.042"})

    assert jev.price_input_per_million == Decimal("0.042")


@pytest.mark.parametrize(
    ("extra", "setting"),
    [
        ("[jev]\nthreshold = 0\n", "jev.threshold"),
        ("[jev]\nthreshold = 1.5\n", "jev.threshold"),
        ('[jev]\nthreshold = "high"\n', "jev.threshold"),
        ("[jev]\nthreshold = true\n", "jev.threshold"),
        ("[jev]\ntimeout_seconds = 0\n", "jev.timeout_seconds"),
        ("[jev]\ntime_budget_seconds = -1\n", "jev.time_budget_seconds"),
        ("[jev]\nstate_lines = 0\n", "jev.state_lines"),
        ("[jev]\nstate_lines = 2.5\n", "jev.state_lines"),
        ("[jev]\nmax_consecutive_failures = 0\n", "jev.max_consecutive_failures"),
        ("[jev]\nmodel = 3\n", "jev.model"),
        ('[jev]\nmodel = ""\n', "jev.model"),
        ("[jev]\nprice_input_per_million = -1\n", "jev.price_input_per_million"),
        ("[jev]\nnonsense = 1\n", "jev.nonsense"),
        ("jev = 3\n", "jev"),
    ],
)
def test_an_invalid_table_is_a_configuration_error_naming_the_setting(tmp_path, extra, setting):
    invalid(lambda: load_jev_settings(settings_file(tmp_path, extra), {"USE_JEV": "true"}), setting)


def test_a_missing_settings_file_is_a_configuration_error_only_when_the_step_is_on(tmp_path):
    invalid(lambda: load_jev_settings(tmp_path / "absent.toml", {"USE_JEV": "true"}), "settings file")


# --- the steps ---------------------------------------------------------------------------------------------------------------------


def test_without_a_steps_table_the_defaults_are_jev_and_the_llm_provider(tmp_path):
    assert load_step_settings(settings_file(tmp_path), "openai") == StepSettings("jev", "openai")
    assert load_step_settings(settings_file(tmp_path), "fake") == StepSettings("jev", "fake")


def test_the_steps_table_names_a_provider_for_each_step(tmp_path):
    path = settings_file(tmp_path, '[steps]\nclassify = "jev"\nextract = "openai"\n')

    assert load_step_settings(path, "openai") == StepSettings("jev", "openai")


@pytest.mark.parametrize(
    ("extra", "setting"),
    [
        ('[steps]\nclassify = "gpt"\n', "steps.classify"),
        ('[steps]\nextract = "jev"\n', "steps.extract"),
        ('[steps]\nextract = "fake"\n', "steps.extract"),  # the extractor is the [llm] provider; the two must agree
        ('[steps]\nsummarise = "openai"\n', "steps.summarise"),
        ("[steps]\nclassify = 3\n", "steps.classify"),
        ("steps = 1\n", "steps"),
    ],
)
def test_a_bad_steps_table_is_a_configuration_error_naming_the_setting(tmp_path, extra, setting):
    invalid(lambda: load_step_settings(settings_file(tmp_path, extra), "openai"), setting)


# --- the key -----------------------------------------------------------------------------------------------------------------------


def test_the_key_is_typesafe_api_key_or_failing_that_jev_api_key():
    assert typesafe_api_key({"TYPESAFE_API_KEY": "a"}) == "a"
    assert typesafe_api_key({"JEV_API_KEY": "b"}) == "b"
    assert typesafe_api_key({"TYPESAFE_API_KEY": "a", "JEV_API_KEY": "b"}) == "a"
    assert typesafe_api_key({"TYPESAFE_API_KEY": "  ", "JEV_API_KEY": "b"}) == "b"
    assert typesafe_api_key({"TYPESAFE_API_KEY": " a \n"}) == "a"


def test_no_key_is_none_and_an_empty_one_is_no_key():
    assert typesafe_api_key({}) is None and typesafe_api_key({"TYPESAFE_API_KEY": "", "JEV_API_KEY": " "}) is None
