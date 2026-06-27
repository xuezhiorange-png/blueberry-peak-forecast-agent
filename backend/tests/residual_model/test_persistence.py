from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text
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
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.persistence import (
    ResidualModelPersistenceError,
    ResidualModelPersistenceIntegrityError,
    load_residual_prediction_run_by_id,
    load_residual_training_artifacts,
    load_residual_training_run_by_id,
    save_residual_prediction_run,
    save_residual_training_run,
)
from backend.app.residual_model.schemas import (
    FeatureValue,
    ResidualPredictionExecutionResult,
    ResidualTrainingManifestRow,
)
from backend.app.residual_model.service import (
    structural_only_prediction,
    train_residual_model_from_manifest,
)
from backend.tests.residual_model.support import residual_model_config_path

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


@pytest.fixture(autouse=True)
def stub_task9_authority(monkeypatch: pytest.MonkeyPatch) -> dict[int, str]:
    authority_hashes = {
        10: "a" * 64,
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


def _config():
    return load_residual_model_config(residual_model_config_path())


def _relaxed_config():
    config = _config()
    eligibility = replace(
        config.rules.eligibility,
        min_training_rows=1,
        min_seasons=1,
        min_factories=1,
        max_validation_wmape=1.0,
        require_improvement_over_structural=False,
        max_fallback_rate=1.0,
    )
    return replace(config, rules=replace(config.rules, eligibility=eligibility))


def _training_row(
    index: int,
    *,
    season_id: int | None = None,
    split: str | None = None,
) -> ResidualTrainingManifestRow:
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
        season_id=season_id if season_id is not None else (index % 3) + 1,
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
        split=split if split is not None else ("train" if index < 20 else "validation"),
        include=True,
        sample_weight=Decimal("1"),
        source_refs=("task9", "analytics"),
    )


def _eligible_training():
    rows = [
        _training_row(
            index,
            season_id=(index % 2) + 1 if index < 20 else 3,
            split="train" if index < 20 else "validation",
        )
        for index in range(30)
    ]
    result = train_residual_model_from_manifest(rows=rows, config=_relaxed_config())
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
async def test_training_signature_idempotency_rejects_corrupted_existing_run(
    sqlite_session: AsyncSession,
) -> None:
    rows, result = _eligible_training()

    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_manifest_row "
            "SET observed_effective_receipt_kg = :value "
            "WHERE training_run_id = :run_id AND row_index = 1"
        ),
        {"value": "999.000000", "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)


@pytest.mark.asyncio
async def test_training_signature_corrupted_parent_is_rejected_by_integrity_gate(
    sqlite_session: AsyncSession,
) -> None:
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

    with pytest.raises(ResidualModelPersistenceIntegrityError):
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


@pytest.mark.asyncio
async def test_prediction_signature_idempotency_rejects_corrupted_existing_run(
    sqlite_session: AsyncSession,
) -> None:
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
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_prediction_row "
            "SET feature_vector_hash = :value "
            "WHERE prediction_run_id = :run_id"
        ),
        {"value": "f" * 64, "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await save_residual_prediction_run(
            sqlite_session,
            result=prediction,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


@pytest.mark.asyncio
async def test_load_training_run_detects_missing_manifest_row(
    sqlite_session: AsyncSession,
) -> None:
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "DELETE FROM residual_model_manifest_row "
            "WHERE training_run_id = :run_id AND row_index = 1"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_load_training_run_detects_modified_observed_receipt_column(
    sqlite_session: AsyncSession,
) -> None:
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_manifest_row "
            "SET observed_effective_receipt_kg = :value "
            "WHERE training_run_id = :run_id AND row_index = 1"
        ),
        {"value": "1234.000000", "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_load_training_run_detects_modified_include_flag(
    sqlite_session: AsyncSession,
) -> None:
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_manifest_row "
            "SET include = 0 "
            "WHERE training_run_id = :run_id AND row_index = 1"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_load_training_artifacts_detects_metadata_mismatch(
    sqlite_session: AsyncSession,
) -> None:
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_artifact "
            "SET config_hash = :config_hash "
            "WHERE training_run_id = :run_id AND quantile_label = 'P50'"
        ),
        {"config_hash": "f" * 64, "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_artifacts(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("column_name", "value", "match"),
    [
        ("python_version", "0.0.0", "python version mismatch"),
        ("numpy_version", "0.0.0", "numpy version mismatch"),
        ("sklearn_version", "0.0.0", "sklearn version mismatch"),
    ],
)
async def test_load_training_run_detects_parent_dependency_version_mismatch(
    sqlite_session: AsyncSession,
    column_name: str,
    value: str,
    match: str,
) -> None:
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            f"UPDATE residual_model_training_run SET {column_name} = :value "
            "WHERE id = :run_id"
        ),
        {"value": value, "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError, match=match):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_load_training_run_detects_corrupted_artifact_bytes(
    sqlite_session: AsyncSession,
) -> None:
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_artifact "
            "SET artifact_bytes = :artifact_bytes "
            "WHERE training_run_id = :run_id AND quantile_label = 'P50'"
        ),
        {"artifact_bytes": b"corrupted-bytes", "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)


@pytest.mark.asyncio
async def test_load_prediction_run_detects_deleted_child_row(
    sqlite_session: AsyncSession,
) -> None:
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
    await sqlite_session.execute(
        text(
            "DELETE FROM residual_model_prediction_row "
            "WHERE prediction_run_id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_load_prediction_run_detects_modified_child_row(
    sqlite_session: AsyncSession,
) -> None:
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
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_prediction_row "
            "SET feature_vector_hash = :feature_vector_hash "
            "WHERE prediction_run_id = :run_id"
        ),
        {"feature_vector_hash": "f" * 64, "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_load_prediction_run_detects_modified_input_signature(
    sqlite_session: AsyncSession,
) -> None:
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
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_prediction_run "
            "SET prediction_input_signature = :value "
            "WHERE id = :run_id"
        ),
        {"value": "f" * 64, "run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(sqlite_session, run_id=run.id)


# ── Section 9: Task 3 authority binding tests ────────────────────────────────


@pytest.fixture
async def sqlite_session_with_task3() -> AsyncSession:
    """SQLite session with both residual model AND Task 3 tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from sqlalchemy import JSON as SAJSON
    from sqlalchemy import Integer as SAInteger

    AnalyticsBuildRun.__table__.c.id.type = SAInteger()
    AnalyticsBuildRun.__table__.c.season_id.type = SAInteger()
    AnalyticsBuildRun.__table__.c.source_max_raw_id.type = SAInteger()
    AnalyticsBuildRun.__table__.c.source_eligible_row_count.type = SAInteger()
    AnalyticsBuildRun.__table__.c.daily_fact_row_count.type = SAInteger()
    AnalyticsBuildRun.__table__.c.config_snapshot.type = SAJSON()
    FactorySeasonPeakMetric.__table__.c.id.type = SAInteger()
    FactorySeasonPeakMetric.__table__.c.build_run_id.type = SAInteger()
    FactorySeasonPeakMetric.__table__.c.season_id.type = SAInteger()
    FactorySeasonPeakMetric.__table__.c.factory_id.type = SAInteger()
    FactorySeasonPeakMetric.__table__.c.calendar_day_count.type = SAInteger()
    FactorySeasonPeakMetric.__table__.c.observed_day_count.type = SAInteger()
    FactorySeasonPeakMetric.__table__.c.spring_festival_day_count.type = SAInteger()

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


async def _seed_task3_build(
    session: AsyncSession,
    *,
    build_run_id: int = 1,
    season_id: int = 1,
    source_max_raw_id: int = 100,
    config_hash: str | None = None,
    finished_at: datetime | None = None,
    aggregation_version: str = "task3-v1",
    factory_ids: tuple[int, ...] = (701,),
    analysis_start_date: date | None = None,
    analysis_end_date: date | None = None,
) -> AnalyticsBuildRun:
    """Seed an AnalyticsBuildRun with FactorySeasonPeakMetric coverage."""
    if config_hash is None:
        config_hash = "a" * 64
    if finished_at is None:
        finished_at = datetime(2026, 2, 28, 12, 0, tzinfo=UTC)

    build = AnalyticsBuildRun(
        id=build_run_id,
        season_id=season_id,
        aggregation_version=aggregation_version,
        source_max_raw_id=source_max_raw_id,
        config_hash=config_hash,
        config_snapshot={"version": "task3-v1", "analysis_months": [1, 2, 3, 4]},
        status="completed",
        source_eligible_row_count=1,
        source_eligible_weight_kg=Decimal("1"),
        daily_fact_row_count=1,
        started_at=finished_at,
        finished_at=finished_at,
    )
    session.add(build)
    await session.flush()

    for factory_id in factory_ids:
        session.add(
            FactorySeasonPeakMetric(
                id=build_run_id * 1000 + factory_id,
                build_run_id=build.id,
                season_id=season_id,
                factory_id=factory_id,
                analysis_start_date=analysis_start_date or date(2026, 1, 1),
                analysis_end_date=analysis_end_date or date(2026, 3, 31),
                calendar_day_count=90,
                observed_day_count=90,
                total_weight_kg=Decimal("1000"),
                single_day_peak_kg=Decimal("100"),
                single_day_peak_date=date(2026, 2, 15),
                stable_median_3d_peak_kg=Decimal("90"),
                stable_median_3d_peak_date=date(2026, 2, 15),
                mean_3d_peak_kg=Decimal("85"),
                mean_3d_peak_date=date(2026, 2, 15),
                peak_concentration=Decimal("0.5"),
                variety_hhi=Decimal("0.3"),
                farm_hhi=Decimal("0.4"),
                subfarm_hhi=Decimal("0.2"),
                unknown_farm_weight_share=Decimal("0"),
                unknown_subfarm_weight_share=Decimal("0"),
                spring_festival_day_count=0,
                computed_at=finished_at,
            )
        )
    await session.flush()
    return build


def _prediction_with_task3(
    *,
    build_run_id: int | None = 1,
    feature_source_max_raw_id: int = 100,
    feature_aggregation_version: str = "task3-v1",
    feature_config_hash: str | None = None,
    feature_source_cutoff: datetime | None = None,
    factory_id: int = 701,
    arrival_date: date | None = None,
    config_hash: str | None = None,
    task9_run_id: int = 11,
    task9_result_hash: str | None = None,
) -> ResidualPredictionExecutionResult:
    """Create a prediction result with Task 3 feature_actual_snapshot for testing."""
    if config_hash is None:
        config_hash = "b" * 64
    if feature_config_hash is None:
        feature_config_hash = "a" * 64
    if feature_source_cutoff is None:
        feature_source_cutoff = datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    if task9_result_hash is None:
        task9_result_hash = "c" * 64
    if arrival_date is None:
        arrival_date = date(2026, 3, 2)

    feature_actual_snapshot = {
        "build_run_id": build_run_id,
        "source_max_raw_id": feature_source_max_raw_id,
        "aggregation_version": feature_aggregation_version,
        "config_hash": feature_config_hash,
        "source_cutoff": feature_source_cutoff,
    }
    input_snapshot = {
        "model_run_id": None,
        "training_signature": "d" * 64,
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "feature_analytics_build_run_id": build_run_id,
        "feature_actual_snapshot": feature_actual_snapshot,
        "supplemental_feature_values": [],
        "feature_audit_hashes": [],
        "feature_rows": [],
        "artifact_hashes": [],
        "config_hash": config_hash,
        "feature_schema_version": "task10-features-v1",
        "feature_schema_hash": "e" * 64,
        "projection_version": "v1",
        "fallback_policy": "structural_only_fallback",
    }
    row = {
        "destination_factory_id": factory_id,
        "arrival_local_date": arrival_date,
        "forecast_horizon_days": 1,
        "structural_p50_kg": Decimal("100"),
        "structural_p80_kg": Decimal("110"),
        "structural_p90_kg": Decimal("120"),
    }

    result = structural_only_prediction(
        model_run_id=None,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        config_hash=config_hash,
        structural_rows=[row],
        fallback_reason="model_ineligible",
        input_snapshot=input_snapshot,
    )
    return result


@pytest.mark.asyncio
async def test_save_and_load_prediction_with_task3_authority(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Happy path: save and load a prediction run with full Task 3 authority binding."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session)
    await session.commit()

    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
        feature_aggregation_version=build.aggregation_version,
    )

    run = await save_residual_prediction_run(
        session,
        result=result,
        feature_schema_version="task10-features-v1",
        feature_schema_hash="e" * 64,
        artifact_hashes=[],
    )
    loaded = await load_residual_prediction_run_by_id(session, run_id=run.id)
    assert loaded is not None
    assert loaded.execution_status == "completed"


@pytest.mark.asyncio
async def test_task3_authority_rejects_wrong_build_run_id(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Snapshot build_run_id does not match the actual AnalyticsBuildRun."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session, build_run_id=1)
    await session.commit()

    # Use build_run_id=2 in snapshot but only build_run_id=1 exists
    result = _prediction_with_task3(
        build_run_id=2,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
    )

    with pytest.raises(ResidualModelPersistenceError, match="was not found"):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


@pytest.mark.asyncio
async def test_task3_authority_rejects_wrong_source_max_raw_id(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Coordinated mutation of source_max_raw_id detected."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session, build_run_id=1, source_max_raw_id=100)
    await session.commit()

    # Use source_max_raw_id=999 in snapshot while build has 100
    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=999,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
    )

    with pytest.raises(ResidualModelPersistenceError, match="source_max_raw_id authority mismatch"):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


@pytest.mark.asyncio
async def test_task3_authority_rejects_wrong_config_hash(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Coordinated mutation of config_hash detected."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(session, build_run_id=1, config_hash="a" * 64)
    await session.commit()

    # Use different config_hash in snapshot
    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash="f" * 64,
        feature_source_cutoff=build.finished_at,
    )

    with pytest.raises(ResidualModelPersistenceError, match="config_hash authority mismatch"):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


@pytest.mark.asyncio
async def test_task3_authority_rejects_wrong_source_cutoff(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Coordinated mutation of source_cutoff detected."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(
        session,
        build_run_id=1,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    await session.commit()

    # Use wrong source_cutoff in snapshot
    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(ResidualModelPersistenceError, match="source_cutoff authority mismatch"):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


@pytest.mark.asyncio
async def test_task3_authority_rejects_uncovered_factory(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Destination factory not in frozen coverage (FactorySeasonPeakMetric) is rejected."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(
        session,
        build_run_id=1,
        factory_ids=(701,),  # Only factory 701 is covered
    )
    await session.commit()

    # Use factory 999 which is NOT in coverage
    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
        factory_id=999,
    )

    with pytest.raises(
        ResidualModelPersistenceError,
        match="is not in AnalyticsBuildRun",
    ):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


@pytest.mark.asyncio
async def test_task3_authority_rejects_date_outside_calendar(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """source_cutoff date outside analysis calendar coverage is rejected."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(
        session,
        build_run_id=1,
        factory_ids=(701,),
        finished_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),  # June, outside Jan-Mar range
        analysis_start_date=date(2026, 1, 1),
        analysis_end_date=date(2026, 3, 31),
    )
    await session.commit()

    # source_cutoff (June 1) is after analysis calendar end (March 31)
    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
        arrival_date=date(2026, 6, 15),
    )

    with pytest.raises(
        ResidualModelPersistenceError,
        match="source_cutoff date is after analysis calendar end",
    ):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


@pytest.mark.asyncio
async def test_task3_authority_rejects_source_cutoff_after_asof(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """source_cutoff after prediction as-of contract is rejected."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(
        session,
        build_run_id=1,
        factory_ids=(701,),
        finished_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
    )
    await session.commit()

    # source_cutoff date = 2026-03-10, but earliest arrival = 2026-03-02
    # This should fail because cutoff (March 10) > arrival (March 2)
    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
        arrival_date=date(2026, 3, 2),
    )

    with pytest.raises(
        ResidualModelPersistenceError,
        match="source_cutoff is later than prediction as-of contract",
    ):
        await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version="task10-features-v1",
            feature_schema_hash="e" * 64,
            artifact_hashes=[],
        )


@pytest.mark.asyncio
async def test_task3_authority_load_rejects_modified_source_cutoff(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Load detects a modified source_cutoff in the stored snapshot."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(
        session,
        build_run_id=1,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    await session.commit()

    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
    )

    run = await save_residual_prediction_run(
        session,
        result=result,
        feature_schema_version="task10-features-v1",
        feature_schema_hash="e" * 64,
        artifact_hashes=[],
    )

    # Directly corrupt the source_cutoff in the stored input_snapshot
    await session.execute(
        text(
            "UPDATE residual_model_prediction_run "
            "SET input_snapshot = json_set(input_snapshot, "
            "'$.feature_actual_snapshot.source_cutoff', '2026-03-15T12:00:00+00:00') "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await session.commit()

    with pytest.raises(
        (ResidualModelPersistenceError, ResidualModelPersistenceIntegrityError),
    ):
        await load_residual_prediction_run_by_id(session, run_id=run.id)


@pytest.mark.asyncio
async def test_task3_authority_load_rejects_deleted_factory_coverage(
    sqlite_session_with_task3: AsyncSession,
) -> None:
    """Load detects when factory coverage rows are deleted after save."""
    session = sqlite_session_with_task3
    build = await _seed_task3_build(
        session,
        build_run_id=1,
        factory_ids=(701,),
    )
    await session.commit()

    result = _prediction_with_task3(
        build_run_id=build.id,
        feature_source_max_raw_id=build.source_max_raw_id,
        feature_config_hash=build.config_hash,
        feature_source_cutoff=build.finished_at,
    )

    run = await save_residual_prediction_run(
        session,
        result=result,
        feature_schema_version="task10-features-v1",
        feature_schema_hash="e" * 64,
        artifact_hashes=[],
    )

    # Delete the factory coverage
    await session.execute(
        text("DELETE FROM factory_season_peak_metric WHERE build_run_id = :bid"),
        {"bid": build.id},
    )
    await session.commit()

    with pytest.raises(
        (ResidualModelPersistenceError, ResidualModelPersistenceIntegrityError),
    ):
        await load_residual_prediction_run_by_id(session, run_id=run.id)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10: Complete parent parity independent derivation tests
#
# Each test corrupts a single stored column (or a coordinated pair) and verifies
# that the load integrity gate catches it — confirming the independent derivation
# does not rely on the corrupted column itself.
# ═══════════════════════════════════════════════════════════════════════════════

# ── Training: single-field corruption tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_config_snapshot(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting config_snapshot column is caught by independent re-serialization."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET config_snapshot = json_set(config_snapshot, '$.model_version', 'corrupted') "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_manifest_snapshot_rows(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting manifest_snapshot.rows is caught by independent rebuild."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    # Remove one row from the stored manifest_snapshot
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET manifest_snapshot = json_set(manifest_snapshot, '$.rows', json('[]')) "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_manifest_snapshot_summary(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting manifest_snapshot.summary is caught by independent summary rebuild."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET manifest_snapshot = json_set(manifest_snapshot, "
            "'$.summary.row_count', 9999) "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_training_metrics(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting training_metrics column is caught by separate-column comparison."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET training_metrics = json_set(training_metrics, '$.row_count', 9999) "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_validation_metrics(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting validation_metrics column is caught by independent re-extraction."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET validation_metrics = json_set(validation_metrics, '$.row_count', 9999) "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_python_version(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting python_version column is caught by independent derivation from artifacts."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET python_version = 'corrupted' "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_numpy_version(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting numpy_version column is caught by independent derivation from artifacts."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET numpy_version = 'corrupted' "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_sklearn_version(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting sklearn_version column is caught by independent derivation from artifacts."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET sklearn_version = 'corrupted' "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_feature_audit_summary(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting feature_audit_summary column is caught by canonical_output comparison."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET feature_audit_summary = json_set(feature_audit_summary, '$.row_count', 9999) "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_manifest_row_count(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting manifest_row_count column is caught by independent row count."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET manifest_row_count = 9999 "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_sample_count(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting sample_count column is caught by independent train-row count."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET sample_count = 9999 "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_distinct_season_count(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting distinct_season_count column is caught by independent season count."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET distinct_season_count = 9999 "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_corrupted_distinct_factory_count(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting distinct_factory_count column is caught by independent factory count."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET distinct_factory_count = 9999 "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


# ── Training: coordinated multi-field mutation tests ─────────────────────────


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_coordinated_metrics_and_counts(
    sqlite_session: AsyncSession,
) -> None:
    """Coordinated corruption of training_metrics AND sample_count is caught."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    # Corrupt both training_metrics AND sample_count in the same way
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET training_metrics = json_set(training_metrics, '$.row_count', 8888), "
            "    sample_count = 8888 "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    # At least one of the independently rebuilt values should mismatch
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_coordinated_config_and_manifest(
    sqlite_session: AsyncSession,
) -> None:
    """Coordinated corruption of config_snapshot AND manifest_snapshot is caught."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    # Corrupt both config_snapshot and manifest_snapshot (both stored JSON columns)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET config_snapshot = json('{\"corrupted\": true}'), "
            "    manifest_snapshot = json('{\"rows\": [], \"summary\": {}}') "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_coordinated_version_triple(
    sqlite_session: AsyncSession,
) -> None:
    """Coordinated corruption of python/numpy/sklearn versions is caught."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET python_version = 'p', "
            "    numpy_version = 'n', "
            "    sklearn_version = 's' "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_training_independent_derivation_rejects_coordinated_counts_triple(
    sqlite_session: AsyncSession,
) -> None:
    """Coordinated corruption of manifest_row_count, sample_count, and distinct counts is caught."""
    rows, result = _eligible_training()
    run = await save_residual_training_run(sqlite_session, result=result, manifest_rows=rows)
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_training_run "
            "SET manifest_row_count = 5555, "
            "    sample_count = 5555, "
            "    distinct_season_count = 5555, "
            "    distinct_factory_count = 5555 "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_training_run_by_id(sqlite_session, run_id=run.id)


# ── Prediction: single-field corruption tests ────────────────────────────────
# NOTE: feature_schema_version/hash independent derivation only works when
# a training run exists (structural_only has placeholder input_snapshot values).
# These tests use structural_only predictions + the always-independent
# expected_prediction_row_count field.


@pytest.mark.asyncio
async def test_prediction_independent_derivation_rejects_corrupted_expected_prediction_row_count(
    sqlite_session: AsyncSession,
) -> None:
    """Corrupting expected_prediction_row_count is caught by independent row count."""
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
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_prediction_run "
            "SET expected_prediction_row_count = 9999 "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(sqlite_session, run_id=run.id)


# ── Prediction: coordinated multi-field mutation tests ───────────────────────
# NOTE: schema-field-only coordinated tests use structural_only predictions
# where feature_schema_version/hash have no independent authority.  Only the
# row-count-based coordinated test is meaningful here.


@pytest.mark.asyncio
async def test_prediction_independent_derivation_rejects_coordinated_row_count_and_schema(
    sqlite_session: AsyncSession,
) -> None:
    """Coordinated corruption of expected_prediction_row_count AND feature_schema_version.
    Expected_prediction_row_count mismatch is caught by Section 8.1 independent row count check."""
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
    await sqlite_session.execute(
        text(
            "UPDATE residual_model_prediction_run "
            "SET expected_prediction_row_count = 7777, "
            "    feature_schema_version = 'v-corrupted' "
            "WHERE id = :run_id"
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()
    with pytest.raises(ResidualModelPersistenceIntegrityError):
        await load_residual_prediction_run_by_id(sqlite_session, run_id=run.id)
