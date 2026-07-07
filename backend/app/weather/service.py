from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.master_data import Season, Variety
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherDailyObservation,
    WeatherFeatureRun,
    WeatherSourceLocation,
)
from backend.app.planning.json_types import canonical_decimal_string, canonical_json_value
from backend.app.planning.plan_config import ProductionPlanConfig
from backend.app.planning.plan_service import get_effective_plan
from backend.app.weather.config import WeatherFeatureConfig
from backend.app.weather.hashing import sha256_payload
from backend.app.weather.provider import (
    CsvWeatherProvider,
    WeatherProviderError,
)
from backend.app.weather.repository import (
    create_base_temperature_search_run,
    create_location_weather_mapping,
    create_weather_feature_run,
    create_weather_import_run,
    create_weather_observation,
    create_weather_source_location,
    find_existing_base_temperature_search_run,
    find_existing_weather_feature_run,
    find_location_reference_for_plan,
    get_base_temperature_search_run,
    get_location_reference,
    get_location_weather_mapping_by_row_hash,
    get_plan_by_id,
    get_weather_feature_run,
    get_weather_observation_by_row_hash,
    get_weather_source_location,
    get_weather_source_location_by_business_key,
    get_weather_source_location_by_row_hash,
    list_effective_explicit_mappings,
    list_visible_weather_observations,
    list_visible_weather_source_locations,
    mark_weather_import_run_completed,
    mark_weather_import_run_failed,
    update_weather_feature_run,
)
from backend.app.weather.schemas import (
    BaseTemperatureCandidateScore,
    BaseTemperatureSearchExecutionResult,
    BaseTemperatureTrainingSample,
    DailyWeatherRecord,
    PhenologyTimeline,
    WeatherFeatureExecutionResult,
    WeatherMappingResult,
    WeatherSourceLocationRecord,
    WeatherSourceSelection,
    WeatherWindowFeature,
)

WEATHER_HISTORY_PROVIDER_VERSION = "task7-csv-v1"


class WeatherDataVersionConflictError(ValueError):
    pass


class WeatherMappingUnavailableError(ValueError):
    pass


class WeatherMappingConflictError(ValueError):
    pass


class WeatherCoverageError(ValueError):
    pass


class BaseTemperatureSearchUnavailableError(ValueError):
    pass


def _sanitize_error_message(message: str) -> str:
    return " ".join(str(message).replace("\n", " ").replace("\r", " ").split())[:500]


def _now() -> datetime:
    return datetime.now(UTC)


def _file_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_decimal_value(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value: {value}") from exc
    if not parsed.is_finite():
        raise ValueError(f"non-finite decimal value: {value}")
    return parsed


def _decimal_from_json(value: object | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            raise ValueError("decimal JSON value must be finite")
        return parsed
    raise ValueError(f"unsupported decimal JSON value: {type(value).__name__}")


def _date_from_json(value: object | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"unsupported date JSON value: {type(value).__name__}")


def _date_value(value: date | str, *, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO date") from exc


def _daterange(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def _window_start(feature_date: date, window_days: int) -> date:
    return feature_date - timedelta(days=window_days - 1)


def _mapping_confidence(
    score: Decimal,
    config: WeatherFeatureConfig,
) -> Literal["high", "medium", "low"]:
    rules = config.rules.mapping
    if score <= rules.high_confidence_max_score:
        return "high"
    if score <= rules.medium_confidence_max_score:
        return "medium"
    return "low"


def _source_location_row_hash(record: WeatherSourceLocationRecord) -> str:
    return sha256_payload(
        {
            "provider_code": record.provider_code,
            "external_location_id": record.external_location_id,
            "location_type": record.location_type,
            "name": record.name,
            "latitude": record.latitude,
            "longitude": record.longitude,
            "altitude_m": record.altitude_m,
            "timezone_name": record.timezone_name,
            "grid_resolution": record.grid_resolution,
            "source_version": record.source_version,
            "valid_from": record.valid_from,
            "valid_to": record.valid_to,
        }
    )


def _observation_row_hash(
    source_location_id: int,
    record: DailyWeatherRecord,
    *,
    source_file_sha256: str | None,
) -> str:
    return sha256_payload(
        {
            "weather_source_location_id": source_location_id,
            "observation_date": record.observation_date,
            "temperature_min_c": record.temperature_min_c,
            "temperature_max_c": record.temperature_max_c,
            "temperature_mean_c": record.temperature_mean_c,
            "temperature_mean_source": record.temperature_mean_source,
            "precipitation_mm": record.precipitation_mm,
            "solar_radiation_mj_m2": record.solar_radiation_mj_m2,
            "provider_code": record.provider_code,
            "source_version": record.source_version,
            "available_at": record.available_at,
            "quality_code": record.quality_code,
            "quality_flags": record.quality_flags,
            "source_file_sha256": source_file_sha256,
            "source_row_number": record.source_row_number,
        }
    )


def _mapping_row_hash(
    *,
    location_reference_id: int,
    weather_source_location_id: int,
    mapping_method: str,
    mapping_version: str,
    config_hash: str,
    available_at: date,
    valid_from: date,
    valid_to: date | None,
) -> str:
    return sha256_payload(
        {
            "location_reference_id": location_reference_id,
            "weather_source_location_id": weather_source_location_id,
            "mapping_method": mapping_method,
            "mapping_version": mapping_version,
            "config_hash": config_hash,
            "available_at": available_at,
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
    )


def _selected_observation_fingerprint(
    selections: list[WeatherSourceSelection] | tuple[WeatherSourceSelection, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "observation_date": item.observation_date,
            "observation_id": item.observation_id,
            "row_hash": item.row_hash,
            "available_at": item.available_at,
            "source_version": item.source_version,
            "weather_source_location_id": item.weather_source_location_id,
        }
        for item in sorted(
            selections,
            key=lambda entry: (entry.observation_date, entry.observation_id),
        )
    ]


def _feature_source_signature(
    *,
    plan_id: int,
    plan_version: int,
    as_of_date: date,
    feature_date: date,
    mapping_row_hash: str,
    base_temperature_search_run_id: int | None,
    base_temperature_search_source_signature: str | None,
    selected_base_temperature: Decimal | None,
    config_hash: str,
    feature_version: str,
    weather_observation_fingerprint: list[dict[str, Any]],
) -> str:
    return sha256_payload(
        {
            "plan_id": plan_id,
            "plan_version": plan_version,
            "as_of_date": as_of_date,
            "feature_date": feature_date,
            "mapping_row_hash": mapping_row_hash,
            "base_temperature_search_run_id": base_temperature_search_run_id,
            "base_temperature_search_source_signature": base_temperature_search_source_signature,
            "selected_base_temperature": selected_base_temperature,
            "config_hash": config_hash,
            "feature_version": feature_version,
            "weather_observation_fingerprint": weather_observation_fingerprint,
        }
    )


def _base_temperature_source_signature(
    *,
    training_cutoff: date,
    scope_type: str,
    variety_id: int | None,
    climate_zone_id: int | None,
    config_hash: str,
    feature_version: str,
    candidate_temperatures: tuple[Decimal, ...],
    training_manifest: list[dict[str, Any]],
) -> str:
    return sha256_payload(
        {
            "training_cutoff": training_cutoff,
            "scope_type": scope_type,
            "variety_id": variety_id,
            "climate_zone_id": climate_zone_id,
            "config_hash": config_hash,
            "feature_version": feature_version,
            "candidate_temperatures": list(candidate_temperatures),
            "training_manifest": training_manifest,
        }
    )


def _quantized_distance(
    latitude_a: Decimal,
    longitude_a: Decimal,
    latitude_b: Decimal,
    longitude_b: Decimal,
) -> Decimal:
    from backend.app.planning.similarity import haversine_distance_km

    return haversine_distance_km(
        float(latitude_a),
        float(longitude_a),
        float(latitude_b),
        float(longitude_b),
    )


def _source_location_altitude_difference(
    reference_altitude_m: Decimal | None,
    source_altitude_m: Decimal | None,
) -> Decimal | None:
    if reference_altitude_m is None or source_altitude_m is None:
        return None
    return abs(reference_altitude_m - source_altitude_m).quantize(Decimal("0.000001"))


def _mapping_score(
    *,
    distance_km: Decimal,
    altitude_difference_m: Decimal | None,
    provider_priority: int,
    location_type_priority: int,
    config: WeatherFeatureConfig,
) -> Decimal:
    score = distance_km
    if altitude_difference_m is None:
        score += config.rules.mapping.missing_altitude_penalty
    else:
        score += (
            altitude_difference_m / Decimal("1000")
        ) * config.rules.mapping.altitude_penalty_weight
    score += Decimal(provider_priority) / Decimal("1000")
    score += Decimal(location_type_priority) / Decimal("10000")
    return score.quantize(Decimal("0.000001"))


def _select_visible_observation_per_day(
    rows: list[WeatherDailyObservation],
) -> list[WeatherSourceSelection]:
    grouped: dict[date, list[WeatherDailyObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.observation_date].append(row)

    selections: list[WeatherSourceSelection] = []
    for observation_date in sorted(grouped):
        candidates = sorted(
            grouped[observation_date],
            key=lambda item: (
                item.available_at,
                item.source_version,
                item.id,
            ),
            reverse=True,
        )
        winner = candidates[0]
        if len(candidates) > 1:
            second = candidates[1]
            if (
                second.available_at == winner.available_at
                and second.source_version == winner.source_version
                and second.row_hash != winner.row_hash
            ):
                raise WeatherDataVersionConflictError(
                    f"conflicting weather observations for {observation_date.isoformat()}"
                )
        mean_value = winner.temperature_mean_c
        if mean_value is None:
            raise WeatherDataVersionConflictError(
                "temperature_mean_c must be available after parse"
            )
        selections.append(
            WeatherSourceSelection(
                observation_date=winner.observation_date,
                observation_id=winner.id,
                row_hash=winner.row_hash,
                weather_source_location_id=winner.weather_source_location_id,
                provider_code=winner.provider_code,
                source_version=winner.source_version,
                available_at=winner.available_at,
                temperature_min_c=winner.temperature_min_c,
                temperature_max_c=winner.temperature_max_c,
                temperature_mean_c=mean_value,
                precipitation_mm=winner.precipitation_mm,
                solar_radiation_mj_m2=winner.solar_radiation_mj_m2,
                quality_code=winner.quality_code,
                quality_flags=tuple(winner.quality_flags),
            )
        )
    return selections


def _window_feature_from_observations(
    *,
    observations_by_date: dict[date, WeatherSourceSelection],
    feature_date: date,
    window_days: int,
    base_temperature: Decimal | None,
    config: WeatherFeatureConfig,
) -> WeatherWindowFeature:
    expected_dates = _daterange(_window_start(feature_date, window_days), feature_date)
    valid_days: list[WeatherSourceSelection] = []
    missing_dates: list[date] = []
    aggregated_quality: set[str] = set()

    rainy_threshold = config.rules.features.rainy_day_threshold_mm
    current_rainy_streak = 0
    max_rainy_streak = 0

    for day in expected_dates:
        observation = observations_by_date.get(day)
        if observation is None or observation.solar_radiation_mj_m2 is None:
            missing_dates.append(day)
            current_rainy_streak = 0
            continue
        valid_days.append(observation)
        aggregated_quality.update(observation.quality_flags)
        if observation.precipitation_mm >= rainy_threshold:
            current_rainy_streak += 1
            max_rainy_streak = max(max_rainy_streak, current_rainy_streak)
        else:
            current_rainy_streak = 0

    expected_day_count = len(expected_dates)
    observed_day_count = len(valid_days)
    coverage_ratio = (
        (Decimal(observed_day_count) / Decimal(expected_day_count)).quantize(Decimal("0.000001"))
        if expected_day_count > 0
        else Decimal("0")
    )
    if coverage_ratio < config.rules.features.minimum_coverage_ratio or not valid_days:
        flags = sorted(aggregated_quality | {"insufficient_weather_coverage"})
        return WeatherWindowFeature(
            window_days=window_days,
            status="unavailable",
            effective_temperature_sum=None,
            solar_radiation_sum=None,
            precipitation_sum=None,
            minimum_temperature=None,
            mean_diurnal_temperature_range=None,
            maximum_consecutive_rainy_days=None,
            observed_day_count=observed_day_count,
            expected_day_count=expected_day_count,
            coverage_ratio=coverage_ratio,
            missing_dates=tuple(missing_dates),
            quality_flags=tuple(flags),
            source_observation_ids=tuple(item.observation_id for item in valid_days),
        )

    effective_temperature_sum = (
        sum(
            (max(item.temperature_mean_c - base_temperature, Decimal("0")) for item in valid_days),
            Decimal("0"),
        )
        if base_temperature is not None
        else None
    )
    precipitation_sum = sum((item.precipitation_mm for item in valid_days), Decimal("0"))
    solar_sum = sum(
        (cast(Decimal, item.solar_radiation_mj_m2) for item in valid_days),
        Decimal("0"),
    )
    minimum_temperature = min(item.temperature_min_c for item in valid_days)
    mean_dtr = sum(
        (item.temperature_max_c - item.temperature_min_c for item in valid_days),
        Decimal("0"),
    ) / Decimal(len(valid_days))

    return WeatherWindowFeature(
        window_days=window_days,
        status="available",
        effective_temperature_sum=(
            None
            if effective_temperature_sum is None
            else effective_temperature_sum.quantize(Decimal("0.000001"))
        ),
        solar_radiation_sum=solar_sum.quantize(Decimal("0.000001")),
        precipitation_sum=precipitation_sum.quantize(Decimal("0.000001")),
        minimum_temperature=minimum_temperature.quantize(Decimal("0.000001")),
        mean_diurnal_temperature_range=mean_dtr.quantize(Decimal("0.000001")),
        maximum_consecutive_rainy_days=max_rainy_streak,
        observed_day_count=observed_day_count,
        expected_day_count=expected_day_count,
        coverage_ratio=coverage_ratio,
        missing_dates=tuple(missing_dates),
        quality_flags=tuple(sorted(aggregated_quality)),
        source_observation_ids=tuple(item.observation_id for item in valid_days),
    )


def _event_date(plan: FarmSeasonVarietyPlan, event_name: str) -> date | None:
    mapping = {
        "pruning_date": plan.pruning_date,
        "flowering_start_date": plan.flowering_start_date,
        "flowering_peak_date": plan.flowering_peak_date,
        "flowering_end_date": plan.flowering_end_date,
        "first_pick_date": plan.first_pick_date,
    }
    if event_name not in mapping:
        raise ValueError(f"unsupported phenology event: {event_name}")
    return mapping[event_name]


def _days_since(anchor: date | None, feature_date: date) -> int | None:
    if anchor is None:
        return None
    return (feature_date - anchor).days


def _days_until(target: date | None, feature_date: date) -> int | None:
    if target is None:
        return None
    return (target - feature_date).days


def _build_phenology_timeline(
    *,
    plan: FarmSeasonVarietyPlan,
    feature_date: date,
    mapping_id: int | None,
    feature_version: str,
    anchor_event: str | None,
    base_temperature: Decimal | None,
    observations_by_date: dict[date, WeatherSourceSelection],
) -> PhenologyTimeline:
    warnings: list[str] = []
    anchor_date = _event_date(plan, anchor_event) if anchor_event is not None else None

    cumulative_effective_temperature: Decimal | None = None
    cumulative_expected_day_count = 0
    cumulative_observed_day_count = 0
    cumulative_coverage_ratio: Decimal | None = None
    cumulative_missing_dates: tuple[date, ...] = ()
    if anchor_event is not None and anchor_date is None:
        warnings.append(f"missing_{anchor_event}")
    elif anchor_date is not None and feature_date >= anchor_date and base_temperature is not None:
        expected_dates = _daterange(anchor_date, feature_date)
        cumulative_expected_day_count = len(expected_dates)
        observed_values: list[Decimal] = []
        missing_dates: list[date] = []
        for day in expected_dates:
            observation = observations_by_date.get(day)
            if observation is None:
                missing_dates.append(day)
                continue
            observed_values.append(
                max(observation.temperature_mean_c - base_temperature, Decimal("0"))
            )
        cumulative_observed_day_count = len(observed_values)
        cumulative_missing_dates = tuple(missing_dates)
        if cumulative_expected_day_count > 0:
            cumulative_coverage_ratio = (
                Decimal(cumulative_observed_day_count) / Decimal(cumulative_expected_day_count)
            ).quantize(Decimal("0.000001"))
        if missing_dates:
            warnings.append("anchor_weather_incomplete")
        else:
            cumulative_effective_temperature = sum(
                observed_values,
                Decimal("0"),
            ).quantize(Decimal("0.000001"))

    return PhenologyTimeline(
        plan_id=plan.id,
        plan_version=plan.version,
        pruning_date=plan.pruning_date,
        flowering_start_date=plan.flowering_start_date,
        flowering_peak_date=plan.flowering_peak_date,
        flowering_end_date=plan.flowering_end_date,
        first_pick_date=plan.first_pick_date,
        days_since_pruning=_days_since(plan.pruning_date, feature_date),
        days_since_flowering_start=_days_since(plan.flowering_start_date, feature_date),
        days_since_flowering_peak=_days_since(plan.flowering_peak_date, feature_date),
        days_since_flowering_end=_days_since(plan.flowering_end_date, feature_date),
        days_until_first_pick=_days_until(plan.first_pick_date, feature_date),
        anchor_event=anchor_event,
        anchor_date=anchor_date,
        cumulative_effective_temperature=cumulative_effective_temperature,
        cumulative_expected_day_count=cumulative_expected_day_count,
        cumulative_observed_day_count=cumulative_observed_day_count,
        cumulative_coverage_ratio=cumulative_coverage_ratio,
        cumulative_missing_dates=cumulative_missing_dates,
        selected_weather_mapping_id=mapping_id,
        weather_feature_version=feature_version,
        warnings=tuple(warnings),
    )


def _weather_feature_payload(result: WeatherFeatureExecutionResult) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "status": result.status,
                "run_id": result.run_id,
                "source_signature": result.source_signature,
                "feature_version": result.feature_version,
                "config_hash": result.config_hash,
                "mapping": result.mapping,
                "weather_source_version": result.weather_source_version,
                "plan": result.plan,
                "windows": [asdict(item) for item in result.windows],
                "timeline": asdict(result.timeline),
                "weather_observation_ids": list(result.weather_observation_ids),
                "warnings": list(result.warnings),
                "blockers": list(result.blockers),
                "input_snapshot": result.input_snapshot,
                "error_message": result.error_message,
            }
        ),
    )


def _base_temperature_payload(result: BaseTemperatureSearchExecutionResult) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "status": result.status,
                "run_id": result.run_id,
                "source_signature": result.source_signature,
                "config_hash": result.config_hash,
                "feature_version": result.feature_version,
                "selected_base_temperature": result.selected_base_temperature,
                "scoring_method": result.scoring_method,
                "selected_score": result.selected_score,
                "sample_count": result.sample_count,
                "distinct_season_count": result.distinct_season_count,
                "candidate_scores": [asdict(item) for item in result.candidate_scores],
                "warnings": list(result.warnings),
                "blockers": list(result.blockers),
                "input_snapshot": result.input_snapshot,
                "error_message": result.error_message,
            }
        ),
    )


def _candidate_scores_payload(
    candidate_scores: list[BaseTemperatureCandidateScore]
    | tuple[BaseTemperatureCandidateScore, ...],
) -> dict[str, Any]:
    payload = {
        "candidates": [
            {
                "base_temperature": canonical_decimal_string(item.base_temperature),
                "fold_count": item.fold_count,
                "evaluated_sample_count": item.evaluated_sample_count,
                "mae_days": None if item.mae_days is None else format(item.mae_days, "f"),
                "warnings": list(item.warnings),
            }
            for item in candidate_scores
        ],
    }
    return cast(
        dict[str, Any],
        canonical_json_value(payload),
    )


def _run_status_value(
    status: str,
) -> Literal["completed", "skipped", "running", "failed", "unavailable", "dry_run"]:
    if status in {"running", "completed", "failed", "unavailable"}:
        return cast(Literal["completed", "running", "failed", "unavailable"], status)
    raise ValueError(f"unsupported persisted run status: {status}")


def _base_temperature_result_from_run(
    run: BaseTemperatureSearchRun,
) -> BaseTemperatureSearchExecutionResult:
    return BaseTemperatureSearchExecutionResult(
        status=_run_status_value(run.status),
        run_id=run.id,
        source_signature=run.source_signature,
        config_hash=run.config_hash,
        feature_version=run.feature_version,
        selected_base_temperature=run.selected_base_temperature,
        scoring_method=run.scoring_method,
        selected_score=run.selected_score,
        sample_count=run.sample_count,
        distinct_season_count=run.distinct_season_count,
        candidate_scores=tuple(
            _rehydrate_candidate_score(item)
            for item in cast(list[dict[str, Any]], run.candidate_scores.get("candidates", []))
        ),
        warnings=tuple(run.warnings),
        blockers=tuple(run.blockers),
        input_snapshot=run.input_snapshot,
        error_message=run.error_message,
    )


def _weather_feature_result_from_run(run: WeatherFeatureRun) -> WeatherFeatureExecutionResult:
    payload = run.window_features
    return WeatherFeatureExecutionResult(
        status=_run_status_value(run.status),
        run_id=run.id,
        source_signature=run.source_signature,
        feature_version=run.feature_version,
        config_hash=run.config_hash,
        mapping=cast(dict[str, Any], run.input_snapshot.get("mapping", {})),
        weather_source_version=run.weather_source_version,
        plan=cast(dict[str, Any], run.input_snapshot.get("plan", {})),
        windows=tuple(
            _rehydrate_window_feature(item)
            for item in cast(list[dict[str, Any]], payload.get("windows", []))
        ),
        timeline=_rehydrate_timeline(run.timeline_payload),
        weather_observation_ids=tuple(run.weather_observation_ids),
        warnings=tuple(run.warnings),
        blockers=tuple(run.blockers),
        input_snapshot=run.input_snapshot,
        error_message=run.error_message,
    )


def _rehydrate_window_feature(payload: dict[str, Any]) -> WeatherWindowFeature:
    return WeatherWindowFeature(
        window_days=int(payload["window_days"]),
        status=cast(Literal["available", "unavailable"], payload["status"]),
        effective_temperature_sum=_decimal_from_json(payload.get("effective_temperature_sum")),
        solar_radiation_sum=_decimal_from_json(payload.get("solar_radiation_sum")),
        precipitation_sum=_decimal_from_json(payload.get("precipitation_sum")),
        minimum_temperature=_decimal_from_json(payload.get("minimum_temperature")),
        mean_diurnal_temperature_range=_decimal_from_json(
            payload.get("mean_diurnal_temperature_range")
        ),
        maximum_consecutive_rainy_days=(
            None
            if payload.get("maximum_consecutive_rainy_days") is None
            else int(payload["maximum_consecutive_rainy_days"])
        ),
        observed_day_count=int(payload["observed_day_count"]),
        expected_day_count=int(payload["expected_day_count"]),
        coverage_ratio=cast(Decimal, _decimal_from_json(payload["coverage_ratio"])),
        missing_dates=tuple(
            item
            for item in (_date_from_json(value) for value in payload.get("missing_dates", []))
            if item is not None
        ),
        quality_flags=tuple(str(item) for item in payload.get("quality_flags", [])),
        source_observation_ids=tuple(
            int(item) for item in payload.get("source_observation_ids", [])
        ),
    )


def _rehydrate_timeline(payload: dict[str, Any]) -> PhenologyTimeline:
    return PhenologyTimeline(
        plan_id=int(payload["plan_id"]),
        plan_version=int(payload["plan_version"]),
        pruning_date=_date_from_json(payload.get("pruning_date")),
        flowering_start_date=_date_from_json(payload.get("flowering_start_date")),
        flowering_peak_date=_date_from_json(payload.get("flowering_peak_date")),
        flowering_end_date=_date_from_json(payload.get("flowering_end_date")),
        first_pick_date=_date_from_json(payload.get("first_pick_date")),
        days_since_pruning=(
            None
            if payload.get("days_since_pruning") is None
            else int(payload["days_since_pruning"])
        ),
        days_since_flowering_start=(
            None
            if payload.get("days_since_flowering_start") is None
            else int(payload["days_since_flowering_start"])
        ),
        days_since_flowering_peak=(
            None
            if payload.get("days_since_flowering_peak") is None
            else int(payload["days_since_flowering_peak"])
        ),
        days_since_flowering_end=(
            None
            if payload.get("days_since_flowering_end") is None
            else int(payload["days_since_flowering_end"])
        ),
        days_until_first_pick=(
            None
            if payload.get("days_until_first_pick") is None
            else int(payload["days_until_first_pick"])
        ),
        anchor_event=cast(str | None, payload.get("anchor_event")),
        anchor_date=_date_from_json(payload.get("anchor_date")),
        cumulative_effective_temperature=_decimal_from_json(
            payload.get("cumulative_effective_temperature")
        ),
        cumulative_expected_day_count=int(payload.get("cumulative_expected_day_count", 0)),
        cumulative_observed_day_count=int(payload.get("cumulative_observed_day_count", 0)),
        cumulative_coverage_ratio=_decimal_from_json(payload.get("cumulative_coverage_ratio")),
        cumulative_missing_dates=tuple(
            item
            for item in (
                _date_from_json(value) for value in payload.get("cumulative_missing_dates", [])
            )
            if item is not None
        ),
        selected_weather_mapping_id=(
            None
            if payload.get("selected_weather_mapping_id") is None
            else int(payload["selected_weather_mapping_id"])
        ),
        weather_feature_version=str(payload["weather_feature_version"]),
        warnings=tuple(str(item) for item in payload.get("warnings", [])),
    )


def _rehydrate_candidate_score(payload: dict[str, Any]) -> BaseTemperatureCandidateScore:
    return BaseTemperatureCandidateScore(
        base_temperature=cast(Decimal, _decimal_from_json(payload["base_temperature"])),
        fold_count=int(payload["fold_count"]),
        evaluated_sample_count=int(payload["evaluated_sample_count"]),
        mae_days=_decimal_from_json(payload.get("mae_days")),
        warnings=tuple(str(item) for item in payload.get("warnings", [])),
    )


async def import_weather_locations(
    session: AsyncSession,
    *,
    file_path: Path,
    provider_code: str,
    dataset_version: str,
    location_type: Literal["station", "grid"],
    dry_run: bool,
) -> dict[str, Any]:
    provider = CsvWeatherProvider(
        file_path=file_path,
        provider_code=provider_code,
        provider_version=WEATHER_HISTORY_PROVIDER_VERSION,
        dataset_version=dataset_version,
        location_type=location_type,
    )
    file_sha256 = _file_sha256(file_path)
    report: dict[str, Any] = {
        "provider_code": provider_code,
        "dataset_version": dataset_version,
        "location_type": location_type,
        "errors": [],
    }
    inserted = 0
    skipped = 0
    duplicate_count = 0
    rejected_count = 0
    invalid_date_count = 0
    invalid_numeric_count = 0
    conflict_count = 0

    run_id: int | None = None
    if not dry_run:
        run = await create_weather_import_run(
            session,
            import_type="location",
            provider_code=provider_code,
            file_name=file_path.name,
            file_sha256=file_sha256,
            source_version=dataset_version,
            dry_run=False,
            report_json=report,
        )
        run_id = run.id

    rows: list[WeatherSourceLocationRecord]
    try:
        rows = provider.parse_location_rows()
    except WeatherProviderError as exc:
        if run_id is not None:
            await mark_weather_import_run_failed(
                session,
                run_id=run_id,
                report_json=report,
                error_message=_sanitize_error_message(str(exc)),
            )
        raise

    try:
        for row in rows:
            row_hash = _source_location_row_hash(row)
            existing = await get_weather_source_location_by_row_hash(session, row_hash=row_hash)
            if existing is not None:
                skipped += 1
                duplicate_count += 1
                continue
            business_existing = await get_weather_source_location_by_business_key(
                session,
                provider_code=row.provider_code,
                external_location_id=row.external_location_id,
                source_version=row.source_version,
            )
            if business_existing is not None:
                skipped += 1
                duplicate_count += 1
                continue
            inserted += 1
            if dry_run:
                continue
            await create_weather_source_location(
                session,
                record=WeatherSourceLocation(
                    provider_code=row.provider_code,
                    external_location_id=row.external_location_id,
                    location_type=row.location_type,
                    name=row.name,
                    latitude=row.latitude,
                    longitude=row.longitude,
                    altitude_m=row.altitude_m,
                    timezone_name=row.timezone_name,
                    grid_resolution=row.grid_resolution,
                    source_version=row.source_version,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    row_hash=row_hash,
                ),
            )
        if dry_run:
            return {
                "status": "dry_run",
                "file_sha256": file_sha256,
                "row_count": len(rows),
                "inserted_count": inserted,
                "skipped_count": skipped,
            }
        await session.commit()
        assert run_id is not None
        await mark_weather_import_run_completed(
            session,
            run_id=run_id,
            row_count=len(rows),
            inserted_count=inserted,
            skipped_count=skipped,
            duplicate_count=duplicate_count,
            rejected_count=rejected_count,
            invalid_date_count=invalid_date_count,
            invalid_numeric_count=invalid_numeric_count,
            unknown_location_count=0,
            conflict_count=conflict_count,
            report_json=report,
        )
        return {
            "status": "completed",
            "file_sha256": file_sha256,
            "row_count": len(rows),
            "inserted_count": inserted,
            "skipped_count": skipped,
            "audit_run_id": run_id,
        }
    except Exception as exc:
        await session.rollback()
        if run_id is not None:
            await mark_weather_import_run_failed(
                session,
                run_id=run_id,
                report_json=report,
                error_message=_sanitize_error_message(str(exc)),
            )
        raise


async def import_weather_observations(
    session: AsyncSession,
    *,
    file_path: Path,
    provider_code: str,
    dataset_version: str,
    location_type: Literal["station", "grid"],
    dry_run: bool,
) -> dict[str, Any]:
    provider = CsvWeatherProvider(
        file_path=file_path,
        provider_code=provider_code,
        provider_version=WEATHER_HISTORY_PROVIDER_VERSION,
        dataset_version=dataset_version,
        location_type=location_type,
    )
    file_sha256 = _file_sha256(file_path)
    report: dict[str, Any] = {
        "provider_code": provider_code,
        "dataset_version": dataset_version,
        "errors": [],
    }
    inserted = 0
    skipped = 0
    duplicate_count = 0
    rejected_count = 0
    invalid_date_count = 0
    invalid_numeric_count = 0
    unknown_location_count = 0
    conflict_count = 0

    run_id: int | None = None
    if not dry_run:
        run = await create_weather_import_run(
            session,
            import_type="observation",
            provider_code=provider_code,
            file_name=file_path.name,
            file_sha256=file_sha256,
            source_version=dataset_version,
            dry_run=False,
            report_json=report,
        )
        run_id = run.id

    rows = provider.parse_observation_rows()
    try:
        for row in rows:
            locations = await list_visible_weather_source_locations(
                session,
                as_of_date=row.observation_date,
                provider_code=row.provider_code,
            )
            matches = [
                item for item in locations if item.external_location_id == row.external_location_id
            ]
            if not matches:
                unknown_location_count += 1
                rejected_count += 1
                continue
            matches.sort(
                key=lambda item: (
                    item.valid_from,
                    item.source_version,
                    item.id,
                ),
                reverse=True,
            )
            source_location = matches[0]
            row_hash = _observation_row_hash(
                source_location.id,
                row,
                source_file_sha256=file_sha256,
            )
            if await get_weather_observation_by_row_hash(session, row_hash=row_hash) is not None:
                skipped += 1
                duplicate_count += 1
                continue
            inserted += 1
            if dry_run:
                continue
            await create_weather_observation(
                session,
                record=WeatherDailyObservation(
                    weather_source_location_id=source_location.id,
                    observation_date=row.observation_date,
                    temperature_min_c=row.temperature_min_c,
                    temperature_max_c=row.temperature_max_c,
                    temperature_mean_c=row.temperature_mean_c,
                    temperature_mean_source=row.temperature_mean_source,
                    precipitation_mm=row.precipitation_mm,
                    solar_radiation_mj_m2=row.solar_radiation_mj_m2,
                    provider_code=row.provider_code,
                    source_version=row.source_version,
                    available_at=row.available_at,
                    quality_code=row.quality_code,
                    quality_flags=list(row.quality_flags),
                    source_file_sha256=file_sha256,
                    source_row_number=row.source_row_number,
                    row_hash=row_hash,
                ),
            )
        if dry_run:
            return {
                "status": "dry_run",
                "file_sha256": file_sha256,
                "row_count": len(rows),
                "inserted_count": inserted,
                "skipped_count": skipped,
                "unknown_location_count": unknown_location_count,
            }
        await session.commit()
        assert run_id is not None
        await mark_weather_import_run_completed(
            session,
            run_id=run_id,
            row_count=len(rows),
            inserted_count=inserted,
            skipped_count=skipped,
            duplicate_count=duplicate_count,
            rejected_count=rejected_count,
            invalid_date_count=invalid_date_count,
            invalid_numeric_count=invalid_numeric_count,
            unknown_location_count=unknown_location_count,
            conflict_count=conflict_count,
            report_json=report,
        )
        return {
            "status": "completed",
            "file_sha256": file_sha256,
            "row_count": len(rows),
            "inserted_count": inserted,
            "skipped_count": skipped,
            "audit_run_id": run_id,
        }
    except Exception as exc:
        await session.rollback()
        if run_id is not None:
            await mark_weather_import_run_failed(
                session,
                run_id=run_id,
                report_json=report,
                error_message=_sanitize_error_message(str(exc)),
            )
        raise


async def import_location_weather_mappings(
    session: AsyncSession,
    *,
    file_path: Path,
    config: WeatherFeatureConfig,
    dry_run: bool,
) -> dict[str, Any]:
    import csv

    file_sha256 = _file_sha256(file_path)
    report: dict[str, Any] = {"errors": []}
    inserted = 0
    skipped = 0
    duplicate_count = 0
    rejected_count = 0
    unknown_location_count = 0
    conflict_count = 0
    with file_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    run_id: int | None = None
    if not dry_run:
        run = await create_weather_import_run(
            session,
            import_type="mapping",
            provider_code=None,
            file_name=file_path.name,
            file_sha256=file_sha256,
            source_version=None,
            dry_run=False,
            report_json=report,
        )
        run_id = run.id

    try:
        for row in rows:
            location_reference_id = int(row["location_reference_id"])
            location_reference = await get_location_reference(
                session,
                location_reference_id=location_reference_id,
            )
            if location_reference is None:
                unknown_location_count += 1
                rejected_count += 1
                continue
            provider_code = str(row["provider_code"]).strip()
            external_location_id = str(row["external_location_id"]).strip()
            valid_from = _date_value(row["valid_from"], field="valid_from")
            valid_to = (
                _date_value(row["valid_to"], field="valid_to") if row.get("valid_to") else None
            )
            available_at = _date_value(row["available_at"], field="available_at")
            source_locations = await list_visible_weather_source_locations(
                session,
                as_of_date=valid_from,
                provider_code=provider_code,
            )
            matches = [
                item
                for item in source_locations
                if item.external_location_id == external_location_id
            ]
            if not matches:
                unknown_location_count += 1
                rejected_count += 1
                continue
            if len(matches) > 1:
                conflict_count += 1
                rejected_count += 1
                continue
            source_location = matches[0]
            distance_km = _quantized_distance(
                location_reference.latitude,
                location_reference.longitude,
                source_location.latitude,
                source_location.longitude,
            )
            altitude_difference_m = _source_location_altitude_difference(
                location_reference.altitude_m,
                source_location.altitude_m,
            )
            row_hash = _mapping_row_hash(
                location_reference_id=location_reference.id,
                weather_source_location_id=source_location.id,
                mapping_method=str(row["mapping_method"]).strip(),
                mapping_version=str(row["mapping_version"]).strip(),
                config_hash=config.config_hash,
                available_at=available_at,
                valid_from=valid_from,
                valid_to=valid_to,
            )
            existing_mapping = await get_location_weather_mapping_by_row_hash(
                session,
                row_hash=row_hash,
            )
            if existing_mapping is not None:
                skipped += 1
                duplicate_count += 1
                continue
            inserted += 1
            if dry_run:
                continue
            await create_location_weather_mapping(
                session,
                record=LocationWeatherMapping(
                    location_reference_id=location_reference.id,
                    weather_source_location_id=source_location.id,
                    mapping_method=str(row["mapping_method"]).strip(),
                    distance_km=distance_km,
                    altitude_difference_m=altitude_difference_m,
                    mapping_score=Decimal("0"),
                    confidence_level="high",
                    mapping_version=str(row["mapping_version"]).strip(),
                    config_hash=config.config_hash,
                    available_at=available_at,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    row_hash=row_hash,
                ),
            )
        if dry_run:
            return {
                "status": "dry_run",
                "file_sha256": file_sha256,
                "row_count": len(rows),
                "inserted_count": inserted,
                "skipped_count": skipped,
            }
        await session.commit()
        assert run_id is not None
        await mark_weather_import_run_completed(
            session,
            run_id=run_id,
            row_count=len(rows),
            inserted_count=inserted,
            skipped_count=skipped,
            duplicate_count=duplicate_count,
            rejected_count=rejected_count,
            invalid_date_count=0,
            invalid_numeric_count=0,
            unknown_location_count=unknown_location_count,
            conflict_count=conflict_count,
            report_json=report,
        )
        return {
            "status": "completed",
            "file_sha256": file_sha256,
            "row_count": len(rows),
            "inserted_count": inserted,
            "skipped_count": skipped,
            "audit_run_id": run_id,
        }
    except Exception as exc:
        await session.rollback()
        if run_id is not None:
            await mark_weather_import_run_failed(
                session,
                run_id=run_id,
                report_json=report,
                error_message=_sanitize_error_message(str(exc)),
            )
        raise


def _explicit_mapping_result(
    mapping: LocationWeatherMapping,
    source_location: WeatherSourceLocation,
    *,
    config: WeatherFeatureConfig,
) -> WeatherMappingResult:
    return WeatherMappingResult(
        status="resolved",
        mapping_id=mapping.id,
        location_reference_id=mapping.location_reference_id,
        weather_source_location_id=source_location.id,
        mapping_method=mapping.mapping_method,
        distance_km=mapping.distance_km,
        altitude_difference_m=mapping.altitude_difference_m,
        mapping_score=mapping.mapping_score,
        confidence_level=cast(Literal["high", "medium", "low"], mapping.confidence_level),
        mapping_version=mapping.mapping_version,
        config_hash=config.config_hash,
        provider_code=source_location.provider_code,
        external_location_id=source_location.external_location_id,
        warnings=(),
        reproducibility_snapshot={
            "mapping_id": mapping.id,
            "row_hash": mapping.row_hash,
            "location_reference_id": mapping.location_reference_id,
            "weather_source_location_id": source_location.id,
            "provider_code": source_location.provider_code,
            "external_location_id": source_location.external_location_id,
            "mapping_method": mapping.mapping_method,
            "mapping_version": mapping.mapping_version,
            "config_hash": config.config_hash,
        },
    )


async def resolve_weather_mapping(
    session: AsyncSession,
    *,
    location_reference_id: int,
    as_of_date: date,
    config: WeatherFeatureConfig,
    persist: bool,
) -> WeatherMappingResult:
    location_reference = await get_location_reference(
        session,
        location_reference_id=location_reference_id,
    )
    if location_reference is None:
        raise WeatherMappingUnavailableError("location_reference not found")

    explicit = await list_effective_explicit_mappings(
        session,
        location_reference_id=location_reference_id,
        as_of_date=as_of_date,
    )
    if len(explicit) > 1:
        return WeatherMappingResult(
            status="conflict",
            mapping_id=None,
            location_reference_id=location_reference_id,
            weather_source_location_id=None,
            mapping_method=None,
            distance_km=None,
            altitude_difference_m=None,
            mapping_score=None,
            confidence_level=None,
            mapping_version=config.rules.features.version,
            config_hash=config.config_hash,
            provider_code=None,
            external_location_id=None,
            warnings=("mapping_conflict",),
            reproducibility_snapshot={},
        )
    if explicit:
        source_location = await get_weather_source_location(
            session,
            weather_source_location_id=explicit[0].weather_source_location_id,
        )
        if source_location is None:
            raise WeatherMappingConflictError("explicit mapping target not found")
        return _explicit_mapping_result(explicit[0], source_location, config=config)

    source_locations = await list_visible_weather_source_locations(
        session,
        as_of_date=as_of_date,
    )
    if not source_locations:
        return WeatherMappingResult(
            status="unavailable",
            mapping_id=None,
            location_reference_id=location_reference_id,
            weather_source_location_id=None,
            mapping_method=None,
            distance_km=None,
            altitude_difference_m=None,
            mapping_score=None,
            confidence_level=None,
            mapping_version=config.rules.features.version,
            config_hash=config.config_hash,
            provider_code=None,
            external_location_id=None,
            warnings=("mapping_unavailable",),
            reproducibility_snapshot={},
        )

    candidates: list[
        tuple[
            Decimal,
            Decimal,
            int,
            str,
            int,
            WeatherSourceLocation,
            str,
            Decimal | None,
        ]
    ] = []
    for source_location in source_locations:
        distance_km = _quantized_distance(
            location_reference.latitude,
            location_reference.longitude,
            source_location.latitude,
            source_location.longitude,
        )
        if distance_km > config.rules.mapping.maximum_mapping_distance_km:
            continue
        location_type_priority = config.rules.mapping.location_type_priorities[
            source_location.location_type
        ]
        provider_priority = config.rules.mapping.provider_priorities.get(
            source_location.provider_code,
            max(config.rules.mapping.provider_priorities.values()) + 1,
        )
        altitude_difference_m = _source_location_altitude_difference(
            location_reference.altitude_m,
            source_location.altitude_m,
        )
        mapping_score = _mapping_score(
            distance_km=distance_km,
            altitude_difference_m=altitude_difference_m,
            provider_priority=provider_priority,
            location_type_priority=location_type_priority,
            config=config,
        )
        mapping_method = (
            "nearest_station" if source_location.location_type == "station" else "nearest_grid"
        )
        candidates.append(
            (
                mapping_score,
                distance_km,
                provider_priority,
                source_location.external_location_id,
                source_location.id,
                source_location,
                mapping_method,
                altitude_difference_m,
            )
        )

    if not candidates:
        return WeatherMappingResult(
            status="unavailable",
            mapping_id=None,
            location_reference_id=location_reference_id,
            weather_source_location_id=None,
            mapping_method=None,
            distance_km=None,
            altitude_difference_m=None,
            mapping_score=None,
            confidence_level=None,
            mapping_version=config.rules.features.version,
            config_hash=config.config_hash,
            provider_code=None,
            external_location_id=None,
            warnings=("mapping_unavailable",),
            reproducibility_snapshot={},
        )

    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
    score, distance_km, _, _, _, source_location, mapping_method, altitude_difference_m = (
        candidates[0]
    )
    confidence = _mapping_confidence(score, config)
    row_hash = _mapping_row_hash(
        location_reference_id=location_reference.id,
        weather_source_location_id=source_location.id,
        mapping_method=mapping_method,
        mapping_version=config.rules.features.version,
        config_hash=config.config_hash,
        available_at=as_of_date,
        valid_from=as_of_date,
        valid_to=None,
    )
    mapping = await get_location_weather_mapping_by_row_hash(session, row_hash=row_hash)
    if mapping is None and persist:
        try:
            mapping = await create_location_weather_mapping(
                session,
                record=LocationWeatherMapping(
                    location_reference_id=location_reference.id,
                    weather_source_location_id=source_location.id,
                    mapping_method=mapping_method,
                    distance_km=distance_km,
                    altitude_difference_m=altitude_difference_m,
                    mapping_score=score,
                    confidence_level=confidence,
                    mapping_version=config.rules.features.version,
                    config_hash=config.config_hash,
                    available_at=as_of_date,
                    valid_from=as_of_date,
                    valid_to=None,
                    row_hash=row_hash,
                ),
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            mapping = await get_location_weather_mapping_by_row_hash(session, row_hash=row_hash)
            if mapping is None:
                raise

    return WeatherMappingResult(
        status="resolved",
        mapping_id=mapping.id if mapping is not None else None,
        location_reference_id=location_reference.id,
        weather_source_location_id=source_location.id,
        mapping_method=mapping_method,
        distance_km=distance_km,
        altitude_difference_m=altitude_difference_m,
        mapping_score=score,
        confidence_level=confidence,
        mapping_version=config.rules.features.version,
        config_hash=config.config_hash,
        provider_code=source_location.provider_code,
        external_location_id=source_location.external_location_id,
        warnings=(() if altitude_difference_m is not None else ("mapping_altitude_missing",)),
        reproducibility_snapshot={
            "mapping_id": mapping.id if mapping is not None else None,
            "row_hash": row_hash,
            "location_reference_id": location_reference.id,
            "weather_source_location_id": source_location.id,
            "provider_code": source_location.provider_code,
            "external_location_id": source_location.external_location_id,
            "mapping_method": mapping_method,
            "distance_km": distance_km,
            "altitude_difference_m": altitude_difference_m,
            "mapping_score": score,
            "confidence_level": confidence,
            "mapping_version": config.rules.features.version,
            "config_hash": config.config_hash,
        },
    )


async def get_effective_weather_observations(
    session: AsyncSession,
    *,
    weather_source_location_id: int,
    start_date: date,
    end_date: date,
    feature_date: date,
    as_of_date: date,
) -> list[WeatherSourceSelection]:
    rows = await list_visible_weather_observations(
        session,
        weather_source_location_id=weather_source_location_id,
        start_date=start_date,
        end_date=end_date,
        feature_date=feature_date,
        as_of_date=as_of_date,
    )
    return _select_visible_observation_per_day(rows)


def _plan_payload(plan: FarmSeasonVarietyPlan, season: Season, variety: Variety) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "plan_id": plan.id,
                "farm_id": plan.farm_id,
                "subfarm_id": plan.subfarm_id,
                "season_id": plan.season_id,
                "season_code": season.code,
                "variety_id": plan.variety_id,
                "variety_code": variety.code,
                "variety_name": variety.name,
                "version": plan.version,
                "effective_from": plan.effective_from,
                "effective_to": plan.effective_to,
                "available_at": plan.available_at,
            }
        ),
    )


async def _get_supporting_plan_dimensions(
    session: AsyncSession,
    *,
    plan: FarmSeasonVarietyPlan,
) -> tuple[Season, Variety]:
    season = await session.get(Season, plan.season_id)
    variety = await session.get(Variety, plan.variety_id)
    if season is None or variety is None:
        raise ValueError("plan master data not found")
    return season, variety


async def compute_weather_window_features(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
    as_of_date: date,
    feature_date: date,
    config: WeatherFeatureConfig,
    production_plan_config: ProductionPlanConfig,
    base_temperature_search_run_id: int | None,
    anchor_event: str | None,
    dry_run: bool,
) -> WeatherFeatureExecutionResult:
    plan_record = await get_effective_plan(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        season_id=season_id,
        variety_id=variety_id,
        as_of_date=as_of_date,
        config=production_plan_config,
    )
    plan_row = await get_plan_by_id(session, plan_id=plan_record.id)
    if plan_row is None:
        raise ValueError("effective production plan not found")
    season, variety = await _get_supporting_plan_dimensions(session, plan=plan_row)
    references = await find_location_reference_for_plan(
        session,
        farm_id=plan_row.farm_id,
        subfarm_id=plan_row.subfarm_id,
        as_of_date=as_of_date,
    )
    if len(references) != 1:
        raise WeatherMappingUnavailableError("location reference unavailable for plan")
    location_reference = references[0]
    mapping = await resolve_weather_mapping(
        session,
        location_reference_id=location_reference.id,
        as_of_date=as_of_date,
        config=config,
        persist=not dry_run,
    )
    if mapping.status != "resolved" or mapping.weather_source_location_id is None:
        blockers = tuple(mapping.warnings or ("mapping_unavailable",))
        result = WeatherFeatureExecutionResult(
            status="unavailable",
            run_id=None,
            source_signature="",
            feature_version=config.rules.features.version,
            config_hash=config.config_hash,
            mapping=cast(dict[str, Any], canonical_json_value(asdict(mapping))),
            weather_source_version="unavailable",
            plan=_plan_payload(plan_row, season, variety),
            windows=(),
            timeline=_build_phenology_timeline(
                plan=plan_row,
                feature_date=feature_date,
                mapping_id=None,
                feature_version=config.rules.features.version,
                anchor_event=anchor_event,
                base_temperature=None,
                observations_by_date={},
            ),
            weather_observation_ids=(),
            warnings=(),
            blockers=blockers,
            input_snapshot={"as_of_date": as_of_date, "feature_date": feature_date},
        )
        return result

    mapping_payload = cast(dict[str, Any], canonical_json_value(asdict(mapping)))
    mapping_row_hash = cast(str | None, mapping.reproducibility_snapshot.get("row_hash"))
    if mapping_row_hash is None:
        raise WeatherMappingConflictError("mapping row hash unavailable for feature signature")
    base_temperature_run = None
    base_temperature: Decimal | None = None
    base_temperature_blockers: list[str] = []
    if base_temperature_search_run_id is not None:
        base_temperature_run = await get_base_temperature_search_run(
            session,
            run_id=base_temperature_search_run_id,
        )
        if base_temperature_run is None:
            raise BaseTemperatureSearchUnavailableError("base temperature search run unavailable")
        _validate_base_temperature_search_run(
            run=base_temperature_run,
            variety_id=variety_id,
            climate_zone_id=location_reference.climate_zone_id,
            config=config,
        )
        base_temperature = base_temperature_run.selected_base_temperature
        if anchor_event is None:
            anchor_event = base_temperature_run.anchor_event
    else:
        base_temperature_blockers.append("base_temperature_search_required")

    source_location = await get_weather_source_location(
        session,
        weather_source_location_id=mapping.weather_source_location_id,
    )
    if source_location is None:
        raise WeatherMappingUnavailableError("mapped weather source location not found")

    earliest_window_start = _window_start(
        feature_date,
        max(config.rules.features.rolling_windows),
    )
    timeline_anchor = _event_date(plan_row, anchor_event) if anchor_event is not None else None
    observation_start = (
        min(earliest_window_start, timeline_anchor)
        if timeline_anchor is not None and timeline_anchor <= feature_date
        else earliest_window_start
    )
    selections = await get_effective_weather_observations(
        session,
        weather_source_location_id=source_location.id,
        start_date=observation_start,
        end_date=feature_date,
        feature_date=feature_date,
        as_of_date=as_of_date,
    )
    observations_by_date = {item.observation_date: item for item in selections}
    observation_fingerprint = _selected_observation_fingerprint(selections)
    windows = tuple(
        _window_feature_from_observations(
            observations_by_date=observations_by_date,
            feature_date=feature_date,
            window_days=window_days,
            base_temperature=base_temperature,
            config=config,
        )
        for window_days in config.rules.features.rolling_windows
    )
    blockers = tuple(
        base_temperature_blockers
        + [
            f"insufficient_weather_coverage_{item.window_days}d"
            for item in windows
            if item.status != "available"
        ]
    )
    timeline = _build_phenology_timeline(
        plan=plan_row,
        feature_date=feature_date,
        mapping_id=mapping.mapping_id,
        feature_version=config.rules.features.version,
        anchor_event=anchor_event,
        base_temperature=base_temperature,
        observations_by_date=observations_by_date,
    )
    source_signature = _feature_source_signature(
        plan_id=plan_row.id,
        plan_version=plan_row.version,
        as_of_date=as_of_date,
        feature_date=feature_date,
        mapping_row_hash=mapping_row_hash,
        base_temperature_search_run_id=base_temperature_search_run_id,
        base_temperature_search_source_signature=(
            None if base_temperature_run is None else base_temperature_run.source_signature
        ),
        selected_base_temperature=base_temperature,
        config_hash=config.config_hash,
        feature_version=config.rules.features.version,
        weather_observation_fingerprint=observation_fingerprint,
    )
    if not dry_run:
        existing = await find_existing_weather_feature_run(
            session,
            source_signature=source_signature,
        )
        if existing is not None:
            payload = existing.window_features
            timeline_payload = existing.timeline_payload
            timeline_result = _rehydrate_timeline(timeline_payload)
            return WeatherFeatureExecutionResult(
                status="skipped",
                run_id=existing.id,
                source_signature=source_signature,
                feature_version=existing.feature_version,
                config_hash=existing.config_hash,
                mapping=mapping_payload,
                weather_source_version=existing.weather_source_version,
                plan=_plan_payload(plan_row, season, variety),
                windows=tuple(
                    _rehydrate_window_feature(item)
                    for item in cast(list[dict[str, Any]], payload["windows"])
                ),
                timeline=timeline_result,
                weather_observation_ids=tuple(existing.weather_observation_ids),
                warnings=tuple(existing.warnings),
                blockers=tuple(existing.blockers),
                input_snapshot=existing.input_snapshot,
            )

    status: Literal["completed", "unavailable", "dry_run"] = (
        "unavailable" if blockers else ("dry_run" if dry_run else "completed")
    )
    result = WeatherFeatureExecutionResult(
        status=status,
        run_id=None,
        source_signature=source_signature,
        feature_version=config.rules.features.version,
        config_hash=config.config_hash,
        mapping=mapping_payload,
        weather_source_version=source_location.source_version,
        plan=_plan_payload(plan_row, season, variety),
        windows=windows,
        timeline=timeline,
        weather_observation_ids=tuple(item.observation_id for item in selections),
        warnings=tuple(mapping.warnings + timeline.warnings),
        blockers=blockers,
        input_snapshot=cast(
            dict[str, Any],
            canonical_json_value(
                {
                    "farm_id": farm_id,
                    "subfarm_id": subfarm_id,
                    "season_id": season_id,
                    "variety_id": variety_id,
                    "plan_id": plan_row.id,
                    "as_of_date": as_of_date,
                    "feature_date": feature_date,
                    "location_reference_id": location_reference.id,
                    "weather_source_location_id": source_location.id,
                    "base_temperature_search_run": (
                        None
                        if base_temperature_run is None
                        else _search_run_snapshot(base_temperature_run)
                    ),
                    "base_temperature_search_run_id": base_temperature_search_run_id,
                    "base_temperature": base_temperature,
                    "anchor_event": anchor_event,
                    "mapping": mapping_payload,
                    "plan": _plan_payload(plan_row, season, variety),
                    "weather_observation_fingerprint": observation_fingerprint,
                }
            ),
        ),
    )
    if dry_run:
        return result

    run = await create_weather_feature_run(
        session,
        payload={
            "feature_version": config.rules.features.version,
            "config_hash": config.config_hash,
            "mapping_version": mapping.mapping_version,
            "weather_source_version": source_location.source_version,
            "base_temperature_search_run_id": base_temperature_search_run_id,
            "plan_id": plan_row.id,
            "location_reference_id": location_reference.id,
            "location_weather_mapping_id": cast(int, mapping.mapping_id),
            "weather_source_location_id": source_location.id,
            "as_of_date": as_of_date,
            "feature_date": feature_date,
            "source_signature": source_signature,
            "status": "running",
            "input_snapshot": result.input_snapshot,
            "window_features": {},
            "timeline_payload": {},
            "weather_observation_ids": [],
            "warnings": [],
            "blockers": [],
        },
    )
    try:
        await update_weather_feature_run(
            session,
            run_id=run.id,
            values={
                "status": status,
                "window_features": {"windows": [asdict(item) for item in windows]},
                "timeline_payload": asdict(timeline),
                "weather_observation_ids": list(result.weather_observation_ids),
                "warnings": list(result.warnings),
                "blockers": list(result.blockers),
                "finished_at": _now(),
                "error_message": None,
            },
        )
    except Exception as exc:
        await update_weather_feature_run(
            session,
            run_id=run.id,
            values={
                "status": "failed",
                "finished_at": _now(),
                "error_message": _sanitize_error_message(str(exc)),
            },
        )
        raise

    return replace(result, run_id=run.id)


def _training_sample_payload(sample: BaseTemperatureTrainingSample) -> dict[str, Any]:
    return {
        "plan_id": sample.plan_id,
        "anchor_event": sample.anchor_event,
        "target_event": sample.target_event,
        "sample_weight": canonical_decimal_string(sample.sample_weight),
        "include": sample.include,
        "exclusion_reason": sample.exclusion_reason,
    }


def _search_run_snapshot(run: BaseTemperatureSearchRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "source_signature": run.source_signature,
        "selected_base_temperature": run.selected_base_temperature,
        "config_hash": run.config_hash,
        "feature_version": run.feature_version,
        "scope_type": run.scope_type,
        "variety_id": run.variety_id,
        "climate_zone_id": run.climate_zone_id,
        "anchor_event": run.anchor_event,
        "target_event": run.target_event,
        "status": run.status,
    }


def _validate_base_temperature_search_run(
    *,
    run: BaseTemperatureSearchRun,
    variety_id: int,
    climate_zone_id: int | None,
    config: WeatherFeatureConfig,
) -> None:
    if run.status != "completed":
        raise BaseTemperatureSearchUnavailableError(
            f"base temperature search run is not completed: {run.status}"
        )
    if run.selected_base_temperature is None:
        raise BaseTemperatureSearchUnavailableError(
            "base temperature search run did not select a base temperature"
        )
    if run.feature_version != config.rules.features.version:
        raise BaseTemperatureSearchUnavailableError(
            "base temperature search run feature_version is incompatible"
        )
    if run.config_hash != config.config_hash:
        raise BaseTemperatureSearchUnavailableError(
            "base temperature search run config_hash is incompatible"
        )
    if run.variety_id != variety_id:
        raise BaseTemperatureSearchUnavailableError(
            "base temperature search run variety scope does not match"
        )
    if run.climate_zone_id != climate_zone_id:
        raise BaseTemperatureSearchUnavailableError(
            "base temperature search run climate-zone scope does not match"
        )


def _weighted_median(values: list[Decimal], weights: list[Decimal]) -> Decimal:
    from backend.app.planning.quantiles import weighted_quantile

    return weighted_quantile(values, weights, Decimal("0.50"))


async def search_base_temperature(
    session: AsyncSession,
    *,
    training_cutoff: date,
    samples: list[BaseTemperatureTrainingSample],
    config: WeatherFeatureConfig,
    variety_id: int | None,
    climate_zone_id: int | None,
    scope_type: str,
    dry_run: bool,
) -> BaseTemperatureSearchExecutionResult:
    eligible_samples: list[dict[str, Any]] = []
    training_manifest: list[dict[str, Any]] = []
    blockers: list[str] = []
    for sample in samples:
        manifest_row: dict[str, Any] = {
            "plan_id": sample.plan_id,
            "anchor_event": sample.anchor_event,
            "target_event": sample.target_event,
            "sample_weight": sample.sample_weight,
            "include": sample.include,
            "exclusion_reason": sample.exclusion_reason,
        }
        if not sample.include:
            manifest_row["status"] = "excluded"
            manifest_row["resolved_exclusion_reason"] = sample.exclusion_reason or "input_excluded"
            training_manifest.append(manifest_row)
            continue
        plan = await get_plan_by_id(session, plan_id=sample.plan_id)
        if plan is None:
            manifest_row["status"] = "invalid"
            manifest_row["resolved_exclusion_reason"] = "plan_not_found"
            training_manifest.append(manifest_row)
            continue
        manifest_row["plan_version"] = plan.version
        manifest_row["available_at"] = plan.available_at
        if plan.available_at > training_cutoff:
            manifest_row["status"] = "excluded"
            manifest_row["resolved_exclusion_reason"] = "plan_not_available_at_cutoff"
            training_manifest.append(manifest_row)
            continue
        anchor_date = _event_date(plan, sample.anchor_event)
        target_date = _event_date(plan, sample.target_event)
        manifest_row["anchor_date"] = anchor_date
        manifest_row["target_date"] = target_date
        if anchor_date is None or target_date is None or target_date < anchor_date:
            manifest_row["status"] = "invalid"
            manifest_row["resolved_exclusion_reason"] = "invalid_anchor_target_dates"
            training_manifest.append(manifest_row)
            continue
        season, _ = await _get_supporting_plan_dimensions(session, plan=plan)
        manifest_row["season_id"] = season.id
        manifest_row["season_code"] = season.code
        references = await find_location_reference_for_plan(
            session,
            farm_id=plan.farm_id,
            subfarm_id=plan.subfarm_id,
            as_of_date=training_cutoff,
        )
        if len(references) != 1:
            manifest_row["status"] = "excluded"
            manifest_row["resolved_exclusion_reason"] = "location_reference_unavailable"
            training_manifest.append(manifest_row)
            continue
        mapping = await resolve_weather_mapping(
            session,
            location_reference_id=references[0].id,
            as_of_date=training_cutoff,
            config=config,
            persist=not dry_run,
        )
        if mapping.status != "resolved" or mapping.weather_source_location_id is None:
            manifest_row["status"] = "excluded"
            manifest_row["resolved_exclusion_reason"] = "mapping_unavailable"
            manifest_row["mapping"] = canonical_json_value(asdict(mapping))
            training_manifest.append(manifest_row)
            continue
        mapping_row_hash = cast(str | None, mapping.reproducibility_snapshot.get("row_hash"))
        if mapping_row_hash is None:
            raise WeatherMappingConflictError(
                "mapping row hash unavailable for base temperature search"
            )
        observations = await get_effective_weather_observations(
            session,
            weather_source_location_id=mapping.weather_source_location_id,
            start_date=anchor_date,
            end_date=season.end_date,
            feature_date=season.end_date,
            as_of_date=training_cutoff,
        )
        observations_by_date = {item.observation_date: item for item in observations}
        target_expected_dates = _daterange(anchor_date, target_date)
        missing_target_dates = [
            day for day in target_expected_dates if day not in observations_by_date
        ]
        observation_fingerprint = _selected_observation_fingerprint(observations)
        manifest_row["mapping"] = {
            "mapping_id": mapping.mapping_id,
            "location_reference_id": references[0].id,
            "weather_source_location_id": mapping.weather_source_location_id,
            "row_hash": mapping_row_hash,
            "mapping_method": mapping.mapping_method,
            "mapping_version": mapping.mapping_version,
        }
        manifest_row["weather_observation_fingerprint"] = observation_fingerprint
        manifest_row["season_end_date"] = season.end_date
        if missing_target_dates:
            manifest_row["status"] = "excluded"
            manifest_row["resolved_exclusion_reason"] = "training_weather_incomplete"
            manifest_row["missing_target_dates"] = missing_target_dates
            training_manifest.append(manifest_row)
            continue
        manifest_row["status"] = "included"
        manifest_row["resolved_exclusion_reason"] = None
        training_manifest.append(manifest_row)
        eligible_samples.append(
            {
                "plan_id": plan.id,
                "plan_version": plan.version,
                "season_id": plan.season_id,
                "season_code": season.code,
                "anchor_event": sample.anchor_event,
                "target_event": sample.target_event,
                "anchor_date": anchor_date,
                "target_date": target_date,
                "sample_weight": sample.sample_weight,
                "observations": observations_by_date,
                "season_end_date": season.end_date,
                "mapping_row_hash": mapping_row_hash,
                "location_reference_id": references[0].id,
                "weather_source_location_id": mapping.weather_source_location_id,
                "weather_observation_fingerprint": observation_fingerprint,
            }
        )

    training_manifest.sort(
        key=lambda item: (
            cast(int, item.get("plan_id", 0)),
            cast(str, item.get("anchor_event", "")),
            cast(str, item.get("target_event", "")),
            cast(str, item.get("status", "")),
            canonical_decimal_string(cast(Decimal, item.get("sample_weight", Decimal("0")))),
            cast(str, item.get("resolved_exclusion_reason", "") or ""),
        )
    )
    source_signature = _base_temperature_source_signature(
        training_cutoff=training_cutoff,
        scope_type=scope_type,
        variety_id=variety_id,
        climate_zone_id=climate_zone_id,
        config_hash=config.config_hash,
        feature_version=config.rules.features.version,
        candidate_temperatures=config.rules.search.base_temperature_candidates,
        training_manifest=training_manifest,
    )
    if not dry_run:
        existing = await find_existing_base_temperature_search_run(
            session,
            source_signature=source_signature,
        )
        if existing is not None:
            return BaseTemperatureSearchExecutionResult(
                status="skipped",
                run_id=existing.id,
                source_signature=existing.source_signature,
                config_hash=existing.config_hash,
                feature_version=existing.feature_version,
                selected_base_temperature=existing.selected_base_temperature,
                scoring_method=existing.scoring_method,
                selected_score=existing.selected_score,
                sample_count=existing.sample_count,
                distinct_season_count=existing.distinct_season_count,
                candidate_scores=tuple(
                    _rehydrate_candidate_score(item)
                    for item in cast(
                        list[dict[str, Any]],
                        existing.candidate_scores.get("candidates", []),
                    )
                ),
                warnings=tuple(existing.warnings),
                blockers=tuple(existing.blockers),
                input_snapshot=existing.input_snapshot,
                error_message=existing.error_message,
            )

    distinct_season_count = len({item["season_code"] for item in eligible_samples})
    input_snapshot = cast(
        dict[str, Any],
        canonical_json_value(
            {
                "training_cutoff": training_cutoff,
                "scope_type": scope_type,
                "variety_id": variety_id,
                "climate_zone_id": climate_zone_id,
                "candidate_temperatures": list(config.rules.search.base_temperature_candidates),
                "samples": training_manifest,
            }
        ),
    )
    if (
        len(eligible_samples) < config.rules.search.minimum_training_sample_count
        or distinct_season_count < config.rules.search.minimum_distinct_season_count
    ):
        blockers.append("insufficient_training_data")
        result = BaseTemperatureSearchExecutionResult(
            status="unavailable" if not dry_run else "dry_run",
            run_id=None,
            source_signature=source_signature,
            config_hash=config.config_hash,
            feature_version=config.rules.features.version,
            selected_base_temperature=None,
            scoring_method=config.rules.search.scoring_method,
            selected_score=None,
            sample_count=len(eligible_samples),
            distinct_season_count=distinct_season_count,
            candidate_scores=(),
            warnings=(),
            blockers=tuple(blockers),
            input_snapshot=input_snapshot,
        )
        if not dry_run:
            included_plan_ids = sorted(item["plan_id"] for item in eligible_samples)
            run = await create_base_temperature_search_run(
                session,
                payload={
                    "scope_type": scope_type,
                    "variety_id": variety_id,
                    "climate_zone_id": climate_zone_id,
                    "training_cutoff": training_cutoff,
                    "anchor_event": samples[0].anchor_event if samples else "",
                    "target_event": samples[0].target_event if samples else "",
                    "candidate_temperatures": [
                        canonical_decimal_string(item)
                        for item in config.rules.search.base_temperature_candidates
                    ],
                    "selected_base_temperature": None,
                    "scoring_method": config.rules.search.scoring_method,
                    "selected_score": None,
                    "sample_count": len(eligible_samples),
                    "distinct_season_count": distinct_season_count,
                    "training_sample_ids": included_plan_ids,
                    "candidate_scores": _candidate_scores_payload(()),
                    "config_hash": config.config_hash,
                    "feature_version": config.rules.features.version,
                    "source_signature": source_signature,
                    "status": "unavailable",
                    "warnings": [],
                    "blockers": blockers,
                    "input_snapshot": result.input_snapshot,
                    "finished_at": _now(),
                    "error_message": None,
                },
            )
            return replace(result, run_id=run.id)
        return result

    candidate_scores: list[BaseTemperatureCandidateScore] = []
    for candidate_base_temperature in config.rules.search.base_temperature_candidates:
        fold_errors: list[Decimal] = []
        evaluated_count = 0
        for validation_season in sorted({item["season_code"] for item in eligible_samples}):
            training_rows = [
                item for item in eligible_samples if item["season_code"] != validation_season
            ]
            validation_rows = [
                item for item in eligible_samples if item["season_code"] == validation_season
            ]
            if not training_rows or not validation_rows:
                continue
            training_thresholds = []
            training_weights = []
            for row in training_rows:
                cumulative = Decimal("0")
                for day in _daterange(
                    cast(date, row["anchor_date"]),
                    cast(date, row["target_date"]),
                ):
                    observation = cast(dict[date, WeatherSourceSelection], row["observations"])[day]
                    cumulative += max(
                        observation.temperature_mean_c - candidate_base_temperature,
                        Decimal("0"),
                    )
                training_thresholds.append(cumulative)
                training_weights.append(cast(Decimal, row["sample_weight"]))
            threshold = _weighted_median(training_thresholds, training_weights)
            for row in validation_rows:
                cumulative = Decimal("0")
                predicted_date: date | None = None
                observation_map = cast(
                    dict[date, WeatherSourceSelection],
                    row["observations"],
                )
                for day in _daterange(
                    cast(date, row["anchor_date"]),
                    cast(date, row["season_end_date"]),
                ):
                    selected_observation = observation_map.get(day)
                    if selected_observation is None:
                        continue
                    cumulative += max(
                        selected_observation.temperature_mean_c - candidate_base_temperature,
                        Decimal("0"),
                    )
                    if cumulative >= threshold:
                        predicted_date = day
                        break
                if predicted_date is None:
                    continue
                actual_target = cast(date, row["target_date"])
                fold_errors.append(Decimal(abs((predicted_date - actual_target).days)))
                evaluated_count += 1
        mae_days = (
            (sum(fold_errors, Decimal("0")) / Decimal(len(fold_errors))).quantize(
                Decimal("0.000001")
            )
            if fold_errors
            else None
        )
        candidate_scores.append(
            BaseTemperatureCandidateScore(
                base_temperature=candidate_base_temperature,
                fold_count=distinct_season_count,
                evaluated_sample_count=evaluated_count,
                mae_days=mae_days,
            )
        )

    available_scores = [item for item in candidate_scores if item.mae_days is not None]
    if not available_scores:
        raise BaseTemperatureSearchUnavailableError(
            "no base temperature candidates produced a score"
        )
    available_scores.sort(key=lambda item: (cast(Decimal, item.mae_days), item.base_temperature))
    winner = available_scores[0]

    result = BaseTemperatureSearchExecutionResult(
        status="dry_run" if dry_run else "completed",
        run_id=None,
        source_signature=source_signature,
        config_hash=config.config_hash,
        feature_version=config.rules.features.version,
        selected_base_temperature=winner.base_temperature,
        scoring_method=config.rules.search.scoring_method,
        selected_score=winner.mae_days,
        sample_count=len(eligible_samples),
        distinct_season_count=distinct_season_count,
        candidate_scores=tuple(candidate_scores),
        warnings=(),
        blockers=(),
        input_snapshot=input_snapshot,
    )
    if dry_run:
        return result

    included_plan_ids = sorted(item["plan_id"] for item in eligible_samples)
    run = await create_base_temperature_search_run(
        session,
        payload={
            "scope_type": scope_type,
            "variety_id": variety_id,
            "climate_zone_id": climate_zone_id,
            "training_cutoff": training_cutoff,
            "anchor_event": samples[0].anchor_event if samples else "",
            "target_event": samples[0].target_event if samples else "",
            "candidate_temperatures": [
                canonical_decimal_string(item)
                for item in config.rules.search.base_temperature_candidates
            ],
            "selected_base_temperature": winner.base_temperature,
            "scoring_method": config.rules.search.scoring_method,
            "selected_score": winner.mae_days,
            "sample_count": len(eligible_samples),
            "distinct_season_count": distinct_season_count,
            "training_sample_ids": included_plan_ids,
            "candidate_scores": _candidate_scores_payload(candidate_scores),
            "config_hash": config.config_hash,
            "feature_version": config.rules.features.version,
            "source_signature": source_signature,
            "status": "completed",
            "warnings": [],
            "blockers": [],
            "input_snapshot": input_snapshot,
            "finished_at": _now(),
            "error_message": None,
        },
    )
    return replace(result, run_id=run.id)


async def load_base_temperature_search_result(
    session: AsyncSession,
    *,
    run_id: int,
) -> BaseTemperatureSearchExecutionResult:
    run = await get_base_temperature_search_run(session, run_id=run_id)
    if run is None:
        raise ValueError("base temperature search run not found")
    return _base_temperature_result_from_run(run)


async def load_weather_feature_result(
    session: AsyncSession,
    *,
    run_id: int,
) -> WeatherFeatureExecutionResult:
    run = await get_weather_feature_run(session, run_id=run_id)
    if run is None:
        raise ValueError("weather feature run not found")
    return _weather_feature_result_from_run(run)


async def build_phenology_timeline(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
    as_of_date: date,
    feature_date: date,
    config: WeatherFeatureConfig,
    production_plan_config: ProductionPlanConfig,
    base_temperature_search_run_id: int | None,
    anchor_event: str | None,
) -> PhenologyTimeline:
    result = await compute_weather_window_features(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        season_id=season_id,
        variety_id=variety_id,
        as_of_date=as_of_date,
        feature_date=feature_date,
        config=config,
        production_plan_config=production_plan_config,
        base_temperature_search_run_id=base_temperature_search_run_id,
        anchor_event=anchor_event,
        dry_run=True,
    )
    return result.timeline


async def get_weather_history(
    session: AsyncSession,
    *,
    location_reference_id: int,
    as_of_date: date,
    start_date: date,
    end_date: date,
    config: WeatherFeatureConfig,
) -> dict[str, Any]:
    mapping = await resolve_weather_mapping(
        session,
        location_reference_id=location_reference_id,
        as_of_date=as_of_date,
        config=config,
        persist=False,
    )
    if mapping.status != "resolved" or mapping.weather_source_location_id is None:
        raise WeatherMappingUnavailableError("weather mapping unavailable")
    observations = await get_effective_weather_observations(
        session,
        weather_source_location_id=mapping.weather_source_location_id,
        start_date=start_date,
        end_date=end_date,
        feature_date=end_date,
        as_of_date=as_of_date,
    )
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "mapping": asdict(mapping),
                "observations": [asdict(item) for item in observations],
                "as_of_date": as_of_date,
                "start_date": start_date,
                "end_date": end_date,
            }
        ),
    )


async def list_weather_source_locations(
    session: AsyncSession,
    *,
    as_of_date: date,
    provider_code: str | None,
) -> dict[str, Any]:
    rows = await list_visible_weather_source_locations(
        session,
        as_of_date=as_of_date,
        provider_code=provider_code,
    )
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "as_of_date": as_of_date,
                "provider_code": provider_code,
                "items": [
                    {
                        "id": row.id,
                        "provider_code": row.provider_code,
                        "external_location_id": row.external_location_id,
                        "location_type": row.location_type,
                        "name": row.name,
                        "latitude": row.latitude,
                        "longitude": row.longitude,
                        "altitude_m": row.altitude_m,
                        "timezone_name": row.timezone_name,
                        "grid_resolution": row.grid_resolution,
                        "source_version": row.source_version,
                        "valid_from": row.valid_from,
                        "valid_to": row.valid_to,
                        "row_hash": row.row_hash,
                    }
                    for row in rows
                ],
            }
        ),
    )
