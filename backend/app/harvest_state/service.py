from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.harvest_state.canonical import (
    canonical_json_value,
    make_membership_hash,
    make_result_hash,
    quantize_quantity,
)
from backend.app.harvest_state.capacity import allocate_fifo_harvest, allocate_fifo_loss
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
    daily_pool_parameters: dict[tuple[date, str], DailyPoolResolvedParameters]
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


def _cohort_sort_key(cohort: dict[str, Any]) -> tuple[date, int, int, str]:
    subfarm_value = -1 if cohort["subfarm_id"] is None else int(cohort["subfarm_id"])
    return (
        cohort["cohort_date"],
        int(cohort["variety_id"]),
        subfarm_value,
        str(cohort["stable_cohort_key"]),
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
    return make_result_hash(payload)


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
    return make_result_hash(payload)


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
        "run_parameter_source_refs": [
            item.model_dump(mode="python")
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
        "daily_capacity_inputs": [item.model_dump(mode="python") for item in capacity_inputs],
        "daily_weather_features": [item.model_dump(mode="python") for item in weather_inputs],
        "task8_daily_predictions": [item.model_dump(mode="python") for item in task8_inputs],
        "initial_inventory_cohorts": [item.model_dump(mode="python") for item in initial_inputs],
        "initial_opening_mature_inventory_kg": request.initial_opening_mature_inventory_kg,
        "mature_inventory_loss_inputs": [item.model_dump(mode="python") for item in loss_inputs],
    }
    if validated is not None:
        snapshot["pool_membership_hash_by_pool"] = validated.pool_membership_hash_by_pool
    return canonical_json_value(snapshot)  # type: ignore[return-value]


def _config_hash(request: Task9ARequest) -> str:
    return make_result_hash(
        {
            "weather_rule_config": request.weather_rule_config.model_dump(mode="python"),
            "holiday_calendar_version": request.holiday_calendar_version,
            "holiday_calendar_hash": request.holiday_calendar_hash,
            "source_ref_schema_version": SOURCE_REF_SCHEMA_VERSION,
            "stable_cohort_key_schema_version": STABLE_COHORT_KEY_SCHEMA_VERSION,
            "resolved_parameter_snapshot_schema_version": (
                RESOLVED_PARAMETER_SNAPSHOT_SCHEMA_VERSION
            ),
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
        }
    )


def _sorted_blockers(blockers: list[str]) -> list[str]:
    return sorted(dict.fromkeys(blockers))


def _validated_request(request: Task9ARequest) -> ValidatedRequest:
    blockers: list[str] = []
    warnings: list[str] = []
    pools_by_id = {pool.capacity_pool_id: pool for pool in request.capacity_pools}
    pool_membership_hash_by_pool: dict[str, str] = {}
    member_to_pool: dict[tuple[int, int | None, int], str] = {}
    source_refs: list[SourceRef] = []

    if not request.initial_inventory_cohorts and request.initial_inventory_cohorts is None:
        blockers.append(BlockerCode.MISSING_INITIAL_INVENTORY_COHORTS)

    for item in request.run_parameter_source_refs:
        source_refs.append(item)
        if item.available_at > request.as_of_date:
            blockers.append(
                f"{BlockerCode.PARAMETER_SOURCE_NOT_VISIBLE_AT_AS_OF}:{item.parameter_code}"
            )

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
    for feature in request.daily_weather_features:
        source_refs.append(feature.source_ref)
        if feature.source_ref.available_at > request.as_of_date:
            blockers.append(
                f"{BlockerCode.PARAMETER_SOURCE_NOT_VISIBLE_AT_AS_OF}:{feature.feature_id}"
            )
        weather_lookup_key = (feature.capacity_date, feature.capacity_pool_id)
        weather_values_by_key.setdefault(weather_lookup_key, {})
        weather_refs_by_key.setdefault(weather_lookup_key, [])
        weather_values_by_key[weather_lookup_key][feature.feature_id] = feature.value
        weather_refs_by_key[weather_lookup_key].append(feature.source_ref)

    blockers.extend(validate_weather_rule_config(request.weather_rule_config))

    daily_pool_parameters: dict[tuple[date, str], DailyPoolResolvedParameters] = {}
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
        for source_ref in capacity_input.capacity_parameter_source_refs:
            if source_ref.available_at > request.as_of_date:
                blockers.append(
                    f"{BlockerCode.PARAMETER_SOURCE_NOT_VISIBLE_AT_AS_OF}:{source_ref.parameter_code}"
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
        found_codes = {
            item.parameter_code.value for item in capacity_input.capacity_parameter_source_refs
        }
        if not required_codes.issubset(found_codes):
            blockers.append(
                f"{BlockerCode.CAPACITY_MODE_PROVENANCE_MISSING}:{capacity_input.capacity_pool_id}:{capacity_input.capacity_date}"
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
            resolved_nominal = quantize_quantity(
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
            resolved_nominal = quantize_quantity(capacity_input.direct_nominal_capacity_kg_per_day)

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
                blockers.append(str(exc))
                weather_ratio = Decimal("0")
            weather_refs = sorted(
                weather_refs_by_key.get(weather_key, []),
                key=lambda item: (item.available_at, item.source_row_hash),
            )

        resolved_effective = quantize_quantity(
            resolved_nominal
            * capacity_input.labor_availability_ratio
            * weather_ratio
            * capacity_input.operational_efficiency_ratio
        )
        daily_pool_parameters[capacity_lookup_key] = DailyPoolResolvedParameters(
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
            capacity_parameter_source_refs=sorted(
                capacity_input.capacity_parameter_source_refs,
                key=lambda item: (item.parameter_code, item.source_row_hash),
            ),
            weather_feature_source_refs=weather_refs,
        )

    for forecast_date in forecast_dates:
        for pool_id in pools_by_id:
            if (forecast_date, pool_id) not in daily_pool_parameters:
                blockers.append(
                    f"{BlockerCode.MISSING_RESOLVED_PARAMETER}:{pool_id}:{forecast_date}"
                )

    task8_daily_predictions_by_key: dict[
        tuple[ForecastQuantile, date, str], list[Task8DailyPredictionInput]
    ] = {}
    for prediction in request.task8_daily_predictions:
        source_refs.append(prediction.source_ref)
        member_key = _member_key(prediction.farm_id, prediction.subfarm_id, prediction.variety_id)
        mapped_pool_id = member_to_pool.get(member_key)
        if mapped_pool_id is None:
            blockers.append(f"{BlockerCode.MISSING_POOL_MEMBERSHIP}:{member_key}")
            continue
        if prediction.source_ref.prediction_date != prediction.prediction_date:
            blockers.append(
                f"{BlockerCode.TASK8_SOURCE_RELATION_MISMATCH}:{prediction.prediction_date}"
            )
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
        if cohort.source_ref.available_at > request.as_of_date:
            blockers.append(BlockerCode.INITIAL_SOURCE_NOT_VISIBLE_AT_AS_OF)
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
        initial_cohort_keys.append(computed_key)
        initial_total += cohort.remaining_quantity_kg
    if request.initial_opening_mature_inventory_kg is not None and quantize_quantity(
        initial_total
    ) != quantize_quantity(request.initial_opening_mature_inventory_kg):
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
        if loss_input.source_ref.available_at > request.as_of_date:
            blockers.append(
                f"{BlockerCode.PARAMETER_SOURCE_NOT_VISIBLE_AT_AS_OF}:{loss_input.source_ref.parameter_code}"
            )

    for forecast_date in forecast_dates:
        for pool_id in pools_by_id:
            for quantile in request.forecast_quantiles:
                if (forecast_date, pool_id, quantile) not in loss_inputs_by_key:
                    blockers.append(
                        f"{BlockerCode.MISSING_MATURE_LOSS_INPUT}:{pool_id}:{forecast_date}:{quantile}"
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
    source_ref_catalog, catalog_blockers = build_source_ref_catalog(validated.source_refs)
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


def run_harvest_state_model(
    request: Task9ARequest,
) -> Task9ACompletedOutput | Task9ABlockedOutput:
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
        holiday_calendar_hash=request.holiday_calendar_hash,
        weather_rule_version=request.weather_rule_config.version,
        weather_rule_config_hash=validated.config_hash,
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
            validated.daily_pool_parameters[key]
            for key in sorted(validated.daily_pool_parameters, key=lambda item: (item[0], item[1]))
        ],
    )

    all_pool_rows: list[DailyPoolStateRow] = []
    all_member_rows: list[DailyMemberStateRow] = []
    all_cohort_rows: list[CohortTransitionRow] = []
    future_arrivals: dict[tuple[int, date, int, ForecastQuantile], Decimal] = {}

    for quantile in request.forecast_quantiles:
        current_cohorts: list[dict[str, Any]] = []
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
            current_cohorts.append(
                {
                    "stable_cohort_key": stable_key,
                    "source_ref_hash": source_ref_hash(initial_cohort.source_ref),
                    "source_ref": initial_cohort.source_ref,
                    "capacity_pool_id": pool_id,
                    "capacity_pool_membership_hash": membership_hash,
                    "farm_id": initial_cohort.farm_id,
                    "subfarm_id": initial_cohort.subfarm_id,
                    "variety_id": initial_cohort.variety_id,
                    "cohort_date": initial_cohort.cohort_date,
                    "forecast_quantile": quantile,
                    "remaining_quantity_kg": quantize_quantity(
                        initial_cohort.remaining_quantity_kg
                    ),
                }
            )

        previous_closing_by_key: dict[str, Decimal] = {}
        date_count = (request.forecast_end_date - request.forecast_start_date).days + 1
        for offset in range(date_count):
            state_date = request.forecast_start_date + timedelta(days=offset)
            for pool_id, pool in sorted(validated.pools_by_id.items(), key=lambda item: item[0]):
                params = validated.daily_pool_parameters[(state_date, pool_id)]
                member_keys = [
                    _member_key(member.farm_id, member.subfarm_id, member.variety_id)
                    for member in sorted(pool.members, key=_member_sort_key)
                ]
                opening_cohorts = [
                    cohort
                    for cohort in current_cohorts
                    if cohort["capacity_pool_id"] == pool_id and cohort["remaining_quantity_kg"] > 0
                ]
                opening_qty_map = {
                    cohort["stable_cohort_key"]: quantize_quantity(cohort["remaining_quantity_kg"])
                    for cohort in opening_cohorts
                }
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
                    new_cohorts.append(
                        {
                            "stable_cohort_key": stable_key,
                            "source_ref_hash": source_ref_hash(prediction.source_ref),
                            "source_ref": prediction.source_ref,
                            "capacity_pool_id": pool_id,
                            "capacity_pool_membership_hash": validated.pool_membership_hash_by_pool[
                                pool_id
                            ],
                            "farm_id": prediction.farm_id,
                            "subfarm_id": prediction.subfarm_id,
                            "variety_id": prediction.variety_id,
                            "cohort_date": prediction.prediction_date,
                            "forecast_quantile": quantile,
                            "remaining_quantity_kg": quantize_quantity(
                                prediction.source_ref.source_quantity_kg
                            ),
                        }
                    )
                current_cohorts.extend(new_cohorts)
                pool_cohorts = [
                    cohort for cohort in current_cohorts if cohort["capacity_pool_id"] == pool_id
                ]
                fifo_cohorts = sorted(pool_cohorts, key=_cohort_sort_key)
                new_supply_qty_map = {
                    cohort["stable_cohort_key"]: quantize_quantity(cohort["remaining_quantity_kg"])
                    for cohort in new_cohorts
                }
                before_loss_map = {
                    cohort["stable_cohort_key"]: quantize_quantity(cohort["remaining_quantity_kg"])
                    for cohort in fifo_cohorts
                }
                available_total = quantize_quantity(
                    sum(
                        (Decimal(value) for value in before_loss_map.values()),
                        Decimal("0"),
                    )
                )
                loss_input = validated.loss_inputs_by_key[(state_date, pool_id, quantile)]
                if loss_input.mature_inventory_loss_quantity_kg > available_total:
                    validated.blockers.append(
                        f"{BlockerCode.MATURE_LOSS_EXCEEDS_AVAILABLE}:{pool_id}:{state_date}:{quantile}"
                    )
                    return _blocked_output(request, validated)
                loss_allocations = allocate_fifo_loss(
                    fifo_cohorts,
                    quantize_quantity(loss_input.mature_inventory_loss_quantity_kg),
                )
                loss_map = {
                    item.stable_cohort_key: item.loss_quantity_kg for item in loss_allocations
                }
                before_harvest_map = {
                    cohort["stable_cohort_key"]: quantize_quantity(cohort["remaining_quantity_kg"])
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
                    cohort["stable_cohort_key"]: quantize_quantity(cohort["remaining_quantity_kg"])
                    for cohort in fifo_cohorts
                }

                member_rows: list[DailyMemberStateRow] = []
                pool_transition_rows: list[CohortTransitionRow] = []
                continuity_passed = True
                for working_cohort in fifo_cohorts:
                    stable_key = str(working_cohort["stable_cohort_key"])
                    opening_quantity = opening_qty_map.get(stable_key, Decimal("0"))
                    if (
                        stable_key in previous_closing_by_key
                        and opening_quantity != previous_closing_by_key[stable_key]
                    ):
                        continuity_passed = False
                    harvested_quantity = harvest_map.get(stable_key, Decimal("0"))
                    arrival_payload: dict[str, Any] = {
                        "harvest_anchor_at": None,
                        "arrival_at": None,
                        "arrival_local_date": None,
                    }
                    if harvested_quantity > 0:
                        farm_zone = ZoneInfo(request.farm_timezone)
                        factory_zone = ZoneInfo(request.destination_factory_timezone)
                        harvest_anchor_at = datetime.combine(
                            state_date,
                            request.harvest_bucket_anchor_local_time,
                            farm_zone,
                        )
                        arrival_at = harvest_anchor_at + timedelta(
                            days=request.harvest_to_arrival_lag_days
                        )
                        arrival_local = arrival_at.astimezone(factory_zone)
                        arrival_payload = {
                            "harvest_anchor_at": harvest_anchor_at,
                            "arrival_at": arrival_local,
                            "arrival_local_date": arrival_local.date(),
                        }
                        if arrival_local.date() > request.forecast_end_date:
                            future_key = (
                                request.destination_factory_id,
                                arrival_local.date(),
                                int(working_cohort["variety_id"]),
                                quantile,
                            )
                            future_arrivals[future_key] = (
                                future_arrivals.get(
                                    future_key,
                                    Decimal("0"),
                                )
                                + harvested_quantity
                            )
                    pool_transition_rows.append(
                        CohortTransitionRow(
                            state_date=state_date,
                            forecast_quantile=quantile,
                            capacity_pool_id=pool_id,
                            farm_id=int(working_cohort["farm_id"]),
                            subfarm_id=working_cohort["subfarm_id"],
                            variety_id=int(working_cohort["variety_id"]),
                            destination_factory_id=request.destination_factory_id,
                            stable_cohort_key=stable_key,
                            source_ref_hash=str(working_cohort["source_ref_hash"]),
                            cohort_date=working_cohort["cohort_date"],
                            opening_quantity_kg=opening_quantity,
                            new_supply_quantity_kg=new_supply_qty_map.get(stable_key, Decimal("0")),
                            quantity_before_loss_kg=before_loss_map[stable_key],
                            mature_inventory_loss_quantity_kg=loss_map.get(
                                stable_key, Decimal("0")
                            ),
                            quantity_before_harvest_kg=before_harvest_map[stable_key],
                            harvested_quantity_kg=harvested_quantity,
                            closing_quantity_kg=closing_map[stable_key],
                            harvest_anchor_at=arrival_payload["harvest_anchor_at"],
                            arrival_at=arrival_payload["arrival_at"],
                            arrival_local_date=arrival_payload["arrival_local_date"],
                            arrival_quantity_kg=harvested_quantity,
                        )
                    )
                current_cohorts = [
                    cohort for cohort in current_cohorts if cohort["remaining_quantity_kg"] > 0
                ]
                previous_closing_by_key = {
                    row.stable_cohort_key: row.closing_quantity_kg
                    for row in pool_transition_rows
                    if row.closing_quantity_kg > 0
                }
                for member_key in member_keys:
                    farm_id, subfarm_id, variety_id = member_key
                    member_rows_for_day = [
                        row
                        for row in pool_transition_rows
                        if row.farm_id == farm_id
                        and row.subfarm_id == subfarm_id
                        and row.variety_id == variety_id
                    ]
                    member_rows.append(
                        DailyMemberStateRow(
                            state_date=state_date,
                            forecast_quantile=quantile,
                            capacity_pool_id=pool_id,
                            capacity_pool_grain=pool.capacity_pool_grain,
                            capacity_pool_membership_hash=validated.pool_membership_hash_by_pool[
                                pool_id
                            ],
                            farm_id=farm_id,
                            subfarm_id=subfarm_id,
                            variety_id=variety_id,
                            destination_factory_id=request.destination_factory_id,
                            opening_mature_inventory_kg=quantize_quantity(
                                sum(
                                    (row.opening_quantity_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            natural_maturity_supply_kg=quantize_quantity(
                                sum(
                                    (row.new_supply_quantity_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            available_mature_quantity_kg=quantize_quantity(
                                sum(
                                    (row.quantity_before_loss_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            mature_inventory_loss_quantity_kg=quantize_quantity(
                                sum(
                                    (
                                        row.mature_inventory_loss_quantity_kg
                                        for row in member_rows_for_day
                                    ),
                                    Decimal("0"),
                                )
                            ),
                            harvestable_mature_quantity_kg=quantize_quantity(
                                sum(
                                    (row.quantity_before_harvest_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            allocated_harvest_capacity_kg=quantize_quantity(
                                sum(
                                    (row.harvested_quantity_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            harvested_quantity_kg=quantize_quantity(
                                sum(
                                    (row.harvested_quantity_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            closing_mature_inventory_kg=quantize_quantity(
                                sum(
                                    (row.closing_quantity_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            unharvested_backlog_kg=quantize_quantity(
                                sum(
                                    (row.closing_quantity_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            arrival_quantity_kg=quantize_quantity(
                                sum(
                                    (row.arrival_quantity_kg for row in member_rows_for_day),
                                    Decimal("0"),
                                )
                            ),
                            opening_cohort_count=sum(
                                1 for row in member_rows_for_day if row.opening_quantity_kg > 0
                            ),
                            closing_cohort_count=sum(
                                1 for row in member_rows_for_day if row.closing_quantity_kg > 0
                            ),
                            cohort_source_ref_hashes=sorted(
                                {row.source_ref_hash for row in member_rows_for_day}
                            ),
                        )
                    )
                pool_opening = quantize_quantity(
                    sum((row.opening_mature_inventory_kg for row in member_rows), Decimal("0"))
                )
                pool_supply = quantize_quantity(
                    sum((row.natural_maturity_supply_kg for row in member_rows), Decimal("0"))
                )
                pool_available = quantize_quantity(
                    sum((row.available_mature_quantity_kg for row in member_rows), Decimal("0"))
                )
                pool_loss = quantize_quantity(
                    sum(
                        (row.mature_inventory_loss_quantity_kg for row in member_rows), Decimal("0")
                    )
                )
                pool_harvestable = quantize_quantity(
                    sum((row.harvestable_mature_quantity_kg for row in member_rows), Decimal("0"))
                )
                pool_harvested = quantize_quantity(
                    sum((row.harvested_quantity_kg for row in member_rows), Decimal("0"))
                )
                pool_closing = quantize_quantity(
                    sum((row.closing_mature_inventory_kg for row in member_rows), Decimal("0"))
                )
                pool_arrival = quantize_quantity(
                    sum((row.arrival_quantity_kg for row in member_rows), Decimal("0"))
                )
                mass_balance_passed = (
                    pool_opening + pool_supply == pool_loss + pool_harvested + pool_closing
                )
                capacity_constraint_passed = (
                    pool_harvested <= pool_available
                    and pool_harvested <= params.resolved_effective_capacity_kg_per_day
                )
                all_pool_rows.append(
                    DailyPoolStateRow(
                        state_date=state_date,
                        forecast_quantile=quantile,
                        capacity_pool_id=pool_id,
                        capacity_pool_grain=pool.capacity_pool_grain,
                        capacity_pool_membership_hash=validated.pool_membership_hash_by_pool[
                            pool_id
                        ],
                        capacity_input_mode=params.capacity_input_mode,
                        opening_mature_inventory_kg=pool_opening,
                        natural_maturity_supply_kg=pool_supply,
                        available_mature_quantity_kg=pool_available,
                        mature_inventory_loss_quantity_kg=pool_loss,
                        harvestable_mature_quantity_kg=pool_harvestable,
                        nominal_harvest_capacity_kg_per_day=params.resolved_nominal_capacity_kg_per_day,
                        labor_availability_ratio=params.labor_availability_ratio,
                        weather_harvest_efficiency_ratio=params.weather_harvest_efficiency_ratio,
                        operational_efficiency_ratio=params.operational_efficiency_ratio,
                        effective_harvest_capacity_kg_per_day=params.resolved_effective_capacity_kg_per_day,
                        effective_capacity_for_day_kg=params.resolved_effective_capacity_kg_per_day,
                        harvested_quantity_kg=pool_harvested,
                        closing_mature_inventory_kg=pool_closing,
                        unharvested_backlog_kg=pool_closing,
                        arrival_quantity_kg=pool_arrival,
                        opening_cohort_count=sum(
                            1 for row in pool_transition_rows if row.opening_quantity_kg > 0
                        ),
                        closing_cohort_count=sum(
                            1 for row in pool_transition_rows if row.closing_quantity_kg > 0
                        ),
                        member_count=len(member_rows),
                        mass_balance_passed=mass_balance_passed,
                        capacity_constraint_passed=capacity_constraint_passed,
                        continuity_passed=continuity_passed,
                        parameter_source_ref_hashes=sorted(
                            {
                                source_ref_hash(item)
                                for item in (
                                    list(params.capacity_parameter_source_refs)
                                    + list(params.weather_feature_source_refs)
                                )
                            }
                        ),
                        cohort_source_ref_hashes=sorted(
                            {row.source_ref_hash for row in pool_transition_rows}
                        ),
                    )
                )
                all_member_rows.extend(member_rows)
                all_cohort_rows.extend(pool_transition_rows)

    all_pool_rows = sorted(
        all_pool_rows,
        key=lambda row: (
            row.state_date,
            row.capacity_pool_id,
            _forecast_quantile_sort_key(row.forecast_quantile),
        ),
    )
    all_member_rows = sorted(
        all_member_rows,
        key=lambda row: (
            row.state_date,
            row.capacity_pool_id,
            row.farm_id,
            -1 if row.subfarm_id is None else row.subfarm_id,
            row.variety_id,
            _forecast_quantile_sort_key(row.forecast_quantile),
        ),
    )
    all_cohort_rows = sorted(
        all_cohort_rows,
        key=lambda row: (
            row.state_date,
            row.capacity_pool_id,
            row.cohort_date,
            row.variety_id,
            -1 if row.subfarm_id is None else row.subfarm_id,
            row.stable_cohort_key,
        ),
    )
    future_arrival_schedule = [
        FutureArrivalScheduleRow(
            destination_factory_id=destination_factory_id,
            arrival_local_date=arrival_local_date,
            variety_id=variety_id,
            forecast_quantile=forecast_quantile,
            quantity_kg=quantize_quantity(quantity),
        )
        for (
            destination_factory_id,
            arrival_local_date,
            variety_id,
            forecast_quantile,
        ), quantity in sorted(
            future_arrivals.items(),
            key=lambda item: (
                item[0][0],
                item[0][1],
                item[0][2],
                _forecast_quantile_sort_key(item[0][3]),
            ),
        )
    ]
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
        "mass_balance_result": {"passed": all(row.mass_balance_passed for row in all_pool_rows)},
        "continuity_result": {"passed": all(row.continuity_passed for row in all_pool_rows)},
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
        mass_balance_result={"passed": all(row.mass_balance_passed for row in all_pool_rows)},
        continuity_result={"passed": all(row.continuity_passed for row in all_pool_rows)},
        config_hash=validated.config_hash,
        result_hash=make_result_hash(payload),
    )
