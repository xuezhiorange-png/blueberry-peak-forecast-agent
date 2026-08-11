from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.weather import WeatherFeatureRun
from backend.app.residual_model.schemas import FeatureValue

WEATHER_FEATURE_NAMES = frozenset({"weather_7d_rainfall", "weather_7d_gdd"})
_LOWERCASE_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class WeatherFeatureAuthorityError(ValueError):
    """Raised when a Weather supplemental feature lacks persisted authority."""


def _error(feature_name: str, detail: str) -> WeatherFeatureAuthorityError:
    return WeatherFeatureAuthorityError(f"{feature_name}: {detail}")


def _required_run_id(feature: FeatureValue) -> int:
    source_ref = feature.source_ref
    raw_run_id = source_ref.get("weather_feature_run_id")
    if type(raw_run_id) is not int or raw_run_id < 1:
        raise _error(
            feature.feature_name,
            "weather_feature_run_id is required and must be a positive integer",
        )
    return raw_run_id


def _require_matching_ref(
    feature: FeatureValue,
    *,
    key: str,
    expected: str,
) -> None:
    actual = feature.source_ref.get(key)
    if actual != expected:
        raise _error(
            feature.feature_name,
            f"{key} does not match the persisted WeatherFeatureRun",
        )


async def bind_weather_feature_authority(
    session: AsyncSession,
    *,
    feature_values: Sequence[FeatureValue],
    as_of_date: date,
) -> tuple[FeatureValue, ...]:
    """Bind Weather feature provenance to one persisted completed feature run.

    The caller still supplies the feature value and its exact visibility
    timestamps.  The persisted ``WeatherFeatureRun`` is the authority for
    the run identity and all Weather provenance fields.  ``finished_at`` is
    intentionally not used as a historical feature availability timestamp;
    the existing ``FeatureValue`` visibility audit remains responsible for
    ``known_at`` and ``source_available_at`` versus the exact forecast cutoff.
    """

    weather_values = [
        feature for feature in feature_values if feature.feature_name in WEATHER_FEATURE_NAMES
    ]
    if not weather_values:
        return tuple(feature_values)

    run_ids = [_required_run_id(feature) for feature in weather_values]
    if len(set(run_ids)) != 1:
        raise WeatherFeatureAuthorityError(
            "Weather supplemental features must bind to one persisted WeatherFeatureRun"
        )

    persisted_runs = {
        run.id: run
        for run in await session.scalars(
            select(WeatherFeatureRun).where(WeatherFeatureRun.id.in_(set(run_ids)))
        )
    }

    bound: list[FeatureValue] = []
    for feature in feature_values:
        if feature.feature_name not in WEATHER_FEATURE_NAMES:
            bound.append(feature)
            continue

        run_id = _required_run_id(feature)
        run = persisted_runs.get(run_id)
        if run is None:
            raise _error(feature.feature_name, "persisted WeatherFeatureRun was not found")
        if run.status != "completed":
            raise _error(feature.feature_name, "persisted WeatherFeatureRun is not completed")
        if not _LOWERCASE_SHA256.fullmatch(run.source_signature):
            raise _error(
                feature.feature_name,
                "persisted WeatherFeatureRun source_signature is not a SHA-256 identity",
            )
        if run.as_of_date > as_of_date:
            raise _error(
                feature.feature_name,
                "persisted WeatherFeatureRun as_of_date is after the Task 9 as_of date",
            )
        if run.feature_date > as_of_date:
            raise _error(
                feature.feature_name,
                "persisted WeatherFeatureRun feature_date is after the Task 9 as_of date",
            )
        if feature.observation_date is None:
            raise _error(feature.feature_name, "observation_date is required")
        if feature.observation_date != run.feature_date:
            raise _error(
                feature.feature_name,
                "observation_date does not match the persisted WeatherFeatureRun feature_date",
            )

        _require_matching_ref(
            feature,
            key="weather_source_signature",
            expected=run.source_signature,
        )
        _require_matching_ref(feature, key="weather_config_hash", expected=run.config_hash)
        _require_matching_ref(
            feature,
            key="weather_mapping_version",
            expected=run.mapping_version,
        )
        _require_matching_ref(
            feature,
            key="weather_source_version",
            expected=run.weather_source_version,
        )
        if feature.source_version != run.feature_version:
            raise _error(
                feature.feature_name,
                "source_version does not match the persisted WeatherFeatureRun feature_version",
            )

        bound.append(
            feature.model_copy(
                update={
                    "source_ref": {
                        "weather_feature_run_id": run.id,
                        "weather_source_signature": run.source_signature,
                        "weather_config_hash": run.config_hash,
                        "weather_mapping_version": run.mapping_version,
                        "weather_source_version": run.weather_source_version,
                    },
                    "source_version": run.feature_version,
                    "observation_date": run.feature_date,
                }
            )
        )

    return tuple(bound)
