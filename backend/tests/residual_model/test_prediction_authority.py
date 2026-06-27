"""Section 12: Missing regression tests — prediction authority tests.

Tests that save_residual_prediction_run and load_residual_prediction_run_by_id
detect various forms of DB-level corruption.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, Integer, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.analytics import AnalyticsBuildRun, FactorySeasonPeakMetric
from backend.app.models.master_data import Factory, Season
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelExecutionAttempt,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.persistence import (
    ResidualModelPersistenceError,
    ResidualModelPersistenceIntegrityError,
    load_residual_prediction_run_by_id,
    save_residual_prediction_run,
    save_residual_training_run,
)
from backend.app.residual_model.service import structural_only_prediction
from backend.tests.residual_model.test_persistence import (
    _eligible_training,
    _prediction_with_task3,
    _seed_task3_build,
)

RESIDUAL_TABLES = [
    ResidualModelTrainingRun.__table__,
    ResidualModelManifestRow.__table__,
    ResidualModelArtifact.__table__,
    ResidualModelPredictionRun.__table__,
    ResidualModelPredictionRow.__table__,
    ResidualModelExecutionAttempt.__table__,
]

TASK3_TABLES = [
    AnalyticsBuildRun.__table__,
    FactorySeasonPeakMetric.__table__,
    Season.__table__,
    Factory.__table__,
]


@pytest.fixture
async def sqlite_session_with_task3() -> AsyncSession:
    """SQLite session with both residual model AND Task 3 tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    AnalyticsBuildRun.__table__.c.id.type = Integer()
    AnalyticsBuildRun.__table__.c.season_id.type = Integer()
    AnalyticsBuildRun.__table__.c.source_max_raw_id.type = Integer()
    AnalyticsBuildRun.__table__.c.source_eligible_row_count.type = Integer()
    AnalyticsBuildRun.__table__.c.daily_fact_row_count.type = Integer()
    AnalyticsBuildRun.__table__.c.config_snapshot.type = JSON()
    FactorySeasonPeakMetric.__table__.c.id.type = Integer()
    FactorySeasonPeakMetric.__table__.c.build_run_id.type = Integer()
    FactorySeasonPeakMetric.__table__.c.season_id.type = Integer()
    FactorySeasonPeakMetric.__table__.c.factory_id.type = Integer()
    FactorySeasonPeakMetric.__table__.c.calendar_day_count.type = Integer()
    FactorySeasonPeakMetric.__table__.c.observed_day_count.type = Integer()
    FactorySeasonPeakMetric.__table__.c.spring_festival_day_count.type = Integer()

    all_tables = RESIDUAL_TABLES + TASK3_TABLES
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ResidualModelTrainingRun.metadata.create_all(
                sync_conn, tables=all_tables
            )
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def stub_task9_authority(monkeypatch: pytest.MonkeyPatch) -> dict[int, str]:
    authority_hashes = {
        10: "c" * 64,
        11: "c" * 64,
    }

    async def _fake_load_harvest_state_output_by_id(
        session: AsyncSession,
        *,
        run_id: int,
    ) -> object | None:
        result_hash = authority_hashes.get(run_id)
        if result_hash is None:
            return None
        return SimpleNamespace(status="completed", result_hash=result_hash)

    monkeypatch.setattr(
        "backend.app.residual_model.persistence.load_harvest_state_output_by_id",
        _fake_load_harvest_state_output_by_id,
    )
    return authority_hashes


# ── 1. Prediction parent + canonical output + payload hash all modified ──


@pytest.mark.asyncio
async def test_prediction_authority_parent_output_hash_coordinated_modification(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Parent run-level columns (fallback_reason, prediction_hash) are
    modified after save.  The independent derivation in Section 10
    should catch this by rebuilding from row-level data and authorities.
    """
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session, factory_ids=(701,))

    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
        factory_id=701,
    )
    run = await save_residual_prediction_run(
        session,
        result=result,
        feature_schema_version="task10-features-v1",
        feature_schema_hash="e" * 64,
        artifact_hashes=[],
    )

    await session.execute(
        text(
            "UPDATE residual_model_prediction_run "
            "SET fallback_reason = :new_reason, "
            "    prediction_hash = :new_hash "
            "WHERE id = :run_id"
        ),
        {"new_reason": "fraud_reason", "new_hash": "f" * 64, "run_id": run.id},
    )
    await session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(session, run_id=run.id)


# ── 2. Task 9 hash modified ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prediction_authority_task9_hash_modified(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """task9_result_hash on run and rows are changed.
    Load should detect via independent derivation of prediction_hash.
    """
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session, factory_ids=(701,))

    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
        factory_id=701,
    )
    run = await save_residual_prediction_run(
        session,
        result=result,
        feature_schema_version="task10-features-v1",
        feature_schema_hash="e" * 64,
        artifact_hashes=[],
    )

    await session.execute(
        text(
            "UPDATE residual_model_prediction_run "
            "SET task9_result_hash = :new_hash "
            "WHERE id = :run_id"
        ),
        {"new_hash": "f" * 64, "run_id": run.id},
    )
    await session.execute(
        text(
            "UPDATE residual_model_prediction_row "
            "SET task9_result_hash = :new_hash "
            "WHERE prediction_run_id = :run_id"
        ),
        {"new_hash": "f" * 64, "run_id": run.id},
    )
    await session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(session, run_id=run.id)


# ── 3. Task 3 build identity modified ────────────────────────────────────


@pytest.mark.asyncio
async def test_prediction_authority_task3_build_identity_modified(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Input_snapshot's build_run_id is changed to point to a different
    AnalyticsBuildRun.  save_residual_prediction_run should detect this.
    """
    session = sqlite_session_with_task3
    await _seed_task3_build(
        session,
        build_run_id=1,
        factory_ids=(701,),
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    await _seed_task3_build(
        session,
        build_run_id=2,
        factory_ids=(702,),
        source_max_raw_id=200,
        config_hash="z" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )

    result = _prediction_with_task3(
        build_run_id=1,
        feature_source_max_raw_id=100,
        feature_config_hash="a" * 64,
        feature_source_cutoff=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        factory_id=701,
    )

    mutated_snapshot = dict(result.input_snapshot)
    mutated_snapshot["feature_analytics_build_run_id"] = 2
    mutated_snapshot["feature_actual_snapshot"] = {
        "build_run_id": 2,
        "source_max_raw_id": 200,
        "aggregation_version": "task3-v1",
        "config_hash": "z" * 64,
        "source_cutoff": datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    }
    result = result.model_copy(update={"input_snapshot": mutated_snapshot})

    with pytest.raises(ResidualModelPersistenceError):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


# ── 4. Artifact hash modified (with training run) ────────────────────────


@pytest.mark.asyncio
async def test_prediction_authority_artifact_hash_modified(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Artifact_hashes on the prediction run are changed after save.
    The prediction is linked to an eligible training run, so the load
    should detect via Section 8.9 comparison with training artifacts.
    """
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session, factory_ids=(701,))

    # Create an eligible training run first
    rows, training_result = _eligible_training()
    training_run = await save_residual_training_run(
        session, result=training_result, manifest_rows=rows
    )
    # Get the training artifact hashes
    training_artifact_rows = (await session.execute(
        text("SELECT artifact_sha256 FROM residual_model_artifact "
             "WHERE training_run_id = :tid ORDER BY quantile_label"),
        {"tid": training_run.id},
    )).fetchall()
    training_artifact_hashes = [row[0] for row in training_artifact_rows]

    # Build a structural_only prediction that references the training run
    input_snapshot = {
        "model_run_id": training_run.id,
        "training_signature": training_run.training_signature,
        "task9_run_id": 10,
        "task9_result_hash": "c" * 64,
        "feature_analytics_build_run_id": build.id,
        "feature_actual_snapshot": {
            "build_run_id": build.id,
            "source_max_raw_id": build.source_max_raw_id,
            "aggregation_version": "task3-v1",
            "config_hash": build.config_hash,
            "source_cutoff": build.finished_at,
        },
        "supplemental_feature_values": [],
        "feature_audit_hashes": [],
        "feature_rows": [],
        "artifact_hashes": training_artifact_hashes,
        "config_hash": training_run.config_hash,
        "feature_schema_version": training_run.feature_schema_version,
        "feature_schema_hash": training_run.feature_schema_hash,
        "projection_version": "v1",
        "fallback_policy": "structural_only_fallback",
    }
    result = structural_only_prediction(
        model_run_id=training_run.id,
        task9_run_id=10,
        task9_result_hash="c" * 64,
        config_hash=training_run.config_hash,
        structural_rows=[{
            "destination_factory_id": 701,
            "arrival_local_date": date(2026, 3, 2),
            "forecast_horizon_days": 1,
            "structural_p50_kg": Decimal("100"),
            "structural_p80_kg": Decimal("110"),
            "structural_p90_kg": Decimal("120"),
        }],
        fallback_reason="model_ineligible",
        input_snapshot=input_snapshot,
    )
    run = await save_residual_prediction_run(
        session,
        result=result,
        feature_schema_version=training_run.feature_schema_version,
        feature_schema_hash=training_run.feature_schema_hash,
        artifact_hashes=training_artifact_hashes,
    )

    # Mutate artifact_hashes column
    await session.execute(
        text(
            "UPDATE residual_model_prediction_run "
            "SET artifact_hashes = :new_hashes "
            "WHERE id = :run_id"
        ),
        {
            "new_hashes": json.dumps(["f" * 64, "g" * 64, "h" * 64]),
            "run_id": run.id,
        },
    )
    await session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(session, run_id=run.id)


# ── 5. Schema version/hash modified ──────────────────────────────────────


@pytest.mark.asyncio
async def test_prediction_authority_schema_hash_mismatch_on_load(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Feature_schema_hash modified after save, detected on load
    via Section 8.8 comparison with the training run.
    """
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session, factory_ids=(701,))

    # Create an eligible training run first
    rows, training_result = _eligible_training()
    training_run = await save_residual_training_run(
        session, result=training_result, manifest_rows=rows
    )
    training_artifact_rows = (await session.execute(
        text("SELECT artifact_sha256 FROM residual_model_artifact "
             "WHERE training_run_id = :tid ORDER BY quantile_label"),
        {"tid": training_run.id},
    )).fetchall()
    training_artifact_hashes = [row[0] for row in training_artifact_rows]

    # Create prediction linked to training run
    input_snapshot = {
        "model_run_id": training_run.id,
        "training_signature": training_run.training_signature,
        "task9_run_id": 10,
        "task9_result_hash": "c" * 64,
        "feature_analytics_build_run_id": build.id,
        "feature_actual_snapshot": {
            "build_run_id": build.id,
            "source_max_raw_id": build.source_max_raw_id,
            "aggregation_version": "task3-v1",
            "config_hash": build.config_hash,
            "source_cutoff": build.finished_at,
        },
        "supplemental_feature_values": [],
        "feature_audit_hashes": [],
        "feature_rows": [],
        "artifact_hashes": training_artifact_hashes,
        "config_hash": training_run.config_hash,
        "feature_schema_version": training_run.feature_schema_version,
        "feature_schema_hash": training_run.feature_schema_hash,
        "projection_version": "v1",
        "fallback_policy": "structural_only_fallback",
    }
    result = structural_only_prediction(
        model_run_id=training_run.id,
        task9_run_id=10,
        task9_result_hash="c" * 64,
        config_hash=training_run.config_hash,
        structural_rows=[{
            "destination_factory_id": 701,
            "arrival_local_date": date(2026, 3, 2),
            "forecast_horizon_days": 1,
            "structural_p50_kg": Decimal("100"),
            "structural_p80_kg": Decimal("110"),
            "structural_p90_kg": Decimal("120"),
        }],
        fallback_reason="model_ineligible",
        input_snapshot=input_snapshot,
    )
    run = await save_residual_prediction_run(
        session,
        result=result,
        feature_schema_version=training_run.feature_schema_version,
        feature_schema_hash=training_run.feature_schema_hash,
        artifact_hashes=training_artifact_hashes,
    )

    # Mutate the feature_schema_hash column
    await session.execute(
        text(
            "UPDATE residual_model_prediction_run "
            "SET feature_schema_hash = :new_hash "
            "WHERE id = :run_id"
        ),
        {"new_hash": "f" * 64, "run_id": run.id},
    )
    await session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(session, run_id=run.id)


@pytest.mark.asyncio
async def test_prediction_authority_schema_version_mismatch_with_training_run(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """When a prediction is linked to a training run, save should
    detect mismatched feature_schema_version."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session, factory_ids=(701,))

    # Create an eligible training run
    rows, training_result = _eligible_training()
    training_run = await save_residual_training_run(
        session, result=training_result, manifest_rows=rows
    )

    training_artifact_rows = (await session.execute(
        text("SELECT artifact_sha256 FROM residual_model_artifact "
             "WHERE training_run_id = :tid ORDER BY quantile_label"),
        {"tid": training_run.id},
    )).fetchall()
    training_artifact_hashes = [row[0] for row in training_artifact_rows]

    input_snapshot = {
        "model_run_id": training_run.id,
        "training_signature": training_run.training_signature,
        "task9_run_id": 10,
        "task9_result_hash": "c" * 64,
        "feature_analytics_build_run_id": build.id,
        "feature_actual_snapshot": {
            "build_run_id": build.id,
            "source_max_raw_id": build.source_max_raw_id,
            "aggregation_version": "task3-v1",
            "config_hash": build.config_hash,
            "source_cutoff": build.finished_at,
        },
        "supplemental_feature_values": [],
        "feature_audit_hashes": [],
        "feature_rows": [],
        "artifact_hashes": training_artifact_hashes,
        "config_hash": training_run.config_hash,
        "feature_schema_version": training_run.feature_schema_version,
        "feature_schema_hash": training_run.feature_schema_hash,
        "projection_version": "v1",
        "fallback_policy": "structural_only_fallback",
    }
    result = structural_only_prediction(
        model_run_id=training_run.id,
        task9_run_id=10,
        task9_result_hash="c" * 64,
        config_hash=training_run.config_hash,
        structural_rows=[{
            "destination_factory_id": 701,
            "arrival_local_date": date(2026, 3, 2),
            "forecast_horizon_days": 1,
            "structural_p50_kg": Decimal("100"),
            "structural_p80_kg": Decimal("110"),
            "structural_p90_kg": Decimal("120"),
        }],
        fallback_reason="model_ineligible",
        input_snapshot=input_snapshot,
    )

    # Try to save with wrong schema version - should be rejected
    with pytest.raises(ResidualModelPersistenceError):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v999",
            feature_schema_hash=training_run.feature_schema_hash,
            artifact_hashes=training_artifact_hashes,
        )
