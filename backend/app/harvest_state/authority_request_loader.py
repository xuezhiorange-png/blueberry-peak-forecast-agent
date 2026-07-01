from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import ValidationError

from backend.app.harvest_state.authority_request_errors import (
    Task9AuthorityRequestAssemblyError,
)
from backend.app.harvest_state.authority_request_types import (
    ResolvedAuthorityBinding,
    Task9AuthorityRequestAssembly,
)
from backend.app.harvest_state.authority_resolution_types import (
    ResolvedCapacityPoolAuthority,
    ResolvedDailyCapacityAuthority,
    ResolvedInitialInventoryAuthority,
    ResolvedMatureLossAuthority,
    ResolvedRunParameterPackageAuthority,
)
from backend.app.harvest_state.canonical import (
    canonical_json_value,
    make_membership_hash,
    make_stable_cohort_key,
    sha256_hex,
)
from backend.app.harvest_state.enums import (
    CANONICAL_FORECAST_QUANTILES,
    AuthorityFamily,
    CapacityInputMode,
    ForecastQuantile,
    ParameterCode,
)
from backend.app.harvest_state.schemas import (
    CapacityPoolInput,
    CapacityPoolMember,
    DailyCapacityInput,
    DailyWeatherFeatureInput,
    InitialInventoryCohortInput,
    InitialInventorySourceRef,
    MatureInventoryLossInput,
    ParameterSourceRef,
    Task8DailyPredictionInput,
    Task9ARequest,
    WeatherEfficiencyRuleConfig,
)
from backend.app.harvest_state.service import _sorted_request_snapshot, _validated_request


class _ResolvedAuthorityLike(Protocol):
    @property
    def authority_family(self) -> AuthorityFamily: ...

    @property
    def authority_id(self) -> int: ...

    @property
    def authority_stable_key(self) -> str: ...

    @property
    def business_version(self) -> str: ...

    @property
    def revision(self) -> int: ...

    @property
    def row_hash(self) -> str: ...


_PARAMETER_SOURCE_REF_ORDER: dict[ParameterCode, int] = {
    ParameterCode.HOLIDAY_CALENDAR: 10,
    ParameterCode.WEATHER_RULE_CONFIG: 20,
    ParameterCode.HARVEST_TO_ARRIVAL_LAG: 30,
    ParameterCode.TIMEZONE_CONFIG: 40,
    ParameterCode.HARVEST_BUCKET_ANCHOR_TIME: 50,
    ParameterCode.PLANNED_PICKER_COUNT: 60,
    ParameterCode.PICKER_PRODUCTIVITY: 70,
    ParameterCode.DIRECT_NOMINAL_CAPACITY: 80,
    ParameterCode.LABOR_AVAILABILITY_RATIO: 90,
    ParameterCode.OPERATIONAL_EFFICIENCY_RATIO: 100,
    ParameterCode.MATURE_INVENTORY_LOSS: 110,
}


def _date_range(start: date, end: date) -> tuple[date, ...]:
    return tuple(start.fromordinal(day) for day in range(start.toordinal(), end.toordinal() + 1))


def _raise(
    reason: str,
    *,
    authority_family: AuthorityFamily | None = None,
    authority_stable_key: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    raise Task9AuthorityRequestAssemblyError(
        reason=reason,
        authority_family=authority_family,
        authority_stable_key=authority_stable_key,
        details=details,
    )


def _binding(authority: _ResolvedAuthorityLike) -> ResolvedAuthorityBinding:
    return ResolvedAuthorityBinding(
        authority_family=authority.authority_family,
        authority_id=authority.authority_id,
        authority_stable_key=authority.authority_stable_key,
        business_version=authority.business_version,
        revision=authority.revision,
        row_hash=authority.row_hash,
    )


def _semantic_binding_payload(binding: ResolvedAuthorityBinding) -> dict[str, object]:
    return {
        "authority_family": binding.authority_family.value,
        "authority_stable_key": binding.authority_stable_key,
        "business_version": binding.business_version,
        "revision": binding.revision,
        "row_hash": binding.row_hash,
    }


def _source_record_key(binding: ResolvedAuthorityBinding) -> str:
    return (
        f"{binding.authority_family.value}:{binding.authority_stable_key}:"
        f"{binding.business_version}:{binding.revision}"
    )


def _parameter_source_ref(
    *,
    code: ParameterCode,
    binding: ResolvedAuthorityBinding,
    source_system: str,
    source_version: str,
    available_at: date,
    as_of_date: date,
) -> ParameterSourceRef:
    return ParameterSourceRef(
        parameter_code=code,
        source_system=source_system,
        source_record_key=_source_record_key(binding),
        source_version=source_version,
        source_row_hash=binding.row_hash,
        available_at=available_at,
        as_of_date=as_of_date,
    )


def _capacity_pool_input(authority: ResolvedCapacityPoolAuthority) -> CapacityPoolInput:
    bundle = authority.semantic_bundle
    return CapacityPoolInput(
        capacity_pool_id=bundle.capacity_pool_code,
        capacity_pool_grain=bundle.capacity_pool_grain,
        members=[
            CapacityPoolMember(
                farm_id=member.farm_id,
                subfarm_id=member.subfarm_id,
                variety_id=member.variety_id,
            )
            for member in sorted(
                bundle.members,
                key=lambda item: (
                    item.farm_id,
                    -1 if item.subfarm_id is None else item.subfarm_id,
                    item.variety_id,
                ),
            )
        ],
    )


def _capacity_refs(
    authority: ResolvedDailyCapacityAuthority,
    *,
    as_of_date: date,
) -> list[ParameterSourceRef]:
    daily = authority.semantic_input
    binding = _binding(authority)
    if daily.capacity_input_mode is CapacityInputMode.LABOR_DERIVED:
        codes: tuple[ParameterCode, ...] = (
            ParameterCode.PLANNED_PICKER_COUNT,
            ParameterCode.PICKER_PRODUCTIVITY,
            ParameterCode.LABOR_AVAILABILITY_RATIO,
            ParameterCode.OPERATIONAL_EFFICIENCY_RATIO,
        )
    else:
        codes = (
            ParameterCode.DIRECT_NOMINAL_CAPACITY,
            ParameterCode.LABOR_AVAILABILITY_RATIO,
            ParameterCode.OPERATIONAL_EFFICIENCY_RATIO,
        )
    return [
        _parameter_source_ref(
            code=code,
            binding=binding,
            source_system=daily.source_system,
            source_version=daily.source_version,
            available_at=daily.available_at_local_date,
            as_of_date=as_of_date,
        )
        for code in codes
    ]


def _daily_capacity_input(
    authority: ResolvedDailyCapacityAuthority,
    *,
    as_of_date: date,
) -> DailyCapacityInput:
    daily = authority.semantic_input
    parent = authority.parent_pool.semantic_bundle
    if daily.capacity_pool_code != parent.capacity_pool_code:
        _raise(
            "authority_parent_pool_mismatch",
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            authority_stable_key=authority.authority_stable_key,
        )
    if daily.capacity_pool_version != parent.capacity_pool_version:
        _raise(
            "authority_parent_pool_mismatch",
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            authority_stable_key=authority.authority_stable_key,
        )
    if daily.capacity_pool_revision != parent.revision:
        _raise(
            "authority_parent_pool_mismatch",
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            authority_stable_key=authority.authority_stable_key,
        )
    return DailyCapacityInput(
        capacity_date=daily.capacity_date,
        capacity_pool_id=daily.capacity_pool_code,
        capacity_input_mode=daily.capacity_input_mode,
        planned_picker_count=daily.planned_picker_count,
        kg_per_person_per_day=daily.kg_per_person_per_day,
        direct_nominal_capacity_kg_per_day=daily.direct_nominal_capacity_kg_per_day,
        labor_availability_ratio=daily.labor_availability_ratio,
        operational_efficiency_ratio=daily.operational_efficiency_ratio,
        capacity_parameter_source_refs=_capacity_refs(authority, as_of_date=as_of_date),
    )


def _weather_rule_config(
    authority: ResolvedRunParameterPackageAuthority,
) -> WeatherEfficiencyRuleConfig:
    weather = authority.weather_rule.semantic_input
    return WeatherEfficiencyRuleConfig(
        version=weather.rule_version,
        required_feature_ids=list(weather.required_feature_ids),
        feature_rules=list(weather.feature_rules),
        combination_method=weather.combination_method,
        minimum_ratio=weather.minimum_ratio,
        maximum_ratio=weather.maximum_ratio,
        missing_feature_policy=weather.missing_feature_policy,
    )


def _holiday_request_dates(authority: ResolvedRunParameterPackageAuthority) -> list[date]:
    return sorted({item.holiday_date for item in authority.holiday_calendar.semantic_bundle.dates})


def _run_parameter_refs(
    authority: ResolvedRunParameterPackageAuthority,
    *,
    as_of_date: date,
) -> list[ParameterSourceRef]:
    package = authority.semantic_input
    package_binding = _binding(authority)
    holiday_binding = _binding(authority.holiday_calendar)
    weather_binding = _binding(authority.weather_rule)
    return [
        _parameter_source_ref(
            code=ParameterCode.HOLIDAY_CALENDAR,
            binding=holiday_binding,
            source_system=authority.holiday_calendar.semantic_bundle.source_system,
            source_version=authority.holiday_calendar.semantic_bundle.source_version,
            available_at=authority.holiday_calendar.semantic_bundle.available_at_local_date,
            as_of_date=as_of_date,
        ),
        _parameter_source_ref(
            code=ParameterCode.WEATHER_RULE_CONFIG,
            binding=weather_binding,
            source_system=authority.weather_rule.semantic_input.source_system,
            source_version=authority.weather_rule.semantic_input.source_version,
            available_at=authority.weather_rule.semantic_input.available_at_local_date,
            as_of_date=as_of_date,
        ),
        _parameter_source_ref(
            code=ParameterCode.HARVEST_TO_ARRIVAL_LAG,
            binding=package_binding,
            source_system=package.source_system,
            source_version=package.source_version,
            available_at=package.available_at_local_date,
            as_of_date=as_of_date,
        ),
        _parameter_source_ref(
            code=ParameterCode.TIMEZONE_CONFIG,
            binding=package_binding,
            source_system=package.source_system,
            source_version=package.source_version,
            available_at=package.available_at_local_date,
            as_of_date=as_of_date,
        ),
        _parameter_source_ref(
            code=ParameterCode.HARVEST_BUCKET_ANCHOR_TIME,
            binding=package_binding,
            source_system=package.source_system,
            source_version=package.source_version,
            available_at=package.available_at_local_date,
            as_of_date=as_of_date,
        ),
    ]


def _initial_inventory_source_ref(
    authority: ResolvedInitialInventoryAuthority,
    *,
    as_of_date: date,
) -> InitialInventorySourceRef:
    bundle = authority.semantic_bundle
    return InitialInventorySourceRef(
        source_system=bundle.source_system,
        source_record_key=_source_record_key(_binding(authority)),
        source_version=bundle.source_version,
        source_row_hash=authority.row_hash,
        available_at=bundle.available_at_local_date,
        as_of_date=as_of_date,
    )


def _membership_hash(pool: ResolvedCapacityPoolAuthority) -> str:
    return make_membership_hash(
        pool.semantic_bundle.capacity_pool_grain.value,
        [
            {
                "farm_id": item.farm_id,
                "subfarm_id": item.subfarm_id,
                "variety_id": item.variety_id,
            }
            for item in sorted(
                pool.semantic_bundle.members,
                key=lambda member: (
                    member.farm_id,
                    -1 if member.subfarm_id is None else member.subfarm_id,
                    member.variety_id,
                ),
            )
        ],
    )


def _initial_inventory_inputs(
    authority: ResolvedInitialInventoryAuthority,
    *,
    pool: ResolvedCapacityPoolAuthority,
    as_of_date: date,
) -> list[InitialInventoryCohortInput]:
    source_ref = _initial_inventory_source_ref(authority, as_of_date=as_of_date)
    membership_hash = _membership_hash(pool)
    out: list[InitialInventoryCohortInput] = []
    for cohort in sorted(
        authority.semantic_bundle.cohorts,
        key=lambda item: (
            item.cohort_date,
            item.farm_id,
            -1 if item.subfarm_id is None else item.subfarm_id,
            item.variety_id,
            item.forecast_quantile.value,
            item.stable_cohort_key,
        ),
    ):
        expected_key = make_stable_cohort_key(
            {
                "schema_version": "task9a-cohort-key-v1",
                "source_ref_type": "INITIAL_INVENTORY_SNAPSHOT",
                "source_system": source_ref.source_system,
                "source_record_key": source_ref.source_record_key,
                "source_version": source_ref.source_version,
                "source_row_hash": source_ref.source_row_hash,
                "cohort_date": cohort.cohort_date,
                "forecast_quantile": cohort.forecast_quantile,
                "farm_id": cohort.farm_id,
                "subfarm_id": cohort.subfarm_id,
                "variety_id": cohort.variety_id,
                "capacity_pool_id": pool.semantic_bundle.capacity_pool_code,
                "capacity_pool_membership_hash": membership_hash,
                "destination_factory_id": pool.semantic_bundle.destination_factory_id,
            }
        )
        if cohort.stable_cohort_key != expected_key:
            _raise(
                "authority_initial_inventory_total_mismatch",
                authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
                authority_stable_key=authority.authority_stable_key,
                details={"field": "stable_cohort_key"},
            )
        out.append(
            InitialInventoryCohortInput(
                cohort_date=cohort.cohort_date,
                farm_id=cohort.farm_id,
                subfarm_id=cohort.subfarm_id,
                variety_id=cohort.variety_id,
                remaining_quantity_kg=cohort.remaining_quantity_kg,
                source_ref=source_ref,
                forecast_quantile=cohort.forecast_quantile,
                stable_cohort_key=cohort.stable_cohort_key,
            )
        )
    total = sum((item.remaining_quantity_kg for item in out), start=Decimal("0"))
    if total != authority.semantic_bundle.initial_opening_mature_inventory_kg:
        _raise(
            "authority_initial_inventory_total_mismatch",
            authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
            authority_stable_key=authority.authority_stable_key,
        )
    return out


def _mature_loss_input(
    authority: ResolvedMatureLossAuthority,
    *,
    as_of_date: date,
) -> MatureInventoryLossInput:
    loss = authority.semantic_input
    return MatureInventoryLossInput(
        state_date=loss.state_date,
        capacity_pool_id=loss.capacity_pool_code,
        forecast_quantile=loss.forecast_quantile,
        mature_inventory_loss_quantity_kg=loss.mature_inventory_loss_quantity_kg,
        source_ref=_parameter_source_ref(
            code=ParameterCode.MATURE_INVENTORY_LOSS,
            binding=_binding(authority),
            source_system=loss.source_system,
            source_version=loss.source_version,
            available_at=loss.available_at_local_date,
            as_of_date=as_of_date,
        ),
    )


def _manifest(
    authorities: Iterable[_ResolvedAuthorityLike],
) -> tuple[ResolvedAuthorityBinding, ...]:
    return tuple(
        sorted(
            (_binding(authority) for authority in authorities),
            key=lambda item: (
                item.authority_family.value,
                item.authority_stable_key,
                item.business_version,
                item.revision,
                item.row_hash,
            ),
        )
    )


def _validate_scope(
    *,
    capacity_pool: ResolvedCapacityPoolAuthority,
    run_package: ResolvedRunParameterPackageAuthority,
    initial_inventory: ResolvedInitialInventoryAuthority,
) -> None:
    pool = capacity_pool.semantic_bundle
    package = run_package.semantic_input
    inventory = initial_inventory.semantic_bundle
    if pool.season_id != package.season_id or pool.season_id != inventory.season_id:
        _raise("authority_scope_mismatch", authority_stable_key=capacity_pool.authority_stable_key)
    if (
        pool.destination_factory_id != package.destination_factory_id
        or pool.destination_factory_id != inventory.destination_factory_id
    ):
        _raise("authority_scope_mismatch", authority_stable_key=capacity_pool.authority_stable_key)
    if (
        package.destination_factory_timezone
        != run_package.holiday_calendar.semantic_bundle.lifecycle_timezone_name
    ):
        _raise(
            "authority_dependency_hash_mismatch",
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=run_package.authority_stable_key,
        )
    if (
        package.destination_factory_timezone
        != run_package.weather_rule.semantic_input.lifecycle_timezone_name
    ):
        _raise(
            "authority_dependency_hash_mismatch",
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=run_package.authority_stable_key,
        )


def _validate_coverage(
    *,
    forecast_dates: tuple[date, ...],
    quantiles: tuple[ForecastQuantile, ...],
    capacity_pool: ResolvedCapacityPoolAuthority,
    daily_capacities: tuple[ResolvedDailyCapacityAuthority, ...],
    mature_losses: tuple[ResolvedMatureLossAuthority, ...],
    task8_daily_predictions: tuple[Task8DailyPredictionInput, ...],
) -> None:
    pool = capacity_pool.semantic_bundle
    pool_code = pool.capacity_pool_code
    member_keys = {
        (member.farm_id, member.subfarm_id, member.variety_id) for member in pool.members
    }
    daily_keys = [
        (
            daily_authority.semantic_input.capacity_date,
            daily_authority.semantic_input.capacity_pool_code,
        )
        for daily_authority in daily_capacities
    ]
    if len(set(daily_keys)) != len(daily_keys):
        _raise(
            "authority_duplicate_daily_capacity",
            authority_stable_key=capacity_pool.authority_stable_key,
        )
    for daily_authority in daily_capacities:
        daily = daily_authority.semantic_input
        if (
            daily.season_id != pool.season_id
            or daily.destination_factory_id != pool.destination_factory_id
        ):
            _raise(
                "authority_scope_mismatch",
                authority_family=AuthorityFamily.DAILY_CAPACITY,
                authority_stable_key=daily_authority.authority_stable_key,
            )
    expected_daily = {(day, pool_code) for day in forecast_dates}
    if set(daily_keys) != expected_daily:
        _raise(
            "authority_date_coverage_incomplete",
            authority_stable_key=capacity_pool.authority_stable_key,
            details={"expected": sorted(str(day) for day, _pool in expected_daily)},
        )
    loss_keys = [
        (
            loss_authority.semantic_input.state_date,
            loss_authority.semantic_input.capacity_pool_code,
            loss_authority.semantic_input.forecast_quantile,
        )
        for loss_authority in mature_losses
    ]
    if len(set(loss_keys)) != len(loss_keys):
        _raise(
            "authority_quantile_coverage_incomplete",
            authority_stable_key=capacity_pool.authority_stable_key,
        )
    for loss_authority in mature_losses:
        loss = loss_authority.semantic_input
        if (
            loss.season_id != pool.season_id
            or loss.destination_factory_id != pool.destination_factory_id
        ):
            _raise(
                "authority_scope_mismatch",
                authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                authority_stable_key=loss_authority.authority_stable_key,
            )
    expected_loss = {(day, pool_code, quantile) for day in forecast_dates for quantile in quantiles}
    if set(loss_keys) != expected_loss:
        _raise(
            "authority_quantile_coverage_incomplete",
            authority_stable_key=capacity_pool.authority_stable_key,
        )
    task8_keys = [
        (prediction.prediction_date, prediction.source_ref.forecast_quantile)
        for prediction in task8_daily_predictions
    ]
    if len(set(task8_keys)) != len(task8_keys):
        _raise(
            "authority_date_coverage_incomplete",
            authority_stable_key=capacity_pool.authority_stable_key,
        )
    for prediction in task8_daily_predictions:
        if (prediction.farm_id, prediction.subfarm_id, prediction.variety_id) not in member_keys:
            _raise(
                "authority_scope_mismatch",
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=capacity_pool.authority_stable_key,
            )
    expected_task8 = {(day, quantile) for day in forecast_dates for quantile in quantiles}
    if set(task8_keys) != expected_task8:
        _raise(
            "authority_date_coverage_incomplete",
            authority_stable_key=capacity_pool.authority_stable_key,
        )


def _canonical_payload(
    *,
    request: Task9ARequest,
    manifest: tuple[ResolvedAuthorityBinding, ...],
) -> dict[str, object]:
    return {
        "assembly_schema_version": "task9-authority-request-assembly-v1",
        "request": _sorted_request_snapshot(request),
        "authority_manifest": [_semantic_binding_payload(item) for item in manifest],
    }


def assemble_task9_request_from_resolved_authorities(
    *,
    as_of_date: date,
    forecast_start_date: date,
    forecast_end_date: date,
    capacity_pool: ResolvedCapacityPoolAuthority,
    daily_capacities: tuple[ResolvedDailyCapacityAuthority, ...],
    run_package: ResolvedRunParameterPackageAuthority,
    initial_inventory: ResolvedInitialInventoryAuthority,
    mature_losses: tuple[ResolvedMatureLossAuthority, ...],
    task8_daily_predictions: tuple[Task8DailyPredictionInput, ...],
    daily_weather_features: tuple[DailyWeatherFeatureInput, ...],
) -> Task9AuthorityRequestAssembly:
    forecast_dates = _date_range(forecast_start_date, forecast_end_date)
    quantiles = CANONICAL_FORECAST_QUANTILES
    _validate_scope(
        capacity_pool=capacity_pool,
        run_package=run_package,
        initial_inventory=initial_inventory,
    )
    _validate_coverage(
        forecast_dates=forecast_dates,
        quantiles=quantiles,
        capacity_pool=capacity_pool,
        daily_capacities=daily_capacities,
        mature_losses=mature_losses,
        task8_daily_predictions=task8_daily_predictions,
    )

    pool_input = _capacity_pool_input(capacity_pool)
    daily_inputs = [
        _daily_capacity_input(item, as_of_date=as_of_date)
        for item in sorted(
            daily_capacities,
            key=lambda item: (item.semantic_input.capacity_date, item.authority_stable_key),
        )
    ]
    run_refs = _run_parameter_refs(run_package, as_of_date=as_of_date)
    initial_cohorts = _initial_inventory_inputs(
        initial_inventory,
        pool=capacity_pool,
        as_of_date=as_of_date,
    )
    mature_loss_inputs = [
        _mature_loss_input(item, as_of_date=as_of_date)
        for item in sorted(
            mature_losses,
            key=lambda item: (
                item.semantic_input.state_date,
                item.semantic_input.capacity_pool_code,
                item.semantic_input.forecast_quantile.value,
            ),
        )
    ]
    try:
        request = Task9ARequest(
            as_of_date=as_of_date,
            forecast_start_date=forecast_start_date,
            forecast_end_date=forecast_end_date,
            forecast_quantiles=list(quantiles),
            destination_factory_id=run_package.semantic_input.destination_factory_id,
            farm_timezone=run_package.semantic_input.farm_timezone,
            destination_factory_timezone=run_package.semantic_input.destination_factory_timezone,
            harvest_bucket_anchor_local_time=(
                run_package.semantic_input.harvest_bucket_anchor_local_time
            ),
            harvest_to_arrival_lag_days=run_package.semantic_input.harvest_to_arrival_lag_days,
            holiday_calendar_version=run_package.holiday_calendar.semantic_bundle.calendar_version,
            holiday_calendar_hash=run_package.holiday_calendar.semantic_bundle.calendar_hash,
            holiday_dates=_holiday_request_dates(run_package),
            weather_rule_config=_weather_rule_config(run_package),
            run_parameter_source_refs=run_refs,
            capacity_pools=[pool_input],
            daily_capacity_inputs=daily_inputs,
            daily_weather_features=sorted(
                daily_weather_features,
                key=lambda item: (item.capacity_date, item.capacity_pool_id, item.feature_id),
            ),
            task8_daily_predictions=sorted(
                task8_daily_predictions,
                key=lambda item: (
                    item.prediction_date,
                    item.farm_id,
                    -1 if item.subfarm_id is None else item.subfarm_id,
                    item.variety_id,
                    item.source_ref.forecast_quantile.value,
                ),
            ),
            initial_inventory_cohorts=initial_cohorts,
            initial_opening_mature_inventory_kg=(
                initial_inventory.semantic_bundle.initial_opening_mature_inventory_kg
            ),
            mature_inventory_loss_inputs=mature_loss_inputs,
        )
    except ValidationError as exc:
        _raise(
            "authority_request_schema_rejected",
            details={"validation_errors": exc.errors()},
        )
    validated = _validated_request(request)
    if validated.blockers:
        _raise(
            "authority_request_schema_rejected",
            details={"blockers": tuple(validated.blockers)},
        )
    manifest = _manifest(
        (
            capacity_pool,
            *daily_capacities,
            run_package,
            run_package.holiday_calendar,
            run_package.weather_rule,
            initial_inventory,
            *mature_losses,
        )
    )
    parameter_source_refs = tuple(
        sorted(
            [
                *run_refs,
                *(ref for item in daily_inputs for ref in item.capacity_parameter_source_refs),
                *(item.source_ref for item in mature_loss_inputs),
            ],
            key=lambda item: (
                _PARAMETER_SOURCE_REF_ORDER[item.parameter_code],
                item.source_record_key,
                item.source_row_hash,
            ),
        )
    )
    payload = _canonical_payload(request=request, manifest=manifest)
    return Task9AuthorityRequestAssembly(
        request=request,
        authority_manifest=manifest,
        parameter_source_refs=parameter_source_refs,
        canonical_payload=canonical_json_value(payload),  # type: ignore[arg-type]
        assembly_hash=sha256_hex(payload),
    )
