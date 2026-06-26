from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.residual_model.application import (
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionRequest,
    ResidualTrainingSampleSpec,
)
from backend.tests.residual_model.test_training_manifest import (
    _config,
    _diverse_training_samples,
    _persist_task9_run,
    _seed_build_run,
    _seed_daily_fact,
    _seed_master_data,
    _snapshot_as_of_date,
    _supplemental_features,
)

pytestmark = pytest.mark.asyncio
pytest_plugins = ("backend.tests.residual_model.test_training_manifest",)


def _relaxed_config():
    config = _config()
    eligibility = replace(
        config.rules.eligibility,
        min_training_rows=1,
        min_seasons=1,
        min_factories=1,
    )
    rules = replace(config.rules, eligibility=eligibility)
    return replace(config, rules=rules)


async def test_execute_residual_prediction_persists_and_reloads(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=100 + index,
            build_run_id=label_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("100") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("11")), (3, Decimal("13")), (7, Decimal("17"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=200 + offset,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()

    training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            as_of_date=as_of_date,
        ),
        config=_relaxed_config(),
    )
    assert training_result.eligibility_status == "eligible"

    prediction_result, prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build.id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
    )

    assert prediction_run_id > 0
    assert prediction_result.execution_status == "completed"
    assert prediction_result.mode == "residual_corrected"
    assert prediction_result.task9_run_id == task9_run_id
    assert prediction_result.rows
    assert any(
        row.corrected_raw_p50_kg != row.structural_p50_kg for row in prediction_result.rows
    )


async def test_execute_residual_prediction_falls_back_for_ineligible_model(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=1,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=output.forecast_start_date,
        weight_kg=Decimal("100"),
    )
    for offset, fact_id in ((1, 2), (3, 3), (7, 4)):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=fact_id,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=Decimal("10") + Decimal(offset),
        )
    await sqlite_session.commit()

    training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=[
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.id,
                feature_analytics_build_run_id=feature_build.id,
                split="train",
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            )
        ],
        config=_config(),
    )
    assert training_result.eligibility_status == "ineligible"

    prediction_result, _prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build.id,
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        ),
    )

    assert prediction_result.execution_status == "completed"
    assert prediction_result.mode == "structural_only"
    assert prediction_result.fallback_reason == "model_not_eligible"
    assert all(row.raw_residual_p50_kg == Decimal("0") for row in prediction_result.rows)
