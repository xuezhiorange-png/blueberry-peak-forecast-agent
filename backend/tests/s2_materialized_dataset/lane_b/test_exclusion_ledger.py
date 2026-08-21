from __future__ import annotations

import pytest
import sqlalchemy as sa

from backend.app.s2_materialized_dataset.lane_b.cleaning import build_cleaned_dataset
from backend.app.s2_materialized_dataset.lane_b.exclusion_ledger import ExclusionLedgerConflictError
from backend.app.s2_materialized_dataset.lane_b.persistence import persist_cleaning_build_result
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
    request = cleaning_build_request.model_copy(update={"manual_exclusions": (first, second)})

    with pytest.raises(ExclusionLedgerConflictError):
        build_cleaned_dataset(request)


@pytest.mark.migration
def test_lane_b_exclusion_ledger_rejects_update_under_migration_triggers(
    lane_b_migrated_session,
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row,
) -> None:
    source_hash = make_source_row_identity_hash(known_quantity_row)
    request = cleaning_build_request.model_copy(
        update={
            "manual_exclusions": (
                ManualExclusionRequest(
                    exclusion_event_id="exclude-migration-1",
                    source_row_identity_hash=source_hash,
                    exclusion_code=ExclusionCode.BUSINESS_EXCLUSION,
                    exclusion_reason_reference="policy-ref-1",
                    decision_authority_reference="approver-1",
                ),
            )
        }
    )
    result = build_cleaned_dataset(request)
    version_row = persist_cleaning_build_result(lane_b_migrated_session, result)
    lane_b_migrated_session.commit()
    entry_id = lane_b_migrated_session.execute(
        sa.text(
            """
            SELECT id FROM s2_exclusion_ledger_entry
            WHERE cleaned_dataset_version_id = :version_id
            """
        ),
        {"version_id": version_row.id},
    ).scalar_one()
    with pytest.raises(sa.exc.IntegrityError):
        lane_b_migrated_session.execute(
            sa.text(
                """
                UPDATE s2_exclusion_ledger_entry
                SET exclusion_reason_reference = 'mutated'
                WHERE id = :entry_id
                """
            ),
            {"entry_id": entry_id},
        )
        lane_b_migrated_session.commit()
