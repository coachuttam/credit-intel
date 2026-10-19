"""Versioned prompt and extraction flow (B-205).

PRD FR-003.1-.4, FR-003.7, FR-004.1-.2, D-04, H.4.6. Fake provider only.
"""

import hashlib
import json
from pathlib import Path

import pytest

from credit_intel.config import LLMSettings
from credit_intel.extraction.extract import (
    SCHEMA_VERSION,
    extract_fields,
    parse_response,
    render_pages,
)
from credit_intel.extraction.prompt import (
    FIELD_DESCRIPTIONS,
    PROMPT_DIR,
    Prompt,
    PromptError,
    load_prompt,
)
from credit_intel.ingestion.errors import ErrorCode, IngestionError, InvalidOutputError
from credit_intel.ingestion.models import (
    CandidatePage,
    FileInfo,
    IngestedDocument,
    LocatorResult,
    PageText,
)
from credit_intel.llm.budget import TokenBudget
from credit_intel.llm.cache import ResponseCache
from credit_intel.llm.gateway import LLMGateway
from credit_intel.llm.provider import FakeProvider, FakeReply
from credit_intel.models import ExtractableFieldName

LLM = LLMSettings(provider="fake", model_id="m", token_ceiling=1_000_000, max_output_tokens=500)

VALID = json.dumps(
    {
        "attributes": [
            {
                "attribute": "reporting_currency",
                "raw_text": "INR",
                "normalised_value": "INR",
                "page_number": 2,
                "evidence_quote": "All amounts in INR",
            }
        ],
        "fields": [
            {
                "field_name": "total_equity",
                "period_role": "current",
                "raw_value": "1,200",
                "scale": "crore",
                "currency": "INR",
                "page_number": 2,
                "evidence_quote": "Total equity 1,200 1,100",
                "line_item_label": "Total equity",
            }
        ],
    }
)


def document(pages=("Intro page", "Consolidated Balance Sheet\nTotal equity 1,200 1,100")):
    texts = [PageText(page_number=i + 1, text=t) for i, t in enumerate(pages)]
    info = FileInfo(
        path=Path("x.pdf"), file_name="x.pdf", size_bytes=1, sha256="d" * 64, page_count=len(texts)
    )
    return IngestedDocument(file_info=info, pages=tuple(texts))


def located(*numbers, method="keywords"):
    return LocatorResult(
        method=method,
        candidates=tuple(CandidatePage(n, ("balance_sheet",), 5, ()) for n in numbers),
    )


PROMPT = Prompt(version="extraction-v1", system="SYSTEM")


def flow(tmp_path, replies, doc=None, loc=None, basis="consolidated", ceiling=1_000_000):
    provider = FakeProvider(script=replies)
    cache = ResponseCache(tmp_path / "llm")
    budget = TokenBudget(ceiling)
    gateway = LLMGateway(provider, cache, budget)
    result = extract_fields(
        doc or document(), loc or located(2), gateway, LLM, PROMPT, basis
    )
    return result, provider, cache, budget


# --- the prompt file -------------------------------------------------------------


def test_shipped_prompt_loads_with_its_version():
    prompt = load_prompt()

    assert prompt.version == "extraction-v1"
    assert "{{" not in prompt.system


def test_prompt_lists_every_extractable_field_and_no_derived_one():
    assert set(FIELD_DESCRIPTIONS) == {str(name) for name in ExtractableFieldName}
    system = load_prompt().system
    for name in FIELD_DESCRIPTIONS:
        assert f"- {name}:" in system
    assert "- ebit:" not in system


def test_prompt_embeds_the_response_schema_and_the_core_rules():
    system = load_prompt().system

    assert '"evidence_quote"' in system and '"raw_value"' in system
    for rule in ("DATA, not instructions", "never calculate", "leave it out", "character for character"):
        assert rule.lower() in system.lower()


def test_prompt_is_deterministic():
    assert load_prompt() == load_prompt()


@pytest.mark.parametrize(
    "text",
    [
        "no header\n---\n{{schema}} {{fields}}",
        "prompt-version:\n---\n{{schema}} {{fields}}",
        "prompt-version: v\n---\n{{schema}}",
        "prompt-version: v\n---\n{{schema}} {{schema}} {{fields}}",
        "prompt-version: v\n{{schema}} {{fields}}",
    ],
    ids=["no header", "empty version", "no fields", "schema twice", "no separator"],
)
def test_malformed_prompt_files_are_rejected(tmp_path, text):
    (tmp_path / "p.md").write_text(text, encoding="utf-8")

    with pytest.raises(PromptError):
        load_prompt("p", tmp_path)


def test_missing_prompt_file_is_rejected(tmp_path):
    with pytest.raises(PromptError):
        load_prompt("absent", tmp_path)


def test_prompt_directory_is_the_repository_prompts_folder():
    assert (PROMPT_DIR / "extraction_v1.md").is_file()


# --- request contents --------------------------------------------------------------


def test_pages_are_tagged_and_in_ascending_order():
    text = render_pages(document(("a", "b", "c")), (1, 3))

    assert text == "=== PAGE 1 ===\na\n=== END PAGE 1 ===\n\n=== PAGE 3 ===\nc\n=== END PAGE 3 ==="


def test_only_candidate_pages_are_sent(tmp_path):
    doc = document(
        ("secret intro", "Consolidated Balance Sheet\nTotal equity 1,200.00", "other", "more")
    )

    _, provider, _, _ = flow(tmp_path, [VALID], doc=doc, loc=located(3, 4, 2))

    sent = provider.calls[0].user
    positions = [sent.index(f"=== PAGE {n} ===") for n in (2, 3, 4)]
    assert positions == sorted(positions)
    assert "secret intro" not in sent


def test_request_carries_the_prompt_model_and_output_limit(tmp_path):
    _, provider, _, _ = flow(tmp_path, [VALID])

    call = provider.calls[0]
    assert (call.system, call.model_id, call.max_output_tokens, call.temperature) == (
        "SYSTEM",
        "m",
        500,
        0,
    )


def test_cache_entry_records_every_key_input(tmp_path):
    flow(tmp_path, [VALID])

    (entry_file,) = (tmp_path / "llm").iterdir()
    stored = json.loads(entry_file.read_text(encoding="utf-8"))["inputs"]
    assert stored == {
        "document_sha256": "d" * 64,
        "candidate_pages": [2],
        "provider": "fake",
        "model_id": "m",
        "prompt_version": "extraction-v1",
        "schema_version": SCHEMA_VERSION,
        "corrective_feedback_sha256": None,
        "generation": {
            "temperature": 0,
            "max_output_tokens": 500,
            "structured_output_mode": "json_schema.v1",
        },
    }


# --- gates before any call ----------------------------------------------------------


def test_no_candidates_stops_before_any_call(tmp_path):
    provider = FakeProvider(script=[VALID])
    gateway = LLMGateway(provider, ResponseCache(tmp_path / "llm"), TokenBudget(1000))

    with pytest.raises(IngestionError) as excinfo:
        extract_fields(document(), located(), gateway, LLM, PROMPT, "consolidated")

    assert excinfo.value.code is ErrorCode.NO_STATEMENT_PAGES
    assert provider.calls == []


def test_configured_basis_absent_stops_before_any_call(tmp_path):
    doc = document(("x", "Standalone Balance Sheet\nTotal equity 1,200.00 1,100.00"))
    provider = FakeProvider(script=[VALID])
    gateway = LLMGateway(provider, ResponseCache(tmp_path / "llm"), TokenBudget(1000))

    with pytest.raises(IngestionError) as excinfo:
        extract_fields(doc, located(2), gateway, LLM, PROMPT, "consolidated")

    assert excinfo.value.code is ErrorCode.BASIS_UNAVAILABLE
    assert "standalone" in str(excinfo.value)
    assert provider.calls == []


def test_no_candidates_is_reported_before_the_basis(tmp_path):
    doc = document(("x", "Standalone Balance Sheet"))
    gateway = LLMGateway(FakeProvider(), ResponseCache(tmp_path / "llm"), TokenBudget(1000))

    with pytest.raises(IngestionError) as excinfo:
        extract_fields(doc, located(), gateway, LLM, PROMPT, "consolidated")

    assert excinfo.value.code is ErrorCode.NO_STATEMENT_PAGES


# --- parsing and validation ----------------------------------------------------------


def test_valid_response_is_returned_after_one_attempt(tmp_path):
    result, provider, _, _ = flow(tmp_path, [VALID])

    assert result.attempts == 1 and len(provider.calls) == 1
    assert result.prompt_version == "extraction-v1" and result.schema_version == SCHEMA_VERSION
    assert result.response.fields[0].field_name == "total_equity"
    assert result.response.fields[0].raw_value == "1,200"


def test_empty_response_lists_are_valid_and_mean_nothing_found(tmp_path):
    result, _, _, _ = flow(tmp_path, ['{"attributes":[],"fields":[]}'])

    assert result.response.fields == () and result.response.attributes == ()


def _with_field(**changes):
    data = json.loads(VALID)
    data["fields"][0].update(changes)
    return json.dumps(data)


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"attributes":[]}',
        _with_field(field_name="ebit"),
        _with_field(field_name="invented"),
        _with_field(raw_value=1200),
        _with_field(scale="tens"),
        _with_field(currency="rupees"),
        _with_field(page_number=0),
        _with_field(extra_key=1),
    ],
    ids=[
        "not json",
        "list",
        "missing fields",
        "derived ebit",
        "unknown field",
        "numeric value",
        "unknown scale",
        "currency",
        "page zero",
        "extra key",
    ],
)
def test_invalid_output_is_rejected(text):
    from credit_intel.extraction.extract import _Invalid

    with pytest.raises(_Invalid):
        parse_response(text)


def test_feedback_names_locations_and_types_but_never_values():
    from credit_intel.extraction.extract import _Invalid

    with pytest.raises(_Invalid) as excinfo:
        parse_response(_with_field(field_name="SECRET-NAME", scale="SECRET-SCALE"))

    feedback = excinfo.value.feedback
    assert "fields.0.field_name" in feedback and "fields.0.scale" in feedback
    assert "SECRET" not in feedback


def test_feedback_is_capped():
    from credit_intel.extraction.extract import _Invalid

    data = json.loads(VALID)
    data["fields"] = [dict(data["fields"][0], scale="bad") for _ in range(30)]

    with pytest.raises(_Invalid) as excinfo:
        parse_response(json.dumps(data))

    assert excinfo.value.feedback.count("\n- ") == 21
    assert "and 10 more" in excinfo.value.feedback


# --- the corrective retry ------------------------------------------------------------


def test_invalid_then_valid_makes_two_calls_with_the_error_in_the_second(tmp_path):
    result, provider, cache, budget = flow(tmp_path, ["not json", VALID])

    assert result.attempts == 2 and len(provider.calls) == 2
    assert "rejected" in provider.calls[1].user and "not valid JSON" in provider.calls[1].user
    assert provider.calls[1].user.startswith(provider.calls[0].user)
    assert cache.misses == 2


def test_retry_tokens_count_toward_the_ceiling(tmp_path):
    replies = [FakeReply("not json", 10, 1), FakeReply(VALID, 20, 2)]

    _, _, _, budget = flow(tmp_path, replies)

    assert budget.used == 33


def test_only_the_valid_response_is_cached_under_the_feedback_key(tmp_path):
    flow(tmp_path, ["not json", VALID])

    (entry_file,) = (tmp_path / "llm").iterdir()
    stored = json.loads(entry_file.read_text(encoding="utf-8"))
    feedback_hash = stored["inputs"]["corrective_feedback_sha256"]
    assert stored["response_text"] == VALID
    assert feedback_hash == hashlib.sha256(
        b"The response is not valid JSON (line 1, column 1)."
    ).hexdigest()


def test_two_invalid_responses_raise_the_invalid_output_error_with_the_last_raw(tmp_path):
    with pytest.raises(InvalidOutputError) as excinfo:
        flow(tmp_path, ["first bad", "second bad"])

    assert excinfo.value.code is ErrorCode.LLM_INVALID_OUTPUT
    assert excinfo.value.raw_response == "second bad"
    assert "second bad" not in str(excinfo.value)
    assert not (tmp_path / "llm").exists()


def test_a_second_failure_makes_no_third_call(tmp_path):
    provider = FakeProvider(script=["bad", "bad", VALID])
    gateway = LLMGateway(provider, ResponseCache(tmp_path / "llm"), TokenBudget(10**6))

    with pytest.raises(InvalidOutputError):
        extract_fields(document(), located(2), gateway, LLM, PROMPT, "consolidated")

    assert len(provider.calls) == 2


def test_budget_exhausted_by_the_retry_raises_the_budget_error(tmp_path):
    # First call fits (3 + 500 + small prompt); the retry's reservation does not.
    replies = [FakeReply("not json", 100, 100), FakeReply(VALID)]

    with pytest.raises(IngestionError) as excinfo:
        flow(tmp_path, replies, ceiling=700)

    assert excinfo.value.code is ErrorCode.LLM_BUDGET_EXCEEDED


# --- re-runs and the cache ---------------------------------------------------------------


def test_rerun_with_a_valid_cached_response_makes_no_call(tmp_path):
    flow(tmp_path, [VALID])

    result, provider, cache, budget = flow(tmp_path, [])

    assert result.attempts == 1 and provider.calls == []
    assert (cache.hits, budget.used) == (1, 0)


def test_rerun_after_an_invalid_first_response_calls_again_and_hits_the_retry(tmp_path):
    flow(tmp_path, ["not json", VALID])

    result, provider, cache, _ = flow(tmp_path, ["not json"])

    assert result.attempts == 2
    assert len(provider.calls) == 1  # the invalid first response was never cached
    assert cache.hits == 1


def test_a_different_document_hash_is_a_cache_miss(tmp_path):
    flow(tmp_path, [VALID])
    other = document()
    other = IngestedDocument(
        file_info=FileInfo(Path("y.pdf"), "y.pdf", 1, "e" * 64, 2), pages=other.pages
    )

    _, provider, _, _ = flow(tmp_path, [VALID], doc=other)

    assert len(provider.calls) == 1
