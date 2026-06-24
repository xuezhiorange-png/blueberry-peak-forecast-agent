from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from sklearn.linear_model import Ridge
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.maturity.calibration import empirical_quantile
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
    TrainingDensityPoint,
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
from backend.app.models.weather import BaseTemperatureSearchRun, WeatherDailyObservation
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


_UNKNOWN_SUBFARM = "__UNKNOWN_SUBFARM__"
_UNKNOWN_FACILITY = "unknown"
_PHASE_COORDINATE_FORMULA_VERSION = "observed_weather_phase_adjusted_day_v1"


def _code_version() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[3],
                text=True,
            )
            .strip()
        )
    except Exception:
        return "unknown"


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


def _normalize_facility_type(
    value: str | None,
    vocabulary: tuple[str, ...] | None = None,
) -> tuple[str | None, str]:
    raw = (value or "").strip() or None
    candidate = raw or _UNKNOWN_FACILITY
    if vocabulary is not None and candidate not in vocabulary:
        return raw, _UNKNOWN_FACILITY
    return raw, candidate


def _subfarm_identity(
    *,
    farm_id: int,
    subfarm_id: int | None,
    subfarm_key: str | None = None,
) -> tuple[int, str]:
    if subfarm_id is not None:
        return farm_id, f"id:{subfarm_id}"
    if subfarm_key:
        return farm_id, f"key:{subfarm_key}"
    return farm_id, f"key:{_UNKNOWN_SUBFARM}"


def _group_counts(samples: list[ResolvedTrainingSample]) -> dict[str, int]:
    return {
        "sample_count": len(samples),
        "distinct_season_count": len({item.season_code for item in samples}),
        "distinct_farm_count": len({item.manifest_row.farm_id for item in samples}),
        "distinct_subfarm_count": len(
            {
                _subfarm_identity(
                    farm_id=item.manifest_row.farm_id,
                    subfarm_id=item.manifest_row.subfarm_id,
                    subfarm_key=item.manifest_row.subfarm_key,
                )
                for item in samples
            }
        ),
    }


def _training_blockers(
    *,
    sample_count: int,
    distinct_season_count: int,
    distinct_farm_count: int,
    distinct_subfarm_count: int,
    config: MaturityCurveConfig,
) -> list[str]:
    blockers: list[str] = []
    if sample_count < config.rules.pooling.minimum_samples:
        blockers.append("insufficient_training_samples")
    if distinct_season_count < config.rules.pooling.minimum_seasons:
        blockers.append("insufficient_training_seasons")
    if distinct_farm_count < config.rules.pooling.minimum_farms:
        blockers.append("insufficient_training_farms")
    if distinct_subfarm_count < config.rules.pooling.minimum_subfarms:
        blockers.append("insufficient_training_subfarms")
    return blockers


_LEAKAGE_CHECK_REASON_MAP: dict[str, tuple[str, ...]] = {
    "analytics_completed_finished_visibility": (
        "analytics_build_run_not_found",
        "analytics_build_run_not_completed",
        "analytics_build_run_season_mismatch",
        "analytics_build_run_missing_finished_at",
        "analytics_build_run_not_visible_at_cutoff",
    ),
    "season_complete_by_cutoff": (
        "season_not_complete_by_training_cutoff",
    ),
    "fact_visibility": (
        "future_fact_rows_not_visible_at_cutoff",
        "fact_rows_not_visible_at_cutoff",
    ),
    "effective_task6_plan": (
        "effective_plan_unavailable_at_cutoff",
        "manifest_plan_not_effective_at_cutoff",
        "plan_not_found",
        "plan_manifest_mismatch",
    ),
    "weather_mapping": (
        "location_reference_farm_mismatch",
        "location_reference_subfarm_mismatch",
        "mapping_unavailable",
    ),
    "weather_observation_visibility": (),
    "base_temperature_cutoff": (
        "base_temperature_run_not_visible_at_cutoff",
    ),
    "future_revision_exclusion": (
        "analytics_build_run_missing_finished_at",
        "analytics_build_run_not_visible_at_cutoff",
        "future_fact_rows_not_visible_at_cutoff",
        "fact_rows_not_visible_at_cutoff",
        "base_temperature_run_not_visible_at_cutoff",
    ),
}


def _manifest_row_ref(snapshot: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "index": index,
        "season_id": snapshot.get("season_id"),
        "season_code": snapshot.get("season_code"),
        "farm_id": snapshot.get("farm_id"),
        "farm_key": snapshot.get("farm_key"),
        "subfarm_id": snapshot.get("subfarm_id"),
        "subfarm_key": snapshot.get("subfarm_key"),
        "variety_id": snapshot.get("variety_id"),
        "production_plan_id": snapshot.get("production_plan_id"),
        "analytics_build_run_id": snapshot.get("analytics_build_run_id"),
        "resolved_exclusion_reason": snapshot.get("resolved_exclusion_reason"),
    }


def _leakage_check_status(
    *,
    affected_count: int,
    included_count: int,
    training_unavailable: bool,
) -> str:
    if affected_count == 0:
        return "pass"
    if training_unavailable or included_count == 0:
        return "fail"
    return "warn"


def _leakage_checks(
    *,
    resolved_snapshots: list[dict[str, Any]],
    training_unavailable: bool,
) -> dict[str, Any]:
    included_count = sum(1 for row in resolved_snapshots if row.get("status") == "included")
    checks: dict[str, Any] = {}
    for check_name, reasons in _LEAKAGE_CHECK_REASON_MAP.items():
        if check_name in {"weather_observation_visibility", "future_revision_exclusion"}:
            continue
        affected_rows = [
            _manifest_row_ref(row, index)
            for index, row in enumerate(resolved_snapshots)
            if cast(str | None, row.get("resolved_exclusion_reason")) in reasons
        ]
        reason_breakdown: dict[str, int] = defaultdict(int)
        for row in affected_rows:
            reason = cast(str | None, row.get("resolved_exclusion_reason"))
            if reason is not None:
                reason_breakdown[reason] += 1
        affected_count = len(affected_rows)
        status = _leakage_check_status(
            affected_count=affected_count,
            included_count=included_count,
            training_unavailable=training_unavailable,
        )
        excluded_count = affected_count if status == "warn" else 0
        failed_count = affected_count if status == "fail" else 0
        checks[check_name] = {
            "status": status,
            "checked_row_count": len(resolved_snapshots),
            "passed_row_count": len(resolved_snapshots) - affected_count,
            "excluded_row_count": excluded_count,
            "failed_row_count": failed_count,
            "reason_code_breakdown": dict(reason_breakdown),
            "affected_manifest_rows": affected_rows,
        }
    weather_visibility_rows: list[dict[str, Any]] = []
    selected_observation_count = 0
    visible_observation_count = 0
    weather_reason_breakdown: dict[str, int] = defaultdict(int)
    future_revision_rows: list[dict[str, Any]] = []
    future_revision_checked_count = 0
    future_revision_excluded_count = 0
    future_revision_reason_breakdown: dict[str, int] = defaultdict(int)
    for index, row in enumerate(resolved_snapshots):
        audit = cast(dict[str, Any], row.get("weather_observation_audit", {}))
        selected_count = int(audit.get("selected_observation_count", 0) or 0)
        visible_count = int(audit.get("visible_observation_count", 0) or 0)
        selected_observation_count += selected_count
        visible_observation_count += visible_count
        invisible_count = max(selected_count - visible_count, 0)
        if invisible_count > 0:
            entry = _manifest_row_ref(row, index)
            entry["invisible_selected_observation_count"] = invisible_count
            weather_visibility_rows.append(entry)
            weather_reason_breakdown[
                "selected_weather_observations_not_visible_at_cutoff"
            ] += invisible_count

        revision_count = int(audit.get("candidate_observation_count", 0) or 0)
        future_excluded_count = int(audit.get("future_excluded_observation_count", 0) or 0)
        future_revision_checked_count += revision_count
        future_revision_excluded_count += future_excluded_count
        if future_excluded_count > 0:
            entry = _manifest_row_ref(row, index)
            entry["future_excluded_observation_count"] = future_excluded_count
            entry["future_excluded_observation_dates"] = cast(
                list[str],
                audit.get("future_excluded_observation_dates", []),
            )
            future_revision_rows.append(entry)
            future_revision_reason_breakdown[
                "future_weather_revisions_excluded_at_cutoff"
            ] += future_excluded_count

    weather_status = _leakage_check_status(
        affected_count=len(weather_visibility_rows),
        included_count=included_count,
        training_unavailable=training_unavailable,
    )
    checks["weather_observation_visibility"] = {
        "status": weather_status,
        "checked_row_count": len(resolved_snapshots),
        "passed_row_count": len(resolved_snapshots) - len(weather_visibility_rows),
        "excluded_row_count": len(weather_visibility_rows) if weather_status == "warn" else 0,
        "failed_row_count": len(weather_visibility_rows) if weather_status == "fail" else 0,
        "reason_code_breakdown": dict(weather_reason_breakdown),
        "affected_manifest_rows": weather_visibility_rows,
        "selected_observation_count": selected_observation_count,
        "visible_observation_count": visible_observation_count,
        "invisible_selected_observation_count": max(
            selected_observation_count - visible_observation_count,
            0,
        ),
    }
    future_status = _leakage_check_status(
        affected_count=len(future_revision_rows),
        included_count=included_count,
        training_unavailable=training_unavailable,
    )
    checks["future_revision_exclusion"] = {
        "status": future_status,
        "checked_row_count": len(resolved_snapshots),
        "passed_row_count": len(resolved_snapshots) - len(future_revision_rows),
        "excluded_row_count": len(future_revision_rows) if future_status == "warn" else 0,
        "failed_row_count": len(future_revision_rows) if future_status == "fail" else 0,
        "reason_code_breakdown": dict(future_revision_reason_breakdown),
        "affected_manifest_rows": future_revision_rows,
        "candidate_observation_count": future_revision_checked_count,
        "future_excluded_observation_count": future_revision_excluded_count,
    }
    return checks


def _run_status_value(status: str) -> PersistedMaturityRunStatus:
    if status in {"running", "completed", "failed", "unavailable"}:
        return cast(PersistedMaturityRunStatus, status)
    raise ValueError(f"unsupported persisted run status: {status}")


def _model_run_status_value(status: str) -> PersistedMaturityRunStatus:
    return _run_status_value(status)


def _sorted_manifest_rows(
    manifest_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        canonical_row = cast(dict[str, Any], canonical_json_value(item))
        return (
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
            cast(int, item.get("analytics_build_run_id", 0) or 0),
            cast(int, item.get("farm_id", 0) or 0),
            cast(int, item.get("subfarm_id", 0) or 0),
            cast(int, item.get("location_reference_id", 0) or 0),
            cast(int, item.get("base_temperature_search_run_id", 0) or 0),
            json.dumps(
                canonical_row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    return sorted(
        manifest_rows,
        key=sort_key,
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
    expected_marketable_total_kg: Decimal,
    expected_total_source: str,
    facility_type_raw: str | None,
    facility_type_normalized: str,
    altitude_m: Decimal | None,
    tree_age_years: Decimal | None,
    pruning_offset_days: Decimal | None,
    flowering_peak_offset_days: Decimal | None,
    first_pick_offset_days: Decimal | None,
    shift_feature_snapshot: dict[str, Any],
    predicted_shift_days: Decimal,
    selected_group_model_key: str,
    fallback_level: str,
    axis_mode: str,
    axis_snapshot: dict[str, Any],
    plan_row_hash: str,
    location_reference_source_hash: str,
    base_temperature_context: dict[str, Any],
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
            "expected_marketable_total_kg": expected_marketable_total_kg,
            "expected_total_source": expected_total_source,
            "facility_type_raw": facility_type_raw,
            "facility_type_normalized": facility_type_normalized,
            "altitude_m": altitude_m,
            "tree_age_years": tree_age_years,
            "pruning_offset_days": pruning_offset_days,
            "flowering_peak_offset_days": flowering_peak_offset_days,
            "first_pick_offset_days": first_pick_offset_days,
            "shift_feature_snapshot": shift_feature_snapshot,
            "predicted_shift_days": predicted_shift_days,
            "selected_group_model_key": selected_group_model_key,
            "fallback_level": fallback_level,
            "axis_mode": axis_mode,
            "axis_snapshot": axis_snapshot,
            "plan_row_hash": plan_row_hash,
            "location_reference_source_hash": location_reference_source_hash,
            "base_temperature_context": base_temperature_context,
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


def _datetime_visible_on_or_before(value: datetime | None, cutoff: date) -> bool:
    if value is None:
        return False
    return value.date() <= cutoff


def _fact_row_fingerprint(row: FactReceiptDaily) -> dict[str, Any]:
    return {
        "id": row.id,
        "receipt_date": row.receipt_date,
        "factory_id": row.factory_id,
        "farm_key": row.farm_key,
        "subfarm_key": row.subfarm_key,
        "variety_id": row.variety_id,
        "weight_kg": row.weight_kg,
        "source_row_count": row.source_row_count,
        "holiday_codes": list(row.holiday_codes),
        "is_spring_festival": row.is_spring_festival,
        "created_at": row.created_at,
    }


def _safe_shift_feature_values(
    *,
    altitude_m: Decimal | None,
    tree_age_years: Decimal | None,
    facility_type_raw: str | None,
    facility_type: str,
    pruning_offset_days: Decimal | None,
    flowering_peak_offset_days: Decimal | None,
    first_pick_offset_days: Decimal | None,
) -> dict[str, Decimal | str | None]:
    return {
        "altitude_m": altitude_m,
        "tree_age_years": tree_age_years,
        "facility_type_raw": facility_type_raw,
        "facility_type": facility_type,
        "pruning_offset_days": pruning_offset_days,
        "flowering_peak_offset_days": flowering_peak_offset_days,
        "first_pick_offset_days": first_pick_offset_days,
    }


def _observed_peak_day(sample: ResolvedTrainingSample) -> Decimal:
    best = max(
        sample.training_points,
        key=lambda item: (item.proxy_share, -abs(item.relative_day)),
    )
    return Decimal(best.relative_day).quantize(Decimal("0.000001"))


def _reference_phase_rate_for_series(
    *,
    observations_by_date: dict[date, Any],
    anchor_date: date,
    end_date: date,
    base_temperature: Decimal,
) -> tuple[Decimal | None, dict[str, Any]]:
    if end_date < anchor_date:
        return None, {
            "observed_elapsed_day_count": 0,
            "expected_day_count": 0,
            "coverage_ratio": Decimal("0"),
            "missing_dates": [],
            "cumulative_effective_temperature": None,
        }
    cumulative, missing = _cumulative_effective_temperature_by_date(
        observations_by_date=observations_by_date,
        anchor_date=anchor_date,
        end_date=end_date,
        base_temperature=base_temperature,
    )
    expected_day_count = (end_date - anchor_date).days + 1
    observed_day_count = len(cumulative)
    coverage_ratio = (
        (Decimal(observed_day_count) / Decimal(expected_day_count)).quantize(Decimal("0.000001"))
        if expected_day_count > 0
        else Decimal("0")
    )
    cumulative_effective_temperature = cumulative.get(end_date)
    if observed_day_count <= 0 or missing or cumulative_effective_temperature is None:
        return None, {
            "observed_elapsed_day_count": observed_day_count,
            "expected_day_count": expected_day_count,
            "coverage_ratio": coverage_ratio,
            "missing_dates": missing,
            "cumulative_effective_temperature": cumulative_effective_temperature,
        }
    return (
        (cumulative_effective_temperature / Decimal(observed_day_count)).quantize(
            Decimal("0.000001")
        ),
        {
            "observed_elapsed_day_count": observed_day_count,
            "expected_day_count": expected_day_count,
            "coverage_ratio": coverage_ratio,
            "missing_dates": missing,
            "cumulative_effective_temperature": cumulative_effective_temperature,
        },
    )


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

    analytics_run = await session.get(AnalyticsBuildRun, row.analytics_build_run_id)
    if analytics_run is None:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "analytics_build_run_not_found"
        return snapshot, None
    if analytics_run.status != "completed":
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "analytics_build_run_not_completed"
        return snapshot, None
    if analytics_run.season_id != row.season_id:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "analytics_build_run_season_mismatch"
        return snapshot, None

    season = await _season(session, row.season_id)
    if season.end_date > training_cutoff:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "season_not_complete_by_training_cutoff"
        return snapshot, None
    visible_at = analytics_run.finished_at
    if visible_at is None:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "analytics_build_run_missing_finished_at"
        return snapshot, None
    if not _datetime_visible_on_or_before(visible_at, training_cutoff):
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "analytics_build_run_not_visible_at_cutoff"
        return snapshot, None

    plan_config = load_production_plan_config(Path("configs/production_plan.yaml"))
    try:
        effective_plan = await get_effective_plan(
            session,
            farm_id=row.farm_id,
            subfarm_id=row.subfarm_id,
            season_id=row.season_id,
            variety_id=row.variety_id,
            as_of_date=training_cutoff,
            config=plan_config,
        )
    except Exception:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "effective_plan_unavailable_at_cutoff"
        return snapshot, None
    if effective_plan.id != row.production_plan_id:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "manifest_plan_not_effective_at_cutoff"
        return snapshot, None
    plan = await session.get(FarmSeasonVarietyPlan, row.production_plan_id)
    if plan is None:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "plan_not_found"
        return snapshot, None
    if plan.season_id != row.season_id or plan.variety_id != row.variety_id:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "plan_manifest_mismatch"
        return snapshot, None
    reference = await _location_reference(
        session,
        location_reference_id=row.location_reference_id,
        as_of_date=training_cutoff,
    )
    if reference.farm_id != row.farm_id or reference.farm_id != plan.farm_id:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "location_reference_farm_mismatch"
        return snapshot, None
    if reference.subfarm_id != row.subfarm_id or reference.subfarm_id != plan.subfarm_id:
        snapshot["status"] = "invalid"
        snapshot["resolved_exclusion_reason"] = "location_reference_subfarm_mismatch"
        return snapshot, None
    base_temp_run = await _base_temperature_run(
        session,
        run_id=row.base_temperature_search_run_id,
        variety_id=row.variety_id,
        climate_zone_id=cast(int, reference.climate_zone_id),
    )
    if base_temp_run.training_cutoff > training_cutoff:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "base_temperature_run_not_visible_at_cutoff"
        return snapshot, None
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
    all_observation_rows = list(
        (
            await session.scalars(
                select(WeatherDailyObservation)
                .where(
                    WeatherDailyObservation.weather_source_location_id
                    == mapping.weather_source_location_id,
                    WeatherDailyObservation.observation_date >= season.start_date,
                    WeatherDailyObservation.observation_date <= season.end_date,
                )
                .order_by(
                    WeatherDailyObservation.observation_date.asc(),
                    WeatherDailyObservation.available_at.desc(),
                    WeatherDailyObservation.source_version.desc(),
                    WeatherDailyObservation.id.desc(),
                )
            )
        ).all()
    )
    observation_fingerprint = tuple(_selected_observation_fingerprint(observations))
    selected_visible_count = sum(
        1
        for item in observation_fingerprint
        if date.fromisoformat(str(item["available_at"])) <= training_cutoff
    )
    future_excluded_observation_rows = [
        row
        for row in all_observation_rows
        if row.available_at > training_cutoff and row.observation_date <= season.end_date
    ]
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
    if any(entry.receipt_date > training_cutoff for entry in daily_rows):
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "future_fact_rows_not_visible_at_cutoff"
        return snapshot, None
    if any(entry.created_at.date() > training_cutoff for entry in daily_rows):
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "fact_rows_not_visible_at_cutoff"
        return snapshot, None
    observations_by_date = {item.observation_date: item for item in observations}
    reference_phase_rate, weather_phase_reference = _reference_phase_rate_for_series(
        observations_by_date=observations_by_date,
        anchor_date=anchor_date,
        end_date=season.end_date,
        base_temperature=cast(Decimal, base_temp_run.selected_base_temperature),
    )
    date_series = analysis_dates(season)
    daily_weight_by_date = {entry.receipt_date: entry.weight_kg for entry in daily_rows}
    raw_weights = [daily_weight_by_date.get(day, Decimal("0")) for day in date_series]
    smoothed_weights = smooth_series(raw_weights)
    density_points: list[tuple[int, Decimal]] = []
    training_points: list[TrainingDensityPoint] = []
    raw_day_count = len(date_series)
    downweighted_day_count = 0
    excluded_day_count = 0
    used_day_count = 0
    raw_proxy_weight = sum(smoothed_weights, Decimal("0"))
    if raw_proxy_weight <= 0:
        snapshot["status"] = "excluded"
        snapshot["resolved_exclusion_reason"] = "empty_proxy_curve"
        return snapshot, None
    effective_training_weight = Decimal("0")
    downweighted_weight = Decimal("0")
    exclusion_reason_breakdown: dict[str, int] = defaultdict(int)
    for day, smoothed in zip(date_series, smoothed_weights, strict=True):
        rel_day = (day - anchor_date).days
        if (
            rel_day < config.rules.curve.support_min_day
            or rel_day > config.rules.curve.support_max_day
        ):
            continue
        is_disturbance = day in holiday_dates
        proxy_share = (smoothed / raw_proxy_weight).quantize(Decimal("0.000001"))
        included_in_loss = True
        loss_weight = row.sample_weight
        disturbance_reason: str | None = None
        if is_disturbance:
            disturbance_reason = "spring_festival"
            if config.rules.holidays.exclude_from_loss:
                included_in_loss = False
                excluded_day_count += 1
                exclusion_reason_breakdown["spring_festival"] += 1
            elif config.rules.holidays.disturbance_weight < Decimal("1"):
                downweighted_day_count += 1
                loss_weight = (
                    row.sample_weight * config.rules.holidays.disturbance_weight
                ).quantize(Decimal("0.000001"))
                downweighted_weight += loss_weight
        if included_in_loss:
            used_day_count += 1
            effective_training_weight += loss_weight
        density_points.append((rel_day, proxy_share))
        training_points.append(
            TrainingDensityPoint(
                relative_day=rel_day,
                proxy_share=proxy_share,
                loss_weight=loss_weight,
                disturbance_reason=disturbance_reason,
                included_in_loss=included_in_loss,
            )
        )
    expected_total = plan.expected_total_marketable_kg or (
        plan.planted_area_mu * plan.expected_yield_kg_per_mu * plan.marketable_rate
    )
    snapshot["status"] = "included"
    snapshot["resolved_exclusion_reason"] = None
    snapshot["plan_version"] = plan.version
    snapshot["plan_row_hash"] = plan.row_hash
    snapshot["plan_available_at"] = plan.available_at
    snapshot["plan_effective_from"] = plan.effective_from
    snapshot["plan_effective_to"] = plan.effective_to
    snapshot["season_code"] = season.code
    snapshot["anchor_date"] = anchor_date
    snapshot["location_reference_source_hash"] = reference.source_row_hash
    snapshot["analytics_provenance"] = {
        "build_run_id": analytics_run.id,
        "aggregation_version": analytics_run.aggregation_version,
        "config_hash": analytics_run.config_hash,
        "source_max_raw_id": analytics_run.source_max_raw_id,
        "source_eligible_row_count": analytics_run.source_eligible_row_count,
        "source_eligible_weight_kg": analytics_run.source_eligible_weight_kg,
        "daily_fact_row_count": analytics_run.daily_fact_row_count,
        "started_at": analytics_run.started_at,
        "finished_at": analytics_run.finished_at,
        "completion_visibility_decision": "finished_at_lte_training_cutoff",
    }
    snapshot["fact_row_fingerprint"] = cast(
        list[dict[str, Any]],
        canonical_json_value(
            sorted(
                (_fact_row_fingerprint(entry) for entry in daily_rows),
                key=lambda item: (
                    item["id"],
                    item["receipt_date"],
                    item["factory_id"],
                    item["farm_key"],
                    item["subfarm_key"],
                    item["variety_id"],
                ),
            )
        ),
    )
    snapshot["base_temperature_run"] = {
        "run_id": base_temp_run.id,
        "source_signature": base_temp_run.source_signature,
        "selected_base_temperature": base_temp_run.selected_base_temperature,
        "training_cutoff": base_temp_run.training_cutoff,
        "feature_version": base_temp_run.feature_version,
        "config_hash": base_temp_run.config_hash,
        "scope_type": base_temp_run.scope_type,
        "climate_zone_id": base_temp_run.climate_zone_id,
        "variety_id": base_temp_run.variety_id,
    }
    snapshot["weather_phase_reference"] = weather_phase_reference | {
        "reference_effective_temperature_per_day": reference_phase_rate,
    }
    snapshot["mapping"] = cast(
        dict[str, Any],
        canonical_json_value(mapping.reproducibility_snapshot),
    )
    snapshot["weather_observation_fingerprint"] = cast(
        list[dict[str, Any]],
        canonical_json_value(list(observation_fingerprint)),
    )
    snapshot["weather_observation_audit"] = {
        "selected_observation_count": len(observation_fingerprint),
        "visible_observation_count": selected_visible_count,
        "candidate_observation_count": len(all_observation_rows),
        "future_excluded_observation_count": len(
            future_excluded_observation_rows
        ),
        "future_excluded_observation_dates": sorted(
            {item.observation_date.isoformat() for item in future_excluded_observation_rows}
        ),
    }
    snapshot["holiday_summary"] = {
        "raw_day_count": raw_day_count,
        "used_day_count": used_day_count,
        "downweighted_day_count": downweighted_day_count,
        "excluded_day_count": excluded_day_count,
        "raw_proxy_weight": raw_proxy_weight,
        "effective_training_weight": effective_training_weight,
        "downweighted_weight_share": (
            Decimal("0")
            if effective_training_weight <= 0
            else (downweighted_weight / effective_training_weight).quantize(Decimal("0.000001"))
        ),
        "excluded_reason_codes": sorted(exclusion_reason_breakdown),
        "reason_code_breakdown": dict(exclusion_reason_breakdown),
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
        plan_id=plan.id,
        plan_version=plan.version,
        plan_row_hash=plan.row_hash,
        plan_available_at=plan.available_at,
        plan_effective_from=plan.effective_from,
        plan_effective_to=plan.effective_to,
        mapping_row_hash=mapping_row_hash,
        location_reference_source_hash=reference.source_row_hash,
        analytics_build_run_finished_at=visible_at.date() if visible_at is not None else None,
        analytics_provenance={
            "build_run_id": analytics_run.id,
            "aggregation_version": analytics_run.aggregation_version,
            "config_hash": analytics_run.config_hash,
            "source_max_raw_id": analytics_run.source_max_raw_id,
            "source_eligible_row_count": analytics_run.source_eligible_row_count,
            "source_eligible_weight_kg": analytics_run.source_eligible_weight_kg,
            "daily_fact_row_count": analytics_run.daily_fact_row_count,
            "finished_at": analytics_run.finished_at,
        },
        fact_row_fingerprint=tuple(
            sorted(
                (_fact_row_fingerprint(entry) for entry in daily_rows),
                key=lambda item: (
                    item["id"],
                    item["receipt_date"],
                    item["factory_id"],
                    item["farm_key"],
                    item["subfarm_key"],
                    item["variety_id"],
                ),
            )
        ),
        base_temperature_source_signature=base_temp_run.source_signature,
        base_temperature_training_cutoff=base_temp_run.training_cutoff,
        base_temperature_feature_version=base_temp_run.feature_version,
        base_temperature_config_hash=base_temp_run.config_hash,
        selected_base_temperature=cast(Decimal, base_temp_run.selected_base_temperature),
        reference_effective_temperature_per_day=reference_phase_rate,
        observation_fingerprint=observation_fingerprint,
        holiday_summary=snapshot["holiday_summary"],
        density_points=tuple(sorted(density_points, key=lambda item: item[0])),
        training_points=tuple(sorted(training_points, key=lambda item: item.relative_day)),
        feature_values=_safe_shift_feature_values(
            altitude_m=_optional_decimal_value(reference.altitude_m),
            tree_age_years=_optional_decimal_value(plan.tree_age_years),
            facility_type_raw=_normalize_facility_type(row.facility_type)[0],
            facility_type=_normalize_facility_type(row.facility_type)[1],
            pruning_offset_days=pruning_offset,
            flowering_peak_offset_days=flowering_peak_offset,
            first_pick_offset_days=first_pick_offset,
        ),
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


def _group_shrinkage(
    *,
    sample_count: int,
    distinct_season_count: int,
    distinct_farm_count: int,
    distinct_subfarm_count: int,
    config: MaturityCurveConfig,
) -> Decimal:
    ratios = [
        Decimal(sample_count) / Decimal(config.rules.pooling.full_pooling_sample_target),
        Decimal(distinct_season_count) / Decimal(max(config.rules.pooling.minimum_seasons, 1)),
        Decimal(distinct_farm_count) / Decimal(max(config.rules.pooling.minimum_farms, 1)),
        Decimal(distinct_subfarm_count) / Decimal(max(config.rules.pooling.minimum_subfarms, 1)),
    ]
    return _quantized_decimal(min(ratios), Decimal("0"), Decimal("1"))


def _reference_phase_rate_payload(
    samples: list[ResolvedTrainingSample],
) -> dict[str, Any] | None:
    weighted_sum = Decimal("0")
    used_samples = 0
    for sample in samples:
        rate = sample.reference_effective_temperature_per_day
        if rate is None:
            continue
        weighted_sum += rate
        used_samples += 1
    if used_samples == 0:
        return None
    return {
        "effective_temperature_per_day": (
            weighted_sum / Decimal(used_samples)
        ).quantize(Decimal("0.000001")),
        "sample_count": used_samples,
    }


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
            for point in sample.training_points:
                if not point.included_in_loss or point.loss_weight <= 0:
                    continue
                point_map[point.relative_day].append((point.proxy_share, point.loss_weight))
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
    metrics: dict[str, Any] = {"group_levels": {}, "reference_phase_rates": {}}
    global_curves: dict[int, tuple[Decimal, ...]] = {}
    for group_key, samples in variety_grouped.items():
        counts = _group_counts(samples)
        blockers = _training_blockers(config=config, **counts)
        if blockers:
            metrics["group_levels"][group_key] = {
                "level": "variety_global",
                "sample_count": counts["sample_count"],
                "distinct_season_count": counts["distinct_season_count"],
                "distinct_farm_count": counts["distinct_farm_count"],
                "distinct_subfarm_count": counts["distinct_subfarm_count"],
                "parent_group_key": None,
                "shrinkage": None,
                "fallback_reason": blockers[0],
                "warnings": list(blockers),
                "available": False,
            }
            metrics["reference_phase_rates"][group_key] = _reference_phase_rate_payload(samples)
            continue
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
            sample_count=counts["sample_count"],
            distinct_season_count=counts["distinct_season_count"],
            distinct_farm_count=counts["distinct_farm_count"],
            distinct_subfarm_count=counts["distinct_subfarm_count"],
            parent_group_key=None,
            shrinkage=Decimal("1.000000"),
        )
        metrics["reference_phase_rates"][group_key] = _reference_phase_rate_payload(samples)
    province_curves: dict[str, tuple[Decimal, ...]] = {}
    for group_key, samples in province_grouped.items():
        counts = _group_counts(samples)
        parent_key = f"variety:{samples[0].manifest_row.variety_id}"
        parent_curve = global_curves.get(samples[0].manifest_row.variety_id)
        if parent_curve is None:
            metrics["group_levels"][group_key] = {
                "level": "province_variety",
                "sample_count": counts["sample_count"],
                "distinct_season_count": counts["distinct_season_count"],
                "distinct_farm_count": counts["distinct_farm_count"],
                "distinct_subfarm_count": counts["distinct_subfarm_count"],
                "parent_group_key": parent_key,
                "shrinkage": None,
                "fallback_reason": "parent_group_unavailable",
                "warnings": ["parent_group_unavailable"],
                "available": False,
            }
            metrics["reference_phase_rates"][group_key] = _reference_phase_rate_payload(samples)
            continue
        blockers = _training_blockers(config=config, **counts)
        if blockers:
            density = parent_curve
            shrinkage = Decimal("0.000000")
            fallback_reason = blockers[0]
            warnings = tuple(blockers)
        else:
            density = fit_for_samples(samples)
            shrinkage = _group_shrinkage(config=config, **counts)
            density = blend_curves(parent=parent_curve, local=density, shrinkage=shrinkage)
            fallback_reason = None
            warnings = ()
        province_curves[group_key] = density
        peak_day = Decimal(
            support_days[int(np.argmax(np.asarray([float(item) for item in density], dtype=float)))]
        ).quantize(Decimal("0.000001"))
        artifacts[group_key] = GroupCurveArtifact(
            group_key=group_key,
            level="province_variety",
            density=density,
            peak_day=peak_day,
            sample_count=counts["sample_count"],
            distinct_season_count=counts["distinct_season_count"],
            distinct_farm_count=counts["distinct_farm_count"],
            distinct_subfarm_count=counts["distinct_subfarm_count"],
            parent_group_key=parent_key,
            shrinkage=shrinkage,
            warnings=warnings,
            fallback_reason=fallback_reason,
        )
        metrics["reference_phase_rates"][group_key] = _reference_phase_rate_payload(samples)
    for group_key, samples in grouped.items():
        counts = _group_counts(samples)
        province_key = (
            f"province:{samples[0].province}|"
            f"variety:{samples[0].manifest_row.variety_id}"
        )
        parent_key = (
            province_key
            if province_key in province_curves
            else f"variety:{samples[0].manifest_row.variety_id}"
        )
        parent_artifact = artifacts.get(parent_key)
        if parent_artifact is None:
            metrics["group_levels"][group_key] = {
                "level": "climate_zone_variety",
                "sample_count": counts["sample_count"],
                "distinct_season_count": counts["distinct_season_count"],
                "distinct_farm_count": counts["distinct_farm_count"],
                "distinct_subfarm_count": counts["distinct_subfarm_count"],
                "parent_group_key": parent_key,
                "shrinkage": None,
                "fallback_reason": "parent_group_unavailable",
                "warnings": ["parent_group_unavailable"],
                "available": False,
            }
            metrics["reference_phase_rates"][group_key] = _reference_phase_rate_payload(samples)
            continue
        parent_curve = parent_artifact.density
        blockers = _training_blockers(config=config, **counts)
        if blockers:
            density = parent_curve
            shrinkage = Decimal("0.000000")
            fallback_reason = blockers[0]
            warnings = tuple(blockers)
        else:
            density = fit_for_samples(samples)
            shrinkage = _group_shrinkage(config=config, **counts)
            density = blend_curves(parent=parent_curve, local=density, shrinkage=shrinkage)
            fallback_reason = None
            warnings = ()
        peak_day = Decimal(
            support_days[int(np.argmax(np.asarray([float(item) for item in density], dtype=float)))]
        ).quantize(Decimal("0.000001"))
        artifacts[group_key] = GroupCurveArtifact(
            group_key=group_key,
            level="climate_zone_variety",
            density=density,
            peak_day=peak_day,
            sample_count=counts["sample_count"],
            distinct_season_count=counts["distinct_season_count"],
            distinct_farm_count=counts["distinct_farm_count"],
            distinct_subfarm_count=counts["distinct_subfarm_count"],
            parent_group_key=parent_key,
            shrinkage=shrinkage,
            warnings=warnings,
            fallback_reason=fallback_reason,
        )
        metrics["reference_phase_rates"][group_key] = _reference_phase_rate_payload(samples)
    metrics["group_levels"] = {
        **metrics["group_levels"],
        **{
            key: {
                "level": artifact.level,
                "sample_count": artifact.sample_count,
                "distinct_season_count": artifact.distinct_season_count,
                "distinct_farm_count": artifact.distinct_farm_count,
                "distinct_subfarm_count": artifact.distinct_subfarm_count,
                "parent_group_key": artifact.parent_group_key,
                "shrinkage": artifact.shrinkage,
                "fallback_reason": artifact.fallback_reason,
                "warnings": list(artifact.warnings),
                "available": True,
            }
            for key, artifact in artifacts.items()
        },
    }
    return artifacts, metrics


def _build_shift_model(
    *,
    resolved_samples: list[ResolvedTrainingSample],
    artifacts: dict[str, GroupCurveArtifact],
    config: MaturityCurveConfig,
) -> ShiftModelArtifact:
    facility_types = tuple(
        sorted(
            {
                cast(str, item.feature_values.get("facility_type", "unknown")) or "unknown"
                for item in resolved_samples
            }
            | {"unknown"}
        )
    )
    reference_facility = facility_types[0] if facility_types else "unknown"
    numeric_features = (
        "altitude_m",
        "tree_age_years",
        "pruning_offset_days",
        "flowering_peak_offset_days",
        "first_pick_offset_days",
    )
    if len(resolved_samples) < config.rules.offset.minimum_training_samples:
        return ShiftModelArtifact(
            enabled=False,
            intercept_days=Decimal("0"),
            coefficients={},
            category_vocabulary={"facility_type": facility_types},
            reference_categories={"facility_type": reference_facility},
            unknown_categories={"facility_type": _UNKNOWN_FACILITY},
            unknown_handling_rules={"facility_type": "map_unseen_to_unknown"},
            feature_order=(),
            scaler_center={},
            scaler_scale={},
            feature_units={
                "altitude_m": "m",
                "tree_age_years": "year",
                "pruning_offset_days": "day",
                "flowering_peak_offset_days": "day",
                "first_pick_offset_days": "day",
            },
            missing_value_rules={name: "mean_impute" for name in numeric_features},
            bounds=(
                -config.rules.offset.maximum_abs_shift_days,
                config.rules.offset.maximum_abs_shift_days,
            ),
            warnings=("insufficient_shift_training_data",),
        )

    def feature_numeric(sample: ResolvedTrainingSample, name: str) -> Decimal | None:
        value = sample.feature_values.get(name)
        if value is None:
            return None
        return _optional_decimal_value(cast(Decimal | int | float | str | None, value))

    imputation_values: dict[str, Decimal] = {}
    scaler_scale: dict[str, Decimal] = {}
    targets: list[Decimal] = []
    for sample in resolved_samples:
        artifact, _ = _curve_for_sample(
            artifacts=artifacts,
            climate_zone_id=sample.climate_zone_id,
            province=sample.province,
            variety_id=sample.manifest_row.variety_id,
        )
        if artifact is None:
            continue
        parent_artifact = artifact
        if artifact.parent_group_key is not None and artifact.parent_group_key in artifacts:
            parent_artifact = artifacts[artifact.parent_group_key]
        observed_peak = _observed_peak_day(sample)
        targets.append((observed_peak - parent_artifact.peak_day).quantize(Decimal("0.000001")))
    if len(targets) < config.rules.offset.minimum_training_samples:
        return ShiftModelArtifact(
            enabled=False,
            intercept_days=Decimal("0"),
            coefficients={},
            category_vocabulary={"facility_type": facility_types},
            reference_categories={"facility_type": reference_facility},
            unknown_categories={"facility_type": _UNKNOWN_FACILITY},
            unknown_handling_rules={"facility_type": "map_unseen_to_unknown"},
            feature_order=(),
            scaler_center={},
            scaler_scale={},
            feature_units={
                "altitude_m": "m",
                "tree_age_years": "year",
                "pruning_offset_days": "day",
                "flowering_peak_offset_days": "day",
                "first_pick_offset_days": "day",
            },
            missing_value_rules={name: "mean_impute" for name in numeric_features},
            bounds=(
                -config.rules.offset.maximum_abs_shift_days,
                config.rules.offset.maximum_abs_shift_days,
            ),
            warnings=("insufficient_shift_training_data",),
        )

    for name in numeric_features:
        observed = [feature_numeric(sample, name) for sample in resolved_samples]
        present = [item for item in observed if item is not None]
        if present:
            center = (sum(present, Decimal("0")) / Decimal(len(present))).quantize(
                Decimal("0.000001")
            )
            variance = sum(
                ((item - center) ** 2 for item in present),
                Decimal("0"),
            ) / Decimal(len(present))
            scale = Decimal(str(float(variance.sqrt()) if variance > 0 else 1.0)).quantize(
                Decimal("0.000001")
            )
            if scale == 0:
                scale = Decimal("1.000000")
        else:
            center = Decimal("0.000000")
            scale = Decimal("1.000000")
        imputation_values[name] = center
        scaler_scale[name] = scale

    feature_order = list(numeric_features)
    facility_feature_names = [
        f"facility_type={name}"
        for name in facility_types
        if name != reference_facility
    ]
    feature_order.extend(facility_feature_names)

    matrix_rows: list[list[float]] = []
    filtered_samples: list[ResolvedTrainingSample] = []
    for sample in resolved_samples:
        artifact, _ = _curve_for_sample(
            artifacts=artifacts,
            climate_zone_id=sample.climate_zone_id,
            province=sample.province,
            variety_id=sample.manifest_row.variety_id,
        )
        if artifact is None:
            continue
        filtered_samples.append(sample)
        row_values: list[float] = []
        for name in numeric_features:
            raw = feature_numeric(sample, name)
            filled = imputation_values[name] if raw is None else raw
            standardized = (filled - imputation_values[name]) / scaler_scale[name]
            row_values.append(float(standardized))
        facility_value = (
            cast(str, sample.feature_values.get("facility_type", "unknown")) or "unknown"
        )
        for name in facility_types:
            if name == reference_facility:
                continue
            row_values.append(1.0 if facility_value == name else 0.0)
        matrix_rows.append(row_values)
    y = np.asarray([float(item) for item in targets[: len(matrix_rows)]], dtype=float)
    X = np.asarray(matrix_rows, dtype=float)
    model = Ridge(
        alpha=float(config.rules.curve.ridge_alpha),
        random_state=config.rules.random_seed,
    )
    model.fit(X, y)

    coefficients = {
        name: Decimal(f"{value:.6f}")
        for name, value in zip(feature_order, model.coef_.tolist(), strict=True)
    }
    return ShiftModelArtifact(
        enabled=True,
        intercept_days=Decimal(f"{float(model.intercept_):.6f}"),
        coefficients=coefficients,
        category_vocabulary={"facility_type": facility_types},
        reference_categories={"facility_type": reference_facility},
        unknown_categories={"facility_type": _UNKNOWN_FACILITY},
        unknown_handling_rules={"facility_type": "map_unseen_to_unknown"},
        feature_order=tuple(feature_order),
        scaler_center=imputation_values,
        scaler_scale=scaler_scale,
        feature_units={
            "altitude_m": "m",
            "tree_age_years": "year",
            "pruning_offset_days": "day",
            "flowering_peak_offset_days": "day",
            "first_pick_offset_days": "day",
            **{name: "indicator" for name in facility_feature_names},
        },
        missing_value_rules={name: "mean_impute" for name in numeric_features},
        bounds=(
            -config.rules.offset.maximum_abs_shift_days,
            config.rules.offset.maximum_abs_shift_days,
        ),
        warnings=(),
    )


def _predict_shift_days(
    *,
    shift_model: ShiftModelArtifact,
    feature_values: dict[str, Decimal | str | None],
) -> Decimal:
    if not shift_model.enabled or not shift_model.feature_order:
        return _quantized_decimal(
            shift_model.intercept_days,
            shift_model.bounds[0],
            shift_model.bounds[1],
        )
    total = shift_model.intercept_days
    facility_input = cast(
        str | None,
        feature_values.get("facility_type_raw")
        or feature_values.get("facility_type"),
    )
    _, facility_value = _normalize_facility_type(
        facility_input,
        shift_model.category_vocabulary.get("facility_type"),
    )
    for feature_name in shift_model.feature_order:
        if feature_name.startswith("facility_type="):
            category = feature_name.split("=", 1)[1]
            feature_value = Decimal("1") if facility_value == category else Decimal("0")
        else:
            raw = _optional_decimal_value(
                cast(Decimal | int | float | str | None, feature_values.get(feature_name))
            )
            center = shift_model.scaler_center.get(feature_name, Decimal("0"))
            scale = shift_model.scaler_scale.get(feature_name, Decimal("1"))
            filled = center if raw is None else raw
            feature_value = (filled - center) / scale if scale != 0 else Decimal("0")
        total += shift_model.coefficients.get(feature_name, Decimal("0")) * feature_value
    return _quantized_decimal(total, shift_model.bounds[0], shift_model.bounds[1])


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


def _calibration_payload(
    *,
    resolved_samples: list[ResolvedTrainingSample],
    artifacts: dict[str, GroupCurveArtifact],
    config: MaturityCurveConfig,
) -> dict[str, Any]:
    del artifacts
    support_days = _support_days(config)
    seasons = sorted({item.season_code for item in resolved_samples})
    if len(seasons) < 2:
        return {
            "p80_margin_share": Decimal("0"),
            "p90_margin_share": Decimal("0"),
            "p80_margin_share_by_support_day": {},
            "p90_margin_share_by_support_day": {},
            "residual_count": 0,
            "held_out_seasons": seasons,
            "fold_count": 0,
            "interval_semantics": "pointwise_marginal",
            "calibration_status": "uncalibrated",
            "pointwise_p80_coverage": None,
            "pointwise_p90_coverage": None,
            "peak_date_mae_days": None,
            "curve_wmape": None,
            "cumulative_share_error": None,
            "warnings": ["uncalibrated_interval"],
        }

    by_day: dict[int, list[Decimal]] = defaultdict(list)
    all_residuals: list[Decimal] = []
    peak_date_errors: list[Decimal] = []
    cumulative_errors: list[Decimal] = []
    absolute_error_sum = Decimal("0")
    actual_sum = Decimal("0")
    covered_p80 = 0
    covered_p90 = 0

    for held_out_season in seasons:
        train_samples = [
            item for item in resolved_samples if item.season_code != held_out_season
        ]
        held_out_samples = [
            item for item in resolved_samples if item.season_code == held_out_season
        ]
        if not train_samples or not held_out_samples:
            continue
        train_artifacts, _ = _build_group_curves(resolved_samples=train_samples, config=config)
        train_shift = _build_shift_model(
            resolved_samples=train_samples,
            artifacts=train_artifacts,
            config=config,
        )
        for sample in held_out_samples:
            artifact, _ = _curve_for_sample(
                artifacts=train_artifacts,
                climate_zone_id=sample.climate_zone_id,
                province=sample.province,
                variety_id=sample.manifest_row.variety_id,
            )
            if artifact is None:
                continue
            shift_days = _predict_shift_days(
                shift_model=train_shift,
                feature_values=sample.feature_values,
            )
            shifted_density = _shift_curve(
                density=artifact.density,
                support_days=support_days,
                shift_days=shift_days,
            )
            predicted_map = {
                rel_day: share
                for rel_day, share in zip(support_days, shifted_density, strict=True)
            }
            actual_map = {point.relative_day: point.proxy_share for point in sample.training_points}
            for rel_day, actual_share in actual_map.items():
                residual = abs(actual_share - predicted_map.get(rel_day, Decimal("0")))
                by_day[rel_day].append(residual)
                all_residuals.append(residual)
                absolute_error_sum += residual
                actual_sum += actual_share
            observed_peak = _observed_peak_day(sample)
            predicted_peak_index = int(
                np.argmax(np.asarray([float(item) for item in shifted_density], dtype=float))
            )
            predicted_peak = Decimal(support_days[predicted_peak_index]).quantize(
                Decimal("0.000001")
            )
            peak_date_errors.append(abs(observed_peak - predicted_peak))
            cumulative_errors.append(
                abs(sum(actual_map.values(), Decimal("0")) - sum(shifted_density, Decimal("0")))
            )

    p80_by_day = {
        str(day): empirical_quantile(values, config.rules.intervals.p80_quantile).quantize(
            Decimal("0.000001")
        )
        for day, values in sorted(by_day.items())
    }
    p90_by_day = {
        str(day): empirical_quantile(values, config.rules.intervals.p90_quantile).quantize(
            Decimal("0.000001")
        )
        for day, values in sorted(by_day.items())
    }
    p80_margin = empirical_quantile(all_residuals, config.rules.intervals.p80_quantile).quantize(
        Decimal("0.000001")
    )
    p90_margin = empirical_quantile(all_residuals, config.rules.intervals.p90_quantile).quantize(
        Decimal("0.000001")
    )
    for day, values in by_day.items():
        margin80 = p80_by_day[str(day)]
        margin90 = p90_by_day[str(day)]
        covered_p80 += sum(1 for value in values if value <= margin80)
        covered_p90 += sum(1 for value in values if value <= margin90)
    residual_count = len(all_residuals)
    warnings: list[str] = []
    status = "calibrated"
    if residual_count < 10:
        warnings.append("uncalibrated_interval")
        status = "uncalibrated"
        p80_margin *= config.rules.intervals.uncalibrated_widening_factor
        p90_margin *= config.rules.intervals.uncalibrated_widening_factor

    return {
        "p80_margin_share": p80_margin.quantize(Decimal("0.000001")),
        "p90_margin_share": p90_margin.quantize(Decimal("0.000001")),
        "p80_margin_share_by_support_day": p80_by_day,
        "p90_margin_share_by_support_day": p90_by_day,
        "residual_count": residual_count,
        "held_out_seasons": seasons,
        "fold_count": len(seasons),
        "interval_semantics": "pointwise_marginal",
        "calibration_status": status,
        "pointwise_p80_coverage": (
            None
            if residual_count == 0
            else (Decimal(covered_p80) / Decimal(residual_count)).quantize(Decimal("0.000001"))
        ),
        "pointwise_p90_coverage": (
            None
            if residual_count == 0
            else (Decimal(covered_p90) / Decimal(residual_count)).quantize(Decimal("0.000001"))
        ),
        "peak_date_mae_days": (
            None
            if not peak_date_errors
            else (sum(peak_date_errors, Decimal("0")) / Decimal(len(peak_date_errors))).quantize(
                Decimal("0.000001")
            )
        ),
        "curve_wmape": (
            None
            if actual_sum <= 0
            else (absolute_error_sum / actual_sum).quantize(Decimal("0.000001"))
        ),
        "cumulative_share_error": (
            None
            if not cumulative_errors
            else (
                sum(cumulative_errors, Decimal("0")) / Decimal(len(cumulative_errors))
            ).quantize(Decimal("0.000001"))
        ),
        "warnings": warnings,
    }


def _model_artifact_payload(
    *,
    config: MaturityCurveConfig,
    artifacts: dict[str, GroupCurveArtifact],
    group_audit: dict[str, Any],
    shift_model: ShiftModelArtifact,
    calibration: dict[str, Any],
    anchor_event: str,
    base_temperature_context: dict[str, Any],
    reference_phase_rates: dict[str, Any],
) -> dict[str, Any]:
    support_days = _support_days(config)
    return {
        "model_family": config.rules.model_family,
        "model_version": config.rules.curve.version,
        "coordinate_system": "relative_day",
        "coordinate_unit": "day",
        "formula_version": _PHASE_COORDINATE_FORMULA_VERSION,
        "support_days": support_days,
        "anchor_event": anchor_event,
        "group_audit": group_audit,
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
                "fallback_reason": artifact.fallback_reason,
            }
            for key, artifact in sorted(artifacts.items())
        },
        "shift_model": asdict(shift_model),
        "calibration": calibration,
        "base_temperature_context": base_temperature_context,
        "reference_phase_rates": reference_phase_rates,
        "phase_adjustment_bounds_days": (
            -config.rules.forecast.observed_phase_adjustment_max_days,
            config.rules.forecast.observed_phase_adjustment_max_days,
        ),
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
            fallback_reason=cast(str | None, row.get("fallback_reason")),
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
        unknown_categories=cast(dict[str, str], shift_row.get("unknown_categories", {})),
        unknown_handling_rules=cast(dict[str, str], shift_row.get("unknown_handling_rules", {})),
        feature_order=tuple(cast(list[str], shift_row.get("feature_order", []))),
        scaler_center={
            key: _decimal_value(value, field=key)
            for key, value in cast(dict[str, Any], shift_row.get("scaler_center", {})).items()
        },
        scaler_scale={
            key: _decimal_value(value, field=key)
            for key, value in cast(dict[str, Any], shift_row.get("scaler_scale", {})).items()
        },
        feature_units=cast(dict[str, str], shift_row.get("feature_units", {})),
        missing_value_rules=cast(
            dict[str, str],
            shift_row.get("missing_value_rules", {}),
        ),
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
    counts = _group_counts(resolved_samples)
    blockers = _training_blockers(config=config, **counts)
    leakage_checks = _leakage_checks(
        resolved_snapshots=resolved_snapshots,
        training_unavailable=bool(blockers) or not resolved_samples,
    )
    shared_input_snapshot = {
        "training_cutoff": training_cutoff,
        "manifest_rows": resolved_snapshots,
        "config_snapshot": config.snapshot,
        "random_seed": config.rules.random_seed,
        "code_version": _code_version(),
        "leakage_checks": leakage_checks,
    }
    if blockers:
        result = MaturityModelExecutionResult(
            status="dry_run" if dry_run else "unavailable",
            run_id=None,
            source_signature=source_signature,
            config_hash=config.config_hash,
            model_version=config.rules.curve.version,
            model_family=config.rules.model_family,
            sample_count=counts["sample_count"],
            distinct_season_count=counts["distinct_season_count"],
            distinct_farm_count=counts["distinct_farm_count"],
            distinct_subfarm_count=counts["distinct_subfarm_count"],
            warnings=(),
            blockers=tuple(blockers),
            training_metrics={},
            calibration_metrics={},
            artifact={},
            input_snapshot=shared_input_snapshot,
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
    supported_variety_global_models = [
        key for key, artifact in artifacts.items() if artifact.level == "variety_global"
    ]
    if not supported_variety_global_models:
        unavailable_blockers = ("no_supported_variety_global_models",)
        result = MaturityModelExecutionResult(
            status="dry_run" if dry_run else "unavailable",
            run_id=None,
            source_signature=source_signature,
            config_hash=config.config_hash,
            model_version=config.rules.curve.version,
            model_family=config.rules.model_family,
            sample_count=counts["sample_count"],
            distinct_season_count=counts["distinct_season_count"],
            distinct_farm_count=counts["distinct_farm_count"],
            distinct_subfarm_count=counts["distinct_subfarm_count"],
            warnings=(),
            blockers=unavailable_blockers,
            training_metrics=training_metrics,
            calibration_metrics={},
            artifact={},
            input_snapshot=shared_input_snapshot,
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
                "training_metrics": result.training_metrics,
                "calibration_metrics": {},
                "warnings": [],
                "blockers": list(unavailable_blockers),
                "input_snapshot": result.input_snapshot,
                "finished_at": _now(),
                "error_message": None,
            },
        )
        return MaturityModelExecutionResult(**{**asdict(result), "run_id": run.id})
    shift_model = _build_shift_model(
        resolved_samples=resolved_samples,
        artifacts=artifacts,
        config=config,
    )
    calibration = _calibration_payload(
        resolved_samples=resolved_samples,
        artifacts=artifacts,
        config=config,
    )
    warnings.extend(cast(list[str], calibration.get("warnings", [])))
    base_temperature_context: dict[str, Any] = {}
    for sample in resolved_samples:
        context_key = (
            f"zone:{sample.climate_zone_id}|variety:{sample.manifest_row.variety_id}"
        )
        row_payload = {
            "run_id": sample.manifest_row.base_temperature_search_run_id,
            "source_signature": sample.base_temperature_source_signature,
            "selected_base_temperature": sample.selected_base_temperature,
            "training_cutoff": sample.base_temperature_training_cutoff,
            "feature_version": sample.base_temperature_feature_version,
            "config_hash": sample.base_temperature_config_hash,
            "scope": "climate_zone_variety",
            "climate_zone_id": sample.climate_zone_id,
            "variety_id": sample.manifest_row.variety_id,
        }
        existing_payload = base_temperature_context.get(context_key)
        if existing_payload is not None and existing_payload != row_payload:
            raise ValueError("conflicting base temperature context for climate zone and variety")
        base_temperature_context[context_key] = row_payload
    artifact_payload = _model_artifact_payload(
        config=config,
        artifacts=artifacts,
        group_audit=cast(dict[str, Any], training_metrics.get("group_levels", {})),
        shift_model=shift_model,
        calibration=calibration,
        anchor_event=anchor_event,
        base_temperature_context=base_temperature_context,
        reference_phase_rates=cast(
            dict[str, Any],
            training_metrics.get("reference_phase_rates", {}),
        ),
    )
    artifact_hash = _artifact_hash(artifact_payload)
    result = MaturityModelExecutionResult(
        status="dry_run" if dry_run else "completed",
        run_id=None,
        source_signature=source_signature,
        config_hash=config.config_hash,
        model_version=config.rules.curve.version,
        model_family=config.rules.model_family,
        sample_count=counts["sample_count"],
        distinct_season_count=counts["distinct_season_count"],
        distinct_farm_count=counts["distinct_farm_count"],
        distinct_subfarm_count=counts["distinct_subfarm_count"],
        warnings=tuple(warnings),
        blockers=(),
        training_metrics=training_metrics,
        calibration_metrics=calibration,
        artifact=artifact_payload,
        input_snapshot={
            **shared_input_snapshot,
            "artifact_hash": artifact_hash,
            "base_temperature_context": base_temperature_context,
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


def _cumulative_effective_temperature_by_date(
    *,
    observations_by_date: dict[date, Any],
    anchor_date: date,
    end_date: date,
    base_temperature: Decimal,
) -> tuple[dict[date, Decimal], list[date]]:
    cumulative: dict[date, Decimal] = {}
    running = Decimal("0")
    missing: list[date] = []
    for day in date_range(anchor_date, end_date):
        observation = observations_by_date.get(day)
        if observation is None:
            missing.append(day)
            continue
        running += max(observation.temperature_mean_c - base_temperature, Decimal("0"))
        cumulative[day] = running.quantize(Decimal("0.000001"))
    return cumulative, missing


def _bounded_coordinate_day(
    *,
    calendar_day: Decimal,
    bounded_phase_adjustment_days: Decimal,
    support_min_day: int,
    support_max_day: int,
) -> Decimal:
    raw = calendar_day + bounded_phase_adjustment_days
    return _quantized_decimal(
        raw,
        Decimal(support_min_day),
        Decimal(support_max_day),
    )


def _forecast_axis_payload(
    *,
    anchor_date: date,
    as_of_date: date,
    prediction_dates: list[date],
    base_temperature: Decimal,
    observations_by_date: dict[date, Any],
    reference_effective_temperature_per_day: Decimal | None,
    support_min_day: int,
    support_max_day: int,
    maximum_abs_adjustment_days: Decimal,
    minimum_observed_axis_coverage_ratio: Decimal,
) -> tuple[
    Literal["observed_phenology_axis", "calendar_proxy_axis"],
    dict[str, Any],
    dict[date, Decimal],
    list[str],
]:
    if not prediction_dates:
        return (
            "calendar_proxy_axis",
            {
                "coordinate_system": "observed_weather_phase_adjusted_day",
                "coordinate_unit": "day",
                "formula": "calendar_day_plus_bounded_phase_adjustment",
                "formula_version": _PHASE_COORDINATE_FORMULA_VERSION,
                "axis_provenance": "empty_prediction_window",
                "selected_base_temperature": base_temperature,
                "reference_effective_temperature_per_day": reference_effective_temperature_per_day,
                "calendar_day": None,
                "cumulative_effective_temperature": None,
                "observed_elapsed_day_count": 0,
                "phase_adjustment_days": Decimal("0"),
                "bounded_phase_adjustment_days": Decimal("0"),
                "observed_day_count": 0,
                "expected_day_count": 0,
                "coverage_ratio": Decimal("0"),
                "missing_dates": [],
                "observed_prefix_end_date": None,
                "proxy_suffix_start_date": None,
            },
            {},
            ["calendar_proxy_axis"],
        )
    prediction_end_date = prediction_dates[-1]
    observed_end_date = min(prediction_end_date, as_of_date)
    cumulative, observed_missing = _cumulative_effective_temperature_by_date(
        observations_by_date=observations_by_date,
        anchor_date=anchor_date,
        end_date=observed_end_date,
        base_temperature=base_temperature,
    )
    expected_observed_days = max((observed_end_date - anchor_date).days + 1, 0)
    coverage_ratio = (
        (Decimal(len(cumulative)) / Decimal(expected_observed_days)).quantize(Decimal("0.000001"))
        if expected_observed_days > 0
        else Decimal("0")
    )
    observed_prefix_end_date = observed_end_date if expected_observed_days > 0 else None
    observed_elapsed_day_count = max((observed_end_date - anchor_date).days + 1, 0)

    def _phase_adjustment_for_day(day: date) -> tuple[Decimal, Decimal, Decimal | None]:
        calendar_day = Decimal((day - anchor_date).days).quantize(Decimal("0.000001"))
        cumulative_effective_temperature = cumulative.get(day)
        if (
            cumulative_effective_temperature is None
            or reference_effective_temperature_per_day is None
            or reference_effective_temperature_per_day <= 0
        ):
            return calendar_day, Decimal("0"), cumulative_effective_temperature
        observed_days = Decimal((day - anchor_date).days + 1)
        phase_adjustment = (
            cumulative_effective_temperature / reference_effective_temperature_per_day
            - observed_days
        ).quantize(Decimal("0.000001"))
        bounded_phase_adjustment = _quantized_decimal(
            phase_adjustment,
            -maximum_abs_adjustment_days,
            maximum_abs_adjustment_days,
        )
        return (
            _bounded_coordinate_day(
                calendar_day=calendar_day,
                bounded_phase_adjustment_days=bounded_phase_adjustment,
                support_min_day=support_min_day,
                support_max_day=support_max_day,
            ),
            bounded_phase_adjustment,
            cumulative_effective_temperature,
        )

    if (
        prediction_end_date <= as_of_date
        and not observed_missing
        and reference_effective_temperature_per_day is not None
        and coverage_ratio >= minimum_observed_axis_coverage_ratio
    ):
        coordinates: dict[date, Decimal] = {}
        final_coordinate = Decimal("0")
        final_adjustment = Decimal("0")
        final_cumulative: Decimal | None = None
        for day in prediction_dates:
            coordinate, bounded_phase_adjustment, cumulative_effective_temperature = (
                _phase_adjustment_for_day(day)
            )
            coordinates[day] = coordinate
            final_coordinate = coordinate
            final_adjustment = bounded_phase_adjustment
            final_cumulative = cumulative_effective_temperature
        return (
            "observed_phenology_axis",
            {
                "coordinate_system": "observed_weather_phase_adjusted_day",
                "coordinate_unit": "day",
                "formula": "calendar_day_plus_bounded_phase_adjustment",
                "formula_version": _PHASE_COORDINATE_FORMULA_VERSION,
                "axis_provenance": "observed_weather_complete",
                "selected_base_temperature": base_temperature,
                "calendar_day": Decimal((prediction_dates[-1] - anchor_date).days).quantize(
                    Decimal("0.000001")
                ),
                "cumulative_effective_temperature": final_cumulative,
                "observed_elapsed_day_count": len(cumulative),
                "reference_effective_temperature_per_day": reference_effective_temperature_per_day,
                "phase_adjustment_days": final_adjustment,
                "bounded_phase_adjustment_days": final_adjustment,
                "observed_day_count": len(cumulative),
                "expected_day_count": len(prediction_dates),
                "coverage_ratio": coverage_ratio,
                "missing_dates": [],
                "observed_prefix_end_date": observed_prefix_end_date,
                "proxy_suffix_start_date": None,
                "phenology_coordinate_day": final_coordinate,
            },
            coordinates,
            [],
        )

    phase_correction_days = Decimal("0")
    prefix_cumulative: Decimal | None = cumulative.get(observed_end_date)
    if (
        anchor_date <= observed_end_date
        and prefix_cumulative is not None
        and reference_effective_temperature_per_day is not None
        and reference_effective_temperature_per_day > 0
        and coverage_ratio >= minimum_observed_axis_coverage_ratio
    ):
        observed_days = Decimal((observed_end_date - anchor_date).days + 1)
        phase_correction_days = (
            prefix_cumulative / reference_effective_temperature_per_day - observed_days
        ).quantize(Decimal("0.000001"))
    bounded_phase_correction = _quantized_decimal(
        phase_correction_days,
        -maximum_abs_adjustment_days,
        maximum_abs_adjustment_days,
    )
    coordinates = {
        day: _bounded_coordinate_day(
            calendar_day=Decimal((day - anchor_date).days).quantize(Decimal("0.000001")),
            bounded_phase_adjustment_days=bounded_phase_correction,
            support_min_day=support_min_day,
            support_max_day=support_max_day,
        )
        for day in prediction_dates
    }
    warnings = ["calendar_proxy_axis"]
    if observed_missing:
        warnings.append("anchor_weather_incomplete")
    if reference_effective_temperature_per_day is None:
        warnings.append("reference_phase_rate_unavailable")
    if coverage_ratio < minimum_observed_axis_coverage_ratio:
        warnings.append("observed_weather_coverage_below_threshold")
    if prediction_end_date > as_of_date:
        warnings.append("future_weather_not_used")
    return (
        "calendar_proxy_axis",
        {
            "coordinate_system": "observed_weather_phase_adjusted_day",
            "coordinate_unit": "day",
            "formula": "calendar_day_plus_bounded_phase_adjustment",
            "formula_version": _PHASE_COORDINATE_FORMULA_VERSION,
            "axis_provenance": "calendar_proxy_from_observed_prefix",
            "selected_base_temperature": base_temperature,
            "calendar_day": Decimal((prediction_dates[-1] - anchor_date).days).quantize(
                Decimal("0.000001")
            ),
            "cumulative_effective_temperature": prefix_cumulative,
            "observed_elapsed_day_count": observed_elapsed_day_count,
            "reference_effective_temperature_per_day": reference_effective_temperature_per_day,
            "phase_adjustment_days": phase_correction_days,
            "bounded_phase_adjustment_days": bounded_phase_correction,
            "observed_day_count": len(cumulative),
            "expected_day_count": expected_observed_days,
            "coverage_ratio": coverage_ratio,
            "missing_dates": observed_missing,
            "observed_prefix_end_date": observed_prefix_end_date,
            "proxy_suffix_start_date": next(
                (day for day in prediction_dates if day > as_of_date),
                None,
            ),
        },
        coordinates,
        warnings,
    )


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
    base_temp_context_key = f"zone:{reference.climate_zone_id}|variety:{variety_id}"
    base_temp_context_row = cast(
        dict[str, Any] | None,
        base_temp_context.get(base_temp_context_key),
    )
    if base_temp_context_row is None:
        raise ValueError("base temperature context unavailable for climate zone and variety")
    base_temp_run_id = int(base_temp_context_row["run_id"])
    base_temp_run = await get_base_temperature_search_run(session, run_id=base_temp_run_id)
    if base_temp_run is None:
        raise ValueError("base temperature search run not found")
    if base_temp_run.status != "completed":
        raise ValueError(f"base temperature search run not completed: {base_temp_run.status}")
    if base_temp_run.selected_base_temperature is None:
        raise ValueError("base temperature search run missing selected base temperature")
    if base_temp_run.variety_id != variety_id:
        raise ValueError("base temperature context variety mismatch")
    if base_temp_run.climate_zone_id != reference.climate_zone_id:
        raise ValueError("base temperature context climate zone mismatch")
    if base_temp_run.source_signature != base_temp_context_row.get("source_signature"):
        raise ValueError("base temperature context source signature mismatch")
    if base_temp_run.feature_version != base_temp_context_row.get("feature_version"):
        raise ValueError("base temperature context feature version mismatch")
    if base_temp_run.config_hash != base_temp_context_row.get("config_hash"):
        raise ValueError("base temperature context config hash mismatch")
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
    source_signature = ""
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
    pruning_offset = (
        Decimal((plan.pruning_date - anchor_date).days).quantize(Decimal("0.000001"))
        if plan.pruning_date is not None
        else None
    )
    flowering_peak_offset = (
        Decimal((plan.flowering_peak_date - anchor_date).days).quantize(Decimal("0.000001"))
        if plan.flowering_peak_date is not None
        else None
    )
    first_pick_offset = (
        Decimal((plan.first_pick_date - anchor_date).days).quantize(Decimal("0.000001"))
        if plan.first_pick_date is not None
        else None
    )
    facility_type_raw, facility_type_normalized = _normalize_facility_type(
        facility_type,
        shift_model.category_vocabulary.get("facility_type"),
    )
    shift_feature_snapshot = _safe_shift_feature_values(
        altitude_m=_optional_decimal_value(reference.altitude_m),
        tree_age_years=_optional_decimal_value(plan.tree_age_years),
        facility_type_raw=facility_type_raw,
        facility_type=facility_type_normalized,
        pruning_offset_days=pruning_offset,
        flowering_peak_offset_days=flowering_peak_offset,
        first_pick_offset_days=first_pick_offset,
    )
    shift_days = _predict_shift_days(
        shift_model=shift_model,
        feature_values=shift_feature_snapshot,
    )
    shifted_density = _shift_curve(
        density=artifact.density,
        support_days=support_days,
        shift_days=shift_days,
    )
    prediction_dates = date_range(prediction_start_date, prediction_end_date)
    observations_by_date = {
        item.observation_date: item for item in observations
    }
    selected_base_temperature = base_temp_run.selected_base_temperature
    if selected_base_temperature is None:
        raise ValueError("base temperature search run missing selected base temperature")
    reference_phase_rates = cast(
        dict[str, Any],
        artifact_row.artifact_payload.get("reference_phase_rates", {}),
    )
    reference_phase_rate_row = cast(
        dict[str, Any] | None,
        reference_phase_rates.get(artifact.group_key),
    )
    reference_phase_rate = None
    if reference_phase_rate_row is not None:
        reference_phase_rate = _optional_decimal_value(
            reference_phase_rate_row.get("effective_temperature_per_day")
        )
    axis_mode, axis_snapshot, axis_coordinates, axis_warnings = _forecast_axis_payload(
        anchor_date=anchor_date,
        as_of_date=as_of_date,
        prediction_dates=prediction_dates,
        base_temperature=selected_base_temperature,
        observations_by_date=observations_by_date,
        reference_effective_temperature_per_day=reference_phase_rate,
        support_min_day=support_days[0],
        support_max_day=support_days[-1],
        maximum_abs_adjustment_days=config.rules.forecast.observed_phase_adjustment_max_days,
        minimum_observed_axis_coverage_ratio=config.rules.forecast.minimum_observed_axis_coverage_ratio,
    )
    source_signature = _forecast_source_signature(
        plan_id=plan.id,
        plan_version=plan.version,
        mapping_row_hash=mapping_row_hash,
        base_temperature_search_run_id=base_temp_run_id,
        base_temperature_source_signature=base_temp_run.source_signature,
        selected_base_temperature=selected_base_temperature,
        artifact_hash=artifact_row.artifact_hash,
        config_hash=config.config_hash,
        model_version=model_run.model_version,
        as_of_date=as_of_date,
        prediction_start_date=prediction_start_date,
        prediction_end_date=prediction_end_date,
        expected_marketable_total_kg=effective_total,
        expected_total_source=total_source,
        facility_type_raw=facility_type_raw,
        facility_type_normalized=facility_type_normalized,
        altitude_m=_optional_decimal_value(reference.altitude_m),
        tree_age_years=_optional_decimal_value(plan.tree_age_years),
        pruning_offset_days=pruning_offset,
        flowering_peak_offset_days=flowering_peak_offset,
        first_pick_offset_days=first_pick_offset,
        shift_feature_snapshot=cast(dict[str, Any], canonical_json_value(shift_feature_snapshot)),
        predicted_shift_days=shift_days,
        selected_group_model_key=artifact.group_key,
        fallback_level=fallback_level,
        axis_mode=axis_mode,
        axis_snapshot=cast(dict[str, Any], canonical_json_value(axis_snapshot)),
        plan_row_hash=plan.row_hash,
        location_reference_source_hash=reference.source_row_hash,
        base_temperature_context=cast(dict[str, Any], canonical_json_value(base_temp_context_row)),
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
    slice_shares: list[Decimal] = []
    slice_coords: list[Decimal] = []
    density_map = {
        rel_day: share
        for rel_day, share in zip(support_days, shifted_density, strict=True)
    }
    for day in prediction_dates:
        rel_day = axis_coordinates[day]
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
    widening = Decimal("1")
    warnings = list(calibration_warnings) + axis_warnings
    if axis_mode == "calendar_proxy_axis":
        widening = config.rules.intervals.calendar_proxy_widening_factor
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
        "plan_available_at": plan.available_at,
        "plan_effective_from": plan.effective_from,
        "plan_effective_to": plan.effective_to,
        "location_reference_id": reference.id,
        "location_reference_source_hash": reference.source_row_hash,
        "mapping": mapping.reproducibility_snapshot,
        "base_temperature_search_run_id": base_temp_run_id,
        "base_temperature_source_signature": base_temp_run.source_signature,
        "selected_base_temperature": selected_base_temperature,
        "base_temperature_context_key": base_temp_context_key,
        "base_temperature_context": base_temp_context_row,
        "observation_fingerprint": observation_fingerprint,
        "shift_feature_snapshot": shift_feature_snapshot,
        "facility_type_raw": facility_type_raw,
        "facility_type_normalized": facility_type_normalized,
        "predicted_shift_days": shift_days,
        "selected_group_model_key": artifact.group_key,
        "fallback_level": fallback_level,
        "axis_mode": axis_mode,
        "axis_snapshot": axis_snapshot,
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
