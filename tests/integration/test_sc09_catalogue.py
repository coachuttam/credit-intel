"""SC-09: every catalogued failure scenario gives its documented code, a non-zero exit and no output that looks complete
(PRD SC-09, FR-011.6, G.1, FR-014.3, Definition of Done item 6; Phase 5 step 5m; B-272).

Each of the twenty codes of the error catalogue is provoked through the command line with synthetic input and a fake
provider. A test fails if a code has no scenario, so a code added to the catalogue without one cannot go unnoticed.
"""

import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.config import IngestionSettings
from credit_intel.ingestion.errors import CATALOGUE, ErrorCode, IngestionError
from credit_intel.llm.factory import build_provider
from credit_intel.llm.provider import FakeProvider

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
KEY = "sk-test-NOT-A-REAL-KEY-12345"


def clock():
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    return lambda: next(ticks)


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


OCR_TABLE = "[ocr]\nenabled = true\nmin_image_area_share = 0.5\nmax_pages = 5\ntimeout_seconds = 60\ncolumn_margin_pt = 3\nsplit_figure_gap_pt = 2.0\n"


def settings(tmp_path, provider="fake", ceiling=1_000_000, ocr=False):
    path = tmp_path / "settings.toml"
    path.write_text(f'[llm]\nprovider = "{provider}"\nmodel_id = "m"\ntoken_ceiling = {ceiling}\nmax_output_tokens = 2000\n' + (OCR_TABLE if ocr else ""), encoding="utf-8")
    return path


def balance_sheet(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def invoke(tmp_path, pdf, *extra, replies=None, factory=None, provider="fake", ceiling=1_000_000, config=None, env=None, ocr=False, ocr_factory=None, extractor_factory=None):
    out, err = io.StringIO(), io.StringIO()
    argv = [str(pdf), *extra, "--config", str(config or settings(tmp_path, provider, ceiling, ocr))]
    engine = {} if ocr_factory is None else {"ocr_factory": ocr_factory}
    if extractor_factory is not None:
        engine["extractor_factory"] = extractor_factory
    code = main(argv, provider_factory=factory or (lambda s, e: FakeProvider(script=replies or [])), clock=clock(), stdout=out, stderr=err,
                assignments=tmp_path / "none.jsonl", env=env if env is not None else {}, **engine)  # fmt: skip
    return code, out.getvalue(), err.getvalue()


# --- the scenarios: one per catalogue code -----------------------------------------------------------------------------------------------------


def not_found(tmp_path):
    return invoke(tmp_path, tmp_path / "absent.pdf")


def too_large(tmp_path):
    big = tmp_path / "big.pdf"
    with big.open("wb") as handle:
        handle.write(b"%PDF-1.4\n")
        handle.truncate(IngestionSettings().max_file_bytes + 1)
    return invoke(tmp_path, big)


def not_pdf(tmp_path):
    text = tmp_path / "note.pdf"
    text.write_text("this is not a pdf", encoding="utf-8")
    return invoke(tmp_path, text)


def corrupt(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\n" + b"this is not a pdf body\n" * 20)
    return invoke(tmp_path, broken)


def encrypted(tmp_path):
    path = tmp_path / "locked.pdf"
    pdf = canvas.Canvas(str(path), encrypt=StandardEncryption("user", "owner"))
    pdf.drawString(72, 700, "Consolidated Balance Sheet")
    pdf.save()
    return invoke(tmp_path, path)


def too_many_pages(tmp_path):
    path = tmp_path / "long.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    for page in range(IngestionSettings().max_pages + 1):
        pdf.drawString(72, 700, f"Page {page}")
        pdf.showPage()
    pdf.save()
    return invoke(tmp_path, path)


def no_text_layer(tmp_path):
    path = tmp_path / "image.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.rect(72, 72, 200, 200, fill=1)  # drawing only: no text
    pdf.showPage()
    pdf.save()
    return invoke(tmp_path, path)


def send_refused(tmp_path):
    return invoke(tmp_path, balance_sheet(tmp_path), provider="openai", env={})  # not on the record, no confirmation: the refusal comes first


def page_range(tmp_path):
    return invoke(tmp_path, balance_sheet(tmp_path), "--pages", "99")


def profile_invalid(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text('{"unknown": "x"}', encoding="utf-8")
    return invoke(tmp_path, balance_sheet(tmp_path), "--profile", str(profile))


def no_statement_pages(tmp_path):
    return invoke(tmp_path, fx.blank_text_pdf(tmp_path / "blank.pdf"))


def basis_unavailable(tmp_path):
    return invoke(tmp_path, balance_sheet(tmp_path), "--basis", "standalone")


def llm_invalid_output(tmp_path):
    return invoke(tmp_path, balance_sheet(tmp_path), replies=["not json", "still not json"])


def llm_unavailable(tmp_path):
    class Down:
        def complete(self, request):
            raise IngestionError(ErrorCode.LLM_UNAVAILABLE)

    return invoke(tmp_path, balance_sheet(tmp_path), factory=lambda s, e: Down())


def llm_auth(tmp_path):
    return invoke(tmp_path, balance_sheet(tmp_path), "--confirm-public-document", factory=build_provider, provider="openai", env={})


def llm_budget(tmp_path):
    return invoke(tmp_path, balance_sheet(tmp_path), ceiling=10)


def config_invalid(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\nmax_output_tokens = 10\n', encoding="utf-8")
    return invoke(tmp_path, balance_sheet(tmp_path), config=bad)


def export_failed(tmp_path):
    pdf = balance_sheet(tmp_path)
    first = invoke(tmp_path, pdf, replies=[fx.good_response(pdf)])
    assert first[0] == 0
    return invoke(tmp_path, pdf, replies=[fx.good_response(pdf)])  # the same clock gives the same run ID: the folder exists


def scanned_pdf(tmp_path):
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    path = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    pdf.drawImage(ImageReader(Image.new("RGB", (20, 20), "white")), 0, 0, 612, 792)  # one full-page image and no text
    pdf.showPage()
    pdf.save()
    return path


def ocr_unavailable(tmp_path):
    from credit_intel.ingestion.tesseract_ocr import TesseractExtractor

    absent = lambda: TesseractExtractor(command="no-such-ocr-engine-installed")  # noqa: E731  (whatever is installed on this machine)
    return invoke(tmp_path, scanned_pdf(tmp_path), "--ocr", "--pages", "1", ocr=True, ocr_factory=absent)


def ocr_failed(tmp_path):
    from credit_intel.ingestion.fake_ocr import FakeOcrExtractor

    return invoke(tmp_path, scanned_pdf(tmp_path), "--ocr", "--pages", "1", ocr=True, ocr_factory=lambda: FakeOcrExtractor({}, page_count=1, fail=True))


def parse_limit(tmp_path):
    from credit_intel.config import ENV_PARSE_MEMORY, ENV_PARSE_TIMEOUT, ParseLimits
    from credit_intel.ingestion.sandbox import SandboxedExtractor

    stub = tmp_path / "slow_worker.py"
    stub.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")  # a worker that never finishes
    slow = lambda config, env: SandboxedExtractor(ParseLimits(1, 4096), command=(sys.executable, str(stub)), poll_seconds=0.05)  # noqa: E731
    return invoke(tmp_path, balance_sheet(tmp_path), extractor_factory=slow, env={ENV_PARSE_TIMEOUT: "1", ENV_PARSE_MEMORY: "4096"})


SCENARIOS = {
    ErrorCode.NOT_FOUND: not_found,
    ErrorCode.TOO_LARGE: too_large,
    ErrorCode.NOT_PDF: not_pdf,
    ErrorCode.CORRUPT: corrupt,
    ErrorCode.ENCRYPTED: encrypted,
    ErrorCode.TOO_MANY_PAGES: too_many_pages,
    ErrorCode.NO_TEXT_LAYER: no_text_layer,
    ErrorCode.PAGE_RANGE: page_range,
    ErrorCode.SEND_REFUSED: send_refused,
    ErrorCode.PROFILE_INVALID: profile_invalid,
    ErrorCode.NO_STATEMENT_PAGES: no_statement_pages,
    ErrorCode.BASIS_UNAVAILABLE: basis_unavailable,
    ErrorCode.LLM_INVALID_OUTPUT: llm_invalid_output,
    ErrorCode.LLM_UNAVAILABLE: llm_unavailable,
    ErrorCode.LLM_AUTH: llm_auth,
    ErrorCode.LLM_BUDGET_EXCEEDED: llm_budget,
    ErrorCode.CONFIG_INVALID: config_invalid,
    ErrorCode.EXPORT_FAILED: export_failed,
    ErrorCode.OCR_UNAVAILABLE: ocr_unavailable,
    ErrorCode.OCR_FAILED: ocr_failed,
    ErrorCode.PARSE_LIMIT: parse_limit,
}


def test_every_code_in_the_catalogue_has_a_scenario_and_no_scenario_is_for_an_unknown_code():
    api_only = {ErrorCode.RUN_TIMEOUT, ErrorCode.API_REQUEST}  # raised only by the API: their scenarios are in test_api_*.py
    assert set(SCENARIOS) == set(CATALOGUE) - api_only == set(ErrorCode) - api_only and len(SCENARIOS) == 21


@pytest.mark.parametrize("code", list(SCENARIOS), ids=[c.value for c in SCENARIOS])
def test_each_scenario_gives_its_code_its_exit_code_and_no_output_that_looks_complete(tmp_path, code):
    exit_, out, err = SCENARIOS[code](tmp_path)
    entry = CATALOGUE[code]

    assert exit_ == entry.exit_code != 0, err
    assert out == "", "nothing may be printed to standard output on a failure"
    error_lines = [line for line in err.splitlines() if line.startswith("E-")]
    assert len(error_lines) == 1 and error_lines[0].startswith(f"{code.value}: "), err
    assert entry.action.rstrip(".") in error_lines[0] or entry.action in error_lines[0]  # the line says what the user should do
    assert "Traceback" not in err and str(tmp_path) not in err

    for folder in (tmp_path / "runs").glob("*") if (tmp_path / "runs").exists() else []:
        names = sorted(p.name for p in folder.iterdir())
        if code is ErrorCode.EXPORT_FAILED and names == ["manifest.json", "memo.md", "results.json"]:
            continue  # the earlier successful run that the refused export collided with
        assert names == ["manifest.json"], (folder, names)  # at most a failure record: no memo, no results
        record = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        assert record["final_state"] == "failed" and record["error_code"] == code.value
        assert record["failed_stage"] in [s.strip() for s in entry.stage.split("/")], (record["failed_stage"], entry.stage)

    assert not list((tmp_path / "runs").glob("*/memo.md")) or code is ErrorCode.EXPORT_FAILED
    assert not list(tmp_path.glob("runs/.*.partial")), "no staging folder is left behind"


def test_no_failure_message_contains_the_api_key_document_text_or_a_value(tmp_path):
    seen = []
    for code, scenario in SCENARIOS.items():
        sub = tmp_path / code.value
        sub.mkdir()
        seen.append(scenario_in(sub, scenario))
    text = "\n".join(seen)

    for forbidden in (KEY, "Total current assets", "1,482.30", "Acme", "Directors' report", "good year"):
        assert forbidden not in text


def scenario_in(directory: Path, scenario) -> str:
    import os

    previous = Path.cwd()
    os.chdir(directory)
    try:
        return scenario(directory)[2]
    finally:
        os.chdir(previous)


def test_a_failure_with_a_key_in_the_environment_never_prints_it(tmp_path):
    pdf = balance_sheet(tmp_path)

    class Broken:
        def complete(self, request):
            raise RuntimeError(f"the key {KEY} was rejected")

    code, out, err = invoke(tmp_path, pdf, factory=lambda s, e: Broken(), env={"OPENAI_API_KEY": KEY})

    assert code == 1 and KEY not in err and KEY not in out
