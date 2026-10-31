"""The container image files, read as text, and the scripts that build and measure it (PRD FR-018 criteria 1 to 9, 11 and 12; SEC-02, SEC-03, SEC-11, SEC-17; Phase 7 step 2).

Docker is not installed on the development machine, so these tests can only check what the files say and run their shell logic with stand-in commands. The
image itself is built, started and tested by the owner (``docs/RUNBOOK_container.md``); that is stated in the runbook and in PROGRESS.md.
"""

import os
import re
import stat
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
IGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")
SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "OPENAI")


def instructions(text=DOCKERFILE):
    """The Dockerfile as (instruction, arguments, stage) with continuation lines joined and comments dropped."""
    joined, pending = [], ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not pending and (not line.strip() or line.lstrip().startswith("#")):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        joined.append(pending + line)
        pending = ""
    result, stage = [], None
    for line in joined:
        keyword, _, rest = line.strip().partition(" ")
        keyword = keyword.upper()
        if keyword == "FROM":
            match = re.fullmatch(r"(\S+)(?:\s+AS\s+(\S+))?", rest.strip(), re.I)
            stage = match.group(2)
        result.append((keyword, rest.strip(), stage))
    return result


def in_stage(name):
    return [(k, a) for k, a, s in instructions() if s == name]


def run_sh(snippet, **env):
    return subprocess.run(["sh", "-c", snippet], env={"PATH": os.environ["PATH"], **env}, capture_output=True, text=True)


# --- the Dockerfile ------------------------------------------------------------------------------------------------------------------------------


def test_the_stages_are_in_order_and_the_last_is_the_product():
    stages = [(a, s) for k, a, s in instructions() if k == "FROM"]
    assert [s for _, s in stages] == ["base", "builder", "runtime", "test", "product"]
    assert [a.split()[0] for a, _ in stages] == ["${PYTHON_IMAGE}", "base", "base", "runtime", "runtime"]  # a bare `docker build .` builds the last stage: the product


def test_the_base_image_is_an_argument_with_no_default_so_nothing_can_be_built_from_a_floating_tag():
    args = [a for k, a, s in instructions() if k == "ARG" and s is None]
    assert args == ["PYTHON_IMAGE"]  # before the first FROM, and without "=value"
    assert not re.search(r"^FROM\s+python", DOCKERFILE, re.M)


GOOD_DIGEST = "python@sha256:" + "0123456789abcdef" * 4


def digest_guard():
    run = next(a for k, a in in_stage("base") if k == "RUN")
    return run


@pytest.mark.parametrize("image, ok", [(GOOD_DIGEST, True), ("registry.example/python@sha256:" + "a" * 64, True), ("python:3.12-slim", False), ("python:3.12-slim@sha256:abc", False),
                                       ("python@sha256:" + "a" * 63, False), ("python@sha256:" + "a" * 65, False), ("", False), ("python@sha256:", False), ("python", False)])  # fmt: skip
def test_the_digest_guard_accepts_only_a_name_pinned_by_a_full_digest(image, ok):
    done = run_sh(digest_guard(), PYTHON_IMAGE=image)
    assert (done.returncode == 0) is ok, done.stderr
    if not ok:
        assert "pinned by digest" in done.stderr


def commit_guard():
    return next(a for k, a in in_stage("runtime") if k == "RUN" and "BUILD_COMMIT" in a)


@pytest.mark.parametrize("commit, ok", [("0123456789abcdef0123456789abcdef01234567", True), ("0" * 40, True), ("0" * 39, False), ("0" * 41, False), ("A" * 40, False), ("g" * 40, False),
                                        ("HEAD", False), ("", False), ("0123456789abcdef0123456789abcdef0123456\n", False)])  # fmt: skip
def test_the_commit_guard_accepts_only_a_full_lower_case_commit(commit, ok):
    done = run_sh(commit_guard(), BUILD_COMMIT=commit)
    assert (done.returncode == 0) is ok, done.stderr


def test_only_named_paths_are_copied_into_the_product_and_never_the_whole_context():
    copies = [a.split() for k, a in in_stage("runtime") if k == "COPY"]
    sources = sorted(c[-2] if not c[0].startswith("--") else c[-2] for c in copies)
    assert sources == sorted(["/opt/venv", "src", "prompts", "config", "tests/eval/assignments.jsonl"])
    for k, a, s in instructions():
        if k in ("COPY", "ADD"):
            assert k == "COPY", "ADD can fetch a URL or unpack an archive"
            for source in a.split()[:-1]:
                assert source not in (".", "./", "*", "/") and not source.startswith(("http:", "https:", "..")), source


def test_the_product_is_copied_to_the_places_the_code_resolves_its_files_from():
    destinations = {a.split()[-2]: a.split()[-1] for k, a in in_stage("runtime") if k == "COPY"}
    assert destinations["src"] == "/app/src" and destinations["prompts"] == "/app/prompts" and destinations["config"] == "/app/config"
    assert destinations["tests/eval/assignments.jsonl"] == "/app/tests/eval/assignments.jsonl"  # PROJECT_ROOT/tests/eval, with PROJECT_ROOT = /app
    envs = " ".join(a for k, a in in_stage("runtime") if k == "ENV")
    assert "PYTHONPATH=/app/src" in envs


def test_the_product_runs_as_a_non_root_numeric_user_and_never_switches_back():
    users = [(a, s) for k, a, s in instructions() if k == "USER"]
    assert users == [("10001:10001", "runtime")]
    runtime = in_stage("runtime")
    assert [k for k, _ in runtime].index("USER") > [k for k, _ in runtime].index("COPY")  # root does the setup, then the user takes over
    assert [k for k, _ in runtime][-3:] == ["HEALTHCHECK", "ENTRYPOINT", "CMD"] and [k for k, _ in runtime].index("USER") < [k for k, _ in runtime].index("ENTRYPOINT")
    assert re.search(r"useradd[^&]*--uid 10001", DOCKERFILE) and "--shell /usr/sbin/nologin" in DOCKERFILE


def test_no_secret_is_set_or_given_to_the_build():
    for keyword, argument, stage in instructions():
        if keyword in ("ENV", "ARG"):
            for name in re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=?", argument.replace("\\", " ")):
                if name.isupper() or "_" in name:
                    assert not any(word in name.upper() for word in SECRET_WORDS) or name == "CREDIT_INTEL_BUILD_COMMIT", (keyword, argument)
    assert {a.split("=")[0] for k, a, s in instructions() if k == "ARG"} == {"PYTHON_IMAGE", "UV_VERSION", "BUILD_COMMIT"}
    assert "sk-" not in DOCKERFILE and "Bearer" not in DOCKERFILE


def test_the_product_environment_is_what_the_service_needs():
    envs = " ".join(a for k, a in in_stage("runtime") if k == "ENV")
    for needed in ("PATH=/opt/venv/bin:$PATH", "PYTHONDONTWRITEBYTECODE=1", "CREDIT_INTEL_BUILD_COMMIT=${BUILD_COMMIT}", "CREDIT_INTEL_API_OUTPUT_DIR=/data/runs",
                   "CREDIT_INTEL_API_CACHE_DIR=/data/cache", "CREDIT_INTEL_API_HOST=0.0.0.0", "TMPDIR=/tmp"):  # fmt: skip
        assert needed in envs, needed
    assert not re.search(r"CREDIT_INTEL_API_TOKEN|OPENAI_API_KEY|TOKEN_CEILING", DOCKERFILE.replace("# ", ""))


def test_system_packages_are_only_tesseract_with_its_english_data_and_the_lists_are_removed():
    apt = next(a for k, a in in_stage("runtime") if k == "RUN" and "apt-get" in a)
    assert "--no-install-recommends" in apt and "rm -rf /var/lib/apt/lists/*" in apt and "apt-get update" in apt
    packages = re.search(r"install\s+(?:--\S+\s+|-y\s+)*(.*?)\s*(?:&&|$)", apt).group(1).split()
    assert sorted(p for p in packages if not p.startswith("-")) == ["tesseract-ocr", "tesseract-ocr-eng"]


def test_the_environment_is_built_from_the_lock_file_with_a_pinned_uv_and_no_dev_tools_in_the_product():
    builder = in_stage("builder")
    assert any(k == "ARG" and re.fullmatch(r"UV_VERSION=\d+\.\d+\.\d+", a) for k, a in builder)
    assert any(k == "RUN" and 'pip install --no-cache-dir "uv==${UV_VERSION}"' in a for k, a in builder)
    syncs = [a for k, a in builder if k == "RUN" and "uv sync" in a]
    assert len(syncs) == 2 and all("--frozen" in a and "--no-install-project" in a for a in syncs)
    assert "--no-dev" in syncs[0] and "--no-dev" not in syncs[1]
    runtime_text = " ".join(a for k, a in in_stage("runtime"))
    assert "uv " not in runtime_text and "pip install" not in runtime_text and "venv-dev" not in runtime_text


def test_the_health_check_calls_the_health_endpoint_and_the_entry_point_is_the_service():
    health = next(a for k, a in in_stage("runtime") if k == "HEALTHCHECK")
    assert "/health" in health and "127.0.0.1:8000" in health and "--timeout" in health and "--interval" in health
    entry = next(a for k, a in in_stage("runtime") if k == "ENTRYPOINT")
    assert entry == '["python", "-m", "credit_intel.api"]'
    assert next(a for k, a in in_stage("runtime") if k == "CMD") == '["--config", "/config/settings.toml"]'
    assert any(k == "EXPOSE" and a == "8000" for k, a in in_stage("runtime"))


def test_the_data_folders_belong_to_the_service_user_and_nothing_else_is_writable_by_it():
    run = next(a for k, a in in_stage("runtime") if k == "RUN" and "groupadd" in a)
    assert "mkdir -p /data/runs /data/cache /config" in run and "chown 10001:10001 /data/runs /data/cache" in run
    assert "chmod 777" not in DOCKERFILE and "chmod -R 777" not in DOCKERFILE


def test_the_test_stage_is_a_separate_target_that_runs_the_golden_and_reproducibility_tests_and_the_product_has_no_tests():
    test = in_stage("test")
    assert ("COPY", "tests /app/tests") in test
    command = next(a for k, a in test if k == "CMD")
    for needed in ("test_fresh_process_golden.py", "test_reproducibility.py", "test_results_json.py", "test_parse_limits.py", "test_memory_reading.py", "test_container_sizing.py"):
        assert needed in command, needed
    for name in re.findall(r'"(tests/[^"]+\.py)"', command):
        assert (ROOT / name).is_file(), name
    assert all("tests /app/tests" not in a for k, a in in_stage("runtime"))


def test_the_uv_version_matches_the_one_that_wrote_the_lock_file():
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert lock.startswith("version = ") and "revision" in lock[:200]
    version = re.search(r"ARG UV_VERSION=(\S+)", DOCKERFILE).group(1)
    assert re.fullmatch(r"0\.\d+\.\d+", version)


# --- .dockerignore ---------------------------------------------------------------------------------------------------------------------------------


def _regex(pattern: str) -> re.Pattern:
    """Docker's ignore patterns (Go ``filepath.Match`` with ``**``) as a regular expression on a slash-separated path."""
    anchored = pattern.rstrip("/")
    out, i = "", 0
    while i < len(anchored):
        if anchored.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif anchored.startswith("**", i):
            out += ".*"
            i += 2
        elif anchored[i] == "*":
            out += "[^/]*"
            i += 1
        elif anchored[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(anchored[i])
            i += 1
    return re.compile(out + r"(?:/.*)?")


def in_context(path: str, patterns=None) -> bool:
    """Whether Docker would send ``path`` in the build context: the last matching line wins, ``!`` re-includes."""
    included = True
    for line in (patterns if patterns is not None else [l.strip() for l in IGNORE.splitlines() if l.strip() and not l.startswith("#")]):
        negate = line.startswith("!")
        if _regex(line.lstrip("!")).fullmatch(path):
            included = negate
    return included


SENSITIVE = [".env", ".env.local", "deploy/.env", "src/.env", "config/.env", "tests/.env", "src/credit_intel/.env", "src/.env.production", "private/R1.pdf", "private/eval/labels.json", "runs/20261030T101530.123456Z-abcdef12/memo.md",
             ".cache/llm/abc.json", "InfoEdge_Annual_Report_2025.pdf", "MM-Annual-Report-2025-26-compressed.pdf", "src/credit_intel/x.pdf", "tests/fixtures/a.pdf",
             "server.pem", "config/server.key", "secrets/token", "config/secrets/a", "data/x.csv", "tests/a.xlsx", ".git/config", ".venv/bin/python", "docs/PRD.md",
             "PROGRESS.md", "CLAUDE.md", "README.md", "compose.yaml", "deploy/credit-intel.env.example", "src/credit_intel/__pycache__/x.pyc", "tests/unit/__pycache__/a.pyc"]  # fmt: skip
WANTED = ["pyproject.toml", "uv.lock", "src/credit_intel/api/app.py", "src/credit_intel/report/fonts/DejaVuSans.ttf", "prompts/extraction_v5.md", "config/settings.toml",
          "config/risk_rules.toml", "tests/eval/assignments.jsonl", "tests/unit/test_x.py", "tests/conftest.py"]  # fmt: skip


@pytest.mark.parametrize("path", SENSITIVE)
def test_nothing_sensitive_and_nothing_unneeded_can_enter_the_build_context(path):
    assert not in_context(path), path


@pytest.mark.parametrize("path", WANTED)
def test_what_the_image_needs_is_in_the_build_context(path):
    assert in_context(path), path


def test_the_matcher_follows_the_last_line_that_matches():
    assert in_context("a/b.txt", ["*", "!a/", "**/*.txt"]) is False
    assert in_context("a/b.md", ["*", "!a/", "**/*.txt"]) is True
    assert in_context("x", ["*"]) is False and in_context("x", []) is True


def test_no_real_file_of_the_repository_that_the_context_would_send_is_sensitive():
    """Walks the working tree (not ``private/``, not run folders, not the cache, not tool folders: none of those is ever entered) and checks every file that would be sent."""
    pruned = {".git", ".venv", "private", "runs", ".cache", ".archify", ".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__", "node_modules"}
    sent = []
    for folder, names, files in os.walk(ROOT):
        names[:] = [n for n in names if n not in pruned]
        for name in files:
            path = Path(folder, name).relative_to(ROOT).as_posix()
            if in_context(path):
                sent.append(path)
    assert sent, "the context would be empty"
    for path in sent:
        assert path.split("/")[0] in ("pyproject.toml", "uv.lock", "src", "prompts", "config", "tests"), path
        assert not re.search(r"(^|/)\.env|\.pdf$|\.pem$|\.key$|\.xlsx?$|\.csv$|(^|/)secrets/|\.pyc$", path), path
    root_pdfs = [p.name for p in ROOT.glob("*.pdf")]
    assert not any(in_context(name) for name in root_pdfs)  # the PDFs that sit in the repository root, if any


# --- compose.yaml ------------------------------------------------------------------------------------------------------------------------------


def test_the_service_is_hardened_the_way_the_requirement_says():
    for needed in ('read_only: true', 'init: true', 'user: "10001:10001"', "no-new-privileges:true", "pids_limit:"):
        assert needed in COMPOSE, needed
    assert re.search(r"cap_drop:\s*\n\s*-\s*ALL", COMPOSE)
    for forbidden in ("privileged", "network_mode", "cap_add", "/var/run/docker.sock", "pid: host", "ipc: host", "user: root", 'user: "0'):
        assert forbidden not in COMPOSE, forbidden


def test_the_service_is_published_on_the_loopback_address_of_the_host_only():
    section = re.search(r"^    ports:\s*\n((?:\s+-\s+\S+\s*\n)+)", COMPOSE, re.M).group(1)
    assert [l.strip() for l in section.splitlines() if l.strip()] == ['- "127.0.0.1:8000:8000"']
    assert COMPOSE.count("ports:") == 1 and "expose:" not in COMPOSE


def test_nothing_with_a_limit_or_a_secret_has_a_default_and_a_missing_value_stops_compose_with_a_message():
    for variable in ("CREDIT_INTEL_BUILD_COMMIT", "PYTHON_IMAGE", "CREDIT_INTEL_CONTAINER_MEMORY", "CREDIT_INTEL_ENV_FILE", "CREDIT_INTEL_TOKEN_CEILING"):
        assert re.search(r"\$\{" + variable + r":\?[^}]+\}", COMPOSE), variable
        assert not re.search(r"\$\{" + variable + r":-", COMPOSE), variable
    assert "mem_limit: ${CREDIT_INTEL_CONTAINER_MEMORY:?" in COMPOSE and "memswap_limit: ${CREDIT_INTEL_CONTAINER_MEMORY:?" in COMPOSE  # no swap beyond the limit


def test_the_two_secrets_come_from_an_env_file_outside_the_repository_and_appear_nowhere_in_the_compose_file():
    assert re.search(r"env_file:\s*\n\s*-\s*\$\{CREDIT_INTEL_ENV_FILE:\?", COMPOSE)
    assert not re.search(r"(OPENAI_API_KEY|CREDIT_INTEL_API_TOKEN)\s*[:=]", COMPOSE)
    assert "sk-" not in COMPOSE and "Bearer" not in COMPOSE and ".env" not in re.sub(r"#.*", "", COMPOSE).replace("env_file", "")


def test_the_volumes_hold_the_read_only_settings_and_the_two_data_folders_and_nothing_else():
    mounts = re.findall(r"^\s*-\s*(\S+:/\S+?)\s*$", re.sub(r"tmpfs:.*?\n\s*logging", "logging", COMPOSE, flags=re.S), re.M)
    assert mounts == ["${CREDIT_INTEL_SETTINGS:-./config/settings.toml}:/config/settings.toml:ro", "runs:/data/runs", "cache:/data/cache"]
    assert re.search(r"^volumes:\s*\n\s+runs:\s*\n\s+cache:\s*$", COMPOSE, re.M)


def test_uploads_go_to_a_small_private_tmpfs_the_server_user_owns_and_cannot_execute_from():
    tmpfs = re.search(r"tmpfs:\s*\n\s*-\s*(/tmp:\S+)", COMPOSE).group(1)
    for needed in ("uid=10001", "gid=10001", "mode=0700", "noexec", "nosuid", "nodev", "size="):
        assert needed in tmpfs, needed


def test_the_stop_grace_period_is_longer_than_the_run_time_limit_so_a_planned_restart_lets_runs_finish():
    grace = int(re.search(r"stop_grace_period:\s*\$\{CREDIT_INTEL_STOP_GRACE:-(\d+)s\}", COMPOSE).group(1))
    limit = tomllib.loads((ROOT / "config" / "settings.toml").read_text(encoding="utf-8"))["api"]["run_timeout_seconds"]
    assert grace > limit


def test_logs_are_capped_and_the_image_is_the_product_stage_tagged_with_the_commit():
    assert re.search(r'max-size:\s*"10m"', COMPOSE) and re.search(r'max-file:\s*"5"', COMPOSE) and "driver: json-file" in COMPOSE
    assert re.search(r"target:\s*runtime", COMPOSE) and "image: credit-intel:${CREDIT_INTEL_BUILD_COMMIT:?" in COMPOSE
    assert re.search(r"BUILD_COMMIT:\s*\$\{CREDIT_INTEL_BUILD_COMMIT:\?", COMPOSE) and re.search(r"PYTHON_IMAGE:\s*\$\{PYTHON_IMAGE:\?", COMPOSE)


def test_the_memory_the_sizing_rule_names_is_the_one_in_the_compose_message_and_the_runbook():
    from credit_intel.api.sizing import SERVER_ALLOWANCE_MB, minimum_container_mb
    from credit_intel.config import load_api_settings, load_parse_limits

    settings = ROOT / "config" / "settings.toml"
    api = load_api_settings(settings, {"CREDIT_INTEL_API_OUTPUT_DIR": "/a", "CREDIT_INTEL_API_CACHE_DIR": "/b"})
    needed = minimum_container_mb(api, load_parse_limits(settings, {}))
    runbook = (ROOT / "docs" / "RUNBOOK_container.md").read_text(encoding="utf-8")
    assert f"{needed:,}" in runbook and "1,536 MB" in runbook and SERVER_ALLOWANCE_MB == 1536 and needed == 8180
    assert "1.5 GB" in COMPOSE and "uploads" in COMPOSE


def test_the_default_size_of_the_upload_tmpfs_holds_what_the_service_can_receive():
    """The tmpfs is a cap; the sizing rule counts the uploads. If the cap were smaller than the uploads, an upload would run out of room (a disk-full error) instead of being refused."""
    from credit_intel.api.sizing import uploads_mb
    from credit_intel.config import load_api_settings

    api = load_api_settings(ROOT / "config" / "settings.toml", {"CREDIT_INTEL_API_OUTPUT_DIR": "/a", "CREDIT_INTEL_API_CACHE_DIR": "/b"})
    size = re.search(r"CREDIT_INTEL_UPLOAD_TMPFS:-(\d+)([mg])\}", COMPOSE)
    megabytes = int(size.group(1)) * (1024 if size.group(2) == "g" else 1)
    from credit_intel.config import IngestionSettings

    assert megabytes >= uploads_mb(api, IngestionSettings().max_file_bytes)


# --- the scripts and the env example ------------------------------------------------------------------------------------------------------------


def test_the_env_example_names_the_two_secrets_and_holds_neither():
    lines = [l for l in (ROOT / "deploy" / "credit-intel.env.example").read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    assert lines == ["OPENAI_API_KEY=", "CREDIT_INTEL_API_TOKEN="]  # empty: an empty token stops the service, so the file cannot be used as it is


def test_the_example_is_not_ignored_by_git_but_a_filled_in_copy_would_be():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*.env" in ignore and ".env.*" in ignore and ".env" in ignore
    assert not any(l == "credit-intel.env.example" for l in ignore)


@pytest.mark.parametrize("script", ["build.sh", "measure_container.sh"])
def test_the_scripts_are_executable_posix_shell_that_stops_at_the_first_error(script):
    path = ROOT / "deploy" / script
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and "set -eu" in text and path.stat().st_mode & stat.S_IXUSR
    assert "bash" not in text.split("\n")[0] and "eval " not in text and "curl | sh" not in text
    assert subprocess.run(["sh", "-n", str(path)], capture_output=True).returncode == 0  # it parses


def stand_ins(tmp_path, **scripts):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in scripts.items():
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)
    return bin_dir


def run_script(name, args, bin_dir, **env):
    full = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(bin_dir)}
    full.update(env)
    return subprocess.run(["sh", str(ROOT / "deploy" / name), *args], env=full, capture_output=True, text=True, cwd=ROOT)


COMMIT = "0123456789abcdef0123456789abcdef01234567"


def build_stand_ins(tmp_path, diff_status=0, untracked=""):
    log = tmp_path / "docker.log"
    return stand_ins(
        tmp_path,
        git=f'''case "$1" in
  diff) exit {diff_status} ;;
  ls-files) printf '%s' "{untracked}" ;;
  rev-parse) echo {COMMIT} ;;
esac
''',
        docker=f'echo "$@" >> {log}\n',
    ), log


def test_build_refuses_without_a_pinned_base_image(tmp_path):
    bin_dir, log = build_stand_ins(tmp_path)
    done = run_script("build.sh", [], bin_dir)
    assert done.returncode != 0 and "PYTHON_IMAGE" in done.stderr and not log.exists()


def test_build_refuses_when_the_files_that_go_into_the_image_differ_from_the_commit(tmp_path):
    bin_dir, log = build_stand_ins(tmp_path, diff_status=1)
    done = run_script("build.sh", [], bin_dir, PYTHON_IMAGE=GOOD_DIGEST)
    assert done.returncode == 1 and "differ from HEAD" in done.stderr and not log.exists()


def test_build_refuses_untracked_files_in_the_folders_that_go_into_the_image(tmp_path):
    bin_dir, log = build_stand_ins(tmp_path, untracked="src/credit_intel/new.py")
    done = run_script("build.sh", [], bin_dir, PYTHON_IMAGE=GOOD_DIGEST)
    assert done.returncode == 1 and "untracked" in done.stderr and not log.exists()


def test_build_passes_the_pinned_image_the_commit_and_the_product_target_and_tags_with_the_commit(tmp_path):
    bin_dir, log = build_stand_ins(tmp_path)
    done = run_script("build.sh", [], bin_dir, PYTHON_IMAGE=GOOD_DIGEST)
    assert done.returncode == 0 and f"CREDIT_INTEL_BUILD_COMMIT={COMMIT}" in done.stdout
    assert log.read_text(encoding="utf-8").strip() == f"build --target runtime --build-arg PYTHON_IMAGE={GOOD_DIGEST} --build-arg BUILD_COMMIT={COMMIT} -t credit-intel:{COMMIT} ."


def test_build_test_makes_the_test_image_under_another_name_so_it_cannot_be_mistaken_for_the_product(tmp_path):
    bin_dir, log = build_stand_ins(tmp_path)
    done = run_script("build.sh", ["test"], bin_dir, PYTHON_IMAGE=GOOD_DIGEST)
    assert done.returncode == 0
    line = log.read_text(encoding="utf-8").strip()
    assert "--target test" in line and f"-t credit-intel-test:{COMMIT}" in line and f"-t credit-intel:{COMMIT}" not in line


def measure_stand_ins(tmp_path, answers):
    log = tmp_path / "calls.log"
    return stand_ins(
        tmp_path,
        curl=f'''echo "$@" >> {log}
case "$*" in
  *"-F "*) cat <<'EOT'
{answers[0]}
EOT
  ;;
  *) echo '{{"run_id":"20261030T101530.123456Z-abcdef12","state":"exported","files":["memo.md","manifest.json"]}}' ;;
esac
''',
        docker='''case "$*" in
  *memory.peak) echo 3145728000 ;;
  *memory.events) printf 'low 0\\nhigh 0\\nmax 0\\noom 0\\noom_kill 0\\n' ;;
  *memory.max) echo 8589934592 ;;
esac
''',
        sleep="exit 0\n",
    ), log


ACCEPTED = '{"run_id":"20261030T101530.123456Z-abcdef12","state":"queued"}'


def test_measure_submits_waits_and_prints_only_statuses_seconds_peak_memory_and_kernel_events(tmp_path):
    bin_dir, log = measure_stand_ins(tmp_path, [ACCEPTED])
    done = run_script("measure_container.sh", ["any.pdf", "2"], bin_dir, CREDIT_INTEL_API_TOKEN="t" * 40)
    out = done.stdout
    assert done.returncode == 0, done.stderr
    assert out.count("run 20261030T101530.123456Z-abcdef12:") == 2 and '"state":"exported"' in out
    assert "container peak memory: 3000 MB" in out and "oom_kill 0" in out and "memory limit of the container: 8589934592" in out
    assert re.search(r"seconds, first submission to last end: \d+", out)
    assert "t" * 40 not in out and "t" * 40 not in done.stderr  # the token is not echoed
    assert log.read_text(encoding="utf-8").count("-F file=@any.pdf") == 2 and "confirm_public_document=true" in log.read_text(encoding="utf-8")


def test_measure_stops_with_the_catalogued_message_when_a_submission_is_not_accepted(tmp_path):
    refused = '{"code":"E-INPUT-SEND-REFUSED","message":"The document may not be sent to the hosted API (not_recorded)."}'
    bin_dir, _ = measure_stand_ins(tmp_path, [refused])
    done = run_script("measure_container.sh", ["any.pdf"], bin_dir, CREDIT_INTEL_API_TOKEN="t" * 40)
    assert done.returncode == 1 and "was not accepted" in done.stderr and "E-INPUT-SEND-REFUSED" in done.stderr


def test_measure_needs_the_document_and_the_token_and_says_when_the_kernel_will_not_tell_the_peak(tmp_path):
    bin_dir, _ = measure_stand_ins(tmp_path, [ACCEPTED])
    assert run_script("measure_container.sh", [], bin_dir, CREDIT_INTEL_API_TOKEN="x").returncode != 0
    assert run_script("measure_container.sh", ["any.pdf"], bin_dir).returncode != 0
    (bin_dir / "docker").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    done = run_script("measure_container.sh", ["any.pdf"], bin_dir, CREDIT_INTEL_API_TOKEN="t" * 40)
    assert done.returncode == 0 and "container peak memory: unavailable" in done.stdout


def test_measure_never_asks_for_a_file_of_a_run_only_for_its_status():
    text = (ROOT / "deploy" / "measure_container.sh").read_text(encoding="utf-8")
    assert not re.search(r"/(memo|results|manifest|report)\b", re.sub(r"#.*", "", text))


# --- the TLS proxy files (PRD OD-35 (a), OD-36, FR-018 criterion 11; Phase 7 step 5) ----------------------------------------------------------------------

PROXY = (ROOT / "compose.proxy.yaml").read_text(encoding="utf-8")
CADDY = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
CADDY_CODE = re.sub(r"#.*", "", CADDY)
PROXY_CODE = re.sub(r"#.*", "", PROXY)


def test_the_base_compose_states_the_loopback_only_condition_with_its_reason_and_makes_no_statement_about_tls():
    lines = COMPOSE.splitlines()
    at = next(n for n, l in enumerate(lines) if "CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION" in l and not l.lstrip().startswith("#"))
    reason = " ".join(l for l in lines[max(0, at - 4):at] if l.lstrip().startswith("#"))
    assert 'CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION: "true"' in lines[at] and "loopback" in reason and "NOT a statement about TLS" in reason
    assert "BEHIND_TLS:" not in COMPOSE and COMPOSE.count("LOOPBACK_ONLY_PUBLICATION:") == 1  # there is no TLS here, so none is claimed


def test_the_proxy_overlay_takes_the_service_off_the_host_and_publishes_only_the_proxy():
    assert re.search(r"^\s+ports: !reset \[\]\s*$", PROXY_CODE, re.M)
    published = re.findall(r'^\s*-\s*"(\d+:\d+)"', PROXY_CODE, re.M)
    assert published == ["80:80", "443:443"]
    service, proxy = PROXY_CODE.split("  proxy:")
    assert "ports:" in service and "80:80" not in service and "80:80" in proxy


def test_every_value_that_matters_in_the_proxy_overlay_is_required_and_has_no_default():
    for variable in ("CREDIT_INTEL_PUBLIC_HOST", "CREDIT_INTEL_PROXY_SUBNET", "CREDIT_INTEL_PROXY_IMAGE"):
        assert re.search(r"\$\{" + variable + r":\?[^}]+\}", PROXY_CODE), variable
        assert not re.search(r"\$\{" + variable + r":-", PROXY_CODE), variable


def test_the_proxy_image_must_be_named_by_digest_in_the_message_and_the_runbook_shows_how():
    assert "pinned by digest" in PROXY and "name@sha256" in PROXY
    runbook = (ROOT / "docs" / "RUNBOOK_container.md").read_text(encoding="utf-8")
    assert "CREDIT_INTEL_PROXY_IMAGE=$(docker inspect --format '{{index .RepoDigests 0}}' caddy:2)" in runbook


def test_the_service_is_told_the_three_things_the_proxy_means_for_it():
    assert 'CREDIT_INTEL_API_BEHIND_TLS: "true"' in PROXY_CODE and 'CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION: "false"' in PROXY_CODE  # TLS ends here; the base file's other statement no longer holds
    assert re.search(r"CREDIT_INTEL_API_PUBLIC_HOSTS: \$\{CREDIT_INTEL_PUBLIC_HOST:\?", PROXY_CODE)
    assert re.search(r"CREDIT_INTEL_API_TRUSTED_PROXIES: \$\{CREDIT_INTEL_PROXY_SUBNET:\?", PROXY_CODE)
    assert re.search(r"ipam:\s*\n\s*config:\s*\n\s*-\s*subnet:\s*\$\{CREDIT_INTEL_PROXY_SUBNET:\?", PROXY_CODE)  # the trusted network is the one the compose network is made with


def test_the_proxy_is_hardened_waits_for_the_service_and_carries_no_secret():
    proxy = PROXY_CODE.split("  proxy:")[1]
    for needed in ("read_only: true", "no-new-privileges:true", "mem_limit:", "pids_limit:", "condition: service_healthy", "- ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro"):
        assert needed in proxy, needed
    assert re.search(r"cap_drop:\s*\n\s*-\s*ALL", proxy) and re.findall(r"cap_add:\s*\n((?:\s*-\s*\S+\n)+)", proxy) == ["      - NET_BIND_SERVICE\n"]
    for forbidden in ("privileged", "network_mode", "/var/run/docker.sock", "user: root", "pid: host", "OPENAI", "API_TOKEN", "sk-", "Bearer"):
        assert forbidden not in PROXY_CODE, forbidden


def test_the_caddyfile_names_the_service_and_port_of_the_compose_file_and_the_image():
    name = re.search(r"^  (\S+):\s*\n    image: credit-intel:", COMPOSE, re.M).group(1)
    port = re.search(r"EXPOSE (\d+)", DOCKERFILE).group(1)
    assert re.search(rf"reverse_proxy {re.escape(name)}:{port}\s*$", CADDY_CODE, re.M)
    assert "{$CREDIT_INTEL_PUBLIC_HOST}" in CADDY_CODE and "admin off" in CADDY_CODE


def test_the_caddyfile_limits_the_body_to_the_file_size_limit_with_room_for_the_form_and_trusts_no_forwarded_header():
    from credit_intel.api.uploads import FIELD_ALLOWANCE
    from credit_intel.config import IngestionSettings

    size = int(re.search(r"max_size (\d+)MB", CADDY_CODE).group(1))
    assert size * 1000 * 1000 >= IngestionSettings().max_file_bytes + FIELD_ALLOWANCE
    for forbidden in ("trusted_proxies", "header_up X-Forwarded", "insecure_skip_verify", "tls internal", "tls off", "auto_https off", "http://"):
        assert forbidden not in CADDY_CODE, forbidden


def test_the_runbook_names_every_variable_of_the_proxy_overlay_and_the_checks():
    runbook = (ROOT / "docs" / "RUNBOOK_container.md").read_text(encoding="utf-8")
    section = re.search(r"## 5b\. (.*?)\n## 6\.", runbook, re.S).group(1)
    for variable in set(re.findall(r"\$\{(CREDIT_INTEL_[A-Z_]+):\?", PROXY)):
        assert variable in section, variable
    for needed in ("docker compose -f compose.yaml -f compose.proxy.yaml up -d", "strict-transport-security: max-age=31536000", "401", "429", "api.public_hosts", "api.trusted_proxies", "api.behind_tls",
                   "2.24", "usable through this proxy"):  # fmt: skip
        assert needed in section, needed
    assert "written, not run" in runbook


def test_the_runbook_gives_a_concrete_check_for_each_of_the_four_facts_written_from_memory():
    runbook = (ROOT / "docs" / "RUNBOOK_container.md").read_text(encoding="utf-8")
    table = re.search(r"\| Recalled fact \| Check \| What you should see.*?\n((?:\|.*\n)+)", runbook).group(1)
    rows = [r for r in table.splitlines() if r.startswith("| **")]
    assert len(rows) == 4
    wanted = {
        "`!reset`": ("docker compose version", "config", "published", "2.24", "8000"),
        "`admin off`": ("caddy validate", "2019", "admin endpoint closed"),
        "`request_body": ("caddy validate", "big105", "big115", "E-INPUT-TOO-LARGE", "413"),
        "`X-Forwarded-For`": ("X-Forwarded-For: 1.2.3.4", "429", "200", "locked out", "not `1.2.3.4`"),
    }
    for fact, needles in wanted.items():
        row = next(r for r in rows if fact in r.split("|")[1])
        for needle in needles:
            assert needle in row, (fact, needle)


def test_the_two_files_of_the_body_limit_check_straddle_the_proxy_limit_and_the_service_limit():
    from credit_intel.api.uploads import FIELD_ALLOWANCE
    from credit_intel.config import IngestionSettings

    proxy_limit = int(re.search(r"max_size (\d+)MB", CADDY_CODE).group(1)) * 1000 * 1000  # Caddy reads MB as a million bytes
    service_limit = IngestionSettings().max_file_bytes
    small, large = 105_000_000, 115_000_000
    assert service_limit < small and small + 1000 < proxy_limit < large  # the first reaches the service and is refused by it; the second is stopped by the proxy
    assert small <= service_limit + FIELD_ALLOWANCE  # and it is the streaming limit, not the early refusal from the header, that refuses it


def test_the_runbook_command_for_the_test_image_lets_its_tmpfs_run_programs_and_the_product_tmpfs_does_not():
    """First real run: Docker mounts ``--tmpfs`` noexec, so the tests' executable stand-ins under /tmp failed with PermissionError (56 tests, one cause)."""
    runbook = (ROOT / "docs" / "RUNBOOK_container.md").read_text(encoding="utf-8")
    command = re.search(r"docker run --rm --init --read-only --tmpfs (\S+) --network none \\\n\s+credit-intel-test:", runbook)
    assert command is not None
    assert command.group(1).split(",")[1:].count("exec") == 1
    assert "noexec" not in command.group(1)
    assert "noexec" in re.search(r"tmpfs:\s*\n\s*-\s*(/tmp:\S+)", COMPOSE).group(1)


def test_both_environments_can_import_the_package_from_an_isolated_interpreter_as_the_workers_start():
    """Real runs in the image: the workers start as ``python -I`` (``PYTHONPATH`` is ignored) and the project is synced with --no-install-project, so each environment
    needs a .pth file; with it in the dev environment only, the tests passed and every real document failed with E-INPUT-CORRUPT."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.count("credit_intel_src.pth") == 1
    builder = dockerfile.split("FROM base AS builder")[1].split("FROM base AS runtime")[0]
    assert "for env in /opt/venv /opt/venv-dev" in builder and "echo /app/src" in builder
    assert builder.index("UV_PROJECT_ENVIRONMENT=/opt/venv-dev") < builder.index("credit_intel_src.pth")
    assert builder.index("uv sync --frozen --no-dev") < builder.index("credit_intel_src.pth")
    assert "-I" in (ROOT / "src/credit_intel/ingestion/sandbox.py").read_text(encoding="utf-8")  # if the workers stop using -I, this reasoning needs revisiting
    runbook = (ROOT / "docs" / "RUNBOOK_container.md").read_text(encoding="utf-8")
    assert "--entrypoint python credit-intel:$CREDIT_INTEL_BUILD_COMMIT -I -c" in runbook
