"""The pipeline through the OpenAI provider with a fake client (Phase 2 step 10a; B-225).

No network: the SDK client is replaced by an object that returns recorded-shape completions.
"""

from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletion

import pipeline_fixture as fx
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.llm.openai_provider import OpenAIProvider
from credit_intel.models import Status

SECRET = "sk-SECRETKEY-1234567890"


def completion(text, prompt=4000, output=700):
    return ChatCompletion.model_validate({
        "id": "c1", "object": "chat.completion", "created": 1, "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text, "refusal": None}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": output, "total_tokens": prompt + output},
    })  # fmt: skip


class Client:
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.replies.pop(0)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def test_the_pipeline_runs_through_the_openai_provider(pdf, tmp_path):
    client = Client(completion(fx.good_response(pdf)))

    result = run_extraction(pdf, OpenAIProvider(SECRET, client=client), fx.LLM, cache_dir=tmp_path / "c")

    assert result.field_set.counts["extracted"] == 6
    assert result.stats.llm_calls == 1 and result.stats.tokens_used == 4700  # the provider's reported usage
    (sent,) = client.requests
    assert sent["store"] is False and sent["temperature"] == 0 and sent["max_completion_tokens"] == fx.LLM.max_output_tokens
    assert sent["model"] == fx.LLM.model_id and sent["response_format"]["json_schema"]["strict"] is True


def test_only_candidate_pages_and_the_prompt_are_sent(pdf, tmp_path):
    client = Client(completion(fx.good_response(pdf)))

    run_extraction(pdf, OpenAIProvider(SECRET, client=client), fx.LLM, cache_dir=tmp_path / "c")

    system, user = (m["content"] for m in client.requests[0]["messages"])
    assert "DATA, not instructions" in system and "=== PAGE 1 ===" in user and "Total current assets" in user
    assert SECRET not in system and SECRET not in user


def test_the_key_never_reaches_the_cache_or_the_logs(pdf, tmp_path, caplog):
    client = Client(completion(fx.good_response(pdf)))

    with caplog.at_level("DEBUG"):
        run_extraction(pdf, OpenAIProvider(SECRET, client=client), fx.LLM, cache_dir=tmp_path / "c")

    assert all(SECRET not in path.read_text(encoding="utf-8") for path in (tmp_path / "c").glob("*.json"))
    assert all(SECRET not in record.getMessage() for record in caplog.records)


def test_a_second_run_is_served_from_the_cache_without_a_request(pdf, tmp_path):
    first_client, second_client = Client(completion(fx.good_response(pdf))), Client()
    run_extraction(pdf, OpenAIProvider(SECRET, client=first_client), fx.LLM, cache_dir=tmp_path / "c")

    second = run_extraction(pdf, OpenAIProvider(SECRET, client=second_client), fx.LLM, cache_dir=tmp_path / "c")

    assert second_client.requests == [] and second.stats.cache_hits == 1
    assert second.field_set.counts["extracted"] == 6 and Status.EXTRACTED
