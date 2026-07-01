from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.authority_repository import (
    _build_persisted_schema,
    _stable_key_from_orm_capacity_pool,
    _stable_key_from_orm_holiday,
    _stable_key_from_orm_initial_inventory,
    _stable_key_from_orm_mature_loss,
    _stable_key_from_orm_run_package,
    _stable_key_from_orm_weather,
    load_capacity_pool_definition_by_id,
    load_daily_capacity_by_id,
    load_holiday_calendar_by_id,
    load_initial_inventory_by_id,
    load_mature_loss_by_id,
    load_run_parameter_package_by_id,
    load_weather_rule_by_id,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityHashConflictError,
)
from backend.app.harvest_state.authority_resolution_errors import (
    AmbiguousHistoricalAuthorityError,
    AuthorityDependencyMismatchError,
    AuthorityEffectiveIntervalMismatchError,
    AuthorityExactReferenceMismatchError,
    AuthorityNotConsumableAtCutoffError,
    AuthorityParentChildMismatchError,
    AuthorityScopeMismatchError,
    HistoricalAuthorityNotFoundError,
    TimezoneAuthorityInvalidError,
)
from backend.app.harvest_state.authority_resolution_types import (
    AuthorityCandidateSnapshot,
    AuthorityExactReference,
    AuthorityResolutionMode,
    CapacityPoolResolutionRequest,
    DailyCapacityResolutionRequest,
    HolidayCalendarResolutionRequest,
    InitialInventoryResolutionRequest,
    MatureLossResolutionRequest,
    ResolvedCapacityPoolAuthority,
    ResolvedDailyCapacityAuthority,
    ResolvedHolidayCalendarAuthority,
    ResolvedInitialInventoryAuthority,
    ResolvedMatureLossAuthority,
    ResolvedRunParameterPackageAuthority,
    ResolvedWeatherRuleAuthority,
    RunParameterPackageResolutionRequest,
    WeatherRuleResolutionRequest,
)
from backend.app.harvest_state.authority_schemas import (
    Task9CapacityPoolDefinitionSemanticBundle,
    Task9CapacityPoolMemberSchema,
    Task9DailyCapacitySemanticInput,
    Task9HolidayCalendarDateSchema,
    Task9HolidayCalendarSemanticBundle,
    Task9InitialInventoryCohortSchema,
    Task9InitialInventorySemanticBundle,
    Task9MatureLossSemanticInput,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleSemanticInput,
)
from backend.app.harvest_state.enums import AuthorityFamily, AuthorityStatus
from backend.app.models.task9_authority import (
    Task9CapacityPoolDefinition,
    Task9CapacityPoolMember,
    Task9DailyCapacityAuthority,
    Task9HolidayCalendarDate,
    Task9HolidayCalendarVersion,
    Task9InitialInventoryCohort,
    Task9InitialInventorySnapshot,
    Task9MatureInventoryLossAuthority,
    Task9RunParameterPackage,
    Task9WeatherRuleConfigVersion,
)


def _validate_timezone_name(timezone_name: str) -> str:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise TimezoneAuthorityInvalidError(timezone_name=timezone_name) from exc
    return timezone_name


def _candidate_is_current_operational(
    snapshot: AuthorityCandidateSnapshot,
    *,
    as_of_local_date: date,
) -> bool:
    return (
        snapshot.status == AuthorityStatus.ACTIVE
        and snapshot.available_at_local_date <= as_of_local_date
        and snapshot.consumable_from_local_date is not None
        and snapshot.consumable_from_local_date <= as_of_local_date
        and snapshot.consumable_to_local_date is None
    )


def _candidate_is_consumable_at_as_of(
    snapshot: AuthorityCandidateSnapshot,
    *,
    as_of_local_date: date,
) -> bool:
    return (
        snapshot.status
        in (
            AuthorityStatus.ACTIVE,
            AuthorityStatus.SUPERSEDED,
            AuthorityStatus.RETIRED,
        )
        and snapshot.available_at_local_date <= as_of_local_date
        and snapshot.consumable_from_local_date is not None
        and snapshot.consumable_from_local_date <= as_of_local_date
        and (
            snapshot.consumable_to_local_date is None
            or as_of_local_date < snapshot.consumable_to_local_date
        )
    )


def _semantic_identity(snapshot: AuthorityCandidateSnapshot) -> tuple[str, str, int, str]:
    return (
        snapshot.authority_stable_key,
        snapshot.business_version,
        snapshot.revision,
        snapshot.row_hash,
    )


def _choose_candidate_snapshot(
    snapshots: list[AuthorityCandidateSnapshot],
    *,
    authority_family: AuthorityFamily,
    as_of_local_date: date,
    reason: str,
) -> AuthorityCandidateSnapshot:
    if not snapshots:
        raise ValueError("snapshots must be non-empty")
    first_identity = _semantic_identity(snapshots[0])
    if any(_semantic_identity(snapshot) != first_identity for snapshot in snapshots[1:]):
        raise AmbiguousHistoricalAuthorityError(
            authority_family=authority_family,
            as_of_local_date=as_of_local_date,
            business_key=snapshots[0].authority_stable_key,
            details={
                "reason": reason,
                "candidate_count": len(snapshots),
            },
        )
    return sorted(
        snapshots,
        key=lambda snapshot: (
            snapshot.authority_stable_key,
            snapshot.business_version,
            snapshot.revision,
            snapshot.row_hash,
        ),
    )[0]


def _effective_interval_contains(
    *,
    effective_from: date,
    effective_to: date | None,
    target_local_date: date,
) -> bool:
    return effective_from <= target_local_date and (
        effective_to is None or target_local_date <= effective_to
    )


def _current_predicates(
    model: Any,
    *,
    as_of_local_date: date,
) -> tuple[Any, ...]:
    return (
        model.status == AuthorityStatus.ACTIVE,
        model.available_at_local_date <= as_of_local_date,
        model.consumable_from_local_date.is_not(None),
        model.consumable_from_local_date <= as_of_local_date,
        model.consumable_to_local_date.is_(None),
    )


def _historical_predicates(
    model: Any,
    *,
    as_of_local_date: date,
) -> tuple[Any, ...]:
    return (
        model.status.in_(
            [AuthorityStatus.ACTIVE, AuthorityStatus.SUPERSEDED, AuthorityStatus.RETIRED]
        ),
        model.available_at_local_date <= as_of_local_date,
        model.consumable_from_local_date.is_not(None),
        model.consumable_from_local_date <= as_of_local_date,
        or_(
            model.consumable_to_local_date.is_(None),
            as_of_local_date < model.consumable_to_local_date,
        ),
    )


def _predicates_for_mode(
    model: Any,
    *,
    mode: AuthorityResolutionMode,
    as_of_local_date: date,
) -> tuple[Any, ...]:
    if mode == AuthorityResolutionMode.CURRENT_OPERATIONAL:
        return _current_predicates(model, as_of_local_date=as_of_local_date)
    return _historical_predicates(model, as_of_local_date=as_of_local_date)


def _snapshot_visible_for_mode(
    snapshot: AuthorityCandidateSnapshot,
    *,
    mode: AuthorityResolutionMode,
    as_of_local_date: date,
) -> bool:
    if mode == AuthorityResolutionMode.CURRENT_OPERATIONAL:
        return _candidate_is_current_operational(
            snapshot,
            as_of_local_date=as_of_local_date,
        )
    return _candidate_is_consumable_at_as_of(
        snapshot,
        as_of_local_date=as_of_local_date,
    )


async def _load_row_by_id(
    session: AsyncSession,
    *,
    model: Any,
    authority_id: int,
) -> Any:
    return (await session.execute(select(model).where(model.id == authority_id))).scalar_one()


def _build_candidate_snapshot(
    *,
    authority_id: int,
    authority_family: AuthorityFamily,
    authority_stable_key: str,
    business_version: str,
    revision: int,
    row_hash: str,
    status: str,
    available_at_local_date: date,
    consumable_from_local_date: date | None,
    consumable_to_local_date: date | None,
) -> AuthorityCandidateSnapshot:
    return AuthorityCandidateSnapshot(
        authority_id=authority_id,
        authority_family=authority_family,
        authority_stable_key=authority_stable_key,
        business_version=business_version,
        revision=revision,
        row_hash=row_hash,
        status=status,
        available_at_local_date=available_at_local_date,
        consumable_from_local_date=consumable_from_local_date,
        consumable_to_local_date=consumable_to_local_date,
    )


def _assert_exact_reference_match(
    *,
    resolved: ResolvedCapacityPoolAuthority
    | ResolvedDailyCapacityAuthority
    | ResolvedHolidayCalendarAuthority
    | ResolvedWeatherRuleAuthority
    | ResolvedRunParameterPackageAuthority
    | ResolvedInitialInventoryAuthority
    | ResolvedMatureLossAuthority,
    exact_reference: AuthorityExactReference,
) -> None:
    if resolved.row_hash != exact_reference.row_hash:
        raise AuthorityHashConflictError(
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            expected_hash=exact_reference.row_hash,
            actual_hash=resolved.row_hash,
            details={"reason": "exact_reference_row_hash_mismatch"},
        )
    if (
        resolved.authority_id != exact_reference.authority_id
        or resolved.authority_stable_key != exact_reference.authority_stable_key
        or resolved.business_version != exact_reference.business_version
        or resolved.revision != exact_reference.revision
    ):
        raise AuthorityExactReferenceMismatchError(
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            details={
                "reason": "exact_reference_identity_mismatch",
                "expected_authority_id": exact_reference.authority_id,
                "actual_authority_id": resolved.authority_id,
                "expected_stable_key": exact_reference.authority_stable_key,
                "actual_stable_key": resolved.authority_stable_key,
                "expected_business_version": exact_reference.business_version,
                "actual_business_version": resolved.business_version,
                "expected_revision": exact_reference.revision,
                "actual_revision": resolved.revision,
            },
        )


def _raise_dependency_from_canonical_error(
    exc: ValueError,
    *,
    ctx: RunPackageDependencyErrorContext,
) -> None:
    """Convert canonical builder ValueError to typed AuthorityDependencyMismatchError."""
    msg = str(exc)
    if "RUN_PARAMETER_DEPENDENCY_SCOPE_CONFLICT" in msg:
        raise AuthorityDependencyMismatchError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=ctx.package_stable_key,
            details={
                "reason": "holiday_season_mismatch",
                "dependency_family": "holiday_calendar_version",
                "dependency_authority_stable_key": ctx.holiday_stable_key,
                "expected_season_id": ctx.package_season_id,
                "actual_season_id": ctx.holiday_season_id,
            },
        ) from exc
    if "RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT" in msg:
        # Deterministic precedence: holiday first, then weather.
        if ctx.package_destination_timezone != ctx.holiday_timezone:
            raise AuthorityDependencyMismatchError(
                authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_stable_key=ctx.package_stable_key,
                details={
                    "reason": "dependency_timezone_mismatch",
                    "dependency_family": "holiday_calendar_version",
                    "dependency_authority_stable_key": ctx.holiday_stable_key,
                    "expected_timezone": ctx.package_destination_timezone,
                    "actual_timezone": ctx.holiday_timezone,
                },
            ) from exc
        if ctx.package_destination_timezone != ctx.weather_timezone:
            raise AuthorityDependencyMismatchError(
                authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_stable_key=ctx.package_stable_key,
                details={
                    "reason": "dependency_timezone_mismatch",
                    "dependency_family": "weather_rule_config_version",
                    "dependency_authority_stable_key": ctx.weather_stable_key,
                    "expected_timezone": ctx.package_destination_timezone,
                    "actual_timezone": ctx.weather_timezone,
                },
            ) from exc
        # Canonical builder reported timezone conflict but full context shows
        # no difference — fail closed as internal canonical parity error.
        raise AuthorityDependencyMismatchError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=ctx.package_stable_key,
            details={
                "reason": "canonical_dependency_context_parity_error",
                "package_authority_stable_key": ctx.package_stable_key,
                "holiday_dependency_authority_stable_key": ctx.holiday_stable_key,
                "weather_dependency_authority_stable_key": ctx.weather_stable_key,
                "package_destination_timezone": ctx.package_destination_timezone,
                "holiday_timezone": ctx.holiday_timezone,
                "weather_timezone": ctx.weather_timezone,
            },
        ) from exc
    raise


def _assert_scope(
    *,
    authority_family: AuthorityFamily,
    authority_stable_key: str,
    expected: dict[str, object],
    actual: dict[str, object],
) -> None:
    for key, expected_value in expected.items():
        if actual[key] != expected_value:
            raise AuthorityScopeMismatchError(
                authority_family=authority_family,
                authority_stable_key=authority_stable_key,
                details={
                    "reason": "scope_field_mismatch",
                    "field": key,
                    "expected": expected_value,
                    "actual": actual[key],
                },
            )


def _assert_consumable(
    *,
    snapshot: AuthorityCandidateSnapshot,
    mode: AuthorityResolutionMode,
    as_of_local_date: date,
) -> None:
    if mode == AuthorityResolutionMode.CURRENT_OPERATIONAL:
        ok = _candidate_is_current_operational(snapshot, as_of_local_date=as_of_local_date)
    else:
        ok = _candidate_is_consumable_at_as_of(snapshot, as_of_local_date=as_of_local_date)
    if not ok:
        raise AuthorityNotConsumableAtCutoffError(
            authority_family=snapshot.authority_family,
            authority_stable_key=snapshot.authority_stable_key,
            as_of_local_date=as_of_local_date,
            details={"reason": "resolved_row_not_consumable_at_cutoff"},
        )


async def _resolved_capacity_pool_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    mode: AuthorityResolutionMode,
) -> ResolvedCapacityPoolAuthority:
    load_result = await load_capacity_pool_definition_by_id(session, authority_id=authority_id)
    row = await _load_row_by_id(
        session,
        model=Task9CapacityPoolDefinition,
        authority_id=authority_id,
    )
    members = list(
        (
            await session.execute(
                select(Task9CapacityPoolMember)
                .where(Task9CapacityPoolMember.capacity_pool_definition_id == row.id)
                .order_by(
                    Task9CapacityPoolMember.farm_id,
                    Task9CapacityPoolMember.subfarm_id,
                    Task9CapacityPoolMember.variety_id,
                )
            )
        ).scalars()
    )
    stable_key = _stable_key_from_orm_capacity_pool(row)
    bundle = _build_persisted_schema(
        Task9CapacityPoolDefinitionSemanticBundle,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key=stable_key,
        component="resolution_capacity_pool_bundle",
        season_id=row.season_id,
        destination_factory_id=row.destination_factory_id,
        capacity_pool_code=row.capacity_pool_code,
        capacity_pool_grain=row.capacity_pool_grain,
        capacity_input_mode=row.capacity_input_mode,
        capacity_pool_version=row.capacity_pool_version,
        revision=row.revision,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
        status=row.status,
        status_changed_at=row.status_changed_at,
        source_system=row.source_system,
        source_record_key=row.source_record_key,
        source_version=row.source_version,
        members=[
            Task9CapacityPoolMemberSchema(
                farm_id=member.farm_id,
                subfarm_id=member.subfarm_id,
                variety_id=member.variety_id,
            )
            for member in members
        ],
    )
    return ResolvedCapacityPoolAuthority(
        mode=mode,
        authority_id=row.id,
        authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_stable_key=stable_key,
        business_version=row.capacity_pool_version,
        revision=row.revision,
        row_hash=load_result.parent.row_hash,
        status=load_result.parent.status,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=load_result.parent.consumable_from_local_date,
        consumable_to_local_date=load_result.parent.consumable_to_local_date,
        semantic_bundle=bundle,
        child_row_hashes=tuple(load_result.child_hashes),
    )


async def _resolved_holiday_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    mode: AuthorityResolutionMode,
) -> ResolvedHolidayCalendarAuthority:
    load_result = await load_holiday_calendar_by_id(session, authority_id=authority_id)
    row = await _load_row_by_id(
        session,
        model=Task9HolidayCalendarVersion,
        authority_id=authority_id,
    )
    dates = list(
        (
            await session.execute(
                select(Task9HolidayCalendarDate)
                .where(Task9HolidayCalendarDate.holiday_calendar_version_id == row.id)
                .order_by(
                    Task9HolidayCalendarDate.holiday_date,
                    Task9HolidayCalendarDate.holiday_code,
                )
            )
        ).scalars()
    )
    stable_key = _stable_key_from_orm_holiday(row)
    bundle = _build_persisted_schema(
        Task9HolidayCalendarSemanticBundle,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=stable_key,
        component="resolution_holiday_bundle",
        season_id=row.season_id,
        calendar_code=row.calendar_code,
        calendar_version=row.calendar_version,
        revision=row.revision,
        calendar_hash=row.calendar_hash,
        region_scope=row.region_scope,
        lifecycle_timezone_name=row.lifecycle_timezone_name,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
        status=row.status,
        status_changed_at=row.status_changed_at,
        source_system=row.source_system,
        source_record_key=row.source_record_key,
        source_version=row.source_version,
        dates=[
            Task9HolidayCalendarDateSchema(
                holiday_date=item.holiday_date,
                holiday_code=item.holiday_code,
                holiday_name=item.holiday_name,
            )
            for item in dates
        ],
    )
    return ResolvedHolidayCalendarAuthority(
        mode=mode,
        authority_id=row.id,
        authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_stable_key=stable_key,
        business_version=row.calendar_version,
        revision=row.revision,
        row_hash=load_result.parent.row_hash,
        status=load_result.parent.status,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=load_result.parent.consumable_from_local_date,
        consumable_to_local_date=load_result.parent.consumable_to_local_date,
        semantic_bundle=bundle,
    )


async def _resolved_weather_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    mode: AuthorityResolutionMode,
) -> ResolvedWeatherRuleAuthority:
    load_result = await load_weather_rule_by_id(session, authority_id=authority_id)
    row = await _load_row_by_id(
        session,
        model=Task9WeatherRuleConfigVersion,
        authority_id=authority_id,
    )
    stable_key = _stable_key_from_orm_weather(row)
    semantic_input = _build_persisted_schema(
        Task9WeatherRuleSemanticInput,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=stable_key,
        component="resolution_weather_rule",
        rule_code=row.rule_code,
        rule_version=row.rule_version,
        revision=row.revision,
        lifecycle_timezone_name=row.lifecycle_timezone_name,
        combination_method=row.combination_method,
        minimum_ratio=row.minimum_ratio,
        maximum_ratio=row.maximum_ratio,
        required_feature_ids=row.required_feature_ids,
        feature_rules=row.feature_rules_json,
        missing_feature_policy=row.missing_feature_policy,
        config_hash=row.config_hash,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
        status=row.status,
        status_changed_at=row.status_changed_at,
        source_system=row.source_system,
        source_record_key=row.source_record_key,
        source_version=row.source_version,
    )
    return ResolvedWeatherRuleAuthority(
        mode=mode,
        authority_id=row.id,
        authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_stable_key=stable_key,
        business_version=row.rule_version,
        revision=row.revision,
        row_hash=load_result.row_hash,
        status=load_result.status,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=load_result.consumable_from_local_date,
        consumable_to_local_date=load_result.consumable_to_local_date,
        semantic_input=semantic_input,
    )


async def _resolved_initial_inventory_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    mode: AuthorityResolutionMode,
) -> ResolvedInitialInventoryAuthority:
    load_result = await load_initial_inventory_by_id(session, authority_id=authority_id)
    row = await _load_row_by_id(
        session,
        model=Task9InitialInventorySnapshot,
        authority_id=authority_id,
    )
    cohorts = list(
        (
            await session.execute(
                select(Task9InitialInventoryCohort)
                .where(Task9InitialInventoryCohort.initial_inventory_snapshot_id == row.id)
                .order_by(Task9InitialInventoryCohort.stable_cohort_key)
            )
        ).scalars()
    )
    stable_key = _stable_key_from_orm_initial_inventory(row)
    bundle = _build_persisted_schema(
        Task9InitialInventorySemanticBundle,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        stable_key=stable_key,
        component="resolution_initial_inventory_bundle",
        season_id=row.season_id,
        destination_factory_id=row.destination_factory_id,
        opening_state_date=row.opening_state_date,
        snapshot_version=row.snapshot_version,
        revision=row.revision,
        initial_opening_mature_inventory_kg=row.initial_opening_mature_inventory_kg,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
        status=row.status,
        status_changed_at=row.status_changed_at,
        source_system=row.source_system,
        source_record_key=row.source_record_key,
        source_version=row.source_version,
        cohorts=[
            Task9InitialInventoryCohortSchema(
                stable_cohort_key=cohort.stable_cohort_key,
                forecast_quantile=cohort.forecast_quantile,
                cohort_date=cohort.cohort_date,
                farm_id=cohort.farm_id,
                subfarm_id=cohort.subfarm_id,
                variety_id=cohort.variety_id,
                remaining_quantity_kg=cohort.remaining_quantity_kg,
            )
            for cohort in cohorts
        ],
    )
    return ResolvedInitialInventoryAuthority(
        mode=mode,
        authority_id=row.id,
        authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        authority_stable_key=stable_key,
        business_version=row.snapshot_version,
        revision=row.revision,
        row_hash=load_result.parent.row_hash,
        status=load_result.parent.status,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=load_result.parent.consumable_from_local_date,
        consumable_to_local_date=load_result.parent.consumable_to_local_date,
        semantic_bundle=bundle,
        child_row_hashes=tuple(load_result.child_hashes),
    )


async def _resolved_mature_loss_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    mode: AuthorityResolutionMode,
) -> ResolvedMatureLossAuthority:
    load_result = await load_mature_loss_by_id(session, authority_id=authority_id)
    row = (
        await session.execute(
            select(Task9MatureInventoryLossAuthority).where(
                Task9MatureInventoryLossAuthority.id == authority_id
            )
        )
    ).scalar_one()
    stable_key = _stable_key_from_orm_mature_loss(row)
    semantic_input = _build_persisted_schema(
        Task9MatureLossSemanticInput,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        stable_key=stable_key,
        component="resolution_mature_loss",
        season_id=row.season_id,
        destination_factory_id=row.destination_factory_id,
        state_date=row.state_date,
        capacity_pool_code=row.capacity_pool_code,
        forecast_quantile=row.forecast_quantile,
        loss_version=row.loss_version,
        revision=row.revision,
        mature_inventory_loss_quantity_kg=row.mature_inventory_loss_quantity_kg,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
        status=row.status,
        status_changed_at=row.status_changed_at,
        source_system=row.source_system,
        source_record_key=row.source_record_key,
        source_version=row.source_version,
    )
    return ResolvedMatureLossAuthority(
        mode=mode,
        authority_id=row.id,
        authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        authority_stable_key=stable_key,
        business_version=row.loss_version,
        revision=row.revision,
        row_hash=load_result.row_hash,
        status=load_result.status,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=load_result.consumable_from_local_date,
        consumable_to_local_date=load_result.consumable_to_local_date,
        semantic_input=semantic_input,
    )


async def _resolved_daily_capacity_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    mode: AuthorityResolutionMode,
) -> ResolvedDailyCapacityAuthority:
    load_result = await load_daily_capacity_by_id(session, authority_id=authority_id)
    row = await _load_row_by_id(
        session,
        model=Task9DailyCapacityAuthority,
        authority_id=authority_id,
    )
    pool = await _resolved_capacity_pool_by_id(
        session,
        authority_id=row.capacity_pool_definition_id,
        mode=mode,
    )
    stable_key = (
        f"daily-capacity:{pool.semantic_bundle.season_id}:{pool.semantic_bundle.destination_factory_id}:"
        f"{pool.semantic_bundle.capacity_pool_code}:{pool.business_version}:"
        f"{pool.revision}:{row.capacity_date.isoformat()}"
    )
    semantic_input = _build_persisted_schema(
        Task9DailyCapacitySemanticInput,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=stable_key,
        component="resolution_daily_capacity",
        season_id=pool.semantic_bundle.season_id,
        destination_factory_id=pool.semantic_bundle.destination_factory_id,
        capacity_pool_code=pool.semantic_bundle.capacity_pool_code,
        capacity_pool_version=pool.business_version,
        capacity_pool_revision=pool.revision,
        capacity_date=row.capacity_date,
        daily_capacity_revision=row.daily_capacity_revision,
        capacity_input_mode=pool.semantic_bundle.capacity_input_mode,
        planned_picker_count=row.planned_picker_count,
        kg_per_person_per_day=row.kg_per_person_per_day,
        direct_nominal_capacity_kg_per_day=row.direct_nominal_capacity_kg_per_day,
        labor_availability_ratio=row.labor_availability_ratio,
        operational_efficiency_ratio=row.operational_efficiency_ratio,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
        status=row.status,
        status_changed_at=row.status_changed_at,
        source_system=row.source_system,
        source_record_key=row.source_record_key,
        source_version=row.source_version,
    )
    return ResolvedDailyCapacityAuthority(
        mode=mode,
        authority_id=row.id,
        authority_family=AuthorityFamily.DAILY_CAPACITY,
        authority_stable_key=stable_key,
        business_version=pool.business_version,
        revision=row.daily_capacity_revision,
        row_hash=load_result.row_hash,
        status=load_result.status,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=load_result.consumable_from_local_date,
        consumable_to_local_date=load_result.consumable_to_local_date,
        semantic_input=semantic_input,
        parent_pool=pool,
    )


async def _resolved_run_package_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    mode: AuthorityResolutionMode,
) -> ResolvedRunParameterPackageAuthority:
    load_result = await load_run_parameter_package_by_id(session, authority_id=authority_id)
    row = (
        await session.execute(
            select(Task9RunParameterPackage).where(Task9RunParameterPackage.id == authority_id)
        )
    ).scalar_one()
    holiday = await _resolved_holiday_by_id(
        session,
        authority_id=row.holiday_calendar_version_id,
        mode=mode,
    )
    weather = await _resolved_weather_by_id(
        session,
        authority_id=row.weather_rule_config_version_id,
        mode=mode,
    )
    pkg_stable_key = _stable_key_from_orm_run_package(row)
    try:
        semantic_input = _build_persisted_schema(
            Task9RunParameterPackageSemanticInput,
            family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            stable_key=pkg_stable_key,
            component="resolution_run_package",
            season_id=row.season_id,
            destination_factory_id=row.destination_factory_id,
            farm_scope_key=row.farm_scope_key,
            farm_timezone=row.farm_timezone,
            destination_factory_timezone=row.destination_factory_timezone,
            harvest_bucket_anchor_local_time=row.harvest_bucket_anchor_local_time,
            harvest_to_arrival_lag_days=row.harvest_to_arrival_lag_days,
            package_version=row.package_version,
            revision=row.revision,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            available_at_local_date=row.available_at_local_date,
            consumable_from_local_date=row.consumable_from_local_date,
            consumable_to_local_date=row.consumable_to_local_date,
            superseded_by_id=row.superseded_by_id,
            status=row.status,
            status_changed_at=row.status_changed_at,
            source_system=row.source_system,
            source_record_key=row.source_record_key,
            source_version=row.source_version,
        )
    except ValueError as exc:
        _raise_dependency_from_canonical_error(
            exc,
            ctx=RunPackageDependencyErrorContext(
                package_stable_key=pkg_stable_key,
                package_season_id=row.season_id,
                package_destination_timezone=row.destination_factory_timezone,
                holiday_stable_key=holiday.authority_stable_key,
                holiday_season_id=holiday.semantic_bundle.season_id,
                holiday_timezone=holiday.semantic_bundle.lifecycle_timezone_name,
                weather_stable_key=weather.authority_stable_key,
                weather_timezone=weather.semantic_input.lifecycle_timezone_name,
            ),
        )
    return ResolvedRunParameterPackageAuthority(
        mode=mode,
        authority_id=row.id,
        authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_stable_key=_stable_key_from_orm_run_package(row),
        business_version=row.package_version,
        revision=row.revision,
        row_hash=load_result.row_hash,
        status=load_result.status,
        available_at_local_date=row.available_at_local_date,
        consumable_from_local_date=load_result.consumable_from_local_date,
        consumable_to_local_date=load_result.consumable_to_local_date,
        semantic_input=semantic_input,
        holiday_calendar=holiday,
        weather_rule=weather,
    )


async def resolve_capacity_pool_definition(
    session: AsyncSession,
    *,
    request: CapacityPoolResolutionRequest,
) -> ResolvedCapacityPoolAuthority:
    _validate_timezone_name(request.timezone_name)
    if request.mode == AuthorityResolutionMode.EXACT_REFERENCE:
        assert request.exact_reference is not None
        resolved = await _resolved_capacity_pool_by_id(
            session, authority_id=request.exact_reference.authority_id, mode=request.mode
        )
        _assert_exact_reference_match(resolved=resolved, exact_reference=request.exact_reference)
        _assert_scope(
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            expected={
                "season_id": request.season_id,
                "destination_factory_id": request.destination_factory_id,
                "capacity_pool_code": request.capacity_pool_code,
            },
            actual={
                "season_id": resolved.semantic_bundle.season_id,
                "destination_factory_id": resolved.semantic_bundle.destination_factory_id,
                "capacity_pool_code": resolved.semantic_bundle.capacity_pool_code,
            },
        )
        if not _effective_interval_contains(
            effective_from=resolved.semantic_bundle.effective_from,
            effective_to=resolved.semantic_bundle.effective_to,
            target_local_date=request.effective_local_date,
        ):
            raise AuthorityEffectiveIntervalMismatchError(
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                target_local_date=request.effective_local_date,
            )
        _assert_consumable(
            snapshot=_build_candidate_snapshot(
                authority_id=resolved.authority_id,
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                business_version=resolved.business_version,
                revision=resolved.revision,
                row_hash=resolved.row_hash,
                status=resolved.status,
                available_at_local_date=resolved.available_at_local_date,
                consumable_from_local_date=resolved.consumable_from_local_date,
                consumable_to_local_date=resolved.consumable_to_local_date,
            ),
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
        return resolved

    filters = [
        Task9CapacityPoolDefinition.season_id == request.season_id,
        Task9CapacityPoolDefinition.destination_factory_id == request.destination_factory_id,
        Task9CapacityPoolDefinition.capacity_pool_code == request.capacity_pool_code,
        Task9CapacityPoolDefinition.effective_from <= request.effective_local_date,
        or_(
            Task9CapacityPoolDefinition.effective_to.is_(None),
            request.effective_local_date <= Task9CapacityPoolDefinition.effective_to,
        ),
    ]
    filters.extend(
        _predicates_for_mode(
            Task9CapacityPoolDefinition,
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
    )
    rows = list(
        (
            await session.execute(
                select(Task9CapacityPoolDefinition)
                .where(*filters)
                .order_by(Task9CapacityPoolDefinition.row_hash.asc())
                .limit(2)
            )
        ).scalars()
    )
    if not rows:
        business_key = (
            f"{request.season_id}:{request.destination_factory_id}:{request.capacity_pool_code}"
        )
        # Level 1: No scope row at all
        any_scope_rows = list(
            (
                await session.execute(
                    select(Task9CapacityPoolDefinition)
                    .where(
                        Task9CapacityPoolDefinition.season_id == request.season_id,
                        Task9CapacityPoolDefinition.destination_factory_id
                        == request.destination_factory_id,
                        Task9CapacityPoolDefinition.capacity_pool_code
                        == request.capacity_pool_code,
                    )
                    .limit(1)
                )
            ).scalars()
        )
        if not any_scope_rows:
            raise HistoricalAuthorityNotFoundError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                as_of_local_date=request.as_of_local_date,
                business_key=business_key,
            )
        # Level 2: Scope row exists but no effective interval covers target
        effective_rows = list(
            (
                await session.execute(
                    select(Task9CapacityPoolDefinition)
                    .where(
                        Task9CapacityPoolDefinition.season_id == request.season_id,
                        Task9CapacityPoolDefinition.destination_factory_id
                        == request.destination_factory_id,
                        Task9CapacityPoolDefinition.capacity_pool_code
                        == request.capacity_pool_code,
                        Task9CapacityPoolDefinition.effective_from <= request.effective_local_date,
                        or_(
                            Task9CapacityPoolDefinition.effective_to.is_(None),
                            request.effective_local_date
                            <= Task9CapacityPoolDefinition.effective_to,
                        ),
                    )
                    .limit(1)
                )
            ).scalars()
        )
        if not effective_rows:
            raise AuthorityEffectiveIntervalMismatchError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=request.capacity_pool_code,
                target_local_date=request.effective_local_date,
            )
        # Level 3: Scope+effective row exists but all future available_at
        visible_rows = list(
            (
                await session.execute(
                    select(Task9CapacityPoolDefinition)
                    .where(
                        Task9CapacityPoolDefinition.season_id == request.season_id,
                        Task9CapacityPoolDefinition.destination_factory_id
                        == request.destination_factory_id,
                        Task9CapacityPoolDefinition.capacity_pool_code
                        == request.capacity_pool_code,
                        Task9CapacityPoolDefinition.effective_from <= request.effective_local_date,
                        or_(
                            Task9CapacityPoolDefinition.effective_to.is_(None),
                            request.effective_local_date
                            <= Task9CapacityPoolDefinition.effective_to,
                        ),
                        Task9CapacityPoolDefinition.available_at_local_date
                        <= request.as_of_local_date,
                    )
                    .limit(1)
                )
            ).scalars()
        )
        if not visible_rows:
            raise AuthorityNotConsumableAtCutoffError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=request.capacity_pool_code,
                as_of_local_date=request.as_of_local_date,
                details={"reason": "authority_not_available_at_cutoff"},
            )
        # Level 4: Scope+effective+visible row exists but lifecycle not consumable
        # Use _predicates_for_mode() to get mode-specific lifecycle predicates
        # that are consistent with the main query.
        consumable_rows = list(
            (
                await session.execute(
                    select(Task9CapacityPoolDefinition)
                    .where(
                        Task9CapacityPoolDefinition.season_id == request.season_id,
                        Task9CapacityPoolDefinition.destination_factory_id
                        == request.destination_factory_id,
                        Task9CapacityPoolDefinition.capacity_pool_code
                        == request.capacity_pool_code,
                        Task9CapacityPoolDefinition.effective_from <= request.effective_local_date,
                        or_(
                            Task9CapacityPoolDefinition.effective_to.is_(None),
                            request.effective_local_date
                            <= Task9CapacityPoolDefinition.effective_to,
                        ),
                        Task9CapacityPoolDefinition.available_at_local_date
                        <= request.as_of_local_date,
                        *_predicates_for_mode(
                            Task9CapacityPoolDefinition,
                            mode=request.mode,
                            as_of_local_date=request.as_of_local_date,
                        ),
                    )
                    .limit(1)
                )
            ).scalars()
        )
        if not consumable_rows:
            raise AuthorityNotConsumableAtCutoffError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=request.capacity_pool_code,
                as_of_local_date=request.as_of_local_date,
                details={"reason": "authority_lifecycle_not_consumable_at_cutoff"},
            )
        # Level 5: All conditions met — fall through to proceed
    snapshot = _choose_candidate_snapshot(
        [
            _build_candidate_snapshot(
                authority_id=row.id,
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=_stable_key_from_orm_capacity_pool(row),
                business_version=row.capacity_pool_version,
                revision=row.revision,
                row_hash=row.row_hash,
                status=row.status,
                available_at_local_date=row.available_at_local_date,
                consumable_from_local_date=row.consumable_from_local_date,
                consumable_to_local_date=row.consumable_to_local_date,
            )
            for row in rows
        ],
        authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        as_of_local_date=request.as_of_local_date,
        reason="same_priority_conflict",
    )
    return await _resolved_capacity_pool_by_id(
        session,
        authority_id=snapshot.authority_id,
        mode=request.mode,
    )


async def resolve_holiday_calendar(
    session: AsyncSession,
    *,
    request: HolidayCalendarResolutionRequest,
) -> ResolvedHolidayCalendarAuthority:
    _validate_timezone_name(request.timezone_name)
    _validate_timezone_name(request.lifecycle_timezone_name)
    if request.mode == AuthorityResolutionMode.EXACT_REFERENCE:
        assert request.exact_reference is not None
        resolved = await _resolved_holiday_by_id(
            session, authority_id=request.exact_reference.authority_id, mode=request.mode
        )
        _assert_exact_reference_match(resolved=resolved, exact_reference=request.exact_reference)
        _assert_scope(
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            expected={
                "season_id": request.season_id,
                "calendar_code": request.calendar_code,
                "lifecycle_timezone_name": request.lifecycle_timezone_name,
            },
            actual={
                "season_id": resolved.semantic_bundle.season_id,
                "calendar_code": resolved.semantic_bundle.calendar_code,
                "lifecycle_timezone_name": resolved.semantic_bundle.lifecycle_timezone_name,
            },
        )
        _assert_consumable(
            snapshot=_build_candidate_snapshot(
                authority_id=resolved.authority_id,
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                business_version=resolved.business_version,
                revision=resolved.revision,
                row_hash=resolved.row_hash,
                status=resolved.status,
                available_at_local_date=resolved.available_at_local_date,
                consumable_from_local_date=resolved.consumable_from_local_date,
                consumable_to_local_date=resolved.consumable_to_local_date,
            ),
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
        return resolved
    filters = [
        Task9HolidayCalendarVersion.season_id == request.season_id,
        Task9HolidayCalendarVersion.calendar_code == request.calendar_code,
        Task9HolidayCalendarVersion.lifecycle_timezone_name == request.lifecycle_timezone_name,
    ]
    filters.extend(
        _predicates_for_mode(
            Task9HolidayCalendarVersion,
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
    )
    rows = list(
        (
            await session.execute(
                select(Task9HolidayCalendarVersion)
                .where(*filters)
                .order_by(
                    Task9HolidayCalendarVersion.revision.desc(),
                    Task9HolidayCalendarVersion.available_at_local_date.desc(),
                    Task9HolidayCalendarVersion.row_hash.asc(),
                )
                .limit(2)
            )
        ).scalars()
    )
    if not rows:
        business_key = (
            f"{request.season_id}:{request.calendar_code}:{request.lifecycle_timezone_name}"
        )
        raise HistoricalAuthorityNotFoundError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            as_of_local_date=request.as_of_local_date,
            business_key=business_key,
        )
    snapshot = _choose_candidate_snapshot(
        [
            _build_candidate_snapshot(
                authority_id=row.id,
                authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                authority_stable_key=_stable_key_from_orm_holiday(row),
                business_version=row.calendar_version,
                revision=row.revision,
                row_hash=row.row_hash,
                status=row.status,
                available_at_local_date=row.available_at_local_date,
                consumable_from_local_date=row.consumable_from_local_date,
                consumable_to_local_date=row.consumable_to_local_date,
            )
            for row in rows
        ],
        authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        as_of_local_date=request.as_of_local_date,
        reason="same_priority_conflict",
    )
    return await _resolved_holiday_by_id(
        session,
        authority_id=snapshot.authority_id,
        mode=request.mode,
    )


async def resolve_weather_rule(
    session: AsyncSession,
    *,
    request: WeatherRuleResolutionRequest,
) -> ResolvedWeatherRuleAuthority:
    _validate_timezone_name(request.timezone_name)
    _validate_timezone_name(request.lifecycle_timezone_name)
    if request.mode == AuthorityResolutionMode.EXACT_REFERENCE:
        assert request.exact_reference is not None
        resolved = await _resolved_weather_by_id(
            session, authority_id=request.exact_reference.authority_id, mode=request.mode
        )
        _assert_exact_reference_match(resolved=resolved, exact_reference=request.exact_reference)
        _assert_scope(
            expected={
                "rule_code": request.rule_code,
                "lifecycle_timezone_name": request.lifecycle_timezone_name,
            },
            actual={
                "rule_code": resolved.semantic_input.rule_code,
                "lifecycle_timezone_name": resolved.semantic_input.lifecycle_timezone_name,
            },
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            authority_stable_key=resolved.authority_stable_key,
        )
        if not _effective_interval_contains(
            effective_from=resolved.semantic_input.effective_from,
            effective_to=resolved.semantic_input.effective_to,
            target_local_date=request.effective_local_date,
        ):
            raise AuthorityEffectiveIntervalMismatchError(
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                target_local_date=request.effective_local_date,
            )
        _assert_consumable(
            snapshot=_build_candidate_snapshot(
                authority_id=resolved.authority_id,
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                business_version=resolved.business_version,
                revision=resolved.revision,
                row_hash=resolved.row_hash,
                status=resolved.status,
                available_at_local_date=resolved.available_at_local_date,
                consumable_from_local_date=resolved.consumable_from_local_date,
                consumable_to_local_date=resolved.consumable_to_local_date,
            ),
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
        return resolved
    filters = [
        Task9WeatherRuleConfigVersion.rule_code == request.rule_code,
        Task9WeatherRuleConfigVersion.lifecycle_timezone_name == request.lifecycle_timezone_name,
        Task9WeatherRuleConfigVersion.effective_from <= request.effective_local_date,
        or_(
            Task9WeatherRuleConfigVersion.effective_to.is_(None),
            request.effective_local_date <= Task9WeatherRuleConfigVersion.effective_to,
        ),
    ]
    filters.extend(
        _predicates_for_mode(
            Task9WeatherRuleConfigVersion,
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
    )
    rows = list(
        (
            await session.execute(
                select(Task9WeatherRuleConfigVersion)
                .where(*filters)
                .order_by(
                    Task9WeatherRuleConfigVersion.revision.desc(),
                    Task9WeatherRuleConfigVersion.available_at_local_date.desc(),
                    Task9WeatherRuleConfigVersion.row_hash.asc(),
                )
                .limit(2)
            )
        ).scalars()
    )
    if not rows:
        raise HistoricalAuthorityNotFoundError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            as_of_local_date=request.as_of_local_date,
            business_key=f"{request.rule_code}:{request.lifecycle_timezone_name}",
        )
    snapshot = _choose_candidate_snapshot(
        [
            _build_candidate_snapshot(
                authority_id=row.id,
                authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                authority_stable_key=_stable_key_from_orm_weather(row),
                business_version=row.rule_version,
                revision=row.revision,
                row_hash=row.row_hash,
                status=row.status,
                available_at_local_date=row.available_at_local_date,
                consumable_from_local_date=row.consumable_from_local_date,
                consumable_to_local_date=row.consumable_to_local_date,
            )
            for row in rows
        ],
        authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        as_of_local_date=request.as_of_local_date,
        reason="same_priority_conflict",
    )
    return await _resolved_weather_by_id(
        session,
        authority_id=snapshot.authority_id,
        mode=request.mode,
    )


async def resolve_initial_inventory(
    session: AsyncSession,
    *,
    request: InitialInventoryResolutionRequest,
) -> ResolvedInitialInventoryAuthority:
    _validate_timezone_name(request.timezone_name)
    if request.mode == AuthorityResolutionMode.EXACT_REFERENCE:
        assert request.exact_reference is not None
        resolved = await _resolved_initial_inventory_by_id(
            session, authority_id=request.exact_reference.authority_id, mode=request.mode
        )
        _assert_exact_reference_match(resolved=resolved, exact_reference=request.exact_reference)
        _assert_scope(
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            expected={
                "season_id": request.season_id,
                "destination_factory_id": request.destination_factory_id,
                "opening_state_date": request.opening_state_date,
            },
            actual={
                "season_id": resolved.semantic_bundle.season_id,
                "destination_factory_id": resolved.semantic_bundle.destination_factory_id,
                "opening_state_date": resolved.semantic_bundle.opening_state_date,
            },
        )
        _assert_consumable(
            snapshot=_build_candidate_snapshot(
                authority_id=resolved.authority_id,
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                business_version=resolved.business_version,
                revision=resolved.revision,
                row_hash=resolved.row_hash,
                status=resolved.status,
                available_at_local_date=resolved.available_at_local_date,
                consumable_from_local_date=resolved.consumable_from_local_date,
                consumable_to_local_date=resolved.consumable_to_local_date,
            ),
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
        return resolved
    filters = [
        Task9InitialInventorySnapshot.season_id == request.season_id,
        Task9InitialInventorySnapshot.destination_factory_id == request.destination_factory_id,
        Task9InitialInventorySnapshot.opening_state_date == request.opening_state_date,
    ]
    filters.extend(
        _predicates_for_mode(
            Task9InitialInventorySnapshot,
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
    )
    rows = list(
        (
            await session.execute(
                select(Task9InitialInventorySnapshot)
                .where(*filters)
                .order_by(
                    Task9InitialInventorySnapshot.revision.desc(),
                    Task9InitialInventorySnapshot.available_at_local_date.desc(),
                    Task9InitialInventorySnapshot.row_hash.asc(),
                )
                .limit(2)
            )
        ).scalars()
    )
    if not rows:
        business_key = (
            f"{request.season_id}:{request.destination_factory_id}:"
            f"{request.opening_state_date.isoformat()}"
        )
        raise HistoricalAuthorityNotFoundError(
            authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
            as_of_local_date=request.as_of_local_date,
            business_key=business_key,
        )
    snapshot = _choose_candidate_snapshot(
        [
            _build_candidate_snapshot(
                authority_id=row.id,
                authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
                authority_stable_key=_stable_key_from_orm_initial_inventory(row),
                business_version=row.snapshot_version,
                revision=row.revision,
                row_hash=row.row_hash,
                status=row.status,
                available_at_local_date=row.available_at_local_date,
                consumable_from_local_date=row.consumable_from_local_date,
                consumable_to_local_date=row.consumable_to_local_date,
            )
            for row in rows
        ],
        authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        as_of_local_date=request.as_of_local_date,
        reason="same_priority_conflict",
    )
    return await _resolved_initial_inventory_by_id(
        session,
        authority_id=snapshot.authority_id,
        mode=request.mode,
    )


async def resolve_mature_inventory_loss(
    session: AsyncSession,
    *,
    request: MatureLossResolutionRequest,
) -> ResolvedMatureLossAuthority:
    _validate_timezone_name(request.timezone_name)
    if request.mode == AuthorityResolutionMode.EXACT_REFERENCE:
        assert request.exact_reference is not None
        resolved = await _resolved_mature_loss_by_id(
            session, authority_id=request.exact_reference.authority_id, mode=request.mode
        )
        _assert_exact_reference_match(resolved=resolved, exact_reference=request.exact_reference)
        _assert_scope(
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            expected={
                "season_id": request.season_id,
                "destination_factory_id": request.destination_factory_id,
                "capacity_pool_code": request.capacity_pool_code,
                "state_date": request.state_date,
                "forecast_quantile": request.forecast_quantile,
            },
            actual={
                "season_id": resolved.semantic_input.season_id,
                "destination_factory_id": resolved.semantic_input.destination_factory_id,
                "capacity_pool_code": resolved.semantic_input.capacity_pool_code,
                "state_date": resolved.semantic_input.state_date,
                "forecast_quantile": resolved.semantic_input.forecast_quantile,
            },
        )
        _assert_consumable(
            snapshot=_build_candidate_snapshot(
                authority_id=resolved.authority_id,
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                business_version=resolved.business_version,
                revision=resolved.revision,
                row_hash=resolved.row_hash,
                status=resolved.status,
                available_at_local_date=resolved.available_at_local_date,
                consumable_from_local_date=resolved.consumable_from_local_date,
                consumable_to_local_date=resolved.consumable_to_local_date,
            ),
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
        return resolved
    filters = [
        Task9MatureInventoryLossAuthority.season_id == request.season_id,
        Task9MatureInventoryLossAuthority.destination_factory_id == request.destination_factory_id,
        Task9MatureInventoryLossAuthority.capacity_pool_code == request.capacity_pool_code,
        Task9MatureInventoryLossAuthority.state_date == request.state_date,
        Task9MatureInventoryLossAuthority.forecast_quantile == request.forecast_quantile,
    ]
    filters.extend(
        _current_predicates(
            Task9MatureInventoryLossAuthority, as_of_local_date=request.as_of_local_date
        )
        if request.mode == AuthorityResolutionMode.CURRENT_OPERATIONAL
        else _historical_predicates(
            Task9MatureInventoryLossAuthority, as_of_local_date=request.as_of_local_date
        )
    )
    rows = list(
        (
            await session.execute(
                select(Task9MatureInventoryLossAuthority)
                .where(*filters)
                .order_by(
                    Task9MatureInventoryLossAuthority.revision.desc(),
                    Task9MatureInventoryLossAuthority.available_at_local_date.desc(),
                    Task9MatureInventoryLossAuthority.row_hash.asc(),
                )
                .limit(2)
            )
        ).scalars()
    )
    if not rows:
        business_key = (
            f"{request.season_id}:{request.destination_factory_id}:"
            f"{request.capacity_pool_code}:{request.state_date.isoformat()}:"
            f"{request.forecast_quantile}"
        )
        raise HistoricalAuthorityNotFoundError(
            authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            as_of_local_date=request.as_of_local_date,
            business_key=business_key,
        )
    snapshot = _choose_candidate_snapshot(
        [
            _build_candidate_snapshot(
                authority_id=row.id,
                authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                authority_stable_key=_stable_key_from_orm_mature_loss(row),
                business_version=row.loss_version,
                revision=row.revision,
                row_hash=row.row_hash,
                status=row.status,
                available_at_local_date=row.available_at_local_date,
                consumable_from_local_date=row.consumable_from_local_date,
                consumable_to_local_date=row.consumable_to_local_date,
            )
            for row in rows
        ],
        authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        as_of_local_date=request.as_of_local_date,
        reason="same_priority_conflict",
    )
    return await _resolved_mature_loss_by_id(
        session,
        authority_id=snapshot.authority_id,
        mode=request.mode,
    )


@dataclass(frozen=True)
class RunPackageDependencyErrorContext:
    """All fields required for deterministic dependency error attribution."""

    package_stable_key: str
    package_season_id: int
    package_destination_timezone: str
    holiday_stable_key: str
    holiday_season_id: int
    holiday_timezone: str
    weather_stable_key: str
    weather_timezone: str


async def _load_dependency_context_for_error(
    session: AsyncSession,
    *,
    authority_id: int,
) -> RunPackageDependencyErrorContext:
    """Load package + dependency info for typed error context."""
    row = (
        await session.execute(
            select(Task9RunParameterPackage).where(Task9RunParameterPackage.id == authority_id)
        )
    ).scalar_one()
    pkg_stable_key = _stable_key_from_orm_run_package(row)
    holiday_row = (
        await session.execute(
            select(Task9HolidayCalendarVersion).where(
                Task9HolidayCalendarVersion.id == row.holiday_calendar_version_id
            )
        )
    ).scalar_one()
    weather_row = (
        await session.execute(
            select(Task9WeatherRuleConfigVersion).where(
                Task9WeatherRuleConfigVersion.id == row.weather_rule_config_version_id
            )
        )
    ).scalar_one()
    return RunPackageDependencyErrorContext(
        package_stable_key=pkg_stable_key,
        package_season_id=row.season_id,
        package_destination_timezone=row.destination_factory_timezone,
        holiday_stable_key=_stable_key_from_orm_holiday(holiday_row),
        holiday_season_id=holiday_row.season_id,
        holiday_timezone=holiday_row.lifecycle_timezone_name,
        weather_stable_key=_stable_key_from_orm_weather(weather_row),
        weather_timezone=weather_row.lifecycle_timezone_name,
    )


async def resolve_run_parameter_package(
    session: AsyncSession,
    *,
    request: RunParameterPackageResolutionRequest,
) -> ResolvedRunParameterPackageAuthority:
    _validate_timezone_name(request.timezone_name)
    if request.mode == AuthorityResolutionMode.EXACT_REFERENCE:
        assert request.exact_reference is not None
        try:
            resolved = await _resolved_run_package_by_id(
                session, authority_id=request.exact_reference.authority_id, mode=request.mode
            )
        except ValueError as exc:
            ctx = await _load_dependency_context_for_error(
                session, authority_id=request.exact_reference.authority_id
            )
            _raise_dependency_from_canonical_error(exc, ctx=ctx)
        _assert_exact_reference_match(resolved=resolved, exact_reference=request.exact_reference)
    else:
        filters = [
            Task9RunParameterPackage.season_id == request.season_id,
            Task9RunParameterPackage.destination_factory_id == request.destination_factory_id,
            Task9RunParameterPackage.farm_scope_key == request.farm_scope_key,
            Task9RunParameterPackage.effective_from <= request.effective_local_date,
            or_(
                Task9RunParameterPackage.effective_to.is_(None),
                request.effective_local_date <= Task9RunParameterPackage.effective_to,
            ),
        ]
        filters.extend(
            _predicates_for_mode(
                Task9RunParameterPackage,
                mode=request.mode,
                as_of_local_date=request.as_of_local_date,
            )
        )
        rows = list(
            (
                await session.execute(
                    select(Task9RunParameterPackage)
                    .where(*filters)
                    .order_by(Task9RunParameterPackage.row_hash.asc())
                    .limit(2)
                )
            ).scalars()
        )
        if not rows:
            business_key = (
                f"{request.season_id}:{request.destination_factory_id}:{request.farm_scope_key}"
            )
            raise HistoricalAuthorityNotFoundError(
                authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                as_of_local_date=request.as_of_local_date,
                business_key=business_key,
            )
        snapshot = _choose_candidate_snapshot(
            [
                _build_candidate_snapshot(
                    authority_id=row.id,
                    authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                    authority_stable_key=_stable_key_from_orm_run_package(row),
                    business_version=row.package_version,
                    revision=row.revision,
                    row_hash=row.row_hash,
                    status=row.status,
                    available_at_local_date=row.available_at_local_date,
                    consumable_from_local_date=row.consumable_from_local_date,
                    consumable_to_local_date=row.consumable_to_local_date,
                )
                for row in rows
            ],
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            as_of_local_date=request.as_of_local_date,
            reason="same_priority_conflict",
        )
        try:
            resolved = await _resolved_run_package_by_id(
                session,
                authority_id=snapshot.authority_id,
                mode=request.mode,
            )
        except ValueError as exc:
            ctx = await _load_dependency_context_for_error(
                session, authority_id=snapshot.authority_id
            )
            _raise_dependency_from_canonical_error(exc, ctx=ctx)

    _assert_scope(
        authority_family=resolved.authority_family,
        authority_stable_key=resolved.authority_stable_key,
        expected={
            "season_id": request.season_id,
            "destination_factory_id": request.destination_factory_id,
            "farm_scope_key": request.farm_scope_key,
        },
        actual={
            "season_id": resolved.semantic_input.season_id,
            "destination_factory_id": resolved.semantic_input.destination_factory_id,
            "farm_scope_key": resolved.semantic_input.farm_scope_key,
        },
    )
    if not _effective_interval_contains(
        effective_from=resolved.semantic_input.effective_from,
        effective_to=resolved.semantic_input.effective_to,
        target_local_date=request.effective_local_date,
    ):
        raise AuthorityEffectiveIntervalMismatchError(
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            target_local_date=request.effective_local_date,
        )
    _assert_consumable(
        snapshot=_build_candidate_snapshot(
            authority_id=resolved.authority_id,
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            business_version=resolved.business_version,
            revision=resolved.revision,
            row_hash=resolved.row_hash,
            status=resolved.status,
            available_at_local_date=resolved.available_at_local_date,
            consumable_from_local_date=resolved.consumable_from_local_date,
            consumable_to_local_date=resolved.consumable_to_local_date,
        ),
        mode=request.mode,
        as_of_local_date=request.as_of_local_date,
    )
    holiday_timezone = resolved.holiday_calendar.semantic_bundle.lifecycle_timezone_name
    if resolved.semantic_input.destination_factory_timezone != holiday_timezone:
        raise AuthorityDependencyMismatchError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=resolved.authority_stable_key,
            details={
                "reason": "dependency_timezone_mismatch",
                "dependency_family": AuthorityFamily.HOLIDAY_CALENDAR_VERSION.value,
                "dependency_authority_stable_key": resolved.holiday_calendar.authority_stable_key,
                "expected_timezone": resolved.semantic_input.destination_factory_timezone,
                "actual_timezone": holiday_timezone,
            },
        )
    weather_timezone = resolved.weather_rule.semantic_input.lifecycle_timezone_name
    if resolved.semantic_input.destination_factory_timezone != weather_timezone:
        raise AuthorityDependencyMismatchError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=resolved.authority_stable_key,
            details={
                "reason": "dependency_timezone_mismatch",
                "dependency_family": AuthorityFamily.WEATHER_RULE_CONFIG_VERSION.value,
                "dependency_authority_stable_key": resolved.weather_rule.authority_stable_key,
                "expected_timezone": resolved.semantic_input.destination_factory_timezone,
                "actual_timezone": weather_timezone,
            },
        )
    if resolved.holiday_calendar.semantic_bundle.season_id != resolved.semantic_input.season_id:
        raise AuthorityDependencyMismatchError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=resolved.authority_stable_key,
            details={
                "reason": "holiday_season_mismatch",
                "dependency_family": "holiday_calendar_version",
                "expected_season_id": resolved.semantic_input.season_id,
                "actual_season_id": resolved.holiday_calendar.semantic_bundle.season_id,
                "dependency_authority_stable_key": resolved.holiday_calendar.authority_stable_key,
            },
        )
    for dep in (resolved.holiday_calendar, resolved.weather_rule):
        snapshot = _build_candidate_snapshot(
            authority_id=dep.authority_id,
            authority_family=dep.authority_family,
            authority_stable_key=dep.authority_stable_key,
            business_version=dep.business_version,
            revision=dep.revision,
            row_hash=dep.row_hash,
            status=dep.status,
            available_at_local_date=dep.available_at_local_date,
            consumable_from_local_date=dep.consumable_from_local_date,
            consumable_to_local_date=dep.consumable_to_local_date,
        )
        ok = _snapshot_visible_for_mode(
            snapshot,
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
        if not ok:
            raise AuthorityDependencyMismatchError(
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                details={
                    "reason": "dependency_not_consumable_at_cutoff",
                    "dependency_family": dep.authority_family.value,
                    "as_of_local_date": request.as_of_local_date.isoformat(),
                },
            )
    return resolved


async def resolve_daily_capacity(
    session: AsyncSession,
    *,
    request: DailyCapacityResolutionRequest,
) -> ResolvedDailyCapacityAuthority:
    _validate_timezone_name(request.timezone_name)
    if request.mode == AuthorityResolutionMode.EXACT_REFERENCE:
        assert request.exact_reference is not None
        resolved = await _resolved_daily_capacity_by_id(
            session,
            authority_id=request.exact_reference.authority_id,
            mode=request.mode,
        )
        _assert_exact_reference_match(resolved=resolved, exact_reference=request.exact_reference)
    else:
        parent_rows = list(
            (
                await session.execute(
                    select(Task9CapacityPoolDefinition)
                    .where(
                        Task9CapacityPoolDefinition.season_id == request.season_id,
                        Task9CapacityPoolDefinition.destination_factory_id
                        == request.destination_factory_id,
                        Task9CapacityPoolDefinition.capacity_pool_code
                        == request.capacity_pool_code,
                        Task9CapacityPoolDefinition.effective_from <= request.capacity_date,
                        or_(
                            Task9CapacityPoolDefinition.effective_to.is_(None),
                            request.capacity_date <= Task9CapacityPoolDefinition.effective_to,
                        ),
                        *(
                            _predicates_for_mode(
                                Task9CapacityPoolDefinition,
                                mode=request.mode,
                                as_of_local_date=request.as_of_local_date,
                            )
                        ),
                    )
                    .order_by(Task9CapacityPoolDefinition.row_hash.asc())
                    .limit(2)
                )
            ).scalars()
        )
        if not parent_rows:
            any_parent = list(
                (
                    await session.execute(
                        select(Task9CapacityPoolDefinition)
                        .where(
                            Task9CapacityPoolDefinition.season_id == request.season_id,
                            Task9CapacityPoolDefinition.destination_factory_id
                            == request.destination_factory_id,
                            Task9CapacityPoolDefinition.capacity_pool_code
                            == request.capacity_pool_code,
                        )
                        .limit(1)
                    )
                ).scalars()
            )
            if any_parent:
                parent = any_parent[0]
                if not _effective_interval_contains(
                    effective_from=parent.effective_from,
                    effective_to=parent.effective_to,
                    target_local_date=request.capacity_date,
                ):
                    raise AuthorityEffectiveIntervalMismatchError(
                        authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                        authority_stable_key=_stable_key_from_orm_capacity_pool(parent),
                        target_local_date=request.capacity_date,
                        details={"reason": "parent_effective_interval_mismatch"},
                    )
                raise AuthorityNotConsumableAtCutoffError(
                    authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                    authority_stable_key=_stable_key_from_orm_capacity_pool(parent),
                    as_of_local_date=request.as_of_local_date,
                    details={"reason": "parent_not_consumable_at_cutoff"},
                )
            business_key = (
                f"{request.season_id}:{request.destination_factory_id}:"
                f"{request.capacity_pool_code}:{request.capacity_date.isoformat()}"
            )
            raise HistoricalAuthorityNotFoundError(
                authority_family=AuthorityFamily.DAILY_CAPACITY,
                as_of_local_date=request.as_of_local_date,
                business_key=business_key,
            )
        parent_snapshot = _choose_candidate_snapshot(
            [
                _build_candidate_snapshot(
                    authority_id=row.id,
                    authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                    authority_stable_key=_stable_key_from_orm_capacity_pool(row),
                    business_version=row.capacity_pool_version,
                    revision=row.revision,
                    row_hash=row.row_hash,
                    status=row.status,
                    available_at_local_date=row.available_at_local_date,
                    consumable_from_local_date=row.consumable_from_local_date,
                    consumable_to_local_date=row.consumable_to_local_date,
                )
                for row in parent_rows
            ],
            authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            as_of_local_date=request.as_of_local_date,
            reason="same_priority_conflict",
        )
        daily_rows = list(
            (
                await session.execute(
                    select(Task9DailyCapacityAuthority)
                    .where(
                        Task9DailyCapacityAuthority.capacity_pool_definition_id
                        == parent_snapshot.authority_id,
                        Task9DailyCapacityAuthority.capacity_date == request.capacity_date,
                        *(
                            _predicates_for_mode(
                                Task9DailyCapacityAuthority,
                                mode=request.mode,
                                as_of_local_date=request.as_of_local_date,
                            )
                        ),
                    )
                    .order_by(
                        Task9DailyCapacityAuthority.daily_capacity_revision.desc(),
                        Task9DailyCapacityAuthority.available_at_local_date.desc(),
                        Task9DailyCapacityAuthority.row_hash.asc(),
                    )
                    .limit(2)
                )
            ).scalars()
        )
        if not daily_rows:
            raw_child = list(
                (
                    await session.execute(
                        select(Task9DailyCapacityAuthority)
                        .where(
                            Task9DailyCapacityAuthority.capacity_pool_definition_id
                            == parent_snapshot.authority_id,
                            Task9DailyCapacityAuthority.capacity_date == request.capacity_date,
                        )
                        .limit(1)
                    )
                ).scalars()
            )
            if raw_child:
                raise AuthorityNotConsumableAtCutoffError(
                    authority_family=AuthorityFamily.DAILY_CAPACITY,
                    authority_stable_key=parent_snapshot.authority_stable_key,
                    as_of_local_date=request.as_of_local_date,
                    details={"reason": "daily_capacity_not_consumable_at_cutoff"},
                )
            business_key = (
                f"{request.season_id}:{request.destination_factory_id}:"
                f"{request.capacity_pool_code}:{request.capacity_date.isoformat()}"
            )
            raise HistoricalAuthorityNotFoundError(
                authority_family=AuthorityFamily.DAILY_CAPACITY,
                as_of_local_date=request.as_of_local_date,
                business_key=business_key,
            )
        daily_snapshot = _choose_candidate_snapshot(
            [
                _build_candidate_snapshot(
                    authority_id=row.id,
                    authority_family=AuthorityFamily.DAILY_CAPACITY,
                    authority_stable_key=(
                        f"daily-capacity:{request.season_id}:{request.destination_factory_id}:"
                        f"{request.capacity_pool_code}:{parent_snapshot.business_version}:"
                        f"{parent_snapshot.revision}:{request.capacity_date.isoformat()}"
                    ),
                    business_version=parent_snapshot.business_version,
                    revision=row.daily_capacity_revision,
                    row_hash=row.row_hash,
                    status=row.status,
                    available_at_local_date=row.available_at_local_date,
                    consumable_from_local_date=row.consumable_from_local_date,
                    consumable_to_local_date=row.consumable_to_local_date,
                )
                for row in daily_rows
            ],
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            as_of_local_date=request.as_of_local_date,
            reason="same_priority_conflict",
        )
        resolved = await _resolved_daily_capacity_by_id(
            session,
            authority_id=daily_snapshot.authority_id,
            mode=request.mode,
        )

    _assert_scope(
        authority_family=resolved.authority_family,
        authority_stable_key=resolved.authority_stable_key,
        expected={
            "season_id": request.season_id,
            "destination_factory_id": request.destination_factory_id,
            "capacity_pool_code": request.capacity_pool_code,
            "capacity_date": request.capacity_date,
        },
        actual={
            "season_id": resolved.semantic_input.season_id,
            "destination_factory_id": resolved.semantic_input.destination_factory_id,
            "capacity_pool_code": resolved.semantic_input.capacity_pool_code,
            "capacity_date": resolved.semantic_input.capacity_date,
        },
    )
    if not _effective_interval_contains(
        effective_from=resolved.parent_pool.semantic_bundle.effective_from,
        effective_to=resolved.parent_pool.semantic_bundle.effective_to,
        target_local_date=request.capacity_date,
    ):
        raise AuthorityEffectiveIntervalMismatchError(
            authority_family=resolved.parent_pool.authority_family,
            authority_stable_key=resolved.parent_pool.authority_stable_key,
            target_local_date=request.capacity_date,
            details={"reason": "parent_effective_interval_mismatch"},
        )
    for snapshot, reason in (
        (
            _build_candidate_snapshot(
                authority_id=resolved.authority_id,
                authority_family=resolved.authority_family,
                authority_stable_key=resolved.authority_stable_key,
                business_version=resolved.business_version,
                revision=resolved.revision,
                row_hash=resolved.row_hash,
                status=resolved.status,
                available_at_local_date=resolved.available_at_local_date,
                consumable_from_local_date=resolved.consumable_from_local_date,
                consumable_to_local_date=resolved.consumable_to_local_date,
            ),
            "daily_capacity_not_consumable_at_cutoff",
        ),
        (
            _build_candidate_snapshot(
                authority_id=resolved.parent_pool.authority_id,
                authority_family=resolved.parent_pool.authority_family,
                authority_stable_key=resolved.parent_pool.authority_stable_key,
                business_version=resolved.parent_pool.business_version,
                revision=resolved.parent_pool.revision,
                row_hash=resolved.parent_pool.row_hash,
                status=resolved.parent_pool.status,
                available_at_local_date=resolved.parent_pool.available_at_local_date,
                consumable_from_local_date=resolved.parent_pool.consumable_from_local_date,
                consumable_to_local_date=resolved.parent_pool.consumable_to_local_date,
            ),
            "parent_not_consumable_at_cutoff",
        ),
    ):
        ok = _snapshot_visible_for_mode(
            snapshot,
            mode=request.mode,
            as_of_local_date=request.as_of_local_date,
        )
        if not ok:
            raise AuthorityNotConsumableAtCutoffError(
                authority_family=snapshot.authority_family,
                authority_stable_key=snapshot.authority_stable_key,
                as_of_local_date=request.as_of_local_date,
                details={"reason": reason},
            )
    if (
        resolved.parent_pool.semantic_bundle.capacity_pool_code
        != resolved.semantic_input.capacity_pool_code
    ):
        raise AuthorityParentChildMismatchError(
            authority_family=resolved.authority_family,
            authority_stable_key=resolved.authority_stable_key,
            details={"reason": "parent_pool_code_mismatch"},
        )
    return resolved
