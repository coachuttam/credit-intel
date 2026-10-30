"""An image is told its commit when it is built, so the manifest still says which code ran (PRD FR-012.1; Phase 7 step 1, finding F-8)."""

import pytest

from credit_intel.export.manifest import ENV_BUILD_COMMIT, REPOSITORY, CodeVersion, code_version

SHA = "0123456789abcdef0123456789abcdef01234567"


def test_outside_a_checkout_the_commit_comes_from_the_build_argument_and_the_tree_state_is_unknown(tmp_path):
    assert code_version(tmp_path, {ENV_BUILD_COMMIT: SHA}) == CodeVersion(SHA, None)


def test_without_a_checkout_and_without_the_argument_nothing_is_claimed(tmp_path):
    assert code_version(tmp_path, {}) == CodeVersion(None, None)


@pytest.mark.parametrize("bad", ["", "abc", SHA[:-1], SHA + "0", SHA.upper(), "g" * 40, SHA + "\n", " " + SHA, "HEAD", "0" * 39 + "\x00"])
def test_a_value_that_is_not_a_full_lower_case_sha_is_ignored(tmp_path, bad):
    assert code_version(tmp_path, {ENV_BUILD_COMMIT: bad}) == CodeVersion(None, None)


def test_in_a_checkout_git_wins_over_the_argument():
    version = code_version(REPOSITORY, {ENV_BUILD_COMMIT: SHA})
    if version.git_commit is not None:  # git is installed and this is a checkout
        assert version.git_commit != SHA and version.dirty is not None


def test_the_variable_is_named_for_the_build_and_the_process_environment_is_the_default(tmp_path, monkeypatch):
    assert ENV_BUILD_COMMIT == "CREDIT_INTEL_BUILD_COMMIT"
    monkeypatch.setenv(ENV_BUILD_COMMIT, SHA)
    assert code_version(tmp_path) == CodeVersion(SHA, None)
