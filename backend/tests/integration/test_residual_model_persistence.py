from __future__ import annotations

import copy
import os
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.canonical import make_stable_cohort_key
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.master_data import Season
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelExecutionAttempt,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.application import (
    ResidualPredictionApplicationIntegrityError,
    ResidualTrainingApplicationIntegrityError,
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.persistence import (
    load_residual_prediction_run_by_id,
    load_residual_training_run_by_id,
    training_result_json_payload,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionRequest,
    ResidualTrainingSampleSpec,
)
from backend.tests.harvest_state.conftest import make_request
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

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


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


def _apply_task8_authority_to_payload(
    payload: dict[str, Any],
    authority: dict[str, Any],
    *,
    include_availability: bool = True,
) -> None:
    """Override Task 8 authority fields with one exact persisted variety chain.

    The orchestration fixture re-anchors the task8 dict's date fields
    (forecast_as_of_date / prediction_start_date / prediction_end_date)
    to the future season (e.g. 2099-02-28 / 2099-03-01..03) before
    passing the task8_authority into this helper. The request payload
    created by ``make_request(season_id=2099)`` already carries the
    same season-anchored dates, but as an additional safety net we
    also force the payload's top-level scalar date fields to follow
    the task8_authority dates so production-side validation (e.g.
    `verification.maturity_forecast_as_of_date > request.as_of_date`)
    can never see a season mismatch even if ``make_request()`` was
    invoked with the wrong ``season_id``.
    """
    payload["as_of_date"] = authority["forecast_as_of_date"]
    payload["forecast_start_date"] = authority["prediction_start_date"]
    payload["forecast_end_date"] = authority["prediction_end_date"]
    pool = copy.deepcopy(payload["capacity_pools"][0])
    pool["members"] = [
        {
            "farm_id": authority["farm_id"],
            "subfarm_id": authority["subfarm_id"],
            "variety_id": authority["variety_id"],
        }
    ]
    payload["capacity_pools"] = [pool]
    capacity_pool_membership_hash = make_stable_cohort_key(
        {
            "capacity_pool_grain": pool["capacity_pool_grain"],
            "members": sorted(
                pool["members"],
                key=lambda item: (item["farm_id"], item["subfarm_id"], item["variety_id"]),
            ),
        }
    )

    filtered_predictions = [
        copy.deepcopy(item)
        for item in payload["task8_daily_predictions"]
        if item.get("variety_id") == authority["variety_id"]
    ]
    assert len(filtered_predictions) == 9

    for item in filtered_predictions:
        src = item["source_ref"]
        vs = item["verification_snapshot"]
        prediction_date = item["prediction_date"]
        forecast_quantile = src["forecast_quantile"]
        daily_row = authority["daily_predictions_by_date"][prediction_date]
        quantity_by_quantile = {
            "P50": daily_row["p50_kg"],
            "P80": daily_row["p80_kg"],
            "P90": daily_row["p90_kg"],
        }
        source_quantity_kg = quantity_by_quantile[forecast_quantile]

        item["farm_id"] = authority["farm_id"]
        item["subfarm_id"] = authority["subfarm_id"]
        item["variety_id"] = authority["variety_id"]

        src["maturity_model_run_id"] = authority["model_run_id"]
        src["maturity_model_version"] = authority["model_version"]
        src["maturity_model_config_hash"] = authority["model_config_hash"]
        src["maturity_model_source_signature"] = authority["model_source_signature"]
        src["maturity_model_artifact_id"] = authority["artifact_id"]
        src["maturity_model_artifact_hash"] = authority["artifact_hash"]
        src["maturity_forecast_run_id"] = authority["forecast_run_id"]
        src["maturity_forecast_source_signature"] = authority["forecast_source_signature"]
        src["maturity_forecast_as_of_date"] = authority["forecast_as_of_date"]
        if include_availability:
            src["maturity_daily_prediction_available_at"] = daily_row["created_at"]
        src["maturity_daily_prediction_id"] = daily_row["id"]
        src["prediction_date"] = prediction_date
        src["source_quantity_kg"] = source_quantity_kg
        src["plan_id"] = authority["plan_id"]
        src["location_reference_id"] = authority["location_reference_id"]
        src["weather_mapping_id"] = authority["weather_mapping_id"]
        src["base_temperature_search_run_id"] = authority["base_temperature_search_run_id"]

        vs["maturity_model_run_id"] = authority["model_run_id"]
        vs["maturity_model_version"] = authority["model_version"]
        vs["maturity_model_config_hash"] = authority["model_config_hash"]
        vs["maturity_model_source_signature"] = authority["model_source_signature"]
        vs["maturity_model_artifact_id"] = authority["artifact_id"]
        vs["maturity_model_artifact_run_id"] = authority["artifact_run_id"]
        vs["maturity_model_artifact_hash"] = authority["artifact_hash"]
        vs["maturity_forecast_run_id"] = authority["forecast_run_id"]
        vs["maturity_forecast_run_status"] = authority["forecast_run_status"]
        vs["maturity_forecast_model_run_id"] = authority["model_run_id"]
        vs["maturity_forecast_artifact_id"] = authority["artifact_id"]
        vs["maturity_forecast_source_signature"] = authority["forecast_source_signature"]
        vs["maturity_forecast_as_of_date"] = authority["forecast_as_of_date"]
        if include_availability:
            vs["maturity_daily_prediction_available_at"] = daily_row["created_at"]
        vs["maturity_forecast_prediction_start_date"] = authority["prediction_start_date"]
        vs["maturity_forecast_prediction_end_date"] = authority["prediction_end_date"]
        vs["maturity_daily_prediction_id"] = daily_row["id"]
        vs["maturity_daily_prediction_forecast_run_id"] = authority["forecast_run_id"]
        vs["prediction_date"] = prediction_date
        vs["farm_id"] = authority["farm_id"]
        vs["subfarm_id"] = authority["subfarm_id"]
        vs["variety_id"] = authority["variety_id"]
        vs["plan_id"] = authority["plan_id"]
        vs["location_reference_id"] = authority["location_reference_id"]
        vs["p50_kg"] = daily_row["p50_kg"]
        vs["p80_kg"] = daily_row["p80_kg"]
        vs["p90_kg"] = daily_row["p90_kg"]

    payload["task8_daily_predictions"] = filtered_predictions

    filtered_cohorts = [
        copy.deepcopy(item)
        for item in payload["initial_inventory_cohorts"]
        if item["variety_id"] == authority["variety_id"]
    ]
    assert len(filtered_cohorts) == 3
    for cohort in filtered_cohorts:
        cohort["farm_id"] = authority["farm_id"]
        cohort["subfarm_id"] = authority["subfarm_id"]
        cohort["variety_id"] = authority["variety_id"]
        cohort["stable_cohort_key"] = make_stable_cohort_key(
            {
                "schema_version": cohort["stable_cohort_key_schema_version"],
                "source_ref_type": cohort["source_ref"]["source_ref_type"],
                "source_system": cohort["source_ref"]["source_system"],
                "source_record_key": cohort["source_ref"]["source_record_key"],
                "source_version": cohort["source_ref"]["source_version"],
                "source_row_hash": cohort["source_ref"]["source_row_hash"],
                "cohort_date": cohort["cohort_date"].isoformat(),
                "forecast_quantile": cohort["forecast_quantile"],
                "farm_id": cohort["farm_id"],
                "subfarm_id": cohort["subfarm_id"],
                "variety_id": cohort["variety_id"],
                "capacity_pool_id": pool["capacity_pool_id"],
                "capacity_pool_membership_hash": capacity_pool_membership_hash,
                "destination_factory_id": payload["destination_factory_id"],
            }
        )
    payload["initial_inventory_cohorts"] = filtered_cohorts
    payload["initial_opening_mature_inventory_kg"] = sum(
        Decimal(str(item["remaining_quantity_kg"])) for item in filtered_cohorts
    )


async def _seed_prediction_fixture(
    *,
    task8_authority: dict[str, Any] | None = None,
    analytics_season_id: int | None = None,
) -> dict[str, int]:
    async with AsyncSessionMaker() as session:
        season_id, factory_id, variety_id = await _seed_master_data(session)
        resolved_analytics_season_id = (
            analytics_season_id if analytics_season_id is not None else season_id
        )
        # Ensure the analytics build's season row exists (FK target for
        # analytics_build_run.season_id). _seed_master_data only creates
        # season_id=1; callers may want analytics builds for a different
        # season (e.g. when the orchestration node uses a future year).
        if resolved_analytics_season_id != season_id:
            existing_analytics_season = await session.get(Season, resolved_analytics_season_id)
            if existing_analytics_season is None:
                session.add(
                    Season(
                        id=resolved_analytics_season_id,
                        code=f"analytics-season-{resolved_analytics_season_id}",
                        start_date=date(resolved_analytics_season_id, 1, 1),
                        end_date=date(resolved_analytics_season_id, 12, 31),
                    )
                )
                await session.flush()
        # The validation season (id=2) is used as the FK target for
        # validation_label_build / validation_feature_build runs. Pin
        # its date range to the same anchor season as the request
        # payload so receipt dates land inside the coverage window.
        # The default anchor (when no `analytics_season_id` override
        # is supplied) is year 2026 — this matches the legacy fixture
        # `Season(id=1)` created by `_seed_master_data`.
        validation_anchor_season_id = (
            analytics_season_id if analytics_season_id is not None else 2026
        )
        validation_season_id = await _seed_season(
            session,
            season_id=2,
            code="2026-2027",
            start_date=date(validation_anchor_season_id, 1, 1),
            end_date=date(validation_anchor_season_id, 3, 31),
        )
        # Default the request payload to the legacy 2026 fixture when
        # the caller did not override `analytics_season_id` to a different
        # future year. `_seed_master_data` creates a `Season(id=1)` whose
        # `start_date=date(2026, 1, 1)` and `end_date=date(2026, 12, 31)`,
        # so anchoring the request payload to year 2026 keeps the
        # structural rows inside the analytics season's coverage window.
        request_anchor_season_id = analytics_season_id if analytics_season_id is not None else 2026
        if task8_authority is not None:
            base_payload = copy.deepcopy(make_request(season_id=request_anchor_season_id))
            _apply_task8_authority_to_payload(base_payload, task8_authority)
            task9_run_id, output = await _persist_task9_run(session, payload=base_payload)
        else:
            task9_run_id, output = await _persist_task9_run(
                session, payload=make_request(season_id=request_anchor_season_id)
            )
        if task8_authority is not None:
            validation_payload = copy.deepcopy(make_request(season_id=request_anchor_season_id))
            _apply_task8_authority_to_payload(validation_payload, task8_authority)
        else:
            validation_payload = make_request(season_id=request_anchor_season_id)
        validation_payload["initial_inventory_cohorts"][0]["remaining_quantity_kg"] = Decimal("6")
        validation_payload["initial_opening_mature_inventory_kg"] = sum(
            Decimal(str(item["remaining_quantity_kg"]))
            for item in validation_payload["initial_inventory_cohorts"]
        )
        validation_task9_run_id, _validation_output = await _persist_task9_run(
            session,
            payload=validation_payload,
        )
        as_of_date = _snapshot_as_of_date(output)
        # The default anchor for analytics build coverage is 2026 (the
        # legacy `Season(id=1)` created by `_seed_master_data`). When
        # the caller overrides `analytics_season_id` to a different
        # year (e.g. 2099 for the orchestration fixture), anchor the
        # build's coverage and the receipt dates to that year so they
        # stay inside the analytics season's coverage window.
        coverage_anchor_season_id = analytics_season_id if analytics_season_id is not None else 2026
        label_build = await _seed_build_run(
            session,
            build_run_id=1,
            season_id=resolved_analytics_season_id,
            source_max_raw_id=100,
            config_hash="a" * 64,
            finished_at=datetime(coverage_anchor_season_id, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
            analysis_start_date=date(coverage_anchor_season_id, 1, 1),
            analysis_end_date=date(coverage_anchor_season_id, 3, 20),
        )
        feature_build = await _seed_build_run(
            session,
            build_run_id=2,
            season_id=resolved_analytics_season_id,
            source_max_raw_id=50,
            config_hash="b" * 64,
            finished_at=datetime(coverage_anchor_season_id, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
            analysis_start_date=date(coverage_anchor_season_id, 1, 1),
            analysis_end_date=date(coverage_anchor_season_id, 2, 27),
        )
        # Use a receipt date in the analytics season's date range so the
        # manifest builder's `date_outside_build_season` exclusion does
        # not drop the row. The default season (id=1) created by
        # _seed_master_data has start_date=2026-01-01 — receipt dates
        # in March 2026 fall inside. When the caller overrides the
        # analytics season to a different year (e.g. 2099 for the
        # orchestration fixture), anchor the dates to that year instead
        # so the analytics build's season matches its facts' dates.
        if resolved_analytics_season_id == season_id:
            season_anchor = date(2026, 3, 1)
        else:
            season_anchor = date(resolved_analytics_season_id, 3, 1)
        analytics_receipt_dates = (
            season_anchor,
            season_anchor + timedelta(days=1),
            season_anchor + timedelta(days=2),
        )
        for index, target_date in enumerate(analytics_receipt_dates):
            await _seed_daily_fact(
                session,
                fact_id=100 + index,
                build_run_id=label_build.id,
                season_id=resolved_analytics_season_id,
                factory_id=factory_id,
                variety_id=variety_id,
                receipt_date=target_date,
                weight_kg=Decimal("100") + Decimal(index),
            )
        # Feature build: seed facts near the season anchor within the
        # analytics season range (offset back a few days for the feature
        # window).
        for offset, weight in ((1, Decimal("11")), (3, Decimal("13")), (7, Decimal("17"))):
            await _seed_daily_fact(
                session,
                fact_id=200 + offset,
                build_run_id=feature_build.id,
                season_id=resolved_analytics_season_id,
                factory_id=factory_id,
                variety_id=variety_id,
                receipt_date=season_anchor - timedelta(days=offset),
                weight_kg=weight,
            )
        validation_label_build = await _seed_build_run(
            session,
            build_run_id=101,
            season_id=validation_season_id,
            source_max_raw_id=200,
            config_hash="c" * 64,
            finished_at=datetime(validation_anchor_season_id, 3, 20, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        validation_feature_build = await _seed_build_run(
            session,
            build_run_id=102,
            season_id=validation_season_id,
            source_max_raw_id=150,
            config_hash="d" * 64,
            finished_at=datetime(validation_anchor_season_id, 2, 28, 12, 0, tzinfo=UTC),
            covered_factory_ids=(factory_id,),
        )
        for index, target_date in enumerate(
            (
                date(resolved_analytics_season_id, 3, 1),
                date(resolved_analytics_season_id, 3, 2),
                date(resolved_analytics_season_id, 3, 3),
            )
        ):
            await _seed_daily_fact(
                session,
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
                session,
                fact_id=400 + offset,
                build_run_id=validation_feature_build.id,
                season_id=validation_season_id,
                factory_id=factory_id,
                variety_id=variety_id,
                receipt_date=as_of_date - timedelta(days=offset),
                weight_kg=weight,
            )
        await session.commit()
        # The downstream task10 prediction_run row binds to
        # `train_task9_run_id`, and the rolling-backtest stage-6
        # `_resolve_task10_reuse` audit enforces
        # `prediction.task9_run_id == ctx.task9_authority.reference_value`.
        # Under the historical resolver the candidate with the
        # highest `created_at` wins, so re-stamp train to be strictly
        # newer than validation here. Without this re-stamp a single
        # fixture call would still leave train (the first persisted
        # task9) at a lower created_at than validation, and historical
        # tests that depend on the train reference would fail with
        # TASK10_TASK9_BINDING_MISMATCH. The conftest.py autouse
        # truncate resets this state between tests.
        train_row = await session.get(HarvestStateRun, task9_run_id)
        validation_row = await session.get(HarvestStateRun, validation_task9_run_id)
        if (
            train_row is not None
            and validation_row is not None
            and train_row.created_at is not None
            and (
                validation_row.created_at is None
                or validation_row.created_at >= train_row.created_at
            )
        ):
            train_row.created_at = (
                validation_row.created_at + timedelta(microseconds=1)
                if validation_row.created_at is not None
                else train_row.created_at
            )
            await session.commit()
        return {
            "train_task9_run_id": task9_run_id,
            "validation_task9_run_id": validation_task9_run_id,
            "train_label_build_run_id": label_build.id,
            "train_feature_build_run_id": feature_build.id,
            "validation_label_build_run_id": validation_label_build.id,
            "validation_feature_build_run_id": validation_feature_build.id,
            "season_id": season_id,
            "validation_season_id": validation_season_id,
            "factory_id": factory_id,
        }


async def _set_model_authority_visible(
    session: AsyncSession,
    *,
    training_run_id: int,
) -> None:
    """Make a synthetic trained model historically visible for prediction tests."""

    authority_at = datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    await session.execute(
        update(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.id == training_run_id)
        .values(finished_at=authority_at)
    )
    await session.execute(
        update(ResidualModelArtifact)
        .where(ResidualModelArtifact.training_run_id == training_run_id)
        .values(created_at=authority_at)
    )
    await session.commit()


@pytest.mark.integration
async def test_residual_model_tables_exist_after_migration_upgrade() -> None:
    _require_postgres()
    async with AsyncSessionMaker() as session:
        for table_name in (
            "residual_model_training_run",
            "residual_model_manifest_row",
            "residual_model_artifact",
            "residual_model_prediction_run",
            "residual_model_prediction_row",
            "residual_model_execution_attempt",
        ):
            exists = await session.scalar(select(func.to_regclass(table_name)))
            assert exists == table_name


@pytest.mark.integration
async def test_postgres_execute_residual_training_completed_eligible_round_trip() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )
        loaded = await load_residual_training_run_by_id(session, run_id=training_run_id)

        assert training_result.blockers == ()
        assert training_result.input_snapshot["manifest_summary"]["included_row_count"] > 0
        assert training_result.execution_status == "completed"
        assert training_result.eligibility_status == "eligible"
        assert loaded is not None
        assert training_result_json_payload(loaded) == training_result_json_payload(training_result)
        assert {item.quantile_label: item.artifact_bytes for item in loaded.artifacts} == {
            item.quantile_label: item.artifact_bytes for item in training_result.artifacts
        }
        assert await session.scalar(select(func.count()).select_from(ResidualModelTrainingRun)) == 1
        expected_manifest_row_count = int(
            training_result.input_snapshot["manifest_summary"]["row_count"]
        )
        assert (
            await session.scalar(select(func.count()).select_from(ResidualModelManifestRow))
            == expected_manifest_row_count
        )
        assert training_result.input_snapshot["manifest_summary"]["included_row_count"] > 0
        assert await session.scalar(select(func.count()).select_from(ResidualModelArtifact)) == 3


@pytest.mark.integration
async def test_postgres_execute_residual_training_same_signature_is_idempotent() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()
    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        first_result, first_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )
        second_result, second_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )

        assert first_run_id == second_run_id
        assert first_result.training_signature == second_result.training_signature
        assert await session.scalar(select(func.count()).select_from(ResidualModelTrainingRun)) == 1
        expected_manifest_row_count = int(
            first_result.input_snapshot["manifest_summary"]["row_count"]
        )
        assert (
            await session.scalar(select(func.count()).select_from(ResidualModelManifestRow))
            == expected_manifest_row_count
        )
        assert first_result.input_snapshot["manifest_summary"]["included_row_count"] > 0
        assert await session.scalar(select(func.count()).select_from(ResidualModelArtifact)) == 3


@pytest.mark.integration
async def test_postgres_execute_residual_prediction_round_trip() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()
    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )
        assert training_result.eligibility_status == "eligible"
        await _set_model_authority_visible(session, training_run_id=training_run_id)

        prediction_result, prediction_run_id = await execute_residual_prediction(
            session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=fixture["train_task9_run_id"],
                feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
            ),
        )
        loaded = await load_residual_prediction_run_by_id(session, run_id=prediction_run_id)

        assert prediction_result.execution_status == "completed"
        assert prediction_result.mode == "residual_corrected"
        assert loaded is not None
        assert loaded.model_dump(mode="json") == prediction_result.model_dump(mode="json")
        assert (
            await session.scalar(select(func.count()).select_from(ResidualModelPredictionRun)) == 1
        )
        assert await session.scalar(
            select(func.count()).select_from(ResidualModelPredictionRow)
        ) == len(prediction_result.rows)


@pytest.mark.integration
async def test_postgres_execute_residual_prediction_structural_only_for_ineligible_model() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=fixture["train_task9_run_id"],
                    label_analytics_build_run_id=fixture["train_label_build_run_id"],
                    feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                )
            ],
            config=_config(),
        )
        assert training_result.eligibility_status == "ineligible"
        await _set_model_authority_visible(session, training_run_id=training_run_id)

        prediction_result, _prediction_run_id = await execute_residual_prediction(
            session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=fixture["train_task9_run_id"],
                feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
            ),
        )

        assert prediction_result.execution_status == "completed"
        assert prediction_result.mode == "structural_only"
        assert prediction_result.fallback_reason == "model_not_eligible"


@pytest.mark.integration
async def test_postgres_artifact_hash_corruption_forces_structural_only_fallback() -> None:
    _require_postgres()
    fixture = await _seed_prediction_fixture()
    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        _training_result, training_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_config(),
        )
        await _set_model_authority_visible(session, training_run_id=training_run_id)
        await session.execute(
            text(
                """
                UPDATE residual_model_artifact
                SET artifact_sha256 = :artifact_sha256
                WHERE training_run_id = :training_run_id
                  AND quantile_label = 'P50'
                """
            ),
            {
                "artifact_sha256": "f" * 64,
                "training_run_id": training_run_id,
            },
        )
        await session.commit()

        prediction_result, _prediction_run_id = await execute_residual_prediction(
            session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=fixture["train_task9_run_id"],
                feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
            ),
        )

        assert prediction_result.execution_status == "completed"
        assert prediction_result.mode == "structural_only"
        assert prediction_result.fallback_reason == "artifact_validation_failed"


# ── Section 6: Failed-attempt persistence tests ──────────────────────────────


@pytest.mark.integration
async def test_postgres_training_manifest_build_failure_persists_failed_attempt() -> None:
    """Manifest build failure persists a failed attempt record."""
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    # Use non-existent task9_run_id to trigger manifest build failure
    samples = [
        ResidualTrainingSampleSpec(
            task9_run_id=999999,
            label_analytics_build_run_id=fixture["train_label_build_run_id"],
            feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
            split="train",
            supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
        )
    ]

    with pytest.raises(ResidualTrainingApplicationIntegrityError):
        async with AsyncSessionMaker() as session:
            await execute_residual_training(
                session,
                samples=samples,
                config=_relaxed_config(),
            )

    # Verify attempt record was persisted as failed
    async with AsyncSessionMaker() as session:
        attempts = (
            await session.scalars(
                select(ResidualModelExecutionAttempt)
                .order_by(ResidualModelExecutionAttempt.id.desc())
                .limit(1)
            )
        ).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.attempt_type == "training"
        assert attempt.execution_status == "failed"
        assert attempt.current_stage == "manifest_build"
        assert attempt.sanitized_error is not None
        assert len(attempt.sanitized_error) > 0
        assert attempt.finished_at is not None
        assert attempt.linked_training_run_id is None
        assert attempt.linked_prediction_run_id is None


@pytest.mark.integration
async def test_postgres_prediction_training_load_failure_persists_failed_attempt() -> None:
    """Non-existent training run triggers a failed attempt record."""
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    with pytest.raises(ResidualTrainingApplicationIntegrityError):
        async with AsyncSessionMaker() as session:
            await execute_residual_prediction(
                session,
                request=ResidualPredictionRequest(
                    model_run_id=999999,
                    task9_run_id=fixture["train_task9_run_id"],
                    feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                ),
            )

    # Verify attempt record was persisted as failed
    async with AsyncSessionMaker() as session:
        attempts = (
            await session.scalars(
                select(ResidualModelExecutionAttempt)
                .order_by(ResidualModelExecutionAttempt.id.desc())
                .limit(1)
            )
        ).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.attempt_type == "prediction"
        assert attempt.execution_status == "failed"
        assert attempt.linked_training_run_id is None
        assert attempt.linked_prediction_run_id is None


@pytest.mark.integration
async def test_postgres_prediction_feature_build_failure_persists_failed_attempt() -> None:
    """Non-existent feature build triggers a failed attempt record."""
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    async with AsyncSessionMaker() as session:
        _training_result, train_model_run_id = await execute_residual_training(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=fixture["train_task9_run_id"],
                    label_analytics_build_run_id=fixture["train_label_build_run_id"],
                    feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                )
            ],
            config=_relaxed_config(),
        )

    with pytest.raises(ResidualPredictionApplicationIntegrityError):
        async with AsyncSessionMaker() as session:
            await execute_residual_prediction(
                session,
                request=ResidualPredictionRequest(
                    model_run_id=train_model_run_id,
                    task9_run_id=fixture["train_task9_run_id"],
                    feature_analytics_build_run_id=999999,
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                ),
            )

    # Verify attempt record was persisted as failed
    async with AsyncSessionMaker() as session:
        attempts = (
            await session.scalars(
                select(ResidualModelExecutionAttempt)
                .order_by(ResidualModelExecutionAttempt.id.desc())
                .limit(1)
            )
        ).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.attempt_type == "prediction"
        assert attempt.execution_status == "failed"
        assert attempt.linked_training_run_id is None
        assert attempt.linked_prediction_run_id is None


@pytest.mark.integration
async def test_postgres_successful_training_run_attempt_finalized_as_completed() -> None:
    """Successful training run finalizes as completed and linked."""
    _require_postgres()
    fixture = await _seed_prediction_fixture()

    # Perform successful training
    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=fixture["train_task9_run_id"],
                    label_analytics_build_run_id=fixture["train_label_build_run_id"],
                    feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=date(2026, 2, 28)
                    ),
                )
            ],
            config=_relaxed_config(),
        )

        assert training_result.execution_status == "completed"
        assert training_run_id > 0

        # Verify attempt record was persisted as completed
        attempts = (
            await session.scalars(
                select(ResidualModelExecutionAttempt)
                .where(ResidualModelExecutionAttempt.attempt_type == "training")
                .order_by(ResidualModelExecutionAttempt.id.desc())
                .limit(1)
            )
        ).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt.execution_status == "completed"
        assert attempt.current_stage == "completed"
        assert attempt.linked_training_run_id == training_run_id
        assert attempt.finished_at is not None
