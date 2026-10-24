"""Evaluating all the rules, the properties that hold for any run, and the absence of any score or decision (PRD FR-008, J.1, J.2, J.5; Phase 4 step 4f; B-253)."""

import ast
import random
from decimal import Decimal
from pathlib import Path

import pytest

import risk_golden as rg
from calc_records import CUR, D24, D25, rec
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status
from credit_intel.risk import evaluate as evaluate_module, results as results_module, rules as rules_module
from credit_intel.risk.config import DEFAULT_RULES_PATH, load_risk_rules
from credit_intel.risk.evaluate import RuleSet, evaluate_rules
from credit_intel.risk.results import ConditionOutcome as C, RuleOutcome as R
from credit_intel.risk.spec import RULE_ORDER

COMP = PeriodRole.COMPARATIVE
CONFIG = load_risk_rules()


def run(scenario="stressed", config=None):
    field_set = rg.scenarios()[scenario]
    return evaluate_rules(field_set, calculate_metrics(field_set), config)


# --- the entry point ---------------------------------------------------------------------------------------------------------------------------


def test_all_seven_rules_are_evaluated_in_the_files_order():
    rule_set = run()

    assert isinstance(rule_set, RuleSet) and [r.rule_id for r in rule_set.results] == list(RULE_ORDER)
    assert rule_set.disabled == ()


def test_the_default_configuration_is_the_shipped_file():
    assert run(config=None) == run(config=load_risk_rules(DEFAULT_RULES_PATH))


def test_the_provisional_notice_travels_with_the_results():
    assert "illustrative placeholders" in run("calm").provisional_notice


def test_get_and_triggered():
    rule_set = run("stressed")

    assert rule_set.get("RI-002").outcome is R.TRIGGERED
    assert [r.rule_id for r in rule_set.triggered] == ["RI-001", "RI-002", "RI-003", "RI-004", "RI-005", "RI-006"]
    assert run("calm").triggered == ()


def test_a_rule_switched_off_in_the_file_is_left_out_and_listed():
    text = DEFAULT_RULES_PATH.read_text(encoding="utf-8").replace(
        'description = "Net profit for the current period is below zero."\nenabled = true',
        'description = "Net profit for the current period is below zero."\nenabled = false',
    )
    path = Path(__file__).resolve().parent / "_off.toml"
    path.write_text(text, encoding="utf-8")
    try:
        off = load_risk_rules(path)
    finally:
        path.unlink()

    rule_set = run("stressed", off)

    assert rule_set.disabled == ("RI-002",) and "RI-002" not in [r.rule_id for r in rule_set.results]
    assert [r for r in rule_set.results] == [r for r in run("stressed").results if r.rule_id != "RI-002"]


def test_an_enabled_rule_without_an_implementation_is_an_error(monkeypatch):
    monkeypatch.delitem(evaluate_module.RULE_FUNCTIONS, "RI-005")

    with pytest.raises(ValueError):
        run()


def test_the_evaluation_is_repeatable_and_leaves_its_inputs_unchanged():
    field_set = rg.scenarios()["stressed"]
    metrics = calculate_metrics(field_set)
    before = [r.model_dump() for r in field_set.fields]

    first, second = evaluate_rules(field_set, metrics), evaluate_rules(field_set, metrics)

    assert first == second and [r.model_dump() for r in field_set.fields] == before


def test_j3_examples_through_the_entry_point():
    # RI-003 at 0.84 with no comparative period: triggered. At 1.20: not evaluable. RI-004 with negative equity and no borrowings: triggered.
    def entry(current, comparative=None):
        records = [rec(n, v, role=CUR, end=D25) for n, v in current.items()] + [rec(n, v, role=COMP, end=D24) for n, v in (comparative or {}).items()]
        fs = FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ())
        return evaluate_rules(fs, calculate_metrics(fs))

    assert entry({F.CURRENT_ASSETS: "84", F.CURRENT_LIABILITIES: "100"}).get("RI-003").outcome is R.TRIGGERED
    assert entry({F.CURRENT_ASSETS: "120", F.CURRENT_LIABILITIES: "100"}).get("RI-003").outcome is R.NOT_EVALUABLE
    four = entry({F.TOTAL_EQUITY: "-100"}, {F.TOTAL_EQUITY: "100"}).get("RI-004")
    assert four.outcome is R.TRIGGERED and four.conditions[2].outcome is C.FIRED


# --- no score, rating, grade, approval or decision (J.5) -------------------------------------------------------------------------------------

RISK_PACKAGE = Path(rules_module.__file__).parent
FORBIDDEN = {"score", "scores", "scoring", "rating", "ratings", "grade", "grades", "approve", "approval", "approved", "reject", "rejection", "rejected", "decision", "decisions", "verdict", "creditworthiness"}


def speaks_of_a_decision(name: str) -> bool:
    """Whole words only, split on underscores (so ``deteriorating`` is not ``rating``)."""
    return any(word in FORBIDDEN for word in name.lower().split("_"))


def _identifiers(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.name)
    return names


@pytest.mark.parametrize("path", sorted(RISK_PACKAGE.glob("*.py")), ids=lambda p: p.name)
def test_no_identifier_in_the_risk_package_speaks_of_a_score_rating_grade_or_decision(path):
    bad = [n for n in _identifiers(path) if speaks_of_a_decision(n)]

    assert not bad, bad


def test_the_shipped_rules_file_has_no_key_for_a_score_or_a_decision():
    text = DEFAULT_RULES_PATH.read_text(encoding="utf-8")
    keys = {line.split("=")[0].strip() for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#")}

    assert not [k for k in keys if speaks_of_a_decision(k)]


BANNED_IMPORTS = {"random", "os", "sys", "socket", "subprocess", "requests", "httpx", "httpx2", "openai", "urllib", "shutil", "tempfile", "time", "logging", "pathlib", "secrets", "uuid", "tomllib"}


@pytest.mark.parametrize("name", ["rules.py", "results.py", "evaluate.py", "spec.py"])
def test_the_rule_code_does_no_io_randomness_or_model_call_and_uses_no_float(name):
    tree = ast.parse((RISK_PACKAGE / name).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "float", "eval", "exec", "input"}
        if isinstance(node, ast.Constant):
            assert not isinstance(node.value, float)

    assert not imported & BANNED_IMPORTS, imported & BANNED_IMPORTS
    assert "llm" not in {p for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module for p in n.module.split(".")}


def test_a_rule_set_has_no_number_that_adds_the_rules_up():
    import dataclasses

    names = {f.name for cls in (RuleSet, results_module.RuleResult, results_module.ConditionResult) for f in dataclasses.fields(cls)}

    assert not [n for n in names if n in {"total", "overall", "count", "index", "points", "weight", "sum"}]


# --- properties of any run ---------------------------------------------------------------------------------------------------------------------------

NAMES = [n for n in F if n is not F.EBIT]
STATUSES = [Status.EXTRACTED] * 6 + [Status.NOT_FOUND, Status.REQUIRES_REVIEW]


def random_field_set(rng, scale=Decimal(1)):
    records = []
    for role, end in ((CUR, D25), (COMP, D24)):
        for name in NAMES:
            if rng.random() < 0.08:
                continue
            status = rng.choice(STATUSES)
            if status is Status.EXTRACTED:
                value = Decimal(rng.choice(["0", "1", "-3", "7.5", "250", "-40", str(rng.randint(-10**5, 10**5) / 100)])) * scale
                records.append(rec(name, str(value), role=role, end=end, currency=rng.choice(["INR"] * 12 + ["USD"])))
            else:
                records.append(rec(name, status=status, role=role, end=end))
    return FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ())


def evaluate_fs(field_set):
    return evaluate_rules(field_set, calculate_metrics(field_set), CONFIG)


def test_property_every_run_gives_seven_consistent_results():
    rng = random.Random(110)
    for _ in range(400):
        rule_set = evaluate_fs(random_field_set(rng))

        assert [r.rule_id for r in rule_set.results] == list(RULE_ORDER)
        for result in rule_set.results:
            outcomes = [c.outcome for c in result.conditions]
            if C.FIRED in outcomes:
                best = max(c.severity.rank for c in result.conditions if c.outcome is C.FIRED)
                assert result.outcome is R.TRIGGERED and result.severity.rank == best
            elif C.NOT_EVALUABLE in outcomes:
                assert result.outcome is R.NOT_EVALUABLE and result.severity is None and result.missing_inputs
            else:
                assert result.outcome is R.NOT_TRIGGERED and result.severity is None
            for c in result.conditions:
                assert (c.outcome is C.NOT_EVALUABLE) == bool(c.missing_inputs)
                if c.outcome is C.FIRED and result.rule_id not in ("RI-006", "RI-007"):
                    assert c.threshold is not None and c.values_used


def test_property_rules_006_and_007_are_always_evaluable():
    rng = random.Random(111)
    for _ in range(300):
        rule_set = evaluate_fs(random_field_set(rng))

        assert rule_set.get("RI-006").outcome in (R.TRIGGERED, R.NOT_TRIGGERED)
        assert rule_set.get("RI-007").outcome in (R.TRIGGERED, R.NOT_TRIGGERED)


def test_property_scaling_every_amount_changes_no_outcome_and_no_severity():
    rng = random.Random(112)
    for _ in range(150):
        seed = rng.randint(0, 10**9)
        a = evaluate_fs(random_field_set(random.Random(seed)))
        b = evaluate_fs(random_field_set(random.Random(seed), scale=Decimal(rng.randint(2, 300))))

        assert [(r.outcome, r.severity) for r in a.results] == [(r.outcome, r.severity) for r in b.results]


def test_property_a_field_the_rules_do_not_read_cannot_change_them():
    rng = random.Random(113)
    for _ in range(100):
        base = random_field_set(rng)
        noisy = FieldSet(
            Basis.CONSOLIDATED,
            (*base.fields, rec(F.CURRENT_MATURITIES_LONG_TERM_BORROWINGS, status=Status.NOT_FOUND, role=CUR, end=D25)) if not any(
                r.field_name is F.CURRENT_MATURITIES_LONG_TERM_BORROWINGS and r.period_role is CUR for r in base.fields) else base.fields,
            (), (), (),
        )  # fmt: skip
        assert [(r.outcome, r.severity) for r in evaluate_fs(base).results] == [(r.outcome, r.severity) for r in evaluate_fs(noisy).results]


def test_the_word_scan_catches_a_real_offender_and_spares_deteriorating():
    assert speaks_of_a_decision("risk_score") and speaks_of_a_decision("credit_decision") and speaks_of_a_decision("approve")
    assert not speaks_of_a_decision("deteriorating_liquidity") and not speaks_of_a_decision("rank")
