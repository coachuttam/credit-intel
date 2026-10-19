"""Safety and settings for live use (Phase 2 step 10c; B-227).

PRD D-02, SEC-02, SEC-03, SEC-10, NFR-09, O.1. Nothing here touches the network.
"""

import os
import socket
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from credit_intel.config import (
    ENV_LIVE,
    ENV_MAX_OUTPUT_TOKENS,
    ENV_OPENAI_API_KEY,
    ENV_PRICE_INPUT,
    ENV_PRICE_OUTPUT,
    ENV_LLM_MODEL_ID,
    ENV_LLM_PROVIDER,
    ENV_TOKEN_CEILING,
    LLMSettings,
    PricingSettings,
    load_pricing,
)
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.cost import estimate_cost
from credit_intel.llm.factory import build_provider
from credit_intel.llm.openai_provider import OpenAIProvider
from credit_intel.llm.retry import RetryingProvider

ROOT = Path(__file__).resolve().parents[2]
SECRET = "sk-SECRETKEY-1234567890"
OPENAI = LLMSettings(provider="openai", model_id="gpt-4o-mini", token_ceiling=1000, max_output_tokens=100)


# --- .env.example (SEC-03) -----------------------------------------------------------------------


def example_lines():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def test_env_example_has_only_placeholder_names_with_empty_values():
    lines = example_lines()

    assert lines and all(line.endswith("=") and line[:-1].replace("_", "").isalnum() for line in lines)


def test_env_example_names_every_variable_the_code_reads():
    names = {line[:-1] for line in example_lines()}

    assert names == {
        ENV_OPENAI_API_KEY, ENV_TOKEN_CEILING, ENV_LLM_PROVIDER, ENV_LLM_MODEL_ID, ENV_MAX_OUTPUT_TOKENS,
        ENV_PRICE_INPUT, ENV_PRICE_OUTPUT, ENV_LIVE,
    }  # fmt: skip


def test_env_example_contains_no_key_like_text():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "sk-" not in text and "Bearer" not in text


def test_a_real_env_file_is_ignored_by_git_and_the_example_is_not():
    ignored = subprocess.run(["git", "check-ignore", ".env", ".env.local"], cwd=ROOT, capture_output=True, text=True)
    example = subprocess.run(["git", "check-ignore", ".env.example"], cwd=ROOT, capture_output=True, text=True)

    assert set(ignored.stdout.split()) == {".env", ".env.local"} and example.returncode == 1


def test_there_is_no_env_file_in_the_repository():
    assert not (ROOT / ".env").exists()


# --- the provider factory (SEC-02) -------------------------------------------------------------------------


@pytest.mark.parametrize("env", [{}, {ENV_OPENAI_API_KEY: ""}, {ENV_OPENAI_API_KEY: "   "}])
def test_a_missing_or_blank_key_is_an_authentication_failure_before_any_call(env):
    with pytest.raises(IngestionError) as excinfo:
        build_provider(OPENAI, env)

    assert excinfo.value.code is ErrorCode.LLM_AUTH


def test_with_a_key_the_provider_is_the_real_one_inside_the_retry_layer():
    provider = build_provider(OPENAI, {ENV_OPENAI_API_KEY: SECRET}, sleep=lambda _: None)

    assert isinstance(provider, RetryingProvider) and isinstance(provider._provider, OpenAIProvider)
    assert provider.retries == 0


def test_the_key_is_not_visible_on_the_built_provider():
    provider = build_provider(OPENAI, {ENV_OPENAI_API_KEY: SECRET})

    assert SECRET not in repr(provider) and SECRET not in repr(provider._provider)
    assert SECRET not in str(provider) and SECRET not in str(provider._provider)


def test_the_key_is_read_from_the_process_environment_by_default(monkeypatch):
    monkeypatch.delenv(ENV_OPENAI_API_KEY, raising=False)
    with pytest.raises(IngestionError):
        build_provider(OPENAI)

    monkeypatch.setenv(ENV_OPENAI_API_KEY, SECRET)

    assert isinstance(build_provider(OPENAI), RetryingProvider)


def test_the_fake_provider_is_never_built_from_settings():
    with pytest.raises(ValueError):
        build_provider(LLMSettings("fake", "m", 1000, 100), {ENV_OPENAI_API_KEY: SECRET})


def test_an_unknown_provider_is_refused():
    with pytest.raises(ValueError):
        build_provider(LLMSettings("other", "m", 1000, 100), {ENV_OPENAI_API_KEY: SECRET})


# --- prices and the cost estimate (D-02, NFR-09) ---------------------------------------------------------------


def settings_file(tmp_path, text):
    path = tmp_path / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_shipped_settings_file_has_no_prices():
    assert load_pricing(ROOT / "config" / "settings.toml", {}) is None


def test_prices_are_read_from_the_pricing_table_exactly(tmp_path):
    path = settings_file(tmp_path, "[pricing]\ninput_per_million = 0.15\noutput_per_million = 0.6\n")

    pricing = load_pricing(path, {})

    assert pricing == PricingSettings(Decimal("0.15"), Decimal("0.6"))


def test_integer_prices_and_zero_are_accepted(tmp_path):
    path = settings_file(tmp_path, "[pricing]\ninput_per_million = 2\noutput_per_million = 0\n")

    assert load_pricing(path, {}) == PricingSettings(Decimal(2), Decimal(0))


def test_the_environment_overrides_the_file_and_can_supply_the_prices_alone(tmp_path):
    path = settings_file(tmp_path, "[pricing]\ninput_per_million = 0.15\noutput_per_million = 0.6\n")
    only_env = settings_file(tmp_path, "[llm]\nprovider = \"openai\"\n")
    env = {ENV_PRICE_INPUT: "1.25", ENV_PRICE_OUTPUT: "10"}

    assert load_pricing(path, env) == PricingSettings(Decimal("1.25"), Decimal(10))
    assert load_pricing(only_env, env) == PricingSettings(Decimal("1.25"), Decimal(10))


@pytest.mark.parametrize(
    ("text", "setting"),
    [
        ("[pricing]\noutput_per_million = 1\n", "pricing.input_per_million"),
        ("[pricing]\ninput_per_million = 1\n", "pricing.output_per_million"),
        ("[pricing]\ninput_per_million = -1\noutput_per_million = 1\n", "pricing.input_per_million"),
        ("[pricing]\ninput_per_million = true\noutput_per_million = 1\n", "pricing.input_per_million"),
        ("[pricing]\ninput_per_million = \"1\"\noutput_per_million = 1\n", "pricing.input_per_million"),
        ("[pricing]\ninput_per_million = nan\noutput_per_million = 1\n", "pricing.input_per_million"),
        ("[pricing]\ninput_per_million = inf\noutput_per_million = 1\n", "pricing.input_per_million"),
        ("[pricing]\ninput_per_million = 1\noutput_per_million = 1\ncurrency = \"USD\"\n", "pricing.currency"),
        ("pricing = 5\n", "pricing"),
    ],
)
def test_invalid_prices_fail_with_e_config_invalid_naming_the_setting(tmp_path, text, setting):
    with pytest.raises(IngestionError) as excinfo:
        load_pricing(settings_file(tmp_path, text), {})

    assert excinfo.value.code is ErrorCode.CONFIG_INVALID and excinfo.value.detail == setting


@pytest.mark.parametrize("value", ["", "-1", "1e3", " 1", "1,5", "abc", "1."])
def test_invalid_prices_in_the_environment_fail_without_echoing_the_value(tmp_path, value):
    path = settings_file(tmp_path, "[pricing]\ninput_per_million = 1\noutput_per_million = 1\n")

    with pytest.raises(IngestionError) as excinfo:
        load_pricing(path, {ENV_PRICE_INPUT: value})

    assert excinfo.value.detail == "pricing.input_per_million"
    assert not value.strip() or value.strip() not in str(excinfo.value)


def test_a_missing_settings_file_is_a_config_error(tmp_path):
    with pytest.raises(IngestionError) as excinfo:
        load_pricing(tmp_path / "absent.toml", {})

    assert excinfo.value.detail == "settings file"


def test_pricing_does_not_disturb_the_llm_settings_loader(tmp_path):
    from credit_intel.config import load_llm_settings

    path = settings_file(
        tmp_path,
        '[llm]\nprovider = "openai"\nmodel_id = "m"\ntoken_ceiling = 5\nmax_output_tokens = 9\n'
        "[pricing]\ninput_per_million = 1\noutput_per_million = 2\n",
    )

    assert load_llm_settings(path, {}).token_ceiling == 5 and load_pricing(path, {}) is not None


PRICES = PricingSettings(Decimal("0.15"), Decimal("0.6"))


def test_the_cost_is_exact_per_million_tokens():
    assert estimate_cost(1_000_000, 0, PRICES) == Decimal("0.15")
    assert estimate_cost(0, 1_000_000, PRICES) == Decimal("0.6")
    assert estimate_cost(2_000_000, 500_000, PRICES) == Decimal("0.60")


def test_the_cost_is_never_rounded_or_a_float():
    cost = estimate_cost(1234, 567, PRICES)

    assert isinstance(cost, Decimal) and cost == Decimal("0.00052530")  # 1234*0.15 + 567*0.6 = 525.3 per million


def test_no_tokens_cost_nothing_and_negative_counts_are_refused():
    assert estimate_cost(0, 0, PRICES) == 0
    with pytest.raises(ValueError):
        estimate_cost(-1, 0, PRICES)


def test_free_prices_cost_nothing():
    assert estimate_cost(10**9, 10**9, PricingSettings(Decimal(0), Decimal(0))) == 0


# --- no network by default; live tests are opt-in (O.1) -------------------------------------------------------------


def test_the_default_suite_cannot_open_a_network_connection():
    with pytest.raises(RuntimeError, match="network access is blocked"):
        socket.create_connection(("127.0.0.1", 9), timeout=1)

    with pytest.raises(RuntimeError, match="network access is blocked"):
        socket.socket().connect(("127.0.0.1", 9))


def test_live_enabled_needs_both_the_flag_and_a_key():
    from conftest import live_enabled

    assert not live_enabled({})
    assert not live_enabled({"CREDIT_INTEL_LIVE": "1"})
    assert not live_enabled({"CREDIT_INTEL_LIVE": "1", "OPENAI_API_KEY": "  "})
    assert not live_enabled({"OPENAI_API_KEY": "sk-x"})
    assert not live_enabled({"CREDIT_INTEL_LIVE": "true", "OPENAI_API_KEY": "sk-x"})
    assert live_enabled({"CREDIT_INTEL_LIVE": "1", "OPENAI_API_KEY": "sk-x"})


def nested_pytest(env_changes):
    env = {k: v for k, v in os.environ.items() if k not in ("CREDIT_INTEL_LIVE", "OPENAI_API_KEY")}
    env.update(env_changes)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/live", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip


def test_the_live_tests_are_skipped_by_default():
    done = nested_pytest({})

    assert done.returncode == 0 and "1 skipped" in done.stdout and "passed" not in done.stdout


def test_the_flag_alone_or_a_key_alone_still_skips_them():
    flag = nested_pytest({"CREDIT_INTEL_LIVE": "1"})
    key = nested_pytest({"OPENAI_API_KEY": "sk-not-a-real-key"})

    assert "1 skipped" in flag.stdout and "1 skipped" in key.stdout


def test_the_live_marker_is_registered():
    done = subprocess.run([sys.executable, "-m", "pytest", "--markers", "-p", "no:cacheprovider"], cwd=ROOT,
                          capture_output=True, text=True, timeout=120, check=False)  # fmt: skip

    assert "@pytest.mark.live" in done.stdout


def test_no_other_test_module_is_marked_live():
    marked = [p.name for p in (ROOT / "tests").rglob("test_*.py") if "mark.live" in p.read_text(encoding="utf-8")
              and p.name not in ("test_live_openai.py", "test_live_enablement.py")]  # fmt: skip

    assert marked == []
