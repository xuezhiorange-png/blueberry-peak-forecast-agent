from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.planning.json_types import canonical_json_value


def _now() -> datetime:
    return datetime.now(UTC)


async def find_existing_maturity_model_run(
    session: AsyncSession,
    *,
    source_signature: str,
) -> MaturityModelRun | None:
    return cast(
        MaturityModelRun | None,
        await session.scalar(
            select(MaturityModelRun).where(
                MaturityModelRun.source_signature == source_signature,
                MaturityModelRun.status.in_(("running", "completed", "unavailable")),
            )
        ),
    )


async def create_maturity_model_run(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> MaturityModelRun:
    run = MaturityModelRun(
        model_version=cast(str, payload["model_version"]),
        config_hash=cast(str, payload["config_hash"]),
        config_snapshot=cast(dict[str, Any], canonical_json_value(payload["config_snapshot"])),
        training_cutoff=payload["training_cutoff"],
        source_signature=cast(str, payload["source_signature"]),
        status=cast(str, payload["status"]),
        random_seed=cast(int, payload["random_seed"]),
        model_family=cast(str, payload["model_family"]),
        scope=cast(str, payload["scope"]),
        sample_count=cast(int, payload["sample_count"]),
        distinct_season_count=cast(int, payload["distinct_season_count"]),
        distinct_farm_count=cast(int, payload["distinct_farm_count"]),
        distinct_subfarm_count=cast(int, payload["distinct_subfarm_count"]),
        training_metrics=cast(dict[str, Any], canonical_json_value(payload["training_metrics"])),
        calibration_metrics=cast(
            dict[str, Any],
            canonical_json_value(payload["calibration_metrics"]),
        ),
        warnings=cast(list[str], canonical_json_value(payload["warnings"])),
        blockers=cast(list[str], canonical_json_value(payload["blockers"])),
        input_snapshot=cast(dict[str, Any], canonical_json_value(payload["input_snapshot"])),
        finished_at=payload.get("finished_at"),
        error_message=cast(str | None, payload.get("error_message")),
    )
    session.add(run)
    await session.commit()
    return run


async def create_maturity_model_artifact(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> MaturityModelArtifact:
    artifact = MaturityModelArtifact(
        run_id=cast(int, payload["run_id"]),
        artifact_hash=cast(str, payload["artifact_hash"]),
        support_min_day=cast(int, payload["support_min_day"]),
        support_max_day=cast(int, payload["support_max_day"]),
        artifact_payload=cast(dict[str, Any], canonical_json_value(payload["artifact_payload"])),
    )
    session.add(artifact)
    await session.commit()
    return artifact


async def get_maturity_model_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> MaturityModelRun | None:
    return await session.get(MaturityModelRun, run_id)


async def get_maturity_model_artifact_by_run_id(
    session: AsyncSession,
    *,
    run_id: int,
) -> MaturityModelArtifact | None:
    return cast(
        MaturityModelArtifact | None,
        await session.scalar(
            select(MaturityModelArtifact).where(MaturityModelArtifact.run_id == run_id)
        ),
    )


async def update_maturity_model_run(
    session: AsyncSession,
    *,
    run_id: int,
    values: dict[str, Any],
) -> None:
    payload = dict(values)
    for key in (
        "training_metrics",
        "calibration_metrics",
        "warnings",
        "blockers",
        "input_snapshot",
    ):
        if key in payload:
            payload[key] = canonical_json_value(payload[key])
    await session.execute(
        update(MaturityModelRun).where(MaturityModelRun.id == run_id).values(**payload)
    )
    await session.commit()


async def find_existing_maturity_forecast_run(
    session: AsyncSession,
    *,
    source_signature: str,
) -> MaturityForecastRun | None:
    return cast(
        MaturityForecastRun | None,
        await session.scalar(
            select(MaturityForecastRun).where(
                MaturityForecastRun.source_signature == source_signature,
                MaturityForecastRun.status.in_(("running", "completed", "unavailable")),
            )
        ),
    )


async def create_maturity_forecast_run(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> MaturityForecastRun:
    run = MaturityForecastRun(
        model_run_id=cast(int, payload["model_run_id"]),
        artifact_id=cast(int, payload["artifact_id"]),
        plan_id=cast(int, payload["plan_id"]),
        location_reference_id=cast(int, payload["location_reference_id"]),
        weather_mapping_id=cast(int | None, payload.get("weather_mapping_id")),
        base_temperature_search_run_id=cast(
            int | None,
            payload.get("base_temperature_search_run_id"),
        ),
        as_of_date=payload["as_of_date"],
        prediction_start_date=payload["prediction_start_date"],
        prediction_end_date=payload["prediction_end_date"],
        expected_marketable_total_kg=payload["expected_marketable_total_kg"],
        expected_total_source=cast(str, payload["expected_total_source"]),
        axis_mode=cast(str, payload["axis_mode"]),
        source_signature=cast(str, payload["source_signature"]),
        status=cast(str, payload["status"]),
        warnings=cast(list[str], canonical_json_value(payload["warnings"])),
        blockers=cast(list[str], canonical_json_value(payload["blockers"])),
        input_snapshot=cast(dict[str, Any], canonical_json_value(payload["input_snapshot"])),
        finished_at=payload.get("finished_at"),
        error_message=cast(str | None, payload.get("error_message")),
    )
    session.add(run)
    await session.commit()
    return run


async def create_maturity_daily_predictions(
    session: AsyncSession,
    *,
    forecast_run_id: int,
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        session.add(
            MaturityDailyPredictionModel(
                forecast_run_id=forecast_run_id,
                prediction_date=row["prediction_date"],
                phenology_coordinate_day=row["phenology_coordinate_day"],
                p50_kg=row["p50_kg"],
                p80_kg=row["p80_kg"],
                p90_kg=row["p90_kg"],
                cumulative_p50_kg=row["cumulative_p50_kg"],
                cumulative_p80_kg=row["cumulative_p80_kg"],
                cumulative_p90_kg=row["cumulative_p90_kg"],
                curve_share=row["curve_share"],
                confidence_level=cast(str, row["confidence_level"]),
                quality_flags=cast(list[str], canonical_json_value(row["quality_flags"])),
            )
        )
    await session.commit()


async def get_maturity_forecast_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> MaturityForecastRun | None:
    return await session.get(MaturityForecastRun, run_id)


async def list_maturity_daily_predictions(
    session: AsyncSession,
    *,
    forecast_run_id: int,
) -> list[MaturityDailyPredictionModel]:
    statement = (
        select(MaturityDailyPredictionModel)
        .where(MaturityDailyPredictionModel.forecast_run_id == forecast_run_id)
        .order_by(MaturityDailyPredictionModel.prediction_date.asc())
    )
    return list((await session.scalars(statement)).all())


async def update_maturity_forecast_run(
    session: AsyncSession,
    *,
    run_id: int,
    values: dict[str, Any],
) -> None:
    payload = dict(values)
    for key in ("warnings", "blockers", "input_snapshot"):
        if key in payload:
            payload[key] = canonical_json_value(payload[key])
    await session.execute(
        update(MaturityForecastRun).where(MaturityForecastRun.id == run_id).values(**payload)
    )
    await session.commit()
