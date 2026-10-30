"""The parse limits and the worker process (PRD SEC-12, OD-6 option (b), FR-001 criterion 10, v0.4.50; B-324).

Synthetic PDFs and stub worker scripts only. A stub is a Python file that takes the worker's arguments (operation, pdf, output file,
memory) and behaves as the test needs; the real worker is run on generated PDFs and compared with the in-process extractor.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

from conftest import write_pdf
from credit_intel.config import ENV_PARSE_MEMORY, ENV_PARSE_TIMEOUT, ParseLimits, load_parse_limits
from credit_intel.ingestion import parse_worker, sandbox
from credit_intel.ingestion.errors import CATALOGUE, ErrorCode, IngestionError, exit_code
from credit_intel.ingestion.models import PageImageCoverage, PageText, PageWords, PdfInspection, Word
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor
from credit_intel.ingestion.sandbox import SandboxedExtractor

LIMITS = ParseLimits(timeout_seconds=60, memory_mb=2048)
TEXT = ["Balance Sheet as at 31 March 2025\nTotal assets 1,740.00\nBorrowings 300.00", "", "Profit before tax 352.70\nFinance costs 38.50"]


# --- the settings ----------------------------------------------------------------------------------------


def settings_file(tmp_path, body):
    path = tmp_path / "settings.toml"
    path.write_text(body, encoding="utf-8")
    return path


def fails(path, env=None):
    with pytest.raises(IngestionError) as error:
        load_parse_limits(path, env or {})
    assert error.value.code is ErrorCode.CONFIG_INVALID
    return error.value.detail


def test_both_limits_are_read_from_the_file(tmp_path):
    path = settings_file(tmp_path, "[ingestion]\nparse_timeout_seconds = 90.5\nparse_memory_mb = 3000\n")
    assert load_parse_limits(path, {}) == ParseLimits(90.5, 3000)


def test_the_environment_overrides_the_file(tmp_path):
    path = settings_file(tmp_path, "[ingestion]\nparse_timeout_seconds = 90\nparse_memory_mb = 3000\n")
    assert load_parse_limits(path, {ENV_PARSE_TIMEOUT: "12.5", ENV_PARSE_MEMORY: "512"}) == ParseLimits(12.5, 512)


def test_the_environment_alone_is_enough(tmp_path):
    assert load_parse_limits(settings_file(tmp_path, ""), {ENV_PARSE_TIMEOUT: "5", ENV_PARSE_MEMORY: "100"}) == ParseLimits(5, 100)


def test_there_is_no_default_for_either_limit(tmp_path):
    assert fails(settings_file(tmp_path, "")) == "ingestion.parse_timeout_seconds"
    assert fails(settings_file(tmp_path, "[ingestion]\nparse_timeout_seconds = 5\n")) == "ingestion.parse_memory_mb"
    assert fails(settings_file(tmp_path, "[ingestion]\nparse_memory_mb = 5\n")) == "ingestion.parse_timeout_seconds"


@pytest.mark.parametrize("value", ["0", "-5", '"ten"', "true", "100000", "[1]"])
def test_an_invalid_timeout_in_the_file_is_refused_by_name(tmp_path, value):
    assert fails(settings_file(tmp_path, f"[ingestion]\nparse_timeout_seconds = {value}\nparse_memory_mb = 100\n")) == "ingestion.parse_timeout_seconds"


@pytest.mark.parametrize("value", ["0", "-5", "1.5", '"big"', "true"])
def test_an_invalid_memory_limit_in_the_file_is_refused_by_name(tmp_path, value):
    assert fails(settings_file(tmp_path, f"[ingestion]\nparse_timeout_seconds = 5\nparse_memory_mb = {value}\n")) == "ingestion.parse_memory_mb"


@pytest.mark.parametrize("value", ["", "abc", "-1", "1e3", "0x10", " 5"])
def test_an_invalid_environment_value_is_refused_by_name_and_never_repeated(tmp_path, value):
    path = settings_file(tmp_path, "[ingestion]\nparse_timeout_seconds = 5\nparse_memory_mb = 100\n")
    assert fails(path, {ENV_PARSE_TIMEOUT: value}) == "ingestion.parse_timeout_seconds"
    assert fails(path, {ENV_PARSE_MEMORY: value}) == "ingestion.parse_memory_mb"


def test_an_unknown_ingestion_setting_is_refused_by_name(tmp_path):
    assert fails(settings_file(tmp_path, "[ingestion]\nparse_timeout_seconds = 5\nparse_memory_mb = 1\nmax_pages = 5\n")) == "ingestion.max_pages"


def test_a_settings_file_that_cannot_be_read_is_refused(tmp_path):
    assert fails(tmp_path / "absent.toml") == "settings file"


def test_the_repository_settings_file_holds_the_owners_two_limits():
    repo = Path(__file__).resolve().parents[2] / "config" / "settings.toml"
    assert load_parse_limits(repo, {}) == ParseLimits(timeout_seconds=700, memory_mb=6144)  # set by the owner on 2026-10-27 (first 300 / 4096)


# --- the catalogued error ----------------------------------------------------------------------------------


def test_the_new_code_is_an_input_error_with_exit_3_and_a_fixed_message():
    entry = CATALOGUE[ErrorCode.PARSE_LIMIT]
    assert ErrorCode.PARSE_LIMIT.value == "E-INPUT-PARSE-LIMIT" and entry.exit_code == 3 and entry.retried == "No"
    assert exit_code(IngestionError(ErrorCode.PARSE_LIMIT, detail=sandbox.TIME_DETAIL)) == 3
    assert "ingestion.parse_timeout_seconds" in sandbox.TIME_DETAIL and "ingestion.parse_memory_mb" in sandbox.MEMORY_DETAIL


# --- the real worker equals the in-process parse -------------------------------------------------------------


@pytest.fixture
def pdf(tmp_path):
    return write_pdf(tmp_path / "a.pdf", TEXT, draw_shapes=True, page_labels=[(0, "roman-lower", 1)])


def test_the_worker_returns_what_the_in_process_extractor_returns(pdf):
    inside, outside = PdfplumberExtractor(), SandboxedExtractor(LIMITS)
    assert outside.inspect(pdf) == inside.inspect(pdf)
    assert outside.extract_pages(pdf) == inside.extract_pages(pdf)
    assert outside.extract_words(pdf, [3, 1]) == inside.extract_words(pdf, [3, 1])
    assert outside.image_coverage(pdf) == inside.image_coverage(pdf)


def test_the_worker_result_has_the_same_types_not_just_equal_dicts(pdf):
    outside = SandboxedExtractor(LIMITS)
    assert isinstance(outside.inspect(pdf), PdfInspection)
    assert all(isinstance(p, PageText) for p in outside.extract_pages(pdf))
    words = outside.extract_words(pdf, [1])
    assert isinstance(words[0], PageWords) and isinstance(words[0].words[0], Word) and isinstance(words[0].words, tuple)
    assert all(isinstance(c, PageImageCoverage) for c in outside.image_coverage(pdf))


def test_a_catalogued_failure_in_the_worker_is_raised_with_its_own_code(tmp_path):
    outside = SandboxedExtractor(LIMITS)
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"%PDF-1.4\nthis is not a pdf at all\n")
    with pytest.raises(IngestionError) as corrupt:
        outside.inspect(junk)
    assert corrupt.value.code is ErrorCode.CORRUPT
    with pytest.raises(IngestionError) as page_range:
        outside.extract_words(write_pdf(tmp_path / "b.pdf", TEXT), [9])
    assert page_range.value.code is ErrorCode.PAGE_RANGE


def test_an_encrypted_pdf_is_reported_as_the_in_process_extractor_reports_it(tmp_path):
    from reportlab.lib.pdfencrypt import StandardEncryption

    locked = write_pdf(tmp_path / "locked.pdf", TEXT, encrypt=StandardEncryption("user", "owner"))
    codes = []
    for extractor in (PdfplumberExtractor(), SandboxedExtractor(LIMITS)):
        try:
            result = extractor.inspect(locked)
            codes.append(("inspected", result.is_encrypted))
        except IngestionError as error:
            codes.append(error.code)
    assert codes[0] == codes[1] and codes[0] in (ErrorCode.ENCRYPTED, ("inspected", True))


def test_validation_and_ingestion_work_through_the_sandbox(pdf):
    from credit_intel.ingestion.ingest import ingest

    inside, outside = ingest(pdf), ingest(pdf, extractor=SandboxedExtractor(LIMITS))
    assert inside == outside


def test_the_json_round_trip_is_exact_for_every_operation(pdf):
    inside = PdfplumberExtractor()
    for operation, result in (
        ("inspect", inside.inspect(pdf)), ("extract_pages", inside.extract_pages(pdf)),
        ("extract_words", inside.extract_words(pdf, [1, 3])), ("image_coverage", inside.image_coverage(pdf)),
    ):  # fmt: skip
        again = parse_worker.from_jsonable(operation, json.loads(json.dumps(parse_worker.to_jsonable(operation, result))))
        assert again == result


# --- a stub worker: time, memory, crashes ----------------------------------------------------------------


def stub(tmp_path, body):
    path = tmp_path / "stub.py"
    path.write_text("import json, os, sys, time\nop, pdf, out = sys.argv[1:4]\n" + body, encoding="utf-8")
    return (sys.executable, str(path))


def sandboxed(command, timeout=60, memory=2048, **kw):
    return SandboxedExtractor(ParseLimits(timeout, memory), command=command, poll_seconds=0.05, **kw)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        return os.waitpid(pid, os.WNOHANG) == (0, 0)  # a zombie is dead but still listed
    except ChildProcessError:
        return True


def test_a_worker_that_runs_past_the_time_limit_is_stopped_with_the_time_message(tmp_path):
    started = time.monotonic()
    extractor = sandboxed(stub(tmp_path, "time.sleep(60)\n"), timeout=1)
    with pytest.raises(IngestionError) as error:
        extractor.inspect(tmp_path / "x.pdf")
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.TIME_DETAIL in str(error.value)
    assert time.monotonic() - started < 10


def test_a_worker_that_passes_the_memory_limit_is_stopped_with_the_memory_message(tmp_path):
    body = "blocks = [bytearray(1024 * 1024 * 40) for _ in range(5)]\nfor b in blocks: b[::4096] = b'x' * len(b[::4096])\ntime.sleep(60)\n"
    started = time.monotonic()
    extractor = sandboxed(stub(tmp_path, body), memory=120)
    with pytest.raises(IngestionError) as error:
        extractor.inspect(tmp_path / "x.pdf")
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.MEMORY_DETAIL in str(error.value)
    assert time.monotonic() - started < 30


def test_a_generated_decompression_bomb_is_stopped_by_the_limit_not_by_the_test_run(tmp_path):
    """A small file whose compressed stream expands to hundreds of MB when read; a small limit keeps the test safe."""
    import zlib

    expanded = zlib.compress(b"A" * (400 * 1024 * 1024), 9)  # a few hundred KB
    assert len(expanded) < 1024 * 1024
    bomb = tmp_path / "bomb.bin"
    bomb.write_bytes(expanded)
    body = f"import zlib\ndata = zlib.decompress(open({str(bomb)!r}, 'rb').read())\ntime.sleep(60)\n"
    extractor = sandboxed(stub(tmp_path, body), memory=150)
    with pytest.raises(IngestionError) as error:
        extractor.extract_pages(tmp_path / "x.pdf")
    assert error.value.code is ErrorCode.PARSE_LIMIT


def test_the_stopped_worker_and_its_children_are_gone(tmp_path):
    pids = tmp_path / "pids.txt"
    body = (
        "import subprocess\n"
        f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pids)!r}, 'w').write(f'{{os.getpid()}} {{child.pid}}')\n"
        "time.sleep(60)\n"
    )
    with pytest.raises(IngestionError):
        sandboxed(stub(tmp_path, body), timeout=1.5).inspect(tmp_path / "x.pdf")
    worker, child = (int(n) for n in pids.read_text().split())
    time.sleep(0.2)
    assert not alive(worker) and not alive(child)


def test_one_time_budget_covers_all_operations_of_a_run(tmp_path):
    now = [0.0]
    ok = stub(tmp_path, "json.dump({'ok': True, 'result': {'page_count': 1, 'is_encrypted': False}}, open(out, 'w'))\n")
    extractor = SandboxedExtractor(ParseLimits(10, 2048), command=ok, clock=lambda: now[0], poll_seconds=0.01)
    assert extractor.inspect(tmp_path / "x.pdf") == PdfInspection(1, False)  # the first operation starts the budget
    now[0] = 9.9
    assert extractor.inspect(tmp_path / "x.pdf") == PdfInspection(1, False)  # still inside it
    now[0] = 10.0
    with pytest.raises(IngestionError) as error:
        extractor.inspect(tmp_path / "x.pdf")  # the budget is spent: no worker is started
    assert error.value.code is ErrorCode.PARSE_LIMIT and sandbox.TIME_DETAIL in str(error.value)


def test_a_spent_budget_starts_no_worker(tmp_path):
    now = [0.0]
    extractor = SandboxedExtractor(ParseLimits(1, 2048), command=("/nonexistent/worker",), clock=lambda: now[0])
    extractor._deadline = 0.5  # the budget was started earlier and has run out
    now[0] = 1.0
    with pytest.raises(IngestionError) as error:
        extractor.extract_pages(tmp_path / "x.pdf")
    assert error.value.code is ErrorCode.PARSE_LIMIT  # not E-INPUT-CORRUPT: no process was attempted


@pytest.mark.parametrize(
    "body, code",
    [
        ("sys.exit(1)\n", ErrorCode.CORRUPT),
        ("os.kill(os.getpid(), 9)\n", ErrorCode.CORRUPT),
        ("open(out, 'w').write('not json')\n", ErrorCode.CORRUPT),
        ("pass\n", ErrorCode.CORRUPT),  # exits cleanly with no output
        ("json.dump({'ok': True, 'result': 'wrong shape'}, open(out, 'w'))\n", ErrorCode.CORRUPT),
        ("json.dump({'ok': False, 'code': 'E-NOT-A-CODE'}, open(out, 'w'))\n", ErrorCode.CORRUPT),
        ("json.dump({'ok': False, 'code': 'E-INPUT-ENCRYPTED'}, open(out, 'w'))\n", ErrorCode.ENCRYPTED),
        ("json.dump({'ok': False, 'code': 'E-INPUT-PAGE-RANGE'}, open(out, 'w'))\n", ErrorCode.PAGE_RANGE),
        ("json.dump({'ok': False, 'memory': True}, open(out, 'w'))\n", ErrorCode.PARSE_LIMIT),
    ],
)
def test_a_worker_that_fails_or_answers_badly_gives_a_catalogued_error(tmp_path, body, code):
    with pytest.raises(IngestionError) as error:
        sandboxed(stub(tmp_path, body)).inspect(tmp_path / "x.pdf")
    assert error.value.code is code


def test_a_worker_that_exits_with_an_error_after_writing_a_result_is_not_trusted(tmp_path):
    body = "json.dump({'ok': True, 'result': {'page_count': 1, 'is_encrypted': False}}, open(out, 'w'))\nsys.exit(3)\n"
    with pytest.raises(IngestionError) as error:
        sandboxed(stub(tmp_path, body)).inspect(tmp_path / "x.pdf")
    assert error.value.code is ErrorCode.CORRUPT


def test_what_a_worker_writes_to_its_error_stream_never_reaches_this_process(tmp_path, capfd):
    body = "sys.stderr.write('SECRET-DOCUMENT-TEXT')\nsys.stdout.write('SECRET-OUT')\njson.dump({'ok': True, 'result': {'page_count': 1, 'is_encrypted': False}}, open(out, 'w'))\n"
    sandboxed(stub(tmp_path, body)).inspect(tmp_path / "x.pdf")
    captured = capfd.readouterr()
    assert "SECRET" not in captured.out and "SECRET" not in captured.err


def test_a_worker_that_cannot_be_started_is_a_corrupt_input_not_a_crash(tmp_path):
    with pytest.raises(IngestionError) as error:
        SandboxedExtractor(LIMITS, command=("/nonexistent/worker",)).inspect(tmp_path / "x.pdf")
    assert error.value.code is ErrorCode.CORRUPT


def test_no_document_text_or_path_is_in_any_error(tmp_path):
    secret = tmp_path / "SECRET-NAME.pdf"
    for body in ("time.sleep(60)\n", "sys.exit(1)\n", "json.dump({'ok': False, 'code': 'E-INPUT-ENCRYPTED', 'detail': 'SECRET-TEXT'}, open(out, 'w'))\n"):
        with pytest.raises(IngestionError) as error:
            sandboxed(stub(tmp_path, body), timeout=0.5).inspect(secret)
        assert "SECRET" not in str(error.value) and str(tmp_path) not in str(error.value)


def test_no_scratch_file_is_left_behind(tmp_path):
    before = set(Path(tempfile.gettempdir()).glob("credit-intel-parse-*"))
    for body in ("time.sleep(60)\n", "json.dump({'ok': True, 'result': {'page_count': 1, 'is_encrypted': False}}, open(out, 'w'))\n"):
        try:
            sandboxed(stub(tmp_path, body), timeout=0.5).inspect(tmp_path / "x.pdf")
        except IngestionError:
            pass
    assert set(Path(tempfile.gettempdir()).glob("credit-intel-parse-*")) == before


def test_the_worker_is_given_the_path_and_memory_as_arguments_not_through_a_shell(tmp_path):
    seen = tmp_path / "args.json"
    body = f"json.dump(sys.argv[1:], open({str(seen)!r}, 'w'))\njson.dump({{'ok': True, 'result': {{'page_count': 1, 'is_encrypted': False}}}}, open(out, 'w'))\n"
    odd = tmp_path / "a b; echo hi.pdf"
    sandboxed(stub(tmp_path, body), memory=777).inspect(odd)
    args = json.loads(seen.read_text())
    assert args[0] == "inspect" and args[1] == str(odd) and args[3] == "777"


def test_a_worker_whose_memory_cannot_be_read_is_stopped_with_the_parse_limit_code_and_not_left_unwatched(tmp_path):
    """Fail closed (Phase 7 step 1, F-4): before, a reader that returned nothing meant the memory limit silently never applied."""
    slow = stub(tmp_path, "time.sleep(30)\n")
    with pytest.raises(IngestionError) as error:
        sandboxed(slow, memory_reader=lambda pid: None).inspect(tmp_path / "x.pdf")
    assert error.value.code is ErrorCode.PARSE_LIMIT and "memory could not be measured" in str(error.value)


def test_only_consecutive_unreadable_checks_stop_a_worker_a_good_reading_resets_the_count(tmp_path):
    ok = stub(tmp_path, "time.sleep(0.6)\njson.dump({'ok': True, 'result': {'page_count': 1, 'is_encrypted': False}}, open(out, 'w'))\n")
    pattern = iter([None, None, 1.0] * 100)  # never three in a row
    assert sandboxed(ok, memory_reader=lambda pid: next(pattern)).inspect(tmp_path / "x.pdf") == PdfInspection(1, False)


def test_the_resident_memory_of_this_process_is_readable_and_a_missing_one_is_none():
    assert sandbox.resident_mb(os.getpid()) > 1
    assert sandbox.resident_mb(2**22 + 12345) is None


# --- the Linux backstop ----------------------------------------------------------------------------------


def test_the_address_space_backstop_is_set_on_linux_only():
    seen = []
    assert parse_worker.set_address_space_backstop(512, "linux", seen.append) is True
    assert seen == [parse_worker.BACKSTOP_FACTOR * 512 * 1024 * 1024]
    seen.clear()
    assert parse_worker.set_address_space_backstop(512, "darwin", seen.append) is False and seen == []


def test_a_backstop_the_system_refuses_is_not_an_error():
    def refuse(limit):
        raise ValueError("current limit exceeds maximum limit")

    assert parse_worker.set_address_space_backstop(512, "linux", refuse) is False


def test_the_worker_rejects_an_unknown_operation_and_missing_arguments(tmp_path):
    assert parse_worker.main(["nonsense", "a.pdf", str(tmp_path / "o.json")]) == 2
    assert parse_worker.main(["inspect"]) == 2


def test_the_worker_module_never_imports_the_pdf_library_at_import_time():
    import subprocess

    done = subprocess.run([sys.executable, "-I", "-c", "import credit_intel.ingestion.sandbox, sys; print('pdfplumber' in sys.modules)"],
                          capture_output=True, text=True, check=True)  # fmt: skip
    assert done.stdout.strip() == "False"
