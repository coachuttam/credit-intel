"""Provider interface, fake provider, response cache, budget and gateway (B-204).

PRD FR-003.5, FR-003.6, NFR-09, OD-8. No network access; the fake provider only.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.budget import TokenBudget, estimate_tokens
from credit_intel.llm.cache import CacheKeyInputs, ResponseCache
from credit_intel.llm.gateway import LLMGateway
from credit_intel.llm.provider import (
    STRUCTURED_OUTPUT_MODE,
    TEMPERATURE,
    FakeProvider,
    FakeProviderError,
    FakeReply,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    canonical_json,
)

FIXED_NOW = datetime(2026, 10, 19, 12, 30, 45, tzinfo=UTC)


def request(user="page text", system="sys", max_output=100) -> LLMRequest:
    return LLMRequest(system=system, user=user, model_id="m", max_output_tokens=max_output)


def inputs(**changes) -> CacheKeyInputs:
    base = dict(
        document_sha256="a" * 64,
        candidate_pages=(3, 4),
        provider="fake",
        model_id="m",
        prompt_version="p1",
        schema_version="s1",
        temperature=TEMPERATURE,
        max_output_tokens=100,
        structured_output_mode=STRUCTURED_OUTPUT_MODE,
    )
    base.update(changes)
    return CacheKeyInputs(**base)


# --- canonical JSON and keys ---------------------------------------------------


def test_canonical_json_sorts_keys_without_whitespace_and_keeps_unicode():
    assert canonical_json({"b": 1, "a": ["é", 2]}) == '{"a":["é",2],"b":1}'


def test_key_is_a_sha256_hex_and_stable():
    assert inputs().key() == inputs().key()
    assert len(inputs().key()) == 64 and set(inputs().key()) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    "change",
    [
        {"document_sha256": "b" * 64},
        {"candidate_pages": (4, 3)},
        {"candidate_pages": (3,)},
        {"provider": "openai"},
        {"model_id": "other"},
        {"prompt_version": "p2"},
        {"schema_version": "s2"},
        {"temperature": 1},
        {"max_output_tokens": 101},
        {"structured_output_mode": "json_object"},
        {"corrective_feedback_sha256": "c" * 64},
    ],
    ids=lambda c: next(iter(c)) + str(next(iter(c.values()))),
)
def test_every_input_changes_the_key(change):
    assert inputs(**change).key() != inputs().key()


# --- the cache -------------------------------------------------------------------


def make_cache(tmp_path) -> ResponseCache:
    return ResponseCache(tmp_path / "llm", now=lambda: FIXED_NOW)


RESPONSE = LLMResponse("{}", LLMUsage(10, 5))


def test_miss_then_hit_with_counts(tmp_path):
    cache = make_cache(tmp_path)

    assert cache.get(inputs()) is None
    cache.put(inputs(), RESPONSE)
    assert cache.get(inputs()) == RESPONSE
    assert (cache.hits, cache.misses) == (1, 1)


def test_entry_holds_inputs_text_usage_and_utc_time_and_nothing_else(tmp_path):
    cache = make_cache(tmp_path)
    cache.put(inputs(), RESPONSE)

    entry = json.loads((tmp_path / "llm" / f"{inputs().key()}.json").read_text(encoding="utf-8"))

    assert entry == {
        "inputs": inputs().to_object(),
        "response_text": "{}",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "created_at": "2026-10-19T12:30:45Z",
    }


def test_put_leaves_no_temporary_files(tmp_path):
    cache = make_cache(tmp_path)
    cache.put(inputs(), RESPONSE)
    cache.put(inputs(), LLMResponse("{}", LLMUsage(1, 1)))

    assert [p.name for p in (tmp_path / "llm").iterdir()] == [f"{inputs().key()}.json"]


def test_unreadable_entry_is_a_miss_and_is_replaced(tmp_path):
    cache = make_cache(tmp_path)
    path = tmp_path / "llm" / f"{inputs().key()}.json"
    path.parent.mkdir()
    path.write_text("not json", encoding="utf-8")

    assert cache.get(inputs()) is None
    cache.put(inputs(), RESPONSE)
    assert cache.get(inputs()) == RESPONSE


@pytest.mark.parametrize(
    "entry",
    [
        [],
        {},
        {"inputs": "x"},
        {"response_text": 1, "usage": {"input_tokens": 1, "output_tokens": 1}},
        {"response_text": "t", "usage": {"input_tokens": -1, "output_tokens": 1}},
        {"response_text": "t", "usage": {"input_tokens": True, "output_tokens": 1}},
        {"response_text": "t", "usage": {"input_tokens": 1}},
        {"response_text": "t", "usage": 3},
    ],
    ids=["list", "empty", "no text", "bad text", "negative", "bool", "missing output", "usage int"],
)
def test_malformed_entries_are_misses(tmp_path, entry):
    cache = make_cache(tmp_path)
    if isinstance(entry, dict) and "inputs" not in entry:
        entry = {"inputs": inputs().to_object(), **entry}
    path = tmp_path / "llm" / f"{inputs().key()}.json"
    path.parent.mkdir()
    path.write_text(json.dumps(entry), encoding="utf-8")

    assert cache.get(inputs()) is None
    assert cache.misses == 1


def test_stored_inputs_that_differ_are_a_miss(tmp_path):
    cache = make_cache(tmp_path)
    cache.put(inputs(), RESPONSE)
    path = tmp_path / "llm" / f"{inputs().key()}.json"
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["inputs"]["model_id"] = "tampered"
    path.write_text(json.dumps(entry), encoding="utf-8")

    assert cache.get(inputs()) is None


def test_non_utf8_entry_is_a_miss(tmp_path):
    cache = make_cache(tmp_path)
    path = tmp_path / "llm" / f"{inputs().key()}.json"
    path.parent.mkdir()
    path.write_bytes(b"\xff\xfe")

    assert cache.get(inputs()) is None


def test_default_cache_directory_is_git_ignored():
    gitignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8")

    assert ".cache/" in gitignore.splitlines()


# --- the budget ------------------------------------------------------------------


def test_estimate_is_conservative_and_rounds_up():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("abcd") == 2
    assert estimate_tokens("abcde") == 3
    assert estimate_tokens("é") == 1  # two UTF-8 bytes
    assert estimate_tokens("日本") == 3  # six UTF-8 bytes


def test_call_exactly_filling_the_ceiling_is_allowed():
    budget = TokenBudget(100)
    budget.record(40)

    budget.check(estimated_input=30, max_output=30)


def test_call_one_over_the_ceiling_is_refused_with_the_budget_code():
    budget = TokenBudget(100)
    budget.record(40)

    with pytest.raises(IngestionError) as excinfo:
        budget.check(estimated_input=31, max_output=30)

    assert excinfo.value.code is ErrorCode.LLM_BUDGET_EXCEEDED


@pytest.mark.parametrize("ceiling", [0, -1, True, 1.5, "5"])
def test_budget_rejects_a_non_positive_or_non_integer_ceiling(ceiling):
    with pytest.raises(ValueError):
        TokenBudget(ceiling)


# --- the fake provider -----------------------------------------------------------


def test_script_replies_in_order_and_records_calls():
    provider = FakeProvider(script=["one", FakeReply("two", 7, 8)])

    first = provider.complete(request("a"))
    second = provider.complete(request("b"))

    assert (first.text, second.text) == ("one", "two")
    assert second.usage == LLMUsage(7, 8)
    assert [c.user for c in provider.calls] == ["a", "b"]


def test_default_usage_is_the_deterministic_estimate():
    reply = FakeProvider(script=["abcd"]).complete(request("xy", system="s"))

    assert reply.usage == LLMUsage(estimate_tokens("sxy"), estimate_tokens("abcd"))


def test_exhausted_script_raises_rather_than_inventing_a_reply():
    with pytest.raises(FakeProviderError):
        FakeProvider().complete(request())


def test_recorded_reply_is_found_by_request_fingerprint_before_the_script():
    recorded = {request("a").fingerprint(): "recorded"}
    provider = FakeProvider(script=["scripted"], recorded=recorded)

    assert provider.complete(request("a")).text == "recorded"
    assert provider.complete(request("other")).text == "scripted"


def test_fingerprint_depends_on_every_request_field():
    base = request()
    variants = [
        LLMRequest("x", "page text", "m", 100),
        LLMRequest("sys", "x", "m", 100),
        LLMRequest("sys", "page text", "n", 100),
        LLMRequest("sys", "page text", "m", 101),
        LLMRequest("sys", "page text", "m", 100, temperature=1),
        LLMRequest("sys", "page text", "m", 100, structured_output_mode="json_object"),
    ]

    assert len({base.fingerprint(), *(v.fingerprint() for v in variants)}) == 7


def test_from_recording_loads_a_json_file(tmp_path):
    path = tmp_path / "rec.json"
    path.write_text(json.dumps({request("a").fingerprint(): "from file"}), encoding="utf-8")

    assert FakeProvider.from_recording(path).complete(request("a")).text == "from file"


# --- the gateway -----------------------------------------------------------------


def gateway(tmp_path, provider, ceiling=10_000):
    cache = make_cache(tmp_path)
    budget = TokenBudget(ceiling)
    return LLMGateway(provider, cache, budget), cache, budget


def test_miss_calls_the_provider_records_usage_and_caches(tmp_path):
    provider = FakeProvider(script=[FakeReply("answer", 20, 5)])
    gw, cache, budget = gateway(tmp_path, provider)

    response = gw.complete(request(), inputs())

    assert response.text == "answer"
    assert budget.used == 25
    assert (cache.hits, cache.misses) == (0, 1)
    assert len(provider.calls) == 1


def test_hit_makes_no_call_and_counts_zero_tokens(tmp_path):
    provider = FakeProvider(script=[FakeReply("answer", 20, 5)])
    gw, cache, budget = gateway(tmp_path, provider)
    gw.complete(request(), inputs())

    again = gw.complete(request(), inputs())

    assert again.text == "answer"
    assert budget.used == 25
    assert len(provider.calls) == 1
    assert (cache.hits, cache.misses) == (1, 1)


def test_hit_is_served_even_when_the_budget_is_exhausted(tmp_path):
    provider = FakeProvider(script=[FakeReply("answer", 20, 5)])
    gw, _, budget = gateway(tmp_path, provider)
    gw.complete(request(), inputs())
    budget.record(10_000)

    assert gw.complete(request(), inputs()).text == "answer"


def test_budget_refusal_makes_no_call_and_writes_no_entry(tmp_path):
    provider = FakeProvider(script=["never used"])
    gw, cache, budget = gateway(tmp_path, provider, ceiling=50)

    with pytest.raises(IngestionError) as excinfo:
        gw.complete(request(user="x" * 100, max_output=10), inputs())

    assert excinfo.value.code is ErrorCode.LLM_BUDGET_EXCEEDED
    assert provider.calls == []
    assert budget.used == 0
    assert not (tmp_path / "llm").exists()


def test_reservation_counts_against_the_ceiling(tmp_path):
    # Estimate for "syspage text" is 6 tokens; 6 + 95 > 100, so the call is refused.
    gw, _, _ = gateway(tmp_path, FakeProvider(script=["x"]), ceiling=100)

    with pytest.raises(IngestionError):
        gw.complete(request(max_output=95), inputs(max_output_tokens=95))


def test_provider_usage_replaces_the_estimate_for_later_checks(tmp_path):
    provider = FakeProvider(script=[FakeReply("a", 1, 1), FakeReply("b", 1, 1)])
    gw, _, budget = gateway(tmp_path, provider, ceiling=110)

    gw.complete(request("one"), inputs(candidate_pages=(1,)))
    gw.complete(request("two"), inputs(candidate_pages=(2,)))

    assert budget.used == 4


def test_a_corrective_retry_is_a_separate_call_with_its_own_key(tmp_path):
    provider = FakeProvider(script=["bad", "good"])
    gw, _, budget = gateway(tmp_path, provider)

    first = gw.complete(request(), inputs())
    retry = gw.complete(request("page text + error"), inputs(corrective_feedback_sha256="d" * 64))

    assert (first.text, retry.text) == ("bad", "good")
    assert budget.used > 0 and len(provider.calls) == 2
