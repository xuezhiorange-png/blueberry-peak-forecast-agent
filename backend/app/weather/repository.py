from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.planning import LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherDailyObservation,
    WeatherFeatureRun,
    WeatherImportRun,
    WeatherSourceLocation,
)
from backend.app.planning.json_types import canonical_json_value


def _now() -> datetime:
    return datetime.now(UTC)


async def get_location_reference(
    session: AsyncSession,
    *,
    location_reference_id: int,
) -> LocationReference | None:
    return await session.get(LocationReference, location_reference_id)


async def find_location_reference_for_plan(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    as_of_date: date,
) -> list[LocationReference]:
    statement = select(LocationReference).where(
        LocationReference.farm_id == farm_id,
        LocationReference.valid_from <= as_of_date,
        (LocationReference.valid_to.is_(None) | (LocationReference.valid_to >= as_of_date)),
    )
    if subfarm_id is None:
        statement = statement.where(LocationReference.subfarm_id.is_(None))
    else:
        statement = statement.where(LocationReference.subfarm_id == subfarm_id)
    statement = statement.order_by(LocationReference.id.asc())
    return list((await session.scalars(statement)).all())


async def list_visible_weather_source_locations(
    session: AsyncSession,
    *,
    as_of_date: date,
    provider_code: str | None = None,
) -> list[WeatherSourceLocation]:
    statement = select(WeatherSourceLocation).where(
        WeatherSourceLocation.valid_from <= as_of_date,
        (WeatherSourceLocation.valid_to.is_(None) | (WeatherSourceLocation.valid_to >= as_of_date)),
    )
    if provider_code is not None:
        statement = statement.where(WeatherSourceLocation.provider_code == provider_code)
    statement = statement.order_by(
        WeatherSourceLocation.provider_code.asc(),
        WeatherSourceLocation.external_location_id.asc(),
        WeatherSourceLocation.source_version.asc(),
        WeatherSourceLocation.id.asc(),
    )
    return list((await session.scalars(statement)).all())


async def get_weather_source_location(
    session: AsyncSession,
    *,
    weather_source_location_id: int,
) -> WeatherSourceLocation | None:
    return await session.get(WeatherSourceLocation, weather_source_location_id)


async def get_weather_source_location_by_business_key(
    session: AsyncSession,
    *,
    provider_code: str,
    external_location_id: str,
    source_version: str,
) -> WeatherSourceLocation | None:
    return cast(
        WeatherSourceLocation | None,
        await session.scalar(
            select(WeatherSourceLocation).where(
                WeatherSourceLocation.provider_code == provider_code,
                WeatherSourceLocation.external_location_id == external_location_id,
                WeatherSourceLocation.source_version == source_version,
            )
        ),
    )


async def get_weather_source_location_by_row_hash(
    session: AsyncSession,
    *,
    row_hash: str,
) -> WeatherSourceLocation | None:
    return cast(
        WeatherSourceLocation | None,
        await session.scalar(
            select(WeatherSourceLocation).where(WeatherSourceLocation.row_hash == row_hash)
        ),
    )


async def create_weather_source_location(
    session: AsyncSession,
    *,
    record: WeatherSourceLocation,
) -> WeatherSourceLocation:
    session.add(record)
    await session.flush()
    return record


async def get_weather_observation_by_row_hash(
    session: AsyncSession,
    *,
    row_hash: str,
) -> WeatherDailyObservation | None:
    return cast(
        WeatherDailyObservation | None,
        await session.scalar(
            select(WeatherDailyObservation).where(WeatherDailyObservation.row_hash == row_hash)
        ),
    )


async def create_weather_observation(
    session: AsyncSession,
    *,
    record: WeatherDailyObservation,
) -> WeatherDailyObservation:
    session.add(record)
    await session.flush()
    return record


async def list_visible_weather_observations(
    session: AsyncSession,
    *,
    weather_source_location_id: int,
    start_date: date,
    end_date: date,
    feature_date: date,
    as_of_date: date,
) -> list[WeatherDailyObservation]:
    statement = (
        select(WeatherDailyObservation)
        .where(
            WeatherDailyObservation.weather_source_location_id == weather_source_location_id,
            WeatherDailyObservation.observation_date >= start_date,
            WeatherDailyObservation.observation_date <= end_date,
            WeatherDailyObservation.observation_date <= feature_date,
            WeatherDailyObservation.available_at <= as_of_date,
        )
        .order_by(
            WeatherDailyObservation.observation_date.asc(),
            WeatherDailyObservation.available_at.desc(),
            WeatherDailyObservation.source_version.desc(),
            WeatherDailyObservation.id.desc(),
        )
    )
    return list((await session.scalars(statement)).all())


async def get_location_weather_mapping_by_row_hash(
    session: AsyncSession,
    *,
    row_hash: str,
) -> LocationWeatherMapping | None:
    return cast(
        LocationWeatherMapping | None,
        await session.scalar(
            select(LocationWeatherMapping).where(LocationWeatherMapping.row_hash == row_hash)
        ),
    )


async def list_effective_explicit_mappings(
    session: AsyncSession,
    *,
    location_reference_id: int,
    as_of_date: date,
) -> list[LocationWeatherMapping]:
    statement = (
        select(LocationWeatherMapping)
        .where(
            LocationWeatherMapping.location_reference_id == location_reference_id,
            LocationWeatherMapping.mapping_method == "explicit",
            LocationWeatherMapping.available_at <= as_of_date,
            LocationWeatherMapping.valid_from <= as_of_date,
            (
                LocationWeatherMapping.valid_to.is_(None)
                | (LocationWeatherMapping.valid_to >= as_of_date)
            ),
        )
        .order_by(
            LocationWeatherMapping.available_at.desc(),
            LocationWeatherMapping.id.desc(),
        )
    )
    return list((await session.scalars(statement)).all())


async def create_location_weather_mapping(
    session: AsyncSession,
    *,
    record: LocationWeatherMapping,
) -> LocationWeatherMapping:
    session.add(record)
    await session.flush()
    return record


async def create_weather_import_run(
    session: AsyncSession,
    *,
    import_type: str,
    provider_code: str | None,
    file_name: str,
    file_sha256: str,
    source_version: str | None,
    dry_run: bool,
    report_json: dict[str, Any],
) -> WeatherImportRun:
    run = WeatherImportRun(
        import_type=import_type,
        provider_code=provider_code,
        file_name=file_name,
        file_sha256=file_sha256,
        source_version=source_version,
        dry_run=dry_run,
        status="running",
        report_json=cast(dict[str, Any], canonical_json_value(report_json)),
    )
    session.add(run)
    await session.commit()
    return run


async def mark_weather_import_run_completed(
    session: AsyncSession,
    *,
    run_id: int,
    row_count: int,
    inserted_count: int,
    skipped_count: int,
    duplicate_count: int,
    rejected_count: int,
    invalid_date_count: int,
    invalid_numeric_count: int,
    unknown_location_count: int,
    conflict_count: int,
    report_json: dict[str, Any],
) -> None:
    await session.execute(
        update(WeatherImportRun)
        .where(WeatherImportRun.id == run_id)
        .values(
            status="completed",
            row_count=row_count,
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            duplicate_count=duplicate_count,
            rejected_count=rejected_count,
            invalid_date_count=invalid_date_count,
            invalid_numeric_count=invalid_numeric_count,
            unknown_location_count=unknown_location_count,
            conflict_count=conflict_count,
            report_json=cast(dict[str, Any], canonical_json_value(report_json)),
            finished_at=_now(),
            error_message=None,
        )
    )
    await session.commit()


async def mark_weather_import_run_failed(
    session: AsyncSession,
    *,
    run_id: int,
    report_json: dict[str, Any],
    error_message: str,
) -> None:
    await session.execute(
        update(WeatherImportRun)
        .where(WeatherImportRun.id == run_id)
        .values(
            status="failed",
            report_json=cast(dict[str, Any], canonical_json_value(report_json)),
            error_message=error_message,
            finished_at=_now(),
        )
    )
    await session.commit()


async def find_existing_base_temperature_search_run(
    session: AsyncSession,
    *,
    source_signature: str,
) -> BaseTemperatureSearchRun | None:
    return cast(
        BaseTemperatureSearchRun | None,
        await session.scalar(
            select(BaseTemperatureSearchRun)
            .where(
                BaseTemperatureSearchRun.source_signature == source_signature,
                BaseTemperatureSearchRun.status.in_(("running", "completed", "unavailable")),
            )
            .order_by(BaseTemperatureSearchRun.id.desc())
        ),
    )


async def create_base_temperature_search_run(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> BaseTemperatureSearchRun:
    run = BaseTemperatureSearchRun(**payload)
    session.add(run)
    await session.commit()
    return run


async def update_base_temperature_search_run(
    session: AsyncSession,
    *,
    run_id: int,
    values: dict[str, Any],
) -> None:
    normalized = dict(values)
    json_fields = (
        "candidate_temperatures",
        "training_sample_ids",
        "candidate_scores",
        "warnings",
        "blockers",
        "input_snapshot",
    )
    for field in json_fields:
        if field in normalized:
            normalized[field] = canonical_json_value(normalized[field])
    await session.execute(
        update(BaseTemperatureSearchRun)
        .where(BaseTemperatureSearchRun.id == run_id)
        .values(**normalized)
    )
    await session.commit()


async def get_base_temperature_search_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> BaseTemperatureSearchRun | None:
    return await session.get(BaseTemperatureSearchRun, run_id)


async def find_existing_weather_feature_run(
    session: AsyncSession,
    *,
    source_signature: str,
) -> WeatherFeatureRun | None:
    return cast(
        WeatherFeatureRun | None,
        await session.scalar(
            select(WeatherFeatureRun)
            .where(
                WeatherFeatureRun.source_signature == source_signature,
                WeatherFeatureRun.status.in_(("running", "completed", "unavailable")),
            )
            .order_by(WeatherFeatureRun.id.desc())
        ),
    )


async def create_weather_feature_run(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> WeatherFeatureRun:
    run = WeatherFeatureRun(**payload)
    session.add(run)
    await session.commit()
    return run


async def update_weather_feature_run(
    session: AsyncSession,
    *,
    run_id: int,
    values: dict[str, Any],
) -> None:
    normalized = dict(values)
    json_fields = (
        "input_snapshot",
        "window_features",
        "timeline_payload",
        "weather_observation_ids",
        "warnings",
        "blockers",
    )
    for field in json_fields:
        if field in normalized:
            normalized[field] = canonical_json_value(normalized[field])
    await session.execute(
        update(WeatherFeatureRun).where(WeatherFeatureRun.id == run_id).values(**normalized)
    )
    await session.commit()


async def get_weather_feature_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> WeatherFeatureRun | None:
    return await session.get(WeatherFeatureRun, run_id)


async def get_plan_by_id(
    session: AsyncSession,
    *,
    plan_id: int,
) -> FarmSeasonVarietyPlan | None:
    return await session.get(FarmSeasonVarietyPlan, plan_id)
