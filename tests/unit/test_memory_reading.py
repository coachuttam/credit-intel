"""Reading a worker's memory without needing ``ps``, and refusing a host where it cannot be read (PRD SEC-12; Phase 7 step 1, finding F-4)."""

import io
import os
import subprocess
from pathlib import Path

import pytest

from credit_intel.api import __main__ as launcher
from credit_intel.ingestion import sandbox
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.sandbox import _proc_rss, check_memory_measurement, resident_mb


def fake_proc(tmp_path, pid, text):
    folder = tmp_path / "proc" / str(pid)
    folder.mkdir(parents=True)
    (folder / "status").write_text(text, encoding="utf-8")
    return tmp_path / "proc"


STATUS = "Name:\tpython\nVmPeak:\t  999999 kB\nVmRSS:\t  204800 kB\nThreads:\t1\n"


def test_the_resident_size_comes_from_the_vmrss_line_in_kilobytes(tmp_path):
    assert _proc_rss(4242, fake_proc(tmp_path, 4242, STATUS)) == 200.0
    assert _proc_rss(7, fake_proc(tmp_path, 7, "VmRSS:\t 1024 kB\n")) == 1.0


@pytest.mark.parametrize("text", ["", "Name:\tkthreadd\n", "VmRSS:\n", "VmRSS:\tmany kB\n", "VmRSS:\t-\n", "\x00\x01 garbage"])
def test_a_status_without_a_readable_vmrss_line_is_none(tmp_path, text):
    assert _proc_rss(9, fake_proc(tmp_path, 9, text)) is None


def test_a_process_that_has_gone_is_none(tmp_path):
    assert _proc_rss(31337, tmp_path / "proc") is None


def never(*args, **kwargs):
    raise AssertionError("ps must not be run")


def test_on_linux_it_reads_proc_and_does_not_run_ps(tmp_path):
    assert resident_mb(4242, platform="linux", proc=fake_proc(tmp_path, 4242, STATUS), run=never) == 200.0
    assert resident_mb(1, platform="linux2", proc=tmp_path / "nowhere", run=never) is None


def completed(stdout):
    return lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


def test_elsewhere_it_asks_ps_and_a_missing_ps_or_an_empty_answer_is_none(tmp_path):
    assert resident_mb(5, platform="darwin", run=completed("2048\n"), proc=tmp_path / "unused") == 2.0
    assert resident_mb(5, platform="darwin", run=completed("")) is None
    assert resident_mb(5, platform="darwin", run=completed("not a number")) is None

    def absent(*args, **kwargs):
        raise FileNotFoundError("ps")

    assert resident_mb(5, platform="darwin", run=absent) is None

    def hangs(*args, **kwargs):
        raise subprocess.TimeoutExpired("ps", 5)

    assert resident_mb(5, platform="freebsd", run=hangs) is None


def test_this_host_can_measure_its_own_process():
    assert resident_mb(os.getpid()) > 1


def test_the_startup_check_passes_when_the_process_can_be_read_and_refuses_when_it_cannot():
    check_memory_measurement(lambda pid: 123.0)
    seen = []
    with pytest.raises(IngestionError) as error:
        check_memory_measurement(lambda pid: seen.append(pid))
    assert seen == [os.getpid()] and error.value.code is ErrorCode.CONFIG_INVALID and "resident memory cannot be measured" in str(error.value)
    check_memory_measurement()  # the real reader, on the machine the tests run on


def test_the_launcher_does_not_start_on_a_host_that_cannot_be_measured_and_does_not_read_the_settings_first(tmp_path):
    def refuses():
        check_memory_measurement(lambda pid: None)

    served, err = [], io.StringIO()
    code = launcher.main(["--config", str(tmp_path / "does-not-exist.toml")], env={}, stderr=err, serve=lambda *a: served.append(a), check_memory=refuses)
    assert code == 6 and served == [] and "E-CONFIG-INVALID" in err.getvalue() and "resident memory" in err.getvalue()
    assert Path(sandbox.__file__).name == "sandbox.py"
