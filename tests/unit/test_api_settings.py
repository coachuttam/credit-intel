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


# --- the proxy settings (PRD SEC-15, SEC-16, OD-36; Phase 7 step 5) ----------------------------------------------------------------------------------


def test_the_proxy_settings_default_to_nothing_trusted_and_nothing_stated(tmp_path):
    settings = load(tmp_path, GOOD)
    assert (settings.behind_tls, settings.loopback_only_publication, settings.public_hosts, settings.trusted_proxies) == (False, False, (), ())


def test_the_two_statements_are_separate_settings_and_one_does_not_set_the_other(tmp_path):
    assert (lambda s: (s.behind_tls, s.loopback_only_publication))(load(tmp_path, GOOD + "behind_tls = true\n")) == (True, False)
    assert (lambda s: (s.behind_tls, s.loopback_only_publication))(load(tmp_path, GOOD + "loopback_only_publication = true\n")) == (False, True)
    both = load(tmp_path, GOOD, {"CREDIT_INTEL_API_BEHIND_TLS": "true", "CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION": "true"})
    assert both.behind_tls is True and both.loopback_only_publication is True


@pytest.mark.parametrize("line", ["loopback_only_publication = 1", 'loopback_only_publication = "true"', "loopback_only_publication = []"])
def test_loopback_only_publication_in_the_file_must_be_a_true_boolean(tmp_path, line):
    invalid(tmp_path, GOOD + line + "\n", "api.loopback_only_publication")


@pytest.mark.parametrize("text", ["True", "1", "yes", " true", "", "tru"])
def test_loopback_only_publication_in_the_environment_is_exactly_true_or_false(tmp_path, text):
    invalid(tmp_path, GOOD, "api.loopback_only_publication", {"CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION": text})


def test_they_can_be_set_in_the_file(tmp_path):
    settings = load(tmp_path, GOOD + 'behind_tls = true\npublic_hosts = ["Memos.Example.com", "[::1]:8443", "example.org:8080", "MEMOS.example.com"]\ntrusted_proxies = ["172.30.60.0/24", "10.1.2.3", "2001:db8::/32", "172.30.60.5/24"]\n')
    assert settings.behind_tls is True
    assert settings.public_hosts == ("memos.example.com", "[::1]:8443", "example.org:8080")  # lower-cased, duplicates dropped, order kept
    assert settings.trusted_proxies == ("172.30.60.0/24", "10.1.2.3/32", "2001:db8::/32")  # normalised; the host bits of 172.30.60.5/24 go and it joins the first


def test_they_can_be_set_by_the_environment_with_lists_as_comma_separated_text(tmp_path):
    env = {"CREDIT_INTEL_API_BEHIND_TLS": "true", "CREDIT_INTEL_API_PUBLIC_HOSTS": " a.example , b.example:8443 ", "CREDIT_INTEL_API_TRUSTED_PROXIES": "10.0.0.0/8,192.168.0.1"}
    settings = load(tmp_path, GOOD, env)
    assert settings.behind_tls is True and settings.public_hosts == ("a.example", "b.example:8443") and settings.trusted_proxies == ("10.0.0.0/8", "192.168.0.1/32")


def test_the_environment_wins_over_the_file_and_empty_text_is_an_empty_list(tmp_path):
    text = GOOD + 'behind_tls = true\npublic_hosts = ["a.example"]\ntrusted_proxies = ["10.0.0.0/8"]\n'
    settings = load(tmp_path, text, {"CREDIT_INTEL_API_BEHIND_TLS": "false", "CREDIT_INTEL_API_PUBLIC_HOSTS": "", "CREDIT_INTEL_API_TRUSTED_PROXIES": "  "})
    assert (settings.behind_tls, settings.public_hosts, settings.trusted_proxies) == (False, (), ())


@pytest.mark.parametrize("line", ["behind_tls = 1", 'behind_tls = "true"', "behind_tls = []"])
def test_behind_tls_in_the_file_must_be_a_true_boolean(tmp_path, line):
    invalid(tmp_path, GOOD + line + "\n", "api.behind_tls")


@pytest.mark.parametrize("text", ["True", "TRUE", "1", "yes", "on", " true", "true ", "", "tru"])
def test_behind_tls_in_the_environment_is_exactly_true_or_false(tmp_path, text):
    invalid(tmp_path, GOOD, "api.behind_tls", {"CREDIT_INTEL_API_BEHIND_TLS": text})


@pytest.mark.parametrize("entry", ["", " a.example", "a.example ", "-a.example", "a.example-", "a b", "a/b", "a.example/path", "http://a.example", "a.example:", "a.example:port", "a.example:70000",
                                   "[::1", "::1", "[zz]", "a_b.example", "ü.example", "a.example:1:2", "*", "a.example,b.example"])  # fmt: skip
def test_a_malformed_public_host_is_config_invalid_naming_the_setting_and_not_the_value(tmp_path, entry):
    text = GOOD + "public_hosts = [" + json_string(entry) + "]\n"
    error = invalid(tmp_path, text, "api.public_hosts")
    assert entry.strip() == "" or entry not in str(error)


def json_string(value):
    import json

    return json.dumps(value)


@pytest.mark.parametrize("entry", ["", "10.0.0.0/33", "300.1.1.1", "a.example", "10.0.0.0/8/8", "10.0.0.0/-1", "::g", "0.0.0.0/0", "::/0", "1.2.3.4/0", " 10.0.0.1"])
def test_a_malformed_trusted_proxy_or_one_that_is_every_address_is_config_invalid(tmp_path, entry):
    invalid(tmp_path, GOOD + "trusted_proxies = [" + json_string(entry) + "]\n", "api.trusted_proxies")


@pytest.mark.parametrize("name, value", [("public_hosts", '"a.example"'), ("public_hosts", "[1]"), ("public_hosts", "{}"), ("trusted_proxies", '"10.0.0.0/8"'), ("trusted_proxies", "[[]]"), ("trusted_proxies", "5")])
def test_a_list_setting_in_the_file_must_be_a_list_of_strings(tmp_path, name, value):
    invalid(tmp_path, GOOD + f"{name} = {value}\n", f"api.{name}")


def test_a_list_of_more_than_thirty_two_is_refused_and_thirty_two_is_not(tmp_path):
    many = lambda n: ", ".join(json_string(f"h{i}.example") for i in range(n))  # noqa: E731
    assert len(load(tmp_path, GOOD + f"public_hosts = [{many(32)}]\n").public_hosts) == 32
    invalid(tmp_path, GOOD + f"public_hosts = [{many(33)}]\n", "api.public_hosts")
    nets = lambda n: ", ".join(json_string(f"10.{i}.0.0/16") for i in range(n))  # noqa: E731
    assert len(load(tmp_path, GOOD + f"trusted_proxies = [{nets(32)}]\n").trusted_proxies) == 32
    invalid(tmp_path, GOOD + f"trusted_proxies = [{nets(33)}]\n", "api.trusted_proxies")


def test_the_proxy_settings_are_optional_names_so_an_unknown_one_is_still_refused(tmp_path):
    invalid(tmp_path, GOOD + "trusted_proxy = []\n", "api.trusted_proxy")
