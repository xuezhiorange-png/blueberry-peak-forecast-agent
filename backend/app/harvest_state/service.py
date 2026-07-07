from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from backend.app.harvest_state.canonical import (
    canonical_json_dumps,
    canonical_json_value,
    is_sha256_hex,
    make_holiday_calendar_hash,
    make_membership_hash,
    make_result_hash,
    make_stable_cohort_key,
    make_task9a_config_hash,
    make_weather_rule_config_hash,
    quantize_quantity,
    quantize_ratio,
    sha256_hex,
)
from backend.app.harvest_state.capacity import (
    allocate_fifo_harvest,
    allocate_fifo_loss,
    resolve_harvest_arrival,
)
from backend.app.harvest_state.enums import (
    OUTPUT_SCHEMA_VERSION,
    RESOLVED_PARAMETER_SNAPSHOT_SCHEMA_VERSION,
    RESULT_HASH_SCHEMA_VERSION,
    SOURCE_REF_SCHEMA_VERSION,
    STABLE_COHORT_KEY_SCHEMA_VERSION,
    BlockerCode,
    CapacityInputMode,
    CapacityPoolGrain,
    ForecastQuantile,
)
from backend.app.harvest_state.provenance import build_source_ref_catalog, source_ref_hash
from backend.app.harvest_state.schemas import (
    CohortTransitionRow,
    DailyMemberStateRow,
    DailyPoolResolvedParameters,
    DailyPoolStateRow,
    FutureArrivalScheduleRow,
    InitialInventoryCohortInput,
    MatureInventoryLossInput,
    ParameterSourceRef,
    ResolvedParameterSnapshot,
    RunResolvedParameters,
    SourceRef,
    Task8DailyPredictionInput,
    Task9ABlockedOutput,
    Task9ACompletedOutput,
    Task9ARequest,
)
from backend.app.harvest_state.weather import (
    compute_weather_efficiency_ratio,
    validate_weather_rule_config,
)


@dataclass(slots=True)
class ValidatedRequest:
    request: Task9ARequest
    blockers: list[str]
    warnings: list[str]
    pools_by_id: dict[str, Any]
    pool_membership_hash_by_pool: dict[str, str]
    member_to_pool: dict[tuple[int, int | None, int], str]
    daily_pool_parameters: dict[tuple[date, str], InternalDailyPoolParameters]
    weather_values_by_key: dict[tuple[date, str], dict[str, Decimal]]
    task8_daily_predictions_by_key: dict[
        tuple[ForecastQuantile, date, str], list[Task8DailyPredictionInput]
    ]
    initial_inventory_cohorts: list[InitialInventoryCohortInput]
    initial_cohort_keys: list[str]
    loss_inputs_by_key: dict[tuple[date, str, ForecastQuantile], MatureInventoryLossInput]
    config_hash: str
    input_snapshot: dict[str, Any]
    source_refs: list[SourceRef]


@dataclass(slots=True)
class InternalDailyPoolParameters:
    capacity_date: date
    capacity_pool_id: str
    capacity_pool_grain: CapacityPoolGrain
    capacity_pool_membership_hash: str
    capacity_input_mode: CapacityInputMode
    planned_picker_count: Decimal | None
    kg_per_person_per_day: Decimal | None
    direct_nominal_capacity_kg_per_day: Decimal | None
    resolved_nominal_capacity_kg_per_day: Decimal
    labor_availability_ratio: Decimal
    weather_harvest_efficiency_ratio: Decimal
    operational_efficiency_ratio: Decimal
    resolved_effective_capacity_kg_per_day: Decimal
    holiday_applied: bool
    capacity_parameter_source_ref_hashes: list[str]
    weather_feature_source_ref_hashes: list[str]


def _member_key(
    farm_id: int, subfarm_id: int | None, variety_id: int
) -> tuple[int, int | None, int]:
    return (farm_id, subfarm_id, variety_id)


def _member_sort_key(member: Any) -> tuple[int, int, int]:
    subfarm_value = -1 if member.subfarm_id is None else member.subfarm_id
    return (member.farm_id, subfarm_value, member.variety_id)


def _forecast_quantile_sort_key(value: ForecastQuantile) -> int:
    order = {
        ForecastQuantile.P50: 0,
        ForecastQuantile.P80: 1,
        ForecastQuantile.P90: 2,
    }
    return order[value]


def _forecast_quantile_from_string(value: str) -> int:
    return {"P50": 0, "P80": 1, "P90": 2}.get(value, 99)


def _safe_scalar(value: object) -> tuple[int, str]:
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, "true" if value else "false")
    if isinstance(value, (int, Decimal)):
        return (2, str(value))
    if isinstance(value, str):
        return (3, value)
    if isinstance(value, date):
        return (4, value.isoformat())
    return (9, repr(value))


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _cohort_sort_key(cohort: dict[str, Any]) -> tuple[date, int, int, str]:
    subfarm_value = -1 if cohort["subfarm_id"] is None else int(cohort["subfarm_id"])
    return (
        cohort["cohort_date"],
        int(cohort["variety_id"]),
        subfarm_value,
        str(cohort["stable_cohort_key"]),
    )


def _sum_member_field(
    member_rows: list[dict[str, Any]],
    *,
    pool_id: str,
    field_name: str,
) -> Decimal:
    return sum(
        (row[field_name] for row in member_rows if row["capacity_pool_id"] == pool_id),
        Decimal("0"),
    )


def _compute_initial_cohort_key(
    cohort: InitialInventoryCohortInput,
    *,
    capacity_pool_id: str,
    capacity_pool_membership_hash: str,
    destination_factory_id: int,
) -> str:
    payload = {
        "schema_version": STABLE_COHORT_KEY_SCHEMA_VERSION,
        "source_ref_type": "INITIAL_INVENTORY_SNAPSHOT",
        "source_system": cohort.source_ref.source_system,
        "source_record_key": cohort.source_ref.source_record_key,
        "source_version": cohort.source_ref.source_version,
        "source_row_hash": cohort.source_ref.source_row_hash,
        "cohort_date": cohort.cohort_date,
        "forecast_quantile": cohort.forecast_quantile,
        "farm_id": cohort.farm_id,
        "subfarm_id": cohort.subfarm_id,
        "variety_id": cohort.variety_id,
        "capacity_pool_id": capacity_pool_id,
        "capacity_pool_membership_hash": capacity_pool_membership_hash,
        "destination_factory_id": destination_factory_id,
    }
    return make_stable_cohort_key(payload)


def _compute_task8_cohort_key(
    prediction: Task8DailyPredictionInput,
    *,
    capacity_pool_id: str,
    capacity_pool_membership_hash: str,
    destination_factory_id: int,
) -> str:
    payload = {
        "schema_version": STABLE_COHORT_KEY_SCHEMA_VERSION,
        "source_ref_type": "TASK8_DAILY_PREDICTION",
        "maturity_model_source_signature": prediction.source_ref.maturity_model_source_signature,
        "maturity_model_artifact_hash": prediction.source_ref.maturity_model_artifact_hash,
        "maturity_forecast_source_signature": (
            prediction.source_ref.maturity_forecast_source_signature
        ),
        "prediction_date": prediction.prediction_date,
        "forecast_quantile": prediction.source_ref.forecast_quantile,
        "farm_id": prediction.farm_id,
        "subfarm_id": prediction.subfarm_id,
        "variety_id": prediction.variety_id,
        "capacity_pool_id": capacity_pool_id,
        "capacity_pool_membership_hash": capacity_pool_membership_hash,
        "destination_factory_id": destination_factory_id,
    }
    return make_stable_cohort_key(payload)


def _sorted_request_snapshot(
    request: Task9ARequest,
    validated: ValidatedRequest | None = None,
) -> dict[str, Any]:
    pools = sorted(request.capacity_pools, key=lambda item: item.capacity_pool_id)
    capacity_inputs = sorted(
        request.daily_capacity_inputs,
        key=lambda item: (item.capacity_date, item.capacity_pool_id),
    )
    weather_inputs = sorted(
        request.daily_weather_features,
        key=lambda item: (item.capacity_date, item.capacity_pool_id, item.feature_id),
    )
    task8_inputs = sorted(
        request.task8_daily_predictions,
        key=lambda item: (
            item.prediction_date,
            item.farm_id,
            -1 if item.subfarm_id is None else item.subfarm_id,
            item.variety_id,
            _forecast_quantile_sort_key(item.source_ref.forecast_quantile),
        ),
    )
    initial_inputs = sorted(
        request.initial_inventory_cohorts or [],
        key=lambda item: (
            item.cohort_date,
            item.farm_id,
            -1 if item.subfarm_id is None else item.subfarm_id,
            item.variety_id,
            _forecast_quantile_sort_key(item.forecast_quantile),
        ),
    )
    loss_inputs = sorted(
        request.mature_inventory_loss_inputs,
        key=lambda item: (
            item.state_date,
            item.capacity_pool_id,
            _forecast_quantile_sort_key(item.forecast_quantile),
        ),
    )
    snapshot = {
        "as_of_date": request.as_of_date,
        "forecast_start_date": request.forecast_start_date,
        "forecast_end_date": request.forecast_end_date,
        "forecast_quantiles": list(request.forecast_quantiles),
        "destination_factory_id": request.destination_factory_id,
        "farm_timezone": request.farm_timezone,
        "destination_factory_timezone": request.destination_factory_timezone,
        "harvest_bucket_anchor_local_time": request.harvest_bucket_anchor_local_time,
        "harvest_to_arrival_lag_days": request.harvest_to_arrival_lag_days,
        "holiday_calendar_version": request.holiday_calendar_version,
        "holiday_calendar_hash": request.holiday_calendar_hash,
        "holiday_dates": sorted(request.holiday_dates),
        "weather_rule_config": request.weather_rule_config.model_dump(mode="python"),
        "run_parameter_source_ref_hashes": [
            source_ref_hash(item)
            for item in sorted(
                request.run_parameter_source_refs,
                key=lambda item: (item.parameter_code, item.source_row_hash),
            )
        ],
        "capacity_pools": [
            {
                "capacity_pool_id": pool.capacity_pool_id,
                "capacity_pool_grain": pool.capacity_pool_grain,
                "members": [
                    member.model_dump(mode="python")
                    for member in sorted(pool.members, key=_member_sort_key)
                ],
            }
            for pool in pools
        ],
        "daily_capacity_inputs": [
            {
                "capacity_date": item.capacity_date,
                "capacity_pool_id": item.capacity_pool_id,
                "capacity_input_mode": item.capacity_input_mode,
                "planned_picker_count": item.planned_picker_count,
                "kg_per_person_per_day": item.kg_per_person_per_day,
                "direct_nominal_capacity_kg_per_day": item.direct_nominal_capacity_kg_per_day,
                "labor_availability_ratio": item.labor_availability_ratio,
                "operational_efficiency_ratio": item.operational_efficiency_ratio,
                "capacity_parameter_source_ref_hashes": sorted(
                    source_ref_hash(source_ref)
                    for source_ref in item.capacity_parameter_source_refs
                ),
            }
            for item in capacity_inputs
        ],
        "daily_weather_features": [
            {
                "capacity_date": item.capacity_date,
                "capacity_pool_id": item.capacity_pool_id,
                "feature_id": item.feature_id,
                "value": item.value,
                "source_ref_hash": source_ref_hash(item.source_ref),
            }
            for item in weather_inputs
        ],
        "task8_daily_predictions": [
            {
                "prediction_date": item.prediction_date,
                "farm_id": item.farm_id,
                "subfarm_id": item.subfarm_id,
                "variety_id": item.variety_id,
                "source_ref_hash": source_ref_hash(item.source_ref),
                "verification_snapshot": item.verification_snapshot.model_dump(mode="python"),
                "verification_snapshot_hash": sha256_hex(
                    item.verification_snapshot.model_dump(mode="python")
                ),
            }
            for item in task8_inputs
        ],
        "initial_inventory_cohorts": [
            {
                "cohort_date": item.cohort_date,
                "farm_id": item.farm_id,
                "subfarm_id": item.subfarm_id,
                "variety_id": item.variety_id,
                "remaining_quantity_kg": item.remaining_quantity_kg,
                "source_ref_hash": source_ref_hash(item.source_ref),
                "forecast_quantile": item.forecast_quantile,
                "stable_cohort_key": item.stable_cohort_key,
                "stable_cohort_key_schema_version": item.stable_cohort_key_schema_version,
            }
            for item in initial_inputs
        ],
        "initial_opening_mature_inventory_kg": request.initial_opening_mature_inventory_kg,
        "mature_inventory_loss_inputs": [
            {
                "state_date": item.state_date,
                "capacity_pool_id": item.capacity_pool_id,
                "forecast_quantile": item.forecast_quantile,
                "mature_inventory_loss_quantity_kg": item.mature_inventory_loss_quantity_kg,
                "source_ref_hash": source_ref_hash(item.source_ref),
            }
            for item in loss_inputs
        ],
    }
    if validated is not None:
        snapshot["pool_membership_hash_by_pool"] = validated.pool_membership_hash_by_pool
    return canonical_json_value(snapshot)  # type: ignore[return-value]


def _config_hash(request: Task9ARequest) -> str:
    weather_hash = make_weather_rule_config_hash(
        request.weather_rule_config.model_dump(mode="python")
    )
    holiday_hash = make_holiday_calendar_hash(
        holiday_calendar_version=request.holiday_calendar_version,
        holiday_dates=request.holiday_dates,
    )
    return make_task9a_config_hash(
        weather_rule_version=request.weather_rule_config.version,
        weather_rule_config_hash=weather_hash,
        holiday_calendar_version=request.holiday_calendar_version,
        holiday_calendar_hash=holiday_hash,
        source_ref_schema_version=SOURCE_REF_SCHEMA_VERSION,
        stable_cohort_key_schema_version=STABLE_COHORT_KEY_SCHEMA_VERSION,
        resolved_parameter_snapshot_schema_version=(RESOLVED_PARAMETER_SNAPSHOT_SCHEMA_VERSION),
        output_schema_version=OUTPUT_SCHEMA_VERSION,
    )


def _weather_rule_config_hash(request: Task9ARequest) -> str:
    return make_weather_rule_config_hash(request.weather_rule_config.model_dump(mode="python"))


def _holiday_calendar_hash(request: Task9ARequest) -> str:
    return make_holiday_calendar_hash(
        holiday_calendar_version=request.holiday_calendar_version,
        holiday_dates=request.holiday_dates,
    )


def _sorted_blockers(blockers: list[str]) -> list[str]:
    return sorted(dict.fromkeys(blockers))


def _raw_sortable_key(value: object) -> tuple[int, str]:
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, "true" if value else "false")
    if isinstance(value, datetime):
        return (2, value.isoformat())
    if isinstance(value, date):
        return (2, value.isoformat())
    if isinstance(value, time):
        return (2, value.isoformat())
    if isinstance(value, Enum):
        return _raw_sortable_key(value.value)
    if isinstance(value, (int, str, Decimal, float)):
        return (2, str(value))
    if isinstance(value, Mapping):
        return (3, canonical_json_dumps(_canonicalize_raw_value(value)))
    if isinstance(value, list | tuple):
        return (4, canonical_json_dumps(_canonicalize_raw_value(value)))
    return (9, type(value).__name__)


def _canonicalize_raw_value(value: object) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Enum):
        return _canonicalize_raw_value(value.value)
    if value is None or isinstance(value, (bool, int, str, float, Decimal)):
        try:
            return canonical_json_value(value)
        except Exception:
            return {"__unsupported_type__": type(value).__name__}
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            normalized[str(key)] = _canonicalize_raw_value(item)
        return normalized
    if isinstance(value, list | tuple):
        return [_canonicalize_raw_value(item) for item in value]
    return {"__unsupported_type__": type(value).__name__}


def _normalize_raw_snapshot(payload: Mapping[str, object]) -> dict[str, Any]:
    normalized = _canonicalize_raw_value(payload)
    if not isinstance(normalized, dict):
        return {"raw_payload": normalized}

    capacity_pools = normalized.get("capacity_pools")
    if isinstance(capacity_pools, list):
        sorted_pools: list[Any] = []
        for item in capacity_pools:
            if isinstance(item, dict):
                members = item.get("members")
                if isinstance(members, list):
                    item = {
                        **item,
                        "members": sorted(
                            members,
                            key=lambda member: (
                                _raw_sortable_key(_as_mapping(member).get("farm_id")),
                                _raw_sortable_key(_as_mapping(member).get("subfarm_id")),
                                _raw_sortable_key(_as_mapping(member).get("variety_id")),
                            ),
                        ),
                    }
            sorted_pools.append(item)
        normalized["capacity_pools"] = sorted(
            sorted_pools,
            key=lambda item: (
                _raw_sortable_key(_as_mapping(item).get("capacity_pool_id")),
                _raw_sortable_key(item),
            ),
        )

    task8_predictions = normalized.get("task8_daily_predictions")
    if isinstance(task8_predictions, list):
        normalized["task8_daily_predictions"] = sorted(
            task8_predictions,
            key=lambda item: (
                _raw_sortable_key(_as_mapping(item).get("prediction_date")),
                _raw_sortable_key(_as_mapping(item).get("farm_id")),
                _raw_sortable_key(_as_mapping(item).get("subfarm_id")),
                _raw_sortable_key(_as_mapping(item).get("variety_id")),
                _forecast_quantile_from_string(
                    str(
                        _as_mapping(_as_mapping(item).get("source_ref")).get(
                            "forecast_quantile", ""
                        )
                    )
                ),
                _raw_sortable_key(item),
            ),
        )

    mature_loss = normalized.get("mature_inventory_loss_inputs")
    if isinstance(mature_loss, list):
        normalized["mature_inventory_loss_inputs"] = sorted(
            mature_loss,
            key=lambda item: (
                _raw_sortable_key(_as_mapping(item).get("state_date")),
                _raw_sortable_key(_as_mapping(item).get("capacity_pool_id")),
                _raw_sortable_key(_as_mapping(item).get("forecast_quantile")),
                _raw_sortable_key(item),
            ),
        )
    return canonical_json_value(normalized)  # type: ignore[return-value]


def _map_validation_error_codes(error: ValidationError) -> list[str]:
    blockers: list[str] = []
    for detail in error.errors():
        location = ".".join(str(item) for item in detail.get("loc", ()))
        error_type = str(detail.get("type", ""))
        message = str(detail.get("msg", ""))
        if "harvest_to_arrival_lag_days" in location or "harvest_to_arrival_lag_days" in message:
            blockers.append(BlockerCode.INVALID_ARRIVAL_LAG)
        elif "capacity_pool_grain" in location:
            blockers.append(BlockerCode.UNSUPPORTED_CAPACITY_POOL_GRAIN)
        elif "timezone" in location:
            blockers.append(BlockerCode.INVALID_TIMEZONE)
        elif error_type.startswith("missing"):
            blockers.append(f"{BlockerCode.MISSING_REQUIRED_INPUT}:{location}")
        elif error_type.startswith("value_error"):
            if "float" in message:
                blockers.append(BlockerCode.NATIVE_FLOAT_INPUT)
            else:
                blockers.append(f"{BlockerCode.INVALID_DECIMAL_INPUT}:{location}")
        elif error_type.startswith("list_type"):
            blockers.append(f"{BlockerCode.MISSING_REQUIRED_INPUT}:{location}")
        else:
            blockers.append(f"{BlockerCode.INVALID_DECIMAL_INPUT}:{location}")
    return _sorted_blockers(blockers)


def _blocked_from_raw_payload(
    payload: Mapping[str, object],
    blockers: list[str],
) -> Task9ABlockedOutput:
    input_snapshot = _normalize_raw_snapshot(payload)
    response_payload = {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "status": "blocked",
        "input_snapshot": input_snapshot,
        "resolved_parameter_snapshot": None,
        "daily_pool_state_rows": [],
        "daily_member_state_rows": [],
        "cohort_transition_rows": [],
        "future_arrival_schedule": [],
        "source_ref_catalog": [],
        "warnings": [],
        "blockers": _sorted_blockers(blockers),
        "config_hash": make_result_hash({"raw_input_snapshot": input_snapshot}),
    }
    return Task9ABlockedOutput(
        input_snapshot=input_snapshot,
        resolved_parameter_snapshot=None,
        source_ref_catalog=[],
        warnings=[],
        blockers=_sorted_blockers(blockers),
        config_hash=response_payload["config_hash"],
        result_hash=make_result_hash(response_payload),
    )


def _validated_request(request: Task9ARequest) -> ValidatedRequest:
    blockers: list[str] = []
    warnings: list[str] = []
    timezone_valid = True
    try:
        ZoneInfo(request.farm_timezone)
        ZoneInfo(request.destination_factory_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        blockers.append(BlockerCode.INVALID_TIMEZONE)
        timezone_valid = False

    pools_by_id: dict[str, Any] = {}
    for pool in request.capacity_pools:
        if pool.capacity_pool_id in pools_by_id:
            blockers.append(f"{BlockerCode.DUPLICATE_CAPACITY_POOL_ID}:{pool.capacity_pool_id}")
        pools_by_id[pool.capacity_pool_id] = pool
    pool_membership_hash_by_pool: dict[str, str] = {}
    member_to_pool: dict[tuple[int, int | None, int], str] = {}
    source_refs: list[SourceRef] = []

    if not request.initial_inventory_cohorts and request.initial_inventory_cohorts is None:
        blockers.append(BlockerCode.MISSING_INITIAL_INVENTORY_COHORTS)

    expected_run_codes = {
        "HOLIDAY_CALENDAR",
        "WEATHER_RULE_CONFIG",
        "HARVEST_TO_ARRIVAL_LAG",
        "TIMEZONE_CONFIG",
        "HARVEST_BUCKET_ANCHOR_TIME",
    }
    run_sources_by_code: dict[str, list[ParameterSourceRef]] = {}
    for item in request.run_parameter_source_refs:
        source_refs.append(item)
        run_sources_by_code.setdefault(item.parameter_code.value, []).append(item)
        if item.available_at > item.as_of_date or item.as_of_date != request.as_of_date:
            blockers.append(
                f"{BlockerCode.PARAMETER_SOURCE_NOT_VISIBLE_AT_AS_OF}:{item.parameter_code}"
            )
        if not is_sha256_hex(item.source_row_hash):
            blockers.append(
                f"{BlockerCode.SOURCE_REF_HASH_MISMATCH}:{item.parameter_code}:{item.source_row_hash}"
            )
    found_run_codes = set(run_sources_by_code)
    if found_run_codes != expected_run_codes:
        blockers.append(BlockerCode.CAPACITY_MODE_PROVENANCE_MISSING)
    for code, refs in run_sources_by_code.items():
        if len(refs) != 1:
            blockers.append(f"{BlockerCode.PARAMETER_SOURCE_CONFLICT}:{code}")

    expected_holiday_hash = _holiday_calendar_hash(request)
    if request.holiday_calendar_hash != expected_holiday_hash:
        blockers.append(BlockerCode.PARAMETER_SOURCE_CONFLICT)

    for pool in request.capacity_pools:
        sorted_members = sorted(pool.members, key=_member_sort_key)
        membership_hash = make_membership_hash(
            pool.capacity_pool_grain.value,
            [member.model_dump(mode="python") for member in sorted_members],
        )
        pool_membership_hash_by_pool[pool.capacity_pool_id] = membership_hash
        farm_ids = {member.farm_id for member in pool.members}
        subfarm_ids = {member.subfarm_id for member in pool.members}
        if pool.capacity_pool_grain is CapacityPoolGrain.SUBFARM_VARIETY and len(pool.members) != 1:
            blockers.append(f"{BlockerCode.INVALID_SINGLETON_POOL}:{pool.capacity_pool_id}")
        if pool.capacity_pool_grain is CapacityPoolGrain.SUBFARM and (
            len(farm_ids) != 1 or len(subfarm_ids) != 1
        ):
            blockers.append(f"{BlockerCode.POOL_MEMBER_GRAIN_MISMATCH}:{pool.capacity_pool_id}")
        if pool.capacity_pool_grain is CapacityPoolGrain.FARM and len(farm_ids) != 1:
            blockers.append(f"{BlockerCode.CROSS_FARM_CAPACITY_POOL}:{pool.capacity_pool_id}")
        seen_member_keys: set[tuple[int, int | None, int]] = set()
        for member in sorted_members:
            key = _member_key(member.farm_id, member.subfarm_id, member.variety_id)
            if key in seen_member_keys:
                blockers.append(f"{BlockerCode.DUPLICATE_POOL_MEMBER}:{pool.capacity_pool_id}")
            seen_member_keys.add(key)
            if key in member_to_pool:
                blockers.append(f"{BlockerCode.MEMBER_ASSIGNED_TO_MULTIPLE_POOLS}:{key}")
            else:
                member_to_pool[key] = pool.capacity_pool_id

    weather_values_by_key: dict[tuple[date, str], dict[str, Decimal]] = {}
    weather_refs_by_key: dict[tuple[date, str], list[ParameterSourceRef]] = {}
    seen_weather_keys: set[tuple[date, str, str]] = set()
    allowed_weather_features = set(request.weather_rule_config.required_feature_ids)
    for feature in request.daily_weather_features:
        source_refs.append(feature.source_ref)
        if (
            feature.source_ref.available_at > feature.source_ref.as_of_date
            or feature.source_ref.as_of_date != request.as_of_date
        ):
            blockers.append(
                f"{BlockerCode.PARAMETER_SOURCE_NOT_VISIBLE_AT_AS_OF}:{feature.feature_id}"
            )
        if feature.source_ref.parameter_code.value != "WEATHER_FEATURE_OBSERVATION":
            blockers.append(f"{BlockerCode.UNKNOWN_PARAMETER_CODE}:{feature.feature_id}")
        if not is_sha256_hex(feature.source_ref.source_row_hash):
            blockers.append(
                f"{BlockerCode.SOURCE_REF_HASH_MISMATCH}:{feature.feature_id}:{feature.source_ref.source_row_hash}"
            )
        if feature.feature_id not in allowed_weather_features:
            blockers.append(f"{BlockerCode.UNKNOWN_WEATHER_FEATURE}:{feature.feature_id}")
        weather_dedup_key = (feature.capacity_date, feature.capacity_pool_id, feature.feature_id)
        if weather_dedup_key in seen_weather_keys:
            blockers.append(f"{BlockerCode.DUPLICATE_WEATHER_INPUT}:{weather_dedup_key}")
            continue
        seen_weather_keys.add(weather_dedup_key)
        weather_lookup_key = (feature.capacity_date, feature.capacity_pool_id)
        weather_values_by_key.setdefault(weather_lookup_key, {})
        weather_refs_by_key.setdefault(weather_lookup_key, [])
        weather_values_by_key[weather_lookup_key][feature.feature_id] = feature.value
        weather_refs_by_key[weather_lookup_key].append(feature.source_ref)

    blockers.extend(validate_weather_rule_config(request.weather_rule_config))

    daily_pool_parameters: dict[tuple[date, str], InternalDailyPoolParameters] = {}
    seen_capacity_keys: set[tuple[date, str]] = set()
    forecast_dates = list(
        request.forecast_start_date + timedelta(days=offset)
        for offset in range((request.forecast_end_date - request.forecast_start_date).days + 1)
    )

    for capacity_input in request.daily_capacity_inputs:
        source_refs.extend(capacity_input.capacity_parameter_source_refs)
        capacity_lookup_key = (capacity_input.capacity_date, capacity_input.capacity_pool_id)
        if capacity_lookup_key in seen_capacity_keys:
            blockers.append(f"{BlockerCode.DUPLICATE_POOL_CAPACITY}:{capacity_lookup_key}")
            continue
        seen_capacity_keys.add(capacity_lookup_key)
        capacity_pool = pools_by_id.get(capacity_input.capacity_pool_id)
        if capacity_pool is None:
            blockers.append(
                f"{BlockerCode.MISSING_POOL_MEMBERSHIP}:{capacity_input.capacity_pool_id}"
            )
            continue
        source_codes_by_code: dict[str, list[ParameterSourceRef]] = {}
        for source_ref in capacity_input.capacity_parameter_source_refs:
            source_codes_by_code.setdefault(source_ref.parameter_code.value, []).append(source_ref)
            if (
                source_ref.available_at > source_ref.as_of_date
                or source_ref.as_of_date != request.as_of_date
            ):
                blockers.append(
                    f"{BlockerCode.PARAMETER_SOURCE_NOT_VISIBLE_AT_AS_OF}:{source_ref.parameter_code}"
                )
            if not is_sha256_hex(source_ref.source_row_hash):
                blockers.append(
                    f"{BlockerCode.SOURCE_REF_HASH_MISMATCH}:{source_ref.parameter_code}:{source_ref.source_row_hash}"
                )

        required_codes = {
            CapacityInputMode.LABOR_DERIVED: {
                "PLANNED_PICKER_COUNT",
                "PICKER_PRODUCTIVITY",
                "LABOR_AVAILABILITY_RATIO",
                "OPERATIONAL_EFFICIENCY_RATIO",
            },
            CapacityInputMode.DIRECT_CAPACITY: {
                "DIRECT_NOMINAL_CAPACITY",
                "LABOR_AVAILABILITY_RATIO",
                "OPERATIONAL_EFFICIENCY_RATIO",
            },
        }[capacity_input.capacity_input_mode]
        found_codes = set(source_codes_by_code)
        if found_codes != required_codes:
            blockers.append(
                f"{BlockerCode.CAPACITY_MODE_PROVENANCE_MISSING}:{capacity_input.capacity_pool_id}:{capacity_input.capacity_date}"
            )
        for code, refs in source_codes_by_code.items():
            if len(refs) != 1:
                blockers.append(
                    f"{BlockerCode.PARAMETER_SOURCE_CONFLICT}:{capacity_input.capacity_pool_id}:{capacity_input.capacity_date}:{code}"
                )
        if capacity_input.capacity_input_mode is CapacityInputMode.LABOR_DERIVED:
            if (
                capacity_input.planned_picker_count is None
                or capacity_input.kg_per_person_per_day is None
                or capacity_input.direct_nominal_capacity_kg_per_day is not None
            ):
                blockers.append(
                    f"{BlockerCode.CAPACITY_MODE_FIELD_CONFLICT}:{capacity_input.capacity_pool_id}:{capacity_input.capacity_date}"
                )
                continue
            resolved_nominal = (
                capacity_input.planned_picker_count * capacity_input.kg_per_person_per_day
            )
        else:
            if (
                capacity_input.planned_picker_count is not None
                or capacity_input.kg_per_person_per_day is not None
                or capacity_input.direct_nominal_capacity_kg_per_day is None
            ):
                blockers.append(
                    f"{BlockerCode.CAPACITY_MODE_FIELD_CONFLICT}:{capacity_input.capacity_pool_id}:{capacity_input.capacity_date}"
                )
                continue
            resolved_nominal = capacity_input.direct_nominal_capacity_kg_per_day

        weather_key = (capacity_input.capacity_date, capacity_input.capacity_pool_id)
        feature_values = weather_values_by_key.get(weather_key)
        if feature_values is None:
            blockers.append(
                f"{BlockerCode.MISSING_WEATHER_FEATURE}:{capacity_input.capacity_pool_id}:{capacity_input.capacity_date}"
            )
            weather_ratio = Decimal("0")
            weather_refs: list[ParameterSourceRef] = []
        else:
            try:
                weather_ratio = compute_weather_efficiency_ratio(
                    config=request.weather_rule_config,
                    feature_values=feature_values,
                )
            except ValueError as exc:
                message = str(exc)
                if ":" in message:
                    blockers.append(message)
                elif message == "unsupported weather combination method":
                    blockers.append(BlockerCode.UNKNOWN_WEATHER_FEATURE)
                else:
                    blockers.append(f"{BlockerCode.UNKNOWN_WEATHER_FEATURE}:{message}")
                weather_ratio = Decimal("0")
            weather_refs = sorted(
                weather_refs_by_key.get(weather_key, []),
                key=lambda item: (item.available_at, item.source_row_hash),
            )

        resolved_effective = (
            resolved_nominal
            * capacity_input.labor_availability_ratio
            * weather_ratio
            * capacity_input.operational_efficiency_ratio
        )
        daily_pool_parameters[capacity_lookup_key] = InternalDailyPoolParameters(
            capacity_date=capacity_input.capacity_date,
            capacity_pool_id=capacity_input.capacity_pool_id,
            capacity_pool_grain=capacity_pool.capacity_pool_grain,
            capacity_pool_membership_hash=pool_membership_hash_by_pool[
                capacity_pool.capacity_pool_id
            ],
            capacity_input_mode=capacity_input.capacity_input_mode,
            planned_picker_count=capacity_input.planned_picker_count,
            kg_per_person_per_day=capacity_input.kg_per_person_per_day,
            direct_nominal_capacity_kg_per_day=capacity_input.direct_nominal_capacity_kg_per_day,
            resolved_nominal_capacity_kg_per_day=resolved_nominal,
            labor_availability_ratio=capacity_input.labor_availability_ratio,
            weather_harvest_efficiency_ratio=weather_ratio,
            operational_efficiency_ratio=capacity_input.operational_efficiency_ratio,
            resolved_effective_capacity_kg_per_day=resolved_effective,
            holiday_applied=capacity_input.capacity_date in request.holiday_dates,
            capacity_parameter_source_ref_hashes=sorted(
                source_ref_hash(item) for item in capacity_input.capacity_parameter_source_refs
            ),
            weather_feature_source_ref_hashes=sorted(
                source_ref_hash(item) for item in weather_refs
            ),
        )

    if timezone_valid:
        for forecast_date in forecast_dates:
            try:
                resolve_harvest_arrival(
                    harvest_local_date=forecast_date,
                    harvest_bucket_anchor_local_time=request.harvest_bucket_anchor_local_time,
                    farm_timezone=request.farm_timezone,
                    destination_factory_timezone=request.destination_factory_timezone,
                    harvest_to_arrival_lag_days=request.harvest_to_arrival_lag_days,
                )
            except ValueError as exc:
                if str(exc) == "NONEXISTENT_LOCAL_TIME":
                    blockers.append(f"{BlockerCode.DST_NONEXISTENT_LOCAL_TIME}:{forecast_date}")
                elif str(exc) == "AMBIGUOUS_LOCAL_TIME":
                    blockers.append(f"{BlockerCode.DST_AMBIGUOUS_LOCAL_TIME}:{forecast_date}")
                else:
                    blockers.append(BlockerCode.INVALID_TIMEZONE)

    for forecast_date in forecast_dates:
        for pool_id in pools_by_id:
            if (forecast_date, pool_id) not in daily_pool_parameters:
                blockers.append(
                    f"{BlockerCode.MISSING_RESOLVED_PARAMETER}:{pool_id}:{forecast_date}"
                )

    task8_daily_predictions_by_key: dict[
        tuple[ForecastQuantile, date, str], list[Task8DailyPredictionInput]
    ] = {}
    seen_task8_keys: set[tuple[date, int, int | None, int, ForecastQuantile]] = set()
    task8_request_identity: tuple[int, str, str, str, int, str, int, str, date] | None = None
    task8_daily_prediction_identity_by_id: dict[int, dict[str, Any]] = {}
    task8_daily_prediction_id_by_grain: dict[tuple[date, int, int | None, int], int] = {}
    for prediction in request.task8_daily_predictions:
        source_refs.append(prediction.source_ref)
        member_key = _member_key(prediction.farm_id, prediction.subfarm_id, prediction.variety_id)
        mapped_pool_id = member_to_pool.get(member_key)
        if mapped_pool_id is None:
            blockers.append(f"{BlockerCode.MISSING_POOL_MEMBERSHIP}:{member_key}")
            continue
        task8_row_key = (
            prediction.prediction_date,
            prediction.farm_id,
            prediction.subfarm_id,
            prediction.variety_id,
            prediction.source_ref.forecast_quantile,
        )
        if task8_row_key in seen_task8_keys:
            blockers.append(f"{BlockerCode.DUPLICATE_TASK8_INPUT}:{task8_row_key}")
            continue
        seen_task8_keys.add(task8_row_key)
        verification = prediction.verification_snapshot
        if prediction.source_ref.prediction_date != prediction.prediction_date:
            blockers.append(
                f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{prediction.prediction_date}"
            )
        if verification.maturity_forecast_run_status != "completed":
            blockers.append(
                f"{BlockerCode.TASK8_FORECAST_NOT_COMPLETED}:{verification.maturity_forecast_run_id}"
            )
        if verification.maturity_forecast_as_of_date > request.as_of_date:
            blockers.append(
                f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{verification.maturity_forecast_run_id}"
            )
        if (
            prediction.farm_id != verification.farm_id
            or prediction.subfarm_id != verification.subfarm_id
            or prediction.variety_id != verification.variety_id
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if (
            prediction.source_ref.plan_id != verification.plan_id
            or prediction.source_ref.location_reference_id != verification.location_reference_id
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if prediction.source_ref.maturity_model_run_id != verification.maturity_model_run_id:
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if prediction.source_ref.maturity_model_version != verification.maturity_model_version:
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if (
            prediction.source_ref.maturity_model_config_hash
            != verification.maturity_model_config_hash
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_SIGNATURE_MISMATCH}:{task8_row_key}")
        if (
            prediction.source_ref.maturity_model_source_signature
            != verification.maturity_model_source_signature
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_SIGNATURE_MISMATCH}:{task8_row_key}")
        if (
            prediction.source_ref.maturity_model_artifact_id
            != verification.maturity_model_artifact_id
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if (
            prediction.source_ref.maturity_model_artifact_hash
            != verification.maturity_model_artifact_hash
        ):
            blockers.append(f"{BlockerCode.TASK8_ARTIFACT_HASH_MISMATCH}:{task8_row_key}")
        if verification.maturity_model_artifact_run_id != verification.maturity_model_run_id:
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if prediction.source_ref.maturity_forecast_run_id != verification.maturity_forecast_run_id:
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if (
            prediction.source_ref.maturity_forecast_source_signature
            != verification.maturity_forecast_source_signature
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_SIGNATURE_MISMATCH}:{task8_row_key}")
        if (
            prediction.source_ref.maturity_forecast_as_of_date
            != verification.maturity_forecast_as_of_date
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if (
            verification.maturity_forecast_model_run_id != verification.maturity_model_run_id
            or verification.maturity_forecast_artifact_id != verification.maturity_model_artifact_id
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if (
            prediction.source_ref.maturity_daily_prediction_id
            != verification.maturity_daily_prediction_id
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if (
            verification.maturity_daily_prediction_forecast_run_id
            != verification.maturity_forecast_run_id
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if prediction.prediction_date != verification.prediction_date:
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        if not (
            verification.maturity_forecast_prediction_start_date
            <= prediction.prediction_date
            <= verification.maturity_forecast_prediction_end_date
        ):
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")
        expected_quantity = {
            ForecastQuantile.P50: verification.p50_kg,
            ForecastQuantile.P80: verification.p80_kg,
            ForecastQuantile.P90: verification.p90_kg,
        }[prediction.source_ref.forecast_quantile]
        if expected_quantity != prediction.source_ref.source_quantity_kg:
            blockers.append(f"{BlockerCode.TASK8_QUANTILE_VALUE_MISMATCH}:{task8_row_key}")
        request_identity = (
            verification.maturity_model_run_id,
            verification.maturity_model_version,
            verification.maturity_model_config_hash,
            verification.maturity_model_source_signature,
            verification.maturity_model_artifact_id,
            verification.maturity_model_artifact_hash,
            verification.maturity_forecast_run_id,
            verification.maturity_forecast_source_signature,
            verification.maturity_forecast_as_of_date,
        )
        if task8_request_identity is None:
            task8_request_identity = request_identity
        elif task8_request_identity != request_identity:
            if task8_request_identity[5] != request_identity[5]:
                blockers.append(f"{BlockerCode.TASK8_ARTIFACT_HASH_MISMATCH}:{task8_row_key}")
            elif (
                task8_request_identity[1] != request_identity[1]
                or task8_request_identity[2] != request_identity[2]
                or task8_request_identity[3] != request_identity[3]
                or task8_request_identity[7] != request_identity[7]
            ):
                blockers.append(f"{BlockerCode.TASK8_SOURCE_SIGNATURE_MISMATCH}:{task8_row_key}")
            else:
                blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{task8_row_key}")

        daily_prediction_identity = verification.model_dump(mode="python")
        existing_identity = task8_daily_prediction_identity_by_id.get(
            verification.maturity_daily_prediction_id
        )
        if existing_identity is None:
            task8_daily_prediction_identity_by_id[verification.maturity_daily_prediction_id] = (
                daily_prediction_identity
            )
        elif canonical_json_value(existing_identity) != canonical_json_value(
            daily_prediction_identity
        ):
            blockers.append(
                f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{verification.maturity_daily_prediction_id}"
            )

        grain_key = (
            prediction.prediction_date,
            prediction.farm_id,
            prediction.subfarm_id,
            prediction.variety_id,
        )
        existing_daily_prediction_id = task8_daily_prediction_id_by_grain.get(grain_key)
        if existing_daily_prediction_id is None:
            task8_daily_prediction_id_by_grain[grain_key] = (
                verification.maturity_daily_prediction_id
            )
        elif existing_daily_prediction_id != verification.maturity_daily_prediction_id:
            blockers.append(f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{grain_key}")
        prediction_lookup_key = (
            prediction.source_ref.forecast_quantile,
            prediction.prediction_date,
            mapped_pool_id,
        )
        task8_daily_predictions_by_key.setdefault(prediction_lookup_key, []).append(prediction)

    initial_inventory_cohorts = request.initial_inventory_cohorts or []
    initial_cohort_keys: list[str] = []
    initial_total = Decimal("0")
    for cohort in initial_inventory_cohorts:
        source_refs.append(cohort.source_ref)
        if (
            cohort.source_ref.available_at > cohort.source_ref.as_of_date
            or cohort.source_ref.as_of_date != request.as_of_date
        ):
            blockers.append(BlockerCode.INITIAL_SOURCE_NOT_VISIBLE_AT_AS_OF)
        if not is_sha256_hex(cohort.source_ref.source_row_hash):
            blockers.append(BlockerCode.INITIAL_SOURCE_ROW_HASH_MISSING)
        member_key = _member_key(cohort.farm_id, cohort.subfarm_id, cohort.variety_id)
        mapped_pool_id = member_to_pool.get(member_key)
        if mapped_pool_id is None:
            blockers.append(f"{BlockerCode.MISSING_POOL_MEMBERSHIP}:{member_key}")
            continue
        computed_key = _compute_initial_cohort_key(
            cohort,
            capacity_pool_id=mapped_pool_id,
            capacity_pool_membership_hash=pool_membership_hash_by_pool[mapped_pool_id],
            destination_factory_id=request.destination_factory_id,
        )
        if cohort.stable_cohort_key != computed_key:
            blockers.append(f"{BlockerCode.STABLE_COHORT_KEY_MISMATCH}:{computed_key}")
        initial_cohort_keys.append(computed_key)
        initial_total += cohort.remaining_quantity_kg
    if len(set(initial_cohort_keys)) != len(initial_cohort_keys):
        blockers.append(BlockerCode.DUPLICATE_STABLE_COHORT_KEY)
    if (
        request.initial_opening_mature_inventory_kg is not None
        and initial_total != request.initial_opening_mature_inventory_kg
    ):
        blockers.append(BlockerCode.INITIAL_INVENTORY_SUM_MISMATCH)

    loss_inputs_by_key: dict[tuple[date, str, ForecastQuantile], MatureInventoryLossInput] = {}
    seen_loss_keys: set[tuple[date, str, ForecastQuantile]] = set()
    for loss_input in request.mature_inventory_loss_inputs:
        source_refs.append(loss_input.source_ref)
        loss_lookup_key = (
            loss_input.state_date,
            loss_input.capacity_pool_id,
            loss_input.forecast_quantile,
        )
        if loss_lookup_key in seen_loss_keys:
            blockers.append(f"{BlockerCode.DUPLICATE_MATURE_LOSS_INPUT}:{loss_lookup_key}")
            continue
        seen_loss_keys.add(loss_lookup_key)
        loss_inputs_by_key[loss_lookup_key] = loss_input
        if (
            loss_input.source_ref.parameter_code.value != "MATURE_INVENTORY_LOSS"
            or loss_input.source_ref.available_at > loss_input.source_ref.as_of_date
            or loss_input.source_ref.as_of_date != request.as_of_date
        ):
            blockers.append(
                f"{BlockerCode.PARAMETER_SOURCE_NOT_VISIBLE_AT_AS_OF}:{loss_input.source_ref.parameter_code}"
            )
        if not is_sha256_hex(loss_input.source_ref.source_row_hash):
            blockers.append(
                f"{BlockerCode.SOURCE_REF_HASH_MISMATCH}:{loss_input.source_ref.parameter_code}:{loss_input.source_ref.source_row_hash}"
            )

    for forecast_date in forecast_dates:
        for pool_id in pools_by_id:
            for quantile in request.forecast_quantiles:
                if (forecast_date, pool_id, quantile) not in loss_inputs_by_key:
                    blockers.append(
                        f"{BlockerCode.MISSING_MATURE_LOSS_INPUT}:{pool_id}:{forecast_date}:{quantile}"
                    )
                if (
                    quantile,
                    forecast_date,
                    pool_id,
                ) not in task8_daily_predictions_by_key or not task8_daily_predictions_by_key[
                    (quantile, forecast_date, pool_id)
                ]:
                    blockers.append(
                        f"{BlockerCode.MISSING_TASK8_INPUT}:{pool_id}:{forecast_date}:{quantile}"
                    )
                else:
                    expected_member_count = len(pools_by_id[pool_id].members)
                    actual_member_count = len(
                        task8_daily_predictions_by_key[(quantile, forecast_date, pool_id)]
                    )
                    if actual_member_count != expected_member_count:
                        blockers.append(
                            f"{BlockerCode.MISSING_TASK8_INPUT}:{pool_id}:{forecast_date}:{quantile}"
                        )

    provisional = ValidatedRequest(
        request=request,
        blockers=_sorted_blockers(blockers),
        warnings=warnings,
        pools_by_id=pools_by_id,
        pool_membership_hash_by_pool=pool_membership_hash_by_pool,
        member_to_pool=member_to_pool,
        daily_pool_parameters=daily_pool_parameters,
        weather_values_by_key=weather_values_by_key,
        task8_daily_predictions_by_key=task8_daily_predictions_by_key,
        initial_inventory_cohorts=initial_inventory_cohorts,
        initial_cohort_keys=initial_cohort_keys,
        loss_inputs_by_key=loss_inputs_by_key,
        config_hash=_config_hash(request),
        input_snapshot={},
        source_refs=source_refs,
    )
    provisional.input_snapshot = _sorted_request_snapshot(request, provisional)
    return provisional


def _blocked_output(
    request: Task9ARequest,
    validated: ValidatedRequest,
) -> Task9ABlockedOutput:
    referenced_hashes = _referenced_source_hashes_from_input_snapshot(validated.input_snapshot)
    source_ref_catalog, catalog_blockers = build_source_ref_catalog(
        validated.source_refs,
        referenced_hashes=referenced_hashes,
    )
    blockers = _sorted_blockers(validated.blockers + catalog_blockers)
    payload = {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "status": "blocked",
        "input_snapshot": validated.input_snapshot,
        "resolved_parameter_snapshot": None,
        "daily_pool_state_rows": [],
        "daily_member_state_rows": [],
        "cohort_transition_rows": [],
        "future_arrival_schedule": [],
        "source_ref_catalog": [entry.model_dump(mode="python") for entry in source_ref_catalog],
        "warnings": [],
        "blockers": blockers,
        "config_hash": validated.config_hash,
    }
    return Task9ABlockedOutput(
        input_snapshot=validated.input_snapshot,
        resolved_parameter_snapshot=None,
        source_ref_catalog=source_ref_catalog,
        warnings=[],
        blockers=blockers,
        config_hash=validated.config_hash,
        result_hash=make_result_hash(payload),
    )


def _referenced_source_hashes_from_input_snapshot(snapshot: dict[str, Any]) -> set[str]:
    referenced: set[str] = set()
    referenced.update(snapshot.get("run_parameter_source_ref_hashes", []))
    for item in snapshot.get("daily_capacity_inputs", []):
        referenced.update(item.get("capacity_parameter_source_ref_hashes", []))
    for item in snapshot.get("daily_weather_features", []):
        if item.get("source_ref_hash"):
            referenced.add(item["source_ref_hash"])
    for item in snapshot.get("task8_daily_predictions", []):
        if item.get("source_ref_hash"):
            referenced.add(item["source_ref_hash"])
    for item in snapshot.get("initial_inventory_cohorts", []):
        if item.get("source_ref_hash"):
            referenced.add(item["source_ref_hash"])
    for item in snapshot.get("mature_inventory_loss_inputs", []):
        if item.get("source_ref_hash"):
            referenced.add(item["source_ref_hash"])
    return referenced


def _referenced_source_hashes_from_completed_output(
    *,
    input_snapshot: dict[str, Any],
    resolved_snapshot: ResolvedParameterSnapshot,
    pool_rows: list[DailyPoolStateRow],
    member_rows: list[DailyMemberStateRow],
    cohort_rows: list[CohortTransitionRow],
) -> set[str]:
    referenced = _referenced_source_hashes_from_input_snapshot(input_snapshot)
    for item in resolved_snapshot.daily_pool_parameters:
        referenced.update(item.capacity_parameter_source_ref_hashes)
        referenced.update(item.weather_feature_source_ref_hashes)
    for pool_row in pool_rows:
        referenced.update(pool_row.parameter_source_ref_hashes)
        referenced.update(pool_row.cohort_source_ref_hashes)
    for member_row in member_rows:
        referenced.update(member_row.cohort_source_ref_hashes)
    for cohort_row in cohort_rows:
        referenced.add(cohort_row.source_ref_hash)
    return referenced


DISPLAY_TOLERANCE_KG = Decimal("0.001")


def _within_display_tolerance(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= DISPLAY_TOLERANCE_KG


def _display_reconciliation_blockers(
    *,
    pool_rows: list[DailyPoolStateRow],
    member_rows: list[DailyMemberStateRow],
    cohort_rows: list[CohortTransitionRow],
    forecast_start_date: date,
    forecast_end_date: date,
) -> list[str]:
    blockers: list[str] = []

    for row in cohort_rows:
        if not _within_display_tolerance(
            row.quantity_before_loss_kg,
            row.opening_quantity_kg + row.new_supply_quantity_kg,
        ):
            blockers.append(
                f"{BlockerCode.COHORT_TRANSITION_EQUATION_FAILED}:{row.capacity_pool_id}:{row.state_date}:{row.stable_cohort_key}"
            )
        if not _within_display_tolerance(
            row.quantity_before_harvest_kg,
            row.quantity_before_loss_kg - row.mature_inventory_loss_quantity_kg,
        ):
            blockers.append(
                f"{BlockerCode.COHORT_TRANSITION_EQUATION_FAILED}:{row.capacity_pool_id}:{row.state_date}:{row.stable_cohort_key}"
            )
        if not _within_display_tolerance(
            row.closing_quantity_kg,
            row.quantity_before_harvest_kg - row.harvested_quantity_kg,
        ):
            blockers.append(
                f"{BlockerCode.COHORT_TRANSITION_EQUATION_FAILED}:{row.capacity_pool_id}:{row.state_date}:{row.stable_cohort_key}"
            )

    member_sums: dict[
        tuple[date, str, int, int | None, int, ForecastQuantile], dict[str, Decimal]
    ] = {}
    member_arrival_sums: dict[
        tuple[date, str, int, int | None, int, ForecastQuantile], Decimal
    ] = {}
    for row in cohort_rows:
        key = (
            row.state_date,
            row.capacity_pool_id,
            row.farm_id,
            row.subfarm_id,
            row.variety_id,
            row.forecast_quantile,
        )
        bucket = member_sums.setdefault(
            key,
            {
                "opening_mature_inventory_kg": Decimal("0"),
                "natural_maturity_supply_kg": Decimal("0"),
                "available_mature_quantity_kg": Decimal("0"),
                "mature_inventory_loss_quantity_kg": Decimal("0"),
                "harvestable_mature_quantity_kg": Decimal("0"),
                "harvested_quantity_kg": Decimal("0"),
                "closing_mature_inventory_kg": Decimal("0"),
                "unharvested_backlog_kg": Decimal("0"),
                "arrival_quantity_kg": Decimal("0"),
            },
        )
        bucket["opening_mature_inventory_kg"] += row.opening_quantity_kg
        bucket["natural_maturity_supply_kg"] += row.new_supply_quantity_kg
        bucket["available_mature_quantity_kg"] += row.quantity_before_loss_kg
        bucket["mature_inventory_loss_quantity_kg"] += row.mature_inventory_loss_quantity_kg
        bucket["harvestable_mature_quantity_kg"] += row.quantity_before_harvest_kg
        bucket["harvested_quantity_kg"] += row.harvested_quantity_kg
        bucket["closing_mature_inventory_kg"] += row.closing_quantity_kg
        bucket["unharvested_backlog_kg"] += row.closing_quantity_kg
        if (
            row.arrival_local_date is not None
            and forecast_start_date <= row.arrival_local_date <= forecast_end_date
        ):
            arrival_key = (
                row.arrival_local_date,
                row.capacity_pool_id,
                row.farm_id,
                row.subfarm_id,
                row.variety_id,
                row.forecast_quantile,
            )
            member_arrival_sums[arrival_key] = (
                member_arrival_sums.get(arrival_key, Decimal("0")) + row.arrival_quantity_kg
            )

    zero_member_bucket = {
        "opening_mature_inventory_kg": Decimal("0"),
        "natural_maturity_supply_kg": Decimal("0"),
        "available_mature_quantity_kg": Decimal("0"),
        "mature_inventory_loss_quantity_kg": Decimal("0"),
        "harvestable_mature_quantity_kg": Decimal("0"),
        "harvested_quantity_kg": Decimal("0"),
        "closing_mature_inventory_kg": Decimal("0"),
        "unharvested_backlog_kg": Decimal("0"),
    }
    member_fields = tuple(zero_member_bucket.keys())
    for member_row in member_rows:
        member_display_key = (
            member_row.state_date,
            member_row.capacity_pool_id,
            member_row.farm_id,
            member_row.subfarm_id,
            member_row.variety_id,
            member_row.forecast_quantile,
        )
        bucket = member_sums.get(member_display_key, zero_member_bucket)
        for field_name in member_fields:
            if not _within_display_tolerance(getattr(member_row, field_name), bucket[field_name]):
                blockers.append(
                    f"{BlockerCode.POOL_COHORT_SUM_MISMATCH}:{member_row.capacity_pool_id}:{member_row.state_date}:{member_row.forecast_quantile}:{member_row.farm_id}:{member_row.subfarm_id}:{member_row.variety_id}"
                )
                break
        expected_arrival = member_arrival_sums.get(member_display_key, Decimal("0"))
        if not _within_display_tolerance(member_row.arrival_quantity_kg, expected_arrival):
            blockers.append(
                f"{BlockerCode.POOL_COHORT_SUM_MISMATCH}:{member_row.capacity_pool_id}:{member_row.state_date}:{member_row.forecast_quantile}:{member_row.farm_id}:{member_row.subfarm_id}:{member_row.variety_id}"
            )

    pool_sums: dict[tuple[date, str, ForecastQuantile], dict[str, Decimal]] = {}
    pool_arrival_sums: dict[tuple[date, str, ForecastQuantile], Decimal] = {}
    for member_row in member_rows:
        pool_display_key = (
            member_row.state_date,
            member_row.capacity_pool_id,
            member_row.forecast_quantile,
        )
        bucket = pool_sums.setdefault(
            pool_display_key,
            {
                "opening_mature_inventory_kg": Decimal("0"),
                "natural_maturity_supply_kg": Decimal("0"),
                "available_mature_quantity_kg": Decimal("0"),
                "mature_inventory_loss_quantity_kg": Decimal("0"),
                "harvestable_mature_quantity_kg": Decimal("0"),
                "harvested_quantity_kg": Decimal("0"),
                "closing_mature_inventory_kg": Decimal("0"),
                "unharvested_backlog_kg": Decimal("0"),
                "arrival_quantity_kg": Decimal("0"),
            },
        )
        bucket["opening_mature_inventory_kg"] += member_row.opening_mature_inventory_kg
        bucket["natural_maturity_supply_kg"] += member_row.natural_maturity_supply_kg
        bucket["available_mature_quantity_kg"] += member_row.available_mature_quantity_kg
        bucket["mature_inventory_loss_quantity_kg"] += member_row.mature_inventory_loss_quantity_kg
        bucket["harvestable_mature_quantity_kg"] += member_row.harvestable_mature_quantity_kg
        bucket["harvested_quantity_kg"] += member_row.harvested_quantity_kg
        bucket["closing_mature_inventory_kg"] += member_row.closing_mature_inventory_kg
        bucket["unharvested_backlog_kg"] += member_row.unharvested_backlog_kg
        pool_arrival_sums[pool_display_key] = (
            pool_arrival_sums.get(pool_display_key, Decimal("0")) + member_row.arrival_quantity_kg
        )

    zero_pool_bucket = {
        "opening_mature_inventory_kg": Decimal("0"),
        "natural_maturity_supply_kg": Decimal("0"),
        "available_mature_quantity_kg": Decimal("0"),
        "mature_inventory_loss_quantity_kg": Decimal("0"),
        "harvestable_mature_quantity_kg": Decimal("0"),
        "harvested_quantity_kg": Decimal("0"),
        "closing_mature_inventory_kg": Decimal("0"),
        "unharvested_backlog_kg": Decimal("0"),
    }
    pool_fields = tuple(zero_pool_bucket.keys())
    for pool_row in pool_rows:
        pool_display_key = (
            pool_row.state_date,
            pool_row.capacity_pool_id,
            pool_row.forecast_quantile,
        )
        bucket = pool_sums.get(pool_display_key, zero_pool_bucket)
        for field_name in pool_fields:
            if not _within_display_tolerance(getattr(pool_row, field_name), bucket[field_name]):
                blockers.append(
                    f"{BlockerCode.POOL_MEMBER_SUM_MISMATCH}:{pool_row.capacity_pool_id}:{pool_row.state_date}:{pool_row.forecast_quantile}"
                )
                break
        expected_arrival = pool_arrival_sums.get(pool_display_key, Decimal("0"))
        if not _within_display_tolerance(pool_row.arrival_quantity_kg, expected_arrival):
            blockers.append(
                f"{BlockerCode.POOL_MEMBER_SUM_MISMATCH}:{pool_row.capacity_pool_id}:{pool_row.state_date}:{pool_row.forecast_quantile}"
            )

    return _sorted_blockers(blockers)


def run_harvest_state_model(
    payload: Mapping[str, object] | Task9ARequest,
) -> Task9ACompletedOutput | Task9ABlockedOutput:
    if not isinstance(payload, Task9ARequest):
        try:
            request = Task9ARequest.model_validate(payload)
        except ValidationError as exc:
            return _blocked_from_raw_payload(payload, _map_validation_error_codes(exc))
    else:
        request = payload
    validated = _validated_request(request)
    if validated.blockers:
        return _blocked_output(request, validated)

    source_ref_catalog, catalog_blockers = build_source_ref_catalog(validated.source_refs)
    if catalog_blockers:
        validated.blockers.extend(catalog_blockers)
        return _blocked_output(request, validated)

    run_parameters = RunResolvedParameters(
        forecast_start_date=request.forecast_start_date,
        forecast_end_date=request.forecast_end_date,
        forecast_quantiles=list(request.forecast_quantiles),
        destination_factory_id=request.destination_factory_id,
        farm_timezone=request.farm_timezone,
        destination_factory_timezone=request.destination_factory_timezone,
        harvest_bucket_anchor_local_time=request.harvest_bucket_anchor_local_time,
        harvest_to_arrival_lag_days=request.harvest_to_arrival_lag_days,
        holiday_calendar_version=request.holiday_calendar_version,
        holiday_calendar_hash=_holiday_calendar_hash(request),
        weather_rule_version=request.weather_rule_config.version,
        weather_rule_config_hash=_weather_rule_config_hash(request),
        decimal_precision=28,
        quantity_scale="0.001",
        ratio_scale="0.000001",
        rounding_mode="ROUND_HALF_UP",
        source_ref_schema_version=SOURCE_REF_SCHEMA_VERSION,
        stable_cohort_key_schema_version=STABLE_COHORT_KEY_SCHEMA_VERSION,
        result_hash_schema_version=RESULT_HASH_SCHEMA_VERSION,
    )
    resolved_snapshot = ResolvedParameterSnapshot(
        run_parameters=run_parameters,
        daily_pool_parameters=[
            DailyPoolResolvedParameters(
                capacity_date=params.capacity_date,
                capacity_pool_id=params.capacity_pool_id,
                capacity_pool_grain=params.capacity_pool_grain,
                capacity_pool_membership_hash=params.capacity_pool_membership_hash,
                capacity_input_mode=params.capacity_input_mode,
                planned_picker_count=(
                    None
                    if params.planned_picker_count is None
                    else quantize_quantity(params.planned_picker_count)
                ),
                kg_per_person_per_day=(
                    None
                    if params.kg_per_person_per_day is None
                    else quantize_quantity(params.kg_per_person_per_day)
                ),
                direct_nominal_capacity_kg_per_day=(
                    None
                    if params.direct_nominal_capacity_kg_per_day is None
                    else quantize_quantity(params.direct_nominal_capacity_kg_per_day)
                ),
                resolved_nominal_capacity_kg_per_day=quantize_quantity(
                    params.resolved_nominal_capacity_kg_per_day
                ),
                labor_availability_ratio=quantize_ratio(params.labor_availability_ratio),
                weather_harvest_efficiency_ratio=quantize_ratio(
                    params.weather_harvest_efficiency_ratio
                ),
                operational_efficiency_ratio=quantize_ratio(params.operational_efficiency_ratio),
                resolved_effective_capacity_kg_per_day=quantize_quantity(
                    params.resolved_effective_capacity_kg_per_day
                ),
                holiday_applied=params.holiday_applied,
                capacity_parameter_source_ref_hashes=params.capacity_parameter_source_ref_hashes,
                weather_feature_source_ref_hashes=params.weather_feature_source_ref_hashes,
            )
            for _, params in sorted(
                validated.daily_pool_parameters.items(),
                key=lambda item: (item[0][0], item[0][1]),
            )
        ],
    )

    cohort_row_inputs: list[dict[str, Any]] = []
    member_row_inputs: list[dict[str, Any]] = []
    pool_row_inputs: list[dict[str, Any]] = []

    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_UP
        for quantile in request.forecast_quantiles:
            current_cohorts: list[dict[str, Any]] = []
            seen_cohort_identity_by_key: dict[str, dict[str, Any]] = {}
            for initial_cohort in validated.initial_inventory_cohorts:
                if initial_cohort.forecast_quantile is not quantile:
                    continue
                member_key = _member_key(
                    initial_cohort.farm_id,
                    initial_cohort.subfarm_id,
                    initial_cohort.variety_id,
                )
                pool_id = validated.member_to_pool[member_key]
                membership_hash = validated.pool_membership_hash_by_pool[pool_id]
                stable_key = _compute_initial_cohort_key(
                    initial_cohort,
                    capacity_pool_id=pool_id,
                    capacity_pool_membership_hash=membership_hash,
                    destination_factory_id=request.destination_factory_id,
                )
                identity_payload = {
                    "source_ref_hash": source_ref_hash(initial_cohort.source_ref),
                    "pool_id": pool_id,
                    "farm_id": initial_cohort.farm_id,
                    "subfarm_id": initial_cohort.subfarm_id,
                    "variety_id": initial_cohort.variety_id,
                    "cohort_date": initial_cohort.cohort_date,
                    "forecast_quantile": quantile,
                }
                existing = seen_cohort_identity_by_key.get(stable_key)
                if existing is not None and canonical_json_value(existing) != canonical_json_value(
                    identity_payload
                ):
                    validated.blockers.append(
                        f"{BlockerCode.COHORT_IDENTITY_COLLISION}:{stable_key}"
                    )
                    return _blocked_output(request, validated)
                if existing is not None:
                    validated.blockers.append(
                        f"{BlockerCode.DUPLICATE_STABLE_COHORT_KEY}:{stable_key}"
                    )
                    return _blocked_output(request, validated)
                seen_cohort_identity_by_key[stable_key] = identity_payload
                current_cohorts.append(
                    {
                        "stable_cohort_key": stable_key,
                        "source_ref_hash": identity_payload["source_ref_hash"],
                        "capacity_pool_id": pool_id,
                        "capacity_pool_membership_hash": membership_hash,
                        "farm_id": initial_cohort.farm_id,
                        "subfarm_id": initial_cohort.subfarm_id,
                        "variety_id": initial_cohort.variety_id,
                        "cohort_date": initial_cohort.cohort_date,
                        "forecast_quantile": quantile,
                        "remaining_quantity_kg": initial_cohort.remaining_quantity_kg,
                    }
                )

            previous_day_closing_by_key: dict[str, Decimal] = {}
            date_count = (request.forecast_end_date - request.forecast_start_date).days + 1
            for offset in range(date_count):
                state_date = request.forecast_start_date + timedelta(days=offset)
                day_opening_by_key: dict[str, Decimal] = {}
                day_closing_by_key: dict[str, Decimal] = {}
                day_member_inputs: list[dict[str, Any]] = []
                day_pool_inputs: list[dict[str, Any]] = []
                for pool_id, pool in sorted(
                    validated.pools_by_id.items(), key=lambda item: item[0]
                ):
                    params = validated.daily_pool_parameters[(state_date, pool_id)]
                    member_keys = [
                        _member_key(member.farm_id, member.subfarm_id, member.variety_id)
                        for member in sorted(pool.members, key=_member_sort_key)
                    ]
                    opening_cohorts = [
                        cohort
                        for cohort in current_cohorts
                        if cohort["capacity_pool_id"] == pool_id
                        and cohort["remaining_quantity_kg"] > 0
                    ]
                    opening_qty_map = {
                        str(cohort["stable_cohort_key"]): cohort["remaining_quantity_kg"]
                        for cohort in opening_cohorts
                    }
                    day_opening_by_key.update(opening_qty_map)

                    new_predictions = validated.task8_daily_predictions_by_key.get(
                        (quantile, state_date, pool_id),
                        [],
                    )
                    new_cohorts: list[dict[str, Any]] = []
                    for prediction in sorted(
                        new_predictions,
                        key=lambda item: (
                            item.prediction_date,
                            item.variety_id,
                            -1 if item.subfarm_id is None else item.subfarm_id,
                        ),
                    ):
                        stable_key = _compute_task8_cohort_key(
                            prediction,
                            capacity_pool_id=pool_id,
                            capacity_pool_membership_hash=validated.pool_membership_hash_by_pool[
                                pool_id
                            ],
                            destination_factory_id=request.destination_factory_id,
                        )
                        identity_payload = {
                            "source_ref_hash": source_ref_hash(prediction.source_ref),
                            "pool_id": pool_id,
                            "farm_id": prediction.farm_id,
                            "subfarm_id": prediction.subfarm_id,
                            "variety_id": prediction.variety_id,
                            "cohort_date": prediction.prediction_date,
                            "forecast_quantile": quantile,
                        }
                        existing = seen_cohort_identity_by_key.get(stable_key)
                        if existing is not None and canonical_json_value(
                            existing
                        ) != canonical_json_value(identity_payload):
                            validated.blockers.append(
                                f"{BlockerCode.COHORT_IDENTITY_COLLISION}:{stable_key}"
                            )
                            return _blocked_output(request, validated)
                        if existing is not None:
                            validated.blockers.append(
                                f"{BlockerCode.DUPLICATE_STABLE_COHORT_KEY}:{stable_key}"
                            )
                            return _blocked_output(request, validated)
                        seen_cohort_identity_by_key[stable_key] = identity_payload
                        new_cohorts.append(
                            {
                                "stable_cohort_key": stable_key,
                                "source_ref_hash": identity_payload["source_ref_hash"],
                                "capacity_pool_id": pool_id,
                                "capacity_pool_membership_hash": (
                                    validated.pool_membership_hash_by_pool[pool_id]
                                ),
                                "farm_id": prediction.farm_id,
                                "subfarm_id": prediction.subfarm_id,
                                "variety_id": prediction.variety_id,
                                "cohort_date": prediction.prediction_date,
                                "forecast_quantile": quantile,
                                "remaining_quantity_kg": prediction.source_ref.source_quantity_kg,
                            }
                        )

                    current_cohorts.extend(new_cohorts)
                    fifo_cohorts = sorted(
                        [
                            cohort
                            for cohort in current_cohorts
                            if cohort["capacity_pool_id"] == pool_id
                        ],
                        key=_cohort_sort_key,
                    )
                    new_supply_qty_map = {
                        str(cohort["stable_cohort_key"]): cohort["remaining_quantity_kg"]
                        for cohort in new_cohorts
                    }
                    before_loss_map = {
                        str(cohort["stable_cohort_key"]): cohort["remaining_quantity_kg"]
                        for cohort in fifo_cohorts
                    }
                    available_total = sum(before_loss_map.values(), Decimal("0"))
                    loss_input = validated.loss_inputs_by_key[(state_date, pool_id, quantile)]
                    if loss_input.mature_inventory_loss_quantity_kg > available_total:
                        validated.blockers.append(
                            f"{BlockerCode.MATURE_LOSS_EXCEEDS_AVAILABLE}:{pool_id}:{state_date}:{quantile}"
                        )
                        return _blocked_output(request, validated)

                    loss_allocations = allocate_fifo_loss(
                        fifo_cohorts,
                        loss_input.mature_inventory_loss_quantity_kg,
                    )
                    loss_map = {
                        item.stable_cohort_key: item.loss_quantity_kg for item in loss_allocations
                    }
                    before_harvest_map = {
                        str(cohort["stable_cohort_key"]): cohort["remaining_quantity_kg"]
                        for cohort in fifo_cohorts
                    }
                    harvest_allocations = allocate_fifo_harvest(
                        fifo_cohorts,
                        params.resolved_effective_capacity_kg_per_day,
                    )
                    harvest_map = {
                        item.stable_cohort_key: item.harvested_quantity_kg
                        for item in harvest_allocations
                    }
                    closing_map = {
                        str(cohort["stable_cohort_key"]): cohort["remaining_quantity_kg"]
                        for cohort in fifo_cohorts
                    }

                    pool_cohort_inputs: list[dict[str, Any]] = []
                    for working_cohort in fifo_cohorts:
                        stable_key = str(working_cohort["stable_cohort_key"])
                        harvested_quantity = harvest_map.get(stable_key, Decimal("0"))
                        arrival_payload: dict[str, Any] = {
                            "harvest_anchor_at": None,
                            "arrival_at": None,
                            "arrival_local_date": None,
                        }
                        if harvested_quantity > 0:
                            arrival_payload = resolve_harvest_arrival(
                                harvest_local_date=state_date,
                                harvest_bucket_anchor_local_time=request.harvest_bucket_anchor_local_time,
                                farm_timezone=request.farm_timezone,
                                destination_factory_timezone=request.destination_factory_timezone,
                                harvest_to_arrival_lag_days=request.harvest_to_arrival_lag_days,
                            )

                        cohort_input = {
                            "state_date": state_date,
                            "forecast_quantile": quantile,
                            "capacity_pool_id": pool_id,
                            "farm_id": int(working_cohort["farm_id"]),
                            "subfarm_id": working_cohort["subfarm_id"],
                            "variety_id": int(working_cohort["variety_id"]),
                            "destination_factory_id": request.destination_factory_id,
                            "stable_cohort_key": stable_key,
                            "source_ref_hash": str(working_cohort["source_ref_hash"]),
                            "cohort_date": working_cohort["cohort_date"],
                            "opening_quantity_kg": opening_qty_map.get(stable_key, Decimal("0")),
                            "new_supply_quantity_kg": new_supply_qty_map.get(
                                stable_key, Decimal("0")
                            ),
                            "quantity_before_loss_kg": before_loss_map[stable_key],
                            "mature_inventory_loss_quantity_kg": loss_map.get(
                                stable_key, Decimal("0")
                            ),
                            "quantity_before_harvest_kg": before_harvest_map[stable_key],
                            "harvested_quantity_kg": harvested_quantity,
                            "closing_quantity_kg": closing_map[stable_key],
                            "harvest_anchor_at": arrival_payload["harvest_anchor_at"],
                            "arrival_at": arrival_payload["arrival_at"],
                            "arrival_local_date": arrival_payload["arrival_local_date"],
                            "arrival_quantity_kg": harvested_quantity,
                        }
                        if (
                            (
                                cohort_input["quantity_before_loss_kg"]
                                != cohort_input["opening_quantity_kg"]
                                + cohort_input["new_supply_quantity_kg"]
                            )
                            or (
                                cohort_input["quantity_before_harvest_kg"]
                                != cohort_input["quantity_before_loss_kg"]
                                - cohort_input["mature_inventory_loss_quantity_kg"]
                            )
                            or (
                                cohort_input["closing_quantity_kg"]
                                != cohort_input["quantity_before_harvest_kg"]
                                - cohort_input["harvested_quantity_kg"]
                            )
                        ):
                            validated.blockers.append(
                                f"{BlockerCode.COHORT_TRANSITION_EQUATION_FAILED}:{pool_id}:{state_date}:{stable_key}"
                            )
                            return _blocked_output(request, validated)
                        pool_cohort_inputs.append(cohort_input)
                        if closing_map[stable_key] > 0:
                            day_closing_by_key[stable_key] = closing_map[stable_key]

                    current_cohorts = [
                        cohort for cohort in current_cohorts if cohort["remaining_quantity_kg"] > 0
                    ]

                    for member_key in member_keys:
                        farm_id, subfarm_id, variety_id = member_key
                        member_rows_for_day = [
                            row
                            for row in pool_cohort_inputs
                            if row["farm_id"] == farm_id
                            and row["subfarm_id"] == subfarm_id
                            and row["variety_id"] == variety_id
                        ]
                        day_member_inputs.append(
                            {
                                "state_date": state_date,
                                "forecast_quantile": quantile,
                                "capacity_pool_id": pool_id,
                                "capacity_pool_grain": pool.capacity_pool_grain,
                                "capacity_pool_membership_hash": (
                                    validated.pool_membership_hash_by_pool[pool_id]
                                ),
                                "farm_id": farm_id,
                                "subfarm_id": subfarm_id,
                                "variety_id": variety_id,
                                "destination_factory_id": request.destination_factory_id,
                                "opening_mature_inventory_kg": sum(
                                    (row["opening_quantity_kg"] for row in member_rows_for_day),
                                    Decimal("0"),
                                ),
                                "natural_maturity_supply_kg": sum(
                                    (row["new_supply_quantity_kg"] for row in member_rows_for_day),
                                    Decimal("0"),
                                ),
                                "available_mature_quantity_kg": sum(
                                    (row["quantity_before_loss_kg"] for row in member_rows_for_day),
                                    Decimal("0"),
                                ),
                                "mature_inventory_loss_quantity_kg": sum(
                                    (
                                        row["mature_inventory_loss_quantity_kg"]
                                        for row in member_rows_for_day
                                    ),
                                    Decimal("0"),
                                ),
                                "harvestable_mature_quantity_kg": sum(
                                    (
                                        row["quantity_before_harvest_kg"]
                                        for row in member_rows_for_day
                                    ),
                                    Decimal("0"),
                                ),
                                "allocated_harvest_capacity_kg": sum(
                                    (row["harvested_quantity_kg"] for row in member_rows_for_day),
                                    Decimal("0"),
                                ),
                                "harvested_quantity_kg": sum(
                                    (row["harvested_quantity_kg"] for row in member_rows_for_day),
                                    Decimal("0"),
                                ),
                                "closing_mature_inventory_kg": sum(
                                    (row["closing_quantity_kg"] for row in member_rows_for_day),
                                    Decimal("0"),
                                ),
                                "unharvested_backlog_kg": sum(
                                    (row["closing_quantity_kg"] for row in member_rows_for_day),
                                    Decimal("0"),
                                ),
                                "opening_cohort_count": sum(
                                    1
                                    for row in member_rows_for_day
                                    if row["opening_quantity_kg"] > 0
                                ),
                                "closing_cohort_count": sum(
                                    1
                                    for row in member_rows_for_day
                                    if row["closing_quantity_kg"] > 0
                                ),
                                "cohort_source_ref_hashes": sorted(
                                    {str(row["source_ref_hash"]) for row in member_rows_for_day}
                                ),
                            }
                        )

                    pool_opening = _sum_member_field(
                        day_member_inputs,
                        pool_id=pool_id,
                        field_name="opening_mature_inventory_kg",
                    )
                    pool_supply = _sum_member_field(
                        day_member_inputs,
                        pool_id=pool_id,
                        field_name="natural_maturity_supply_kg",
                    )
                    pool_available = _sum_member_field(
                        day_member_inputs,
                        pool_id=pool_id,
                        field_name="available_mature_quantity_kg",
                    )
                    pool_loss = _sum_member_field(
                        day_member_inputs,
                        pool_id=pool_id,
                        field_name="mature_inventory_loss_quantity_kg",
                    )
                    pool_harvestable = _sum_member_field(
                        day_member_inputs,
                        pool_id=pool_id,
                        field_name="harvestable_mature_quantity_kg",
                    )
                    pool_harvested = _sum_member_field(
                        day_member_inputs,
                        pool_id=pool_id,
                        field_name="harvested_quantity_kg",
                    )
                    pool_closing = _sum_member_field(
                        day_member_inputs,
                        pool_id=pool_id,
                        field_name="closing_mature_inventory_kg",
                    )
                    day_pool_inputs.append(
                        {
                            "state_date": state_date,
                            "forecast_quantile": quantile,
                            "capacity_pool_id": pool_id,
                            "capacity_pool_grain": pool.capacity_pool_grain,
                            "capacity_pool_membership_hash": validated.pool_membership_hash_by_pool[
                                pool_id
                            ],
                            "capacity_input_mode": params.capacity_input_mode,
                            "opening_mature_inventory_kg": pool_opening,
                            "natural_maturity_supply_kg": pool_supply,
                            "available_mature_quantity_kg": pool_available,
                            "mature_inventory_loss_quantity_kg": pool_loss,
                            "harvestable_mature_quantity_kg": pool_harvestable,
                            "nominal_harvest_capacity_kg_per_day": (
                                params.resolved_nominal_capacity_kg_per_day
                            ),
                            "labor_availability_ratio": params.labor_availability_ratio,
                            "weather_harvest_efficiency_ratio": (
                                params.weather_harvest_efficiency_ratio
                            ),
                            "operational_efficiency_ratio": params.operational_efficiency_ratio,
                            "effective_harvest_capacity_kg_per_day": (
                                params.resolved_effective_capacity_kg_per_day
                            ),
                            "effective_capacity_for_day_kg": (
                                params.resolved_effective_capacity_kg_per_day
                            ),
                            "harvested_quantity_kg": pool_harvested,
                            "closing_mature_inventory_kg": pool_closing,
                            "unharvested_backlog_kg": pool_closing,
                            "opening_cohort_count": sum(
                                1 for row in pool_cohort_inputs if row["opening_quantity_kg"] > 0
                            ),
                            "closing_cohort_count": sum(
                                1 for row in pool_cohort_inputs if row["closing_quantity_kg"] > 0
                            ),
                            "member_count": len(member_keys),
                            "mass_balance_passed": (
                                pool_opening + pool_supply
                                == pool_loss + pool_harvested + pool_closing
                            ),
                            "capacity_constraint_passed": (
                                pool_harvested <= pool_available
                                and pool_harvested <= params.resolved_effective_capacity_kg_per_day
                            ),
                            "parameter_source_ref_hashes": sorted(
                                params.capacity_parameter_source_ref_hashes
                                + params.weather_feature_source_ref_hashes
                            ),
                            "cohort_source_ref_hashes": sorted(
                                {str(row["source_ref_hash"]) for row in pool_cohort_inputs}
                            ),
                        }
                    )
                    cohort_row_inputs.extend(pool_cohort_inputs)

                continuity_passed = True
                if offset > 0:
                    continuity_passed = canonical_json_value(
                        day_opening_by_key
                    ) == canonical_json_value(previous_day_closing_by_key)
                    if not continuity_passed:
                        validated.blockers.append(BlockerCode.COHORT_KEY_CHANGED_ACROSS_DAYS)
                        return _blocked_output(request, validated)
                for row in day_pool_inputs:
                    row["continuity_passed"] = continuity_passed
                    if not row["mass_balance_passed"]:
                        validated.blockers.append(
                            f"{BlockerCode.COHORT_TRANSITION_EQUATION_FAILED}:{row['capacity_pool_id']}:{row['state_date']}:{row['forecast_quantile']}"
                        )
                        return _blocked_output(request, validated)
                    if not row["capacity_constraint_passed"]:
                        validated.blockers.append(
                            f"{BlockerCode.CAPACITY_COPIED_TO_MEMBER_ROWS}:{row['capacity_pool_id']}:{row['state_date']}:{row['forecast_quantile']}"
                        )
                        return _blocked_output(request, validated)
                previous_day_closing_by_key = day_closing_by_key
                member_row_inputs.extend(day_member_inputs)
                pool_row_inputs.extend(day_pool_inputs)

    arrival_by_member_key: dict[
        tuple[date, str, int, int | None, int, ForecastQuantile], Decimal
    ] = {}
    arrival_by_pool_key: dict[tuple[date, str, ForecastQuantile], Decimal] = {}
    future_arrivals: dict[
        tuple[int, date, str, int, int | None, int, ForecastQuantile], Decimal
    ] = {}
    for row in cohort_row_inputs:
        harvested_quantity = row["harvested_quantity_kg"]
        arrival_local_date = row["arrival_local_date"]
        if harvested_quantity <= 0 or arrival_local_date is None:
            continue
        member_arrival_key = (
            arrival_local_date,
            row["capacity_pool_id"],
            row["farm_id"],
            row["subfarm_id"],
            row["variety_id"],
            row["forecast_quantile"],
        )
        pool_arrival_key = (
            arrival_local_date,
            row["capacity_pool_id"],
            row["forecast_quantile"],
        )
        if request.forecast_start_date <= arrival_local_date <= request.forecast_end_date:
            arrival_by_member_key[member_arrival_key] = (
                arrival_by_member_key.get(member_arrival_key, Decimal("0")) + harvested_quantity
            )
            arrival_by_pool_key[pool_arrival_key] = (
                arrival_by_pool_key.get(pool_arrival_key, Decimal("0")) + harvested_quantity
            )
        else:
            future_key = (
                row["destination_factory_id"],
                arrival_local_date,
                row["capacity_pool_id"],
                row["farm_id"],
                row["subfarm_id"],
                row["variety_id"],
                row["forecast_quantile"],
            )
            future_arrivals[future_key] = (
                future_arrivals.get(future_key, Decimal("0")) + harvested_quantity
            )

    all_member_rows = sorted(
        [
            DailyMemberStateRow(
                state_date=row["state_date"],
                forecast_quantile=row["forecast_quantile"],
                capacity_pool_id=row["capacity_pool_id"],
                capacity_pool_grain=row["capacity_pool_grain"],
                capacity_pool_membership_hash=row["capacity_pool_membership_hash"],
                farm_id=row["farm_id"],
                subfarm_id=row["subfarm_id"],
                variety_id=row["variety_id"],
                destination_factory_id=row["destination_factory_id"],
                opening_mature_inventory_kg=quantize_quantity(row["opening_mature_inventory_kg"]),
                natural_maturity_supply_kg=quantize_quantity(row["natural_maturity_supply_kg"]),
                available_mature_quantity_kg=quantize_quantity(row["available_mature_quantity_kg"]),
                mature_inventory_loss_quantity_kg=quantize_quantity(
                    row["mature_inventory_loss_quantity_kg"]
                ),
                harvestable_mature_quantity_kg=quantize_quantity(
                    row["harvestable_mature_quantity_kg"]
                ),
                allocated_harvest_capacity_kg=quantize_quantity(
                    row["allocated_harvest_capacity_kg"]
                ),
                harvested_quantity_kg=quantize_quantity(row["harvested_quantity_kg"]),
                closing_mature_inventory_kg=quantize_quantity(row["closing_mature_inventory_kg"]),
                unharvested_backlog_kg=quantize_quantity(row["unharvested_backlog_kg"]),
                arrival_quantity_kg=quantize_quantity(
                    arrival_by_member_key.get(
                        (
                            row["state_date"],
                            row["capacity_pool_id"],
                            row["farm_id"],
                            row["subfarm_id"],
                            row["variety_id"],
                            row["forecast_quantile"],
                        ),
                        Decimal("0"),
                    )
                ),
                opening_cohort_count=row["opening_cohort_count"],
                closing_cohort_count=row["closing_cohort_count"],
                cohort_source_ref_hashes=row["cohort_source_ref_hashes"],
            )
            for row in member_row_inputs
        ],
        key=lambda row: (
            row.state_date,
            row.capacity_pool_id,
            row.farm_id,
            -1 if row.subfarm_id is None else row.subfarm_id,
            row.variety_id,
            _forecast_quantile_sort_key(row.forecast_quantile),
        ),
    )
    all_pool_rows = sorted(
        [
            DailyPoolStateRow(
                state_date=row["state_date"],
                forecast_quantile=row["forecast_quantile"],
                capacity_pool_id=row["capacity_pool_id"],
                capacity_pool_grain=row["capacity_pool_grain"],
                capacity_pool_membership_hash=row["capacity_pool_membership_hash"],
                capacity_input_mode=row["capacity_input_mode"],
                opening_mature_inventory_kg=quantize_quantity(row["opening_mature_inventory_kg"]),
                natural_maturity_supply_kg=quantize_quantity(row["natural_maturity_supply_kg"]),
                available_mature_quantity_kg=quantize_quantity(row["available_mature_quantity_kg"]),
                mature_inventory_loss_quantity_kg=quantize_quantity(
                    row["mature_inventory_loss_quantity_kg"]
                ),
                harvestable_mature_quantity_kg=quantize_quantity(
                    row["harvestable_mature_quantity_kg"]
                ),
                nominal_harvest_capacity_kg_per_day=quantize_quantity(
                    row["nominal_harvest_capacity_kg_per_day"]
                ),
                labor_availability_ratio=quantize_ratio(row["labor_availability_ratio"]),
                weather_harvest_efficiency_ratio=quantize_ratio(
                    row["weather_harvest_efficiency_ratio"]
                ),
                operational_efficiency_ratio=quantize_ratio(row["operational_efficiency_ratio"]),
                effective_harvest_capacity_kg_per_day=quantize_quantity(
                    row["effective_harvest_capacity_kg_per_day"]
                ),
                effective_capacity_for_day_kg=quantize_quantity(
                    row["effective_capacity_for_day_kg"]
                ),
                harvested_quantity_kg=quantize_quantity(row["harvested_quantity_kg"]),
                closing_mature_inventory_kg=quantize_quantity(row["closing_mature_inventory_kg"]),
                unharvested_backlog_kg=quantize_quantity(row["unharvested_backlog_kg"]),
                arrival_quantity_kg=quantize_quantity(
                    arrival_by_pool_key.get(
                        (
                            row["state_date"],
                            row["capacity_pool_id"],
                            row["forecast_quantile"],
                        ),
                        Decimal("0"),
                    )
                ),
                opening_cohort_count=row["opening_cohort_count"],
                closing_cohort_count=row["closing_cohort_count"],
                member_count=row["member_count"],
                mass_balance_passed=row["mass_balance_passed"],
                capacity_constraint_passed=row["capacity_constraint_passed"],
                continuity_passed=row["continuity_passed"],
                parameter_source_ref_hashes=row["parameter_source_ref_hashes"],
                cohort_source_ref_hashes=row["cohort_source_ref_hashes"],
            )
            for row in pool_row_inputs
        ],
        key=lambda row: (
            row.state_date,
            row.capacity_pool_id,
            _forecast_quantile_sort_key(row.forecast_quantile),
        ),
    )
    all_cohort_rows = sorted(
        [
            CohortTransitionRow(
                state_date=row["state_date"],
                forecast_quantile=row["forecast_quantile"],
                capacity_pool_id=row["capacity_pool_id"],
                farm_id=row["farm_id"],
                subfarm_id=row["subfarm_id"],
                variety_id=row["variety_id"],
                destination_factory_id=row["destination_factory_id"],
                stable_cohort_key=row["stable_cohort_key"],
                source_ref_hash=row["source_ref_hash"],
                cohort_date=row["cohort_date"],
                opening_quantity_kg=quantize_quantity(row["opening_quantity_kg"]),
                new_supply_quantity_kg=quantize_quantity(row["new_supply_quantity_kg"]),
                quantity_before_loss_kg=quantize_quantity(row["quantity_before_loss_kg"]),
                mature_inventory_loss_quantity_kg=quantize_quantity(
                    row["mature_inventory_loss_quantity_kg"]
                ),
                quantity_before_harvest_kg=quantize_quantity(row["quantity_before_harvest_kg"]),
                harvested_quantity_kg=quantize_quantity(row["harvested_quantity_kg"]),
                closing_quantity_kg=quantize_quantity(row["closing_quantity_kg"]),
                harvest_anchor_at=row["harvest_anchor_at"],
                arrival_at=row["arrival_at"],
                arrival_local_date=row["arrival_local_date"],
                arrival_quantity_kg=quantize_quantity(row["arrival_quantity_kg"]),
            )
            for row in cohort_row_inputs
        ],
        key=lambda row: (
            row.state_date,
            row.capacity_pool_id,
            row.cohort_date,
            row.variety_id,
            -1 if row.subfarm_id is None else row.subfarm_id,
            row.stable_cohort_key,
        ),
    )

    display_blockers = _display_reconciliation_blockers(
        pool_rows=all_pool_rows,
        member_rows=all_member_rows,
        cohort_rows=all_cohort_rows,
        forecast_start_date=request.forecast_start_date,
        forecast_end_date=request.forecast_end_date,
    )
    if display_blockers:
        validated.blockers.extend(display_blockers)
        return _blocked_output(request, validated)

    future_arrival_schedule = [
        FutureArrivalScheduleRow(
            destination_factory_id=destination_factory_id,
            arrival_local_date=arrival_local_date,
            capacity_pool_id=capacity_pool_id,
            farm_id=farm_id,
            subfarm_id=subfarm_id,
            variety_id=variety_id,
            forecast_quantile=forecast_quantile,
            quantity_kg=quantize_quantity(quantity),
        )
        for (
            destination_factory_id,
            arrival_local_date,
            capacity_pool_id,
            farm_id,
            subfarm_id,
            variety_id,
            forecast_quantile,
        ), quantity in sorted(
            future_arrivals.items(),
            key=lambda item: (
                item[0][0],
                item[0][1],
                item[0][2],
                item[0][3],
                -1 if item[0][4] is None else item[0][4],
                item[0][5],
                _forecast_quantile_sort_key(item[0][6]),
            ),
        )
    ]
    referenced_hashes = _referenced_source_hashes_from_completed_output(
        input_snapshot=validated.input_snapshot,
        resolved_snapshot=resolved_snapshot,
        pool_rows=all_pool_rows,
        member_rows=all_member_rows,
        cohort_rows=all_cohort_rows,
    )
    source_ref_catalog, catalog_blockers = build_source_ref_catalog(
        validated.source_refs,
        referenced_hashes=referenced_hashes,
    )
    if catalog_blockers:
        validated.blockers.extend(catalog_blockers)
        return _blocked_output(request, validated)

    internal_mass_balance_passed = all(row.mass_balance_passed for row in all_pool_rows)
    display_mass_balance_passed = not display_blockers
    continuity_passed = all(row.continuity_passed for row in all_pool_rows)

    payload = {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "status": "completed",
        "forecast_start_date": request.forecast_start_date,
        "forecast_end_date": request.forecast_end_date,
        "forecast_quantiles": list(request.forecast_quantiles),
        "input_snapshot": validated.input_snapshot,
        "resolved_parameter_snapshot": resolved_snapshot.model_dump(mode="python"),
        "daily_pool_state_rows": [row.model_dump(mode="python") for row in all_pool_rows],
        "daily_member_state_rows": [row.model_dump(mode="python") for row in all_member_rows],
        "cohort_transition_rows": [row.model_dump(mode="python") for row in all_cohort_rows],
        "future_arrival_schedule": [
            row.model_dump(mode="python") for row in future_arrival_schedule
        ],
        "source_ref_catalog": [entry.model_dump(mode="python") for entry in source_ref_catalog],
        "warnings": [],
        "blockers": [],
        "mass_balance_result": {
            "internal_passed": internal_mass_balance_passed,
            "display_passed": display_mass_balance_passed,
            "tolerance_kg": canonical_json_value(DISPLAY_TOLERANCE_KG),
            "passed": internal_mass_balance_passed and display_mass_balance_passed,
        },
        "continuity_result": {"passed": continuity_passed},
        "config_hash": validated.config_hash,
    }
    return Task9ACompletedOutput(
        forecast_start_date=request.forecast_start_date,
        forecast_end_date=request.forecast_end_date,
        forecast_quantiles=list(request.forecast_quantiles),
        input_snapshot=validated.input_snapshot,
        resolved_parameter_snapshot=resolved_snapshot,
        daily_pool_state_rows=all_pool_rows,
        daily_member_state_rows=all_member_rows,
        cohort_transition_rows=all_cohort_rows,
        future_arrival_schedule=future_arrival_schedule,
        source_ref_catalog=source_ref_catalog,
        warnings=[],
        blockers=[],
        mass_balance_result={
            "internal_passed": internal_mass_balance_passed,
            "display_passed": display_mass_balance_passed,
            "tolerance_kg": canonical_json_value(DISPLAY_TOLERANCE_KG),
            "passed": internal_mass_balance_passed and display_mass_balance_passed,
        },
        continuity_result={"passed": continuity_passed},
        config_hash=validated.config_hash,
        result_hash=make_result_hash(payload),
    )
