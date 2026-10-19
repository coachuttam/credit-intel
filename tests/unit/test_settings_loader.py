"""LLM settings loader (PRD D-02, NFR-09, OD-8; B-201).

The token ceiling is a required setting with no default. A missing, non-integer,
zero or negative value fails with ``E-CONFIG-INVALID``, and the error names the
setting without echoing its value.
"""

from pathlib import Path

import pytest

from credit_intel.config import (
    ENV_LLM_MODEL_ID,
    ENV_LLM_PROVIDER,
    ENV_TOKEN_CEILING,
    LLMSettings,
    load_llm_settings,
)
from credit_intel.ingestion.errors import ErrorCode, IngestionError

REPO_SETTINGS = Path(__file__).resolve().parent.parent.parent / "config" / "settings.toml"

VALID = '[llm]\nprovider = "openai"\nmodel_id = "gpt-4o-mini"\ntoken_ceiling = 50000\n'


def write(tmp_path, text: str) -> Path:
    path = tmp_path / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return path


def fails(path, env=None) -> str:
    with pytest.raises(IngestionError) as excinfo:
        load_llm_settings(path, env or {})
    assert excinfo.value.code is ErrorCode.CONFIG_INVALID
    return str(excinfo.value.detail)


# --- valid files and environment overrides ------------------------------------


def test_valid_file_loads(tmp_path):
    settings = load_llm_settings(write(tmp_path, VALID), {})

    assert settings == LLMSettings(provider="openai", model_id="gpt-4o-mini", token_ceiling=50000)


def test_environment_overrides_the_file(tmp_path):
    env = {ENV_LLM_PROVIDER: "fake", ENV_LLM_MODEL_ID: "other-model", ENV_TOKEN_CEILING: "1200"}

    settings = load_llm_settings(write(tmp_path, VALID), env)

    assert settings == LLMSettings(provider="fake", model_id="other-model", token_ceiling=1200)


def test_environment_can_supply_the_ceiling_missing_from_the_file(tmp_path):
    text = '[llm]\nprovider = "openai"\nmodel_id = "gpt-4o-mini"\n'

    settings = load_llm_settings(write(tmp_path, text), {ENV_TOKEN_CEILING: "7"})

    assert settings.token_ceiling == 7


def test_other_tables_in_the_file_are_ignored(tmp_path):
    text = VALID + "\n[ingestion]\nmax_pages = 100\n"

    assert load_llm_settings(write(tmp_path, text), {}).token_ceiling == 50000


# --- the token ceiling is required, with no default ----------------------------


def test_missing_ceiling_fails_and_names_the_setting(tmp_path):
    text = '[llm]\nprovider = "openai"\nmodel_id = "gpt-4o-mini"\n'

    assert fails(write(tmp_path, text)) == "llm.token_ceiling"


@pytest.mark.parametrize(
    "value",
    ["0", "-5", "1.5", '"50000"', "true", "false", "[1]"],
    ids=["zero", "negative", "float", "quoted string", "true", "false", "list"],
)
def test_invalid_ceiling_in_the_file_fails(tmp_path, value):
    text = f'[llm]\nprovider = "openai"\nmodel_id = "gpt-4o-mini"\ntoken_ceiling = {value}\n'

    assert fails(write(tmp_path, text)) == "llm.token_ceiling"


@pytest.mark.parametrize(
    "value",
    ["", "0", "-1", "1.5", "1e3", " 12", "12 ", "abc", "١٢"],
    ids=["empty", "zero", "negative", "float", "exponent", "leading space", "trailing space", "text", "arabic digits"],
)
def test_invalid_ceiling_in_the_environment_fails(tmp_path, value):
    assert fails(write(tmp_path, VALID), {ENV_TOKEN_CEILING: value}) == "llm.token_ceiling"


def test_the_error_never_echoes_the_value(tmp_path):
    text = '[llm]\nprovider = "openai"\nmodel_id = "gpt-4o-mini"\ntoken_ceiling = -987654\n'

    with pytest.raises(IngestionError) as excinfo:
        load_llm_settings(write(tmp_path, text), {})

    assert "987654" not in str(excinfo.value)


# --- provider and model --------------------------------------------------------


@pytest.mark.parametrize("provider", ['"anthropic"', '""', '"  "', "3"])
def test_unknown_or_empty_provider_fails(tmp_path, provider):
    text = f'[llm]\nprovider = {provider}\nmodel_id = "m"\ntoken_ceiling = 5\n'

    assert fails(write(tmp_path, text)) == "llm.provider"


@pytest.mark.parametrize("model_id", ['""', '"   "', "3"])
def test_empty_or_non_string_model_fails(tmp_path, model_id):
    text = f'[llm]\nprovider = "openai"\nmodel_id = {model_id}\ntoken_ceiling = 5\n'

    assert fails(write(tmp_path, text)) == "llm.model_id"


def test_missing_provider_or_model_fails(tmp_path):
    assert fails(write(tmp_path, '[llm]\nmodel_id = "m"\ntoken_ceiling = 5\n')) == "llm.provider"
    assert fails(write(tmp_path, '[llm]\nprovider = "openai"\ntoken_ceiling = 5\n')) == "llm.model_id"


def test_empty_environment_override_counts_as_set_and_is_invalid(tmp_path):
    assert fails(write(tmp_path, VALID), {ENV_LLM_PROVIDER: ""}) == "llm.provider"
    assert fails(write(tmp_path, VALID), {ENV_LLM_MODEL_ID: ""}) == "llm.model_id"


# --- unknown settings and unreadable files ---------------------------------------


def test_unknown_setting_in_the_llm_table_fails_and_names_it(tmp_path):
    assert fails(write(tmp_path, VALID + "token_celing = 5\n")) == "llm.token_celing"


def test_llm_that_is_not_a_table_fails(tmp_path):
    assert fails(write(tmp_path, 'llm = "x"\n')) == "llm"


def test_missing_file_fails(tmp_path):
    assert fails(tmp_path / "absent.toml") == "settings file"


def test_unparsable_file_fails(tmp_path):
    assert fails(write(tmp_path, "[llm\nprovider = ")) == "settings file"


def test_file_that_is_not_utf8_fails(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_bytes(b"[llm]\nprovider = \xff\n")

    assert fails(path) == "settings file"


def test_reading_the_process_environment_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_TOKEN_CEILING, "321")

    assert load_llm_settings(write(tmp_path, VALID)).token_ceiling == 321


# --- the shipped settings file --------------------------------------------------


def test_shipped_settings_file_leaves_the_ceiling_unset():
    # NFR-09 / OD-8: no default is shipped, so loading it as is must fail.
    assert fails(REPO_SETTINGS) == "llm.token_ceiling"


def test_shipped_settings_file_works_once_a_ceiling_is_supplied():
    settings = load_llm_settings(REPO_SETTINGS, {ENV_TOKEN_CEILING: "1000"})

    assert settings == LLMSettings(provider="openai", model_id="gpt-4o-mini", token_ceiling=1000)
