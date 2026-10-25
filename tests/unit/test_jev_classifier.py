"""The Jev page classifier with a mocked client: replies, errors, the cache, and the key (PRD v0.4.31; B-295). No network, no SDK client is built."""

import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest

from credit_intel.config import JevSettings
from credit_intel.pagefilter import jev as jev_module
from credit_intel.pagefilter.jev import (
    BASIS_QUESTION,
    ORDERS,
    QUESTIONS_VERSION,
    TYPE_QUESTION,
    JevClassifier,
    build_questions,
    failure_reason,
    page_state,
)
from credit_intel.pagefilter.labels import FAILURE_REASONS, ClassifierError, PageBasis, PageType

SETTINGS = JevSettings(enabled=True, state_lines=3)
TEXT = "Consolidated Balance Sheet\n\n(Rs. in crore)\nAs at 31 March 2025\nTotal assets 1,482.30 1,356.75"
KEY = "not-a-real-key-for-tests"


def answer(choice, confidence, probabilities):
    return SimpleNamespace(choice=choice, confidence=confidence, probabilities=probabilities)


def reply(page_type="balance_sheet", type_conf=0.93, basis="consolidated", basis_conf=0.8, tokens=321, model="jev-1.14.0"):
    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(input_tokens=tokens, output_tokens=0),
        choices={
            TYPE_QUESTION: answer(page_type, type_conf, {page_type: 0.95, "other": 0.05}),
            BASIS_QUESTION: answer(basis, basis_conf, {basis: 0.9, "unclear": 0.1}),
        },
    )


class Client:
    """The SDK client's ``system_one``, scripted: a reply, or an exception to raise."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def system_one(self, state, questions, *, model=None):
        self.calls.append((state, questions, model))
        step = self.script.pop(0) if self.script else reply()
        if isinstance(step, BaseException):
            raise step
        return step


def classifier(client, tmp_path, env=None, **kw):
    return JevClassifier(kw.pop("settings", SETTINGS), {"TYPESAFE_API_KEY": KEY} if env is None else env, cache_dir=tmp_path / "jev", client=client, **kw)


# --- what a good reply becomes ----------------------------------------------------------------------------------------------


def test_a_good_reply_becomes_a_classification(tmp_path):
    client = Client(reply("profit_loss", 0.91, "standalone", 0.77, tokens=400, model="jev-1.14.0"))

    result = classifier(client, tmp_path).classify(7, TEXT)

    assert (result.page_type, result.type_confidence, result.basis, result.basis_confidence) == (PageType.PROFIT_LOSS, 0.91, PageBasis.STANDALONE, 0.77)
    assert (result.model_id, result.input_tokens, result.cached) == ("jev-1.14.0", 400, False)
    assert dict(result.type_probabilities)["profit_loss"] == 0.95 and result.latency_ms >= 0


def test_the_call_names_the_model_and_sends_only_the_top_of_the_page(tmp_path):
    client = Client()

    classifier(client, tmp_path).classify(1, TEXT)

    state, questions, model = client.calls[0]
    assert state == "Consolidated Balance Sheet\n(Rs. in crore)\nAs at 31 March 2025"  # three non-empty lines
    assert model == "jev-latest" and set(questions) == {TYPE_QUESTION, BASIS_QUESTION}
    assert "1,482.30" not in state  # the rows below the headings are not sent


def test_page_state_drops_blank_lines_and_trailing_spaces():
    assert page_state("a  \n\n  \nb\nc\nd", 3) == "a\nb\nc" and page_state("\n \n", 5) == ""


@pytest.mark.parametrize("order", ORDERS)
def test_the_questions_carry_every_option_and_the_order_can_be_reversed(order):
    questions = build_questions(order)

    kinds = list(questions[TYPE_QUESTION].criteria)
    assert set(kinds) == {t.value for t in PageType} and set(questions[BASIS_QUESTION].criteria) == {b.value for b in PageBasis}
    assert (kinds == [t.value for t in PageType]) is (order == "forward")


def test_an_unknown_order_is_refused(tmp_path):
    with pytest.raises(ValueError):
        classifier(Client(), tmp_path, order="shuffled")


# --- the cache -----------------------------------------------------------------------------------------------------------------


def test_a_second_call_for_the_same_page_is_served_from_the_cache_without_a_call_or_a_cost(tmp_path):
    client = Client(reply(tokens=500))
    c = classifier(client, tmp_path)
    first = c.classify(1, TEXT)

    second = c.classify(1, TEXT)

    assert len(client.calls) == 1 and second.cached and second.input_tokens == 0 and second.latency_ms == 0
    assert (second.page_type, second.type_confidence, second.model_id) == (first.page_type, first.type_confidence, first.model_id)
    assert first.input_tokens == 500


def test_a_cached_answer_needs_no_key(tmp_path):
    classifier(Client(reply()), tmp_path).classify(1, TEXT)

    keyless = JevClassifier(SETTINGS, {}, cache_dir=tmp_path / "jev")

    assert not keyless.has_key and keyless.classify(1, TEXT).cached


def test_the_cache_key_changes_with_the_model_the_lines_read_the_order_and_the_text(tmp_path):
    base = classifier(Client(), tmp_path)
    base.classify(1, TEXT)
    others = [
        classifier(Client(), tmp_path, settings=JevSettings(enabled=True, state_lines=3, model="jev-1.14.0")),
        classifier(Client(), tmp_path, settings=JevSettings(enabled=True, state_lines=4)),
        classifier(Client(), tmp_path, order="reversed"),
    ]
    for other in others:
        other.classify(1, TEXT)
        assert other.cache.hits == 0
    again = classifier(Client(), tmp_path)
    again.classify(1, TEXT + " changed first lines\nx")  # a different fourth line is beyond the state: same key
    assert again.cache.hits == 1
    different = classifier(Client(), tmp_path)
    different.classify(1, "Standalone Statement\nof Profit and Loss\nFor the year")
    assert different.cache.hits == 0


def test_the_cache_holds_no_page_text(tmp_path):
    classifier(Client(), tmp_path).classify(1, TEXT)

    stored = "".join(p.read_text() for p in (tmp_path / "jev").iterdir())
    assert "Balance Sheet" not in stored and "31 March" not in stored and QUESTIONS_VERSION not in stored


def test_a_damaged_cache_file_is_only_a_miss(tmp_path):
    c = classifier(Client(), tmp_path)
    c.classify(1, TEXT)
    for path in (tmp_path / "jev").iterdir():
        path.write_text('{"page_type": "nonsense"}', encoding="utf-8")

    again = classifier(Client(), tmp_path)

    assert not again.classify(1, TEXT).cached


# --- failures become fixed reason words ---------------------------------------------------------------------------------------


def sdk_error(name, *bases):
    return type(name, bases or (Exception,), {})


@pytest.mark.parametrize(
    ("raised", "reason"),
    [
        (sdk_error("TypeSafeAPITimeoutError")("slow"), "timeout"),
        (sdk_error("TypeSafeAPIConnectionError")("down"), "connection"),
        (sdk_error("TypeSafeRateLimitError")("429"), "rate_limit"),
        (sdk_error("TypeSafeAuthenticationError")("401"), "auth"),
        (sdk_error("TypeSafePermissionDeniedError")("403"), "auth"),
        (sdk_error("TypeSafeBadRequestError")("max_tokens_exceeded"), "bad_request"),
        (sdk_error("TypeSafeUnprocessableEntityError")("422"), "bad_request"),
        (sdk_error("TypeSafeInternalServerError")("500"), "server"),
        (sdk_error("TypeSafeAPIResponseValidationError")("bad body"), "invalid_reply"),
        (sdk_error("TypeSafeError")("other"), "sdk_error"),
        (RuntimeError("anything"), "error"),
        (TimeoutError("os"), "error"),
    ],
)
def test_an_error_from_the_client_is_a_reason_word_and_nothing_else(tmp_path, raised, reason):
    with pytest.raises(ClassifierError) as caught:
        classifier(Client(raised), tmp_path).classify(1, TEXT)

    assert caught.value.reason == reason and str(caught.value) == reason and reason in FAILURE_REASONS


def test_an_error_subclass_is_matched_by_its_base_class_name():
    child = type("MyTimeout", (sdk_error("TypeSafeAPITimeoutError"),), {})

    assert failure_reason(child("x")) == "timeout"


def test_no_text_of_an_error_reaches_the_reason_or_the_log(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    secret = RuntimeError(f"page text 1,482.30 and key {KEY}")

    with pytest.raises(ClassifierError) as caught:
        classifier(Client(secret), tmp_path).classify(1, TEXT)

    assert "1,482.30" not in str(caught.value) and KEY not in str(caught.value) and caught.value.__cause__ is None
    assert KEY not in caplog.text


@pytest.mark.parametrize(
    "bad",
    [
        SimpleNamespace(model="m", usage=SimpleNamespace(input_tokens=1), choices={}),  # a question missing
        reply(page_type="balance sheet"),  # a label that is not an option
        reply(basis="group"),
        reply(type_conf=1.2),  # a confidence out of range
        reply(basis_conf=-0.1),
        reply(type_conf="high"),
        SimpleNamespace(model="m", choices={}),  # no usage
        None,
    ],
)
def test_a_reply_that_is_not_what_was_asked_is_an_invalid_reply(tmp_path, bad):
    with pytest.raises(ClassifierError) as caught:
        classifier(Client(bad), tmp_path).classify(1, TEXT)

    assert caught.value.reason == "invalid_reply"


def test_a_page_with_no_text_is_not_sent(tmp_path):
    client = Client()

    with pytest.raises(ClassifierError) as caught:
        classifier(client, tmp_path).classify(1, "  \n \n")

    assert caught.value.reason == "invalid_reply" and client.calls == []


def test_without_a_key_nothing_is_sent_and_the_reason_is_auth(tmp_path):
    with pytest.raises(ClassifierError) as caught:
        JevClassifier(SETTINGS, {}, cache_dir=tmp_path / "jev").classify(1, TEXT)

    assert caught.value.reason == "auth"


def test_a_failed_call_is_not_cached(tmp_path):
    c = classifier(Client(RuntimeError("x"), reply()), tmp_path)
    with pytest.raises(ClassifierError):
        c.classify(1, TEXT)

    assert not c.classify(1, TEXT).cached  # the second call went to the client


def test_the_latency_is_the_measured_time_of_the_call(tmp_path):
    ticks = iter([10.0, 10.25])

    result = classifier(Client(), tmp_path, clock=lambda: next(ticks)).classify(1, TEXT)

    assert result.latency_ms == 250


def test_the_key_is_taken_from_the_environment_and_never_from_a_file_or_the_state(tmp_path):
    keyed = JevClassifier(SETTINGS, {"JEV_API_KEY": KEY}, cache_dir=tmp_path / "jev")

    assert keyed.has_key and keyed.sends_off_machine
    assert not hasattr(jev_module, "DEFAULT_KEY") and KEY not in repr(vars(keyed).get("_settings"))


def test_the_real_client_is_built_with_no_retry_and_the_settings_timeout(tmp_path, monkeypatch):
    seen = {}

    class Fake:
        def __init__(self, **kw):
            seen.update(kw)

        def system_one(self, state, questions, *, model=None):
            return reply()

    import typesafe_sdk

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", Fake)
    c = JevClassifier(JevSettings(enabled=True, timeout_seconds=7.5), {"TYPESAFE_API_KEY": KEY}, cache_dir=tmp_path / "jev")

    c.classify(1, TEXT)

    assert seen["api_key"] == KEY and seen["model"] == "jev-latest" and seen["timeout"] == 7.5
    assert seen["retry"].max_retries == 0 and seen["retry"].timeout == 7.5


def test_the_price_is_a_decimal_setting_with_no_default():
    assert JevSettings().price_input_per_million is None and Decimal("0.042") * 1000 == Decimal("42.000")
