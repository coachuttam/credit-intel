"""The memory a container needs, and the refusal to start in one that is too small (PRD FR-018 criterion 7; Phase 7 step 2)."""

import io
from pathlib import Path

import pytest

from credit_intel.api import __main__ as launcher
from credit_intel.api.sizing import SERVER_ALLOWANCE_MB, check_container_memory, container_memory_limit_mb, minimum_container_mb, uploads_mb
from credit_intel.config import ApiSettings, ParseLimits
from credit_intel.ingestion.errors import ErrorCode, IngestionError

API = ApiSettings(1, 4, 1200, Path("/data/runs"), Path("/data/cache"))
PARSE = ParseLimits(700, 6144)


def cgroup(tmp_path, **files):
    for relative, text in files.items():
        path = tmp_path / relative.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="ascii")
    return tmp_path


MB100 = 100 * 1024 * 1024


def test_the_minimum_is_the_pool_times_the_parse_limit_plus_the_uploads_plus_the_servers_own_use():
    assert SERVER_ALLOWANCE_MB == 1536
    assert minimum_container_mb(API, PARSE) == 6144 + 500 + 1536 == 8180  # five places of 100 MB in the tmpfs, which is memory
    assert minimum_container_mb(ApiSettings(3, 4, 1200, Path("/a"), Path("/b")), PARSE) == 3 * 6144 + 7 * 100 + 1536
    assert minimum_container_mb(API, ParseLimits(700, 2048)) == 2048 + 500 + 1536


def test_the_uploads_are_one_place_per_run_going_waiting_or_arriving_each_up_to_the_file_size_limit():
    assert uploads_mb(API, MB100) == 5 * 100
    assert uploads_mb(ApiSettings(1, 0, 1200, Path("/a"), Path("/b")), MB100) == 100
    assert uploads_mb(ApiSettings(2, 10, 1200, Path("/a"), Path("/b")), 25 * 1024 * 1024) == 12 * 25
    assert uploads_mb(API, 1) == 5 and uploads_mb(API, 1024 * 1024 + 1) == 10  # a partial megabyte counts as a whole one: the sum errs on the safe side


def test_the_size_given_to_the_tmpfs_is_not_what_is_counted_only_what_the_service_can_hold_in_it():
    from credit_intel.config import IngestionSettings

    assert minimum_container_mb(API, PARSE) == minimum_container_mb(API, PARSE, IngestionSettings().max_file_bytes)  # the default is the real file-size limit
    assert minimum_container_mb(API, PARSE, 10 * 1024 * 1024) == 6144 + 50 + 1536


def test_the_cgroup_files_are_read_by_their_real_names(tmp_path):
    (tmp_path / "memory.max").write_text(f"{8 * 1024**3}\n", encoding="ascii")
    assert container_memory_limit_mb(tmp_path) == 8192


def test_a_version_2_limit_of_max_means_no_limit(tmp_path):
    (tmp_path / "memory.max").write_text("max\n", encoding="ascii")
    assert container_memory_limit_mb(tmp_path) is None


def test_a_version_1_limit_is_read_and_a_huge_one_means_no_limit(tmp_path):
    folder = tmp_path / "memory"
    folder.mkdir()
    (folder / "memory.limit_in_bytes").write_text(f"{4 * 1024**3}\n", encoding="ascii")
    assert container_memory_limit_mb(tmp_path) == 4096
    (folder / "memory.limit_in_bytes").write_text("9223372036854771712\n", encoding="ascii")
    assert container_memory_limit_mb(tmp_path) is None


def test_version_2_is_looked_at_before_version_1(tmp_path):
    (tmp_path / "memory.max").write_text(f"{2 * 1024**3}\n", encoding="ascii")
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "memory.limit_in_bytes").write_text(f"{4 * 1024**3}\n", encoding="ascii")
    assert container_memory_limit_mb(tmp_path) == 2048


@pytest.mark.parametrize("text", ["", "garbage", "-5", "1.5e9", "12 MB", "\x00"])
def test_a_file_that_is_not_a_number_is_no_limit(tmp_path, text):
    (tmp_path / "memory.max").write_bytes(text.encode("ascii"))
    assert container_memory_limit_mb(tmp_path) is None


def test_no_cgroup_at_all_is_no_limit(tmp_path):
    assert container_memory_limit_mb(tmp_path / "absent") is None


def test_a_limit_at_the_minimum_is_accepted_and_one_megabyte_less_is_refused():
    needed = minimum_container_mb(API, PARSE)
    check_container_memory(API, PARSE, needed)
    check_container_memory(API, PARSE, needed + 1)
    with pytest.raises(IngestionError) as error:
        check_container_memory(API, PARSE, needed - 1)
    assert error.value.code is ErrorCode.CONFIG_INVALID
    text = str(error.value)
    assert f"{needed - 1} MB" in text and f"{needed} MB" in text and "api.max_concurrent_runs" in text and "uploads" in text


def test_the_uploads_decide_the_outcome_a_limit_that_covers_the_pool_and_the_server_but_not_the_uploads_is_refused():
    without_uploads = 6144 + 1536  # the sum before the tmpfs was counted
    check_container_memory(API, PARSE, without_uploads + uploads_mb(API, MB100))
    with pytest.raises(IngestionError):
        check_container_memory(API, PARSE, without_uploads)
    with pytest.raises(IngestionError):
        check_container_memory(API, PARSE, without_uploads + uploads_mb(API, MB100) - 1)
    smaller = 20 * 1024 * 1024
    check_container_memory(API, PARSE, without_uploads + uploads_mb(API, smaller), smaller)  # a smaller file-size limit needs less
    with pytest.raises(IngestionError):
        check_container_memory(API, PARSE, without_uploads + uploads_mb(API, smaller) - 1, smaller)


def test_no_known_limit_is_not_refused():
    check_container_memory(API, PARSE, None)


# --- the launcher -----------------------------------------------------------------------------------------------------------------------------


def settings_file(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000\n[ingestion]\nparse_timeout_seconds = 700\nparse_memory_mb = 6144\n'
                    "[api]\nmax_concurrent_runs = 1\nmax_queued_runs = 4\nrun_timeout_seconds = 1200\n", encoding="utf-8")
    return path


def env(tmp_path):
    return {"CREDIT_INTEL_API_OUTPUT_DIR": str(tmp_path / "out"), "CREDIT_INTEL_API_CACHE_DIR": str(tmp_path / "cache")}


def start(tmp_path, limit):
    served, err = [], io.StringIO()
    code = launcher.main(["--config", str(settings_file(tmp_path))], env=env(tmp_path), stderr=err, serve=lambda *a: served.append(a), container_limit=lambda: limit)
    return code, served, err.getvalue()


def test_the_launcher_refuses_to_start_in_a_container_below_the_pool_and_says_the_two_numbers(tmp_path):
    code, served, err = start(tmp_path, 4096)
    assert code == 6 and served == [] and err.startswith("E-CONFIG-INVALID: ") and "4096 MB" in err and "8180 MB" in err


def test_the_launcher_starts_at_the_minimum_and_with_no_known_limit(tmp_path):
    for limit in (8180, 8181, None):
        code, served, err = start(tmp_path, limit)
        assert (code, len(served), err) == (0, 1, ""), limit


def test_the_launcher_reads_the_container_limit_after_the_settings_and_a_missing_parse_limit_stops_it(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000\n[api]\nmax_concurrent_runs = 1\nmax_queued_runs = 4\nrun_timeout_seconds = 1200\n', encoding="utf-8")
    served, err = [], io.StringIO()
    code = launcher.main(["--config", str(path)], env=env(tmp_path), stderr=err, serve=lambda *a: served.append(a), container_limit=lambda: None)
    assert code == 6 and served == [] and "E-CONFIG-INVALID" in err.getvalue() and "ingestion.parse_" in err.getvalue()
