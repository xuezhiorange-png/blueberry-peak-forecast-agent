from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.maturity.calibration import calibration_payload
from backend.app.maturity.config import MaturityCurveConfig
from backend.app.maturity.features import analysis_dates, date_range, smooth_series
from backend.app.maturity.model import blend_curves, fit_shared_curve, reconcile_p50_mass
from backend.app.maturity.repository import (
    create_maturity_daily_predictions,
    create_maturity_forecast_run,
    create_maturity_model_artifact,
    create_maturity_model_run,
    find_existing_maturity_forecast_run,
    find_existing_maturity_model_run,
    get_maturity_forecast_run,
    get_maturity_model_artifact_by_run_id,
    get_maturity_model_run,
    list_maturity_daily_predictions,
)
from backend.app.maturity.schemas import (
    GroupCurveArtifact,
    MaturityDailyPrediction,
    MaturityForecastExecutionResult,
    MaturityManifestRow,
    MaturityModelExecutionResult,
    PersistedMaturityRunStatus,
    ResolvedTrainingSample,
    ShiftModelArtifact,
)
from backend.app.models.analytics import AnalyticsBuildRun, FactReceiptDaily
from backend.app.models.master_data import Holiday, Season
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.models.planning import LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.weather import BaseTemperatureSearchRun
from backend.app.planning.json_types import canonical_decimal_string, canonical_json_value
from backend.app.planning.plan_config import load_production_plan_config
from backend.app.planning.plan_service import get_effective_plan
from backend.app.weather.config import WeatherFeatureConfig, load_weather_feature_config
from backend.app.weather.hashing import sha256_payload
from backend.app.weather.repository import (
    find_location_reference_for_plan,
    get_base_temperature_search_run,
)
from backend.app.weather.service import (
    _selected_observation_fingerprint,
    get_effective_weather_observations,
    resolve_weather_mapping,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], canonical_json_value(payload))


def _decimal_value(value: Decimal | int | float | str | None, *, field: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field} is required")
    if isinstance(value, Decimal):
        parsed = value
    else:
        try:
            parsed = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{field} must be a valid decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _optional_decimal_value(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    return _decimal_value(value, field="decimal")


def _run_status_value(status: str) -> PersistedMaturityRunStatus:
    if status in {"running", "completed", "failed", "unavailable"}:
        return cast(PersistedMaturityRunStatus, status)
    raise ValueError(f"unsupported persisted run status: {status}")


def _model_run_status_value(status: str) -> PersistedMaturityRunStatus:
    return _run_status_value(status)


def _sorted_manifest_rows(
    manifest_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        manifest_rows,
        key=lambda item: (
            cast(int, item.get("season_id", 0)),
            cast(int, item.get("production_plan_id", 0)),
            cast(str, item.get("farm_key", "")),
            cast(str, item.get("subfarm_key", "")),
            cast(int, item.get("variety_id", 0)),
            cast(str, item.get("anchor_event", "")),
            cast(str, item.get("facility_type", "")),
            bool(item.get("include", False)),
            canonical_decimal_string(
                _decimal_value(item.get("sample_weight", Decimal("0")), field="sample_weight")
            ),
            cast(str, item.get("exclusion_reason", "") or ""),
        ),
    )


def _training_source_signature(
    *,
    manifest_rows: list[dict[str, Any]],
    training_cutoff: date,
    config_hash: str,
    model_version: str,
    random_seed: int,
) -> str:
    return sha256_payload(
        {
            "manifest_rows": _sorted_manifest_rows(
                cast(list[dict[str, Any]], canonical_json_value(manifest_rows))
            ),
            "training_cutoff": training_cutoff,
            "config_hash": config_hash,
            "model_version": model_version,
            "random_seed": random_seed,
        }
    )


def _forecast_source_signature(
    *,
    plan_id: int,
    plan_version: int,
    mapping_row_hash: str,
    base_temperature_search_run_id: int | None,
    base_temperature_source_signature: str | None,
    selected_base_temperature: Decimal | None,
    artifact_hash: str,
    config_hash: str,
    model_version: str,
    as_of_date: date,
    prediction_start_date: date,
    prediction_end_date: date,
    observation_fingerprint: list[dict[str, Any]],
) -> str:
    return sha256_payload(
        {
            "plan_id": plan_id,
            "plan_version": plan_version,
            "mapping_row_hash": mapping_row_hash,
            "base_temperature_search_run_id": base_temperature_search_run_id,
            "base_temperature_source_signature": base_temperature_source_signature,
            "selected_base_temperature": selected_base_temperature,
            "artifact_hash": artifact_hash,
            "config_hash": config_hash,
            "model_version": model_version,
            "as_of_date": as_of_date,
            "prediction_start_date": prediction_start_date,
            "prediction_end_date": prediction_end_date,
            "observation_fingerprint": observation_fingerprint,
        }
    )


def _artifact_hash(payload: dict[str, Any]) -> str:
    return sha256_payload(cast(dict[str, Any], canonical_json_value(payload)))


def _support_days(config: MaturityCurveConfig) -> tuple[int, ...]:
    return tuple(
        range(
            config.rules.curve.support_min_day,
            config.rules.curve.support_max_day + 1,
        )
    )


async def _season(session: AsyncSession, season_id: int) -> Season:
    season = await session.get(Season, season_id)
    if season is None:
        raise ValueError("season not found")
    return season


async def _location_reference(
    session: AsyncSession,
    *,
    location_reference_id: int,
    as_of_date: date,
) -> LocationReference:
    reference = await session.get(LocationReference, location_reference_id)
    if reference is None:
        raise ValueError("location reference not found")
    if reference.valid_from > as_of_date or (
        reference.valid_to is not None and reference.valid_to < as_of_date
    ):
        raise ValueError("location reference not valid for as_of_date")
    if reference.climate_zone_id is None:
        raise ValueError("location reference missing climate zone")
    return reference


async def _base_temperature_run(
    session: AsyncSession,
    *,
    run_id: int,
    variety_id: int,
    climate_zone_id: int,
) -> BaseTemperatureSearchRun:
    run = await get_base_temperature_search_run(session, run_id=run_id)
    if run is None:
        raise ValueError("base temperature search run not found")
    if run.status != "completed":
        raise ValueError("base temperature search run must be completed")
    if run.selected_base_temperature is None:
        raise ValueError("base temperature search run missing selected base temperature")
    if run.variety_id != variety_id:
        raise ValueError("base temperature search run variety mismatch")
    if run.climate_zone_id != climate_zone_id:
        raise ValueError("base temperature search run climate zone mismatch")
    return run


async def _holiday_dates(
    session: AsyncSession,
    *,
    season_id: int,
    codes: tuple[str, ...],
) -> set[date]:
    statement = select(Holiday).where(
        Holiday.season_id == season_id,
        Holiday.code.in_(codes),
        Holiday.active.is_(True),
    )
    dates: set[date] = set()
    rows = list((await session.scalars(statement)).all())
    for holiday in rows:
        dates.update(date_range(holiday.start_date, holiday.end_date))
    return dates


async def _resolve_training_sample(
    session: AsyncSession,
    *,
    row: MaturityManifestRow,
    training_cutoff: date,
    config: MaturityCurveConfig,
) -> tuple[dict[str, Any], ResolvedTrainingSample | None]:
    snapshot = cast(dict[str, Any], canonical_json_value(asdict(row)))
    if not row.include:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = row.exclusion_reason or "input_excluded"
        return snapshot, None

    plan = await session.get(FarmSeasonVarietyPlan, row.production_plan_id)
    if plan is None:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "plan_not_found"
        return snapshot, None
    if plan.available_at > training_cutoff:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "plan_not_available_at_cutoff"
        return snapshot, None
    season = await _season(session, row.season_id)
    if plan.season_id != row.season_id or plan.variety_id != row.variety_id:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "plan_manifest_mismatch"
        return snapshot, None
    reference = await _location_reference(
        session,
        location_reference_id=row.location_reference_id,
        as_of_date=training_cutoff,
    )
    base_temp_run = await _base_temperature_run(
        session,
        run_id=row.base_temperature_search_run_id,
        variety_id=row.variety_id,
        climate_zone_id=cast(int, reference.climate_zone_id),
    )
    anchor_date = getattr(plan, row.anchor_event, None)
    if not isinstance(anchor_date, date):
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "anchor_event_missing"
        return snapshot, None
    mapping = await resolve_weather_mapping(
        session,
        location_reference_id=reference.id,
        as_of_date=training_cutoff,
        config=load_dummy_weather_config(),
        persist=False,
    )
    if mapping.status != "resolved" or mapping.weather_source_location_id is None:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "mapping_unavailable"
        snapshot["mapping"] = cast(dict[str, Any], canonical_json_value(asdict(mapping)))
        return snapshot, None
    mapping_row_hash = cast(str | None, mapping.reproducibility_snapshot.get("row_hash"))
    if mapping_row_hash is None:
        raise ValueError("weather mapping row hash missing")
    observations = await get_effective_weather_observations(
        session,
        weather_source_location_id=mapping.weather_source_location_id,
        start_date=season.start_date,
        end_date=season.end_date,
        feature_date=season.end_date,
        as_of_date=training_cutoff,
    )
    observation_fingerprint = tuple(_selected_observation_fingerprint(observations))
    holiday_dates = await _holiday_dates(
        session,
        season_id=row.season_id,
        codes=config.rules.holidays.spring_festival_codes,
    )
    statement = (
        select(FactReceiptDaily)
        .where(
            FactReceiptDaily.build_run_id == row.analytics_build_run_id,
            FactReceiptDaily.season_id == row.season_id,
            FactReceiptDaily.farm_key == row.farm_key,
            FactReceiptDaily.subfarm_key == row.subfarm_key,
            FactReceiptDaily.variety_id == row.variety_id,
        )
        .order_by(FactReceiptDaily.receipt_date.asc())
    )
    daily_rows = list((await session.scalars(statement)).all())
    analytics_run = await session.get(AnalyticsBuildRun, row.analytics_build_run_id)
    if analytics_run is None:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "analytics_build_run_not_found"
        return snapshot, None
    date_series = analysis_dates(season)
    daily_weight_by_date = {entry.receipt_date: entry.weight_kg for entry in daily_rows}
    raw_weights = [daily_weight_by_date.get(day, Decimal("0")) for day in date_series]
    smoothed_weights = smooth_series(raw_weights)
    included_weights: list[Decimal] = []
    density_points: list[tuple[int, Decimal]] = []
    raw_day_count = len(date_series)
    downweighted_day_count = 0
    excluded_day_count = 0
    used_day_count = 0
    for day, smoothed in zip(date_series, smoothed_weights, strict=True):
        if day in holiday_dates and config.rules.holidays.exclude_from_loss:
            excluded_day_count += 1
            continue
        if day in holiday_dates and config.rules.holidays.disturbance_weight < Decimal("1"):
            downweighted_day_count += 1
        used_day_count += 1
        included_weights.append(smoothed)
    total_proxy_weight = sum(included_weights, Decimal("0"))
    if total_proxy_weight <= 0:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "empty_proxy_curve"
        return snapshot, None
    for day, smoothed in zip(date_series, smoothed_weights, strict=True):
        if day in holiday_dates and config.rules.holidays.exclude_from_loss:
            continue
        rel_day = (day - anchor_date).days
        if (
            rel_day < config.rules.curve.support_min_day
            or rel_day > config.rules.curve.support_max_day
        ):
            continue
        density_points.append(
            (rel_day, (smoothed / total_proxy_weight).quantize(Decimal("0.000001")))
        )
    expected_total = plan.expected_total_marketable_kg or (
        plan.planted_area_mu * plan.expected_yield_kg_per_mu * plan.marketable_rate
    )
    snapshot["status"] = "included"
    snapshot["resolved_exclusion_reason"] = None
    snapshot["plan_version"] = plan.version
    snapshot["season_code"] = season.code
    snapshot["anchor_date"] = anchor_date
    snapshot["mapping"] = cast(
        dict[str, Any],
        canonical_json_value(mapping.reproducibility_snapshot),
    )
    snapshot["weather_observation_fingerprint"] = cast(
        list[dict[str, Any]],
        canonical_json_value(list(observation_fingerprint)),
    )
    snapshot["holiday_summary"] = {
        "raw_day_count": raw_day_count,
        "used_day_count": used_day_count,
        "downweighted_day_count": downweighted_day_count,
        "excluded_day_count": excluded_day_count,
        "excluded_reason_codes": ["spring_festival"] if excluded_day_count else [],
    }
    pruning_offset = None
    if plan.pruning_date is not None:
        pruning_offset = Decimal((plan.pruning_date - season.start_date).days)
    flowering_peak_offset = None
    if plan.flowering_peak_date is not None:
        flowering_peak_offset = Decimal((plan.flowering_peak_date - season.start_date).days)
    first_pick_offset = None
    if plan.first_pick_date is not None:
        first_pick_offset = Decimal((plan.first_pick_date - season.start_date).days)
    resolved = ResolvedTrainingSample(
        manifest_row=row,
        season_code=season.code,
        season_end_date=season.end_date,
        climate_zone_id=cast(int, reference.climate_zone_id),
        province=reference.province or "",
        altitude_m=_optional_decimal_value(reference.altitude_m),
        tree_age_years=_optional_decimal_value(plan.tree_age_years),
        anchor_date=anchor_date,
        expected_total_kg=expected_total.quantize(Decimal("0.000001")),
        expected_total_source=(
            "explicit"
            if plan.expected_total_marketable_kg is not None
            else "derived_from_task6_plan"
        ),
        mapping_row_hash=mapping_row_hash,
        base_temperature_source_signature=base_temp_run.source_signature,
        selected_base_temperature=cast(Decimal, base_temp_run.selected_base_temperature),
        observation_fingerprint=observation_fingerprint,
        holiday_summary=snapshot["holiday_summary"],
        density_points=tuple(sorted(density_points, key=lambda item: item[0])),
        feature_values={
            "altitude_m": _optional_decimal_value(reference.altitude_m),
            "tree_age_years": _optional_decimal_value(plan.tree_age_years),
            "facility_type": row.facility_type,
            "pruning_offset_days": pruning_offset,
            "flowering_peak_offset_days": flowering_peak_offset,
            "first_pick_offset_days": first_pick_offset,
        },
    )
    return snapshot, resolved


def _quantized_decimal(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return min(max(value, lower), upper).quantize(Decimal("0.000001"))


def _shift_curve(
    *,
    density: tuple[Decimal, ...],
    support_days: tuple[int, ...],
    shift_days: Decimal,
) -> tuple[Decimal, ...]:
    x = np.asarray(support_days, dtype=float)
    y = np.asarray([float(item) for item in density], dtype=float)
    shifted = np.interp(x - float(shift_days), x, y, left=0.0, right=0.0)
    shifted = np.clip(shifted, 0.0, None)
    total = float(shifted.sum())
    if total <= 0:
        return tuple(Decimal("0") for _ in support_days)
    normalized = shifted / total
    return tuple(Decimal(f"{value:.6f}") for value in normalized.tolist())


def _build_group_curves(
    *,
    resolved_samples: list[ResolvedTrainingSample],
    config: MaturityCurveConfig,
) -> tuple[dict[str, GroupCurveArtifact], dict[str, Any]]:
    support_days = _support_days(config)
    grouped: dict[str, list[ResolvedTrainingSample]] = defaultdict(list)
    province_grouped: dict[str, list[ResolvedTrainingSample]] = defaultdict(list)
    variety_grouped: dict[str, list[ResolvedTrainingSample]] = defaultdict(list)
    for sample in resolved_samples:
        grouped[f"zone:{sample.climate_zone_id}|variety:{sample.manifest_row.variety_id}"].append(sample)
        province_grouped[f"province:{sample.province}|variety:{sample.manifest_row.variety_id}"].append(sample)
        variety_grouped[f"variety:{sample.manifest_row.variety_id}"].append(sample)

    def fit_for_samples(samples: list[ResolvedTrainingSample]) -> tuple[Decimal, ...]:
        point_map: dict[int, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for sample in samples:
            for rel_day, share in sample.density_points:
                point_map[rel_day].append((share, sample.manifest_row.sample_weight))
        rel_days: list[int] = []
        shares: list[Decimal] = []
        weights: list[Decimal] = []
        for rel_day in sorted(point_map):
            total_weight = sum((item[1] for item in point_map[rel_day]), Decimal("0"))
            weighted_share = sum(
                (item[0] * item[1] for item in point_map[rel_day]),
                Decimal("0"),
            ) / total_weight
            rel_days.append(rel_day)
            shares.append(weighted_share.quantize(Decimal("0.000001")))
            weights.append(total_weight.quantize(Decimal("0.000001")))
        return fit_shared_curve(
            relative_days=tuple(rel_days),
            shares=tuple(shares),
            sample_weights=tuple(weights),
            support_days=support_days,
            spline_degree=config.rules.curve.spline_degree,
            spline_knot_count=config.rules.curve.spline_knot_count,
            ridge_alpha=config.rules.curve.ridge_alpha,
        )

    artifacts: dict[str, GroupCurveArtifact] = {}
    metrics: dict[str, Any] = {"group_levels": {}}
    global_curves: dict[int, tuple[Decimal, ...]] = {}
    for group_key, samples in variety_grouped.items():
        density = fit_for_samples(samples)
        peak_day = Decimal(
            support_days[int(np.argmax(np.asarray([float(item) for item in density], dtype=float)))]
        ).quantize(Decimal("0.000001"))
        variety_id = samples[0].manifest_row.variety_id
        global_curves[variety_id] = density
        artifacts[group_key] = GroupCurveArtifact(
            group_key=group_key,
            level="variety_global",
            density=density,
            peak_day=peak_day,
            sample_count=len(samples),
            distinct_season_count=len({item.season_code for item in samples}),
            distinct_farm_count=len({item.manifest_row.farm_id for item in samples}),
            distinct_subfarm_count=len({item.manifest_row.subfarm_id for item in samples}),
            parent_group_key=None,
            shrinkage=Decimal("1.000000"),
        )
    province_curves: dict[str, tuple[Decimal, ...]] = {}
    for group_key, samples in province_grouped.items():
        density = fit_for_samples(samples)
        parent_key = f"variety:{samples[0].manifest_row.variety_id}"
        parent_curve = global_curves[samples[0].manifest_row.variety_id]
        sample_count = len(samples)
        shrinkage = _quantized_decimal(
            Decimal(sample_count) / Decimal(config.rules.pooling.full_pooling_sample_target),
            Decimal("0"),
            Decimal("1"),
        )
        density = blend_curves(parent=parent_curve, local=density, shrinkage=shrinkage)
        province_curves[group_key] = density
        peak_day = Decimal(
            support_days[int(np.argmax(np.asarray([float(item) for item in density], dtype=float)))]
        ).quantize(Decimal("0.000001"))
        artifacts[group_key] = GroupCurveArtifact(
            group_key=group_key,
            level="province_variety",
            density=density,
            peak_day=peak_day,
            sample_count=sample_count,
            distinct_season_count=len({item.season_code for item in samples}),
            distinct_farm_count=len({item.manifest_row.farm_id for item in samples}),
            distinct_subfarm_count=len({item.manifest_row.subfarm_id for item in samples}),
            parent_group_key=parent_key,
            shrinkage=shrinkage,
        )
    for group_key, samples in grouped.items():
        density = fit_for_samples(samples)
        province_key = (
            f"province:{samples[0].province}|"
            f"variety:{samples[0].manifest_row.variety_id}"
        )
        parent_key = (
            province_key
            if province_key in province_curves
            else f"variety:{samples[0].manifest_row.variety_id}"
        )
        parent_curve = artifacts[parent_key].density
        sample_count = len(samples)
        shrinkage = _quantized_decimal(
            Decimal(sample_count) / Decimal(config.rules.pooling.full_pooling_sample_target),
            Decimal("0"),
            Decimal("1"),
        )
        density = blend_curves(parent=parent_curve, local=density, shrinkage=shrinkage)
        peak_day = Decimal(
            support_days[int(np.argmax(np.asarray([float(item) for item in density], dtype=float)))]
        ).quantize(Decimal("0.000001"))
        artifacts[group_key] = GroupCurveArtifact(
            group_key=group_key,
            level="climate_zone_variety",
            density=density,
            peak_day=peak_day,
            sample_count=sample_count,
            distinct_season_count=len({item.season_code for item in samples}),
            distinct_farm_count=len({item.manifest_row.farm_id for item in samples}),
            distinct_subfarm_count=len({item.manifest_row.subfarm_id for item in samples}),
            parent_group_key=parent_key,
            shrinkage=shrinkage,
        )
    metrics["group_levels"] = {
        key: {
            "level": artifact.level,
            "sample_count": artifact.sample_count,
            "distinct_season_count": artifact.distinct_season_count,
        }
        for key, artifact in artifacts.items()
    }
    return artifacts, metrics


def _build_shift_model(
    *,
    resolved_samples: list[ResolvedTrainingSample],
    artifacts: dict[str, GroupCurveArtifact],
    config: MaturityCurveConfig,
) -> ShiftModelArtifact:
    facility_types = tuple(
        sorted({item.manifest_row.facility_type for item in resolved_samples})
    )
    if len(resolved_samples) < config.rules.offset.minimum_training_samples:
        return ShiftModelArtifact(
            enabled=False,
            intercept_days=Decimal("0"),
            coefficients={},
            category_vocabulary={"facility_type": facility_types},
            reference_categories={
                "facility_type": min(item.manifest_row.facility_type for item in resolved_samples)
                if resolved_samples
                else "unknown"
            },
            bounds=(
                -config.rules.offset.maximum_abs_shift_days,
                config.rules.offset.maximum_abs_shift_days,
            ),
            warnings=("insufficient_shift_training_data",),
        )
    return ShiftModelArtifact(
        enabled=False,
        intercept_days=Decimal("0"),
        coefficients={},
        category_vocabulary={"facility_type": facility_types},
        reference_categories={
            "facility_type": min(item.manifest_row.facility_type for item in resolved_samples)
        },
        bounds=(
            -config.rules.offset.maximum_abs_shift_days,
            config.rules.offset.maximum_abs_shift_days,
        ),
        warnings=("shift_model_zero_offset_fallback",),
    )


def _predict_shift_days(
    *,
    shift_model: ShiftModelArtifact,
    feature_values: dict[str, Decimal | str | None],
) -> Decimal:
    del feature_values
    return _quantized_decimal(
        shift_model.intercept_days,
        shift_model.bounds[0],
        shift_model.bounds[1],
    )


def _curve_for_sample(
    *,
    artifacts: dict[str, GroupCurveArtifact],
    climate_zone_id: int,
    province: str,
    variety_id: int,
) -> tuple[GroupCurveArtifact | None, str]:
    climate_zone_key = f"zone:{climate_zone_id}|variety:{variety_id}"
    province_key = f"province:{province}|variety:{variety_id}"
    global_key = f"variety:{variety_id}"
    for key in (climate_zone_key, province_key, global_key):
        artifact = artifacts.get(key)
        if artifact is not None:
            return artifact, artifact.level
    return None, "unavailable"


def _model_artifact_payload(
    *,
    config: MaturityCurveConfig,
    artifacts: dict[str, GroupCurveArtifact],
    shift_model: ShiftModelArtifact,
    calibration: dict[str, Any],
    anchor_event: str,
    base_temperature_context: dict[str, Any],
) -> dict[str, Any]:
    support_days = _support_days(config)
    return {
        "model_family": config.rules.model_family,
        "model_version": config.rules.curve.version,
        "support_days": support_days,
        "anchor_event": anchor_event,
        "group_models": {
            key: {
                "level": artifact.level,
                "density": artifact.density,
                "peak_day": artifact.peak_day,
                "sample_count": artifact.sample_count,
                "distinct_season_count": artifact.distinct_season_count,
                "distinct_farm_count": artifact.distinct_farm_count,
                "distinct_subfarm_count": artifact.distinct_subfarm_count,
                "parent_group_key": artifact.parent_group_key,
                "shrinkage": artifact.shrinkage,
                "warnings": artifact.warnings,
            }
            for key, artifact in sorted(artifacts.items())
        },
        "shift_model": asdict(shift_model),
        "calibration": calibration,
        "base_temperature_context": base_temperature_context,
    }


def _artifact_from_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, GroupCurveArtifact], ShiftModelArtifact]:
    group_models: dict[str, GroupCurveArtifact] = {}
    for key, row in cast(dict[str, dict[str, Any]], payload.get("group_models", {})).items():
        group_models[key] = GroupCurveArtifact(
            group_key=key,
            level=cast(
                Literal["climate_zone_variety", "province_variety", "variety_global"],
                row["level"],
            ),
            density=tuple(_decimal_value(item, field="density") for item in row["density"]),
            peak_day=_decimal_value(row["peak_day"], field="peak_day"),
            sample_count=int(row["sample_count"]),
            distinct_season_count=int(row["distinct_season_count"]),
            distinct_farm_count=int(row["distinct_farm_count"]),
            distinct_subfarm_count=int(row["distinct_subfarm_count"]),
            parent_group_key=cast(str | None, row.get("parent_group_key")),
            shrinkage=_decimal_value(row["shrinkage"], field="shrinkage"),
            warnings=tuple(cast(list[str], row.get("warnings", []))),
        )
    shift_row = cast(dict[str, Any], payload.get("shift_model", {}))
    shift_model = ShiftModelArtifact(
        enabled=bool(shift_row.get("enabled", False)),
        intercept_days=_decimal_value(shift_row.get("intercept_days", "0"), field="intercept_days"),
        coefficients={
            key: _decimal_value(value, field=key)
            for key, value in cast(dict[str, Any], shift_row.get("coefficients", {})).items()
        },
        category_vocabulary={
            key: tuple(value)
            for key, value in cast(
                dict[str, list[str]],
                shift_row.get("category_vocabulary", {}),
            ).items()
        },
        reference_categories=cast(dict[str, str], shift_row.get("reference_categories", {})),
        bounds=(
            _decimal_value(cast(list[Any], shift_row.get("bounds", ["0", "0"]))[0], field="bound"),
            _decimal_value(cast(list[Any], shift_row.get("bounds", ["0", "0"]))[1], field="bound"),
        ),
        warnings=tuple(cast(list[str], shift_row.get("warnings", []))),
    )
    return group_models, shift_model


def _model_payload(result: MaturityModelExecutionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "run_id": result.run_id,
        "source_signature": result.source_signature,
        "config_hash": result.config_hash,
        "model_version": result.model_version,
        "payload": cast(dict[str, Any], canonical_json_value(asdict(result))),
    }


def _forecast_payload(result: MaturityForecastExecutionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "run_id": result.run_id,
        "source_signature": result.source_signature,
        "config_hash": result.config_hash,
        "model_version": result.model_version,
        "payload": cast(dict[str, Any], canonical_json_value(asdict(result))),
    }


def _daily_prediction_from_row(row: MaturityDailyPredictionModel) -> MaturityDailyPrediction:
    return MaturityDailyPrediction(
        prediction_date=row.prediction_date,
        phenology_coordinate_day=row.phenology_coordinate_day,
        p50_kg=row.p50_kg,
        p80_kg=row.p80_kg,
        p90_kg=row.p90_kg,
        cumulative_p50_kg=row.cumulative_p50_kg,
        cumulative_p80_kg=row.cumulative_p80_kg,
        cumulative_p90_kg=row.cumulative_p90_kg,
        curve_share=row.curve_share,
        confidence_level=cast(Literal["high", "medium", "low"], row.confidence_level),
        quality_flags=tuple(row.quality_flags),
    )


def _model_result_from_run(
    run: MaturityModelRun,
    artifact: MaturityModelArtifact | None,
) -> MaturityModelExecutionResult:
    return MaturityModelExecutionResult(
        status=_model_run_status_value(run.status),
        run_id=run.id,
        source_signature=run.source_signature,
        config_hash=run.config_hash,
        model_version=run.model_version,
        model_family=run.model_family,
        sample_count=run.sample_count,
        distinct_season_count=run.distinct_season_count,
        distinct_farm_count=run.distinct_farm_count,
        distinct_subfarm_count=run.distinct_subfarm_count,
        warnings=tuple(run.warnings),
        blockers=tuple(run.blockers),
        training_metrics=run.training_metrics,
        calibration_metrics=run.calibration_metrics,
        artifact={} if artifact is None else artifact.artifact_payload,
        input_snapshot=run.input_snapshot,
        error_message=run.error_message,
    )


def _forecast_result_from_run(
    run: MaturityForecastRun,
    daily_rows: list[MaturityDailyPredictionModel],
    model_run: MaturityModelRun,
) -> MaturityForecastExecutionResult:
    return MaturityForecastExecutionResult(
        status=_run_status_value(run.status),
        run_id=run.id,
        model_run_id=run.model_run_id,
        source_signature=run.source_signature,
        config_hash=model_run.config_hash,
        model_version=model_run.model_version,
        axis_mode=cast(Literal["observed_phenology_axis", "calendar_proxy_axis"], run.axis_mode),
        expected_marketable_total_kg=run.expected_marketable_total_kg,
        expected_total_source=run.expected_total_source,
        daily_predictions=tuple(_daily_prediction_from_row(item) for item in daily_rows),
        warnings=tuple(run.warnings),
        blockers=tuple(run.blockers),
        input_snapshot=run.input_snapshot,
        error_message=run.error_message,
    )


def load_dummy_weather_config() -> WeatherFeatureConfig:
    return load_weather_feature_config(Path("configs/weather_features.yaml"))


async def train_maturity_curve(
    session: AsyncSession,
    *,
    training_cutoff: date,
    manifest_rows: list[MaturityManifestRow],
    config: MaturityCurveConfig,
    dry_run: bool,
) -> MaturityModelExecutionResult:
    if not manifest_rows:
        raise ValueError("manifest_rows must not be empty")
    resolved_snapshots: list[dict[str, Any]] = []
    resolved_samples: list[ResolvedTrainingSample] = []
    for row in manifest_rows:
        snapshot, resolved = await _resolve_training_sample(
            session,
            row=row,
            training_cutoff=training_cutoff,
            config=config,
        )
        resolved_snapshots.append(snapshot)
        if resolved is not None:
            resolved_samples.append(resolved)
    anchor_events = {
        row.manifest_row.anchor_event
        for row in resolved_samples
    }
    if len(anchor_events) > 1:
        raise ValueError("all included samples must share one anchor_event in Task 8")
    anchor_event = next(iter(anchor_events)) if anchor_events else manifest_rows[0].anchor_event
    source_signature = _training_source_signature(
        manifest_rows=resolved_snapshots,
        training_cutoff=training_cutoff,
        config_hash=config.config_hash,
        model_version=config.rules.curve.version,
        random_seed=config.rules.random_seed,
    )
    if not dry_run:
        existing = await find_existing_maturity_model_run(
            session,
            source_signature=source_signature,
        )
        if existing is not None:
            artifact = await get_maturity_model_artifact_by_run_id(
                session,
                run_id=existing.id,
            )
            return _with_status_model(_model_result_from_run(existing, artifact), "skipped")
    warnings: list[str] = []
    blockers: list[str] = []
    if len(resolved_samples) < config.rules.pooling.minimum_samples:
        blockers.append("insufficient_training_samples")
    if len({item.season_code for item in resolved_samples}) < config.rules.pooling.minimum_seasons:
        blockers.append("insufficient_training_seasons")
    if blockers:
        result = MaturityModelExecutionResult(
            status="dry_run" if dry_run else "unavailable",
            run_id=None,
            source_signature=source_signature,
            config_hash=config.config_hash,
            model_version=config.rules.curve.version,
            model_family=config.rules.model_family,
            sample_count=len(resolved_samples),
            distinct_season_count=len({item.season_code for item in resolved_samples}),
            distinct_farm_count=len({item.manifest_row.farm_id for item in resolved_samples}),
            distinct_subfarm_count=len({item.manifest_row.subfarm_id for item in resolved_samples}),
            warnings=(),
            blockers=tuple(blockers),
            training_metrics={},
            calibration_metrics={},
            artifact={},
            input_snapshot={
                "training_cutoff": training_cutoff,
                "manifest_rows": resolved_snapshots,
            },
        )
        if dry_run:
            return result
        run = await create_maturity_model_run(
            session,
            payload={
                "model_version": config.rules.curve.version,
                "config_hash": config.config_hash,
                "config_snapshot": config.snapshot,
                "training_cutoff": training_cutoff,
                "source_signature": source_signature,
                "status": "unavailable",
                "random_seed": config.rules.random_seed,
                "model_family": config.rules.model_family,
                "scope": "task8",
                "sample_count": result.sample_count,
                "distinct_season_count": result.distinct_season_count,
                "distinct_farm_count": result.distinct_farm_count,
                "distinct_subfarm_count": result.distinct_subfarm_count,
                "training_metrics": {},
                "calibration_metrics": {},
                "warnings": [],
                "blockers": list(blockers),
                "input_snapshot": result.input_snapshot,
                "finished_at": _now(),
                "error_message": None,
            },
        )
        return MaturityModelExecutionResult(**{**asdict(result), "run_id": run.id})
    artifacts, training_metrics = _build_group_curves(
        resolved_samples=resolved_samples,
        config=config,
    )
    shift_model = _build_shift_model(
        resolved_samples=resolved_samples,
        artifacts=artifacts,
        config=config,
    )
    calibration = calibration_payload(
        resolved_samples=resolved_samples,
        artifacts=artifacts,
        support_days=_support_days(config),
        config=config,
    )
    warnings.extend(cast(list[str], calibration.get("warnings", [])))
    base_temperature_context = {
        str(sample.climate_zone_id): {
            "run_id": sample.manifest_row.base_temperature_search_run_id,
            "source_signature": sample.base_temperature_source_signature,
            "selected_base_temperature": sample.selected_base_temperature,
        }
        for sample in resolved_samples
    }
    artifact_payload = _model_artifact_payload(
        config=config,
        artifacts=artifacts,
        shift_model=shift_model,
        calibration=calibration,
        anchor_event=anchor_event,
        base_temperature_context=base_temperature_context,
    )
    artifact_hash = _artifact_hash(artifact_payload)
    result = MaturityModelExecutionResult(
        status="dry_run" if dry_run else "completed",
        run_id=None,
        source_signature=source_signature,
        config_hash=config.config_hash,
        model_version=config.rules.curve.version,
        model_family=config.rules.model_family,
        sample_count=len(resolved_samples),
        distinct_season_count=len({item.season_code for item in resolved_samples}),
        distinct_farm_count=len({item.manifest_row.farm_id for item in resolved_samples}),
        distinct_subfarm_count=len({item.manifest_row.subfarm_id for item in resolved_samples}),
        warnings=tuple(warnings),
        blockers=(),
        training_metrics=training_metrics,
        calibration_metrics=calibration,
        artifact=artifact_payload,
        input_snapshot={
            "training_cutoff": training_cutoff,
            "manifest_rows": resolved_snapshots,
            "artifact_hash": artifact_hash,
        },
    )
    if dry_run:
        return result
    run = await create_maturity_model_run(
        session,
        payload={
            "model_version": config.rules.curve.version,
            "config_hash": config.config_hash,
            "config_snapshot": config.snapshot,
            "training_cutoff": training_cutoff,
            "source_signature": source_signature,
            "status": "completed",
            "random_seed": config.rules.random_seed,
            "model_family": config.rules.model_family,
            "scope": "task8",
            "sample_count": result.sample_count,
            "distinct_season_count": result.distinct_season_count,
            "distinct_farm_count": result.distinct_farm_count,
            "distinct_subfarm_count": result.distinct_subfarm_count,
            "training_metrics": training_metrics,
            "calibration_metrics": calibration,
            "warnings": list(warnings),
            "blockers": [],
            "input_snapshot": result.input_snapshot,
            "finished_at": _now(),
            "error_message": None,
        },
    )
    await create_maturity_model_artifact(
        session,
        payload={
            "run_id": run.id,
            "artifact_hash": artifact_hash,
            "support_min_day": config.rules.curve.support_min_day,
            "support_max_day": config.rules.curve.support_max_day,
            "artifact_payload": artifact_payload,
        },
    )
    return MaturityModelExecutionResult(**{**asdict(result), "run_id": run.id})


def _with_status_model(
    result: MaturityModelExecutionResult,
    status: str,
) -> MaturityModelExecutionResult:
    return MaturityModelExecutionResult(**{**asdict(result), "status": status})


def _with_status_forecast(
    result: MaturityForecastExecutionResult,
    status: str,
) -> MaturityForecastExecutionResult:
    return MaturityForecastExecutionResult(**{**asdict(result), "status": status})


async def load_maturity_model_result(
    session: AsyncSession,
    *,
    run_id: int,
) -> MaturityModelExecutionResult:
    run = await get_maturity_model_run(session, run_id=run_id)
    if run is None:
        raise ValueError("maturity model run not found")
    artifact = await get_maturity_model_artifact_by_run_id(session, run_id=run.id)
    return _model_result_from_run(run, artifact)


async def forecast_natural_maturity(
    session: AsyncSession,
    *,
    model_run_id: int,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
    as_of_date: date,
    prediction_start_date: date,
    prediction_end_date: date,
    expected_marketable_total_kg: Decimal | None,
    facility_type: str,
    config: MaturityCurveConfig,
    dry_run: bool,
) -> MaturityForecastExecutionResult:
    model_run = await get_maturity_model_run(session, run_id=model_run_id)
    if model_run is None:
        raise ValueError("maturity model run not found")
    artifact_row = await get_maturity_model_artifact_by_run_id(session, run_id=model_run_id)
    if artifact_row is None:
        raise ValueError("maturity model artifact not found")
    group_models, shift_model = _artifact_from_payload(artifact_row.artifact_payload)
    support_days = tuple(cast(list[int], artifact_row.artifact_payload["support_days"]))
    plan_config = load_production_plan_config(Path("configs/production_plan.yaml"))
    plan = await get_effective_plan(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        season_id=season_id,
        variety_id=variety_id,
        as_of_date=as_of_date,
        config=plan_config,
    )
    references = await find_location_reference_for_plan(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        as_of_date=as_of_date,
    )
    if len(references) != 1:
        raise ValueError("location reference unavailable for forecast")
    reference = references[0]
    if reference.climate_zone_id is None:
        raise ValueError("location reference missing climate zone")
    mapping = await resolve_weather_mapping(
        session,
        location_reference_id=reference.id,
        as_of_date=as_of_date,
        config=load_dummy_weather_config(),
        persist=False,
    )
    mapping_row_hash = cast(str | None, mapping.reproducibility_snapshot.get("row_hash"))
    if (
        mapping.status != "resolved"
        or mapping_row_hash is None
        or mapping.weather_source_location_id is None
    ):
        raise ValueError("weather mapping unavailable for forecast")
    base_temp_context = cast(
        dict[str, Any],
        artifact_row.artifact_payload.get("base_temperature_context", {}),
    )
    base_temp_context_row = cast(
        dict[str, Any] | None,
        base_temp_context.get(str(reference.climate_zone_id)),
    )
    if base_temp_context_row is None:
        raise ValueError("base temperature context unavailable for climate zone")
    base_temp_run_id = int(base_temp_context_row["run_id"])
    base_temp_run = await get_base_temperature_search_run(session, run_id=base_temp_run_id)
    if base_temp_run is None:
        raise ValueError("base temperature search run not found")
    effective_total = expected_marketable_total_kg
    total_source = "explicit"
    if effective_total is None:
        effective_total = plan.expected_total_marketable_kg or plan.derived_total_marketable_kg
        total_source = (
            "explicit"
            if plan.expected_total_marketable_kg is not None
            else "derived_from_task6_plan"
        )
    effective_total = _decimal_value(effective_total, field="expected_marketable_total_kg")
    if effective_total <= 0:
        raise ValueError("expected_marketable_total_kg must be positive")
    observations = await get_effective_weather_observations(
        session,
        weather_source_location_id=mapping.weather_source_location_id,
        start_date=(await _season(session, season_id)).start_date,
        end_date=min(prediction_end_date, as_of_date),
        feature_date=min(prediction_end_date, as_of_date),
        as_of_date=as_of_date,
    )
    observation_fingerprint = _selected_observation_fingerprint(observations)
    source_signature = _forecast_source_signature(
        plan_id=plan.id,
        plan_version=plan.version,
        mapping_row_hash=mapping_row_hash,
        base_temperature_search_run_id=base_temp_run_id,
        base_temperature_source_signature=base_temp_run.source_signature,
        selected_base_temperature=base_temp_run.selected_base_temperature,
        artifact_hash=artifact_row.artifact_hash,
        config_hash=config.config_hash,
        model_version=model_run.model_version,
        as_of_date=as_of_date,
        prediction_start_date=prediction_start_date,
        prediction_end_date=prediction_end_date,
        observation_fingerprint=observation_fingerprint,
    )
    if not dry_run:
        existing = await find_existing_maturity_forecast_run(
            session,
            source_signature=source_signature,
        )
        if existing is not None:
            rows = await list_maturity_daily_predictions(session, forecast_run_id=existing.id)
            return _with_status_forecast(
                _forecast_result_from_run(existing, rows, model_run),
                "skipped",
            )
    artifact, fallback_level = _curve_for_sample(
        artifacts=group_models,
        climate_zone_id=reference.climate_zone_id,
        province=reference.province or "",
        variety_id=variety_id,
    )
    if artifact is None:
        blockers = ("maturity_curve_unavailable",)
        result = MaturityForecastExecutionResult(
            status="dry_run" if dry_run else "unavailable",
            run_id=None,
            model_run_id=model_run_id,
            source_signature=source_signature,
            config_hash=config.config_hash,
            model_version=model_run.model_version,
            axis_mode="calendar_proxy_axis",
            expected_marketable_total_kg=effective_total.quantize(Decimal("0.000000")),
            expected_total_source=total_source,
            daily_predictions=(),
            warnings=(),
            blockers=blockers,
            input_snapshot={},
        )
        return result
    anchor_event = cast(str, artifact_row.artifact_payload["anchor_event"])
    anchor_date = getattr(plan, anchor_event, None)
    if not isinstance(anchor_date, date):
        raise ValueError("forecast anchor date missing")
    shift_days = _predict_shift_days(
        shift_model=shift_model,
        feature_values={
            "facility_type": facility_type,
            "altitude_m": _optional_decimal_value(reference.altitude_m),
            "tree_age_years": plan.tree_age_years,
        },
    )
    shifted_density = _shift_curve(
        density=artifact.density,
        support_days=support_days,
        shift_days=shift_days,
    )
    prediction_dates = date_range(prediction_start_date, prediction_end_date)
    slice_shares: list[Decimal] = []
    slice_coords: list[Decimal] = []
    density_map = {
        rel_day: share
        for rel_day, share in zip(support_days, shifted_density, strict=True)
    }
    for day in prediction_dates:
        rel_day = Decimal((day - anchor_date).days).quantize(Decimal("0.000001")) - shift_days
        rel_day_int = int(rel_day.to_integral_value(rounding=ROUND_HALF_UP))
        slice_coords.append(rel_day)
        slice_shares.append(density_map.get(rel_day_int, Decimal("0")))
    total_slice_share = sum(slice_shares, Decimal("0"))
    if total_slice_share <= 0:
        raise ValueError("forecast support has zero probability mass")
    normalized_slice = tuple(
        (share / total_slice_share).quantize(Decimal("0.000001"))
        for share in slice_shares
    )
    p50_values = reconcile_p50_mass(expected_total_kg=effective_total, density=normalized_slice)
    calibration = cast(dict[str, Any], artifact_row.artifact_payload.get("calibration", {}))
    p80_margin_share = _decimal_value(
        calibration.get("p80_margin_share", "0"),
        field="p80_margin_share",
    )
    p90_margin_share = _decimal_value(
        calibration.get("p90_margin_share", "0"),
        field="p90_margin_share",
    )
    calibration_warnings = tuple(cast(list[str], calibration.get("warnings", [])))
    axis_mode: Literal["observed_phenology_axis", "calendar_proxy_axis"] = (
        "calendar_proxy_axis" if prediction_end_date > as_of_date else "observed_phenology_axis"
    )
    widening = Decimal("1")
    warnings = list(calibration_warnings)
    if axis_mode == "calendar_proxy_axis":
        widening = config.rules.intervals.calendar_proxy_widening_factor
        warnings.append("calendar_proxy_axis")
    daily_predictions: list[MaturityDailyPrediction] = []
    cumulative_p50 = Decimal("0")
    cumulative_p80 = Decimal("0")
    cumulative_p90 = Decimal("0")
    for day, rel_day, share, p50 in zip(
        prediction_dates,
        slice_coords,
        normalized_slice,
        p50_values,
        strict=True,
    ):
        p80 = (p50 + (effective_total * p80_margin_share * widening)).quantize(Decimal("0.000001"))
        p90 = (p50 + (effective_total * p90_margin_share * widening)).quantize(Decimal("0.000001"))
        if p80 < p50:
            p80 = p50
        if p90 < p80:
            p90 = p80
        cumulative_p50 += p50
        cumulative_p80 += p80
        cumulative_p90 += p90
        daily_predictions.append(
            MaturityDailyPrediction(
                prediction_date=day,
                phenology_coordinate_day=rel_day,
                p50_kg=p50,
                p80_kg=p80,
                p90_kg=p90,
                cumulative_p50_kg=cumulative_p50.quantize(Decimal("0.000001")),
                cumulative_p80_kg=cumulative_p80.quantize(Decimal("0.000001")),
                cumulative_p90_kg=cumulative_p90.quantize(Decimal("0.000001")),
                curve_share=share.quantize(Decimal("0.000001")),
                confidence_level="medium" if fallback_level == "climate_zone_variety" else "low",
                quality_flags=tuple(sorted(set([fallback_level] + warnings))),
            )
        )
    input_snapshot = {
        "plan_id": plan.id,
        "plan_version": plan.version,
        "plan_row_hash": plan.row_hash,
        "location_reference_id": reference.id,
        "mapping": mapping.reproducibility_snapshot,
        "base_temperature_search_run_id": base_temp_run_id,
        "base_temperature_source_signature": base_temp_run.source_signature,
        "selected_base_temperature": base_temp_run.selected_base_temperature,
        "observation_fingerprint": observation_fingerprint,
        "axis_mode": axis_mode,
        "artifact_hash": artifact_row.artifact_hash,
    }
    result = MaturityForecastExecutionResult(
        status="dry_run" if dry_run else "completed",
        run_id=None,
        model_run_id=model_run_id,
        source_signature=source_signature,
        config_hash=config.config_hash,
        model_version=model_run.model_version,
        axis_mode=axis_mode,
        expected_marketable_total_kg=effective_total.quantize(Decimal("0.000001")),
        expected_total_source=total_source,
        daily_predictions=tuple(daily_predictions),
        warnings=tuple(warnings),
        blockers=(),
        input_snapshot=input_snapshot,
    )
    if dry_run:
        return result
    forecast_run = await create_maturity_forecast_run(
        session,
        payload={
            "model_run_id": model_run_id,
            "artifact_id": artifact_row.id,
            "plan_id": plan.id,
            "location_reference_id": reference.id,
            "weather_mapping_id": mapping.mapping_id,
            "base_temperature_search_run_id": base_temp_run_id,
            "as_of_date": as_of_date,
            "prediction_start_date": prediction_start_date,
            "prediction_end_date": prediction_end_date,
            "expected_marketable_total_kg": effective_total.quantize(Decimal("0.000001")),
            "expected_total_source": total_source,
            "axis_mode": axis_mode,
            "source_signature": source_signature,
            "status": "completed",
            "warnings": list(warnings),
            "blockers": [],
            "input_snapshot": input_snapshot,
            "finished_at": _now(),
            "error_message": None,
        },
    )
    await create_maturity_daily_predictions(
        session,
        forecast_run_id=forecast_run.id,
        rows=[asdict(item) for item in daily_predictions],
    )
    return MaturityForecastExecutionResult(**{**asdict(result), "run_id": forecast_run.id})


async def load_maturity_forecast_result(
    session: AsyncSession,
    *,
    run_id: int,
) -> MaturityForecastExecutionResult:
    run = await get_maturity_forecast_run(session, run_id=run_id)
    if run is None:
        raise ValueError("maturity forecast run not found")
    model_run = await get_maturity_model_run(session, run_id=run.model_run_id)
    if model_run is None:
        raise ValueError("maturity model run not found")
    rows = await list_maturity_daily_predictions(session, forecast_run_id=run.id)
    return _forecast_result_from_run(run, rows, model_run)
