from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SourceRowBusinessContent,
    SourceRowIdentity,
    SourceRowLineageInput,
)
from backend.app.s2_materialized_dataset.lane_b.cleaning import (
    SOURCE_002_JULY_EXCLUSION_DATE,
    assert_replay_parity,
    build_cleaned_dataset,
    build_july_cohort_exclusions,
    build_source_002_e3_grain_diagnostics,
    resolve_quantity_presence,
    resolve_source_002_season_business_key,
    source_row_input_from_persisted_lane_a,
)
from backend.app.s2_materialized_dataset.lane_b.hashes import (
    compute_synthetic_raw_import_batch_identity_hash,
    compute_synthetic_raw_source_artifact_identity_hash,
    compute_synthetic_source_row_identity_hash,
    digest,
)
from backend.app.s2_materialized_dataset.lane_b.persistence import (
    CleanedDatasetVersionConflictError,
    persist_cleaning_build_result,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    SOURCE_002_CANONICAL_GRAIN_KG_SUM_LEDGER_POLICY_VERSION,
    SOURCE_002_JULY_COHORT_EXCLUSION_REASON,
    SOURCE_002_MAPPED_SEASON_BUSINESS_KEY,
    SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY,
    CleaningBuildRequest,
    ExclusionCode,
    ManualCorrectionRequest,
    QuantityPresenceStatus,
    Source002CleaningBlockedError,
    Source002GrainKgSumBlockedError,
    SyntheticSourceRowInput,
)
from backend.tests.s2_materialized_dataset.lane_b.conftest import (
    LANE_B_MIGRATION_DOWN_REVISION,
    LANE_B_MIGRATION_REVISION,
    _lane_b_migration_module,
    make_source_row,
    make_source_row_identity_hash,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.mark.migration
def test_lane_b_migration_head_and_revision_contract() -> None:
    module = _lane_b_migration_module()
    assert module.revision == LANE_B_MIGRATION_REVISION
    assert module.down_revision == LANE_B_MIGRATION_DOWN_REVISION


@pytest.mark.migration
def test_lane_b_migration_creates_cleaned_tables_with_numeric_quantity_columns(
    lane_b_migrated_session,
) -> None:
    inspector = sa.inspect(lane_b_migrated_session.bind)
    assert {
        "s2_cleaned_dataset_version",
        "s2_cleaned_row",
        "s2_quality_finding",
        "s2_correction_ledger_entry",
        "s2_exclusion_ledger_entry",
    }.issubset(set(inspector.get_table_names()))
    row_columns = {column["name"]: column for column in inspector.get_columns("s2_cleaned_row")}
    for column_name in (
        "source_actual_harvest_quantity_kg",
        "effective_actual_harvest_quantity_kg",
    ):
        column = row_columns[column_name]
        assert "NUMERIC" in str(column["type"]).upper()


@pytest.mark.migration
def test_lane_b_cleaned_tables_reject_update_under_migration_triggers(
    lane_b_migrated_session,
    cleaning_build_request: CleaningBuildRequest,
) -> None:
    result = build_cleaned_dataset(cleaning_build_request)
    version_row = persist_cleaning_build_result(lane_b_migrated_session, result)
    lane_b_migrated_session.commit()
    with pytest.raises(sa.exc.IntegrityError):
        lane_b_migrated_session.execute(
            sa.text(
                """
                UPDATE s2_cleaned_dataset_version
                SET row_count = 99
                WHERE id = :version_id
                """
            ),
            {"version_id": version_row.id},
        )
        lane_b_migrated_session.commit()
    lane_b_migrated_session.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        lane_b_migrated_session.execute(
            sa.text(
                """
                UPDATE s2_cleaned_row
                SET is_excluded = 1
                WHERE cleaned_dataset_version_id = :version_id
                """
            ),
            {"version_id": version_row.id},
        )
        lane_b_migrated_session.commit()


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


def _persisted_identity(
    *,
    logical_id: str,
    harvest_date: date,
    quantity: Decimal = Decimal("10.000000"),
) -> tuple[SourceRowLineageInput, SourceRowIdentity]:
    row_input = SourceRowLineageInput(
        external_logical_record_id=logical_id,
        external_revision_id="source-002-idfl-immutable-final-revision-v1",
        revision_number=1,
        source_system="扫码称重系统",
        source_version="scan-weight-export:v0_3_s1:002",
        schema_version="observed-source-schema-v1",
        source_row_identity_version="v0-3-s2-source-row-identity-v1",
        source_sheet_name="Sheet1",
        source_row_number=2,
        source_column_mapping_snapshot_hash="6" * 64,
        business_content=SourceRowBusinessContent(
            harvest_business_date=harvest_date,
            farm_code="farm-a",
            subfarm_or_plot_code="subfarm-a",
            variety_code="variety-a",
            actual_harvest_quantity_kg=quantity,
        ),
    )
    identity = SourceRowIdentity(
        source_row_identity_hash=digest({"logical_id": logical_id, "harvest_date": harvest_date}),
        content_sha256="b" * 64,
        raw_source_artifact_identity_hash="c" * 64,
        raw_import_batch_identity_hash="d" * 64,
        external_logical_record_id=logical_id,
        external_revision_id="source-002-idfl-immutable-final-revision-v1",
        revision_number=1,
        source_system="扫码称重系统",
        source_version="scan-weight-export:v0_3_s1:002",
        schema_version="observed-source-schema-v1",
        source_row_identity_version="v0-3-s2-source-row-identity-v1",
        source_sheet_name="Sheet1",
        source_row_number=2,
        source_column_mapping_snapshot_hash="6" * 64,
        winner_selection_blocked=False,
    )
    return row_input, identity


def test_source_002_season_resolution_maps_mapped_dates() -> None:
    assert resolve_source_002_season_business_key(date(2025, 8, 5)) == (
        SOURCE_002_MAPPED_SEASON_BUSINESS_KEY
    )
    assert resolve_source_002_season_business_key(date(2026, 4, 16)) == (
        SOURCE_002_MAPPED_SEASON_BUSINESS_KEY
    )


def test_source_002_july_date_uses_unmapped_sentinel_not_auto_season() -> None:
    assert resolve_source_002_season_business_key(SOURCE_002_JULY_EXCLUSION_DATE) == (
        SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY
    )


def test_source_002_out_of_scope_date_fails_closed() -> None:
    with pytest.raises(Source002CleaningBlockedError):
        resolve_source_002_season_business_key(date(2024, 1, 1))


def test_persisted_lane_a_zero_kg_uses_known_quantity_semantics() -> None:
    row_input, identity = _persisted_identity(
        logical_id="zero-kg-row",
        harvest_date=date(2026, 2, 10),
        quantity=Decimal("0"),
    )
    source_row = source_row_input_from_persisted_lane_a(
        row_input=row_input,
        persisted_identity=identity,
    )
    assert source_row.actual_harvest_quantity_kg == Decimal("0")
    assert source_row.missing_record_semantics == "KNOWN"
    assert resolve_quantity_presence(source_row) == QuantityPresenceStatus.KNOWN


def test_july_cohort_exclusions_reference_option_a_reason() -> None:
    row_input, identity = _persisted_identity(
        logical_id="july-row-1",
        harvest_date=SOURCE_002_JULY_EXCLUSION_DATE,
    )
    source_row = source_row_input_from_persisted_lane_a(
        row_input=row_input,
        persisted_identity=identity,
    )
    exclusions = build_july_cohort_exclusions(source_rows=(source_row,))
    assert len(exclusions) == 1
    assert exclusions[0].exclusion_code == ExclusionCode.BUSINESS_EXCLUSION
    assert exclusions[0].exclusion_reason_reference == SOURCE_002_JULY_COHORT_EXCLUSION_REASON


def test_source_002_canonical_grain_kg_sum_collapses_collision_group(
    synthetic_batch,
    synthetic_artifact,
    cleaning_build_request: CleaningBuildRequest,
) -> None:
    row_a = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="logical-a",
        harvest_date=date(2026, 2, 10),
        quantity=Decimal("10.000000"),
    )
    row_b = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="logical-b",
        harvest_date=date(2026, 2, 10),
        quantity=Decimal("20.000000"),
    )
    hash_a = make_source_row_identity_hash(row_a)
    hash_b = make_source_row_identity_hash(row_b)
    row_a = row_a.model_copy(update={"persisted_source_row_identity_hash": hash_a})
    row_b = row_b.model_copy(update={"persisted_source_row_identity_hash": hash_b})

    diagnostics = build_source_002_e3_grain_diagnostics(
        (row_a, row_b),
        july_excluded_row_count=0,
    )
    assert diagnostics.collision_grain_count == 1
    assert diagnostics.kg_in_collision_grains == Decimal("30.000000")

    request = cleaning_build_request.model_copy(
        update={
            "source_rows": (row_a, row_b),
            "canonical_grain_kg_sum_ledger_policy_version": (
                SOURCE_002_CANONICAL_GRAIN_KG_SUM_LEDGER_POLICY_VERSION
            ),
        }
    )
    result = build_cleaned_dataset(request)
    active_rows = [row for row in result.cleaned_rows if not row.is_excluded]
    assert len(active_rows) == 1
    assert active_rows[0].effective_actual_harvest_quantity_kg == Decimal("30.000000")
    assert len(result.version.source_row_identity_hashes) == 2


def test_source_002_kg_sum_blocks_mixed_known_and_unknown_in_one_grain(
    synthetic_batch,
    synthetic_artifact,
    cleaning_build_request: CleaningBuildRequest,
    missing_quantity_row: SyntheticSourceRowInput,
) -> None:
    known_row = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="logical-known",
        harvest_date=date(2026, 2, 10),
        quantity=Decimal("10.000000"),
    )
    request = cleaning_build_request.model_copy(
        update={
            "source_rows": (known_row, missing_quantity_row),
            "canonical_grain_kg_sum_ledger_policy_version": (
                SOURCE_002_CANONICAL_GRAIN_KG_SUM_LEDGER_POLICY_VERSION
            ),
        }
    )
    with pytest.raises(Source002GrainKgSumBlockedError):
        build_cleaned_dataset(request)


def test_e3_grain_diagnostics_no_collision_allows_persist(
    sqlite_session,
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row: SyntheticSourceRowInput,
) -> None:
    diagnostics = build_source_002_e3_grain_diagnostics(
        (known_quantity_row,),
        july_excluded_row_count=0,
    )
    assert diagnostics.collision_grain_count == 0
    assert diagnostics.singleton_grain_count == 1
    assert diagnostics.source_rows_in_scope == 1
    assert diagnostics.rows_in_singleton_grains == 1
    assert diagnostics.rows_in_collision_grains == 0
    assert diagnostics.kg_in_singleton_grains == Decimal("12.500000")
    assert diagnostics.kg_total_in_scope == Decimal("12.500000")
    assert diagnostics.collision_group_size_min == 0
    assert diagnostics.collision_group_samples == ()

    request = cleaning_build_request.model_copy(
        update={
            "canonical_grain_kg_sum_ledger_policy_version": (
                SOURCE_002_CANONICAL_GRAIN_KG_SUM_LEDGER_POLICY_VERSION
            ),
        }
    )
    result = build_cleaned_dataset(request)
    row = persist_cleaning_build_result(sqlite_session, result)
    sqlite_session.commit()
    assert row.row_count == 1


def test_july_rows_remain_in_source_lineage_but_not_canonical_output(
    cleaning_build_request: CleaningBuildRequest,
    synthetic_batch,
    synthetic_artifact,
) -> None:
    mapped_row = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="mapped-row",
        harvest_date=date(2026, 2, 10),
    )
    july_row = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="july-row",
        harvest_date=SOURCE_002_JULY_EXCLUSION_DATE,
    )
    july_row = july_row.model_copy(
        update={
            "season_business_key": SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY,
            "identity": july_row.identity.model_copy(
                update={"external_logical_record_id": "july-logical"}
            ),
        }
    )
    july_hash = make_source_row_identity_hash(july_row)
    july_exclusions = build_july_cohort_exclusions(source_rows=(july_row,))
    request = cleaning_build_request.model_copy(
        update={
            "source_rows": (mapped_row, july_row),
            "manual_exclusions": july_exclusions,
        }
    )
    result = build_cleaned_dataset(request)

    assert len(result.version.source_row_identity_hashes) == 2
    assert july_hash in result.version.source_row_identity_hashes
    assert sum(1 for row in result.cleaned_rows if not row.is_excluded) == 1
    assert any(
        row.source_row_identity_hash == july_hash and row.is_excluded for row in result.cleaned_rows
    )
