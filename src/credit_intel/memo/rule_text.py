"""How each risk-rule condition is worded in the memo (PRD J.4; Phase 5 step 5g).

The comparison operator of a condition is fixed in the code of the rule (``risk/rules.py``), and the threshold
comes from the configuration file, so ``results.json`` carries the threshold but not the wording. The wording is
kept here, one entry per condition, and a test drives every rule at, below and above its threshold to check that
each phrase says what the rule does (``tests/unit/test_memo_rule_text.py``), so the two cannot drift apart.

Each entry is ``(subject, relation, unit)``: the memo prints ``<subject> <relation> <threshold><unit>``. The
relation is one of ``<``, ``<=``, ``>``, ``>=`` for a level, ``fell`` or ``rose`` for a relative change in percent.
"""

LEVEL = ("<", "<=", ">", ">=")
CHANGE = ("fell", "rose")

# (rule, condition) -> (subject, relation, unit). Conditions without a threshold have a fixed sentence below.
THRESHOLD_TEXT: dict[tuple[str, str], tuple[str, str, str]] = {
    ("RI-001", "C1"): ("revenue growth", "<", "%"),
    ("RI-001", "C2"): ("revenue growth", "<=", "%"),
    ("RI-002", "C1"): ("net profit of the current period", "<", ""),
    ("RI-003", "C1"): ("current ratio of the current period", "<", ""),
    ("RI-003", "C2"): ("current ratio", "fell", "%"),
    ("RI-004", "C1"): ("debt-to-equity ratio", "rose", "%"),
    ("RI-004", "C2"): ("debt-to-equity ratio of the current period", ">", ""),
    ("RI-004", "C3"): ("total equity in either period", "<=", ""),
    ("RI-005", "C1"): ("interest coverage ratio of the current period", "<", ""),
    ("RI-005", "C2"): ("interest coverage ratio of the current period", "<", ""),
}
FIXED_TEXT: dict[tuple[str, str], str] = {
    ("RI-006", "C1"): "an input that revenue growth, net profit margin, the current ratio, debt-to-equity or interest coverage needs is not found",
    ("RI-007", "C1"): "a source field is conflicting or needs review",
}


def condition_text(rule_id: str, condition_id: str, threshold: str | None) -> str:
    """The condition as a sentence fragment, e.g. ``current ratio of the current period < 1.00``."""
    fixed = FIXED_TEXT.get((rule_id, condition_id))
    if fixed is not None:
        return fixed
    entry = THRESHOLD_TEXT.get((rule_id, condition_id))
    if entry is None or threshold is None:
        return f"condition {condition_id}"
    subject, relation, unit = entry
    if relation == "fell":
        return f"{subject} fell by at least {threshold}{unit} relative to the comparative period"
    if relation == "rose":
        return f"{subject} rose by at least {threshold}{unit} relative to the comparative period"
    return f"{subject} {relation} {threshold}{unit}"
