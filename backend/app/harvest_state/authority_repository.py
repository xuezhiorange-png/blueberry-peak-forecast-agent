from __future__ import annotations

# mypy: disable-error-code="attr-defined,assignment,union-attr,redundant-cast"
import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from backend.app.harvest_state.authority_canonical import (
    build_capacity_pool_definition_stable_key,
    build_daily_capacity_stable_key,
    build_holiday_calendar_stable_key,
    build_initial_inventory_stable_key,
    build_mature_inventory_loss_stable_key,
    build_run_parameter_package_stable_key,
    build_weather_rule_stable_key,
    make_authority_row_hash,
    make_lifecycle_event_hash,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityConsumabilityIntervalConflictError,
    AuthorityConsumabilityIntervalInvalidError,
    AuthorityConsumabilityIntervalOverlapError,
    AuthorityDependencyConflictError,
    AuthorityHashConflictError,
    AuthorityNotFoundError,
    AuthorityVersionConflictError,
    LifecycleTransitionInvalidError,
)
from backend.app.harvest_state.authority_repository_types import (
    AuthorityCreateOrLoadResult,
    AuthorityPersistentIdentity,
    RunPackageReplacementResult,
)
from backend.app.harvest_state.authority_schemas import (
    Task9AuthorityLifecycleEventSchema,
    Task9CapacityPoolDefinitionBundleSchema,
    Task9CapacityPoolDefinitionSchema,
    Task9CapacityPoolDefinitionSemanticBundle,
    Task9CapacityPoolDefinitionSemanticInput,
    Task9CapacityPoolMemberSchema,
    Task9DailyCapacityAuthoritySchema,
    Task9DailyCapacitySemanticInput,
    Task9HolidayCalendarBundleSchema,
    Task9HolidayCalendarDateSchema,
    Task9HolidayCalendarSemanticBundle,
    Task9HolidayCalendarVersionSchema,
    Task9InitialInventoryBundleSchema,
    Task9InitialInventoryCohortSchema,
    Task9InitialInventorySemanticBundle,
    Task9InitialInventorySnapshotSchema,
    Task9LifecycleEventSemanticInput,
    Task9MatureInventoryLossAuthoritySchema,
    Task9MatureLossSemanticInput,
    Task9RunParameterPackageBundleSchema,
    Task9RunParameterPackageSchema,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleConfigVersionSchema,
    Task9WeatherRuleSemanticInput,
)
from backend.app.harvest_state.enums import AuthorityFamily, AuthorityStatus
from backend.app.models import (
    Task9AuthorityLifecycleEvent,
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

type PoolBundleInput = (
    Task9CapacityPoolDefinitionBundleSchema | Task9CapacityPoolDefinitionSemanticBundle
)
type DailyInput = Task9DailyCapacityAuthoritySchema | Task9DailyCapacitySemanticInput
type HolidayBundleInput = Task9HolidayCalendarBundleSchema | Task9HolidayCalendarSemanticBundle
type WeatherInput = Task9WeatherRuleConfigVersionSchema | Task9WeatherRuleSemanticInput
type RunPackageInput = Task9RunParameterPackageSchema | Task9RunParameterPackageSemanticInput
type RunPackageBundleInput = Task9RunParameterPackageBundleSchema
type InventoryBundleInput = Task9InitialInventoryBundleSchema | Task9InitialInventorySemanticBundle
type MatureLossInput = Task9MatureInventoryLossAuthoritySchema | Task9MatureLossSemanticInput
type LifecycleRowModel = (
    Task9CapacityPoolDefinition
    | Task9DailyCapacityAuthority
    | Task9HolidayCalendarVersion
    | Task9WeatherRuleConfigVersion
    | Task9RunParameterPackage
    | Task9InitialInventorySnapshot
    | Task9MatureInventoryLossAuthority
)
type VerifiedHolidayLoad = tuple[
    Task9HolidayCalendarVersion,
    Task9HolidayCalendarBundleSchema,
]
type VerifiedWeatherLoad = tuple[
    Task9WeatherRuleConfigVersion,
    Task9WeatherRuleConfigVersionSchema,
]

_HASH_CONFLICT_CODE = "AUTHORITY_HASH_CONFLICT"
_VERSION_CONFLICT_CODE = "AUTHORITY_VERSION_CONFLICT"


def _now() -> datetime:
    return datetime.now(UTC)


def _extract_constraint_name(exc: SAIntegrityError) -> str | None:
    for candidate in (
        getattr(exc, "orig", None),
        getattr(getattr(exc, "orig", None), "orig", None),
        getattr(getattr(exc, "orig", None), "__cause__", None),
    ):
        if candidate is None:
            continue
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, bytes):
            return name.decode("ascii")
        if isinstance(name, str):
            return name
        diag = getattr(candidate, "diag", None)
        if diag is not None:
            diag_name = getattr(diag, "constraint_name", None)
            if isinstance(diag_name, bytes):
                return diag_name.decode("ascii")
            if isinstance(diag_name, str):
                return diag_name
    return None


def _extract_sqlstate(exc: SAIntegrityError) -> str | None:
    for candidate in (
        getattr(exc, "orig", None),
        getattr(getattr(exc, "orig", None), "orig", None),
        getattr(getattr(exc, "orig", None), "__cause__", None),
    ):
        if candidate is None:
            continue
        sqlstate = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if isinstance(sqlstate, bytes):
            return sqlstate.decode("ascii")
        if isinstance(sqlstate, str):
            return sqlstate
    return None


def authority_lock_key(
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
) -> int:
    payload = (
        f"family:{family.value}|stable:{stable_key}|"
        f"business_version:{business_version}|revision:{revision}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def _acquire_authority_lock(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                authority_lock_key(
                    family=family,
                    stable_key=stable_key,
                    business_version=business_version,
                    revision=revision,
                )
            )
        )
    )


def _persistent_identity(
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
) -> AuthorityPersistentIdentity:
    return AuthorityPersistentIdentity(
        authority_family=family,
        authority_stable_key=stable_key,
        authority_business_version=business_version,
        authority_revision=revision,
    )


def _family_model(family: AuthorityFamily) -> type[LifecycleRowModel]:
    return cast(
        type[LifecycleRowModel],
        {
            AuthorityFamily.CAPACITY_POOL_DEFINITION: Task9CapacityPoolDefinition,
            AuthorityFamily.DAILY_CAPACITY: Task9DailyCapacityAuthority,
            AuthorityFamily.HOLIDAY_CALENDAR_VERSION: Task9HolidayCalendarVersion,
            AuthorityFamily.WEATHER_RULE_CONFIG_VERSION: Task9WeatherRuleConfigVersion,
            AuthorityFamily.RUN_PARAMETER_PACKAGE: Task9RunParameterPackage,
            AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT: Task9InitialInventorySnapshot,
            AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY: Task9MatureInventoryLossAuthority,
        }[family],
    )


def _row_status(row: LifecycleRowModel) -> AuthorityStatus:
    return AuthorityStatus(row.status)


def _build_initial_lifecycle_events(
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
    row_hash: str,
    status: AuthorityStatus,
    consumable_from_local_date: date | None,
    consumable_to_local_date: date | None,
    status_changed_at: datetime,
    source_system: str,
    source_record_key: str,
) -> list[Task9LifecycleEventSemanticInput]:
    initial = Task9LifecycleEventSemanticInput(
        authority_family=family,
        authority_stable_key=stable_key,
        authority_business_version=business_version,
        authority_revision=revision,
        business_row_hash=row_hash,
        transition_sequence=1,
        old_status=None,
        new_status=AuthorityStatus.DRAFT,
        old_consumable_from_local_date=None,
        old_consumable_to_local_date=None,
        new_consumable_from_local_date=None,
        new_consumable_to_local_date=None,
        superseded_by_authority_stable_key=None,
        superseded_by_authority_business_version=None,
        superseded_by_authority_revision=None,
        transitioned_at=status_changed_at,
        source_system=source_system,
        source_record_key=source_record_key,
    )
    if status is AuthorityStatus.DRAFT:
        return [initial]
    if status is AuthorityStatus.ACTIVE:
        return [
            initial,
            Task9LifecycleEventSemanticInput(
                authority_family=family,
                authority_stable_key=stable_key,
                authority_business_version=business_version,
                authority_revision=revision,
                business_row_hash=row_hash,
                transition_sequence=2,
                old_status=AuthorityStatus.DRAFT,
                new_status=AuthorityStatus.ACTIVE,
                old_consumable_from_local_date=None,
                old_consumable_to_local_date=None,
                new_consumable_from_local_date=consumable_from_local_date,
                new_consumable_to_local_date=None,
                superseded_by_authority_stable_key=None,
                superseded_by_authority_business_version=None,
                superseded_by_authority_revision=None,
                transitioned_at=status_changed_at,
                source_system=source_system,
                source_record_key=source_record_key,
            ),
        ]
    if status is AuthorityStatus.CANCELLED:
        return [
            initial,
            Task9LifecycleEventSemanticInput(
                authority_family=family,
                authority_stable_key=stable_key,
                authority_business_version=business_version,
                authority_revision=revision,
                business_row_hash=row_hash,
                transition_sequence=2,
                old_status=AuthorityStatus.DRAFT,
                new_status=AuthorityStatus.CANCELLED,
                old_consumable_from_local_date=None,
                old_consumable_to_local_date=None,
                new_consumable_from_local_date=None,
                new_consumable_to_local_date=None,
                superseded_by_authority_stable_key=None,
                superseded_by_authority_business_version=None,
                superseded_by_authority_revision=None,
                transitioned_at=status_changed_at,
                source_system=source_system,
                source_record_key=source_record_key,
            ),
        ]
    raise LifecycleTransitionInvalidError(
        authority_family=family.value,
        authority_stable_key=stable_key,
        detail="create_or_load only supports draft/active/cancelled initial states",
    )


def _event_row_from_semantic(
    event: Task9LifecycleEventSemanticInput,
) -> Task9AuthorityLifecycleEvent:
    event_hash = make_lifecycle_event_hash(event)
    return Task9AuthorityLifecycleEvent(
        authority_family=event.authority_family.value,
        authority_stable_key=event.authority_stable_key,
        authority_business_version=event.authority_business_version,
        authority_revision=event.authority_revision,
        business_row_hash=event.business_row_hash,
        transition_sequence=event.transition_sequence,
        old_status=None if event.old_status is None else event.old_status.value,
        new_status=event.new_status.value,
        old_consumable_from_local_date=event.old_consumable_from_local_date,
        old_consumable_to_local_date=event.old_consumable_to_local_date,
        new_consumable_from_local_date=event.new_consumable_from_local_date,
        new_consumable_to_local_date=event.new_consumable_to_local_date,
        superseded_by_authority_stable_key=event.superseded_by_authority_stable_key,
        superseded_by_authority_business_version=event.superseded_by_authority_business_version,
        superseded_by_authority_revision=event.superseded_by_authority_revision,
        transitioned_at=event.transitioned_at,
        source_system=event.source_system,
        source_record_key=event.source_record_key,
        lifecycle_event_hash=event_hash,
    )


def _classify_boundary_integrity_error(
    *,
    exc: SAIntegrityError,
    authority_family: AuthorityFamily,
    authority_stable_key: str,
) -> Exception:
    constraint_name = _extract_constraint_name(exc)
    sqlstate = _extract_sqlstate(exc)
    if constraint_name and constraint_name.startswith("ex_task9_"):
        return AuthorityConsumabilityIntervalOverlapError(
            authority_family=authority_family.value,
            authority_stable_key=authority_stable_key,
            detail=f"constraint={constraint_name} sqlstate={sqlstate}",
        )
    if constraint_name and any(
        token in constraint_name
        for token in (
            "_lifecycle_projection",
            "_consumable_from",
            "_consumable_to",
            "_effective_range",
        )
    ):
        return AuthorityConsumabilityIntervalInvalidError(
            authority_family=authority_family.value,
            authority_stable_key=authority_stable_key,
            detail=f"constraint={constraint_name} sqlstate={sqlstate}",
        )
    if constraint_name and (
        "_superseded" in constraint_name
        or constraint_name.startswith("fk_task9_")
        or constraint_name.startswith("uq_task9_")
    ):
        return AuthorityConsumabilityIntervalConflictError(
            authority_family=authority_family.value,
            authority_stable_key=authority_stable_key,
            detail=f"constraint={constraint_name} sqlstate={sqlstate}",
        )
    return AuthorityConsumabilityIntervalConflictError(
        authority_family=authority_family.value,
        authority_stable_key=authority_stable_key,
        detail=f"sqlstate={sqlstate or 'unknown'}",
    )


def _family_scalar_column(family: AuthorityFamily, field_name: str) -> InstrumentedAttribute[Any]:
    return cast(InstrumentedAttribute[Any], getattr(_family_model(family), field_name))


def _authority_dict(row: LifecycleRowModel) -> dict[str, Any]:
    base = {
        "status": row.status,
        "status_changed_at": row.status_changed_at,
        "available_at_local_date": row.available_at_local_date,
        "consumable_from_local_date": row.consumable_from_local_date,
        "consumable_to_local_date": row.consumable_to_local_date,
        "superseded_by_id": row.superseded_by_id,
        "source_system": row.source_system,
        "source_record_key": row.source_record_key,
        "source_version": row.source_version,
        "row_hash": row.row_hash,
    }
    if isinstance(row, Task9CapacityPoolDefinition):
        return base | {
            "season_id": row.season_id,
            "destination_factory_id": row.destination_factory_id,
            "capacity_pool_code": row.capacity_pool_code,
            "capacity_pool_grain": row.capacity_pool_grain,
            "capacity_input_mode": row.capacity_input_mode,
            "capacity_pool_version": row.capacity_pool_version,
            "revision": row.revision,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
        }
    if isinstance(row, Task9HolidayCalendarVersion):
        return base | {
            "season_id": row.season_id,
            "calendar_code": row.calendar_code,
            "calendar_version": row.calendar_version,
            "revision": row.revision,
            "calendar_hash": row.calendar_hash,
            "region_scope": row.region_scope,
            "lifecycle_timezone_name": row.lifecycle_timezone_name,
        }
    if isinstance(row, Task9WeatherRuleConfigVersion):
        return base | {
            "rule_code": row.rule_code,
            "rule_version": row.rule_version,
            "revision": row.revision,
            "lifecycle_timezone_name": row.lifecycle_timezone_name,
            "combination_method": row.combination_method,
            "minimum_ratio": row.minimum_ratio,
            "maximum_ratio": row.maximum_ratio,
            "required_feature_ids": row.required_feature_ids,
            "feature_rules": row.feature_rules_json,
            "missing_feature_policy": row.missing_feature_policy,
            "config_hash": row.config_hash,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
        }
    if isinstance(row, Task9RunParameterPackage):
        return base | {
            "season_id": row.season_id,
            "destination_factory_id": row.destination_factory_id,
            "farm_scope_key": row.farm_scope_key,
            "farm_timezone": row.farm_timezone,
            "destination_factory_timezone": row.destination_factory_timezone,
            "harvest_bucket_anchor_local_time": row.harvest_bucket_anchor_local_time,
            "harvest_to_arrival_lag_days": row.harvest_to_arrival_lag_days,
            "package_version": row.package_version,
            "revision": row.revision,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "holiday_calendar_version_id": row.holiday_calendar_version_id,
            "weather_rule_config_version_id": row.weather_rule_config_version_id,
        }
    if isinstance(row, Task9InitialInventorySnapshot):
        return base | {
            "season_id": row.season_id,
            "destination_factory_id": row.destination_factory_id,
            "opening_state_date": row.opening_state_date,
            "snapshot_version": row.snapshot_version,
            "revision": row.revision,
            "initial_opening_mature_inventory_kg": row.initial_opening_mature_inventory_kg,
        }
    if isinstance(row, Task9MatureInventoryLossAuthority):
        return base | {
            "season_id": row.season_id,
            "destination_factory_id": row.destination_factory_id,
            "state_date": row.state_date,
            "capacity_pool_code": row.capacity_pool_code,
            "forecast_quantile": row.forecast_quantile,
            "loss_version": row.loss_version,
            "revision": row.revision,
            "mature_inventory_loss_quantity_kg": row.mature_inventory_loss_quantity_kg,
        }
    raise TypeError(f"unsupported authority row type: {type(row).__name__}")


def _member_projection_expected_from_parent(
    parent: Task9CapacityPoolDefinition,
) -> tuple[date, date]:
    infinity = date.max
    return (
        parent.consumable_from_local_date or infinity,
        parent.consumable_to_local_date or infinity,
    )


def _member_schema(member: Task9CapacityPoolMember) -> Task9CapacityPoolMemberSchema:
    return Task9CapacityPoolMemberSchema(
        farm_id=member.farm_id,
        subfarm_id=member.subfarm_id,
        variety_id=member.variety_id,
    )


def _holiday_header_from_bundle(bundle: HolidayBundleInput) -> Task9HolidayCalendarVersionSchema:
    if isinstance(bundle, Task9HolidayCalendarBundleSchema):
        return bundle.header
    return Task9HolidayCalendarVersionSchema.model_validate(bundle.model_dump(exclude={"dates"}))


def _inventory_snapshot_from_bundle(
    bundle: InventoryBundleInput,
) -> Task9InitialInventorySnapshotSchema:
    if isinstance(bundle, Task9InitialInventoryBundleSchema):
        return bundle.snapshot
    return Task9InitialInventorySnapshotSchema.model_validate(
        bundle.model_dump(exclude={"cohorts"})
    )


def _raise_dependency_conflict(
    *,
    package_stable_key: str,
    detail: str,
) -> AuthorityDependencyConflictError:
    return AuthorityDependencyConflictError(
        authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE.value,
        authority_stable_key=package_stable_key,
        detail=detail,
    )


def _holiday_date_schema(row: Task9HolidayCalendarDate) -> Task9HolidayCalendarDateSchema:
    return Task9HolidayCalendarDateSchema(
        holiday_date=row.holiday_date,
        holiday_code=row.holiday_code,
        holiday_name=row.holiday_name,
    )


def _cohort_schema(row: Task9InitialInventoryCohort) -> Task9InitialInventoryCohortSchema:
    return Task9InitialInventoryCohortSchema(
        stable_cohort_key=row.stable_cohort_key,
        forecast_quantile=row.forecast_quantile,
        cohort_date=row.cohort_date,
        farm_id=row.farm_id,
        subfarm_id=row.subfarm_id,
        variety_id=row.variety_id,
        remaining_quantity_kg=row.remaining_quantity_kg,
    )


def _definition_schema(row: Task9CapacityPoolDefinition) -> Task9CapacityPoolDefinitionSchema:
    return Task9CapacityPoolDefinitionSchema.model_validate(_authority_dict(row))


def _daily_schema(
    row: Task9DailyCapacityAuthority,
    *,
    parent_definition: Task9CapacityPoolDefinitionSchema | Task9CapacityPoolDefinitionSemanticInput,
) -> Task9DailyCapacityAuthoritySchema:
    return Task9DailyCapacityAuthoritySchema.model_validate(
        {
            "capacity_pool_definition_id": row.capacity_pool_definition_id,
            "season_id": parent_definition.season_id,
            "destination_factory_id": parent_definition.destination_factory_id,
            "capacity_pool_code": parent_definition.capacity_pool_code,
            "capacity_pool_version": parent_definition.capacity_pool_version,
            "capacity_pool_revision": parent_definition.revision,
            "capacity_date": row.capacity_date,
            "daily_capacity_revision": row.daily_capacity_revision,
            "capacity_input_mode": parent_definition.capacity_input_mode,
            "planned_picker_count": row.planned_picker_count,
            "kg_per_person_per_day": row.kg_per_person_per_day,
            "direct_nominal_capacity_kg_per_day": row.direct_nominal_capacity_kg_per_day,
            "labor_availability_ratio": row.labor_availability_ratio,
            "operational_efficiency_ratio": row.operational_efficiency_ratio,
            "available_at_local_date": row.available_at_local_date,
            "consumable_from_local_date": row.consumable_from_local_date,
            "consumable_to_local_date": row.consumable_to_local_date,
            "status": row.status,
            "status_changed_at": row.status_changed_at,
            "superseded_by_id": row.superseded_by_id,
            "source_system": row.source_system,
            "source_record_key": row.source_record_key,
            "source_version": row.source_version,
            "row_hash": row.row_hash,
        }
    )


def _holiday_header_schema(row: Task9HolidayCalendarVersion) -> Task9HolidayCalendarVersionSchema:
    return Task9HolidayCalendarVersionSchema.model_validate(_authority_dict(row))


def _weather_schema(row: Task9WeatherRuleConfigVersion) -> Task9WeatherRuleConfigVersionSchema:
    return Task9WeatherRuleConfigVersionSchema.model_validate(_authority_dict(row))


def _run_package_schema(row: Task9RunParameterPackage) -> Task9RunParameterPackageSchema:
    return Task9RunParameterPackageSchema.model_validate(_authority_dict(row))


def _inventory_schema(row: Task9InitialInventorySnapshot) -> Task9InitialInventorySnapshotSchema:
    return Task9InitialInventorySnapshotSchema.model_validate(_authority_dict(row))


def _mature_loss_schema(
    row: Task9MatureInventoryLossAuthority,
) -> Task9MatureInventoryLossAuthoritySchema:
    return Task9MatureInventoryLossAuthoritySchema.model_validate(_authority_dict(row))


def _lifecycle_event_schema(
    row: Task9AuthorityLifecycleEvent,
) -> Task9AuthorityLifecycleEventSchema:
    return Task9AuthorityLifecycleEventSchema(
        authority_family=AuthorityFamily(row.authority_family),
        authority_stable_key=row.authority_stable_key,
        authority_business_version=row.authority_business_version,
        authority_revision=row.authority_revision,
        business_row_hash=row.business_row_hash,
        transition_sequence=row.transition_sequence,
        old_status=None if row.old_status is None else AuthorityStatus(row.old_status),
        new_status=AuthorityStatus(row.new_status),
        old_consumable_from_local_date=row.old_consumable_from_local_date,
        old_consumable_to_local_date=row.old_consumable_to_local_date,
        new_consumable_from_local_date=row.new_consumable_from_local_date,
        new_consumable_to_local_date=row.new_consumable_to_local_date,
        superseded_by_authority_stable_key=row.superseded_by_authority_stable_key,
        superseded_by_authority_business_version=row.superseded_by_authority_business_version,
        superseded_by_authority_revision=row.superseded_by_authority_revision,
        transitioned_at=row.transitioned_at,
        source_system=row.source_system,
        source_record_key=row.source_record_key,
        lifecycle_event_hash=row.lifecycle_event_hash,
    )


async def _load_lifecycle_events(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
) -> list[Task9AuthorityLifecycleEvent]:
    result = await session.execute(
        select(Task9AuthorityLifecycleEvent)
        .where(
            Task9AuthorityLifecycleEvent.authority_family == family.value,
            Task9AuthorityLifecycleEvent.authority_stable_key == stable_key,
            Task9AuthorityLifecycleEvent.authority_business_version == business_version,
            Task9AuthorityLifecycleEvent.authority_revision == revision,
        )
        .order_by(Task9AuthorityLifecycleEvent.transition_sequence.asc())
    )
    return list(result.scalars())


async def _verify_lifecycle_chain(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
    authority: LifecycleRowModel,
) -> None:
    events = await _load_lifecycle_events(
        session,
        family=family,
        stable_key=stable_key,
        business_version=business_version,
        revision=revision,
    )
    if not events:
        raise AuthorityNotFoundError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="lifecycle chain missing",
        )

    current_row_hash = authority.row_hash
    previous: Task9AuthorityLifecycleEventSchema | None = None
    allowed = {
        (AuthorityStatus.DRAFT, AuthorityStatus.ACTIVE),
        (AuthorityStatus.DRAFT, AuthorityStatus.CANCELLED),
        (AuthorityStatus.ACTIVE, AuthorityStatus.SUPERSEDED),
        (AuthorityStatus.ACTIVE, AuthorityStatus.RETIRED),
    }
    for index, event in enumerate(events, start=1):
        typed = _lifecycle_event_schema(event)
        if (
            typed.authority_family is not family
            or typed.authority_stable_key != stable_key
            or typed.authority_business_version != business_version
            or typed.authority_revision != revision
        ):
            raise LifecycleTransitionInvalidError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                detail="event identity does not bind to requested authority",
            )
        if typed.business_row_hash != current_row_hash:
            raise AuthorityHashConflictError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                expected_hash=current_row_hash,
                actual_hash=typed.business_row_hash,
            )
        recomputed_hash = make_lifecycle_event_hash(
            Task9LifecycleEventSemanticInput.model_validate(
                typed.model_dump(exclude={"lifecycle_event_hash"})
            )
        )
        if recomputed_hash != typed.lifecycle_event_hash:
            raise AuthorityHashConflictError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                expected_hash=recomputed_hash,
                actual_hash=typed.lifecycle_event_hash,
            )
        if index == 1:
            if not (
                typed.transition_sequence == 1
                and typed.old_status is None
                and typed.new_status is AuthorityStatus.DRAFT
                and typed.old_consumable_from_local_date is None
                and typed.old_consumable_to_local_date is None
                and typed.new_consumable_from_local_date is None
                and typed.new_consumable_to_local_date is None
                and typed.superseded_by_authority_stable_key is None
                and typed.superseded_by_authority_business_version is None
                and typed.superseded_by_authority_revision is None
            ):
                raise LifecycleTransitionInvalidError(
                    authority_family=family.value,
                    authority_stable_key=stable_key,
                    detail="initial lifecycle event must be null->draft",
                )
            previous = typed
            continue
        assert previous is not None
        if typed.transition_sequence != previous.transition_sequence + 1:
            raise AuthorityConsumabilityIntervalConflictError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                detail="lifecycle transition_sequence gap",
            )
        if (
            typed.old_status != previous.new_status
            or typed.old_consumable_from_local_date != previous.new_consumable_from_local_date
            or typed.old_consumable_to_local_date != previous.new_consumable_to_local_date
        ):
            raise AuthorityConsumabilityIntervalConflictError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                detail="lifecycle old/new continuity mismatch",
            )
        if (cast(AuthorityStatus, typed.old_status), typed.new_status) not in allowed:
            raise LifecycleTransitionInvalidError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                detail=(
                    f"illegal lifecycle transition "
                    f"{cast(AuthorityStatus, typed.old_status).value}->{typed.new_status.value}"
                ),
            )
        if typed.new_status is AuthorityStatus.SUPERSEDED:
            if (
                typed.superseded_by_authority_stable_key is None
                or typed.superseded_by_authority_business_version is None
                or typed.superseded_by_authority_revision is None
            ):
                raise LifecycleTransitionInvalidError(
                    authority_family=family.value,
                    authority_stable_key=stable_key,
                    detail="superseded lifecycle event requires replacement identity",
                )
        else:
            if (
                typed.superseded_by_authority_stable_key is not None
                or typed.superseded_by_authority_business_version is not None
                or typed.superseded_by_authority_revision is not None
            ):
                raise LifecycleTransitionInvalidError(
                    authority_family=family.value,
                    authority_stable_key=stable_key,
                    detail="replacement identity only allowed for superseded transition",
                )
        previous = typed

    assert previous is not None
    if (
        previous.new_status.value != authority.status
        or previous.new_consumable_from_local_date != authority.consumable_from_local_date
        or previous.new_consumable_to_local_date != authority.consumable_to_local_date
    ):
        raise AuthorityConsumabilityIntervalConflictError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="final lifecycle projection does not match authority row",
        )
    if authority.status == AuthorityStatus.SUPERSEDED.value:
        if authority.superseded_by_id is None:
            raise LifecycleTransitionInvalidError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                detail="superseded authority missing superseded_by_id",
            )
        replacement = await session.get(type(authority), authority.superseded_by_id)
        if replacement is None:
            raise AuthorityNotFoundError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                detail="superseded replacement row missing",
            )
        repl_stable, repl_version, repl_revision = _row_identity(
            family, cast(LifecycleRowModel, replacement)
        )
        if (
            previous.superseded_by_authority_stable_key != repl_stable
            or previous.superseded_by_authority_business_version != repl_version
            or previous.superseded_by_authority_revision != repl_revision
        ):
            raise AuthorityConsumabilityIntervalConflictError(
                authority_family=family.value,
                authority_stable_key=stable_key,
                detail="replacement event identity does not match superseded_by row",
            )


def _row_identity(
    family: AuthorityFamily,
    row: LifecycleRowModel,
) -> tuple[str, str, int]:
    if family is AuthorityFamily.CAPACITY_POOL_DEFINITION:
        typed_pool = _definition_schema(cast(Task9CapacityPoolDefinition, row))
        return (
            build_capacity_pool_definition_stable_key(typed_pool),
            typed_pool.capacity_pool_version,
            typed_pool.revision,
        )
    if family is AuthorityFamily.DAILY_CAPACITY:
        parts = row.source_record_key.split(":")
        stable_key = ":".join(parts[:7])
        return stable_key, parts[4], int(parts[7])
    if family is AuthorityFamily.HOLIDAY_CALENDAR_VERSION:
        typed_holiday = _holiday_header_schema(cast(Task9HolidayCalendarVersion, row))
        return (
            build_holiday_calendar_stable_key(typed_holiday),
            typed_holiday.calendar_version,
            typed_holiday.revision,
        )
    if family is AuthorityFamily.WEATHER_RULE_CONFIG_VERSION:
        typed_weather = _weather_schema(cast(Task9WeatherRuleConfigVersion, row))
        return (
            build_weather_rule_stable_key(typed_weather),
            typed_weather.rule_version,
            typed_weather.revision,
        )
    if family is AuthorityFamily.RUN_PARAMETER_PACKAGE:
        typed_package = _run_package_schema(cast(Task9RunParameterPackage, row))
        return (
            build_run_parameter_package_stable_key(typed_package),
            typed_package.package_version,
            typed_package.revision,
        )
    if family is AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT:
        typed_inventory = _inventory_schema(cast(Task9InitialInventorySnapshot, row))
        return (
            build_initial_inventory_stable_key(typed_inventory),
            typed_inventory.snapshot_version,
            typed_inventory.revision,
        )
    typed_loss = _mature_loss_schema(cast(Task9MatureInventoryLossAuthority, row))
    return (
        build_mature_inventory_loss_stable_key(typed_loss),
        typed_loss.loss_version,
        typed_loss.revision,
    )


async def _load_verified_capacity_pool_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> tuple[Task9CapacityPoolDefinition, Task9CapacityPoolDefinitionBundleSchema]:
    stmt: Select[tuple[Task9CapacityPoolDefinition]] = select(Task9CapacityPoolDefinition).where(
        Task9CapacityPoolDefinition.id == authority_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION.value,
            detail=f"id={authority_id}",
        )
    member_rows = list(
        (
            await session.execute(
                select(Task9CapacityPoolMember).where(
                    Task9CapacityPoolMember.capacity_pool_definition_id == authority_id
                )
            )
        ).scalars()
    )
    definition = _definition_schema(row)
    bundle = Task9CapacityPoolDefinitionBundleSchema(
        **definition.model_dump(),
        members=[_member_schema(item).model_dump() for item in member_rows],
    )
    expected_pool_hash = make_authority_row_hash(bundle)
    if expected_pool_hash != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION.value,
            authority_stable_key=build_capacity_pool_definition_stable_key(bundle.definition),
            expected_hash=expected_pool_hash,
            actual_hash=row.row_hash,
        )
    expected_from_key, expected_to_key = _member_projection_expected_from_parent(row)
    for member_row in member_rows:
        expected_member_hash = make_authority_row_hash(
            _member_schema(member_row), parent_definition=bundle.definition
        )
        if expected_member_hash != member_row.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION.value,
                authority_stable_key=build_capacity_pool_definition_stable_key(bundle.definition),
                expected_hash=expected_member_hash,
                actual_hash=member_row.row_hash,
            )
        if (
            member_row.season_id != row.season_id
            or member_row.destination_factory_id != row.destination_factory_id
            or member_row.effective_from != row.effective_from
            or member_row.effective_to != row.effective_to
            or member_row.status != row.status
            or member_row.consumable_from_key != expected_from_key
            or member_row.consumable_to_key != expected_to_key
        ):
            raise AuthorityConsumabilityIntervalConflictError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION.value,
                authority_stable_key=build_capacity_pool_definition_stable_key(bundle.definition),
                detail="member projection no longer matches parent row",
            )
    stable_key, business_version, revision = _row_identity(
        AuthorityFamily.CAPACITY_POOL_DEFINITION, row
    )
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key=stable_key,
        business_version=business_version,
        revision=revision,
        authority=row,
    )
    return row, bundle


async def _load_verified_daily_capacity_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> tuple[Task9DailyCapacityAuthority, Task9DailyCapacityAuthoritySchema]:
    stmt: Select[tuple[Task9DailyCapacityAuthority]] = select(Task9DailyCapacityAuthority).where(
        Task9DailyCapacityAuthority.id == authority_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.DAILY_CAPACITY.value,
            detail=f"id={authority_id}",
        )
    parent_row, _parent_bundle = await _load_verified_capacity_pool_by_id(
        session,
        authority_id=row.capacity_pool_definition_id,
        for_update=for_update,
    )
    parent_definition = _definition_schema(parent_row)
    typed = _daily_schema(row, parent_definition=parent_definition)
    expected_hash = make_authority_row_hash(typed)
    stable_key = build_daily_capacity_stable_key(typed)
    if expected_hash != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.DAILY_CAPACITY.value,
            authority_stable_key=stable_key,
            expected_hash=expected_hash,
            actual_hash=row.row_hash,
        )
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=stable_key,
        business_version=typed.capacity_pool_version,
        revision=typed.daily_capacity_revision,
        authority=row,
    )
    return row, typed


async def _load_verified_holiday_dependency_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> VerifiedHolidayLoad:
    stmt: Select[tuple[Task9HolidayCalendarVersion]] = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.id == authority_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION.value,
            detail=f"id={authority_id}",
        )
    child_rows = list(
        (
            await session.execute(
                select(Task9HolidayCalendarDate).where(
                    Task9HolidayCalendarDate.holiday_calendar_version_id == authority_id
                )
            )
        ).scalars()
    )
    try:
        header = _holiday_header_schema(row)
        bundle = Task9HolidayCalendarBundleSchema(
            **header.model_dump(),
            dates=[_holiday_date_schema(item).model_dump() for item in child_rows],
        )
    except ValidationError as exc:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION.value,
            authority_stable_key=(
                f"holiday-calendar:{row.season_id}:{row.calendar_code}:"
                f"{row.lifecycle_timezone_name}"
            ),
            detail="persisted holiday dependency no longer validates against canonical bundle",
        ) from exc
    expected_hash = make_authority_row_hash(bundle)
    stable_key = build_holiday_calendar_stable_key(header)
    if expected_hash != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION.value,
            authority_stable_key=stable_key,
            expected_hash=expected_hash,
            actual_hash=row.row_hash,
        )
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=stable_key,
        business_version=header.calendar_version,
        revision=header.revision,
        authority=row,
    )
    return row, bundle


async def _load_verified_weather_dependency_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> VerifiedWeatherLoad:
    stmt: Select[tuple[Task9WeatherRuleConfigVersion]] = select(
        Task9WeatherRuleConfigVersion
    ).where(Task9WeatherRuleConfigVersion.id == authority_id)
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION.value,
            detail=f"id={authority_id}",
        )
    try:
        typed = _weather_schema(row)
    except ValidationError as exc:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION.value,
            authority_stable_key=f"weather-rule:{row.rule_code}:{row.lifecycle_timezone_name}",
            detail="persisted weather dependency no longer validates against canonical payload",
        ) from exc
    expected_hash = make_authority_row_hash(typed)
    stable_key = build_weather_rule_stable_key(typed)
    if expected_hash != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION.value,
            authority_stable_key=stable_key,
            expected_hash=expected_hash,
            actual_hash=row.row_hash,
        )
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=stable_key,
        business_version=typed.rule_version,
        revision=typed.revision,
        authority=row,
    )
    return row, typed


async def _load_verified_run_package_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> tuple[Task9RunParameterPackage, Task9RunParameterPackageBundleSchema]:
    stmt: Select[tuple[Task9RunParameterPackage]] = select(Task9RunParameterPackage).where(
        Task9RunParameterPackage.id == authority_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE.value,
            detail=f"id={authority_id}",
        )
    holiday_row, holiday_bundle = await _load_verified_holiday_dependency_by_id(
        session,
        authority_id=row.holiday_calendar_version_id,
        for_update=for_update,
    )
    weather_row, weather_schema = await _load_verified_weather_dependency_by_id(
        session,
        authority_id=row.weather_rule_config_version_id,
        for_update=for_update,
    )
    package_schema = _run_package_schema(row)
    if package_schema.season_id != holiday_bundle.season_id:
        raise AuthorityDependencyConflictError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE.value,
            authority_stable_key=build_run_parameter_package_stable_key(package_schema),
            detail="run package season does not match persisted holiday dependency",
        )
    if not (
        package_schema.destination_factory_timezone
        == holiday_bundle.lifecycle_timezone_name
        == weather_schema.lifecycle_timezone_name
    ):
        raise AuthorityDependencyConflictError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE.value,
            authority_stable_key=build_run_parameter_package_stable_key(package_schema),
            detail="run package timezone does not match persisted dependencies",
        )
    expected_hash = make_authority_row_hash(
        package_schema,
        holiday_calendar=holiday_bundle,
        weather_rule=weather_schema,
    )
    stable_key = build_run_parameter_package_stable_key(package_schema)
    if expected_hash != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE.value,
            authority_stable_key=stable_key,
            expected_hash=expected_hash,
            actual_hash=row.row_hash,
        )
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=stable_key,
        business_version=package_schema.package_version,
        revision=package_schema.revision,
        authority=row,
    )
    return row, Task9RunParameterPackageBundleSchema(
        package=package_schema,
        holiday_calendar=holiday_bundle,
        weather_rule=weather_schema,
    )


async def _load_verified_initial_inventory_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> tuple[Task9InitialInventorySnapshot, Task9InitialInventoryBundleSchema]:
    stmt: Select[tuple[Task9InitialInventorySnapshot]] = select(
        Task9InitialInventorySnapshot
    ).where(Task9InitialInventorySnapshot.id == authority_id)
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT.value,
            detail=f"id={authority_id}",
        )
    cohort_rows = list(
        (
            await session.execute(
                select(Task9InitialInventoryCohort).where(
                    Task9InitialInventoryCohort.initial_inventory_snapshot_id == authority_id
                )
            )
        ).scalars()
    )
    snapshot = _inventory_schema(row)
    bundle = Task9InitialInventoryBundleSchema(
        **snapshot.model_dump(),
        cohorts=[_cohort_schema(item).model_dump() for item in cohort_rows],
    )
    expected_hash = make_authority_row_hash(bundle)
    stable_key = build_initial_inventory_stable_key(snapshot)
    if expected_hash != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT.value,
            authority_stable_key=stable_key,
            expected_hash=expected_hash,
            actual_hash=row.row_hash,
        )
    for cohort_row in cohort_rows:
        expected_child_hash = make_authority_row_hash(
            _cohort_schema(cohort_row), parent_snapshot=snapshot
        )
        if expected_child_hash != cohort_row.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT.value,
                authority_stable_key=stable_key,
                expected_hash=expected_child_hash,
                actual_hash=cohort_row.row_hash,
            )
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        stable_key=stable_key,
        business_version=snapshot.snapshot_version,
        revision=snapshot.revision,
        authority=row,
    )
    return row, bundle


async def _load_verified_mature_loss_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> tuple[Task9MatureInventoryLossAuthority, Task9MatureInventoryLossAuthoritySchema]:
    stmt: Select[tuple[Task9MatureInventoryLossAuthority]] = select(
        Task9MatureInventoryLossAuthority
    ).where(Task9MatureInventoryLossAuthority.id == authority_id)
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
            detail=f"id={authority_id}",
        )
    typed = _mature_loss_schema(row)
    expected_hash = make_authority_row_hash(typed)
    stable_key = build_mature_inventory_loss_stable_key(typed)
    if expected_hash != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY.value,
            authority_stable_key=stable_key,
            expected_hash=expected_hash,
            actual_hash=row.row_hash,
        )
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        stable_key=stable_key,
        business_version=typed.loss_version,
        revision=typed.revision,
        authority=row,
    )
    return row, typed


async def load_capacity_pool_definition_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> Task9CapacityPoolDefinition:
    row, _bundle = await _load_verified_capacity_pool_by_id(
        session, authority_id=authority_id, for_update=for_update
    )
    return row


async def load_daily_capacity_authority_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> Task9DailyCapacityAuthority:
    row, _typed = await _load_verified_daily_capacity_by_id(
        session, authority_id=authority_id, for_update=for_update
    )
    return row


async def load_holiday_calendar_version_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> Task9HolidayCalendarVersion:
    row, _bundle = await _load_verified_holiday_dependency_by_id(
        session, authority_id=authority_id, for_update=for_update
    )
    return row


async def load_weather_rule_config_version_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> Task9WeatherRuleConfigVersion:
    row, _typed = await _load_verified_weather_dependency_by_id(
        session, authority_id=authority_id, for_update=for_update
    )
    return row


async def load_run_parameter_package_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> Task9RunParameterPackage:
    row, _bundle = await _load_verified_run_package_by_id(
        session, authority_id=authority_id, for_update=for_update
    )
    return row


async def load_initial_inventory_snapshot_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> Task9InitialInventorySnapshot:
    row, _bundle = await _load_verified_initial_inventory_by_id(
        session, authority_id=authority_id, for_update=for_update
    )
    return row


async def load_mature_inventory_loss_authority_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
    for_update: bool = False,
) -> Task9MatureInventoryLossAuthority:
    row, _typed = await _load_verified_mature_loss_by_id(
        session, authority_id=authority_id, for_update=for_update
    )
    return row


async def load_authority_by_id(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    authority_id: int,
    for_update: bool = False,
) -> LifecycleRowModel:
    if family is AuthorityFamily.CAPACITY_POOL_DEFINITION:
        return await load_capacity_pool_definition_by_id(
            session, authority_id=authority_id, for_update=for_update
        )
    if family is AuthorityFamily.DAILY_CAPACITY:
        return await load_daily_capacity_authority_by_id(
            session, authority_id=authority_id, for_update=for_update
        )
    if family is AuthorityFamily.HOLIDAY_CALENDAR_VERSION:
        return await load_holiday_calendar_version_by_id(
            session, authority_id=authority_id, for_update=for_update
        )
    if family is AuthorityFamily.WEATHER_RULE_CONFIG_VERSION:
        return await load_weather_rule_config_version_by_id(
            session, authority_id=authority_id, for_update=for_update
        )
    if family is AuthorityFamily.RUN_PARAMETER_PACKAGE:
        return await load_run_parameter_package_by_id(
            session, authority_id=authority_id, for_update=for_update
        )
    if family is AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT:
        return await load_initial_inventory_snapshot_by_id(
            session, authority_id=authority_id, for_update=for_update
        )
    return await load_mature_inventory_loss_authority_by_id(
        session, authority_id=authority_id, for_update=for_update
    )


async def _scalar_load_by_filter(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    where_clauses: Sequence[Any],
    for_update: bool = False,
) -> LifecycleRowModel:
    stmt: Any = select(_family_model(family)).where(*where_clauses)
    if for_update:
        stmt = stmt.with_for_update()
    row: Any = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(authority_family=family.value)
    return await load_authority_by_id(
        session, family=family, authority_id=cast(int, row.id), for_update=for_update
    )


async def load_capacity_pool_definition_by_business_key(
    session: AsyncSession,
    *,
    season_id: int,
    destination_factory_id: int,
    capacity_pool_code: str,
    capacity_pool_version: str,
    revision: int,
) -> Task9CapacityPoolDefinition:
    return cast(
        Task9CapacityPoolDefinition,
        await _scalar_load_by_filter(
            session,
            family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            where_clauses=(
                Task9CapacityPoolDefinition.season_id == season_id,
                Task9CapacityPoolDefinition.destination_factory_id == destination_factory_id,
                Task9CapacityPoolDefinition.capacity_pool_code == capacity_pool_code,
                Task9CapacityPoolDefinition.capacity_pool_version == capacity_pool_version,
                Task9CapacityPoolDefinition.revision == revision,
            ),
        ),
    )


async def load_daily_capacity_authority_by_business_key(
    session: AsyncSession,
    *,
    season_id: int,
    destination_factory_id: int,
    capacity_pool_code: str,
    capacity_pool_version: str,
    capacity_pool_revision: int,
    capacity_date: date,
    daily_capacity_revision: int,
) -> Task9DailyCapacityAuthority:
    return cast(
        Task9DailyCapacityAuthority,
        await _scalar_load_by_filter(
            session,
            family=AuthorityFamily.DAILY_CAPACITY,
            where_clauses=(
                Task9DailyCapacityAuthority.season_id == season_id,
                Task9DailyCapacityAuthority.destination_factory_id == destination_factory_id,
                Task9DailyCapacityAuthority.capacity_pool_code == capacity_pool_code,
                Task9DailyCapacityAuthority.capacity_pool_version == capacity_pool_version,
                Task9DailyCapacityAuthority.capacity_pool_revision == capacity_pool_revision,
                Task9DailyCapacityAuthority.capacity_date == capacity_date,
                Task9DailyCapacityAuthority.daily_capacity_revision == daily_capacity_revision,
            ),
        ),
    )


async def load_holiday_calendar_version_by_business_key(
    session: AsyncSession,
    *,
    season_id: int,
    calendar_code: str,
    lifecycle_timezone_name: str,
    calendar_version: str,
    revision: int,
) -> Task9HolidayCalendarVersion:
    return cast(
        Task9HolidayCalendarVersion,
        await _scalar_load_by_filter(
            session,
            family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            where_clauses=(
                Task9HolidayCalendarVersion.season_id == season_id,
                Task9HolidayCalendarVersion.calendar_code == calendar_code,
                Task9HolidayCalendarVersion.lifecycle_timezone_name == lifecycle_timezone_name,
                Task9HolidayCalendarVersion.calendar_version == calendar_version,
                Task9HolidayCalendarVersion.revision == revision,
            ),
        ),
    )


async def load_weather_rule_config_version_by_business_key(
    session: AsyncSession,
    *,
    rule_code: str,
    lifecycle_timezone_name: str,
    rule_version: str,
    revision: int,
) -> Task9WeatherRuleConfigVersion:
    return cast(
        Task9WeatherRuleConfigVersion,
        await _scalar_load_by_filter(
            session,
            family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            where_clauses=(
                Task9WeatherRuleConfigVersion.rule_code == rule_code,
                Task9WeatherRuleConfigVersion.lifecycle_timezone_name == lifecycle_timezone_name,
                Task9WeatherRuleConfigVersion.rule_version == rule_version,
                Task9WeatherRuleConfigVersion.revision == revision,
            ),
        ),
    )


async def load_run_parameter_package_by_business_key(
    session: AsyncSession,
    *,
    season_id: int,
    destination_factory_id: int,
    farm_scope_key: str,
    package_version: str,
    revision: int,
) -> Task9RunParameterPackage:
    return cast(
        Task9RunParameterPackage,
        await _scalar_load_by_filter(
            session,
            family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            where_clauses=(
                Task9RunParameterPackage.season_id == season_id,
                Task9RunParameterPackage.destination_factory_id == destination_factory_id,
                Task9RunParameterPackage.farm_scope_key == farm_scope_key,
                Task9RunParameterPackage.package_version == package_version,
                Task9RunParameterPackage.revision == revision,
            ),
        ),
    )


async def load_initial_inventory_snapshot_by_business_key(
    session: AsyncSession,
    *,
    season_id: int,
    destination_factory_id: int,
    opening_state_date: date,
    snapshot_version: str,
    revision: int,
) -> Task9InitialInventorySnapshot:
    return cast(
        Task9InitialInventorySnapshot,
        await _scalar_load_by_filter(
            session,
            family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
            where_clauses=(
                Task9InitialInventorySnapshot.season_id == season_id,
                Task9InitialInventorySnapshot.destination_factory_id == destination_factory_id,
                Task9InitialInventorySnapshot.opening_state_date == opening_state_date,
                Task9InitialInventorySnapshot.snapshot_version == snapshot_version,
                Task9InitialInventorySnapshot.revision == revision,
            ),
        ),
    )


async def load_mature_inventory_loss_authority_by_business_key(
    session: AsyncSession,
    *,
    season_id: int,
    destination_factory_id: int,
    state_date: date,
    capacity_pool_code: str,
    forecast_quantile: str,
    loss_version: str,
    revision: int,
) -> Task9MatureInventoryLossAuthority:
    return cast(
        Task9MatureInventoryLossAuthority,
        await _scalar_load_by_filter(
            session,
            family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            where_clauses=(
                Task9MatureInventoryLossAuthority.season_id == season_id,
                Task9MatureInventoryLossAuthority.destination_factory_id == destination_factory_id,
                Task9MatureInventoryLossAuthority.state_date == state_date,
                Task9MatureInventoryLossAuthority.capacity_pool_code == capacity_pool_code,
                Task9MatureInventoryLossAuthority.forecast_quantile == forecast_quantile,
                Task9MatureInventoryLossAuthority.loss_version == loss_version,
                Task9MatureInventoryLossAuthority.revision == revision,
            ),
        ),
    )


async def load_authority_by_persistent_identity(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
) -> LifecycleRowModel:
    if family is AuthorityFamily.CAPACITY_POOL_DEFINITION:
        parts = stable_key.split(":")
        return await load_capacity_pool_definition_by_business_key(
            session,
            season_id=int(parts[1]),
            destination_factory_id=int(parts[2]),
            capacity_pool_code=parts[3],
            capacity_pool_version=business_version,
            revision=revision,
        )
    if family is AuthorityFamily.DAILY_CAPACITY:
        parts = stable_key.split(":")
        return await load_daily_capacity_authority_by_business_key(
            session,
            season_id=int(parts[1]),
            destination_factory_id=int(parts[2]),
            capacity_pool_code=parts[3],
            capacity_pool_version=business_version,
            capacity_pool_revision=int(parts[5]),
            capacity_date=date.fromisoformat(parts[6]),
            daily_capacity_revision=revision,
        )
    if family is AuthorityFamily.HOLIDAY_CALENDAR_VERSION:
        parts = stable_key.split(":")
        return await load_holiday_calendar_version_by_business_key(
            session,
            season_id=int(parts[1]),
            calendar_code=parts[2],
            lifecycle_timezone_name=parts[3],
            calendar_version=business_version,
            revision=revision,
        )
    if family is AuthorityFamily.WEATHER_RULE_CONFIG_VERSION:
        parts = stable_key.split(":")
        return await load_weather_rule_config_version_by_business_key(
            session,
            rule_code=parts[1],
            lifecycle_timezone_name=parts[2],
            rule_version=business_version,
            revision=revision,
        )
    if family is AuthorityFamily.RUN_PARAMETER_PACKAGE:
        parts = stable_key.split(":")
        return await load_run_parameter_package_by_business_key(
            session,
            season_id=int(parts[1]),
            destination_factory_id=int(parts[2]),
            farm_scope_key=parts[3],
            package_version=business_version,
            revision=revision,
        )
    if family is AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT:
        parts = stable_key.split(":")
        return await load_initial_inventory_snapshot_by_business_key(
            session,
            season_id=int(parts[1]),
            destination_factory_id=int(parts[2]),
            opening_state_date=date.fromisoformat(parts[3]),
            snapshot_version=business_version,
            revision=revision,
        )
    parts = stable_key.split(":")
    return await load_mature_inventory_loss_authority_by_business_key(
        session,
        season_id=int(parts[1]),
        destination_factory_id=int(parts[2]),
        capacity_pool_code=parts[3],
        state_date=date.fromisoformat(parts[4]),
        forecast_quantile=parts[5],
        loss_version=business_version,
        revision=revision,
    )


async def load_authority_by_row_hash(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    row_hash: str,
) -> LifecycleRowModel:
    model = _family_model(family)
    stmt = select(model).where(_family_scalar_column(family, "row_hash") == row_hash)
    rows = list((await session.execute(stmt)).scalars())
    if not rows:
        raise AuthorityNotFoundError(authority_family=family.value, detail="row_hash not found")
    if len(rows) != 1:
        raise AuthorityHashConflictError(
            authority_family=family.value,
            authority_stable_key="row_hash_lookup",
            detail="row_hash matched multiple rows",
        )
    return await load_authority_by_id(session, family=family, authority_id=rows[0].id)


def _submitted_hash(value: object, **kwargs: object) -> str:
    recomputed = cast(str, make_authority_row_hash(value, **cast(Any, kwargs)))
    existing_hash = getattr(value, "row_hash", None)
    if existing_hash is not None and existing_hash != recomputed:
        raise AuthorityHashConflictError(
            authority_family="submitted",
            authority_stable_key="submitted",
            expected_hash=recomputed,
            actual_hash=existing_hash,
        )
    return recomputed


async def _persist_initial_events(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
    row_hash: str,
    status: AuthorityStatus,
    consumable_from_local_date: date | None,
    consumable_to_local_date: date | None,
    status_changed_at: datetime,
    source_system: str,
    source_record_key: str,
) -> None:
    events = _build_initial_lifecycle_events(
        family=family,
        stable_key=stable_key,
        business_version=business_version,
        revision=revision,
        row_hash=row_hash,
        status=status,
        consumable_from_local_date=consumable_from_local_date,
        consumable_to_local_date=consumable_to_local_date,
        status_changed_at=status_changed_at,
        source_system=source_system,
        source_record_key=source_record_key,
    )
    for event in events:
        session.add(_event_row_from_semantic(event))


async def _existing_or_none_by_business_key(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    payload: object,
    for_update: bool = False,
) -> LifecycleRowModel | None:
    if family is AuthorityFamily.CAPACITY_POOL_DEFINITION:
        row = cast(PoolBundleInput, payload).definition
        stmt = select(Task9CapacityPoolDefinition).where(
            Task9CapacityPoolDefinition.season_id == row.season_id,
            Task9CapacityPoolDefinition.destination_factory_id == row.destination_factory_id,
            Task9CapacityPoolDefinition.capacity_pool_code == row.capacity_pool_code,
            Task9CapacityPoolDefinition.capacity_pool_version == row.capacity_pool_version,
            Task9CapacityPoolDefinition.revision == row.revision,
        )
    elif family is AuthorityFamily.DAILY_CAPACITY:
        row = cast(DailyInput, payload)
        stmt = select(Task9DailyCapacityAuthority).where(
            Task9DailyCapacityAuthority.season_id == row.season_id,
            Task9DailyCapacityAuthority.destination_factory_id == row.destination_factory_id,
            Task9DailyCapacityAuthority.capacity_pool_code == row.capacity_pool_code,
            Task9DailyCapacityAuthority.capacity_pool_version == row.capacity_pool_version,
            Task9DailyCapacityAuthority.capacity_pool_revision == row.capacity_pool_revision,
            Task9DailyCapacityAuthority.capacity_date == row.capacity_date,
            Task9DailyCapacityAuthority.daily_capacity_revision == row.daily_capacity_revision,
        )
    elif family is AuthorityFamily.HOLIDAY_CALENDAR_VERSION:
        row = _holiday_header_from_bundle(cast(HolidayBundleInput, payload))
        stmt = select(Task9HolidayCalendarVersion).where(
            Task9HolidayCalendarVersion.season_id == row.season_id,
            Task9HolidayCalendarVersion.calendar_code == row.calendar_code,
            Task9HolidayCalendarVersion.lifecycle_timezone_name == row.lifecycle_timezone_name,
            Task9HolidayCalendarVersion.calendar_version == row.calendar_version,
            Task9HolidayCalendarVersion.revision == row.revision,
        )
    elif family is AuthorityFamily.WEATHER_RULE_CONFIG_VERSION:
        row = cast(WeatherInput, payload)
        stmt = select(Task9WeatherRuleConfigVersion).where(
            Task9WeatherRuleConfigVersion.rule_code == row.rule_code,
            Task9WeatherRuleConfigVersion.lifecycle_timezone_name == row.lifecycle_timezone_name,
            Task9WeatherRuleConfigVersion.rule_version == row.rule_version,
            Task9WeatherRuleConfigVersion.revision == row.revision,
        )
    elif family is AuthorityFamily.RUN_PARAMETER_PACKAGE:
        row = (
            cast(RunPackageBundleInput, payload).package
            if isinstance(payload, Task9RunParameterPackageBundleSchema)
            else cast(RunPackageInput, payload)
        )
        stmt = select(Task9RunParameterPackage).where(
            Task9RunParameterPackage.season_id == row.season_id,
            Task9RunParameterPackage.destination_factory_id == row.destination_factory_id,
            Task9RunParameterPackage.farm_scope_key == row.farm_scope_key,
            Task9RunParameterPackage.package_version == row.package_version,
            Task9RunParameterPackage.revision == row.revision,
        )
    elif family is AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT:
        row = _inventory_snapshot_from_bundle(cast(InventoryBundleInput, payload))
        stmt = select(Task9InitialInventorySnapshot).where(
            Task9InitialInventorySnapshot.season_id == row.season_id,
            Task9InitialInventorySnapshot.destination_factory_id == row.destination_factory_id,
            Task9InitialInventorySnapshot.opening_state_date == row.opening_state_date,
            Task9InitialInventorySnapshot.snapshot_version == row.snapshot_version,
            Task9InitialInventorySnapshot.revision == row.revision,
        )
    else:
        row = cast(MatureLossInput, payload)
        stmt = select(Task9MatureInventoryLossAuthority).where(
            Task9MatureInventoryLossAuthority.season_id == row.season_id,
            Task9MatureInventoryLossAuthority.destination_factory_id == row.destination_factory_id,
            Task9MatureInventoryLossAuthority.state_date == row.state_date,
            Task9MatureInventoryLossAuthority.capacity_pool_code == row.capacity_pool_code,
            Task9MatureInventoryLossAuthority.forecast_quantile == row.forecast_quantile.value,
            Task9MatureInventoryLossAuthority.loss_version == row.loss_version,
            Task9MatureInventoryLossAuthority.revision == row.revision,
        )
    if for_update:
        stmt = stmt.with_for_update()
    return cast(LifecycleRowModel | None, (await session.execute(stmt)).scalar_one_or_none())


async def _insert_capacity_pool_member_rows(
    session: AsyncSession,
    *,
    parent_id: int,
    members: Sequence[Task9CapacityPoolMemberSchema],
    parent_definition: Task9CapacityPoolDefinitionSemanticInput | Task9CapacityPoolDefinitionSchema,
) -> None:
    for member in members:
        row_hash = make_authority_row_hash(member, parent_definition=parent_definition)
        result = cast(
            Any,
            await session.execute(
                text(
                    """
                INSERT INTO task9_capacity_pool_member (
                    capacity_pool_definition_id,
                    season_id,
                    destination_factory_id,
                    farm_id,
                    subfarm_id,
                    variety_id,
                    effective_from,
                    effective_to,
                    status,
                    consumable_from_key,
                    consumable_to_key,
                    row_hash
                )
                SELECT
                    p.id,
                    p.season_id,
                    p.destination_factory_id,
                    :farm_id,
                    :subfarm_id,
                    :variety_id,
                    p.effective_from,
                    p.effective_to,
                    p.status,
                    p.consumable_from_key,
                    p.consumable_to_key,
                    :row_hash
                FROM task9_capacity_pool_definition AS p
                WHERE p.id = :parent_id
                """
                ),
                {
                    "parent_id": parent_id,
                    "farm_id": member.farm_id,
                    "subfarm_id": member.subfarm_id,
                    "variety_id": member.variety_id,
                    "row_hash": row_hash,
                },
            ),
        )
        if result.rowcount != 1:
            raise AuthorityDependencyConflictError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION.value,
                authority_stable_key=build_capacity_pool_definition_stable_key(parent_definition),
                detail="capacity pool member INSERT ... SELECT did not affect exactly one row",
            )


async def create_or_load_capacity_pool_definition(
    session: AsyncSession,
    *,
    bundle: PoolBundleInput,
) -> AuthorityCreateOrLoadResult[Task9CapacityPoolDefinition]:
    definition = bundle.definition
    stable_key = build_capacity_pool_definition_stable_key(definition)
    await _acquire_authority_lock(
        session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key=stable_key,
        business_version=definition.capacity_pool_version,
        revision=definition.revision,
    )
    submitted_hash = _submitted_hash(bundle)
    existing = await _existing_or_none_by_business_key(
        session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        payload=bundle,
        for_update=True,
    )
    if existing is not None:
        verified = await load_capacity_pool_definition_by_id(
            session,
            authority_id=existing.id,
            for_update=True,
        )
        if submitted_hash != verified.row_hash:
            raise AuthorityVersionConflictError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION.value,
                authority_stable_key=stable_key,
                existing_hash=verified.row_hash,
                submitted_hash=submitted_hash,
            )
        return AuthorityCreateOrLoadResult(
            authority=verified,
            created=False,
            persistent_identity=_persistent_identity(
                family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                stable_key=stable_key,
                business_version=definition.capacity_pool_version,
                revision=definition.revision,
            ),
            row_hash=verified.row_hash,
        )
    row = Task9CapacityPoolDefinition(
        season_id=definition.season_id,
        destination_factory_id=definition.destination_factory_id,
        capacity_pool_code=definition.capacity_pool_code,
        capacity_pool_version=definition.capacity_pool_version,
        revision=definition.revision,
        capacity_pool_grain=definition.capacity_pool_grain.value,
        capacity_input_mode=definition.capacity_input_mode.value,
        effective_from=definition.effective_from,
        effective_to=definition.effective_to,
        available_at_local_date=definition.available_at_local_date,
        consumable_from_local_date=definition.consumable_from_local_date,
        consumable_to_local_date=definition.consumable_to_local_date,
        status=definition.status.value,
        status_changed_at=definition.status_changed_at,
        source_system=definition.source_system,
        source_record_key=definition.source_record_key,
        source_version=definition.source_version,
        row_hash=submitted_hash,
        superseded_by_id=definition.superseded_by_id,
    )
    session.add(row)
    await session.flush()
    await _insert_capacity_pool_member_rows(
        session,
        parent_id=row.id,
        members=list(bundle.members),
        parent_definition=definition,
    )
    await _persist_initial_events(
        session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key=stable_key,
        business_version=definition.capacity_pool_version,
        revision=definition.revision,
        row_hash=submitted_hash,
        status=definition.status,
        consumable_from_local_date=definition.consumable_from_local_date,
        consumable_to_local_date=definition.consumable_to_local_date,
        status_changed_at=definition.status_changed_at,
        source_system=definition.source_system,
        source_record_key=definition.source_record_key,
    )
    await session.flush()
    verified = await load_capacity_pool_definition_by_id(
        session, authority_id=row.id, for_update=True
    )
    return AuthorityCreateOrLoadResult(
        authority=verified,
        created=True,
        persistent_identity=_persistent_identity(
            family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            stable_key=stable_key,
            business_version=definition.capacity_pool_version,
            revision=definition.revision,
        ),
        row_hash=verified.row_hash,
    )


def _create_or_load_existing_result(
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
    existing_row: LifecycleRowModel,
    submitted_hash: str,
) -> AuthorityCreateOrLoadResult[LifecycleRowModel]:
    if submitted_hash != existing_row.row_hash:
        raise AuthorityVersionConflictError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            existing_hash=existing_row.row_hash,
            submitted_hash=submitted_hash,
        )
    return AuthorityCreateOrLoadResult(
        authority=existing_row,
        created=False,
        persistent_identity=_persistent_identity(
            family=family,
            stable_key=stable_key,
            business_version=business_version,
            revision=revision,
        ),
        row_hash=existing_row.row_hash,
    )


async def _resolve_parent_pool_id(
    session: AsyncSession,
    *,
    season_id: int,
    destination_factory_id: int,
    capacity_pool_code: str,
    capacity_pool_version: str,
    capacity_pool_revision: int,
) -> int:
    row = await load_capacity_pool_definition_by_business_key(
        session,
        season_id=season_id,
        destination_factory_id=destination_factory_id,
        capacity_pool_code=capacity_pool_code,
        capacity_pool_version=capacity_pool_version,
        revision=capacity_pool_revision,
    )
    return row.id


async def create_or_load_daily_capacity_authority(
    session: AsyncSession,
    *,
    authority: DailyInput,
) -> AuthorityCreateOrLoadResult[Task9DailyCapacityAuthority]:
    stable_key = build_daily_capacity_stable_key(authority)
    await _acquire_authority_lock(
        session,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=stable_key,
        business_version=authority.capacity_pool_version,
        revision=authority.daily_capacity_revision,
    )
    submitted_hash = _submitted_hash(authority)
    existing = await _existing_or_none_by_business_key(
        session, family=AuthorityFamily.DAILY_CAPACITY, payload=authority, for_update=True
    )
    if existing is not None:
        verified = await load_daily_capacity_authority_by_id(
            session, authority_id=existing.id, for_update=True
        )
        return cast(
            AuthorityCreateOrLoadResult[Task9DailyCapacityAuthority],
            _create_or_load_existing_result(
                family=AuthorityFamily.DAILY_CAPACITY,
                stable_key=stable_key,
                business_version=authority.capacity_pool_version,
                revision=authority.daily_capacity_revision,
                existing_row=verified,
                submitted_hash=submitted_hash,
            ),
        )
    parent_id = await _resolve_parent_pool_id(
        session,
        season_id=authority.season_id,
        destination_factory_id=authority.destination_factory_id,
        capacity_pool_code=authority.capacity_pool_code,
        capacity_pool_version=authority.capacity_pool_version,
        capacity_pool_revision=authority.capacity_pool_revision,
    )
    row = Task9DailyCapacityAuthority(
        capacity_pool_definition_id=parent_id,
        capacity_date=authority.capacity_date,
        daily_capacity_revision=authority.daily_capacity_revision,
        planned_picker_count=authority.planned_picker_count,
        kg_per_person_per_day=authority.kg_per_person_per_day,
        direct_nominal_capacity_kg_per_day=authority.direct_nominal_capacity_kg_per_day,
        labor_availability_ratio=authority.labor_availability_ratio,
        operational_efficiency_ratio=authority.operational_efficiency_ratio,
        available_at_local_date=authority.available_at_local_date,
        consumable_from_local_date=authority.consumable_from_local_date,
        consumable_to_local_date=authority.consumable_to_local_date,
        status=authority.status.value,
        status_changed_at=authority.status_changed_at,
        superseded_by_id=authority.superseded_by_id,
        source_system=authority.source_system,
        source_record_key=authority.source_record_key,
        source_version=authority.source_version,
        row_hash=submitted_hash,
    )
    session.add(row)
    await session.flush()
    await _persist_initial_events(
        session,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=stable_key,
        business_version=authority.capacity_pool_version,
        revision=authority.daily_capacity_revision,
        row_hash=submitted_hash,
        status=authority.status,
        consumable_from_local_date=authority.consumable_from_local_date,
        consumable_to_local_date=authority.consumable_to_local_date,
        status_changed_at=authority.status_changed_at,
        source_system=authority.source_system,
        source_record_key=authority.source_record_key,
    )
    await session.flush()
    verified = await load_daily_capacity_authority_by_id(
        session, authority_id=row.id, for_update=True
    )
    return AuthorityCreateOrLoadResult(
        authority=verified,
        created=True,
        persistent_identity=_persistent_identity(
            family=AuthorityFamily.DAILY_CAPACITY,
            stable_key=stable_key,
            business_version=authority.capacity_pool_version,
            revision=authority.daily_capacity_revision,
        ),
        row_hash=verified.row_hash,
    )


async def create_or_load_holiday_calendar_version(
    session: AsyncSession,
    *,
    bundle: HolidayBundleInput,
) -> AuthorityCreateOrLoadResult[Task9HolidayCalendarVersion]:
    header = _holiday_header_from_bundle(bundle)
    stable_key = build_holiday_calendar_stable_key(header)
    await _acquire_authority_lock(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=stable_key,
        business_version=header.calendar_version,
        revision=header.revision,
    )
    submitted_hash = _submitted_hash(bundle)
    existing = await _existing_or_none_by_business_key(
        session, family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION, payload=bundle, for_update=True
    )
    if existing is not None:
        verified = await load_holiday_calendar_version_by_id(
            session, authority_id=existing.id, for_update=True
        )
        return cast(
            AuthorityCreateOrLoadResult[Task9HolidayCalendarVersion],
            _create_or_load_existing_result(
                family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                stable_key=stable_key,
                business_version=header.calendar_version,
                revision=header.revision,
                existing_row=verified,
                submitted_hash=submitted_hash,
            ),
        )
    row = Task9HolidayCalendarVersion(
        season_id=header.season_id,
        calendar_code=header.calendar_code,
        lifecycle_timezone_name=header.lifecycle_timezone_name,
        calendar_version=header.calendar_version,
        revision=header.revision,
        region_scope=header.region_scope,
        calendar_hash=header.calendar_hash,
        available_at_local_date=header.available_at_local_date,
        consumable_from_local_date=header.consumable_from_local_date,
        consumable_to_local_date=header.consumable_to_local_date,
        status=header.status.value,
        status_changed_at=header.status_changed_at,
        superseded_by_id=header.superseded_by_id,
        source_system=header.source_system,
        source_record_key=header.source_record_key,
        source_version=header.source_version,
        row_hash=submitted_hash,
    )
    session.add(row)
    await session.flush()
    for item in bundle.dates:
        session.add(
            Task9HolidayCalendarDate(
                holiday_calendar_version_id=row.id,
                holiday_date=item.holiday_date,
                holiday_code=item.holiday_code,
                holiday_name=item.holiday_name,
            )
        )
    await _persist_initial_events(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=stable_key,
        business_version=header.calendar_version,
        revision=header.revision,
        row_hash=submitted_hash,
        status=header.status,
        consumable_from_local_date=header.consumable_from_local_date,
        consumable_to_local_date=header.consumable_to_local_date,
        status_changed_at=header.status_changed_at,
        source_system=header.source_system,
        source_record_key=header.source_record_key,
    )
    await session.flush()
    verified = await load_holiday_calendar_version_by_id(
        session, authority_id=row.id, for_update=True
    )
    return AuthorityCreateOrLoadResult(
        authority=verified,
        created=True,
        persistent_identity=_persistent_identity(
            family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            stable_key=stable_key,
            business_version=header.calendar_version,
            revision=header.revision,
        ),
        row_hash=verified.row_hash,
    )


async def create_or_load_weather_rule_config_version(
    session: AsyncSession,
    *,
    authority: WeatherInput,
) -> AuthorityCreateOrLoadResult[Task9WeatherRuleConfigVersion]:
    stable_key = build_weather_rule_stable_key(authority)
    await _acquire_authority_lock(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=stable_key,
        business_version=authority.rule_version,
        revision=authority.revision,
    )
    submitted_hash = _submitted_hash(authority)
    existing = await _existing_or_none_by_business_key(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        payload=authority,
        for_update=True,
    )
    if existing is not None:
        verified = await load_weather_rule_config_version_by_id(
            session, authority_id=existing.id, for_update=True
        )
        return cast(
            AuthorityCreateOrLoadResult[Task9WeatherRuleConfigVersion],
            _create_or_load_existing_result(
                family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                stable_key=stable_key,
                business_version=authority.rule_version,
                revision=authority.revision,
                existing_row=verified,
                submitted_hash=submitted_hash,
            ),
        )
    row = Task9WeatherRuleConfigVersion(
        rule_code=authority.rule_code,
        lifecycle_timezone_name=authority.lifecycle_timezone_name,
        rule_version=authority.rule_version,
        revision=authority.revision,
        combination_method=authority.combination_method.value,
        minimum_ratio=authority.minimum_ratio,
        maximum_ratio=authority.maximum_ratio,
        required_feature_ids=[*authority.required_feature_ids],
        feature_rules_json=[item.model_dump(mode="json") for item in authority.feature_rules],
        missing_feature_policy=authority.missing_feature_policy,
        config_hash=authority.config_hash,
        available_at_local_date=authority.available_at_local_date,
        consumable_from_local_date=authority.consumable_from_local_date,
        consumable_to_local_date=authority.consumable_to_local_date,
        effective_from=authority.effective_from,
        effective_to=authority.effective_to,
        status=authority.status.value,
        status_changed_at=authority.status_changed_at,
        superseded_by_id=authority.superseded_by_id,
        source_system=authority.source_system,
        source_record_key=authority.source_record_key,
        source_version=authority.source_version,
        row_hash=submitted_hash,
    )
    session.add(row)
    await session.flush()
    await _persist_initial_events(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=stable_key,
        business_version=authority.rule_version,
        revision=authority.revision,
        row_hash=submitted_hash,
        status=authority.status,
        consumable_from_local_date=authority.consumable_from_local_date,
        consumable_to_local_date=authority.consumable_to_local_date,
        status_changed_at=authority.status_changed_at,
        source_system=authority.source_system,
        source_record_key=authority.source_record_key,
    )
    await session.flush()
    verified = await load_weather_rule_config_version_by_id(
        session, authority_id=row.id, for_update=True
    )
    return AuthorityCreateOrLoadResult(
        authority=verified,
        created=True,
        persistent_identity=_persistent_identity(
            family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            stable_key=stable_key,
            business_version=authority.rule_version,
            revision=authority.revision,
        ),
        row_hash=verified.row_hash,
    )


async def _ensure_dependency_status(
    *,
    package_stable_key: str,
    holiday_row: Task9HolidayCalendarVersion,
    weather_row: Task9WeatherRuleConfigVersion,
    allow_draft: bool,
) -> None:
    if allow_draft:
        allowed = {AuthorityStatus.DRAFT.value, AuthorityStatus.ACTIVE.value}
    else:
        allowed = {AuthorityStatus.ACTIVE.value}
    if holiday_row.status not in allowed or weather_row.status not in allowed:
        raise _raise_dependency_conflict(
            package_stable_key=package_stable_key,
            detail="run package dependencies are not in an allowed lifecycle state",
        )


def _assert_verified_package_dependency_match(
    *,
    package: RunPackageInput,
    package_stable_key: str,
    submitted_holiday: HolidayBundleInput,
    submitted_weather: WeatherInput,
    verified_holiday_row: Task9HolidayCalendarVersion,
    verified_weather_row: Task9WeatherRuleConfigVersion,
    verified_holiday_bundle: Task9HolidayCalendarBundleSchema,
    verified_weather_schema: Task9WeatherRuleConfigVersionSchema,
) -> None:
    submitted_holiday_hash = _submitted_hash(submitted_holiday)
    submitted_weather_hash = _submitted_hash(submitted_weather)
    if submitted_holiday_hash != verified_holiday_row.row_hash:
        raise _raise_dependency_conflict(
            package_stable_key=package_stable_key,
            detail="submitted holiday dependency does not match exact persisted authority content",
        )
    if submitted_weather_hash != verified_weather_row.row_hash:
        raise _raise_dependency_conflict(
            package_stable_key=package_stable_key,
            detail="submitted weather dependency does not match exact persisted authority content",
        )
    if package.season_id != verified_holiday_bundle.season_id:
        raise _raise_dependency_conflict(
            package_stable_key=package_stable_key,
            detail="run package season does not match exact persisted holiday dependency",
        )
    if not (
        package.destination_factory_timezone
        == verified_holiday_bundle.lifecycle_timezone_name
        == verified_weather_schema.lifecycle_timezone_name
    ):
        raise _raise_dependency_conflict(
            package_stable_key=package_stable_key,
            detail="run package timezone does not match exact persisted dependencies",
        )


async def _create_run_package_locked(
    session: AsyncSession,
    *,
    package: RunPackageInput,
    holiday_row: Task9HolidayCalendarVersion,
    holiday_bundle: Task9HolidayCalendarBundleSchema,
    weather_row: Task9WeatherRuleConfigVersion,
    weather_schema: Task9WeatherRuleConfigVersionSchema,
    allow_draft_dependencies: bool,
) -> Task9RunParameterPackage:
    stable_key = build_run_parameter_package_stable_key(package)
    if package.season_id != holiday_bundle.season_id:
        raise _raise_dependency_conflict(
            package_stable_key=stable_key,
            detail="run package season does not match dependency season",
        )
    if not (
        package.destination_factory_timezone
        == holiday_bundle.lifecycle_timezone_name
        == weather_schema.lifecycle_timezone_name
    ):
        raise _raise_dependency_conflict(
            package_stable_key=stable_key,
            detail="run package timezone does not match dependency timezones",
        )
    await _ensure_dependency_status(
        package_stable_key=stable_key,
        holiday_row=holiday_row,
        weather_row=weather_row,
        allow_draft=allow_draft_dependencies,
    )
    row_hash = make_authority_row_hash(
        package,
        holiday_calendar=holiday_bundle,
        weather_rule=weather_schema,
    )
    row = Task9RunParameterPackage(
        season_id=package.season_id,
        destination_factory_id=package.destination_factory_id,
        farm_scope_key=package.farm_scope_key,
        package_version=package.package_version,
        revision=package.revision,
        farm_timezone=package.farm_timezone,
        destination_factory_timezone=package.destination_factory_timezone,
        harvest_bucket_anchor_local_time=package.harvest_bucket_anchor_local_time,
        harvest_to_arrival_lag_days=package.harvest_to_arrival_lag_days,
        holiday_calendar_version_id=holiday_row.id,
        weather_rule_config_version_id=weather_row.id,
        available_at_local_date=package.available_at_local_date,
        consumable_from_local_date=package.consumable_from_local_date,
        consumable_to_local_date=package.consumable_to_local_date,
        effective_from=package.effective_from,
        effective_to=package.effective_to,
        status=package.status.value,
        status_changed_at=package.status_changed_at,
        superseded_by_id=package.superseded_by_id,
        source_system=package.source_system,
        source_record_key=package.source_record_key,
        source_version=package.source_version,
        row_hash=row_hash,
    )
    session.add(row)
    await session.flush()
    await _persist_initial_events(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=stable_key,
        business_version=package.package_version,
        revision=package.revision,
        row_hash=row_hash,
        status=package.status,
        consumable_from_local_date=package.consumable_from_local_date,
        consumable_to_local_date=package.consumable_to_local_date,
        status_changed_at=package.status_changed_at,
        source_system=package.source_system,
        source_record_key=package.source_record_key,
    )
    await session.flush()
    return row


async def create_or_load_run_parameter_package(
    session: AsyncSession,
    *,
    bundle: RunPackageBundleInput,
) -> AuthorityCreateOrLoadResult[Task9RunParameterPackage]:
    package = cast(RunPackageInput, bundle.package)
    stable_key = build_run_parameter_package_stable_key(package)
    await _acquire_authority_lock(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=stable_key,
        business_version=package.package_version,
        revision=package.revision,
    )
    submitted_hash = _submitted_hash(
        package,
        holiday_calendar=bundle.holiday_calendar,
        weather_rule=bundle.weather_rule,
    )
    existing = await _existing_or_none_by_business_key(
        session, family=AuthorityFamily.RUN_PARAMETER_PACKAGE, payload=bundle, for_update=True
    )
    if existing is not None:
        verified = await load_run_parameter_package_by_id(
            session, authority_id=existing.id, for_update=True
        )
        return cast(
            AuthorityCreateOrLoadResult[Task9RunParameterPackage],
            _create_or_load_existing_result(
                family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                stable_key=stable_key,
                business_version=package.package_version,
                revision=package.revision,
                existing_row=verified,
                submitted_hash=submitted_hash,
            ),
        )
    holiday_row = await load_holiday_calendar_version_by_business_key(
        session,
        season_id=bundle.holiday_calendar.season_id,
        calendar_code=bundle.holiday_calendar.calendar_code,
        lifecycle_timezone_name=bundle.holiday_calendar.lifecycle_timezone_name,
        calendar_version=bundle.holiday_calendar.calendar_version,
        revision=bundle.holiday_calendar.revision,
    )
    weather_row = await load_weather_rule_config_version_by_business_key(
        session,
        rule_code=bundle.weather_rule.rule_code,
        lifecycle_timezone_name=bundle.weather_rule.lifecycle_timezone_name,
        rule_version=bundle.weather_rule.rule_version,
        revision=bundle.weather_rule.revision,
    )
    holiday_row, holiday_bundle = await _load_verified_holiday_dependency_by_id(
        session, authority_id=holiday_row.id, for_update=True
    )
    weather_row, weather_schema = await _load_verified_weather_dependency_by_id(
        session, authority_id=weather_row.id, for_update=True
    )
    _assert_verified_package_dependency_match(
        package=package,
        package_stable_key=stable_key,
        submitted_holiday=bundle.holiday_calendar,
        submitted_weather=bundle.weather_rule,
        verified_holiday_row=holiday_row,
        verified_weather_row=weather_row,
        verified_holiday_bundle=holiday_bundle,
        verified_weather_schema=weather_schema,
    )
    row = await _create_run_package_locked(
        session,
        package=package,
        holiday_row=holiday_row,
        holiday_bundle=holiday_bundle,
        weather_row=weather_row,
        weather_schema=weather_schema,
        allow_draft_dependencies=False,
    )
    verified = await load_run_parameter_package_by_id(session, authority_id=row.id, for_update=True)
    return AuthorityCreateOrLoadResult(
        authority=verified,
        created=True,
        persistent_identity=_persistent_identity(
            family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            stable_key=stable_key,
            business_version=package.package_version,
            revision=package.revision,
        ),
        row_hash=verified.row_hash,
    )


async def create_or_load_initial_inventory_snapshot(
    session: AsyncSession,
    *,
    bundle: InventoryBundleInput,
) -> AuthorityCreateOrLoadResult[Task9InitialInventorySnapshot]:
    snapshot = _inventory_snapshot_from_bundle(bundle)
    stable_key = build_initial_inventory_stable_key(snapshot)
    await _acquire_authority_lock(
        session,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        stable_key=stable_key,
        business_version=snapshot.snapshot_version,
        revision=snapshot.revision,
    )
    submitted_hash = _submitted_hash(bundle)
    existing = await _existing_or_none_by_business_key(
        session, family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT, payload=bundle, for_update=True
    )
    if existing is not None:
        verified = await load_initial_inventory_snapshot_by_id(
            session, authority_id=existing.id, for_update=True
        )
        return cast(
            AuthorityCreateOrLoadResult[Task9InitialInventorySnapshot],
            _create_or_load_existing_result(
                family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
                stable_key=stable_key,
                business_version=snapshot.snapshot_version,
                revision=snapshot.revision,
                existing_row=verified,
                submitted_hash=submitted_hash,
            ),
        )
    row = Task9InitialInventorySnapshot(
        season_id=snapshot.season_id,
        destination_factory_id=snapshot.destination_factory_id,
        opening_state_date=snapshot.opening_state_date,
        snapshot_version=snapshot.snapshot_version,
        revision=snapshot.revision,
        initial_opening_mature_inventory_kg=snapshot.initial_opening_mature_inventory_kg,
        available_at_local_date=snapshot.available_at_local_date,
        consumable_from_local_date=snapshot.consumable_from_local_date,
        consumable_to_local_date=snapshot.consumable_to_local_date,
        status=snapshot.status.value,
        status_changed_at=snapshot.status_changed_at,
        superseded_by_id=snapshot.superseded_by_id,
        source_system=snapshot.source_system,
        source_record_key=snapshot.source_record_key,
        source_version=snapshot.source_version,
        row_hash=submitted_hash,
    )
    session.add(row)
    await session.flush()
    for cohort in bundle.cohorts:
        session.add(
            Task9InitialInventoryCohort(
                initial_inventory_snapshot_id=row.id,
                stable_cohort_key=cohort.stable_cohort_key,
                forecast_quantile=cohort.forecast_quantile.value,
                cohort_date=cohort.cohort_date,
                farm_id=cohort.farm_id,
                subfarm_id=cohort.subfarm_id,
                variety_id=cohort.variety_id,
                remaining_quantity_kg=cohort.remaining_quantity_kg,
                row_hash=make_authority_row_hash(cohort, parent_snapshot=snapshot),
            )
        )
    await _persist_initial_events(
        session,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        stable_key=stable_key,
        business_version=snapshot.snapshot_version,
        revision=snapshot.revision,
        row_hash=submitted_hash,
        status=snapshot.status,
        consumable_from_local_date=snapshot.consumable_from_local_date,
        consumable_to_local_date=snapshot.consumable_to_local_date,
        status_changed_at=snapshot.status_changed_at,
        source_system=snapshot.source_system,
        source_record_key=snapshot.source_record_key,
    )
    await session.flush()
    verified = await load_initial_inventory_snapshot_by_id(
        session, authority_id=row.id, for_update=True
    )
    return AuthorityCreateOrLoadResult(
        authority=verified,
        created=True,
        persistent_identity=_persistent_identity(
            family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
            stable_key=stable_key,
            business_version=snapshot.snapshot_version,
            revision=snapshot.revision,
        ),
        row_hash=verified.row_hash,
    )


async def create_or_load_mature_inventory_loss_authority(
    session: AsyncSession,
    *,
    authority: MatureLossInput,
) -> AuthorityCreateOrLoadResult[Task9MatureInventoryLossAuthority]:
    stable_key = build_mature_inventory_loss_stable_key(authority)
    await _acquire_authority_lock(
        session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        stable_key=stable_key,
        business_version=authority.loss_version,
        revision=authority.revision,
    )
    submitted_hash = _submitted_hash(authority)
    existing = await _existing_or_none_by_business_key(
        session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        payload=authority,
        for_update=True,
    )
    if existing is not None:
        verified = await load_mature_inventory_loss_authority_by_id(
            session, authority_id=existing.id, for_update=True
        )
        return cast(
            AuthorityCreateOrLoadResult[Task9MatureInventoryLossAuthority],
            _create_or_load_existing_result(
                family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                stable_key=stable_key,
                business_version=authority.loss_version,
                revision=authority.revision,
                existing_row=verified,
                submitted_hash=submitted_hash,
            ),
        )
    row = Task9MatureInventoryLossAuthority(
        season_id=authority.season_id,
        destination_factory_id=authority.destination_factory_id,
        state_date=authority.state_date,
        capacity_pool_code=authority.capacity_pool_code,
        forecast_quantile=authority.forecast_quantile.value,
        loss_version=authority.loss_version,
        revision=authority.revision,
        mature_inventory_loss_quantity_kg=authority.mature_inventory_loss_quantity_kg,
        available_at_local_date=authority.available_at_local_date,
        consumable_from_local_date=authority.consumable_from_local_date,
        consumable_to_local_date=authority.consumable_to_local_date,
        status=authority.status.value,
        status_changed_at=authority.status_changed_at,
        superseded_by_id=authority.superseded_by_id,
        source_system=authority.source_system,
        source_record_key=authority.source_record_key,
        source_version=authority.source_version,
        row_hash=submitted_hash,
    )
    session.add(row)
    await session.flush()
    await _persist_initial_events(
        session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        stable_key=stable_key,
        business_version=authority.loss_version,
        revision=authority.revision,
        row_hash=submitted_hash,
        status=authority.status,
        consumable_from_local_date=authority.consumable_from_local_date,
        consumable_to_local_date=authority.consumable_to_local_date,
        status_changed_at=authority.status_changed_at,
        source_system=authority.source_system,
        source_record_key=authority.source_record_key,
    )
    await session.flush()
    verified = await load_mature_inventory_loss_authority_by_id(
        session, authority_id=row.id, for_update=True
    )
    return AuthorityCreateOrLoadResult(
        authority=verified,
        created=True,
        persistent_identity=_persistent_identity(
            family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            stable_key=stable_key,
            business_version=authority.loss_version,
            revision=authority.revision,
        ),
        row_hash=verified.row_hash,
    )


async def activate_authority(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    authority_id: int,
    activation_boundary: date,
) -> LifecycleRowModel:
    row = await load_authority_by_id(
        session, family=family, authority_id=authority_id, for_update=True
    )
    stable_key, business_version, revision = _row_identity(family, row)
    if _row_status(row) is not AuthorityStatus.DRAFT:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="activation requires current draft row",
        )
    if row.consumable_from_local_date is not None or row.consumable_to_local_date is not None:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="draft row must not already expose consumability",
        )
    if activation_boundary < row.available_at_local_date:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="activation boundary must be >= available_at_local_date",
        )
    events = await _load_lifecycle_events(
        session,
        family=family,
        stable_key=stable_key,
        business_version=business_version,
        revision=revision,
    )
    sequence = len(events) + 1
    row.status = AuthorityStatus.ACTIVE.value
    row.consumable_from_local_date = activation_boundary
    row.consumable_to_local_date = None
    row.status_changed_at = _now()
    session.add(
        _event_row_from_semantic(
            Task9LifecycleEventSemanticInput(
                authority_family=family,
                authority_stable_key=stable_key,
                authority_business_version=business_version,
                authority_revision=revision,
                business_row_hash=row.row_hash,
                transition_sequence=sequence,
                old_status=AuthorityStatus.DRAFT,
                new_status=AuthorityStatus.ACTIVE,
                old_consumable_from_local_date=None,
                old_consumable_to_local_date=None,
                new_consumable_from_local_date=activation_boundary,
                new_consumable_to_local_date=None,
                superseded_by_authority_stable_key=None,
                superseded_by_authority_business_version=None,
                superseded_by_authority_revision=None,
                transitioned_at=row.status_changed_at,
                source_system=row.source_system,
                source_record_key=row.source_record_key,
            )
        )
    )
    try:
        await session.flush()
    except SAIntegrityError as exc:
        raise _classify_boundary_integrity_error(
            exc=exc, authority_family=family, authority_stable_key=stable_key
        ) from exc
    return await load_authority_by_id(
        session, family=family, authority_id=authority_id, for_update=True
    )


async def retire_authority(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    authority_id: int,
    retirement_boundary: date,
) -> LifecycleRowModel:
    row = await load_authority_by_id(
        session, family=family, authority_id=authority_id, for_update=True
    )
    stable_key, business_version, revision = _row_identity(family, row)
    if _row_status(row) is not AuthorityStatus.ACTIVE:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="retirement requires current active row",
        )
    if row.consumable_from_local_date is None or row.consumable_to_local_date is not None:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="active row must expose open consumability interval",
        )
    if retirement_boundary <= row.consumable_from_local_date:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="retirement boundary must be > current consumable_from",
        )
    events = await _load_lifecycle_events(
        session,
        family=family,
        stable_key=stable_key,
        business_version=business_version,
        revision=revision,
    )
    sequence = len(events) + 1
    old_from = row.consumable_from_local_date
    row.status = AuthorityStatus.RETIRED.value
    row.consumable_to_local_date = retirement_boundary
    row.status_changed_at = _now()
    session.add(
        _event_row_from_semantic(
            Task9LifecycleEventSemanticInput(
                authority_family=family,
                authority_stable_key=stable_key,
                authority_business_version=business_version,
                authority_revision=revision,
                business_row_hash=row.row_hash,
                transition_sequence=sequence,
                old_status=AuthorityStatus.ACTIVE,
                new_status=AuthorityStatus.RETIRED,
                old_consumable_from_local_date=old_from,
                old_consumable_to_local_date=None,
                new_consumable_from_local_date=old_from,
                new_consumable_to_local_date=retirement_boundary,
                superseded_by_authority_stable_key=None,
                superseded_by_authority_business_version=None,
                superseded_by_authority_revision=None,
                transitioned_at=row.status_changed_at,
                source_system=row.source_system,
                source_record_key=row.source_record_key,
            )
        )
    )
    try:
        await session.flush()
    except SAIntegrityError as exc:
        raise _classify_boundary_integrity_error(
            exc=exc, authority_family=family, authority_stable_key=stable_key
        ) from exc
    return await load_authority_by_id(
        session, family=family, authority_id=authority_id, for_update=True
    )


async def _supersede_authority_locked(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    old_row: LifecycleRowModel,
    new_row: LifecycleRowModel,
    replacement_boundary: date,
) -> None:
    stable_key, business_version, revision = _row_identity(family, old_row)
    new_stable_key, new_business_version, new_revision = _row_identity(family, new_row)
    if _row_status(old_row) is not AuthorityStatus.ACTIVE:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="supersession requires current active row",
        )
    if old_row.consumable_from_local_date is None or old_row.consumable_to_local_date is not None:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="supersession requires open old consumability interval",
        )
    if replacement_boundary <= cast(date, old_row.consumable_from_local_date):
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=stable_key,
            detail="replacement boundary must be > old consumable_from",
        )
    if _row_status(new_row) is not AuthorityStatus.DRAFT:
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=new_stable_key,
            detail="replacement row must be draft",
        )
    if (
        new_row.consumable_from_local_date is not None
        or new_row.consumable_to_local_date is not None
    ):
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=family.value,
            authority_stable_key=new_stable_key,
            detail="replacement draft must not expose consumability",
        )
    old_events = await _load_lifecycle_events(
        session,
        family=family,
        stable_key=stable_key,
        business_version=business_version,
        revision=revision,
    )
    old_sequence = len(old_events) + 1
    old_from = cast(date, old_row.consumable_from_local_date)
    old_row.status = AuthorityStatus.SUPERSEDED.value
    old_row.superseded_by_id = new_row.id
    old_row.consumable_to_local_date = replacement_boundary
    old_row.status_changed_at = _now()
    session.add(
        _event_row_from_semantic(
            Task9LifecycleEventSemanticInput(
                authority_family=family,
                authority_stable_key=stable_key,
                authority_business_version=business_version,
                authority_revision=revision,
                business_row_hash=old_row.row_hash,
                transition_sequence=old_sequence,
                old_status=AuthorityStatus.ACTIVE,
                new_status=AuthorityStatus.SUPERSEDED,
                old_consumable_from_local_date=old_from,
                old_consumable_to_local_date=None,
                new_consumable_from_local_date=old_from,
                new_consumable_to_local_date=replacement_boundary,
                superseded_by_authority_stable_key=new_stable_key,
                superseded_by_authority_business_version=new_business_version,
                superseded_by_authority_revision=new_revision,
                transitioned_at=old_row.status_changed_at,
                source_system=old_row.source_system,
                source_record_key=old_row.source_record_key,
            )
        )
    )


async def replace_authority(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    old_authority_id: int,
    new_authority_id: int,
    replacement_boundary: date,
) -> tuple[LifecycleRowModel, LifecycleRowModel]:
    old_row = await load_authority_by_id(
        session, family=family, authority_id=old_authority_id, for_update=True
    )
    new_row = await load_authority_by_id(
        session, family=family, authority_id=new_authority_id, for_update=True
    )
    if family in {
        AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
    }:
        active_reference = (
            await session.execute(
                select(Task9RunParameterPackage.id).where(
                    Task9RunParameterPackage.status == AuthorityStatus.ACTIVE.value,
                    (
                        Task9RunParameterPackage.holiday_calendar_version_id == old_authority_id
                        if family is AuthorityFamily.HOLIDAY_CALENDAR_VERSION
                        else Task9RunParameterPackage.weather_rule_config_version_id
                        == old_authority_id
                    ),
                )
            )
        ).scalar_one_or_none()
        if active_reference is not None:
            raise AuthorityDependencyConflictError(
                authority_family=family.value,
                authority_stable_key=_row_identity(family, old_row)[0],
                detail=(
                    "standalone dependency supersession is blocked while an active "
                    "run package references it"
                ),
            )
    await _supersede_authority_locked(
        session,
        family=family,
        old_row=old_row,
        new_row=new_row,
        replacement_boundary=replacement_boundary,
    )
    await activate_authority(
        session,
        family=family,
        authority_id=new_authority_id,
        activation_boundary=replacement_boundary,
    )
    try:
        await session.flush()
    except SAIntegrityError as exc:
        stable_key, _version, _revision = _row_identity(family, old_row)
        raise _classify_boundary_integrity_error(
            exc=exc, authority_family=family, authority_stable_key=stable_key
        ) from exc
    return (
        await load_authority_by_id(
            session, family=family, authority_id=old_authority_id, for_update=True
        ),
        await load_authority_by_id(
            session, family=family, authority_id=new_authority_id, for_update=True
        ),
    )


async def replace_run_package_with_dependencies(
    session: AsyncSession,
    *,
    old_package_id: int,
    new_holiday: HolidayBundleInput,
    new_weather: WeatherInput,
    new_package: RunPackageInput,
    replacement_boundary: date,
) -> RunPackageReplacementResult:
    old_package_row, old_package_bundle = await _load_verified_run_package_by_id(
        session, authority_id=old_package_id, for_update=True
    )
    old_holiday_row, _old_holiday_bundle = await _load_verified_holiday_dependency_by_id(
        session, authority_id=old_package_row.holiday_calendar_version_id, for_update=True
    )
    old_weather_row, _old_weather_schema = await _load_verified_weather_dependency_by_id(
        session, authority_id=old_package_row.weather_rule_config_version_id, for_update=True
    )
    if not (
        replacement_boundary > cast(date, old_package_row.consumable_from_local_date)
        and replacement_boundary > cast(date, old_holiday_row.consumable_from_local_date)
        and replacement_boundary > cast(date, old_weather_row.consumable_from_local_date)
    ):
        raise AuthorityConsumabilityIntervalInvalidError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE.value,
            authority_stable_key=build_run_parameter_package_stable_key(old_package_bundle.package),
            detail=(
                "replacement boundary must be > current active consumable_from "
                "for package and dependencies"
            ),
        )
    new_holiday_result = await create_or_load_holiday_calendar_version(session, bundle=new_holiday)
    new_weather_result = await create_or_load_weather_rule_config_version(
        session, authority=new_weather
    )
    new_holiday_row, new_holiday_bundle = await _load_verified_holiday_dependency_by_id(
        session, authority_id=new_holiday_result.authority.id, for_update=True
    )
    new_weather_row, new_weather_schema = await _load_verified_weather_dependency_by_id(
        session, authority_id=new_weather_result.authority.id, for_update=True
    )
    new_package_row = await _create_run_package_locked(
        session,
        package=new_package,
        holiday_row=new_holiday_row,
        holiday_bundle=new_holiday_bundle,
        weather_row=new_weather_row,
        weather_schema=new_weather_schema,
        allow_draft_dependencies=True,
    )
    await _supersede_authority_locked(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        old_row=old_package_row,
        new_row=new_package_row,
        replacement_boundary=replacement_boundary,
    )
    await _supersede_authority_locked(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        old_row=old_holiday_row,
        new_row=new_holiday_row,
        replacement_boundary=replacement_boundary,
    )
    await _supersede_authority_locked(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        old_row=old_weather_row,
        new_row=new_weather_row,
        replacement_boundary=replacement_boundary,
    )
    try:
        await session.flush()
        await activate_authority(
            session,
            family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            authority_id=new_holiday_row.id,
            activation_boundary=replacement_boundary,
        )
        await activate_authority(
            session,
            family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            authority_id=new_weather_row.id,
            activation_boundary=replacement_boundary,
        )
        await activate_authority(
            session,
            family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_id=new_package_row.id,
            activation_boundary=replacement_boundary,
        )
    except SAIntegrityError as exc:
        raise _classify_boundary_integrity_error(
            exc=exc,
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=build_run_parameter_package_stable_key(old_package_bundle.package),
        ) from exc
    return RunPackageReplacementResult(
        old_holiday_id=old_holiday_row.id,
        new_holiday_id=new_holiday_row.id,
        old_weather_id=old_weather_row.id,
        new_weather_id=new_weather_row.id,
        old_package_id=old_package_row.id,
        new_package_id=new_package_row.id,
    )
