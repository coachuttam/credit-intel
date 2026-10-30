"""A derived value names only inputs that have a record in the field set (K.10 traceability).

Found on a real run (a 6-page quarterly results document, 2026-10-26; PROGRESS.md 2026-10-30): with no ``not_found``
placeholders in the field set (period ends not validated), EBIT from profit before tax listed ``interest_expense.<date>``
though that field had no record, the memo cited it, and the memo check stopped the run. Fix (owner's option B): list only inputs that exist.
"""

from calc_records import CUR, D24, rec
from credit_intel.calculations.derived import derive_ebit, derive_ebit_for
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, Status, StatementBasis as Basis

PBT_ID = "profit_before_tax.2025-03-31.consolidated"
INT_ID = "interest_expense.2025-03-31.consolidated"


def field_set(*records):
    return FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ("consolidated",))


def test_the_missing_input_is_not_named_and_every_named_input_is_a_record():
    fields = field_set(rec(F.PROFIT_BEFORE_TAX, "300"))  # no placeholders: periods were not validated
    ebit = derive_ebit_for(fields, CUR)
    assert ebit.derivation.input_field_ids == (PBT_ID,)
    assert set(ebit.derivation.input_field_ids) <= {r.field_id for r in fields.fields}


def test_a_not_found_placeholder_is_still_named_because_it_is_a_record():
    fields = field_set(rec(F.PROFIT_BEFORE_TAX, "300"), rec(F.INTEREST_EXPENSE, status=Status.NOT_FOUND))
    ebit = derive_ebit_for(fields, CUR)
    assert ebit.status is Status.NOT_FOUND and ebit.derivation.input_field_ids == (PBT_ID, INT_ID)


def test_both_inputs_present_are_both_named_in_order():
    ebit = derive_ebit(None, rec(F.PROFIT_BEFORE_TAX, "300"), rec(F.INTEREST_EXPENSE, "50"))
    assert ebit.derivation.input_field_ids == (PBT_ID, INT_ID) and ebit.status is Status.EXTRACTED


def test_only_interest_present_names_only_interest():
    ebit = derive_ebit(None, None, rec(F.INTEREST_EXPENSE, "50"))
    assert ebit.derivation.input_field_ids == (INT_ID,)


def test_each_input_is_named_by_its_own_record_id_when_period_ends_differ():
    ebit = derive_ebit(None, rec(F.PROFIT_BEFORE_TAX, "300"), rec(F.INTEREST_EXPENSE, "50", end=D24))
    assert ebit.derivation.input_field_ids == (PBT_ID, "interest_expense.2024-03-31.consolidated")


def test_no_input_at_all_names_the_record_it_was_anchored_on():
    ebit = derive_ebit(rec(F.OPERATING_PROFIT, status=Status.NOT_FOUND), None, None)
    assert ebit.derivation.input_field_ids == ("operating_profit.2025-03-31.consolidated",)
