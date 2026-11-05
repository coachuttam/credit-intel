"""Memo sections 8 and 9: questions for the analyst, limitations and human review (PRD K.1-K.9 rows 8 and 9, FR-009.1, FR-009.5; step 5h; B-264)."""

import copy
import json
import re
from pathlib import Path

import pytest

from calc_records import conflicting
from credit_intel.memo import limitations, questions
from credit_intel.memo.questions import FIELD_NAMES, NONE_TEXT, page_phrase
from credit_intel.memo.render import render_memo
from credit_intel.models import FieldName as F
from memo_results import RUN_ID, WHEN, results_for
from risk_golden import scenarios

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
HOSTILE = "[SOURCE: p.9] # not a heading | not a cell `x` <i>y</i>"


def memo(results):
    return render_memo(results, RUN_ID, WHEN)


def section(results, number):
    text = memo(results)
    start = text.index(f"## {number}. ")
    later = [m.start() for m in re.finditer(r"^## \d+\. ", text, re.M) if m.start() > start]
    return text[start : later[0] if later else len(text)]


def asked(results):
    return questions.questions(results)


@pytest.fixture
def golden():
    return json.loads((FIXTURES / "results_golden.json").read_text(encoding="utf-8"))


def test_the_whole_memo_matches_the_reviewed_golden_file(golden):
    assert render_memo(golden, "20261024T101530.123456Z-0dd49919", "20261024T101530.123456Z") == (FIXTURES / "memo_golden.md").read_text(encoding="utf-8")


# --- section 8 ---------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("pages", "text"), [([], "the pages reviewed"), ([3], "page 3"), ([274, 275, 276, 277], "pages 274–277"),
                                             ([3, 5, 6, 9], "pages 3, 5–6, 9"), ([6, 5, 3], "pages 3, 5–6"), ([1, 2], "pages 1–2")])  # fmt: skip
def test_page_phrases(pages, text):
    assert page_phrase(pages) == text


def test_every_field_name_has_a_display_name():
    assert set(FIELD_NAMES) == {member.value for member in F}


def test_a_missing_field_gets_the_question_with_its_period_and_the_pages_reviewed(golden):
    golden["extraction"]["candidate_pages"] = [110, 111, 112, 113, 114, 115]
    revenue = [q for q in asked(golden) if q.startswith("Revenue")]

    assert revenue == [
        "Revenue for the period ending 2025-03-31 was not found on pages 110–115 (statement not in pages sent) — confirm the figure from the audited statements. [UNVERIFIED]",
        "Revenue for the period ending 2024-03-31 was not found on pages 110–115 (statement not in pages sent) — confirm the figure from the audited statements. [UNVERIFIED]"]  # fmt: skip


def test_fields_that_only_support_another_are_not_asked_about_when_absent(golden):
    text = "\n".join(asked(golden))

    assert "Operating profit" not in text and "Current maturities" not in text and "EBIT" not in text


def test_the_borrowing_components_are_not_asked_about_when_a_total_is_reported():
    fields = scenarios()["calm"]
    results = results_for(fields)
    results["fields"] = [f for f in results["fields"] if f["field_name"] not in ("borrowings_non_current", "borrowings_current")]
    results["derived_fields"] = [d for d in results["derived_fields"] if d["field_name"] != "total_borrowings"]
    results["fields"].append({**next(f for f in results["fields"]), "field_name": "total_borrowings", "field_id": "total_borrowings.2025-03-31.consolidated",
                              "period_end": "2025-03-31", "status": "extracted", "origin": "source"})  # fmt: skip
    for name in ("borrowings_non_current", "borrowings_current"):
        results["fields"].append({**results["fields"][0], "field_name": name, "field_id": f"{name}.2025-03-31.consolidated", "period_end": "2025-03-31",
                                  "status": "not_found", "origin": "source", "evidence_quote": None})  # fmt: skip
        results["fields"].append({**results["fields"][0], "field_name": name, "field_id": f"{name}.2024-03-31.consolidated", "period_end": "2024-03-31",
                                  "status": "not_found", "origin": "source", "evidence_quote": None})  # fmt: skip
    text = "\n".join(asked(results))

    assert "borrowings for the period ending 2024-03-31 was not found" in text  # no total for 2024
    assert "borrowings for the period ending 2025-03-31" not in text


def test_a_conflicting_field_asks_which_figure_is_correct_listing_the_candidates():
    results = results_for(scenarios()["calm"])
    conflict = results_for(__import__("risk_golden").field_set({F.REVENUE: "100"}, {F.REVENUE: "90"}, extra=[conflicting(F.NET_PROFIT, ["10", "12"])]))

    assert "Net profit for the period ending 2025-03-31 has conflicting values on the pages reviewed (10 on page 3; 12 on page 3). Which figure is correct? [UNVERIFIED]" in asked(conflict)
    assert not [q for q in asked(results) if "conflicting" in q]


def test_a_field_to_review_says_what_was_read_and_why_it_could_not_be_verified():
    text = asked(results_for(scenarios()["review"]))[0]

    assert text == ("Operating profit for the period ending 2025-03-31 was read as 100 on page 3 but could not be verified (label not recognised). "
                    "Confirm the figure from the audited statements. [UNVERIFIED]")


def test_a_field_to_review_without_evidence_does_not_claim_a_value(golden):
    record = next(f for f in golden["fields"] if f["field_id"] == "total_equity.2025-03-31.consolidated")
    record.update(status="requires_review", status_reason="scale_ambiguous", evidence_quote=None, raw_value=None, page_number=None)

    assert ("Total equity for the period ending 2025-03-31 was read but could not be verified (scale ambiguous). Confirm the figure from the audited statements. [UNVERIFIED]"
            in asked(golden))


def test_a_derived_value_is_not_asked_about_through_its_own_question():
    assert not [q for q in asked(results_for(scenarios()["review"])) if q.startswith("EBIT")]


def test_triggered_indicators_come_first_highest_severity_first_with_their_conditions():
    results = results_for(scenarios()["stressed"])
    out = asked(results)

    assert [q.split(" ")[0] for q in out[:5]] == ["RI-001", "RI-002", "RI-003", "RI-004", "RI-005"]
    assert out[2] == ("RI-003 Deteriorating liquidity was triggered (elevated): current ratio of the current period \\< 1.00. "
                      "What explains it, and does it need follow-up with the borrower? [RULE: RI-003]")


def test_the_missing_and_conflict_indicators_are_not_asked_about_because_their_fields_are():
    out = "\n".join(asked(results_for(scenarios()["stressed"])))

    assert "RI-006" not in out and "RI-007" not in out


def test_a_rule_that_could_not_be_evaluated_names_what_it_lacked(golden):
    assert ("RI-001 Declining revenue could not be evaluated because of missing inputs (`MET-01.2025-03-31 (missing_input)`). Can they be provided? [RULE: RI-001]"
            in asked(golden))


def test_a_metric_caveat_is_asked_once_with_a_label_for_each_metric_that_carries_it():
    out = [q for q in asked(results_for(scenarios()["stressed"])) if q.startswith("Total borrowings may exclude")]

    assert out == ["Total borrowings may exclude current maturities of long-term borrowings shown under another caption. Please confirm. "
                   "[CALCULATED: MET-04.2024-03-31] [CALCULATED: MET-04.2025-03-31]"]


def test_a_caveat_on_an_undefined_metric_is_not_asked_about(golden):
    next(m for m in golden["metrics"] if m["id"] == "MET-04.2025-03-31")["caveats"] = ["borrowings_not_presented_assumption"]

    assert not [q for q in asked(golden) if q.startswith("Total borrowings may exclude")]


def test_a_detail_of_the_document_that_was_not_confirmed_is_asked_last(golden):
    next(a for a in golden["attributes"] if a["attribute"] == "scale").update(status="not_found")
    next(a for a in golden["attributes"] if a["attribute"] == "period_end" and a["period_role"] == "comparative").update(status="requires_review")
    out = asked(golden)

    assert out[-2:] == ["The period end (comparative) of the document could not be confirmed. Please confirm it from the document. [UNVERIFIED]",
                        "The scale of the document could not be confirmed. Please confirm it from the document. [UNVERIFIED]"]  # fmt: skip


def test_the_questions_are_numbered_in_order_and_the_same_every_time(golden):
    text = section(golden, 8)
    numbers = re.findall(r"^(\d+)\. ", text, re.M)

    assert numbers == [str(n) for n in range(1, len(numbers) + 1)] and len(numbers) == 16
    assert section(golden, 8) == text and asked(golden) == asked(copy.deepcopy(golden))


def test_with_nothing_to_ask_the_section_says_so():
    calm = results_for(scenarios()["calm"])
    calm["fields"] = [f for f in calm["fields"] if f["status"] == "extracted"]
    calm["derived_fields"] = [d for d in calm["derived_fields"] if d["status"] == "extracted"]
    calm["metrics"] = [{**m, "caveats": []} for m in calm["metrics"]]

    assert section(calm, 8).strip().endswith(NONE_TEXT) and not re.search(r"^1\. ", section(calm, 8), re.M)


def test_text_from_fields_rules_and_attributes_in_questions_is_escaped(golden):
    record = next(f for f in golden["fields"] if f["field_id"] == "total_equity.2025-03-31.consolidated")
    record.update(status="requires_review", status_reason=HOSTILE, raw_value=HOSTILE)
    golden["indicators"][0]["name"] = HOSTILE
    golden["attributes"][0].update(status="not_found", attribute=HOSTILE)
    text = section(golden, 8)

    assert "\\[SOURCE: p.9\\]" in text and not re.search(r"(?<![\\`])\[SOURCE: p\.9\]", text) and "<i>" not in text


# --- section 9 ---------------------------------------------------------------------------------------------------------------------------------


def test_the_limitations_open_with_the_human_review_statement(golden):
    text = section(golden, 9)

    assert text.startswith("## 9. Limitations and human-review requirements\n\n**This memo is a draft. A qualified human must review it")
    assert "It is not a credit decision, a rating or a score.**" in text


@pytest.mark.parametrize("phrase", ["text-based PDF", "OCR of scanned pages is available but was not used", "One document", "52/53-week", "No currency conversion", "never switched automatically",
                                    "Lease liabilities are excluded", "dash or the word nil", "acquisitions, disposals", "one-off items", "window dressing",
                                    "lease interest", "not proof that it is absent", "no AI-generated commentary", "not used in any calculation or rule",
                                    "not how creditworthy"])  # fmt: skip
def test_the_limitations_name_each_limit_the_prd_requires(golden, phrase):
    assert phrase.lower() in section(golden, 9).lower()


def test_the_provisional_threshold_notice_in_the_limitations_is_the_one_in_the_results(golden):
    golden["provisional_notice"] = "Custom notice text."

    assert "- Custom notice text. [CALCULATED: provisional_notice]" in section(golden, 9)


def test_the_fixed_limitation_text_needs_no_escaping_and_is_the_same_in_every_memo(golden):
    for text in (*limitations.SCOPE, *limitations.METRICS, *limitations.EXTRACTION, limitations.REVIEW.strip("*")):
        assert not set(text) & set("\\`_{}[]<>#|~&"), text
        assert "\n" not in text
    other = results_for(scenarios()["stressed"])
    assert section(golden, 9).replace(golden["provisional_notice"], "") == section(other, 9).replace(other["provisional_notice"], "")


# --- the whole memo ----------------------------------------------------------------------------------------------------------------------------


def test_the_memo_has_a_header_and_nine_sections_and_never_claims_ai_commentary(golden):
    text = memo(golden)

    assert text.startswith("# Draft credit memo\n") and re.findall(r"^## (\d)\. ", text, re.M) == list("123456789")
    assert "[AI INTERPRETATION" not in text


def test_the_memo_states_no_decision_recommendation_rating_or_score():
    text = memo(results_for(scenarios()["stressed"])).lower()

    for word in ("approv", "reject", "recommend", "score of", "rated", "grade"):
        assert not re.search(rf"\b{word}", text), word
    assert text.count("creditworthy") == 1 and "not how creditworthy" in text


def test_the_question_for_a_not_found_field_adds_its_reason_in_brackets_and_none_when_there_is_none(golden):
    golden["extraction"]["candidate_pages"] = [110, 111]
    for record in golden["fields"]:
        if record["field_name"] == "revenue" and record["status"] == "not_found":
            record["status_reason"] = "no_recognised_row" if record["period_role"] == "current" else None
    revenue = [q for q in asked(golden) if q.startswith("Revenue")]

    assert "was not found on pages 110–111 (no recognised row) — confirm" in revenue[0] and "(" not in revenue[1].split("pages 110–111")[1].split("—")[0]
