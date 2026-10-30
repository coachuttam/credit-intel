"""KNOWN DEFECT (recorded 2026-10-30 in PROGRESS.md; not fixed): a derived value names input IDs that are not in the results.

Found on a real run (a 6-page quarterly results document, 2026-10-26, replayed from the response cache on 2026-10-30): when neither period end
is verified, ``missing_fields`` adds no ``not_found`` placeholders (it makes them only for validated periods), yet a derived value is still built
from the date of an input that is present (EBIT from profit before tax) and lists **all** its inputs by ID, including one with no record. The
memo then cites an ID that is not in ``results.json`` and the memo check stops the run (exit 1, "the memo failed its traceability check",
a manifest-only failure record). The check did its job; the results are what is inconsistent.

The test states the contract. It is ``xfail(strict=True)``: it must fail today, and when the defect is fixed it will start to pass and the strict
marker will fail the suite until the marker is removed, so the fix cannot go unnoticed.
"""

import pytest

from calc_records import CUR, rec
from credit_intel.calculations.derived import derive_ebit_for
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, StatementBasis as Basis

KNOWN = "known defect: a derived value lists input IDs that have no record when the field set has no not_found placeholders (PROGRESS 2026-10-30)"


@pytest.mark.xfail(strict=True, reason=KNOWN)
def test_every_input_a_derived_value_names_is_a_record_of_the_field_set():
    only_pbt = FieldSet(Basis.CONSOLIDATED, (rec(F.PROFIT_BEFORE_TAX, "300"),), (), (), ("consolidated",))  # no placeholders: periods were not validated
    ebit = derive_ebit_for(only_pbt, CUR)
    assert ebit is not None and ebit.derivation is not None
    ids = {record.field_id for record in only_pbt.fields}
    assert set(ebit.derivation.input_field_ids) <= ids


def test_the_defect_is_what_is_recorded_one_named_input_has_no_record():
    """Not an xfail: it pins the facts so that the xfail above cannot pass for another reason."""
    only_pbt = FieldSet(Basis.CONSOLIDATED, (rec(F.PROFIT_BEFORE_TAX, "300"),), (), (), ("consolidated",))
    ebit = derive_ebit_for(only_pbt, CUR)
    ids = {record.field_id for record in only_pbt.fields}
    missing = [i for i in ebit.derivation.input_field_ids if i not in ids]
    assert missing == ["interest_expense.2025-03-31.consolidated"] and "profit_before_tax.2025-03-31.consolidated" in ids
