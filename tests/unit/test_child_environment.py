"""The environment of the processes that read a document (PRD SEC-02, SEC-06; Phase 7 step 1, finding F-1).

Each child process that parses bytes from outside is started with only the variables on a fixed list. A secret in the parent's environment must not reach
any of them: the parse worker, the page-render worker, Tesseract (directly and under the memory watch) and the report worker.
"""

import json
import os
import stat
import sys

import pytest

from credit_intel.config import ParseLimits
from credit_intel.ingestion import child_env
from credit_intel.ingestion.child_env import ALLOWED, child_environment
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.sandbox import SandboxedExtractor
from credit_intel.ingestion.tesseract_ocr import TesseractExtractor, _ENVIRONMENT
from credit_intel.report import make_report

SECRETS = {
    "OPENAI_API_KEY": "sk-test-NOT-A-REAL-KEY-12345", "CREDIT_INTEL_API_TOKEN": "t" * 40, "TYPESAFE_API_KEY": "jev-secret", "AWS_SECRET_ACCESS_KEY": "aws-secret",
    "HTTPS_PROXY": "http://proxy.example:3128", "GITHUB_TOKEN": "ghp_secret", "DATABASE_URL": "postgres://u:p@h/d", "PATH_SECRET": "x", "LC_SECRET": "x", "PYTHON_SECRET": "x",
    "CREDIT_INTEL_TOKEN_CEILING": "30000",
}  # fmt: skip


@pytest.fixture
def secrets(monkeypatch):
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)
    return SECRETS


ADDED_BY_THE_SYSTEM = {"__CF_USER_TEXT_ENCODING"}  # macOS puts this into every process it starts; it is not ours and carries no secret


def assert_clean(names):
    names = set(names) - ADDED_BY_THE_SYSTEM
    assert not names & set(SECRETS), sorted(names & set(SECRETS))
    assert names <= set(ALLOWED), sorted(names - set(ALLOWED))


# --- the function ------------------------------------------------------------------------------------------------------------------------------


def test_only_the_listed_variables_are_copied_and_nothing_is_allowed_by_pattern():
    source = {**SECRETS, "PATH": "/usr/bin", "LANG": "C.UTF-8", "TESSDATA_PREFIX": "/data", "PYTHONPATH": "/app/src", "HOME": "/home/u"}
    result = child_environment(source)
    assert result == {"PATH": "/usr/bin", "LANG": "C.UTF-8", "TESSDATA_PREFIX": "/data", "PYTHONPATH": "/app/src", "HOME": "/home/u"}
    assert child_environment({}) == {} and source["PATH"] == "/usr/bin"  # the source is not changed


def test_the_list_holds_no_credential_proxy_or_pattern():
    assert len(set(ALLOWED)) == len(ALLOWED)
    for name in ALLOWED:
        assert name.isupper() and not any(word in name for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PROXY", "CREDENTIAL", "AUTH")), name
    assert {"OPENAI_API_KEY", "CREDIT_INTEL_API_TOKEN"}.isdisjoint(ALLOWED)


def test_overrides_are_set_on_top_and_are_the_callers_own_values():
    assert child_environment({"PATH": "/p", "OMP_THREAD_LIMIT": "8"}, {"OMP_THREAD_LIMIT": "1", "FIXED": "yes"}) == {"PATH": "/p", "OMP_THREAD_LIMIT": "1", "FIXED": "yes"}


def test_the_process_environment_is_the_default_source(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("LANG", "xx")
    assert child_environment()["LANG"] == "xx" and "OPENAI_API_KEY" not in child_environment()
    assert child_env.os is os


# --- every place that starts a child ---------------------------------------------------------------------------------------------------------------


def worker_stub(tmp_path, dump):
    path = tmp_path / "worker.py"
    path.write_text(f"import json, os, sys\nop, pdf, out = sys.argv[1:4]\njson.dump(sorted(os.environ), open({str(dump)!r}, 'w'))\n"
                    "json.dump({'ok': True, 'result': {'page_count': 1, 'is_encrypted': False}}, open(out, 'w')) if out != '-' else None\n", encoding="utf-8")  # fmt: skip
    return (sys.executable, str(path))


def test_the_parse_worker_gets_no_secret(tmp_path, secrets):
    dump = tmp_path / "env.json"
    SandboxedExtractor(ParseLimits(60, 2048), command=worker_stub(tmp_path, dump), poll_seconds=0.05).inspect(tmp_path / "x.pdf")
    names = json.loads(dump.read_text(encoding="utf-8"))
    assert_clean(names)
    assert "PATH" in names  # what it needs is there


def test_the_page_render_worker_gets_no_secret(tmp_path, secrets):
    dump = tmp_path / "env.json"
    with pytest.raises(IngestionError):  # the stub is not a renderer; the result is not the point
        SandboxedExtractor(ParseLimits(60, 2048), command=worker_stub(tmp_path, dump), poll_seconds=0.05).render_page(tmp_path / "x.pdf", 1, 100)
    assert_clean(json.loads(dump.read_text(encoding="utf-8")))


def test_a_supervised_engine_gets_no_secret_even_if_the_caller_hands_over_the_whole_environment(tmp_path, secrets):
    code = "import os, json; print(json.dumps(sorted(os.environ)))"
    done = SandboxedExtractor(ParseLimits(60, 2048), poll_seconds=0.05).run_supervised([sys.executable, "-c", code], b"", env=dict(os.environ), timeout_seconds=30)
    assert_clean(json.loads(done.stdout))
    done = SandboxedExtractor(ParseLimits(60, 2048), poll_seconds=0.05).run_supervised([sys.executable, "-c", code], b"", timeout_seconds=30)  # and with no environment given
    assert_clean(json.loads(done.stdout))


def engine_script(tmp_path):
    script = tmp_path / "engine"
    script.write_text(f"#!{sys.executable}\nimport os, json\nprint(json.dumps(sorted(os.environ)))\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_tesseract_started_directly_gets_no_secret_and_its_one_thread_setting(tmp_path, secrets):
    engine = TesseractExtractor(command=str(engine_script(tmp_path)))
    names = json.loads(engine._run(["--version"], timeout=30).stdout)
    assert_clean(names) and "OMP_THREAD_LIMIT" in names


def test_tesseract_under_the_memory_watch_is_handed_no_secret(tmp_path, secrets):
    seen = []
    engine = TesseractExtractor(command="tesseract")
    engine.use_runner(lambda command, stdin, env, timeout_seconds: seen.append(env))
    engine._run(["x"], timeout=30, watched=True)
    assert len(seen) == 1 and set(seen[0]) <= set(ALLOWED) and seen[0]["OMP_THREAD_LIMIT"] == _ENVIRONMENT["OMP_THREAD_LIMIT"]
    assert_clean(seen[0])


def test_the_report_worker_gets_no_secret(tmp_path, secrets):
    dump = tmp_path / "env.json"
    script = tmp_path / "report_worker.py"
    script.write_text(f"import json, os, sys\njson.dump(sorted(os.environ), open({str(dump)!r}, 'w'))\nsys.stdout.write('FAIL render_error\\n')\n", encoding="utf-8")
    outcome = make_report("# memo\n", {}, command=(sys.executable, str(script)))
    assert outcome.status == "failed" and outcome.reason == "render_error"
    assert_clean(json.loads(dump.read_text(encoding="utf-8")))
