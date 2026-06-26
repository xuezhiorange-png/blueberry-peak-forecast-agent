from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.persistence import (
    ResidualModelHashConflictError,
    load_residual_prediction_run_by_id,
    load_residual_training_run_by_id,
    save_residual_prediction_run,
    save_residual_training_run,
)
from backend.app.residual_model.schemas import FeatureValue, ResidualTrainingManifestRow
from backend.app.residual_model.service import (
    structural_only_prediction,
    train_residual_model_from_manifest,
)

RESIDUAL_TABLES = [
    ResidualModelTrainingRun.__table__,
    ResidualModelManifestRow.__table__,
    ResidualModelArtifact.__table__,
    ResidualModelPredictionRun.__table__,
    ResidualModelPredictionRow.__table__,
]


@pytest.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ResidualModelTrainingRun.metadata.create_all(
                sync_conn,
                tables=RESIDUAL_TABLES,
            )
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


def _config():
    return load_residual_model_config(
        Path("/Users/charles/Documents/智能agent开发/configs/residual_model.yaml")
    )


def _training_row(index: int) -> ResidualTrainingManifestRow:
    rainfall = str(3 + (index % 4))
    feature_values = (
        FeatureValue.model_validate(
            {
                "feature_name": "structural_arrival_p50_kg",
                "value": "100",
                "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                "source_ref": {"task9": index},
                "source_version": "v1",
                "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            }
        ),
        FeatureValue.model_validate(
            {
                "feature_name": "weather_7d_rainfall",
                "value": rainfall,
                "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                "source_ref": {"weather": rainfall},
                "source_version": "v1",
                "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                "observation_date": date(2026, 2, 28),
            }
        ),
        FeatureValue.model_validate(
            {
                "feature_name": "destination_factory_category",
                "value": "north" if index % 2 == 0 else "south",
                "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                "source_ref": {"plan": index},
                "source_version": "v1",
                "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            }
        ),
    )
    return ResidualTrainingManifestRow(
        season_id=(index % 3) + 1,
        destination_factory_id=(index % 2) + 1,
        task9_run_id=100 + index,
        task9_result_hash=f"{index + 1:064x}"[-64:],
        as_of_date=date(2026, 3, 1),
        target_arrival_local_date=date(2026, 3, 2 + (index % 5)),
        forecast_horizon_days=1 + (index % 5),
        label_actual_snapshot={
            "build_run_id": 200 + index,
            "source_max_raw_id": 1000 + index,
            "aggregation_version": "task3-v1",
            "config_hash": "c" * 64,
            "source_cutoff": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        },
        feature_actual_snapshot={
            "build_run_id": 300 + index,
            "source_max_raw_id": 900 + index,
            "aggregation_version": "task3-v1",
            "config_hash": "d" * 64,
            "source_cutoff": datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        },
        observed_effective_receipt_kg=Decimal("105") + Decimal(index % 7),
        structural_p50_kg=Decimal("100"),
        structural_p80_kg=Decimal("110"),
        structural_p90_kg=Decimal("120"),
        residual_label_kg=Decimal(5 + (index % 7)),
        feature_values=feature_values,
        feature_vector_hash=canonical_payload_hash(
            [item.model_dump(mode="json") for item in feature_values]
        ),
        feature_visibility_audit_hash="a" * 64,
        split="train" if index < 20 else "validation",
        include=True,
        sample_weight=Decimal("1"),
        source_refs=("task9", "analytics"),
    )


def _eligible_training():
    rows = [_training_row(index) for index in range(30)]
    result = train_residual_model_from_manifest(rows=rows, config=_config())
    assert result.execution_status == "completed"
    assert result.eligibility_status == "eligible"
    return rows, result


@pytest.mark.asyncio
async def test_save_and_load_completed_eligible_training_run(sqlite_session: AsyncSession) -> None:
    rows, result = _eligible_training()

    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    loaded = await load_residual_training_run_by_id(sqlite_session, run_id=run.id)

    assert loaded is not None
    assert loaded.execution_status == "completed"
    assert loaded.eligibility_status == "eligible"
    assert len(loaded.artifacts) == 3


@pytest.mark.asyncio
async def test_save_and_load_blocked_training_run(sqlite_session: AsyncSession) -> None:
    result = train_residual_model_from_manifest(rows=[], config=_config())

    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=[])
    loaded = await load_residual_training_run_by_id(sqlite_session, run_id=run.id)

    assert loaded is not None
    assert loaded.execution_status == "blocked"
    assert loaded.artifacts == ()


@pytest.mark.asyncio
async def test_training_signature_idempotency(sqlite_session: AsyncSession) -> None:
    rows, result = _eligible_training()

    first = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    second = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)

    assert first.id == second.id
    assert (
        await sqlite_session.scalar(select(func.count()).select_from(ResidualModelTrainingRun))
        == 1
    )


@pytest.mark.asyncio
async def test_training_signature_conflict(sqlite_session: AsyncSession) -> None:
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET canonical_payload_hash = :payload_hash "
            "WHERE id = :run_id"
        ),
        {"payload_hash": "f" * 64, "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelHashConflictError):
        await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)


@pytest.mark.asyncio
async def test_save_and_load_structural_only_prediction_run(sqlite_session: AsyncSession) -> None:
    prediction = structural_only_prediction(
        model_run_id=None,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash="b" * 64,
        structural_rows=[
            {
                "destination_factory_id": 1,
                "arrival_local_date": date(2026, 3, 2),
                "forecast_horizon_days": 1,
                "structural_p50_kg": Decimal("100"),
                "structural_p80_kg": Decimal("110"),
                "structural_p90_kg": Decimal("120"),
            }
        ],
        fallback_reason="model_ineligible",
    )

    run = await save_residual_prediction_run(
        sqlite_session,
        result=prediction,
        feature_schema_version="task10-features-v1",
        feature_schema_hash="e" * 64,
        artifact_hashes=[],
    )
    loaded = await load_residual_prediction_run_by_id(sqlite_session, run_id=run.id)

    assert loaded is not None
    assert loaded.execution_status == "completed"
    assert loaded.mode == "structural_only"
    assert len(loaded.rows) == 1
