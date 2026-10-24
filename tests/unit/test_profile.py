"""The analyst profile file (PRD FR-014.7, G.1; Phase 5 step 5b; B-255)."""

import ast
import json
from pathlib import Path

import pytest

from credit_intel.ingestion.errors import CATALOGUE, ErrorCode, IngestionError, exit_code
from credit_intel.profile import LABEL, MAX_FILE_BYTES, MAX_VALUE_CHARACTERS, PROFILE_KEYS, Profile, load_profile

SECRET = "secret-value-424242"


def write(tmp_path, content, name="profile.json"):
    path = tmp_path / name
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


def refused(tmp_path, content) -> IngestionError:
    with pytest.raises(IngestionError) as excinfo:
        load_profile(write(tmp_path, content))
    assert excinfo.value.code is ErrorCode.PROFILE_INVALID
    return excinfo.value


# --- a valid profile ------------------------------------------------------------------------------------------------------------------------------


def test_all_four_keys_are_read(tmp_path):
    body = {"borrower_name": "Acme Industries Ltd", "industry": "Manufacturing", "facility_requested": "Term loan, 50 crore", "notes": "Meeting on 3 May."}

    profile = load_profile(write(tmp_path, json.dumps(body)))

    assert profile.items() == tuple(body.items()) and profile.file_name == "profile.json"


def test_every_key_is_optional_and_an_empty_object_is_a_profile(tmp_path):
    assert load_profile(write(tmp_path, "{}")).items() == ()
    assert load_profile(write(tmp_path, '{"notes": "x"}')).items() == (("notes", "x"),)


def test_items_come_in_the_fixed_key_order_whatever_the_file_order(tmp_path):
    profile = load_profile(write(tmp_path, '{"notes": "n", "borrower_name": "b", "industry": "i"}'))

    assert [k for k, _ in profile.items()] == ["borrower_name", "industry", "notes"]


def test_values_are_kept_exactly_including_spaces_and_non_ascii_text(tmp_path):
    profile = load_profile(write(tmp_path, json.dumps({"borrower_name": "  Café – Tata  ", "notes": ""}, ensure_ascii=False)))

    assert profile.borrower_name == "  Café – Tata  " and profile.notes == ""


def test_the_manifest_gets_the_file_name_only_not_the_directory(tmp_path):
    profile = load_profile(write(tmp_path, "{}", name="borrower_profile.json"))

    assert profile.file_name == "borrower_profile.json" and str(tmp_path) not in profile.file_name


def test_the_label_and_the_key_list_are_the_prds():
    assert LABEL == "[ANALYST-PROVIDED]" and PROFILE_KEYS == ("borrower_name", "industry", "facility_requested", "notes")
    assert MAX_VALUE_CHARACTERS == 500


def test_a_profile_is_immutable():
    profile = Profile("p.json", borrower_name="x")

    with pytest.raises(AttributeError):
        profile.borrower_name = "y"  # type: ignore[misc]


# --- the length limit ------------------------------------------------------------------------------------------------------------------------------


def test_a_value_of_exactly_500_characters_is_accepted_and_501_is_refused(tmp_path):
    assert len(load_profile(write(tmp_path, json.dumps({"notes": "a" * 500}))).notes) == 500
    error = refused(tmp_path, json.dumps({"notes": "a" * 501}))
    assert error.detail == "the value of notes is longer than 500 characters"


def test_the_limit_counts_characters_not_bytes(tmp_path):
    assert len(load_profile(write(tmp_path, json.dumps({"notes": "é" * 500}, ensure_ascii=False))).notes) == 500  # 1,000 bytes
    refused(tmp_path, json.dumps({"notes": "é" * 501}, ensure_ascii=False))


@pytest.mark.parametrize("key", PROFILE_KEYS)
def test_the_limit_applies_to_each_key_and_names_it(tmp_path, key):
    error = refused(tmp_path, json.dumps({key: "x" * 501}))

    assert error.detail == f"the value of {key} is longer than 500 characters"


# --- everything else is refused with E-INPUT-PROFILE-INVALID ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("content", ["", "not json", "{", '{"notes": "x"', '{"notes": "x"} trailing', "{'notes': 'x'}", '{"notes": "x",}', '{"notes": NaN'])
def test_invalid_json_is_refused(tmp_path, content):
    assert refused(tmp_path, content).detail == "the file is not valid JSON or repeats a key"


@pytest.mark.parametrize("content", ["[]", '["notes"]', '"notes"', "5", "true", "null", "NaN", '[{"notes": "x"}]'])
def test_a_value_that_is_not_an_object_is_refused(tmp_path, content):
    assert refused(tmp_path, content).detail == "the profile must be a JSON object"


@pytest.mark.parametrize("key", ["name", "Notes", "borrower", "extra", "", "notes ", "facility"])
def test_an_unknown_key_is_refused_and_not_echoed(tmp_path, key):
    error = refused(tmp_path, json.dumps({key: "x", "notes": "n"}))

    assert error.detail == "the profile has a key that is not allowed"


def test_an_unknown_key_is_not_echoed_even_when_it_is_long_or_odd(tmp_path):
    error = refused(tmp_path, json.dumps({SECRET: "x"}))

    assert SECRET not in str(error) and SECRET not in (error.detail or "")


@pytest.mark.parametrize("value", ["5", "1.5", "true", "false", "null", '["a"]', '{"a": "b"}'])
def test_a_value_that_is_not_a_string_is_refused_and_names_the_key(tmp_path, value):
    error = refused(tmp_path, f'{{"industry": {value}}}')

    assert error.detail == "the value of industry is not a string"


def test_a_repeated_key_is_refused(tmp_path):
    assert refused(tmp_path, '{"notes": "a", "notes": "b"}').detail == "the file is not valid JSON or repeats a key"


def test_a_file_that_is_not_utf8_is_refused(tmp_path):
    assert refused(tmp_path, b'{"notes": "\xff"}').detail == "the file is not UTF-8"


def test_a_byte_order_mark_is_refused_as_invalid_json(tmp_path):
    assert refused(tmp_path, b"\xef\xbb\xbf" + b'{"notes": "x"}').detail == "the file is not valid JSON or repeats a key"


def test_a_file_larger_than_the_cap_is_refused_without_being_parsed(tmp_path):
    error = refused(tmp_path, '{"notes": "' + "a" * MAX_FILE_BYTES + '"}')

    assert error.detail == f"the file is larger than {MAX_FILE_BYTES} bytes"


def test_a_missing_file_or_a_directory_is_refused(tmp_path):
    for target in (tmp_path / "absent.json", tmp_path):
        with pytest.raises(IngestionError) as excinfo:
            load_profile(target)
        assert excinfo.value.code is ErrorCode.PROFILE_INVALID and excinfo.value.detail == "the file cannot be read"


def test_the_error_never_echoes_a_value_or_a_path(tmp_path):
    for content in (json.dumps({"notes": SECRET + "a" * 600}), json.dumps({"industry": [SECRET]}), '{"notes": "' + SECRET, SECRET):
        error = refused(tmp_path, content)
        assert SECRET not in str(error) and str(tmp_path) not in str(error)


def test_a_refusal_has_the_catalogued_exit_code_and_message(tmp_path):
    error = refused(tmp_path, "[]")

    assert exit_code(error) == 3 and CATALOGUE[ErrorCode.PROFILE_INVALID].action in str(error)


@pytest.mark.parametrize("content", ["{", b'{"notes": "\xff"}'])
def test_the_underlying_error_stays_on_the_cause(tmp_path, content):
    assert refused(tmp_path, content).__cause__ is not None


def test_a_path_that_is_not_a_regular_file_is_refused_before_it_is_read(tmp_path, monkeypatch):
    path = write(tmp_path, '{"notes": "x"}')
    monkeypatch.setattr(Path, "is_file", lambda self: False)  # a pipe or device would look like this and could block a read

    with pytest.raises(IngestionError) as excinfo:
        load_profile(path)

    assert excinfo.value.detail == "the file cannot be read"


# --- profile values are never evidence, input to a calculation or input to a rule (FR-014.7) --------------------------------------------------------


@pytest.mark.parametrize("package", ["calculations", "extraction", "risk", "llm", "ingestion"])
def test_no_module_that_gathers_evidence_calculates_or_judges_imports_the_profile(package):
    root = Path(load_profile.__code__.co_filename).parent / package
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            assert not [n for n in names if n == "credit_intel.profile" or n == "profile"], (path.name, names)
