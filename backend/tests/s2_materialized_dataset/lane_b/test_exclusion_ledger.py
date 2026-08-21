from __future__ import annotations

import pytest

from backend.app.s2_materialized_dataset.lane_b.cleaning import build_cleaned_dataset
from backend.app.s2_materialized_dataset.lane_b.exclusion_ledger import ExclusionLedgerConflictError
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    CleaningBuildRequest,
    ExclusionCode,
    ManualExclusionRequest,
    QuantityPresenceStatus,
)
from backend.tests.s2_materialized_dataset.lane_b.conftest import make_source_row_identity_hash

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_exclusion_is_distinct_from_missing_day_semantics(
    cleaning_build_request: CleaningBuildRequest,
    missing_quantity_row,
) -> None:
    source_hash = make_source_row_identity_hash(missing_quantity_row)
    request = cleaning_build_request.model_copy(
        update={
            "source_rows": (missing_quantity_row,),
            "manual_exclusions": (
                ManualExclusionRequest(
                    exclusion_event_id="exclude-1",
                    source_row_identity_hash=source_hash,
                    exclusion_code=ExclusionCode.BUSINESS_EXCLUSION,
                    exclusion_reason_reference="policy-ref-1",
                    decision_authority_reference="approver-1",
                ),
            ),
        }
    )
    result = build_cleaned_dataset(request)
    row = result.cleaned_rows[0]

    assert row.quantity_presence_status == QuantityPresenceStatus.UNKNOWN_NOT_ZERO
    assert row.is_excluded is True
    assert row.effective_actual_harvest_quantity_kg is None
    assert len(result.exclusion_ledger_entries) == 1


def test_contradictory_exclusion_entries_for_same_row_fail_closed(
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row,
) -> None:
    source_hash = make_source_row_identity_hash(known_quantity_row)
    first = ManualExclusionRequest(
        exclusion_event_id="exclude-a",
        source_row_identity_hash=source_hash,
        exclusion_code=ExclusionCode.BUSINESS_EXCLUSION,
        exclusion_reason_reference="policy-ref-1",
        decision_authority_reference="approver-1",
    )
    second = first.model_copy(update={"exclusion_event_id": "exclude-b"})
    request = cleaning_build_request.model_copy(
        update={"manual_exclusions": (first, second)}
    )

    with pytest.raises(ExclusionLedgerConflictError):
        build_cleaned_dataset(request)
