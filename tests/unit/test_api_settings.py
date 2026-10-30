"""The ``[api]`` settings (PRD FR-016 criterion 9, v0.4.59): three limits and two absolute folders are required and have no default."""

import pytest

from credit_intel.config import DEFAULT_API_HOST, DEFAULT_API_PORT, DEFAULT_SETTINGS_PATH, load_api_settings
from credit_intel.ingestion.errors import ErrorCode, IngestionError

GOOD = '[api]\nmax_concurrent_runs = 1\nmax_queued_runs = 4\nrun_timeout_seconds = 1200\noutput_dir = "/srv/out"\ncache_dir = "/srv/cache"\n'


def load(tmp_path, text, env=None):
    path = tmp_path / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return load_api_settings(path, {} if env is None else env)


def invalid(tmp_path, text, setting, env=None):
    with pytest.raises(IngestionError) as error:
        load(tmp_path, text, env)
    assert error.value.code is ErrorCode.CONFIG_INVALID and setting in str(error.value)
    return error.value


def test_the_owners_values_load_and_host_and_port_default(tmp_path):
    settings = load(tmp_path, GOOD)
    assert (settings.max_concurrent_runs, settings.max_queued_runs, settings.run_timeout_seconds) == (1, 4, 1200)
    assert (str(settings.output_dir), str(settings.cache_dir)) == ("/srv/out", "/srv/cache")
    assert (settings.host, settings.port) == (DEFAULT_API_HOST, DEFAULT_API_PORT) == ("127.0.0.1", 8000)


def test_host_and_port_can_be_set(tmp_path):
    settings = load(tmp_path, GOOD + 'host = "0.0.0.0"\nport = 9001\n')
    assert (settings.host, settings.port) == ("0.0.0.0", 9001)


@pytest.mark.parametrize("name", ["max_concurrent_runs", "max_queued_runs", "run_timeout_seconds", "output_dir", "cache_dir"])
def test_each_required_setting_missing_is_config_invalid_naming_it(tmp_path, name):
    text = "\n".join(line for line in GOOD.splitlines() if not line.startswith(name))
    invalid(tmp_path, text, f"api.{name}")


def test_a_missing_api_table_is_config_invalid(tmp_path):
    invalid(tmp_path, "[llm]\nprovider = 'fake'\n", "api.max_concurrent_runs")


@pytest.mark.parametrize("bad", ["0", "-1", "1.5", '"3"', "true"])
@pytest.mark.parametrize("name", ["max_concurrent_runs", "max_queued_runs", "run_timeout_seconds"])
def test_a_limit_that_is_not_a_positive_integer_is_config_invalid_and_its_value_is_not_in_the_message(tmp_path, name, bad):
    text = GOOD.replace(next(line for line in GOOD.splitlines() if line.startswith(name)), f"{name} = {bad}")
    error = invalid(tmp_path, text, f"api.{name}")
    assert bad.strip('"') not in str(error)


@pytest.mark.parametrize("bad", ['"runs"', '"./relative"', '"~/out"', '""', "5", '"/ok\\u0000bad"'])
@pytest.mark.parametrize("name", ["output_dir", "cache_dir"])
def test_a_folder_that_is_not_an_absolute_path_is_config_invalid(tmp_path, name, bad):
    text = GOOD.replace(next(line for line in GOOD.splitlines() if line.startswith(name)), f"{name} = {bad}")
    invalid(tmp_path, text, f"api.{name}")


@pytest.mark.parametrize("extra", ['port = 0\n', 'port = 70000\n', 'port = "80"\n', 'host = ""\n', 'host = "a b"\n', 'host = 5\n'])
def test_a_bad_host_or_port_is_config_invalid(tmp_path, extra):
    invalid(tmp_path, GOOD + extra, "api.")


def test_an_unknown_key_is_config_invalid_naming_it(tmp_path):
    invalid(tmp_path, GOOD + "token = 'x'\n", "api.token")


def test_an_environment_variable_overrides_the_file(tmp_path):
    env = {"CREDIT_INTEL_API_MAX_CONCURRENT_RUNS": "2", "CREDIT_INTEL_API_RUN_TIMEOUT_SECONDS": "30", "CREDIT_INTEL_API_OUTPUT_DIR": "/elsewhere",
           "CREDIT_INTEL_API_PORT": "8123", "CREDIT_INTEL_API_HOST": "localhost"}  # fmt: skip
    settings = load(tmp_path, GOOD, env)
    assert (settings.max_concurrent_runs, settings.run_timeout_seconds, str(settings.output_dir), settings.port, settings.host) == (2, 30, "/elsewhere", 8123, "localhost")
    assert settings.max_queued_runs == 4


@pytest.mark.parametrize("name, bad", [("MAX_QUEUED_RUNS", "x"), ("MAX_QUEUED_RUNS", "0"), ("OUTPUT_DIR", "relative"), ("PORT", "99999"), ("MAX_CONCURRENT_RUNS", "1000")])
def test_a_bad_environment_value_is_config_invalid(tmp_path, name, bad):
    invalid(tmp_path, GOOD, "api.", {f"CREDIT_INTEL_API_{name}": bad})


def test_the_shipped_settings_hold_the_owners_limits_but_not_the_folders_so_the_service_does_not_start_until_they_are_set(tmp_path):
    with pytest.raises(IngestionError) as error:
        load_api_settings(DEFAULT_SETTINGS_PATH, {})
    assert error.value.code is ErrorCode.CONFIG_INVALID and "api.output_dir" in str(error.value)
    settings = load_api_settings(DEFAULT_SETTINGS_PATH, {"CREDIT_INTEL_API_OUTPUT_DIR": "/a", "CREDIT_INTEL_API_CACHE_DIR": "/b"})
    assert (settings.max_concurrent_runs, settings.max_queued_runs, settings.run_timeout_seconds) == (1, 4, 1200)
