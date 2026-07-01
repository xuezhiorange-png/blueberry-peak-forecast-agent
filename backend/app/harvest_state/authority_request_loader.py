from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol

from pydantic import ValidationError

from backend.app.harvest_state.authority_request_errors import (
    Task9AuthorityRequestAssemblyError,
)
from backend.app.harvest_state.authority_request_types import (
    ResolvedAuthorityBinding,
    Task9AuthorityAssemblyContext,
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
    JsonValue,
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
    Task8PredictionVerificationSnapshot,
    Task9ARequest,
    WeatherEfficiencyRuleConfig,
)
from backend.app.harvest_state.service import (
    _validated_request as _service_validated_request,
)

TASK9_HISTORICAL_SOURCE_SYSTEM = "task9_historical_authority"

# Semantic fields for Task8PredictionSourceRef (exclude DB IDs).
# NOTE: farm_id, subfarm_id, variety_id are on Task8DailyPredictionInput, not here.
_SEMANTIC_TASK8_SOURCE_REF_KEYS: tuple[str, ...] = (
    "maturity_model_version",
    "maturity_model_config_hash",
    "maturity_model_source_signature",
    "maturity_model_artifact_hash",
    "maturity_forecast_source_signature",
    "maturity_forecast_as_of_date",
    "prediction_date",
    "forecast_quantile",
    "source_quantity_kg",
)

# Semantic fields for Task8PredictionVerificationSnapshot (exclude DB IDs).
_SEMANTIC_TASK8_VERIFICATION_KEYS: tuple[str, ...] = (
    "maturity_model_version",
    "maturity_model_config_hash",
    "maturity_model_source_signature",
    "maturity_model_artifact_hash",
    "maturity_forecast_run_status",
    "maturity_forecast_source_signature",
    "maturity_forecast_as_of_date",
    "maturity_forecast_prediction_start_date",
    "maturity_forecast_prediction_end_date",
    "prediction_date",
    "farm_id",
    "subfarm_id",
    "variety_id",
    "p50_kg",
    "p80_kg",
    "p90_kg",
)


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


def _semantic_binding_payload(binding: ResolvedAuthorityBinding) -> dict[str, JsonValue]:
    return {
        "authority_family": binding.authority_family.value,
        "authority_stable_key": binding.authority_stable_key,
        "business_version": binding.business_version,
        "revision": binding.revision,
        "row_hash": binding.row_hash,
    }


# ── Family-specific source record key builders (Finding 1) ──────────────


def _run_package_source_record_key(
    binding: ResolvedAuthorityBinding,
    *,
    package_version: str,
) -> str:
    """run-package:{season_id}:{destination_factory_id}:{farm_scope_key}:{package_version}:{revision}"""
    return f"{binding.authority_stable_key}:{package_version}:{binding.revision}"


def _holiday_source_record_key(
    binding: ResolvedAuthorityBinding,
    *,
    calendar_version: str,
) -> str:
    """holiday-calendar:{season_id}:{calendar_code}:{lifecycle_timezone_name}:{calendar_version}:{revision}"""
    return f"{binding.authority_stable_key}:{calendar_version}:{binding.revision}"


def _weather_source_record_key(
    binding: ResolvedAuthorityBinding,
    *,
    rule_version: str,
) -> str:
    """weather-rule:{rule_code}:{lifecycle_timezone_name}:{rule_version}:{revision}"""
    return f"{binding.authority_stable_key}:{rule_version}:{binding.revision}"


def _daily_capacity_source_record_key(
    binding: ResolvedAuthorityBinding,
    *,
    daily_capacity_revision: int,
) -> str:
    """daily-capacity:{season_id}:{destination_factory_id}:{capacity_pool_code}:{capacity_pool_version}:{capacity_pool_revision}:{capacity_date}:{daily_capacity_revision}"""
    return f"{binding.authority_stable_key}:{daily_capacity_revision}"


def _initial_inventory_source_record_key(
    binding: ResolvedAuthorityBinding,
    *,
    snapshot_version: str,
) -> str:
    """initial-inventory:{season_id}:{destination_factory_id}:{opening_state_date}:{snapshot_version}:{revision}"""
    return f"{binding.authority_stable_key}:{snapshot_version}:{binding.revision}"


def _mature_loss_source_record_key(
    binding: ResolvedAuthorityBinding,
    *,
    loss_version: str,
) -> str:
    """mature-loss:{season_id}:{destination_factory_id}:{capacity_pool_code}:{state_date}:{forecast_quantile}:{loss_version}:{revision}"""
    return f"{binding.authority_stable_key}:{loss_version}:{binding.revision}"


# ── Parameter source ref builders ────────────────────────────────────────


def _parameter_source_ref(
    *,
    code: str,
    binding: ResolvedAuthorityBinding,
    source_record_key: str,
    source_version: str,
    available_at: date,
    as_of_date: date,
) -> ParameterSourceRef:
    return ParameterSourceRef(
        parameter_code=code,
        source_system=TASK9_HISTORICAL_SOURCE_SYSTEM,
        source_record_key=source_record_key,
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
    source_key = _daily_capacity_source_record_key(
        binding, daily_capacity_revision=daily.daily_capacity_revision
    )
    source_version = daily.capacity_pool_version
    if daily.capacity_input_mode is CapacityInputMode.LABOR_DERIVED:
        codes: tuple[str, ...] = (
            "PLANNED_PICKER_COUNT",
            "PICKER_PRODUCTIVITY",
            "LABOR_AVAILABILITY_RATIO",
            "OPERATIONAL_EFFICIENCY_RATIO",
        )
    else:
        codes = (
            "DIRECT_NOMINAL_CAPACITY",
            "LABOR_AVAILABILITY_RATIO",
            "OPERATIONAL_EFFICIENCY_RATIO",
        )
    return [
        _parameter_source_ref(
            code=code,
            binding=binding,
            source_record_key=source_key,
            source_version=source_version,
            available_at=daily.available_at_local_date,
            as_of_date=as_of_date,
        )
        for code in codes
    ]


def _validate_daily_capacity_parent(
    authority: ResolvedDailyCapacityAuthority,
    *,
    pools: tuple[ResolvedCapacityPoolAuthority, ...],
) -> None:
    """Verify daily capacity's parent pool identity against each pool in the assembly."""
    daily = authority.semantic_input
    found = False
    for pool_auth in pools:
        parent = pool_auth.semantic_bundle
        if daily.capacity_pool_code != parent.capacity_pool_code:
            continue
        if (
            daily.capacity_pool_version != parent.capacity_pool_version
            or daily.capacity_pool_revision != parent.revision
        ):
            _raise(
                "authority_parent_pool_mismatch",
                authority_family=AuthorityFamily.DAILY_CAPACITY,
                authority_stable_key=authority.authority_stable_key,
            )
        found = True
        break
    if not found:
        _raise(
            "authority_parent_pool_mismatch",
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            authority_stable_key=authority.authority_stable_key,
        )


def _daily_capacity_input(
    authority: ResolvedDailyCapacityAuthority,
    *,
    as_of_date: date,
) -> DailyCapacityInput:
    daily = authority.semantic_input
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

    package_source_key = _run_package_source_record_key(
        package_binding, package_version=package.package_version
    )
    holiday_source_key = _holiday_source_record_key(
        holiday_binding,
        calendar_version=authority.holiday_calendar.semantic_bundle.calendar_version,
    )
    weather_source_key = _weather_source_record_key(
        weather_binding,
        rule_version=authority.weather_rule.semantic_input.rule_version,
    )

    return [
        _parameter_source_ref(
            code="HOLIDAY_CALENDAR",
            binding=holiday_binding,
            source_record_key=holiday_source_key,
            source_version=authority.holiday_calendar.semantic_bundle.calendar_version,
            available_at=authority.holiday_calendar.semantic_bundle.available_at_local_date,
            as_of_date=as_of_date,
        ),
        _parameter_source_ref(
            code="WEATHER_RULE_CONFIG",
            binding=weather_binding,
            source_record_key=weather_source_key,
            source_version=authority.weather_rule.semantic_input.rule_version,
            available_at=authority.weather_rule.semantic_input.available_at_local_date,
            as_of_date=as_of_date,
        ),
        _parameter_source_ref(
            code="HARVEST_TO_ARRIVAL_LAG",
            binding=package_binding,
            source_record_key=package_source_key,
            source_version=package.package_version,
            available_at=package.available_at_local_date,
            as_of_date=as_of_date,
        ),
        _parameter_source_ref(
            code="TIMEZONE_CONFIG",
            binding=package_binding,
            source_record_key=package_source_key,
            source_version=package.package_version,
            available_at=package.available_at_local_date,
            as_of_date=as_of_date,
        ),
        _parameter_source_ref(
            code="HARVEST_BUCKET_ANCHOR_TIME",
            binding=package_binding,
            source_record_key=package_source_key,
            source_version=package.package_version,
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
    binding = _binding(authority)
    source_key = _initial_inventory_source_record_key(
        binding, snapshot_version=bundle.snapshot_version
    )
    return InitialInventorySourceRef(
        source_system=TASK9_HISTORICAL_SOURCE_SYSTEM,
        source_record_key=source_key,
        source_version=bundle.snapshot_version,
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
    return out


def _mature_loss_input(
    authority: ResolvedMatureLossAuthority,
    *,
    as_of_date: date,
) -> MatureInventoryLossInput:
    loss = authority.semantic_input
    binding = _binding(authority)
    source_key = _mature_loss_source_record_key(binding, loss_version=loss.loss_version)
    return MatureInventoryLossInput(
        state_date=loss.state_date,
        capacity_pool_id=loss.capacity_pool_code,
        forecast_quantile=loss.forecast_quantile,
        mature_inventory_loss_quantity_kg=loss.mature_inventory_loss_quantity_kg,
        source_ref=_parameter_source_ref(
            code="MATURE_INVENTORY_LOSS",
            binding=binding,
            source_record_key=source_key,
            source_version=loss.loss_version,
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


def _validate_pool_constraints(
    capacity_pools: tuple[ResolvedCapacityPoolAuthority, ...],
) -> None:
    """Validate multi-pool constraints: unique codes, no shared members, same season/factory."""
    if len(capacity_pools) < 1:
        _raise("authority_scope_mismatch", details={"error": "at least one pool required"})
    codes = [pool.semantic_bundle.capacity_pool_code for pool in capacity_pools]
    if len(set(codes)) != len(codes):
        _raise(
            "authority_scope_mismatch",
            details={"error": "duplicate pool codes", "codes": codes},
        )
    first = capacity_pools[0].semantic_bundle
    for pool in capacity_pools[1:]:
        bundle = pool.semantic_bundle
        if (
            bundle.season_id != first.season_id
            or bundle.destination_factory_id != first.destination_factory_id
        ):
            _raise(
                "authority_scope_mismatch",
                authority_stable_key=pool.authority_stable_key,
                details={"error": "cross-factory pool"},
            )
    member_to_pool: dict[tuple[int, int | None, int], str] = {}
    for pool in capacity_pools:
        bundle = pool.semantic_bundle
        for member in bundle.members:
            key = (member.farm_id, member.subfarm_id, member.variety_id)
            if key in member_to_pool:
                _raise(
                    "authority_pool_membership_conflict",
                    authority_stable_key=pool.authority_stable_key,
                    details={
                        "error": "member in multiple pools",
                        "member": list(key),
                        "first_pool": member_to_pool[key],
                        "second_pool": bundle.capacity_pool_code,
                    },
                )
            member_to_pool[key] = bundle.capacity_pool_code


def _validate_scope(
    *,
    capacity_pools: tuple[ResolvedCapacityPoolAuthority, ...],
    run_package: ResolvedRunParameterPackageAuthority,
    initial_inventory: ResolvedInitialInventoryAuthority,
    context: Task9AuthorityAssemblyContext,
) -> None:
    """Validate scope consistency across all pools, run package, and inventory."""
    pool = capacity_pools[0].semantic_bundle
    package = run_package.semantic_input
    inventory = initial_inventory.semantic_bundle

    # Season / factory scope must match across all pools.
    for pool_auth in capacity_pools:
        bundle = pool_auth.semantic_bundle
        if (
            bundle.season_id != pool.season_id
            or bundle.destination_factory_id != pool.destination_factory_id
        ):
            _raise(
                "authority_scope_mismatch",
                authority_stable_key=pool_auth.authority_stable_key,
            )

    if pool.season_id != package.season_id or pool.season_id != inventory.season_id:
        _raise(
            "authority_scope_mismatch",
            authority_stable_key=capacity_pools[0].authority_stable_key,
        )
    if (
        pool.destination_factory_id != package.destination_factory_id
        or pool.destination_factory_id != inventory.destination_factory_id
    ):
        _raise(
            "authority_scope_mismatch",
            authority_stable_key=capacity_pools[0].authority_stable_key,
        )

    # Timezone match between run package and its dependencies.
    if (
        package.destination_factory_timezone
        != run_package.holiday_calendar.semantic_bundle.lifecycle_timezone_name
    ):
        _raise(
            "authority_scope_mismatch",
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=run_package.authority_stable_key,
            details={"error": "holiday timezone mismatch"},
        )
    if (
        package.destination_factory_timezone
        != run_package.weather_rule.semantic_input.lifecycle_timezone_name
    ):
        _raise(
            "authority_scope_mismatch",
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=run_package.authority_stable_key,
            details={"error": "weather timezone mismatch"},
        )

    # Assembly context mode must match all authorities.
    expected_mode = context.mode
    for pool_auth in capacity_pools:
        if pool_auth.mode != expected_mode:
            _raise(
                "authority_resolution_mode_mismatch",
                authority_stable_key=pool_auth.authority_stable_key,
                details={"expected": expected_mode.value, "actual": pool_auth.mode.value},
            )
    if run_package.mode != expected_mode:
        _raise(
            "authority_resolution_mode_mismatch",
            authority_stable_key=run_package.authority_stable_key,
            details={"expected": expected_mode.value, "actual": run_package.mode.value},
        )
    if initial_inventory.mode != expected_mode:
        _raise(
            "authority_resolution_mode_mismatch",
            authority_stable_key=initial_inventory.authority_stable_key,
            details={"expected": expected_mode.value, "actual": initial_inventory.mode.value},
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

    # ── Daily capacity coverage ──────────────────────────────────────
    daily_keys = [
        (
            daily_authority.semantic_input.capacity_date,
            daily_authority.semantic_input.capacity_pool_code,
        )
        for daily_authority in daily_capacities
    ]
    if len(set(daily_keys)) != len(daily_keys):
        _raise(
            "authority_date_coverage_incomplete",
            authority_stable_key=capacity_pool.authority_stable_key,
            details={"error": "duplicate daily capacity"},
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

    # ── Mature loss coverage ─────────────────────────────────────────
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
            details={"error": "duplicate mature loss"},
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

    # ── Task 8 coverage (Finding 3: member-level key) ────────────────
    task8_keys = [
        (
            prediction.prediction_date,
            prediction.source_ref.forecast_quantile,
            prediction.farm_id,
            prediction.subfarm_id,
            prediction.variety_id,
        )
        for prediction in task8_daily_predictions
    ]
    if len(set(task8_keys)) != len(task8_keys):
        _raise(
            "authority_duplicate_task8_prediction",
            authority_stable_key=capacity_pool.authority_stable_key,
        )
    for prediction in task8_daily_predictions:
        if (prediction.farm_id, prediction.subfarm_id, prediction.variety_id) not in member_keys:
            _raise(
                "authority_member_coverage_incomplete",
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=capacity_pool.authority_stable_key,
                details={
                    "error": "pool-outside member",
                    "member": [prediction.farm_id, prediction.subfarm_id, prediction.variety_id],
                },
            )
    expected_task8 = {
        (day, quantile, farm_id, subfarm_id, variety_id)
        for day in forecast_dates
        for quantile in quantiles
        for farm_id, subfarm_id, variety_id in member_keys
    }
    if set(task8_keys) != expected_task8:
        _raise(
            "authority_member_coverage_incomplete",
            authority_stable_key=capacity_pool.authority_stable_key,
            details={"error": "missing member/date/quantile prediction"},
        )


def _validate_weather_coverage(
    *,
    capacity_pool: ResolvedCapacityPoolAuthority,
    weather_features: tuple[DailyWeatherFeatureInput, ...],
    required_feature_ids: list[str],
    forecast_dates: tuple[date, ...],
) -> None:
    """Validate weather feature coverage per pool per date per required feature."""
    pool_code = capacity_pool.semantic_bundle.capacity_pool_code
    feature_keys = {(f.capacity_date, f.capacity_pool_id, f.feature_id) for f in weather_features}
    expected_features = {
        (day, pool_code, feature_id)
        for day in forecast_dates
        for feature_id in required_feature_ids
    }
    if feature_keys != expected_features:
        _raise(
            "authority_member_coverage_incomplete",
            authority_stable_key=capacity_pool.authority_stable_key,
            details={"error": "weather feature coverage incomplete"},
        )


# ── Semantic payload helpers (Finding 2: exclude DB IDs) ────────────────


def _semantic_task8_source_ref_hash(source_ref: object) -> str:
    """Hash only semantic fields of a Task8PredictionSourceRef, excluding DB IDs."""
    semantic_payload: dict[str, object] = {}
    for field_name in _SEMANTIC_TASK8_SOURCE_REF_KEYS:
        semantic_payload[field_name] = getattr(source_ref, field_name)
    return sha256_hex(semantic_payload)


def _semantic_verification_snapshot_dict(
    snapshot: Task8PredictionVerificationSnapshot,
) -> dict[str, object]:
    """Extract only semantic fields from a verification snapshot."""
    return {field: getattr(snapshot, field) for field in _SEMANTIC_TASK8_VERIFICATION_KEYS}


def _semantic_request_snapshot(request: Task9ARequest) -> dict[str, object]:
    """Build a semantic-only snapshot of the request, excluding DB identity fields."""
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
            item.source_ref.forecast_quantile,
        ),
    )
    initial_inputs = sorted(
        request.initial_inventory_cohorts or [],
        key=lambda item: (
            item.cohort_date,
            item.farm_id,
            -1 if item.subfarm_id is None else item.subfarm_id,
            item.variety_id,
            item.forecast_quantile,
        ),
    )
    loss_inputs = sorted(
        request.mature_inventory_loss_inputs,
        key=lambda item: (
            item.state_date,
            item.capacity_pool_id,
            item.forecast_quantile,
        ),
    )

    return {
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
        "run_parameter_source_ref_hashes": sorted(
            [_parameter_source_ref_hash(item) for item in request.run_parameter_source_refs],
        ),
        "capacity_pools": [
            {
                "capacity_pool_id": pool.capacity_pool_id,
                "capacity_pool_grain": pool.capacity_pool_grain,
                "members": [
                    member.model_dump(mode="python")
                    for member in sorted(
                        pool.members,
                        key=lambda m: (
                            m.farm_id,
                            -1 if m.subfarm_id is None else m.subfarm_id,
                            m.variety_id,
                        ),
                    )
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
                    _parameter_source_ref_hash(ref) for ref in item.capacity_parameter_source_refs
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
                "source_ref_hash": _parameter_source_ref_hash(item.source_ref),
            }
            for item in weather_inputs
        ],
        "task8_daily_predictions": [
            {
                "prediction_date": item.prediction_date,
                "farm_id": item.farm_id,
                "subfarm_id": item.subfarm_id,
                "variety_id": item.variety_id,
                "source_ref_hash": _semantic_task8_source_ref_hash(item.source_ref),
                "verification_snapshot": _semantic_verification_snapshot_dict(
                    item.verification_snapshot
                ),
                "verification_snapshot_hash": sha256_hex(
                    _semantic_verification_snapshot_dict(item.verification_snapshot)
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
                "source_ref_hash": _initial_inventory_ref_hash(item.source_ref),
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
                "source_ref_hash": _parameter_source_ref_hash(item.source_ref),
            }
            for item in loss_inputs
        ],
    }


def _parameter_source_ref_hash(ref: ParameterSourceRef) -> str:
    """Hash a ParameterSourceRef by its semantic fields."""
    return _common_source_ref_hash(
        source_system=ref.source_system,
        source_record_key=ref.source_record_key,
        source_version=ref.source_version,
        source_row_hash=ref.source_row_hash,
        available_at=ref.available_at,
        as_of_date=ref.as_of_date,
    )


def _initial_inventory_ref_hash(ref: InitialInventorySourceRef) -> str:
    """Hash an InitialInventorySourceRef by its semantic fields."""
    return _common_source_ref_hash(
        source_system=ref.source_system,
        source_record_key=ref.source_record_key,
        source_version=ref.source_version,
        source_row_hash=ref.source_row_hash,
        available_at=ref.available_at,
        as_of_date=ref.as_of_date,
    )


def _common_source_ref_hash(
    *,
    source_system: str,
    source_record_key: str,
    source_version: str,
    source_row_hash: str,
    available_at: date,
    as_of_date: date,
) -> str:
    """Hash common source ref fields (no DB identity)."""
    return sha256_hex(
        {
            "source_system": source_system,
            "source_record_key": source_record_key,
            "source_version": source_version,
            "source_row_hash": source_row_hash,
            "available_at": available_at,
            "as_of_date": as_of_date,
        }
    )


def _canonical_payload(
    *,
    request: Task9ARequest,
    manifest: tuple[ResolvedAuthorityBinding, ...],
) -> MappingProxyType[str, JsonValue]:
    """Build an immutable canonical payload excluding DB identity fields."""
    manifest_payload: list[JsonValue] = [_semantic_binding_payload(item) for item in manifest]
    raw: dict[str, object] = {
        "assembly_schema_version": "task9-authority-request-assembly-v1",
        "request": _semantic_request_snapshot(request),
        "authority_manifest": manifest_payload,
    }
    canonical = canonical_json_value(raw)
    assert isinstance(canonical, dict)
    return MappingProxyType(canonical)


def _member_in_pool(
    prediction: Task8DailyPredictionInput,
    pool: ResolvedCapacityPoolAuthority,
) -> bool:
    """Check if a task8 prediction's member belongs to the given pool."""
    return (prediction.farm_id, prediction.subfarm_id, prediction.variety_id) in {
        (m.farm_id, m.subfarm_id, m.variety_id) for m in pool.semantic_bundle.members
    }


def assemble_task9_request_from_resolved_authorities(
    *,
    context: Task9AuthorityAssemblyContext,
    capacity_pools: tuple[ResolvedCapacityPoolAuthority, ...],
    daily_capacities: tuple[ResolvedDailyCapacityAuthority, ...],
    run_package: ResolvedRunParameterPackageAuthority,
    initial_inventory: ResolvedInitialInventoryAuthority,
    mature_losses: tuple[ResolvedMatureLossAuthority, ...],
    task8_daily_predictions: tuple[Task8DailyPredictionInput, ...],
    daily_weather_features: tuple[DailyWeatherFeatureInput, ...],
) -> Task9AuthorityRequestAssembly:
    as_of_date = context.as_of_date
    forecast_start_date = context.forecast_start_date
    forecast_end_date = context.forecast_end_date
    forecast_dates = _date_range(forecast_start_date, forecast_end_date)
    quantiles = CANONICAL_FORECAST_QUANTILES

    # ── Multi-pool constraints (Finding 4) ───────────────────────────
    _validate_pool_constraints(capacity_pools)

    # ── Scope validation (Finding 5: context mode) ──────────────────
    _validate_scope(
        capacity_pools=capacity_pools,
        run_package=run_package,
        initial_inventory=initial_inventory,
        context=context,
    )

    # ── Daily capacity parent verification ──────────────────────────
    for daily_auth in daily_capacities:
        _validate_daily_capacity_parent(daily_auth, pools=capacity_pools)

    # ── Per-pool coverage validation ────────────────────────────────
    required_feature_ids = run_package.weather_rule.semantic_input.required_feature_ids
    for pool in capacity_pools:
        pool_code = pool.semantic_bundle.capacity_pool_code
        pool_daily = tuple(
            d for d in daily_capacities if d.semantic_input.capacity_pool_code == pool_code
        )
        pool_losses = tuple(
            loss for loss in mature_losses if loss.semantic_input.capacity_pool_code == pool_code
        )
        pool_task8 = tuple(p for p in task8_daily_predictions if _member_in_pool(p, pool))
        pool_weather = tuple(w for w in daily_weather_features if w.capacity_pool_id == pool_code)

        _validate_coverage(
            forecast_dates=forecast_dates,
            quantiles=quantiles,
            capacity_pool=pool,
            daily_capacities=pool_daily,
            mature_losses=pool_losses,
            task8_daily_predictions=pool_task8,
        )
        _validate_weather_coverage(
            capacity_pool=pool,
            weather_features=pool_weather,
            required_feature_ids=required_feature_ids,
            forecast_dates=forecast_dates,
        )

    # ── Build request inputs ────────────────────────────────────────
    pool_inputs = [_capacity_pool_input(pool) for pool in capacity_pools]
    daily_inputs = [
        _daily_capacity_input(item, as_of_date=as_of_date)
        for item in sorted(
            daily_capacities,
            key=lambda item: (item.semantic_input.capacity_date, item.authority_stable_key),
        )
    ]
    run_refs = _run_parameter_refs(run_package, as_of_date=as_of_date)

    # Build initial inventory cohorts for all pools combined.
    all_initial_cohorts: list[InitialInventoryCohortInput] = []
    for pool in capacity_pools:
        pool_cohorts = _initial_inventory_inputs(
            initial_inventory, pool=pool, as_of_date=as_of_date
        )
        all_initial_cohorts.extend(pool_cohorts)

    # Validate total opening inventory across all pools.
    total = sum(
        (item.remaining_quantity_kg for item in all_initial_cohorts),
        start=Decimal("0"),
    )
    if total != initial_inventory.semantic_bundle.initial_opening_mature_inventory_kg:
        _raise(
            "authority_initial_inventory_total_mismatch",
            authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
            authority_stable_key=initial_inventory.authority_stable_key,
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
            capacity_pools=pool_inputs,
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
            initial_inventory_cohorts=all_initial_cohorts,
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
    validated = _service_validated_request(request)
    if validated.blockers:
        _raise(
            "authority_request_schema_rejected",
            details={"blockers": tuple(validated.blockers)},
        )

    # ── Manifest includes all pools ─────────────────────────────────
    manifest_authorities: list[_ResolvedAuthorityLike] = [
        *capacity_pools,
        *daily_capacities,
        run_package,
        run_package.holiday_calendar,
        run_package.weather_rule,
        initial_inventory,
        *mature_losses,
    ]
    manifest = _manifest(manifest_authorities)

    # ── Parameter source refs (sort by parameter_code ASC, source_row_hash ASC) ──
    parameter_source_refs = tuple(
        sorted(
            [
                *run_refs,
                *(ref for item in daily_inputs for ref in item.capacity_parameter_source_refs),
                *(item.source_ref for item in mature_loss_inputs),
            ],
            key=lambda item: (item.parameter_code, item.source_row_hash),
        )
    )

    # ── Immutable canonical payload (Finding 6) ─────────────────────
    payload = _canonical_payload(request=request, manifest=manifest)
    assembly_hash = sha256_hex(dict(payload))

    return Task9AuthorityRequestAssembly(
        request=request,
        authority_manifest=manifest,
        parameter_source_refs=parameter_source_refs,
        canonical_payload=payload,
        assembly_hash=assembly_hash,
    )
