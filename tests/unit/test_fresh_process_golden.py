"""Fresh-process golden-output test for page extraction (PRD FR-002.3, O.1 regression (a); B-120).

A fixed synthetic PDF is generated at test time (never committed) and extracted
in a separate Python process, so state held by the test process cannot make two
runs look identical. The extracted ``(page_number, page_label, text)`` rows must
match, byte for byte, the reviewed golden output in
``tests/fixtures/page_extraction_golden.json``.

The golden file is ASCII-only JSON (non-ASCII text appears as ``\\uXXXX``), so a
diff shows exactly which character changed. It is regenerated only in a
reviewed change: run the child script below on the PDF this test builds and
inspect the result before committing it.
"""

import json
import subprocess
import sys
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "page_extraction_golden.json"

# Page 2 is blank. Pages carry roman (i, ii) then arabic (1, 2) labels. Page 3 has
# several lines; page 4 has non-ASCII text (WinAnsi, which reportlab can draw).
PAGES = [
    "Cover",
    "",
    "Balance Sheet as at 31 March 2025\nTotal assets 1,740.00\nTotal equity (600.00)",
    "Directors' report\nCafé – naïve résumé",
]
PAGE_LABELS = [(0, "ROMAN_LOWER", 1), (2, "ARABIC", 1)]

# Runs in the child process: ingest the PDF and print the rows as ASCII JSON.
CHILD_SCRIPT = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "from credit_intel.ingestion.ingest import ingest\n"
    "document = ingest(Path(sys.argv[1]))\n"
    "rows = [[p.page_number, p.page_label, p.text] for p in document.pages]\n"
    "sys.stdout.buffer.write((json.dumps(rows, indent=2, ensure_ascii=True) + '\\n').encode('ascii'))\n"
)


def extract_in_fresh_process(pdf_path: Path) -> bytes:
    result = subprocess.run(
        [sys.executable, "-I", "-c", CHILD_SCRIPT, str(pdf_path)],
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


def test_fresh_process_extraction_matches_the_golden_output(make_pdf):
    path = make_pdf(PAGES, page_labels=PAGE_LABELS)

    assert extract_in_fresh_process(path) == GOLDEN.read_bytes()


def test_golden_output_covers_blank_page_labels_and_multiline_text():
    rows = json.loads(GOLDEN.read_bytes())

    assert [row[0] for row in rows] == [1, 2, 3, 4]
    assert [row[1] for row in rows] == ["i", "ii", "1", "2"]
    assert rows[1][2] == ""  # the blank page is kept, with empty text
    assert rows[2][2].count("\n") == 2  # three lines on one page
    assert any(ord(char) > 127 for char in rows[3][2])  # non-ASCII text survives
