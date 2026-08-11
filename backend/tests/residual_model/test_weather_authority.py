from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.weather import WeatherFeatureRun
from backend.app.residual_model.schemas import FeatureValue
from backend.app.residual_model.weather_authority import (
    WeatherFeatureAuthorityError,
    bind_weather_feature_authority,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def weather_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    for column_name in (
        "input_snapshot",
        "window_features",
        "timeline_payload",
        "weather_observation_ids",
        "warnings",
        "blockers",
    ):
        WeatherFeatureRun.__table__.c[column_name].type = JSON()
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: WeatherFeatureRun.metadata.create_all(
                sync_connection,
                tables=[WeatherFeatureRun.__table__],
            )
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


def _feature(
    *,
    feature_name: str = "weather_7d_rainfall",
    run_id: int | None = 1,
    source_signature: str = "a" * 64,
    config_hash: str = "b" * 64,
    mapping_version: str = "weather-map-v1",
    weather_source_version: str = "weather-source-v1",
    feature_version: str = "task7-v1",
    observation_date: date | None = date(2026, 2, 28),
) -> FeatureValue:
    source_ref: dict[str, object] = {
        "weather_feature_run_id": run_id,
        "weather_source_signature": source_signature,
        "weather_config_hash": config_hash,
        "weather_mapping_version": mapping_version,
        "weather_source_version": weather_source_version,
    }
    return FeatureValue(
        feature_name=feature_name,
        value=Decimal("12.5"),
        known_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        source_ref=source_ref,
        source_version=feature_version,
        source_available_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        observation_date=observation_date,
    )


async def _seed_run(
    session: AsyncSession,
    *,
    run_id: int = 1,
    source_signature: str = "a" * 64,
    status: str = "completed",
    as_of_date: date = date(2026, 2, 28),
    feature_date: date = date(2026, 2, 28),
) -> None:
    session.add(
        WeatherFeatureRun(
            id=run_id,
            feature_version="task7-v1",
            config_hash="b" * 64,
            mapping_version="weather-map-v1",
            weather_source_version="weather-source-v1",
            plan_id=1,
            location_reference_id=1,
            location_weather_mapping_id=1,
            weather_source_location_id=1,
            as_of_date=as_of_date,
            feature_date=feature_date,
            source_signature=source_signature,
            status=status,
            input_snapshot={},
            window_features={},
            timeline_payload={},
            weather_observation_ids=[],
            warnings=[],
            blockers=[],
        )
    )
    await session.flush()


async def test_valid_weather_features_bind_to_persisted_run(weather_session: AsyncSession) -> None:
    await _seed_run(weather_session)

    bound = await bind_weather_feature_authority(
        weather_session,
        feature_values=(
            _feature(feature_name="weather_7d_rainfall"),
            _feature(feature_name="weather_7d_gdd"),
        ),
        as_of_date=date(2026, 2, 28),
    )

    assert len(bound) == 2
    assert bound[0].source_ref == {
        "weather_feature_run_id": 1,
        "weather_source_signature": "a" * 64,
        "weather_config_hash": "b" * 64,
        "weather_mapping_version": "weather-map-v1",
        "weather_source_version": "weather-source-v1",
    }
    assert bound[0].source_version == "task7-v1"
    assert bound[0].observation_date == date(2026, 2, 28)


@pytest.mark.parametrize(
    ("feature", "error_fragment"),
    [
        (_feature(run_id=None), "weather_feature_run_id is required"),
        (_feature(run_id=99), "was not found"),
        (_feature(observation_date=None), "observation_date is required"),
        (_feature(observation_date=date(2026, 2, 27)), "observation_date does not match"),
        (_feature(source_signature="c" * 64), "weather_source_signature"),
        (_feature(config_hash="c" * 64), "weather_config_hash"),
        (_feature(mapping_version="other-map"), "weather_mapping_version"),
        (_feature(weather_source_version="other-source"), "weather_source_version"),
        (_feature(feature_version="other-version"), "source_version"),
    ],
)
async def test_invalid_weather_authority_is_fail_closed(
    weather_session: AsyncSession,
    feature: FeatureValue,
    error_fragment: str,
) -> None:
    await _seed_run(weather_session)

    with pytest.raises(WeatherFeatureAuthorityError, match=error_fragment):
        await bind_weather_feature_authority(
            weather_session,
            feature_values=(feature,),
            as_of_date=date(2026, 2, 28),
        )


async def test_non_completed_and_future_weather_runs_are_blocked(
    weather_session: AsyncSession,
) -> None:
    await _seed_run(weather_session, status="running")
    with pytest.raises(WeatherFeatureAuthorityError, match="not completed"):
        await bind_weather_feature_authority(
            weather_session,
            feature_values=(_feature(),),
            as_of_date=date(2026, 2, 28),
        )

    await weather_session.rollback()
    await weather_session.execute(WeatherFeatureRun.__table__.delete())
    await _seed_run(weather_session, feature_date=date(2026, 3, 1))
    with pytest.raises(WeatherFeatureAuthorityError, match="after the Task 9 as_of date"):
        await bind_weather_feature_authority(
            weather_session,
            feature_values=(_feature(observation_date=date(2026, 3, 1)),),
            as_of_date=date(2026, 2, 28),
        )


async def test_weather_features_cannot_mix_persisted_runs(
    weather_session: AsyncSession,
) -> None:
    await _seed_run(weather_session)
    await _seed_run(weather_session, run_id=2, source_signature="c" * 64)

    with pytest.raises(WeatherFeatureAuthorityError, match="one persisted WeatherFeatureRun"):
        await bind_weather_feature_authority(
            weather_session,
            feature_values=(
                _feature(),
                _feature(
                    feature_name="weather_7d_gdd",
                    run_id=2,
                    source_signature="c" * 64,
                ),
            ),
            as_of_date=date(2026, 2, 28),
        )
