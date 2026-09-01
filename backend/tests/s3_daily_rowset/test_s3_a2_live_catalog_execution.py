"""S3-A2 live catalog origin execution from bound SOURCE_002 actuals."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import Table

from backend.app.s2_materialized_dataset.lane_d.canonical import build_partition_bytes
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.lane_d.partitions import TEST_END, TEST_START
from backend.app.s2_materialized_dataset.lane_d.service import (
    S2MaterializedDatasetModel,
    S2MaterializedPartitionModel,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_002_ROW_LEVEL_READ,
    SPLIT_POLICY_VERSION,
    MaterializableRow,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_DATASET_ID,
    OFFICIAL_DATASET_VERSION,
    OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_ROW_COUNT,
)
from backend.app.s3_daily_rowset.actuals import InMemoryS2ActualsSource
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    ReplayIdentityOriginLandingReasonCode,
    replay_identity_origin_entries,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
)
from backend.app.s3_daily_rowset.registry import CatalogSourceKind
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_live_catalog_execution import (
    LiveCatalogOriginExecutionEnvelope,
    LiveCatalogOriginExecutionReasonCode,
    execute_catalog_origin_from_bound_actuals,
    execute_live_catalog_origin,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY, make_row

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
LIVE_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_live_catalog_execution.py")
TABLE_NAME = "s3_incumbent_forecast_replay_identity"
LIVE_ENVELOPE_KIND = CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF


class _UtcAwareDateTime(sa.TypeDecorator[datetime]):
    impl = sa.DateTime(timezone=True)
    cache_ok = True

    def process_result_value(
        self,
        value: datetime | None,
        dialect: sa.Dialect,
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def _create_replay_table(sync_conn: sa.Connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        TABLE_NAME,
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("forecast_cutoff_at", _UtcAwareDateTime(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "forecast_cutoff_at",
            "model_id",
            "forecast_quantile",
            name="uq_s3_replay_identity_grain",
        ),
    )
    metadata.create_all(sync_conn)


def _create_s2_tables(sync_conn: sa.Connection) -> None:
    cast(Table, S2MaterializedDatasetModel.__table__).create(sync_conn)
    cast(Table, S2MaterializedPartitionModel.__table__).create(sync_conn)


def _sealed_test_bytes() -> bytes:
    from backend.app.s2_materialized_dataset.lane_d.canonical import build_test_synthetic_bytes

    return build_test_synthetic_bytes(
        partition_name="TEST",
        partition_start_date=TEST_START.isoformat(),
        partition_end_date=TEST_END.isoformat(),
        split_policy_version=SPLIT_POLICY_VERSION,
    )


def _placeholder_sha(label: str) -> str:
    return content_sha256(label.encode("utf-8"))


async def _persist_accepted_dataset_async(
    session: AsyncSession,
    *,
    train_rows: tuple[MaterializableRow, ...],
    validation_rows: tuple[MaterializableRow, ...],
) -> None:
    train_bytes = build_partition_bytes(train_rows)
    validation_bytes = build_partition_bytes(validation_rows)
    now = datetime(2026, 4, 1, tzinfo=UTC)
    dataset = S2MaterializedDatasetModel(
        dataset_id=OFFICIAL_DATASET_ID,
        dataset_version=OFFICIAL_DATASET_VERSION,
        materialized_dataset_identity_sha256=OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
        source_cohort_id="source-002-s1-cohort-v1",
        source_cohort_manifest_sha256=(
            "27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca"
        ),
        raw_policy_version="v0-3-s2-raw-policy-v1",
        cleaning_policy_version="v0-3-s2-cleaning-policy-v1",
        correction_policy_version="v0-3-s2-correction-policy-v1",
        exclusion_policy_version="v0-3-s2-exclusion-policy-v1",
        visibility_policy_version="v0-3-s2-visibility-policy-v1",
        revision_winner_policy_version="v0-3-s2-revision-winner-policy-v1",
        cleaned_dataset_version_identity="cleaned-dataset-v1",
        builder_version="v0-3-s2-lane-d-builder-r1",
        dataset_schema_version="v0-3-s2-materialized-dataset-v1",
        lineage_complete=True,
        quality_gate_status="ACCEPTED",
        build_started_at=now,
        build_completed_at=now,
        upstream_snapshot_sha256=_placeholder_sha("upstream"),
    )
    session.add(dataset)
    await session.flush()
    for name, start, end, content_bytes, row_count in (
        ("TRAIN", date(2025, 8, 5), date(2026, 1, 30), train_bytes, len(train_rows)),
        (
            "VALIDATION",
            date(2026, 1, 31),
            date(2026, 3, 9),
            validation_bytes,
            len(validation_rows),
        ),
        ("TEST", TEST_START, TEST_END, _sealed_test_bytes(), 0),
    ):
        session.add(
            S2MaterializedPartitionModel(
                materialized_dataset_id=dataset.id,
                partition_name=name,
                partition_start_date=start,
                partition_end_date=end,
                partition_date_field="HARVEST_BUSINESS_DATE",
                target_decision="OBSERVED_FARM_PICK_QUANTITY",
                canonical_grain="SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE",
                split_policy_version=SPLIT_POLICY_VERSION,
                manifest_schema_version="v0-3-s2-materialized-dataset-manifest-v1",
                materialized_partition_schema_version="v0-3-s2-materialized-partition-v1",
                row_count=row_count,
                byte_count=len(content_bytes),
                content_sha256=content_sha256(content_bytes),
                partition_identity_sha256=_placeholder_sha(f"identity-{name}"),
                manifest_sha256=_placeholder_sha(f"manifest-{name}"),
                content_bytes=content_bytes,
                lineage_complete=True,
                quality_gate_status="ACCEPTED",
                rebuild_hash_replay_status="PASS",
            )
        )
    await session.commit()


def _in_season_rows() -> tuple[tuple[MaterializableRow, ...], tuple[MaterializableRow, ...]]:
    train_row = make_row(harvest_business_date=date(2026, 1, 15), quantity="12.5")
    validation_row = make_row(harvest_business_date=date(2026, 2, 1), quantity="3.0")
    return (train_row,), (validation_row,)


def _patch_official_counts(
    monkeypatch: pytest.MonkeyPatch,
    *,
    train_rows: tuple[MaterializableRow, ...],
    validation_rows: tuple[MaterializableRow, ...],
) -> None:
    train_bytes = build_partition_bytes(train_rows)
    validation_bytes = build_partition_bytes(validation_rows)
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source.OFFICIAL_TRAIN_ROW_COUNT",
        len(train_rows),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source.OFFICIAL_VALIDATION_ROW_COUNT",
        len(validation_rows),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source.OFFICIAL_TRAIN_BYTE_COUNT",
        len(train_bytes),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source.OFFICIAL_VALIDATION_BYTE_COUNT",
        len(validation_bytes),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source.OFFICIAL_TRAIN_CONTENT_SHA256",
        content_sha256(train_bytes),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source.OFFICIAL_VALIDATION_CONTENT_SHA256",
        content_sha256(validation_bytes),
    )


async def _async_session_maker_with_rows(
    train_rows: tuple[MaterializableRow, ...],
    validation_rows: tuple[MaterializableRow, ...],
) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_create_s2_tables)
        await conn.run_sync(_create_replay_table)
    session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        await _persist_accepted_dataset_async(
            session,
            train_rows=train_rows,
            validation_rows=validation_rows,
        )
    return session_maker


def _session_maker_with_rows(
    train_rows: tuple[MaterializableRow, ...],
    validation_rows: tuple[MaterializableRow, ...],
) -> async_sessionmaker[AsyncSession]:
    return asyncio.run(_async_session_maker_with_rows(train_rows, validation_rows))


def _sync_replay_session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _create_replay_table(connection)
    return sessionmaker(bind=engine)()


def test_envelope_does_not_expose_content_bytes_kg_or_farms() -> None:
    field_names = set(LiveCatalogOriginExecutionEnvelope.model_fields)
    assert "content_bytes" not in field_names
    assert "actual_harvest_quantity_kg" not in field_names
    assert "farm" not in field_names
    assert "members" not in field_names
    assert "harvest_business_date" not in field_names


def test_injected_actuals_produce_catalog_without_wiring_default_obtain() -> None:
    train_rows, validation_rows = _in_season_rows()
    actuals = InMemoryS2ActualsSource(train_rows + validation_rows)
    session = _sync_replay_session()

    with patch("backend.app.db.session.AsyncSessionMaker", None):
        envelope = execute_catalog_origin_from_bound_actuals(
            actuals_source=actuals,
            sync_session=session,
            dataset_identity=DATASET_IDENTITY,
        )

    assert (
        envelope.live_execution_reason_code
        is LiveCatalogOriginExecutionReasonCode.ARTIFACT_PRODUCED
    )
    assert envelope.catalog_reason_code == CatalogArtifactReasonCode.ARTIFACT_PRODUCED.value
    assert envelope.origin_entry_count == 3
    assert envelope.aligned_identity_count == 2
    assert envelope.catalog_entry_count == 6
    assert envelope.declared_catalog_source_kind == LIVE_ENVELOPE_KIND.value
    assert envelope.uses_harvest_date_as_forecast_cutoff is False
    assert envelope.test_remains_sealed is True
    assert envelope.current_s3_daily_rowset_completeness_verified is False
    assert envelope.no_bindable_catalog_in_repository is True
    assert envelope.evaluation_instance_registry_available is False
    assert envelope.landing_reason_code == ReplayIdentityOriginLandingReasonCode.LANDED.value
    assert envelope.table_row_count == 3
    assert envelope.default_harvest_obtain_empty is True
    assert (
        envelope.default_catalog_first_blocker
        == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT.value
    )
    assert envelope.default_session_provider_left_unset is True
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        default_catalog = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert (
        default_catalog.reason_code
        == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    )
    clear_v0_2_live_postgres_session_provider()


def test_injected_actuals_without_in_season_rows_fail_closed_alignment() -> None:
    train_row = make_row(harvest_business_date=date(2025, 9, 1), quantity="12.5")
    actuals = InMemoryS2ActualsSource((train_row,))

    envelope = execute_catalog_origin_from_bound_actuals(
        actuals_source=actuals,
        dataset_identity=DATASET_IDENTITY,
    )

    assert envelope.live_execution_reason_code is (
        LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_CATALOG_NOT_PRODUCED
    )
    assert envelope.catalog_reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT.value
    assert envelope.origin_entry_count == 3
    assert envelope.aligned_identity_count == 0
    assert envelope.catalog_entry_count == 0
    assert envelope.current_s3_daily_rowset_completeness_verified is False


def test_patched_session_maker_produces_catalog_from_in_season_partitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_rows, validation_rows = _in_season_rows()
    session_maker = _session_maker_with_rows(train_rows, validation_rows)
    _patch_official_counts(monkeypatch, train_rows=train_rows, validation_rows=validation_rows)

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        envelope = execute_live_catalog_origin()

    assert (
        envelope.live_execution_reason_code
        is LiveCatalogOriginExecutionReasonCode.ARTIFACT_PRODUCED
    )
    assert envelope.catalog_reason_code == CatalogArtifactReasonCode.ARTIFACT_PRODUCED.value
    assert envelope.origin_entry_count == 3
    assert envelope.aligned_identity_count == 2
    assert envelope.catalog_entry_count == 6
    assert envelope.actuals_bound is True
    assert envelope.parsed_total_row_count == 2
    assert envelope.test_row_count == 0
    assert SOURCE_002_ROW_LEVEL_READ is True
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        default_catalog = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert (
        default_catalog.reason_code
        == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    )


def test_official_live_catalog_origin_fail_closed_or_produced() -> None:
    script = """
import json
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_live_catalog_execution import (
    execute_live_catalog_origin,
)
envelope = execute_live_catalog_origin()
print(json.dumps({
    "live_execution_reason_code": envelope.live_execution_reason_code.value,
    "catalog_reason_code": envelope.catalog_reason_code,
    "origin_entry_count": envelope.origin_entry_count,
    "aligned_identity_count": envelope.aligned_identity_count,
    "catalog_entry_count": envelope.catalog_entry_count,
    "completeness_verified": envelope.current_s3_daily_rowset_completeness_verified,
    "test_remains_sealed": envelope.test_remains_sealed,
    "uses_harvest_date_as_forecast_cutoff": envelope.uses_harvest_date_as_forecast_cutoff,
    "default_harvest_obtain_empty": envelope.default_harvest_obtain_empty,
    "default_catalog_first_blocker": envelope.default_catalog_first_blocker,
    "parsed_train_row_count": envelope.parsed_train_row_count,
    "parsed_validation_row_count": envelope.parsed_validation_row_count,
    "table_row_count": envelope.table_row_count,
    "default_harvest_after": S2IdentityAlignmentHarvestSource().obtain() == (),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())
    if payload["live_execution_reason_code"] == "ARTIFACT_PRODUCED":
        assert payload["catalog_reason_code"] == "ARTIFACT_PRODUCED"
        assert payload["origin_entry_count"] == 3
        assert payload["aligned_identity_count"] > 0
        assert payload["catalog_entry_count"] == payload["aligned_identity_count"] * 3
        assert payload["completeness_verified"] is False
        assert payload["test_remains_sealed"] is True
        assert payload["uses_harvest_date_as_forecast_cutoff"] is False
        assert payload["default_harvest_obtain_empty"] is True
        assert payload["default_harvest_after"] is True
        assert payload["default_catalog_first_blocker"] in {
            "ARTIFACT_PRODUCED",
            "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT",
        }
        assert payload["parsed_train_row_count"] == OFFICIAL_TRAIN_ROW_COUNT
        assert payload["parsed_validation_row_count"] == OFFICIAL_VALIDATION_ROW_COUNT
        assert payload["table_row_count"] == 3
    else:
        assert payload["live_execution_reason_code"] != "ARTIFACT_PRODUCED"
        assert payload["completeness_verified"] is False


def test_origin_entries_stable_across_catalog_execution() -> None:
    assert len(replay_identity_origin_entries()) == 3


def test_live_module_contains_no_connection_string() -> None:
    source = LIVE_MODULE.read_text(encoding="utf-8").lower()
    assert "postgresql://" not in source
    assert "create_engine(" not in source
    assert "dsn" not in source


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
