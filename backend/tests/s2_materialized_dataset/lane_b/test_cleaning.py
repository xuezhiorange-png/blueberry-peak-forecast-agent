from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.s2_materialized_dataset.lane_b.cleaning import (
    assert_replay_parity,
    build_cleaned_dataset,
)
from backend.app.s2_materialized_dataset.lane_b.hashes import (
    compute_synthetic_raw_import_batch_identity_hash,
    compute_synthetic_raw_source_artifact_identity_hash,
    compute_synthetic_source_row_identity_hash,
)
from backend.app.s2_materialized_dataset.lane_b.persistence import (
    CleanedDatasetVersionConflictError,
    persist_cleaning_build_result,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    CleaningBuildRequest,
    ManualCorrectionRequest,
    QuantityPresenceStatus,
    SyntheticSourceRowInput,
)
from backend.tests.s2_materialized_dataset.lane_b.conftest import (
    make_source_row,
    make_source_row_identity_hash,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_synthetic_upstream_identities_are_deterministic(
    synthetic_artifact,
    synthetic_batch,
    known_quantity_row: SyntheticSourceRowInput,
) -> None:
    artifact_payload = synthetic_artifact.model_dump(mode="python")
    batch_payload = synthetic_batch.model_dump(mode="python")
    row_payload = known_quantity_row.identity.model_dump(mode="python")

    assert compute_synthetic_raw_source_artifact_identity_hash(artifact_payload) == (
        compute_synthetic_raw_source_artifact_identity_hash(artifact_payload)
    )
    assert compute_synthetic_raw_import_batch_identity_hash(batch_payload) == (
        compute_synthetic_raw_import_batch_identity_hash(batch_payload)
    )
    assert compute_synthetic_source_row_identity_hash(row_payload) == (
        compute_synthetic_source_row_identity_hash(row_payload)
    )


def test_missing_day_stays_unknown_not_zero(
    cleaning_build_request: CleaningBuildRequest,
    missing_quantity_row: SyntheticSourceRowInput,
) -> None:
    request = cleaning_build_request.model_copy(update={"source_rows": (missing_quantity_row,)})
    result = build_cleaned_dataset(request)
    row = result.cleaned_rows[0]

    assert row.quantity_presence_status == QuantityPresenceStatus.UNKNOWN_NOT_ZERO
    assert row.source_actual_harvest_quantity_kg is None
    assert row.effective_actual_harvest_quantity_kg is None
    assert row.effective_actual_harvest_quantity_kg != Decimal("0")


def test_cleaned_row_preserves_source_reference_after_correction(
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row: SyntheticSourceRowInput,
) -> None:
    source_hash = make_source_row_identity_hash(known_quantity_row)
    request = cleaning_build_request.model_copy(
        update={
            "manual_corrections": (
                ManualCorrectionRequest(
                    correction_event_id="corr-1",
                    source_row_identity_hash=source_hash,
                    field_name="actual_harvest_quantity_kg",
                    corrected_value=Decimal("15.000000"),
                    reason="manual audit correction",
                    manual_actor_or_authority_reference="operator-1",
                ),
            )
        }
    )
    result = build_cleaned_dataset(request)
    row = result.cleaned_rows[0]

    assert row.source_row_identity_hash == source_hash
    assert row.source_actual_harvest_quantity_kg == Decimal("12.500000")
    assert row.effective_actual_harvest_quantity_kg == Decimal("15.000000")
    assert len(result.correction_ledger_entries) == 1


def test_cleaned_dataset_version_replay_is_stable(
    cleaning_build_request: CleaningBuildRequest,
) -> None:
    first = build_cleaned_dataset(cleaning_build_request)
    second = build_cleaned_dataset(cleaning_build_request)
    assert_replay_parity(first, second)


def test_duplicate_version_identity_with_different_content_fails_closed(
    sqlite_session,
    cleaning_build_request: CleaningBuildRequest,
) -> None:
    first = build_cleaned_dataset(cleaning_build_request)
    persist_cleaning_build_result(sqlite_session, first)
    sqlite_session.commit()

    mutated_row = make_source_row(
        batch=cleaning_build_request.raw_import_batches[0],
        artifact=cleaning_build_request.raw_source_artifacts[0],
        quantity=Decimal("99.000000"),
    )
    conflicting = build_cleaned_dataset(
        cleaning_build_request.model_copy(update={"source_rows": (mutated_row,)})
    )
    assert (
        conflicting.version.cleaned_dataset_version_identity_hash
        == first.version.cleaned_dataset_version_identity_hash
    )
    assert conflicting.version.cleaned_dataset_version_content_hash != (
        first.version.cleaned_dataset_version_content_hash
    )

    with pytest.raises(CleanedDatasetVersionConflictError):
        persist_cleaning_build_result(sqlite_session, conflicting)


def test_persisted_version_is_immutable_append_only(
    sqlite_session,
    cleaning_build_request: CleaningBuildRequest,
) -> None:
    result = build_cleaned_dataset(cleaning_build_request)
    row = persist_cleaning_build_result(sqlite_session, result)
    sqlite_session.commit()
    replay = persist_cleaning_build_result(sqlite_session, result)
    sqlite_session.commit()

    assert replay.id == row.id
    assert replay.cleaned_dataset_version_content_hash == (
        result.version.cleaned_dataset_version_content_hash
    )
