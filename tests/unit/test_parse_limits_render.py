"""The OCR page render behind the parse limits (PRD SEC-12 step 2, v0.4.50; B-325).

The real worker renders generated pages and is compared with the in-process render; stub workers stand in for a hung, greedy, noisy
or crashing renderer. Synthetic pages only.
"""

import json
import stat
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from credit_intel import service
from credit_intel.config import ParseLimits
from credit_intel.ingestion import sandbox
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.fake_ocr import FakeOcrExtractor
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor
from credit_intel.ingestion.sandbox import SandboxedExtractor
from credit_intel.ingestion.tesseract_ocr import TesseractExtractor

LIMITS = ParseLimits(timeout_seconds=60, memory_mb=4096)


@pytest.fixture
def scan(tmp_path):
    path = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    for shade in ("white", "lightgrey", "grey"):
        pdf.drawImage(ImageReader(Image.new("RGB", (850, 1100), shade)), 0, 0, 612, 792)
        pdf.showPage()
    pdf.save()
    return path


def in_process(path, page, dpi):
    (rendered,) = TesseractExtractor._render(path, [page], {page: dpi})
    return rendered


# --- the real worker renders what this process renders ------------------------------------------------------


def test_the_worker_renders_the_same_image_as_this_process(scan):
    extractor = SandboxedExtractor(LIMITS)
    for page, dpi in ((1, 100), (2, 72), (3, 150)):
        assert extractor.render_page(scan, page, dpi) == in_process(scan, page, dpi)


def test_the_image_comes_back_in_memory_and_no_file_is_written(scan):
    before = {p.name for p in Path(tempfile.gettempdir()).iterdir()}
    png, width, height = SandboxedExtractor(LIMITS).render_page(scan, 1, 100)
    assert png.startswith(b"\x89PNG") and (width, height) == (612.0, 792.0)
    assert {p.name for p in Path(tempfile.gettempdir()).iterdir()} == before  # no scratch directory, no image


def test_a_page_outside_the_document_and_a_file_that_is_not_a_pdf_are_reported(scan, tmp_path):
    extractor = SandboxedExtractor(LIMITS)
    with pytest.raises(IngestionError) as outside:
        extractor.render_page(scan, 9, 100)
    assert outside.value.code is ErrorCode.PAGE_RANGE
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"%PDF-1.4\nnot a pdf\n")
    with pytest.raises(IngestionError) as bad:
        extractor.render_page(junk, 1, 100)
    assert bad.value.code is ErrorCode.OCR_FAILED


def test_the_worker_render_and_the_parse_operations_share_one_budget(scan):
    now = [0.0]
    extractor = SandboxedExtractor(ParseLimits(10, 4096), clock=lambda: now[0], poll_seconds=0.01)
    extractor.inspect(scan)  # the first operation starts the budget
    now[0] = 10.0
    with pytest.raises(IngestionError) as error:
        extractor.render_page(scan, 1, 100)
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.TIME_DETAIL in str(error.value)


# --- stub workers ---------------------------------------------------------------------------------------


def stub(tmp_path, body):
    path = tmp_path / "render_stub.py"
    path.write_text("import json, os, sys, time\n" + body, encoding="utf-8")
    return (sys.executable, str(path))


def sandboxed(command, timeout=60, memory=4096, **kw):
    return SandboxedExtractor(ParseLimits(timeout, memory), command=command, poll_seconds=0.05, **kw)


GOOD = "sys.stdout.buffer.write(json.dumps({'ok': True, 'width': 1.0, 'height': 2.0}).encode() + b'\\n' + b'PNGDATA')\n"


def test_a_stub_that_answers_properly_is_read(tmp_path):
    assert sandboxed(stub(tmp_path, GOOD)).render_page(tmp_path / "x.pdf", 1, 100) == (b"PNGDATA", 1.0, 2.0)


def test_a_render_that_passes_the_parse_budget_is_a_parse_limit(tmp_path):
    with pytest.raises(IngestionError) as error:
        sandboxed(stub(tmp_path, "time.sleep(60)\n"), timeout=1).render_page(tmp_path / "x.pdf", 1, 100)
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.TIME_DETAIL in str(error.value)


def test_a_render_that_passes_the_ocr_calls_own_time_is_an_ocr_failure_not_a_parse_limit(tmp_path):
    with pytest.raises(IngestionError) as error:
        sandboxed(stub(tmp_path, "time.sleep(600)\n"), timeout=5).render_page(tmp_path / "x.pdf", 1, 100, timeout_seconds=0.5)
    assert error.value.code is ErrorCode.OCR_FAILED


def test_a_render_that_passes_the_memory_limit_is_stopped(tmp_path):
    body = "blocks = [bytearray(1024 * 1024 * 40) for _ in range(5)]\nfor b in blocks: b[::4096] = b'x' * len(b[::4096])\ntime.sleep(60)\n"
    with pytest.raises(IngestionError) as error:
        sandboxed(stub(tmp_path, body), memory=120).render_page(tmp_path / "x.pdf", 1, 100)
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.MEMORY_DETAIL in str(error.value)


def test_an_image_larger_than_the_cap_is_a_memory_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MAX_RENDER_BYTES", 1000)
    body = "sys.stdout.buffer.write(b'{\"ok\": true}\\n' + b'x' * 100000)\ntime.sleep(60)\n"
    with pytest.raises(IngestionError) as error:
        sandboxed(stub(tmp_path, body)).render_page(tmp_path / "x.pdf", 1, 100)
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.MEMORY_DETAIL in str(error.value)


@pytest.mark.parametrize(
    "body, code",
    [
        ("sys.exit(1)\n", ErrorCode.OCR_FAILED),
        ("os.kill(os.getpid(), 9)\n", ErrorCode.OCR_FAILED),
        ("pass\n", ErrorCode.OCR_FAILED),  # nothing on the standard output
        ("sys.stdout.write('not json\\n')\n", ErrorCode.OCR_FAILED),
        ("sys.stdout.write(json.dumps({'ok': True, 'width': 1, 'height': 2}) + '\\n')\n", ErrorCode.OCR_FAILED),  # a header and no image
        ("sys.stdout.write(json.dumps({'ok': False, 'code': 'E-INPUT-PAGE-RANGE'}) + '\\n')\n", ErrorCode.PAGE_RANGE),
        ("sys.stdout.write(json.dumps({'ok': False, 'code': 'E-NOT-A-CODE'}) + '\\n')\n", ErrorCode.OCR_FAILED),
        ("sys.stdout.write(json.dumps({'ok': False, 'memory': True}) + '\\n')\n", ErrorCode.PARSE_LIMIT),
        (GOOD + "sys.exit(3)\n", ErrorCode.OCR_FAILED),  # a good answer from a worker that then failed is not trusted
    ],
)
def test_a_render_worker_that_fails_or_answers_badly_gives_a_catalogued_error(tmp_path, body, code):
    with pytest.raises(IngestionError) as error:
        sandboxed(stub(tmp_path, body)).render_page(tmp_path / "x.pdf", 1, 100)
    assert error.value.code is code


def test_an_image_over_the_cap_is_a_memory_limit_even_if_the_worker_has_already_exited():
    with pytest.raises(IngestionError) as error:
        SandboxedExtractor._render_result(0, b'{"ok": true, "width": 1, "height": 2}\nPNG', True)
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.MEMORY_DETAIL in str(error.value)


def test_a_render_worker_that_cannot_be_started_is_an_ocr_failure(tmp_path):
    with pytest.raises(IngestionError) as error:
        SandboxedExtractor(LIMITS, command=("/nonexistent/worker",)).render_page(tmp_path / "x.pdf", 1, 100)
    assert error.value.code is ErrorCode.OCR_FAILED


def test_nothing_from_the_worker_reaches_an_error_or_the_terminal(tmp_path, capfd):
    body = "sys.stderr.write('SECRET-TEXT')\nsys.stdout.write('SECRET-OUT\\n')\nsys.exit(1)\n"
    with pytest.raises(IngestionError) as error:
        sandboxed(stub(tmp_path, body)).render_page(tmp_path / "SECRET-NAME.pdf", 1, 100)
    captured = capfd.readouterr()
    assert "SECRET" not in str(error.value) + captured.out + captured.err and str(tmp_path) not in str(error.value)


def test_a_stopped_render_leaves_no_worker_behind(tmp_path):
    pidfile = tmp_path / "pid.txt"
    body = f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\ntime.sleep(60)\n"
    with pytest.raises(IngestionError):
        sandboxed(stub(tmp_path, body), timeout=1).render_page(tmp_path / "x.pdf", 1, 100)
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        import os
        import time

        time.sleep(0.2)
        os.kill(pid, 0)


# --- the engine and the command line use it ----------------------------------------------------------------

TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
TSV = TSV_HEADER + "\n5\t1\t1\t1\t1\t1\t100\t100\t200\t50\t90.0\tTotal"
ENGINE = """#!{python}
import sys
a = sys.argv[1:]
if a == ["--version"]:
    print("tesseract 5.9.9")
elif a == ["--list-langs"]:
    print("List of available languages (1):\\neng")
else:
    sys.stdin.buffer.read()
    print({tsv!r})
"""


@pytest.fixture
def engine_path(tmp_path):
    path = tmp_path / "tesseract-stub"
    path.write_text(ENGINE.format(python=sys.executable, tsv=TSV), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_the_engine_reads_the_same_pages_whether_the_worker_or_this_process_renders(scan, engine_path):
    plain = TesseractExtractor(command=engine_path).ocr_pages(scan, [1, 3], dpi={1: 100, 3: 100}, timeout_seconds=60)
    engine = TesseractExtractor(command=engine_path)
    engine.use_renderer(SandboxedExtractor(LIMITS).render_page)
    assert engine.ocr_pages(scan, [1, 3], dpi={1: 100, 3: 100}, timeout_seconds=60) == plain


def test_the_engine_asks_the_renderer_for_each_page_with_its_own_resolution(scan, engine_path):
    seen = []

    def spy(path, page, dpi, *, timeout_seconds):
        seen.append((page, dpi, timeout_seconds is not None and 0 < timeout_seconds <= 60))
        return in_process(path, page, dpi)

    engine = TesseractExtractor(command=engine_path)
    engine.use_renderer(spy)
    engine.ocr_pages(scan, [3, 1], dpi={1: 100, 3: 72}, timeout_seconds=60)
    assert seen == [(1, 100, True), (3, 72, True)]


def test_a_renderer_can_be_taken_away(scan, engine_path):
    engine = TesseractExtractor(command=engine_path)
    engine.use_renderer(lambda *a, **k: (_ for _ in ()).throw(AssertionError("the worker was used")))
    engine.use_renderer(None)
    assert engine.ocr_pages(scan, [1], dpi={1: 100}, timeout_seconds=60)


def test_the_command_line_gives_the_sandbox_renderer_to_an_engine_that_takes_one(engine_path):
    parser = SandboxedExtractor(LIMITS)
    engine = TesseractExtractor(command=engine_path)
    assert service.ocr_engine(lambda: engine, parser) is engine and engine._renderer == parser.render_page


def test_the_command_line_leaves_an_engine_alone_when_it_or_the_parser_cannot_use_a_renderer(engine_path):
    engine = TesseractExtractor(command=engine_path)
    assert service.ocr_engine(lambda: engine, PdfplumberExtractor()) is engine and engine._renderer is None  # an in-process parser
    fake = FakeOcrExtractor({}, page_count=1)
    assert service.ocr_engine(lambda: fake, SandboxedExtractor(LIMITS)) is fake  # an engine with no such hook


def test_a_render_that_passes_the_parse_budget_stops_the_engine_call_with_the_new_code(scan, engine_path, tmp_path):
    engine = TesseractExtractor(command=engine_path)
    engine.use_renderer(SandboxedExtractor(ParseLimits(1, 4096), command=stub(tmp_path, "time.sleep(60)\n"), poll_seconds=0.05).render_page)
    with pytest.raises(IngestionError) as error:
        engine.ocr_pages(scan, [1], dpi={1: 100}, timeout_seconds=60)
    assert error.value.code is ErrorCode.PARSE_LIMIT


# --- the render operation of the worker itself ------------------------------------------------------------


def run_render(capsysbinary, path, request, memory=4096):
    from credit_intel.ingestion import parse_worker

    code = parse_worker.main(["render_page", str(path), "-", str(memory), json.dumps(request)])
    return code, capsysbinary.readouterr().out


def test_the_worker_writes_a_header_line_then_the_png(capsysbinary, scan):
    code, out = run_render(capsysbinary, scan, {"page": 2, "dpi": 72})
    header, _, png = out.partition(b"\n")
    assert code == 0 and json.loads(header) == {"ok": True, "width": 612.0, "height": 792.0} and png.startswith(b"\x89PNG")


def test_the_worker_reports_a_catalogued_error_by_its_code_alone(capsysbinary, scan):
    code, out = run_render(capsysbinary, scan, {"page": 9, "dpi": 72})
    assert code == 0 and json.loads(out) == {"ok": False, "code": "E-INPUT-PAGE-RANGE"}


def test_the_worker_reports_running_out_of_memory(capsysbinary, scan, monkeypatch):
    import credit_intel.ingestion.tesseract_ocr as engine

    def greedy(*args):
        raise MemoryError

    monkeypatch.setattr(engine, "render_page_png", greedy)
    code, out = run_render(capsysbinary, scan, {"page": 1, "dpi": 72})
    assert code == 0 and json.loads(out) == {"ok": False, "memory": True}


def test_the_worker_render_asks_for_the_address_space_backstop(scan, monkeypatch, capsysbinary):
    from credit_intel.ingestion import parse_worker

    seen = []
    monkeypatch.setattr(parse_worker, "set_address_space_backstop", lambda mb: seen.append(mb) or False)
    run_render(capsysbinary, scan, {"page": 1, "dpi": 72}, memory=777)
    assert seen == [777]
