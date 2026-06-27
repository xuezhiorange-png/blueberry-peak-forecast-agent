from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.app.residual_model.application import (
    ResidualPredictionApplicationIntegrityError,
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
    _seed_season,
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
        max_validation_wmape=Decimal("10"),
        require_improvement_over_structural=False,
        max_fallback_rate=Decimal("1"),
    )
    rules = replace(config.rules, eligibility=eligibility)
    return replace(config, rules=rules)


async def test_execute_residual_prediction_persists_and_reloads(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
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
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("21")), (3, Decimal("23")), (7, Decimal("27"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
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
            validation_task9_run_id=task9_run_id,
            validation_label_build_run_id=validation_label_build.id,
            validation_feature_build_run_id=validation_feature_build.id,
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
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
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


@pytest.mark.parametrize(
    ("column_name", "value"),
    [
        ("python_version", "0.0.0"),
        ("numpy_version", "0.0.0"),
        ("sklearn_version", "0.0.0"),
    ],
)
async def test_execute_residual_prediction_falls_back_for_dependency_version_mismatch(
    sqlite_session: AsyncSession,
    column_name: str,
    value: str,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
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
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
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
    for offset, weight in ((1, Decimal("21")), (3, Decimal("23")), (7, Decimal("27"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()

    _training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            validation_task9_run_id=task9_run_id,
            validation_label_build_run_id=validation_label_build.id,
            validation_feature_build_run_id=validation_feature_build.id,
            as_of_date=as_of_date,
        ),
        config=_relaxed_config(),
    )
    await sqlite_session.execute(
        text(
            f"UPDATE residual_model_training_run SET {column_name} = :value "
            "WHERE id = :run_id"
        ),
        {"value": value, "run_id": training_run_id},
    )
    await sqlite_session.commit()

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
    assert prediction_result.fallback_reason == "artifact_validation_failed"


async def test_execute_residual_prediction_fails_when_artifact_identity_query_fails(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
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
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
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
    for offset, weight in ((1, Decimal("21")), (3, Decimal("23")), (7, Decimal("27"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()

    _training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            validation_task9_run_id=task9_run_id,
            validation_label_build_run_id=validation_label_build.id,
            validation_feature_build_run_id=validation_feature_build.id,
            as_of_date=as_of_date,
        ),
        config=_relaxed_config(),
    )

    async def _boom(*args, **kwargs):
        raise SQLAlchemyError("artifact identity query failed")

    monkeypatch.setattr("backend.app.residual_model.application.list_residual_artifacts", _boom)

    with pytest.raises(
        ResidualPredictionApplicationIntegrityError,
        match="Authoritative residual artifact identities could not be loaded",
    ):
        await execute_residual_prediction(
            sqlite_session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=task9_run_id,
                feature_analytics_build_run_id=feature_build.id,
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
        )

    assert (
        await sqlite_session.scalar(select(func.count()).select_from(ResidualModelPredictionRun))
        == 0
    )


async def test_execute_residual_prediction_uses_structural_only_for_unknown_category_row(
    sqlite_session: AsyncSession,
) -> None:
    from backend.app.residual_model.config import load_residual_model_config_from_snapshot

    config = _relaxed_config()
    config = load_residual_model_config_from_snapshot(
        {
            **config.snapshot,
            "eligibility": {
                **config.snapshot["eligibility"],
                "min_training_rows": 1,
                "min_seasons": 1,
                "min_factories": 1,
                "max_validation_wmape": 10.0,
                "require_improvement_over_structural": False,
                "max_fallback_rate": 1.0,
            },
            "categorical_encoding": {
                **config.snapshot["categorical_encoding"],
                "unknown_policy": "structural_only_fallback",
            },
        }
    )
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
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
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
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
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight + Decimal("10"),
        )
    await sqlite_session.commit()

    training_result, training_run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            validation_task9_run_id=task9_run_id,
            validation_label_build_run_id=validation_label_build.id,
            validation_feature_build_run_id=validation_feature_build.id,
            as_of_date=as_of_date,
        ),
        config=config,
    )
    assert training_result.eligibility_status == "eligible"

    prediction_result, _prediction_run_id = await execute_residual_prediction(
        sqlite_session,
        request=ResidualPredictionRequest(
            model_run_id=training_run_id,
            task9_run_id=task9_run_id,
            feature_analytics_build_run_id=feature_build.id,
            supplemental_feature_values=_supplemental_features(
                as_of_date=as_of_date,
                destination_factory_category="totally-unknown-category",
            ),
        ),
    )

    assert prediction_result.execution_status == "completed"
    assert prediction_result.mode == "structural_only"
    assert prediction_result.fallback_reason == "unknown_category"
    assert all(row.mode == "structural_only" for row in prediction_result.rows)
    assert all(row.raw_residual_p50_kg == Decimal("0") for row in prediction_result.rows)
