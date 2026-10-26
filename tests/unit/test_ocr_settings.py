"""OCR settings loader and the --ocr flag (PRD v0.4.44, FR-001A; OD-14, OD-18; B-316).

Step 1a of the OCR build: the settings are read and checked, and nothing else happens yet. OCR is off unless the table or
the flag turns it on; once on, every setting except the DPI is required and has no default.
"""

import pytest

from credit_intel.cli import main
from credit_intel.config import OCR_REQUIRED_WHEN_ENABLED, OCR_SETTING_NAMES, OcrSettings, load_ocr_settings
from credit_intel.ingestion.errors import ErrorCode, IngestionError

FULL = (
    "[ocr]\nenabled = true\ndpi = 200\nmin_image_area_share = 0.5\nmax_pages = 20\ntimeout_seconds = 90\n"
    "column_margin_pt = 4\nsplit_figure_gap_pt = 2.5\n"
)
LLM = '[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 50000\nmax_output_tokens = 4096\n'


def write(tmp_path, text):
    path = tmp_path / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return path


def fails(path, flag=False):
    with pytest.raises(IngestionError) as excinfo:
        load_ocr_settings(path, flag)
    assert excinfo.value.code is ErrorCode.CONFIG_INVALID
    return str(excinfo.value.detail)


def test_no_table_and_no_flag_is_off_with_nothing_set(tmp_path):
    assert load_ocr_settings(write(tmp_path, LLM)) == OcrSettings()
    assert not OcrSettings().enabled and OcrSettings().dpi == 300
    assert all(getattr(OcrSettings(), name) is None for name in OCR_REQUIRED_WHEN_ENABLED)


def test_a_full_table_is_read_as_given(tmp_path):
    got = load_ocr_settings(write(tmp_path, FULL))
    assert got == OcrSettings(True, 200, 0.5, 20, 90.0, 4.0, 2.5)


def test_the_flag_turns_it_on_and_then_everything_but_the_dpi_is_required(tmp_path):
    path = write(tmp_path, FULL.replace("enabled = true\n", ""))
    assert load_ocr_settings(path, flag=True).enabled and not load_ocr_settings(path).enabled
    assert fails(write(tmp_path, LLM), flag=True) == "ocr.min_image_area_share"


@pytest.mark.parametrize("name", OCR_REQUIRED_WHEN_ENABLED)
def test_each_required_setting_missing_is_named(tmp_path, name):
    text = "".join(line + "\n" for line in FULL.splitlines() if not line.startswith(f"{name} "))
    assert fails(write(tmp_path, text)) == f"ocr.{name}"


def test_the_dpi_alone_may_be_missing(tmp_path):
    text = "".join(line + "\n" for line in FULL.splitlines() if not line.startswith("dpi "))
    assert load_ocr_settings(write(tmp_path, text)).dpi == 300


def test_nothing_is_required_while_off_but_a_present_value_is_checked(tmp_path):
    assert load_ocr_settings(write(tmp_path, "[ocr]\nenabled = false\nmax_pages = 20\n")).max_pages == 20
    assert fails(write(tmp_path, "[ocr]\nmax_pages = 0\n")) == "ocr.max_pages"


@pytest.mark.parametrize(
    ("line", "setting"),
    [
        ("enabled = 1", "ocr.enabled"),
        ('enabled = "true"', "ocr.enabled"),
        ("dpi = 0", "ocr.dpi"),
        ("dpi = true", "ocr.dpi"),
        ("dpi = 300.5", "ocr.dpi"),
        ("min_image_area_share = 0", "ocr.min_image_area_share"),
        ("min_image_area_share = 1.5", "ocr.min_image_area_share"),
        ("min_image_area_share = true", "ocr.min_image_area_share"),
        ("max_pages = -1", "ocr.max_pages"),
        ("max_pages = 2.5", "ocr.max_pages"),
        ("max_pages = true", "ocr.max_pages"),
        ("timeout_seconds = 0", "ocr.timeout_seconds"),
        ('timeout_seconds = "9"', "ocr.timeout_seconds"),
        ("column_margin_pt = -3", "ocr.column_margin_pt"),
        ("split_figure_gap_pt = -1", "ocr.split_figure_gap_pt"),
        ("split_figure_gap_pt = false", "ocr.split_figure_gap_pt"),
        ("unknown = 1", "ocr.unknown"),
    ],
)
def test_an_invalid_setting_is_named_and_its_value_is_not_echoed(tmp_path, line, setting):
    key = line.split(" = ")[0]
    text = "[ocr]\n" + "".join(l + "\n" for l in FULL.splitlines()[1:] if not l.startswith(f"{key} ")) + line + "\n"
    assert fails(write(tmp_path, text)) == setting


def test_a_table_that_is_not_a_table_is_invalid(tmp_path):
    assert fails(write(tmp_path, "ocr = 3\n")) == "ocr"


def test_an_unreadable_settings_file_is_invalid(tmp_path):
    assert fails(tmp_path / "missing.toml") == "settings file"


def test_every_setting_name_is_covered_by_the_full_table():
    for name in OCR_SETTING_NAMES:
        assert f"{name} = " in FULL


# --- the command line ----------------------------------------------------------------------------------------------


def run(tmp_path, settings_text, *flags):
    from io import StringIO

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out, err = StringIO(), StringIO()
    code = main([str(pdf), "--config", str(write(tmp_path, settings_text)), "--output-dir", str(tmp_path / "runs"), *flags],
                stdout=out, stderr=err, env={})
    return code, err.getvalue()


def test_the_flag_with_incomplete_settings_is_a_configuration_error(tmp_path):
    code, err = run(tmp_path, LLM, "--ocr")
    assert code == 6 and "E-CONFIG-INVALID" in err and "ocr.min_image_area_share" in err


def test_a_bad_ocr_table_is_an_error_even_without_the_flag(tmp_path):
    code, err = run(tmp_path, LLM + "[ocr]\nmax_pages = 0\n")
    assert code == 6 and "ocr.max_pages" in err


def test_without_the_flag_or_the_table_nothing_about_ocr_is_said(tmp_path):
    _, err = run(tmp_path, LLM)
    assert "ocr" not in err.lower()


def test_with_valid_settings_the_run_goes_on_and_says_nothing_about_ocr_not_being_built(tmp_path):
    for flags, text in (("--ocr",), LLM + FULL), ((), LLM + FULL):  # the flag, or the table alone, turns it on
        code, err = run(tmp_path, text, *flags)
        assert "not built yet" not in err and "E-CONFIG-INVALID" not in err and code == 3  # on to the (empty) file: E-INPUT-CORRUPT


# --- the values shipped in config/settings.toml (owner, 2026-10-27) -------------------------------------------------------


from pathlib import Path  # noqa: E402

REPO_SETTINGS = Path(__file__).resolve().parents[2] / "config" / "settings.toml"


def test_a_gap_of_zero_is_accepted_and_means_joining_is_off(tmp_path):
    got = load_ocr_settings(write(tmp_path, FULL.replace("split_figure_gap_pt = 2.5", "split_figure_gap_pt = 0")))
    assert got.split_figure_gap_pt == 0.0


def test_the_shipped_settings_leave_ocr_off_and_hold_the_owner_values():
    got = load_ocr_settings(REPO_SETTINGS)
    assert not got.enabled
    assert (got.min_image_area_share, got.column_margin_pt, got.split_figure_gap_pt) == (0.5, 3.0, 0.0)
    assert (got.max_pages, got.timeout_seconds, got.dpi) == (10, 120.0, 300)


def test_with_ocr_on_the_shipped_settings_are_complete():
    got = load_ocr_settings(REPO_SETTINGS, flag=True)
    assert got.enabled and all(getattr(got, name) is not None for name in OCR_REQUIRED_WHEN_ENABLED)


def test_removing_the_page_cap_or_the_time_limit_from_the_shipped_settings_is_named(tmp_path):
    text = REPO_SETTINGS.read_text(encoding="utf-8")
    for name in ("max_pages", "timeout_seconds"):
        stripped = "".join(line + "\n" for line in text.splitlines() if not line.startswith(f"{name} "))
        assert fails(write(tmp_path, stripped), flag=True) == f"ocr.{name}"
