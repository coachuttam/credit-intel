"""Every catalogued failure through the API (PRD FR-016 criterion 5 and 13, Section Q Phase 6 exit; closes the gap noted in docs/PHASE6_exit_summary.md).

The SC-09 scenarios (``test_sc09_catalogue.py``) provoke each of the twenty-one command-line codes through the command line. These provoke all
twenty-three through the application: a code that is raised in the request (the first group) answers with its HTTP status and a fixed body and
creates no run; a code that is raised inside a run (the second group) leaves the request ``202`` and shows in the run's status with its code and
fixed message, and the run folder holds only a failure record. A test fails if a code has no scenario here.
"""

import sys
import threading
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

import pipeline_fixture as fx
import test_api as base
from test_api import private_temp  # noqa: F401  (the autouse fixture that points uploads at a folder of the test)
from test_sc09_catalogue import OCR_TABLE, scanned_pdf
from credit_intel.api.app import create_app
from credit_intel.api.errors import HTTP_AT_SUBMISSION
from credit_intel.config import ApiSettings, IngestionSettings
from credit_intel.ingestion.errors import CATALOGUE, ErrorCode, IngestionError
from credit_intel.llm.factory import build_provider
from credit_intel.llm.provider import FakeProvider
from credit_intel.service import RunServices

C = ErrorCode
FROZEN = datetime(2026, 10, 30, 10, 15, 30, 123456, tzinfo=UTC)


class Setup:
    """An application over the given settings, and the means to post to it."""

    def __init__(self, tmp_path, *, provider="fake", ceiling=1_000_000, ocr=False, services=None, env=None, clock=None, max_file_bytes=None, replies=None, pdf=None):
        self.tmp_path = tmp_path
        given = pdf is not None
        self.pdf = pdf or fx.balance_sheet_pdf(tmp_path / "statement.pdf")
        config = tmp_path / "settings.toml"
        config.write_text(f'[llm]\nprovider = "{provider}"\nmodel_id = "m"\ntoken_ceiling = {ceiling}\nmax_output_tokens = 2000\n' + (OCR_TABLE if ocr else ""), encoding="utf-8")
        self.settings = ApiSettings(1, 4, 1200, tmp_path / "out", tmp_path / "cache")
        replies = replies if replies is not None else ([] if given else [fx.good_response(self.pdf)])  # the good reply fits the balance sheet only
        services = services or RunServices(provider_factory=lambda s, e: FakeProvider(script=list(replies)), assignments=tmp_path / "none.jsonl")
        self.app = create_app(self.settings, config=config, services=services, env=env or {}, clock=clock or base.ticker(), max_file_bytes=max_file_bytes)

    def run(self, content=None, name="a.pdf", **fields):
        """Post, and if the run was accepted wait for it. Returns ``(answer, status)``; ``status`` is None when the request was refused."""
        with TestClient(self.app) as client:
            answer = client.post("/runs", files={"file": (name, self.pdf.read_bytes() if content is None else content)}, data={"no_report": "true", **fields})
            if answer.status_code != 202:
                return answer, None
            return answer, base.wait(client, answer.json()["run_id"])


def corrupt_pdf():
    return b"%PDF-1.4\n" + b"this is not a pdf body\n" * 20


def encrypted_pdf(tmp_path):
    path = tmp_path / "locked.pdf"
    pdf = canvas.Canvas(str(path), encrypt=StandardEncryption("user", "owner"))
    pdf.drawString(72, 700, "Consolidated Balance Sheet")
    pdf.save()
    return path.read_bytes()


def long_pdf(tmp_path):
    path = tmp_path / "long.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    for page in range(IngestionSettings().max_pages + 1):
        pdf.drawString(72, 700, f"Page {page}")
        pdf.showPage()
    pdf.save()
    return path.read_bytes()


def imageless_pdf(tmp_path):
    path = tmp_path / "image.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.rect(72, 72, 200, 200, fill=1)
    pdf.showPage()
    pdf.save()
    return path.read_bytes()


# --- raised in the request: the HTTP status and a fixed body, and no run ----------------------------------------------------------------------------


def too_large(t):
    return Setup(t, max_file_bytes=1000).run(content=b"%PDF-" + b"x" * 5000)


def not_pdf(t):
    return Setup(t).run(content=b"plain text")


def send_refused(t):
    return Setup(t, provider="openai").run()


def profile_invalid(t):
    return Setup(t).run(profile="{bad")


def page_range_syntax(t):
    return Setup(t).run(pages="9-1")


def api_request(t):
    return Setup(t).run(basis="neither")


def config_invalid(t):
    setup = Setup(t)
    (t / "settings.toml").write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\nmax_output_tokens = 10\n', encoding="utf-8")
    return setup.run()


def ocr_unavailable(t):
    from credit_intel.ingestion.tesseract_ocr import TesseractExtractor

    absent = lambda: TesseractExtractor(command="no-such-ocr-engine-installed")  # noqa: E731  (whatever is installed on this machine)
    pdf = scanned_pdf(t)
    services = RunServices(provider_factory=lambda s, e: FakeProvider(script=[]), ocr_factory=absent, assignments=t / "none.jsonl")
    return Setup(t, ocr=True, services=services, pdf=pdf).run(ocr="true", pages="1")


HTTP = {C.TOO_LARGE: 413, C.NOT_PDF: 422, C.SEND_REFUSED: 403, C.PROFILE_INVALID: 422, C.PAGE_RANGE: 422, C.API_REQUEST: 422, C.CONFIG_INVALID: 500, C.OCR_UNAVAILABLE: 503}  # PRD FR-016.5
SUBMISSION = {C.TOO_LARGE: too_large, C.NOT_PDF: not_pdf, C.SEND_REFUSED: send_refused, C.PROFILE_INVALID: profile_invalid, C.PAGE_RANGE: page_range_syntax,
              C.API_REQUEST: api_request, C.CONFIG_INVALID: config_invalid, C.OCR_UNAVAILABLE: ocr_unavailable}  # fmt: skip


# --- raised inside a run: 202, then the run's status ------------------------------------------------------------------------------------------------


def not_found(t):
    """The upload vanishes between acceptance and the start of the run."""
    pdf = fx.balance_sheet_pdf(t / "statement.pdf")
    gate = threading.Event()
    entered = threading.Semaphore(0)

    def factory(s, e):
        class Provider:
            def complete(self, request):
                entered.release()
                assert gate.wait(30)
                return FakeProvider(script=[fx.good_response(pdf)]).complete(request)

        return Provider()

    setup = Setup(t, pdf=pdf, services=RunServices(provider_factory=factory, assignments=t / "none.jsonl"))
    with TestClient(setup.app) as client:
        first = client.post("/runs", files={"file": ("a.pdf", setup.pdf.read_bytes())}, data={"no_report": "true"})
        assert entered.acquire(timeout=30)
        second = client.post("/runs", files={"file": ("b.pdf", setup.pdf.read_bytes() + b"\n%2")}, data={"no_report": "true"})
        job = setup.app.state.jobs.get(second.json()["run_id"])
        for path in job.upload_dir.iterdir():
            path.unlink()  # the temporary copy is gone before the run starts
        gate.set()
        base.wait(client, first.json()["run_id"])
        return second, base.wait(client, second.json()["run_id"])


def corrupt(t):
    return Setup(t).run(content=corrupt_pdf())


def encrypted(t):
    return Setup(t).run(content=encrypted_pdf(t))


def too_many_pages(t):
    return Setup(t).run(content=long_pdf(t))


def no_text_layer(t):
    return Setup(t).run(content=imageless_pdf(t))


def page_range_in_status(t):
    return Setup(t).run(pages="99")  # a well-formed range that is outside this document


def no_statement_pages(t):
    return Setup(t, pdf=fx.blank_text_pdf(t / "blank.pdf")).run()


def basis_unavailable(t):
    return Setup(t).run(basis="standalone")


def llm_invalid_output(t):
    return Setup(t, replies=["not json", "still not json"]).run()


def llm_unavailable(t):
    class Down:
        def complete(self, request):
            raise IngestionError(C.LLM_UNAVAILABLE)

    return Setup(t, services=RunServices(provider_factory=lambda s, e: Down(), assignments=t / "none.jsonl")).run()


def llm_auth(t):
    services = RunServices(provider_factory=build_provider, assignments=t / "none.jsonl")  # the real factory, with no key in the environment
    return Setup(t, provider="openai", services=services).run(confirm_public_document="true")


def llm_budget(t):
    return Setup(t, ceiling=10).run()


def ocr_failed(t):
    from credit_intel.ingestion.fake_ocr import FakeOcrExtractor

    services = RunServices(provider_factory=lambda s, e: FakeProvider(script=[]), ocr_factory=lambda: FakeOcrExtractor({}, page_count=1, fail=True), assignments=t / "none.jsonl")
    return Setup(t, ocr=True, services=services, pdf=scanned_pdf(t)).run(ocr="true", pages="1")


def parse_limit(t):
    from credit_intel.config import ParseLimits
    from credit_intel.ingestion.sandbox import SandboxedExtractor

    stub = t / "slow_worker.py"
    stub.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")  # a worker that never finishes
    slow = lambda config, env: SandboxedExtractor(ParseLimits(1, 4096), command=(sys.executable, str(stub)), poll_seconds=0.05)  # noqa: E731
    return Setup(t, services=RunServices(provider_factory=lambda s, e: FakeProvider(script=[]), extractor_factory=slow, assignments=t / "none.jsonl")).run()


def run_timeout(t):
    class Clock:
        now = 1000.0

    from credit_intel.api.jobs import JobManager

    time_ = Clock()
    setup = Setup(t)
    pdf = setup.pdf

    def factory(s, e):
        class Provider:
            def complete(self, request):
                time_.now += 5000  # the call outlasts the limit
                return FakeProvider(script=[fx.good_response(pdf)]).complete(request)

        return Provider()

    services = RunServices(provider_factory=factory, assignments=t / "none.jsonl")
    config = t / "settings.toml"
    clock = base.ticker()
    manager = JobManager(setup.settings, config, services, {}, clock, lambda: time_.now)
    setup.app = create_app(setup.settings, config=config, services=services, env={}, clock=clock, manager=manager)
    return setup.run()


def export_failed(t):
    """The run folder already exists: the same document at the same moment, in a service that has forgotten the first run."""
    first = Setup(t, clock=lambda: FROZEN)
    answer, status = first.run()
    assert status["state"] == "exported"
    again = create_app(first.settings, config=t / "settings.toml", services=RunServices(provider_factory=lambda s, e: FakeProvider(script=[fx.good_response(first.pdf)]),
                                                                                         assignments=t / "none.jsonl"), env={}, clock=lambda: FROZEN)  # fmt: skip
    first.app = again
    first.original = (answer.json()["run_id"], sorted(p.name for p in (first.settings.output_dir / answer.json()["run_id"]).iterdir()))
    result = first.run()
    result[1]["original"] = first.original
    result[1]["_setup"] = first
    return result


def run_interrupted(t):
    """The service stops with a run waiting, and is started again: the new service records the run as interrupted. (The request was answered `202` by the first service.)"""
    pdf = fx.balance_sheet_pdf(t / "statement.pdf")
    gate = threading.Event()
    entered = threading.Semaphore(0)

    def factory(s, e):
        class Provider:
            def complete(self, request):
                entered.release()
                assert gate.wait(30)
                return FakeProvider(script=[fx.good_response(pdf)]).complete(request)

        return Provider()

    first = Setup(t, pdf=pdf, services=RunServices(provider_factory=factory, assignments=t / "none.jsonl"), clock=base.ticker())
    with TestClient(first.app) as client:
        client.post("/runs", files={"file": ("a.pdf", pdf.read_bytes())}, data={"no_report": "true"})
        assert entered.acquire(timeout=30)
        waiting = client.post("/runs", files={"file": ("b.pdf", pdf.read_bytes() + b"\n%2")}, data={"no_report": "true"})
        assert waiting.status_code == 202
    gate.set()  # the first service has shut down; its running run may finish, the waiting one never started
    end = time.monotonic() + 30
    while first.app.state.jobs.counts["running"] and time.monotonic() < end:
        time.sleep(0.02)
    second = Setup(t, pdf=pdf, clock=base.ticker())
    with TestClient(second.app) as client:  # the restart: the marker found at start is recorded
        return waiting, client.get(f"/runs/{waiting.json()['run_id']}").json()


IN_RUN = {C.RUN_INTERRUPTED: run_interrupted, C.NOT_FOUND: not_found, C.CORRUPT: corrupt, C.ENCRYPTED: encrypted, C.TOO_MANY_PAGES: too_many_pages, C.NO_TEXT_LAYER: no_text_layer, C.PAGE_RANGE: page_range_in_status,
          C.NO_STATEMENT_PAGES: no_statement_pages, C.BASIS_UNAVAILABLE: basis_unavailable, C.LLM_INVALID_OUTPUT: llm_invalid_output, C.LLM_UNAVAILABLE: llm_unavailable,
          C.LLM_AUTH: llm_auth, C.LLM_BUDGET_EXCEEDED: llm_budget, C.OCR_FAILED: ocr_failed, C.PARSE_LIMIT: parse_limit, C.RUN_TIMEOUT: run_timeout, C.EXPORT_FAILED: export_failed}  # fmt: skip


# --- the tests -----------------------------------------------------------------------------------------------------------------------------------


def test_every_catalogued_code_has_a_scenario_through_the_api():
    assert set(SUBMISSION) | set(IN_RUN) == set(CATALOGUE) == set(ErrorCode)
    for code, status in HTTP_AT_SUBMISSION.items():
        if code in SUBMISSION:
            assert status is not None, code  # a code raised in the request has an HTTP status
    assert set(SUBMISSION) <= {c for c, s in HTTP_AT_SUBMISSION.items() if s is not None}


@pytest.mark.parametrize("code", list(SUBMISSION), ids=[c.value for c in SUBMISSION])
def test_a_code_raised_in_the_request_answers_with_its_http_status_and_a_fixed_body_and_makes_no_run(tmp_path, code, private_temp):
    answer, status = SUBMISSION[code](tmp_path)
    entry = CATALOGUE[code]
    body = answer.json()

    assert status is None and answer.status_code == HTTP[code] == HTTP_AT_SUBMISSION[code], body  # the status of the PRD's table, and the table of the code
    assert set(body) == {"code", "message"} and body["code"] == code.value and body["message"].startswith(entry.message.split(" (")[0].rstrip("."))
    assert entry.action.rstrip(".") in body["message"]
    assert "Traceback" not in body["message"] and str(tmp_path) not in body["message"]
    assert not (tmp_path / "out").exists()
    assert base.upload_leftovers(private_temp) == []


@pytest.mark.parametrize("code", [c for c in IN_RUN if c is not C.EXPORT_FAILED], ids=[c.value for c in IN_RUN if c is not C.EXPORT_FAILED])
def test_a_code_raised_inside_a_run_is_in_the_status_with_its_code_and_message_and_the_folder_holds_only_the_failure_record(tmp_path, code, private_temp):
    answer, status = IN_RUN[code](tmp_path)
    entry = CATALOGUE[code]

    assert answer.status_code == 202 and status["state"] == "failed", status
    assert status["error"]["code"] == code.value and status["error"]["message"].startswith(entry.message.split(" (")[0].rstrip("."))
    assert entry.action.rstrip(".") in status["error"]["message"]
    assert "Traceback" not in str(status) and str(tmp_path) not in str(status)
    folders = sorted(p for p in (tmp_path / "out").glob("*") if p.name != ".pending") if (tmp_path / "out").exists() else []
    if code is C.NOT_FOUND:
        assert answer.json()["run_id"] not in [f.name for f in folders] and status["files"] == []  # it failed before `received`: nothing was recorded (the first run is whole)
    else:
        names = [f.name for f in folders]
        run_id = answer.json()["run_id"]
        assert run_id in names and (code is C.RUN_INTERRUPTED or names == [run_id])  # the interrupted scenario also has the first run, which finished
        assert status["files"] == ["manifest.json"] and [p.name for p in (tmp_path / "out" / run_id).iterdir()] == ["manifest.json"]
        import json

        record = json.loads((tmp_path / "out" / run_id / "manifest.json").read_text(encoding="utf-8"))
        assert record["final_state"] == "failed" and record["error_code"] == code.value
        assert record["failed_stage"] in [s.strip() for s in entry.stage.split("/")] or code in (C.RUN_TIMEOUT, C.RUN_INTERRUPTED), (record["failed_stage"], entry.stage)
        assert status["stage"] == record["failed_stage"]
    assert base.upload_leftovers(private_temp) == []


def test_a_run_folder_that_already_exists_is_export_failed_in_the_status_and_the_first_run_is_left_whole(tmp_path, private_temp):
    answer, status = export_failed(tmp_path)
    original_id, original_files = status["original"]
    assert answer.status_code == 202 and answer.json()["run_id"] == original_id  # the same document at the same moment: the same run ID
    assert status["state"] == "failed" and status["error"]["code"] == "E-EXPORT-FAILED" and CATALOGUE[C.EXPORT_FAILED].action.rstrip(".") in status["error"]["message"]
    folder = tmp_path / "out" / original_id
    assert sorted(p.name for p in folder.iterdir()) == original_files == ["manifest.json", "memo.md", "results.json"]  # never overwritten (FR-010.4)
    import json

    assert json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["final_state"] == "exported"
    assert not list((tmp_path / "out").glob(".*.partial")) and base.upload_leftovers(private_temp) == []
