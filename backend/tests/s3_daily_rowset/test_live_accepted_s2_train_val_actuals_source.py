"""S3-A live accepted S2 TRAIN/VALIDATION actuals source binding tests."""

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
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_DATASET_ID,
    OFFICIAL_DATASET_VERSION,
    OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_ROW_COUNT,
)
from backend.app.s3_daily_rowset.forecast_port import FakeIncumbentDailyCurveProvider
from backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source import (
    LiveAcceptedS2TrainValActualsBindingEnvelope,
    LiveAcceptedS2TrainValActualsSourceReasonCode,
    bind_live_accepted_s2_train_val_actuals_source,
)
from backend.app.s3_daily_rowset.schemas import (
    MaterializationOutcome,
    ReasonCode,
)
from backend.app.s3_daily_rowset.service import build_daily_rowset_materializer_with_live_actuals
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY, make_cell, make_row

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
LIVE_MODULE = Path("backend/app/s3_daily_rowset/live_accepted_s2_train_val_actuals_source.py")


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


def _create_tables(sync_conn: sa.Connection) -> None:
    cast(Table, S2MaterializedDatasetModel.__table__).create(sync_conn)
    cast(Table, S2MaterializedPartitionModel.__table__).create(sync_conn)


async def _persist_accepted_dataset_async(
    session: AsyncSession,
    *,
    train_rows: tuple,
    validation_rows: tuple,
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


async def _async_session_maker_with_rows(
    train_rows: tuple,
    validation_rows: tuple,
) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_create_tables)
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
    train_rows: tuple,
    validation_rows: tuple,
) -> async_sessionmaker[AsyncSession]:
    return asyncio.run(_async_session_maker_with_rows(train_rows, validation_rows))


def _patch_official_counts(
    monkeypatch: pytest.MonkeyPatch,
    *,
    train_rows: tuple,
    validation_rows: tuple,
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


@pytest.fixture
def synthetic_rows() -> tuple:
    train_row = make_row(harvest_business_date=date(2025, 9, 1), quantity="12.5")
    validation_row = make_row(harvest_business_date=date(2026, 2, 1), quantity="3.0")
    return (train_row,), (validation_row,)


def test_binding_envelope_does_not_expose_content_bytes_or_kg() -> None:
    field_names = set(LiveAcceptedS2TrainValActualsBindingEnvelope.model_fields)
    assert "content_bytes" not in field_names
    assert "actual_harvest_quantity_kg" not in field_names
    assert "farm" not in field_names
    assert "members" not in field_names


def test_synthetic_sqlite_bind_with_monkeypatched_official_counts_is_not_official_live(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_rows: tuple,
) -> None:
    train_rows, validation_rows = synthetic_rows
    session_maker = _session_maker_with_rows(train_rows, validation_rows)
    _patch_official_counts(monkeypatch, train_rows=train_rows, validation_rows=validation_rows)

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        outcome = bind_live_accepted_s2_train_val_actuals_source()

    assert outcome.envelope.bound is True
    assert outcome.envelope.reason_code is LiveAcceptedS2TrainValActualsSourceReasonCode.BOUND
    assert outcome.actuals_source is not None
    assert outcome.envelope.parsed_train_row_count == len(train_rows)
    assert outcome.envelope.parsed_validation_row_count == len(validation_rows)
    assert SOURCE_002_ROW_LEVEL_READ is True


def test_materializer_with_synthetic_live_actuals_can_lookup_observed_day(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_rows: tuple,
) -> None:
    train_rows, validation_rows = synthetic_rows
    session_maker = _session_maker_with_rows(train_rows, validation_rows)
    _patch_official_counts(monkeypatch, train_rows=train_rows, validation_rows=validation_rows)

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        built = build_daily_rowset_materializer_with_live_actuals(
            FakeIncumbentDailyCurveProvider(forecasts={}),
            dataset_identity=DATASET_IDENTITY,
        )

    assert built.materializer is not None
    row = train_rows[0]
    lookup = built.materializer.actuals_source.lookup_actual(
        make_cell(
            season=row.season,
            farm=row.farm,
            subfarm=row.subfarm,
            variety=row.variety,
        ),
        row.harvest_business_date,
    )
    assert lookup.actual_harvest_quantity_kg == train_rows[0].actual_harvest_quantity_kg


def test_official_live_window_without_reviewed_grain_fails_closed_forecast_unavailable() -> None:
    script = """
import json
from datetime import UTC, datetime
from backend.app.s3_daily_rowset.forecast_port import FakeIncumbentDailyCurveProvider
from backend.app.s3_daily_rowset.schemas import MaterializationOutcome, ReasonCode
from backend.app.s3_daily_rowset.service import build_daily_rowset_materializer_with_live_actuals
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY, make_cell
from backend.app.s3_daily_rowset.schemas import HorizonWindowRequest

built = build_daily_rowset_materializer_with_live_actuals(
    FakeIncumbentDailyCurveProvider(unavailable=True),
    dataset_identity=DATASET_IDENTITY,
)
if built.materializer is None:
    print(json.dumps({"skipped": True}))
else:
    cutoff = datetime(2026, 2, 28, 16, 0, tzinfo=UTC)
    result = built.materializer.materialize_horizon_window(
        make_cell(forecast_cutoff_at=cutoff),
        HorizonWindowRequest(evaluation_window_days=7),
    )
    print(json.dumps({
        "skipped": False,
        "outcome": result.outcome.value,
        "reason_code": result.reason_code.value if result.reason_code else None,
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
    if payload.get("skipped"):
        pytest.skip("official live binding unavailable in this environment")
    assert payload["outcome"] == MaterializationOutcome.REJECTED.value
    assert payload["reason_code"] in {
        ReasonCode.FORECAST_UNAVAILABLE.value,
        ReasonCode.WINDOW_REJECTED_UNKNOWN_OR_EXCLUDED_DAY.value,
    }


def test_official_live_binding_path_fail_closed_or_bound() -> None:
    script = """
import json
from backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source import (
    bind_live_accepted_s2_train_val_actuals_source,
)
outcome = bind_live_accepted_s2_train_val_actuals_source()
print(json.dumps({
    "bound": outcome.envelope.bound,
    "reason_code": outcome.envelope.reason_code.value,
    "train_row_count": outcome.envelope.train_row_count,
    "validation_row_count": outcome.envelope.validation_row_count,
    "test_row_count": outcome.envelope.test_row_count,
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
    if payload["bound"]:
        assert payload["reason_code"] == "BOUND"
        assert payload["train_row_count"] == OFFICIAL_TRAIN_ROW_COUNT
        assert payload["validation_row_count"] == OFFICIAL_VALIDATION_ROW_COUNT
        assert payload["test_row_count"] == 0
    else:
        assert payload["reason_code"] != "BOUND"


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
