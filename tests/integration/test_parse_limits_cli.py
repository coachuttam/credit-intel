"""The command line parses in a worker process under the required limits (PRD SEC-12, FR-001 criterion 10, v0.4.50; B-324).

These tests pass the real factory (captured before the suite-wide fixture replaces it with an in-process parser).
"""

import io
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel import cli, service
from credit_intel.config import ENV_PARSE_MEMORY, ENV_PARSE_TIMEOUT, load_parse_limits
from credit_intel.ingestion.errors import ErrorCode
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor
from credit_intel.ingestion.sandbox import SandboxedExtractor
from credit_intel.llm.provider import FakeProvider

REAL_FACTORY = service.sandboxed_extractor
START = datetime(2026, 10, 24, 10, 15, 30, tzinfo=UTC)
SETTINGS = '[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'
LIMITS_ENV = {ENV_PARSE_TIMEOUT: "120", ENV_PARSE_MEMORY: "4096"}


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def run(tmp_path, pdf, *, env, factory, settings=SETTINGS):
    config = tmp_path / "settings.toml"
    config.write_text(settings, encoding="utf-8")
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    out, err = io.StringIO(), io.StringIO()
    code = cli.main([str(pdf), "--config", str(config)], provider_factory=lambda s, e: FakeProvider(script=[fx.good_response(pdf)]),
                    clock=lambda: next(ticks), stdout=out, stderr=err, assignments=tmp_path / "none.jsonl", env=env, extractor_factory=factory)  # fmt: skip
    return code, out.getvalue(), err.getvalue()




def test_without_the_two_limits_a_run_stops_with_config_invalid_before_anything_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "sandboxed_extractor", REAL_FACTORY)  # the command line's own default, not an injected factory
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")
    code, out, err = run(tmp_path, pdf, env={}, factory=None)

    assert code == 6 and out == "" and err.startswith(ErrorCode.CONFIG_INVALID.value) and "ingestion.parse_timeout_seconds" in err
    assert not (tmp_path / "runs").exists()


def test_with_the_limits_set_by_environment_the_factory_builds_a_sandboxed_extractor(tmp_path):
    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS, encoding="utf-8")
    extractor = REAL_FACTORY(config, LIMITS_ENV)
    assert isinstance(extractor, SandboxedExtractor)


def test_a_run_through_the_worker_writes_the_same_files_as_an_in_process_run(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")
    code_a, out_a, _ = run(tmp_path, pdf, env=LIMITS_ENV, factory=REAL_FACTORY)
    first = Path(out_a.strip())
    contents_a = {p.name: p.read_bytes() for p in first.iterdir()}
    for p in first.iterdir():
        p.unlink()
    first.rmdir()
    shutil.rmtree(DEFAULT_CACHE_DIR, ignore_errors=True)  # so the second run does not read the first run's cached reply
    code_b, out_b, _ = run(tmp_path, pdf, env=LIMITS_ENV, factory=lambda config, env: PdfplumberExtractor())
    second = Path(out_b.strip())
    contents_b = {p.name: p.read_bytes() for p in second.iterdir()}

    assert code_a == code_b == 0 and sorted(contents_a) == ["manifest.json", "memo.md", "results.json"]
    assert contents_a["memo.md"] == contents_b["memo.md"] and contents_a["results.json"] == contents_b["results.json"]
    assert json.loads(contents_a["manifest.json"]) == json.loads(contents_b["manifest.json"])


def test_a_run_that_passes_the_time_limit_exits_3_with_the_new_code_and_no_document_text(tmp_path, monkeypatch):
    import sys

    stub = tmp_path / "slow.py"
    stub.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf")
    slow = lambda config, env: SandboxedExtractor(load_parse_limits(config, env), command=(sys.executable, str(stub)), poll_seconds=0.05)  # noqa: E731

    code, out, err = run(tmp_path, pdf, env={ENV_PARSE_TIMEOUT: "1", ENV_PARSE_MEMORY: "4096"}, factory=slow)

    assert code == 3 and out == "" and any(line.startswith("E-INPUT-PARSE-LIMIT: ") for line in err.splitlines()) and "ingestion.parse_timeout_seconds" in err
    for forbidden in ("Total current assets", "statement.pdf", str(tmp_path)):
        assert forbidden not in err


def test_with_ocr_the_run_hands_the_sandbox_renderer_to_the_engine(tmp_path):
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    from credit_intel.ingestion.fake_ocr import FakeOcrExtractor

    scan = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(scan), pagesize=(612, 792), invariant=1)
    pdf.drawImage(ImageReader(Image.new("RGB", (1700, 2200), "white")), 0, 0, 612, 792)
    pdf.showPage()
    pdf.save()
    taken = []

    class Engine(FakeOcrExtractor):
        def use_renderer(self, renderer):
            taken.append(renderer)

    config = tmp_path / "settings.toml"
    config.write_text(SETTINGS + "[ocr]\nenabled = true\nmin_image_area_share = 0.5\nmax_pages = 5\ntimeout_seconds = 60\ncolumn_margin_pt = 3\nsplit_figure_gap_pt = 2.0\n", encoding="utf-8")
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    cli.main([str(scan), "--ocr", "--pages", "1", "--config", str(config)], provider_factory=lambda s, e: FakeProvider(script=[]), clock=lambda: next(ticks),
             stdout=io.StringIO(), stderr=io.StringIO(), assignments=tmp_path / "none.jsonl", env=LIMITS_ENV, extractor_factory=REAL_FACTORY,
             ocr_factory=lambda: Engine({}, page_count=1))  # fmt: skip

    assert len(taken) == 1 and getattr(taken[0], "__name__", "") == "render_page" and isinstance(taken[0].__self__, SandboxedExtractor)
