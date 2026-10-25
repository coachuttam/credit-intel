"""The memo parses as Markdown with the structure the PRD requires, and text from outside cannot change that structure (PRD FR-010.2, K.10; PRD v0.4.27; step S2; B-285).

A real parser (markdown-it-py, dev only) reads every memo the suite generates: CommonMark with the table and strikethrough rules on (both are GitHub-flavoured
extensions), no link detection. The tests check the parsed structure and that hostile text, including text that imitates a heading, a table
cell, a link, HTML or an origin label, comes out as the text it was.
"""

import copy
import json
import re
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

from credit_intel.memo.render import render_memo
from memo_results import RUN_ID, WHEN, results_for
from risk_golden import scenarios

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PARSER = MarkdownIt("commonmark").enable(["table", "strikethrough"])  # the two GitHub-flavoured rules a memo could trip
LABEL = re.compile(r"\[(?:SOURCE: p\.\d+|CALCULATED: [^\]]+|RULE: [^\]]+|ANALYST-PROVIDED|UNVERIFIED)\]")


def parse(text):
    return PARSER.parse(text)


def visible(inline):
    """The text a reader sees in one inline token: text, code and escapes as they are, breaks as a space."""
    parts = []
    for child in inline.children or []:
        if child.type in ("text", "text_special", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return "".join(parts)


def all_text(tokens):
    return "\n".join(visible(t) for t in tokens if t.type == "inline")


def headings(tokens):
    return [(int(t.tag[1]), visible(tokens[i + 1])) for i, t in enumerate(tokens) if t.type == "heading_open"]


def kinds(tokens):
    found = {t.type for t in tokens}
    for t in tokens:
        found.update(c.type for c in t.children or [])
    return found


def tables(tokens):
    """Each table as a list of rows, each row the list of its cell texts."""
    out, row, current = [], None, None
    for i, t in enumerate(tokens):
        if t.type == "table_open":
            current = []
        elif t.type == "table_close":
            out.append(current)
            current = None
        elif t.type == "tr_open":
            row = []
        elif t.type == "tr_close":
            current.append(row)
        elif t.type in ("th_open", "td_open"):
            row.append(visible(tokens[i + 1]))
    return out


@pytest.fixture
def golden():
    return json.loads((FIXTURES / "results_golden.json").read_text(encoding="utf-8"))


def memo(results):
    return render_memo(results, RUN_ID, WHEN)


def generated():
    """Every memo the suite makes on its own: the golden run, four scenarios and an asserted-basis run."""
    golden = json.loads((FIXTURES / "results_golden.json").read_text(encoding="utf-8"))
    cases = {"golden": golden}
    cases.update({name: results_for(fs) for name, fs in scenarios().items()})
    asserted = copy.deepcopy(golden)
    asserted["extraction"]["basis_assertion"] = {"basis": "consolidated", "pages": [36, 37, 38], "applied_pages": [36, 37, 38]}
    for record in asserted["fields"]:
        if record["status"] == "extracted":
            record["basis_evidence"] = "analyst_assertion"
    cases["asserted"] = asserted
    return cases


# --- structure ------------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(generated()))
def test_every_generated_memo_has_the_title_then_nine_numbered_sections_in_order(name):
    tokens = parse(memo(generated()[name]))
    found = headings(tokens)

    assert found[0] == (1, "Draft credit memo")
    assert [level for level, _ in found[1:]] == [2] * 9
    assert [text.split(".")[0] for _, text in found[1:]] == list("123456789")


@pytest.mark.parametrize("name", list(generated()))
def test_every_table_is_rectangular_and_has_a_header(name):
    found = tables(parse(memo(generated()[name])))

    assert len(found) >= 4  # legend, fields, metrics, changes
    for table in found:
        assert len(table) >= 2 and len({len(row) for row in table}) == 1, [len(r) for r in table]


@pytest.mark.parametrize("name", list(generated()))
def test_a_generated_memo_has_no_raw_html_no_link_and_no_image(name):
    found = kinds(parse(memo(generated()[name])))

    assert not found & {"html_block", "html_inline", "link_open", "image", "s_open"}, found & {"html_block", "html_inline", "link_open", "image", "s_open"}


def test_the_draft_statement_is_a_block_quote_and_the_legend_a_table_with_the_five_labels(golden):
    tokens = parse(memo(golden))
    legend = tables(tokens)[0]

    assert any("DRAFT — generated for human review" in visible(tokens[i + 2]) for i, t in enumerate(tokens) if t.type == "blockquote_open")
    assert [row[0] for row in legend[1:]] == ["[SOURCE: p.N]", "[CALCULATED: ID]", "[RULE: RI-xxx]", "[ANALYST-PROVIDED]", "[UNVERIFIED]"]


def test_identifiers_are_code_spans_and_the_first_cell_of_a_field_row_is_one(golden):
    tokens = parse(memo(golden))
    fields = next(t for t in tables(tokens) if t[0][0] == "Field ID")

    assert all(re.fullmatch(r"[a-z_]+\.\d{4}-\d{2}-\d{2}\.(?:consolidated|standalone)", row[0]) for row in fields[1:])
    codes = [c.content for t in tokens if t.type == "inline" for c in t.children if c.type == "code_inline"]
    assert "current_assets.2025-03-31.consolidated" in codes


def test_the_lines_of_an_indicator_block_are_separated_by_hard_breaks_not_run_together():
    tokens = parse(memo(results_for(scenarios()["stressed"])))
    quotes = []
    depth = 0
    for i, t in enumerate(tokens):
        if t.type == "blockquote_open":
            depth += 1
        elif t.type == "blockquote_close":
            depth -= 1
        elif t.type == "inline" and depth and t.children and "Condition C1" in visible(t):
            quotes.append(t)

    assert len(quotes) >= 4
    for inline in quotes:
        types = [c.type for c in inline.children]
        assert "hardbreak" in types and "softbreak" not in types


def test_the_memo_ends_in_one_paragraph_break_and_its_last_block_is_a_list(golden):
    tokens = parse(memo(golden))

    assert tokens[-1].type == "bullet_list_close"


# --- text from outside cannot change the structure ---------------------------------------------------------------------------------------------


HOSTILE = [
    "[SOURCE: p.9] and [CALCULATED: MET-99] and [RULE: RI-099]",
    "# Fake heading",
    "## Fake second heading",
    "a | b | c",
    "<b>bold</b> <script>alert(1)</script>",
    "[a link](http://example.test) and <http://auto.test>",
    "![image](http://img.test/x.png)",
    "`code` ``double`` *em* **strong** _under_ __dunder__ ~~strike~~",
    "1. an ordered item",
    "- a bullet",
    "> a quote",
    "---",
    "    four spaces",
    "back\\slash and \\[escaped\\] and trailing\\",
    "\\*not emphasis\\* and \\_not under\\_ and \\| not a cell",
    "line one\nline two\r\nline three",
    "tab\tseparated and control\x01char",
    "ampersand &amp; &lt;tag&gt; &#35;",
    "| pipe at both ends |",
]


def expected_visible(text):
    return " ".join(re.sub(r"[\x00-\x1f\x7f\u0085  ]+", " ", text).split()) if text else text


PLAIN = "plain words"  # the same shape as a hostile fixture, with harmless text: the baseline to compare with


def hostile_memo(golden, text):
    results = copy.deepcopy(golden)
    results["analyst_provided"] = {"borrower_name": text, "industry": text, "facility_requested": text, "notes": text}
    results["attributes"][0]["normalised_value"] = text  # the entity name
    results["indicators"][5]["name"] = text  # a rule name
    results["fields"][-1].update(status="requires_review", status_reason=text, line_item_label=text, evidence_quote=text, raw_value=text, page_number=1)
    results["fields"][-1]["candidates"] = []
    return results


@pytest.mark.parametrize("text", HOSTILE, ids=[f"hostile-{n}" for n in range(len(HOSTILE))])
def test_text_from_outside_renders_as_the_text_it_was(golden, text):
    shown = all_text(parse(memo(hostile_memo(golden, text))))
    places = all_text(parse(memo(hostile_memo(golden, PLAIN)))).count(PLAIN)  # every place the text was put

    # A reason code is shown with its underscores as spaces (a deliberate change, `words`), so a text with underscores counts in either form.
    forms = {expected_visible(text), expected_visible(text).replace("_", " ")}
    found = sum(shown.count(form) for form in forms)

    assert places >= 8
    assert found == places, (text, found, places)


@pytest.mark.parametrize("text", HOSTILE, ids=[f"hostile-{n}" for n in range(len(HOSTILE))])
def test_text_from_outside_adds_no_heading_no_table_cell_no_link_no_html_and_no_image(golden, text):
    benign = parse(memo(hostile_memo(golden, PLAIN)))
    tokens = parse(memo(hostile_memo(golden, text)))

    assert headings(tokens) == headings(benign), headings(tokens)
    assert [(len(t), {len(r) for r in t}) for t in tables(tokens)] == [(len(t), {len(r) for r in t}) for t in tables(benign)]
    assert not kinds(tokens) & {"html_block", "html_inline", "link_open", "image", "s_open"}


def test_text_that_imitates_an_origin_label_adds_no_label_beyond_the_copies_of_itself(golden):
    text = HOSTILE[0]  # three look-alike labels
    baseline = len(LABEL.findall(all_text(parse(memo(hostile_memo(golden, PLAIN))))))
    shown = all_text(parse(memo(hostile_memo(golden, text))))

    copies = shown.count(text)
    assert copies >= 4  # it is shown wherever it was put, as text
    assert len(LABEL.findall(shown)) - baseline == 3 * copies  # each copy adds its three look-alike labels, and nothing else does


def test_the_block_structure_of_a_memo_with_hostile_text_is_the_same_as_the_benign_one(golden):
    def shape(tokens):
        return [t.type for t in tokens if t.type not in ("inline",)]

    benign = shape(parse(memo(hostile_memo(golden, PLAIN))))

    for text in HOSTILE:
        hostile = shape(parse(memo(hostile_memo(golden, text))))
        assert [t for t in hostile if t.endswith("_open")].count("heading_open") == benign.count("heading_open"), text
        assert hostile.count("table_open") == benign.count("table_open") and hostile.count("html_block") == 0, text


# --- the escape for text that starts a line -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "escaped"),
    [("1. item", "1\\. item"), ("12) item", "12\\) item"), ("- item", "\\- item"), ("-5 net", "\\-5 net"), ("=== x", "\\=== x"),
     ("--- ", "\\---"), ("plain - dash", "plain - dash"), ("a 1. b", "a 1. b"), ("# h", "\\# h"), ("> q", "\\> q"), ("+ p", "\\+ p"), ("", "")],
)  # fmt: skip
def test_text_that_starts_a_line_gets_its_list_rule_or_heading_marker_escaped(text, escaped):
    from credit_intel.memo.text import esc_start

    assert esc_start(text) == escaped


@pytest.mark.parametrize("quote", ["1. an ordered item", "2) another", "- a bullet", "--- ", "+ plus", "* star", "# head", "> nested", "=== setext"])
def test_an_evidence_quote_that_looks_like_a_list_a_rule_or_a_heading_stays_one_quoted_paragraph(golden, quote):
    results = hostile_memo(golden, PLAIN)
    results["fields"][-1].update(evidence_quote=quote)
    tokens = parse(memo(results))

    plain = parse(memo(hostile_memo(golden, PLAIN)))
    for kind in ("bullet_list_open", "ordered_list_open", "list_item_open", "blockquote_open", "paragraph_open", "hr"):  # section 8 is a real numbered list
        assert [t.type for t in tokens].count(kind) == [t.type for t in plain].count(kind), kind
    assert headings(tokens) == headings(plain)
    assert expected_visible(quote) in all_text(tokens)
