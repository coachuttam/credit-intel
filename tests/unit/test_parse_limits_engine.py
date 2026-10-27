"""The OCR engine's own memory behind the parse limit (PRD SEC-12 step 3, v0.4.53; B-326).

Stub engines (small Python scripts that behave as the test needs) run through the real adapter and the real supervised run. Synthetic
pages only.
"""

import os
import stat
import sys
import time
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from credit_intel import cli
from credit_intel.config import ParseLimits
from credit_intel.ingestion import sandbox
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.fake_ocr import FakeOcrExtractor
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor
from credit_intel.ingestion.sandbox import SandboxedExtractor
from credit_intel.ingestion.tesseract_ocr import TesseractExtractor
from test_tesseract_ocr import real_engine_available

TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
TSV = TSV_HEADER + "\n5\t1\t1\t1\t1\t1\t100\t100\t200\t50\t90.0\tTotal\n5\t1\t1\t1\t1\t2\t320\t100\t140\t50\t88.5\tassets"
ENGINE = '''#!{python}
import os, subprocess, sys, time
a = sys.argv[1:]
if a == ["--version"]:
    print("tesseract 5.9.9")
    sys.exit(0)
if a == ["--list-langs"]:
    print("List of available languages (1):\\neng")
    sys.exit(0)
data = sys.stdin.buffer.read()
mode = os.environ.get("STUB_MODE", "ok")
if mode == "alloc":
    blocks = [bytearray(1024 * 1024 * 40) for _ in range(5)]
    for b in blocks:
        b[::4096] = b"x" * len(b[::4096])
    time.sleep(60)
elif mode == "flood_exit":
    sys.stdout.write("x" * 8000)  # more than the cap the test sets, but it fits in the pipe, so the engine exits at once
    sys.stdout.flush()
    sys.exit(0)
elif mode == "env":
    print(os.environ.get("PROBE", "absent"))
    sys.exit(0)
elif mode == "sleep":
    time.sleep(600)
elif mode == "flood":
    sys.stdout.write("x" * 200000)
    sys.stdout.flush()
    time.sleep(60)
elif mode == "crash":
    sys.stderr.write("SECRET-DOCUMENT-TEXT")
    sys.exit(2)
elif mode == "child":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    open(os.environ["STUB_PIDS"], "w").write(f"{{os.getpid()}} {{child.pid}}")
    time.sleep(60)
elif mode == "size":
    print({header!r})
    print("5\\t1\\t1\\t1\\t1\\t1\\t0\\t0\\t10\\t10\\t90\\t" + str(len(data)))
    sys.exit(0)
print({tsv!r})
'''
LIMITS = ParseLimits(timeout_seconds=60, memory_mb=4096)


@pytest.fixture
def engine_path(tmp_path):
    path = tmp_path / "tesseract-stub"
    path.write_text(ENGINE.format(python=sys.executable, header=TSV_HEADER, tsv=TSV), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


@pytest.fixture
def scan(tmp_path):
    path = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    pdf.drawImage(ImageReader(Image.new("RGB", (850, 1100), "white")), 0, 0, 612, 792)
    pdf.showPage()
    pdf.save()
    return path


def watched(engine_path, memory=4096, **kw):
    engine = TesseractExtractor(command=engine_path)
    parser = SandboxedExtractor(ParseLimits(60, memory), poll_seconds=0.05, **kw)
    engine.use_runner(parser.run_supervised)
    return engine, parser


def read(engine, scan):
    return engine.ocr_pages(scan, [1], dpi={1: 100}, timeout_seconds=60)


# --- the page read is the same with and without the watch ---------------------------------------------------------


def test_the_page_read_through_the_watch_equals_the_direct_read(engine_path, scan):
    direct = read(TesseractExtractor(command=engine_path), scan)
    engine, _ = watched(engine_path)
    assert read(engine, scan) == direct and direct[0].text == "Total assets"


def test_a_runner_can_be_taken_away(engine_path, scan):
    engine, _ = watched(engine_path)
    engine.use_runner(lambda *a, **k: (_ for _ in ()).throw(AssertionError("the runner was used")))
    engine.use_runner(None)
    assert read(engine, scan)


def test_the_runner_gets_the_command_the_image_the_environment_and_the_remaining_time(engine_path, scan):
    seen = {}

    def spy(command, stdin, *, env, timeout_seconds):
        seen.update(command=command, png=stdin.startswith(b"\x89PNG"), omp=env.get("OMP_THREAD_LIMIT"), time=0 < timeout_seconds <= 60)
        return sandbox.subprocess.CompletedProcess(command, 0, TSV.encode(), b"")

    engine = TesseractExtractor(command=engine_path)
    engine.use_runner(spy)
    read(engine, scan)
    assert seen["command"][:1] == [engine_path] and seen["command"][1:4] == ["stdin", "stdout", "-l"] and seen["png"] and seen["omp"] == "1" and seen["time"]


def test_the_availability_checks_do_not_go_through_the_runner(engine_path, scan):
    engine = TesseractExtractor(command=engine_path)
    engine.use_runner(lambda *a, **k: (_ for _ in ()).throw(AssertionError("a check was run under the watch")))
    assert engine.version == "5.9.9"


def test_a_large_image_on_standard_input_does_not_block_the_engine_or_the_watch(engine_path, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "size")
    parser = SandboxedExtractor(LIMITS, poll_seconds=0.05)
    done = parser.run_supervised([engine_path, "stdin", "stdout"], b"x" * 8_000_000, env=dict(os.environ), timeout_seconds=30)
    assert done.returncode == 0 and b"8000000" in done.stdout


# --- the limits ---------------------------------------------------------------------------------------------------


def test_an_engine_that_passes_the_memory_limit_is_stopped_with_the_new_code(engine_path, scan, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "alloc")
    engine, _ = watched(engine_path, memory=120)
    started = time.monotonic()
    with pytest.raises(IngestionError) as error:
        read(engine, scan)
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.MEMORY_DETAIL in str(error.value) and time.monotonic() - started < 30


def test_an_engine_that_passes_the_ocr_time_is_an_ocr_failure_not_a_parse_limit(engine_path, scan, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "sleep")
    engine, _ = watched(engine_path)
    with pytest.raises(IngestionError) as error:
        engine.ocr_pages(scan, [1], dpi={1: 100}, timeout_seconds=1)
    assert error.value.code is ErrorCode.OCR_FAILED


def test_the_engine_is_not_held_to_the_parse_time_budget(engine_path):
    parser = SandboxedExtractor(ParseLimits(1, 4096), poll_seconds=0.05)
    parser._deadline = parser._clock() - 100  # the parse budget has long run out
    done = parser.run_supervised([engine_path, "stdin", "stdout"], b"x", env=dict(os.environ), timeout_seconds=30)
    assert done.returncode == 0 and TSV.encode() in done.stdout


def test_output_far_larger_than_a_page_of_text_is_a_memory_limit(engine_path, scan, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "flood")
    monkeypatch.setattr(sandbox, "MAX_ENGINE_OUTPUT_BYTES", 1000)
    engine, _ = watched(engine_path)
    with pytest.raises(IngestionError) as error:
        read(engine, scan)
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.MEMORY_DETAIL in str(error.value)


def test_output_over_the_cap_is_caught_even_if_the_engine_exits_before_the_next_poll(engine_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MAX_ENGINE_OUTPUT_BYTES", 1000)
    parser = SandboxedExtractor(LIMITS, poll_seconds=0.6)  # the engine is done before the watch looks again
    with pytest.raises(IngestionError) as error:
        parser.run_supervised([engine_path, "stdin", "stdout"], b"x", env={**os.environ, "STUB_MODE": "flood_exit"}, timeout_seconds=30)
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.MEMORY_DETAIL in str(error.value)


def test_the_environment_given_to_the_runner_is_the_environment_of_the_engine(engine_path):
    assert "PROBE" not in os.environ
    done = SandboxedExtractor(LIMITS, poll_seconds=0.05).run_supervised(
        [engine_path, "stdin", "stdout"], b"x", env={**os.environ, "STUB_MODE": "env", "PROBE": "yes"}, timeout_seconds=30)
    assert done.stdout.strip() == b"yes"


def test_an_engine_that_crashes_is_an_ocr_failure_and_nothing_it_wrote_escapes(engine_path, scan, monkeypatch, capfd):
    monkeypatch.setenv("STUB_MODE", "crash")
    engine, _ = watched(engine_path)
    with pytest.raises(IngestionError) as error:
        read(engine, scan)
    captured = capfd.readouterr()
    assert error.value.code is ErrorCode.OCR_FAILED and "SECRET" not in str(error.value) + captured.out + captured.err
    assert str(scan) not in str(error.value)


def test_a_stopped_engine_and_its_children_are_gone(engine_path, scan, tmp_path, monkeypatch):
    pids = tmp_path / "pids.txt"
    monkeypatch.setenv("STUB_MODE", "child")
    monkeypatch.setenv("STUB_PIDS", str(pids))
    engine, _ = watched(engine_path)
    with pytest.raises(IngestionError):
        engine.ocr_pages(scan, [1], dpi={1: 100}, timeout_seconds=1.5)
    engine_pid, child_pid = (int(n) for n in pids.read_text().split())
    time.sleep(0.3)
    for pid in (engine_pid, child_pid):
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_a_command_that_cannot_be_started_is_reported_as_the_engine_being_unavailable(tmp_path):
    parser = SandboxedExtractor(LIMITS)
    with pytest.raises(IngestionError) as missing:
        parser.run_supervised(["/nonexistent/engine"], b"", env=dict(os.environ), timeout_seconds=5)
    assert missing.value.code is ErrorCode.OCR_UNAVAILABLE
    not_executable = tmp_path / "plain.txt"
    not_executable.write_text("x", encoding="utf-8")
    with pytest.raises(IngestionError) as denied:
        parser.run_supervised([str(not_executable)], b"", env=dict(os.environ), timeout_seconds=5)
    assert denied.value.code is ErrorCode.OCR_UNAVAILABLE


def test_an_engine_that_exits_before_reading_its_input_does_not_hang_the_run(tmp_path):
    quick = tmp_path / "quick.py"
    quick.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    parser = SandboxedExtractor(LIMITS, poll_seconds=0.05)
    done = parser.run_supervised([sys.executable, str(quick)], b"x" * 8_000_000, env=dict(os.environ), timeout_seconds=30)
    assert done.returncode == 0 and done.stdout == b""


def test_no_scratch_file_is_written_for_the_engine(engine_path, scan):
    import tempfile

    before = {p.name for p in Path(tempfile.gettempdir()).iterdir()}
    engine, _ = watched(engine_path)
    read(engine, scan)
    assert {p.name for p in Path(tempfile.gettempdir()).iterdir()} == before


# --- the command line gives the engine the watch -----------------------------------------------------------------


def test_the_command_line_hands_both_hooks_to_an_engine_that_takes_them(engine_path):
    parser = SandboxedExtractor(LIMITS)
    engine = TesseractExtractor(command=engine_path)
    assert cli._ocr_engine(lambda: engine, parser) is engine
    assert engine._renderer == parser.render_page and engine._runner == parser.run_supervised


def test_the_command_line_leaves_an_engine_alone_when_the_parser_or_the_engine_cannot_use_them(engine_path):
    engine = TesseractExtractor(command=engine_path)
    assert cli._ocr_engine(lambda: engine, PdfplumberExtractor()) is engine and engine._runner is None and engine._renderer is None
    fake = FakeOcrExtractor({}, page_count=1)
    assert cli._ocr_engine(lambda: fake, SandboxedExtractor(LIMITS)) is fake


@pytest.mark.real_ocr
@pytest.mark.skipif(not real_engine_available(), reason="needs Tesseract installed and CREDIT_INTEL_REAL_OCR=1")
def test_the_real_engine_reads_the_same_page_with_and_without_the_watch(tmp_path):
    from PIL import ImageDraw

    page = Image.new("L", (1700, 400), 255)
    ImageDraw.Draw(page).text((100, 100), "Total assets 1,740.00", fill=0)
    scan = tmp_path / "real.pdf"
    pdf = canvas.Canvas(str(scan), pagesize=(612, 144), invariant=1)
    pdf.drawImage(ImageReader(page), 0, 0, 612, 144)
    pdf.showPage()
    pdf.save()
    direct = TesseractExtractor().ocr_pages(scan, [1], dpi={1: 200}, timeout_seconds=60)
    engine = TesseractExtractor()
    engine.use_runner(SandboxedExtractor(LIMITS).run_supervised)
    assert engine.ocr_pages(scan, [1], dpi={1: 200}, timeout_seconds=60) == direct
