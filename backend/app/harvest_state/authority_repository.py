"""Task 9 authority repository — create-or-load, exact-load, and lifecycle management.

All 7 authority families:
  capacity_pool_definition, daily_capacity, holiday_calendar_version,
  weather_rule_config_version, run_parameter_package,
  initial_inventory_snapshot, mature_inventory_loss_authority.

CRITICAL INVARIANTS
  • Every async function receives ``session: AsyncSession`` as its first arg.
  • The repository NEVER creates sessions, NEVER commits, NEVER closes sessions.
  • ``flush()`` is acceptable for ID generation; ``commit()`` is FORBIDDEN.
  • All hash computation uses FROZEN canonical builders from authority_canonical.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import Base
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
    AuthorityHashConflictError,
    AuthorityNotFoundError,
    AuthorityStillReferencedByActivePackageError,
    AuthoritySupersessionScopeConflictError,
    AuthorityVersionConflictError,
    DependencyNotFoundError,
    HolidayCalendarHashMismatchError,
    LifecycleTransitionInvalidError,
    RunParameterDependencyStatusConflictError,
    RunParameterDependencyTimezoneConflictError,
    WeatherRuleConfigHashMismatchError,
)
from backend.app.harvest_state.authority_repository_types import (
    AuthorityBundleCreateResult,
    AuthorityBundleLoadResult,
    AuthorityCreateResult,
    AuthorityLoadResult,
    LifecycleTransitionResult,
    SupersessionResult,
)
from backend.app.harvest_state.authority_schemas import (
    Task9CapacityPoolDefinitionSemanticBundle,
    Task9CapacityPoolMemberSchema,
    Task9DailyCapacitySemanticInput,
    Task9HolidayCalendarDateSchema,
    Task9HolidayCalendarSemanticBundle,
    Task9HolidayCalendarSemanticInput,
    Task9InitialInventoryCohortSchema,
    Task9InitialInventorySemanticBundle,
    Task9InitialInventorySemanticInput,
    Task9LifecycleEventSemanticInput,
    Task9MatureLossSemanticInput,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleSemanticInput,
)
from backend.app.harvest_state.canonical import (
    make_holiday_calendar_hash,
)
from backend.app.harvest_state.enums import (
    AuthorityFamily,
    AuthorityStatus,
)
from backend.app.models.task9_authority import (
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

# ── Advisory lock key computation ──────────────────────────────────────


def _advisory_lock_key(family: str, business_key: str, version: str, revision: int) -> int:
    """Deterministic signed-bigint lock key from SHA-256.

    The 64-bit truncated digest is unpacked as a *signed* ``int64`` so that
    the value fits into PostgreSQL's ``bigint`` range for
    ``pg_advisory_xact_lock``.
    """
    raw = f"{family}:{business_key}:{version}:{revision}"
    digest = hashlib.sha256(raw.encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


# ── Allowed lifecycle transitions ──────────────────────────────────────

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    AuthorityStatus.DRAFT: {AuthorityStatus.ACTIVE, AuthorityStatus.CANCELLED},
    AuthorityStatus.ACTIVE: {AuthorityStatus.SUPERSEDED, AuthorityStatus.RETIRED},
    # terminal states — no outgoing transitions
    AuthorityStatus.SUPERSEDED: set(),
    AuthorityStatus.RETIRED: set(),
    AuthorityStatus.CANCELLED: set(),
}


# ── JSON-safe Decimal conversion for JSONB columns ─────────────────────


def _decimal_to_json_safe(obj: Any) -> Any:
    """Recursively convert ``Decimal`` to ``str`` for JSONB serialisation.

    asyncpg's default JSON encoder rejects ``Decimal``; PostgreSQL JSONB
    stores numeric values as strings internally anyway, so converting to
    ``str`` preserves full precision without rounding.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, list):
        return [_decimal_to_json_safe(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_json_safe(v) for k, v in obj.items()}
    return obj


# ── Family enum → value ────────────────────────────────────────────────


def _family_value(family: AuthorityFamily | str) -> str:
    return family.value if isinstance(family, AuthorityFamily) else family


# ── Family-specific scope extraction (for supersession scope check) ───


def _extract_scope_capacity_pool(row: Task9CapacityPoolDefinition) -> dict[str, Any]:
    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "capacity_pool_code": row.capacity_pool_code,
    }


def _extract_scope_daily_capacity(row: Task9DailyCapacityAuthority) -> dict[str, Any]:
    return {
        "capacity_pool_definition_id": row.capacity_pool_definition_id,
        "capacity_date": row.capacity_date,
    }


def _extract_scope_holiday(row: Task9HolidayCalendarVersion) -> dict[str, Any]:
    return {
        "season_id": row.season_id,
        "calendar_code": row.calendar_code,
        "lifecycle_timezone_name": row.lifecycle_timezone_name,
    }


def _extract_scope_weather(row: Task9WeatherRuleConfigVersion) -> dict[str, Any]:
    return {
        "rule_code": row.rule_code,
        "lifecycle_timezone_name": row.lifecycle_timezone_name,
    }


def _extract_scope_run_package(row: Task9RunParameterPackage) -> dict[str, Any]:
    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "farm_scope_key": row.farm_scope_key,
    }


def _extract_scope_initial_inventory(row: Task9InitialInventorySnapshot) -> dict[str, Any]:
    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "opening_state_date": row.opening_state_date,
    }


def _extract_scope_mature_loss(row: Task9MatureInventoryLossAuthority) -> dict[str, Any]:
    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "capacity_pool_code": row.capacity_pool_code,
        "state_date": row.state_date,
        "forecast_quantile": row.forecast_quantile,
    }


_SCOPE_EXTRACTORS: dict[str, Any] = {
    AuthorityFamily.CAPACITY_POOL_DEFINITION: _extract_scope_capacity_pool,
    AuthorityFamily.DAILY_CAPACITY: _extract_scope_daily_capacity,
    AuthorityFamily.HOLIDAY_CALENDAR_VERSION: _extract_scope_holiday,
    AuthorityFamily.WEATHER_RULE_CONFIG_VERSION: _extract_scope_weather,
    AuthorityFamily.RUN_PARAMETER_PACKAGE: _extract_scope_run_package,
    AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT: _extract_scope_initial_inventory,
    AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY: _extract_scope_mature_loss,
}


def _extract_scope(family: AuthorityFamily, row: Any) -> dict[str, Any]:
    extractor = _SCOPE_EXTRACTORS[family]
    return dict(extractor(row))


# ── ORM model → AuthorityFamily mapping ────────────────────────────────


def _family_for_model(model_class: type[Base]) -> AuthorityFamily:
    _map = {
        Task9CapacityPoolDefinition: AuthorityFamily.CAPACITY_POOL_DEFINITION,
        Task9DailyCapacityAuthority: AuthorityFamily.DAILY_CAPACITY,
        Task9HolidayCalendarVersion: AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        Task9WeatherRuleConfigVersion: AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        Task9RunParameterPackage: AuthorityFamily.RUN_PARAMETER_PACKAGE,
        Task9InitialInventorySnapshot: AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        Task9MatureInventoryLossAuthority: AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
    }
    return _map[model_class]


# ── Stable key helpers (reconstruct from ORM row) ─────────────────────


def _stable_key_from_orm_capacity_pool(row: Task9CapacityPoolDefinition) -> str:
    return f"capacity-pool:{row.season_id}:{row.destination_factory_id}:{row.capacity_pool_code}"


def _stable_key_from_orm_daily_capacity(row: Any) -> str:
    pool = row.capacity_pool_definition
    return (
        f"daily-capacity:{pool.season_id}:{pool.destination_factory_id}:"
        f"{pool.capacity_pool_code}:{pool.capacity_pool_version}:{pool.revision}:"
        f"{row.capacity_date.isoformat()}"
    )


def _stable_key_from_orm_holiday(row: Task9HolidayCalendarVersion) -> str:
    return f"holiday-calendar:{row.season_id}:{row.calendar_code}:{row.lifecycle_timezone_name}"


def _stable_key_from_orm_weather(row: Task9WeatherRuleConfigVersion) -> str:
    return f"weather-rule:{row.rule_code}:{row.lifecycle_timezone_name}"


def _stable_key_from_orm_run_package(row: Task9RunParameterPackage) -> str:
    return f"run-package:{row.season_id}:{row.destination_factory_id}:{row.farm_scope_key}"


def _stable_key_from_orm_initial_inventory(row: Task9InitialInventorySnapshot) -> str:
    return (
        f"initial-inventory:{row.season_id}:{row.destination_factory_id}:"
        f"{row.opening_state_date.isoformat()}"
    )


def _stable_key_from_orm_mature_loss(
    row: Task9MatureInventoryLossAuthority,
) -> str:
    return (
        f"mature-loss:{row.season_id}:{row.destination_factory_id}:"
        f"{row.capacity_pool_code}:{row.state_date.isoformat()}:"
        f"{row.forecast_quantile}"
    )


_STABLE_KEY_BUILDERS: dict[str, Any] = {
    AuthorityFamily.CAPACITY_POOL_DEFINITION: _stable_key_from_orm_capacity_pool,
    AuthorityFamily.DAILY_CAPACITY: _stable_key_from_orm_daily_capacity,
    AuthorityFamily.HOLIDAY_CALENDAR_VERSION: _stable_key_from_orm_holiday,
    AuthorityFamily.WEATHER_RULE_CONFIG_VERSION: _stable_key_from_orm_weather,
    AuthorityFamily.RUN_PARAMETER_PACKAGE: _stable_key_from_orm_run_package,
    AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT: _stable_key_from_orm_initial_inventory,
    AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY: _stable_key_from_orm_mature_loss,
}


def _stable_key_from_orm(family: AuthorityFamily, row: Any) -> str:
    result: str = _STABLE_KEY_BUILDERS[family](row)
    return result


def _business_version_from_orm(family: AuthorityFamily, row: Any) -> str:
    """Return the business version string for a given ORM row."""
    if family == AuthorityFamily.CAPACITY_POOL_DEFINITION:
        result: str = row.capacity_pool_version
        return result
    if family == AuthorityFamily.DAILY_CAPACITY:
        result = str(row.capacity_pool_definition.capacity_pool_version)
        return result
    if family == AuthorityFamily.HOLIDAY_CALENDAR_VERSION:
        result = str(row.calendar_version)
        return result
    if family == AuthorityFamily.WEATHER_RULE_CONFIG_VERSION:
        result = str(row.rule_version)
        return result
    if family == AuthorityFamily.RUN_PARAMETER_PACKAGE:
        result = str(row.package_version)
        return result
    if family == AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT:
        result = str(row.snapshot_version)
        return result
    if family == AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY:
        result = str(row.loss_version)
        return result
    raise ValueError(f"unknown family: {family}")


def _revision_from_orm(family: AuthorityFamily, row: Any) -> int:
    """Return the revision number for a given ORM row."""
    if family == AuthorityFamily.DAILY_CAPACITY:
        result: int = row.daily_capacity_revision
        return result
    result = int(row.revision)
    return result


# ── Lifecycle event helper ─────────────────────────────────────────────


async def _write_lifecycle_event(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
    business_row_hash: str,
    transition_sequence: int,
    old_status: AuthorityStatus | None,
    new_status: AuthorityStatus,
    old_consumable_from: date | None = None,
    old_consumable_to: date | None = None,
    new_consumable_from: date | None = None,
    new_consumable_to: date | None = None,
    superseded_by_stable_key: str | None = None,
    superseded_by_business_version: str | None = None,
    superseded_by_revision: int | None = None,
    transitioned_at: datetime | None = None,
) -> Task9AuthorityLifecycleEvent:
    """Create and flush a lifecycle event. Returns the persisted ORM object."""
    if transitioned_at is None:
        transitioned_at = datetime.now(UTC)

    sem_input = Task9LifecycleEventSemanticInput(
        authority_family=family,
        authority_stable_key=stable_key,
        authority_business_version=business_version,
        authority_revision=revision,
        business_row_hash=business_row_hash,
        transition_sequence=transition_sequence,
        old_status=old_status,
        new_status=new_status,
        old_consumable_from_local_date=old_consumable_from,
        old_consumable_to_local_date=old_consumable_to,
        new_consumable_from_local_date=new_consumable_from,
        new_consumable_to_local_date=new_consumable_to,
        superseded_by_authority_stable_key=superseded_by_stable_key,
        superseded_by_authority_business_version=superseded_by_business_version,
        superseded_by_authority_revision=superseded_by_revision,
        transitioned_at=transitioned_at,
        source_system="authority_repository",
        source_record_key=f"lifecycle:{family.value}:{stable_key}:{revision}:{transition_sequence}",
    )
    event_hash = make_lifecycle_event_hash(sem_input)

    event = Task9AuthorityLifecycleEvent(
        authority_family=family.value,
        authority_stable_key=stable_key,
        authority_business_version=business_version,
        authority_revision=revision,
        business_row_hash=business_row_hash,
        transition_sequence=transition_sequence,
        old_status=None if old_status is None else old_status.value,
        new_status=new_status.value,
        old_consumable_from_local_date=old_consumable_from,
        old_consumable_to_local_date=old_consumable_to,
        new_consumable_from_local_date=new_consumable_from,
        new_consumable_to_local_date=new_consumable_to,
        superseded_by_authority_stable_key=superseded_by_stable_key,
        superseded_by_authority_business_version=superseded_by_business_version,
        superseded_by_authority_revision=superseded_by_revision,
        transitioned_at=transitioned_at,
        source_system="authority_repository",
        source_record_key=f"lifecycle:{family.value}:{stable_key}:{revision}:{transition_sequence}",
        lifecycle_event_hash=event_hash,
    )
    session.add(event)
    await session.flush()
    return event


async def _create_initial_draft_event(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
    business_row_hash: str,
    available_at: date,
) -> Task9AuthorityLifecycleEvent:
    """Create the initial draft→draft lifecycle event (sequence=1)."""
    return await _write_lifecycle_event(
        session,
        family=family,
        stable_key=stable_key,
        business_version=business_version,
        revision=revision,
        business_row_hash=business_row_hash,
        transition_sequence=1,
        old_status=None,
        new_status=AuthorityStatus.DRAFT,
        new_consumable_from=None,
        new_consumable_to=None,
        transitioned_at=datetime.now(UTC),
    )


async def _verify_lifecycle_chain(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
    business_row_hash: str,
    authority_status: str | None = None,
    authority_consumable_from: date | None = None,
    authority_consumable_to: date | None = None,
    authority_superseded_by_id: int | None = None,
) -> list[Task9AuthorityLifecycleEvent]:
    """Load lifecycle events for an authority and verify full chain integrity.

    Verifies:
    1. Events non-empty.
    2. transition_sequence starts at 1 and is continuous.
    3. Each event's business_row_hash equals the authority's immutable row_hash.
    4. Sequence 1 must be the canonical initial draft event.
    5. For sequence N > 1: current.old_* == previous.new_*.
    6. Non-supersession events must NOT have superseded_by fields.
    7. Supersession events MUST have ALL three superseded_by fields.
    8. Replacement identity must be resolvable in DB.
    9. Final event's projection must match current authority state.
    10. All errors are typed — never AUTHORITY_NOT_FOUND.
    """
    stmt = (
        select(Task9AuthorityLifecycleEvent)
        .where(
            Task9AuthorityLifecycleEvent.authority_family == family.value,
            Task9AuthorityLifecycleEvent.authority_stable_key == stable_key,
            Task9AuthorityLifecycleEvent.authority_business_version == business_version,
            Task9AuthorityLifecycleEvent.authority_revision == revision,
        )
        .order_by(Task9AuthorityLifecycleEvent.transition_sequence)
    )
    result = await session.execute(stmt)
    events = list(result.scalars().all())

    # (1) Non-empty
    if not events:
        raise LifecycleTransitionInvalidError(
            authority_family=family,
            authority_stable_key=stable_key,
            current_status="unknown",
            target_status="verify_chain",
        )

    for idx, event in enumerate(events):
        expected_seq = idx + 1

        # (2) Sequence starts at 1 and is continuous
        if event.transition_sequence != expected_seq:
            raise LifecycleTransitionInvalidError(
                authority_family=family,
                authority_stable_key=stable_key,
                current_status=f"seq_gap_at_{expected_seq}",
                target_status=str(event.transition_sequence),
            )

        # (3) Each event's business_row_hash must equal the authority's row_hash
        if event.business_row_hash != business_row_hash:
            raise AuthorityHashConflictError(
                authority_family=family,
                authority_stable_key=stable_key,
                expected_hash=business_row_hash,
                actual_hash=event.business_row_hash,
            )

        # Verify lifecycle event self-hash
        old_st = None if event.old_status is None else AuthorityStatus(event.old_status)
        new_st = AuthorityStatus(event.new_status)
        sem = Task9LifecycleEventSemanticInput(
            authority_family=family,
            authority_stable_key=event.authority_stable_key,
            authority_business_version=event.authority_business_version,
            authority_revision=event.authority_revision,
            business_row_hash=event.business_row_hash,
            transition_sequence=event.transition_sequence,
            old_status=old_st,
            new_status=new_st,
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
        )
        expected_hash = make_lifecycle_event_hash(sem)
        if event.lifecycle_event_hash != expected_hash:
            raise AuthorityHashConflictError(
                authority_family=family,
                authority_stable_key=stable_key,
                expected_hash=expected_hash,
                actual_hash=event.lifecycle_event_hash,
            )

        # (4) First event must be the canonical initial draft event
        if expected_seq == 1:
            errors: list[str] = []
            if event.old_status is not None:
                errors.append(f"old_status={event.old_status}, expected NULL")
            if event.new_status != AuthorityStatus.DRAFT:
                errors.append(f"new_status={event.new_status}, expected draft")
            if event.old_consumable_from_local_date is not None:
                errors.append("old_consumable_from not NULL")
            if event.old_consumable_to_local_date is not None:
                errors.append("old_consumable_to not NULL")
            if event.new_consumable_from_local_date is not None:
                errors.append("new_consumable_from not NULL")
            if event.new_consumable_to_local_date is not None:
                errors.append("new_consumable_to not NULL")
            if event.superseded_by_authority_stable_key is not None:
                errors.append("superseded_by_stable_key not NULL")
            if event.superseded_by_authority_business_version is not None:
                errors.append("superseded_by_version not NULL")
            if event.superseded_by_authority_revision is not None:
                errors.append("superseded_by_revision not NULL")
            if errors:
                raise LifecycleTransitionInvalidError(
                    authority_family=family,
                    authority_stable_key=stable_key,
                    current_status="initial_draft",
                    target_status="; ".join(errors),
                )
        else:
            # (5) Chain continuity: current.old_* == previous.new_*
            prev = events[idx - 1]
            chain_errors: list[str] = []
            if event.old_status != prev.new_status:
                chain_errors.append(
                    f"old_status={event.old_status} != prev.new_status={prev.new_status}"
                )
            if event.old_consumable_from_local_date != prev.new_consumable_from_local_date:
                chain_errors.append(
                    f"old_consumable_from={event.old_consumable_from_local_date} "
                    f"!= prev.new_consumable_from={prev.new_consumable_from_local_date}"
                )
            if event.old_consumable_to_local_date != prev.new_consumable_to_local_date:
                chain_errors.append(
                    f"old_consumable_to={event.old_consumable_to_local_date} "
                    f"!= prev.new_consumable_to={prev.new_consumable_to_local_date}"
                )
            if chain_errors:
                raise LifecycleTransitionInvalidError(
                    authority_family=family,
                    authority_stable_key=stable_key,
                    current_status=event.old_status or "null",
                    target_status="; ".join(chain_errors),
                )

        # (6+7) Supersession scope checks
        is_supersession = event.new_status == AuthorityStatus.SUPERSEDED
        has_any_superseded_by = (
            event.superseded_by_authority_stable_key is not None
            or event.superseded_by_authority_business_version is not None
            or event.superseded_by_authority_revision is not None
        )

        if not is_supersession and has_any_superseded_by:
            raise LifecycleTransitionInvalidError(
                authority_family=family,
                authority_stable_key=stable_key,
                current_status=event.new_status,
                target_status="non_supersession_with_superseded_by",
            )

        if is_supersession:
            # (7) Must have ALL three superseded_by fields
            missing_fields: list[str] = []
            if event.superseded_by_authority_stable_key is None:
                missing_fields.append("superseded_by_authority_stable_key")
            if event.superseded_by_authority_business_version is None:
                missing_fields.append("superseded_by_authority_business_version")
            if event.superseded_by_authority_revision is None:
                missing_fields.append("superseded_by_authority_revision")
            if missing_fields:
                raise AuthoritySupersessionScopeConflictError(
                    authority_family=family,
                    details={
                        "missing_fields": missing_fields,
                        "sequence": event.transition_sequence,
                    },
                )

            # (8) Replacement identity must be resolvable
            repl_model_cls = _FAMILY_MODEL_MAP[family]
            repl_stmt = select(repl_model_cls)
            repl_result = await session.execute(repl_stmt)
            all_rows = list(repl_result.scalars().all())
            found_replacement = False
            for candidate in all_rows:
                csk = _stable_key_from_orm(family, candidate)
                cver = _business_version_from_orm(family, candidate)
                crev = _revision_from_orm(family, candidate)
                if (
                    csk == event.superseded_by_authority_stable_key
                    and cver == event.superseded_by_authority_business_version
                    and crev == event.superseded_by_authority_revision
                ):
                    found_replacement = True
                    break
            if not found_replacement:
                raise AuthoritySupersessionScopeConflictError(
                    authority_family=family,
                    details={
                        "reason": "replacement_identity_not_resolvable",
                        "superseded_by_stable_key": event.superseded_by_authority_stable_key,
                        "superseded_by_version": event.superseded_by_authority_business_version,
                        "superseded_by_revision": event.superseded_by_authority_revision,
                        "sequence": event.transition_sequence,
                    },
                )

    # (9) Final event's projection must match current authority
    final = events[-1]
    projection_errors: list[str] = []
    if authority_status is not None and final.new_status != authority_status:
        projection_errors.append(
            f"status: event={final.new_status}, authority={authority_status}"
        )
    if (
        authority_consumable_from is not None
        and final.new_consumable_from_local_date != authority_consumable_from
    ):
        projection_errors.append(
            f"consumable_from: event={final.new_consumable_from_local_date}, "
            f"authority={authority_consumable_from}"
        )
    if (
        authority_consumable_to is not None
        and final.new_consumable_to_local_date != authority_consumable_to
    ):
        projection_errors.append(
            f"consumable_to: event={final.new_consumable_to_local_date}, "
            f"authority={authority_consumable_to}"
        )
    if projection_errors:
        raise AuthorityConsumabilityIntervalConflictError(
            details={
                "reason": "final_event_projection_mismatch",
                "family": family.value,
                "stable_key": stable_key,
                "errors": projection_errors,
            },
        )

    return events


async def _next_lifecycle_sequence(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
) -> int:
    """Return the next transition_sequence for an authority."""
    stmt = (
        select(Task9AuthorityLifecycleEvent.transition_sequence)
        .where(
            Task9AuthorityLifecycleEvent.authority_family == family.value,
            Task9AuthorityLifecycleEvent.authority_stable_key == stable_key,
            Task9AuthorityLifecycleEvent.authority_business_version == business_version,
            Task9AuthorityLifecycleEvent.authority_revision == revision,
        )
        .order_by(Task9AuthorityLifecycleEvent.transition_sequence.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    current_max = result.scalar_one_or_none()
    return (current_max or 0) + 1


# ── Advisory lock acquisition ─────────────────────────────────────────


async def _acquire_advisory_lock(session: AsyncSession, lock_key: int) -> None:
    """Acquire a PostgreSQL transaction-scoped advisory lock."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})


# ── Dependency protection ─────────────────────────────────────────────


async def _check_dependency_references(
    session: AsyncSession,
    *,
    dependency_family: AuthorityFamily,
    dependency_id: int,
) -> None:
    """Raise ``AuthorityStillReferencedByActivePackageError`` if the
    dependency is still referenced by an active run-parameter package.
    """
    if dependency_family == AuthorityFamily.HOLIDAY_CALENDAR_VERSION:
        stmt = select(Task9RunParameterPackage.id).where(
            Task9RunParameterPackage.holiday_calendar_version_id == dependency_id,
            Task9RunParameterPackage.status == AuthorityStatus.ACTIVE,
        )
    elif dependency_family == AuthorityFamily.WEATHER_RULE_CONFIG_VERSION:
        stmt = select(Task9RunParameterPackage.id).where(
            Task9RunParameterPackage.weather_rule_config_version_id == dependency_id,
            Task9RunParameterPackage.status == AuthorityStatus.ACTIVE,
        )
    else:
        return  # Not a dependency family — no check needed

    result = await session.execute(stmt)
    pkg_ids = list(result.scalars().all())
    if pkg_ids:
        raise AuthorityStillReferencedByActivePackageError(
            authority_family=dependency_family,
            referencing_package_ids=pkg_ids,
        )


# ══════════════════════════════════════════════════════════════════════
#  CREATE-OR-LOAD: Capacity Pool Definition (bundle)
# ══════════════════════════════════════════════════════════════════════


async def create_or_load_capacity_pool_definition(
    session: AsyncSession,
    *,
    definition_input: Task9CapacityPoolDefinitionSemanticBundle,
) -> AuthorityBundleCreateResult:
    """Create or load a capacity-pool definition with its members.

    Follows the canonical create-or-load pattern:
    a. Compute canonical payload using frozen builders.
    b. Compute row_hash via make_authority_row_hash.
    c. Compute stable key.
    d. Acquire advisory lock.
    e. Lookup by business unique key.
    f. If exists: recompute hash, verify match → return (created=False).
    g. If not exists: INSERT parent + members, flush, create lifecycle event.
    """
    members = definition_input.members
    definition = definition_input.definition

    # (a+b) Compute canonical payload and row_hash
    row_hash = make_authority_row_hash(definition_input)

    # (c) Compute stable key
    stable_key = build_capacity_pool_definition_stable_key(definition)

    # (d) Advisory lock
    lock_key = _advisory_lock_key(
        AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key,
        definition.capacity_pool_version,
        definition.revision,
    )
    await _acquire_advisory_lock(session, lock_key)

    # (e) Lookup by UQ
    stmt = select(Task9CapacityPoolDefinition).where(
        Task9CapacityPoolDefinition.season_id == definition.season_id,
        Task9CapacityPoolDefinition.destination_factory_id == definition.destination_factory_id,
        Task9CapacityPoolDefinition.capacity_pool_code == definition.capacity_pool_code,
        Task9CapacityPoolDefinition.capacity_pool_version == definition.capacity_pool_version,
        Task9CapacityPoolDefinition.revision == definition.revision,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        # (f) Recompute hash from persisted columns — verify match
        # Reconstruct member schemas from persisted children
        member_stmt = (
            select(Task9CapacityPoolMember)
            .where(Task9CapacityPoolMember.capacity_pool_definition_id == existing.id)
            .order_by(
                Task9CapacityPoolMember.farm_id,
                Task9CapacityPoolMember.subfarm_id,
                Task9CapacityPoolMember.variety_id,
            )
        )
        member_result = await session.execute(member_stmt)
        persisted_members = list(member_result.scalars().all())
        member_schemas = [
            Task9CapacityPoolMemberSchema(
                farm_id=m.farm_id,
                subfarm_id=m.subfarm_id,
                variety_id=m.variety_id,
            )
            for m in persisted_members
        ]
        # Reconstruct semantic bundle for hash verification
        from backend.app.harvest_state.authority_schemas import (
            Task9CapacityPoolDefinitionSemanticBundle as Bundle,
        )

        reconstructed = Bundle(
            season_id=existing.season_id,
            destination_factory_id=existing.destination_factory_id,
            capacity_pool_code=existing.capacity_pool_code,
            capacity_pool_grain=existing.capacity_pool_grain,
            capacity_input_mode=existing.capacity_input_mode,
            capacity_pool_version=existing.capacity_pool_version,
            revision=existing.revision,
            effective_from=existing.effective_from,
            effective_to=existing.effective_to,
            available_at_local_date=existing.available_at_local_date,
            consumable_from_local_date=existing.consumable_from_local_date,
            consumable_to_local_date=existing.consumable_to_local_date,
            superseded_by_id=existing.superseded_by_id,
            status=existing.status,
            status_changed_at=existing.status_changed_at,
            source_system=existing.source_system,
            source_record_key=existing.source_record_key,
            source_version=existing.source_version,
            members=member_schemas,
        )
        recomputed_hash = make_authority_row_hash(reconstructed)
        if recomputed_hash != existing.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=stable_key,
                expected_hash=recomputed_hash,
                actual_hash=existing.row_hash,
            )
        if row_hash != existing.row_hash:
            raise AuthorityVersionConflictError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=stable_key,
                existing_hash=existing.row_hash,
                submitted_hash=row_hash,
            )
        return AuthorityBundleCreateResult(
            parent=AuthorityCreateResult(
                authority_id=existing.id,
                row_hash=existing.row_hash,
                created=False,
                lifecycle_event_id=None,
            ),
            child_ids=[m.id for m in persisted_members],
        )

    # (g) Not found — INSERT
    parent_row = Task9CapacityPoolDefinition(
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
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime.now(UTC),
        source_system=definition.source_system,
        source_record_key=definition.source_record_key,
        source_version=definition.source_version,
        row_hash=row_hash,
        superseded_by_id=None,
    )
    session.add(parent_row)
    await session.flush()  # generate parent ID

    child_ids: list[int] = []
    insert_sql = text("""
        INSERT INTO task9_capacity_pool_member (
            capacity_pool_definition_id, season_id, destination_factory_id,
            farm_id, subfarm_id, variety_id,
            effective_from, effective_to,
            status, consumable_from_key, consumable_to_key, row_hash
        )
        SELECT p.id, p.season_id, p.destination_factory_id,
            :farm_id, :subfarm_id, :variety_id,
            p.effective_from, p.effective_to,
            p.status, p.consumable_from_key, p.consumable_to_key, :child_row_hash
        FROM task9_capacity_pool_definition p
        WHERE p.id = :parent_id
        RETURNING id
    """)
    for member in sorted(
        members,
        key=lambda m: (
            m.farm_id,
            -1 if m.subfarm_id is None else m.subfarm_id,
            m.variety_id,
        ),
    ):
        member_hash = make_authority_row_hash(member, parent_definition=definition)
        insert_result = await session.execute(
            insert_sql,
            {
                "farm_id": member.farm_id,
                "subfarm_id": member.subfarm_id,
                "variety_id": member.variety_id,
                "child_row_hash": member_hash,
                "parent_id": parent_row.id,
            },
        )
        inserted_row = insert_result.fetchone()
        assert inserted_row is not None, (
            f"INSERT...SELECT affected 0 rows for member "
            f"(farm={member.farm_id}, subfarm={member.subfarm_id}, "
            f"variety={member.variety_id})"
        )
        child_ids.append(inserted_row[0])

    # Initial lifecycle event (seq=1, draft→draft)
    event = await _create_initial_draft_event(
        session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key=stable_key,
        business_version=definition.capacity_pool_version,
        revision=definition.revision,
        business_row_hash=row_hash,
        available_at=definition.available_at_local_date,
    )

    return AuthorityBundleCreateResult(
        parent=AuthorityCreateResult(
            authority_id=parent_row.id,
            row_hash=row_hash,
            created=True,
            lifecycle_event_id=event.id,
        ),
        child_ids=child_ids,
    )


# ══════════════════════════════════════════════════════════════════════
#  EXACT LOAD: Capacity Pool Definition (bundle)
# ══════════════════════════════════════════════════════════════════════


async def load_capacity_pool_definition_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
) -> AuthorityBundleLoadResult:
    """Load a capacity-pool definition by ID, verify hashes and lifecycle."""
    stmt = select(Task9CapacityPoolDefinition).where(Task9CapacityPoolDefinition.id == authority_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            lookup_key=str(authority_id),
        )

    stable_key = _stable_key_from_orm_capacity_pool(row)

    # Load members
    member_stmt = (
        select(Task9CapacityPoolMember)
        .where(Task9CapacityPoolMember.capacity_pool_definition_id == row.id)
        .order_by(
            Task9CapacityPoolMember.farm_id,
            Task9CapacityPoolMember.subfarm_id,
            Task9CapacityPoolMember.variety_id,
        )
    )
    member_result = await session.execute(member_stmt)
    members = list(member_result.scalars().all())

    # Reconstruct semantic bundle and recompute hash
    member_schemas = [
        Task9CapacityPoolMemberSchema(
            farm_id=m.farm_id,
            subfarm_id=m.subfarm_id,
            variety_id=m.variety_id,
        )
        for m in members
    ]
    from backend.app.harvest_state.authority_schemas import (
        Task9CapacityPoolDefinitionSemanticBundle as Bundle,
    )

    reconstructed = Bundle(
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
        members=member_schemas,
    )
    recomputed_hash = make_authority_row_hash(reconstructed)
    if recomputed_hash != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            authority_stable_key=stable_key,
            expected_hash=recomputed_hash,
            actual_hash=row.row_hash,
        )

    # Verify child projection: each member's inherited fields must match parent
    _parent_consumable_from_key = (
        row.consumable_from_local_date
        if row.consumable_from_local_date is not None
        else date(9999, 12, 31)
    )
    _parent_consumable_to_key = (
        row.consumable_to_local_date
        if row.consumable_to_local_date is not None
        else date(9999, 12, 31)
    )
    for m in members:
        _field_errors: list[str] = []
        if m.season_id != row.season_id:
            _field_errors.append(
                f"season_id: member={m.season_id} != parent={row.season_id}"
            )
        if m.destination_factory_id != row.destination_factory_id:
            _field_errors.append(
                f"destination_factory_id: member={m.destination_factory_id} "
                f"!= parent={row.destination_factory_id}"
            )
        if m.effective_from != row.effective_from:
            _field_errors.append(
                f"effective_from: member={m.effective_from} != parent={row.effective_from}"
            )
        if m.effective_to != row.effective_to:
            _field_errors.append(
                f"effective_to: member={m.effective_to} != parent={row.effective_to}"
            )
        if m.status != row.status:
            _field_errors.append(
                f"status: member={m.status} != parent={row.status}"
            )
        if m.consumable_from_key != _parent_consumable_from_key:
            _field_errors.append(
                f"consumable_from_key: member={m.consumable_from_key} "
                f"!= parent={_parent_consumable_from_key}"
            )
        if m.consumable_to_key != _parent_consumable_to_key:
            _field_errors.append(
                f"consumable_to_key: member={m.consumable_to_key} "
                f"!= parent={_parent_consumable_to_key}"
            )
        if _field_errors:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=stable_key,
                expected_hash="child_projection_match",
                actual_hash=f"diverged: {'; '.join(_field_errors)}",
            )

    # Verify child hashes
    for m, ms in zip(members, member_schemas, strict=True):
        expected_child_hash = make_authority_row_hash(
            ms,
            parent_definition=reconstructed,
        )
        if m.row_hash != expected_child_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
                authority_stable_key=stable_key,
                expected_hash=expected_child_hash,
                actual_hash=m.row_hash,
            )

    # Verify lifecycle chain
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key=stable_key,
        business_version=row.capacity_pool_version,
        revision=row.revision,
        business_row_hash=row.row_hash,
        authority_status=row.status,
        authority_consumable_from=row.consumable_from_local_date,
        authority_consumable_to=row.consumable_to_local_date,
        authority_superseded_by_id=row.superseded_by_id,
    )

    return AuthorityBundleLoadResult(
        parent=AuthorityLoadResult(
            authority_id=row.id,
            row_hash=row.row_hash,
            status=row.status,
            consumable_from_local_date=row.consumable_from_local_date,
            consumable_to_local_date=row.consumable_to_local_date,
            superseded_by_id=row.superseded_by_id,
        ),
        child_hashes=[m.row_hash for m in members],
    )


# ══════════════════════════════════════════════════════════════════════
#  CREATE-OR-LOAD: Daily Capacity
# ══════════════════════════════════════════════════════════════════════


async def create_or_load_daily_capacity(
    session: AsyncSession,
    *,
    daily_input: Task9DailyCapacitySemanticInput,
) -> AuthorityCreateResult:
    """Create or load a daily-capacity authority row."""
    # Compute hash
    row_hash = make_authority_row_hash(daily_input)

    # Compute stable key
    stable_key = build_daily_capacity_stable_key(daily_input)

    # Advisory lock
    lock_key = _advisory_lock_key(
        AuthorityFamily.DAILY_CAPACITY,
        stable_key,
        daily_input.capacity_pool_version,
        daily_input.daily_capacity_revision,
    )
    await _acquire_advisory_lock(session, lock_key)

    # Resolve pool definition FK
    pool_stmt = select(Task9CapacityPoolDefinition).where(
        Task9CapacityPoolDefinition.season_id == daily_input.season_id,
        Task9CapacityPoolDefinition.destination_factory_id == daily_input.destination_factory_id,
        Task9CapacityPoolDefinition.capacity_pool_code == daily_input.capacity_pool_code,
        Task9CapacityPoolDefinition.capacity_pool_version == daily_input.capacity_pool_version,
        Task9CapacityPoolDefinition.revision == daily_input.capacity_pool_revision,
    )
    pool_result = await session.execute(pool_stmt)
    pool_def = pool_result.scalar_one_or_none()
    if pool_def is None:
        raise DependencyNotFoundError(
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            authority_stable_key=stable_key,
        )

    # Lookup by UQ
    stmt = select(Task9DailyCapacityAuthority).where(
        Task9DailyCapacityAuthority.capacity_pool_definition_id == pool_def.id,
        Task9DailyCapacityAuthority.capacity_date == daily_input.capacity_date,
        Task9DailyCapacityAuthority.daily_capacity_revision == daily_input.daily_capacity_revision,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Recompute hash from persisted columns
        from backend.app.harvest_state.authority_schemas import (
            Task9DailyCapacitySemanticInput as DSI,
        )

        reconstructed = DSI(
            season_id=pool_def.season_id,
            destination_factory_id=pool_def.destination_factory_id,
            capacity_pool_code=pool_def.capacity_pool_code,
            capacity_pool_version=pool_def.capacity_pool_version,
            capacity_pool_revision=pool_def.revision,
            capacity_date=existing.capacity_date,
            daily_capacity_revision=existing.daily_capacity_revision,
            capacity_input_mode=pool_def.capacity_input_mode,
            planned_picker_count=existing.planned_picker_count,
            kg_per_person_per_day=existing.kg_per_person_per_day,
            direct_nominal_capacity_kg_per_day=existing.direct_nominal_capacity_kg_per_day,
            labor_availability_ratio=existing.labor_availability_ratio,
            operational_efficiency_ratio=existing.operational_efficiency_ratio,
            available_at_local_date=existing.available_at_local_date,
            consumable_from_local_date=existing.consumable_from_local_date,
            consumable_to_local_date=existing.consumable_to_local_date,
            superseded_by_id=existing.superseded_by_id,
            status=existing.status,
            status_changed_at=existing.status_changed_at,
            source_system=existing.source_system,
            source_record_key=existing.source_record_key,
            source_version=existing.source_version,
        )
        recomputed = make_authority_row_hash(reconstructed)
        if recomputed != existing.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.DAILY_CAPACITY,
                authority_stable_key=stable_key,
                expected_hash=recomputed,
                actual_hash=existing.row_hash,
            )
        if row_hash != existing.row_hash:
            raise AuthorityVersionConflictError(
                authority_family=AuthorityFamily.DAILY_CAPACITY,
                authority_stable_key=stable_key,
                existing_hash=existing.row_hash,
                submitted_hash=row_hash,
            )
        return AuthorityCreateResult(
            authority_id=existing.id,
            row_hash=existing.row_hash,
            created=False,
            lifecycle_event_id=None,
        )

    # INSERT
    parent_row = Task9DailyCapacityAuthority(
        capacity_pool_definition_id=pool_def.id,
        capacity_date=daily_input.capacity_date,
        daily_capacity_revision=daily_input.daily_capacity_revision,
        planned_picker_count=daily_input.planned_picker_count,
        kg_per_person_per_day=daily_input.kg_per_person_per_day,
        direct_nominal_capacity_kg_per_day=daily_input.direct_nominal_capacity_kg_per_day,
        labor_availability_ratio=daily_input.labor_availability_ratio,
        operational_efficiency_ratio=daily_input.operational_efficiency_ratio,
        available_at_local_date=daily_input.available_at_local_date,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime.now(UTC),
        source_system=daily_input.source_system,
        source_record_key=daily_input.source_record_key,
        source_version=daily_input.source_version,
        row_hash=row_hash,
        superseded_by_id=None,
    )
    session.add(parent_row)
    await session.flush()

    event = await _create_initial_draft_event(
        session,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=stable_key,
        business_version=daily_input.capacity_pool_version,
        revision=daily_input.daily_capacity_revision,
        business_row_hash=row_hash,
        available_at=daily_input.available_at_local_date,
    )

    return AuthorityCreateResult(
        authority_id=parent_row.id,
        row_hash=row_hash,
        created=True,
        lifecycle_event_id=event.id,
    )


# ══════════════════════════════════════════════════════════════════════
#  EXACT LOAD: Daily Capacity
# ══════════════════════════════════════════════════════════════════════


async def load_daily_capacity_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
) -> AuthorityLoadResult:
    """Load a daily-capacity authority by ID, verify hash and lifecycle."""
    stmt = select(Task9DailyCapacityAuthority).where(Task9DailyCapacityAuthority.id == authority_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            lookup_key=str(authority_id),
        )

    # Resolve pool definition for semantic reconstruction
    pool_stmt = select(Task9CapacityPoolDefinition).where(
        Task9CapacityPoolDefinition.id == row.capacity_pool_definition_id
    )
    pool_result = await session.execute(pool_stmt)
    pool_def = pool_result.scalar_one_or_none()
    if pool_def is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            lookup_key=f"pool_not_found:{row.capacity_pool_definition_id}",
        )

    stable_key = _stable_key_from_orm_daily_capacity(row)

    # Reconstruct and verify hash
    from backend.app.harvest_state.authority_schemas import (
        Task9DailyCapacitySemanticInput as DSI,
    )

    reconstructed = DSI(
        season_id=pool_def.season_id,
        destination_factory_id=pool_def.destination_factory_id,
        capacity_pool_code=pool_def.capacity_pool_code,
        capacity_pool_version=pool_def.capacity_pool_version,
        capacity_pool_revision=pool_def.revision,
        capacity_date=row.capacity_date,
        daily_capacity_revision=row.daily_capacity_revision,
        capacity_input_mode=pool_def.capacity_input_mode,
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
    recomputed = make_authority_row_hash(reconstructed)
    if recomputed != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            authority_stable_key=stable_key,
            expected_hash=recomputed,
            actual_hash=row.row_hash,
        )

    # Verify lifecycle chain
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.DAILY_CAPACITY,
        stable_key=stable_key,
        business_version=pool_def.capacity_pool_version,
        revision=row.daily_capacity_revision,
        business_row_hash=row.row_hash,
        authority_status=row.status,
        authority_consumable_from=row.consumable_from_local_date,
        authority_consumable_to=row.consumable_to_local_date,
        authority_superseded_by_id=row.superseded_by_id,
    )

    return AuthorityLoadResult(
        authority_id=row.id,
        row_hash=row.row_hash,
        status=row.status,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
    )


# ══════════════════════════════════════════════════════════════════════
#  CREATE-OR-LOAD: Holiday Calendar Version (bundle)
# ══════════════════════════════════════════════════════════════════════


async def create_or_load_holiday_calendar(
    session: AsyncSession,
    *,
    calendar_input: Task9HolidayCalendarSemanticBundle,
) -> AuthorityBundleCreateResult:
    """Create or load a holiday calendar version with its dates."""
    header = Task9HolidayCalendarSemanticInput(
        **calendar_input.model_dump(exclude={"dates"}),
    )
    dates = calendar_input.dates

    row_hash = make_authority_row_hash(calendar_input)
    stable_key = build_holiday_calendar_stable_key(header)

    lock_key = _advisory_lock_key(
        AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key,
        header.calendar_version,
        header.revision,
    )
    await _acquire_advisory_lock(session, lock_key)

    # Lookup by UQ
    stmt = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.season_id == header.season_id,
        Task9HolidayCalendarVersion.calendar_code == header.calendar_code,
        Task9HolidayCalendarVersion.lifecycle_timezone_name == header.lifecycle_timezone_name,
        Task9HolidayCalendarVersion.calendar_version == header.calendar_version,
        Task9HolidayCalendarVersion.revision == header.revision,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Recompute hash from persisted children
        date_stmt = (
            select(Task9HolidayCalendarDate)
            .where(Task9HolidayCalendarDate.holiday_calendar_version_id == existing.id)
            .order_by(
                Task9HolidayCalendarDate.holiday_date,
                Task9HolidayCalendarDate.holiday_code,
            )
        )
        date_result = await session.execute(date_stmt)
        persisted_dates = list(date_result.scalars().all())
        date_schemas = [
            Task9HolidayCalendarDateSchema(
                holiday_date=d.holiday_date,
                holiday_code=d.holiday_code,
                holiday_name=d.holiday_name,
            )
            for d in persisted_dates
        ]
        # Reconstruct bundle for hash check
        from backend.app.harvest_state.authority_schemas import (
            Task9HolidayCalendarSemanticBundle as HBundle,
        )

        recon_bundle = HBundle(
            season_id=existing.season_id,
            calendar_code=existing.calendar_code,
            calendar_version=existing.calendar_version,
            revision=existing.revision,
            calendar_hash=existing.calendar_hash,
            region_scope=existing.region_scope,
            lifecycle_timezone_name=existing.lifecycle_timezone_name,
            available_at_local_date=existing.available_at_local_date,
            consumable_from_local_date=existing.consumable_from_local_date,
            consumable_to_local_date=existing.consumable_to_local_date,
            superseded_by_id=existing.superseded_by_id,
            status=existing.status,
            status_changed_at=existing.status_changed_at,
            source_system=existing.source_system,
            source_record_key=existing.source_record_key,
            source_version=existing.source_version,
            dates=date_schemas,
        )
        recomputed = make_authority_row_hash(recon_bundle)
        if recomputed != existing.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                authority_stable_key=stable_key,
                expected_hash=recomputed,
                actual_hash=existing.row_hash,
            )
        if row_hash != existing.row_hash:
            raise AuthorityVersionConflictError(
                authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
                authority_stable_key=stable_key,
                existing_hash=existing.row_hash,
                submitted_hash=row_hash,
            )
        return AuthorityBundleCreateResult(
            parent=AuthorityCreateResult(
                authority_id=existing.id,
                row_hash=existing.row_hash,
                created=False,
                lifecycle_event_id=None,
            ),
            child_ids=[d.id for d in persisted_dates],
        )

    # INSERT parent
    parent_row = Task9HolidayCalendarVersion(
        season_id=header.season_id,
        calendar_code=header.calendar_code,
        lifecycle_timezone_name=header.lifecycle_timezone_name,
        calendar_version=header.calendar_version,
        revision=header.revision,
        region_scope=header.region_scope,
        calendar_hash=header.calendar_hash,
        available_at_local_date=header.available_at_local_date,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime.now(UTC),
        source_system=header.source_system,
        source_record_key=header.source_record_key,
        source_version=header.source_version,
        row_hash=row_hash,
        superseded_by_id=None,
    )
    session.add(parent_row)
    await session.flush()

    # INSERT children via SQL text for parent-projection pattern
    for d in sorted(dates, key=lambda x: (x.holiday_date, x.holiday_code)):
        child = Task9HolidayCalendarDate(
            holiday_calendar_version_id=parent_row.id,
            holiday_date=d.holiday_date,
            holiday_code=d.holiday_code,
            holiday_name=d.holiday_name,
        )
        session.add(child)
    await session.flush()

    # Reload children for IDs
    child_stmt = (
        select(Task9HolidayCalendarDate)
        .where(Task9HolidayCalendarDate.holiday_calendar_version_id == parent_row.id)
        .order_by(
            Task9HolidayCalendarDate.holiday_date,
            Task9HolidayCalendarDate.holiday_code,
        )
    )
    child_result = await session.execute(child_stmt)
    child_ids = [c.id for c in child_result.scalars().all()]

    event = await _create_initial_draft_event(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=stable_key,
        business_version=header.calendar_version,
        revision=header.revision,
        business_row_hash=row_hash,
        available_at=header.available_at_local_date,
    )

    return AuthorityBundleCreateResult(
        parent=AuthorityCreateResult(
            authority_id=parent_row.id,
            row_hash=row_hash,
            created=True,
            lifecycle_event_id=event.id,
        ),
        child_ids=child_ids,
    )


# ══════════════════════════════════════════════════════════════════════
#  EXACT LOAD: Holiday Calendar Version (bundle)
# ══════════════════════════════════════════════════════════════════════


async def load_holiday_calendar_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
) -> AuthorityBundleLoadResult:
    """Load a holiday calendar by ID, verify hashes and lifecycle."""
    stmt = select(Task9HolidayCalendarVersion).where(Task9HolidayCalendarVersion.id == authority_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            lookup_key=str(authority_id),
        )

    stable_key = _stable_key_from_orm_holiday(row)

    date_stmt = (
        select(Task9HolidayCalendarDate)
        .where(Task9HolidayCalendarDate.holiday_calendar_version_id == row.id)
        .order_by(
            Task9HolidayCalendarDate.holiday_date,
            Task9HolidayCalendarDate.holiday_code,
        )
    )
    date_result = await session.execute(date_stmt)
    persisted_dates = list(date_result.scalars().all())
    date_schemas = [
        Task9HolidayCalendarDateSchema(
            holiday_date=d.holiday_date,
            holiday_code=d.holiday_code,
            holiday_name=d.holiday_name,
        )
        for d in persisted_dates
    ]

    from backend.app.harvest_state.authority_schemas import (
        Task9HolidayCalendarSemanticBundle as HBundle,
    )

    try:
        recon_bundle = HBundle(
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
            dates=date_schemas,
        )
    except ValueError as exc:
        if "HOLIDAY_CALENDAR_HASH_MISMATCH" in str(exc):
            unique_holiday_dates = sorted({d.holiday_date for d in date_schemas})
            from backend.app.harvest_state.canonical import (
                make_holiday_calendar_hash,
            )

            expected_cal_hash = make_holiday_calendar_hash(
                holiday_calendar_version=row.calendar_version,
                holiday_dates=unique_holiday_dates,
            )
            raise HolidayCalendarHashMismatchError(
                expected_hash=expected_cal_hash,
                actual_hash=row.calendar_hash,
            ) from exc
        raise
    recomputed = make_authority_row_hash(recon_bundle)
    if recomputed != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            authority_stable_key=stable_key,
            expected_hash=recomputed,
            actual_hash=row.row_hash,
        )

    # Also verify calendar_hash
    unique_holiday_dates = sorted({d.holiday_date for d in date_schemas})
    from backend.app.harvest_state.canonical import make_holiday_calendar_hash

    expected_cal_hash = make_holiday_calendar_hash(
        holiday_calendar_version=row.calendar_version,
        holiday_dates=unique_holiday_dates,
    )
    if row.calendar_hash != expected_cal_hash:
        raise HolidayCalendarHashMismatchError(
            expected_hash=expected_cal_hash,
            actual_hash=row.calendar_hash,
        )

    # Verify lifecycle chain
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=stable_key,
        business_version=row.calendar_version,
        revision=row.revision,
        business_row_hash=row.row_hash,
        authority_status=row.status,
        authority_consumable_from=row.consumable_from_local_date,
        authority_consumable_to=row.consumable_to_local_date,
        authority_superseded_by_id=row.superseded_by_id,
    )

    return AuthorityBundleLoadResult(
        parent=AuthorityLoadResult(
            authority_id=row.id,
            row_hash=row.row_hash,
            status=row.status,
            consumable_from_local_date=row.consumable_from_local_date,
            consumable_to_local_date=row.consumable_to_local_date,
            superseded_by_id=row.superseded_by_id,
        ),
        child_hashes=[],  # holiday dates don't have row_hash
    )


# ══════════════════════════════════════════════════════════════════════
#  CREATE-OR-LOAD: Weather Rule Config Version
# ══════════════════════════════════════════════════════════════════════


async def create_or_load_weather_rule(
    session: AsyncSession,
    *,
    weather_input: Task9WeatherRuleSemanticInput,
) -> AuthorityCreateResult:
    """Create or load a weather rule config version."""
    row_hash = make_authority_row_hash(weather_input)
    stable_key = build_weather_rule_stable_key(weather_input)

    lock_key = _advisory_lock_key(
        AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key,
        weather_input.rule_version,
        weather_input.revision,
    )
    await _acquire_advisory_lock(session, lock_key)

    # Lookup by UQ
    stmt = select(Task9WeatherRuleConfigVersion).where(
        Task9WeatherRuleConfigVersion.rule_code == weather_input.rule_code,
        Task9WeatherRuleConfigVersion.lifecycle_timezone_name
        == weather_input.lifecycle_timezone_name,
        Task9WeatherRuleConfigVersion.rule_version == weather_input.rule_version,
        Task9WeatherRuleConfigVersion.revision == weather_input.revision,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Recompute hash from persisted columns
        from backend.app.harvest_state.authority_schemas import (
            Task9WeatherRuleSemanticInput as WSI,
        )

        reconstructed = WSI(
            rule_code=existing.rule_code,
            rule_version=existing.rule_version,
            revision=existing.revision,
            lifecycle_timezone_name=existing.lifecycle_timezone_name,
            combination_method=existing.combination_method,
            minimum_ratio=existing.minimum_ratio,
            maximum_ratio=existing.maximum_ratio,
            required_feature_ids=existing.required_feature_ids,
            feature_rules=existing.feature_rules_json,
            missing_feature_policy=existing.missing_feature_policy,
            config_hash=existing.config_hash,
            effective_from=existing.effective_from,
            effective_to=existing.effective_to,
            available_at_local_date=existing.available_at_local_date,
            consumable_from_local_date=existing.consumable_from_local_date,
            consumable_to_local_date=existing.consumable_to_local_date,
            superseded_by_id=existing.superseded_by_id,
            status=existing.status,
            status_changed_at=existing.status_changed_at,
            source_system=existing.source_system,
            source_record_key=existing.source_record_key,
            source_version=existing.source_version,
        )
        recomputed = make_authority_row_hash(reconstructed)
        if recomputed != existing.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                authority_stable_key=stable_key,
                expected_hash=recomputed,
                actual_hash=existing.row_hash,
            )
        if row_hash != existing.row_hash:
            raise AuthorityVersionConflictError(
                authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
                authority_stable_key=stable_key,
                existing_hash=existing.row_hash,
                submitted_hash=row_hash,
            )
        return AuthorityCreateResult(
            authority_id=existing.id,
            row_hash=existing.row_hash,
            created=False,
            lifecycle_event_id=None,
        )

    # INSERT
    parent_row = Task9WeatherRuleConfigVersion(
        rule_code=weather_input.rule_code,
        lifecycle_timezone_name=weather_input.lifecycle_timezone_name,
        rule_version=weather_input.rule_version,
        revision=weather_input.revision,
        combination_method=weather_input.combination_method.value,
        minimum_ratio=weather_input.minimum_ratio,
        maximum_ratio=weather_input.maximum_ratio,
        required_feature_ids=weather_input.required_feature_ids,
        feature_rules_json=_decimal_to_json_safe(
            [fr.model_dump() for fr in weather_input.feature_rules]
        ),
        missing_feature_policy=weather_input.missing_feature_policy,
        config_hash=weather_input.config_hash,
        available_at_local_date=weather_input.available_at_local_date,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        effective_from=weather_input.effective_from,
        effective_to=weather_input.effective_to,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime.now(UTC),
        source_system=weather_input.source_system,
        source_record_key=weather_input.source_record_key,
        source_version=weather_input.source_version,
        row_hash=row_hash,
        superseded_by_id=None,
    )
    session.add(parent_row)
    await session.flush()

    event = await _create_initial_draft_event(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=stable_key,
        business_version=weather_input.rule_version,
        revision=weather_input.revision,
        business_row_hash=row_hash,
        available_at=weather_input.available_at_local_date,
    )

    return AuthorityCreateResult(
        authority_id=parent_row.id,
        row_hash=row_hash,
        created=True,
        lifecycle_event_id=event.id,
    )


# ══════════════════════════════════════════════════════════════════════
#  EXACT LOAD: Weather Rule Config Version
# ══════════════════════════════════════════════════════════════════════


async def load_weather_rule_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
) -> AuthorityLoadResult:
    """Load a weather rule config by ID, verify hash and lifecycle."""
    stmt = select(Task9WeatherRuleConfigVersion).where(
        Task9WeatherRuleConfigVersion.id == authority_id
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            lookup_key=str(authority_id),
        )

    stable_key = _stable_key_from_orm_weather(row)

    from backend.app.harvest_state.authority_schemas import (
        Task9WeatherRuleSemanticInput as WSI,
    )

    # feature_rules_json is stored as a list of dicts; need to reconstruct
    # Pydantic models for the semantic input.  The canonical builder handles
    # raw dicts as well since it just accesses .feature_id, .bands etc.
    # For hash verification we pass the raw JSON back through the schema.
    try:
        reconstructed = WSI(
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
    except ValueError as exc:
        if "WEATHER_RULE_CONFIG_HASH_MISMATCH" in str(exc):
            raise WeatherRuleConfigHashMismatchError(
                expected_hash="recomputed",
                actual_hash=row.config_hash,
            ) from exc
        raise
    recomputed = make_authority_row_hash(reconstructed)
    if recomputed != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            authority_stable_key=stable_key,
            expected_hash=recomputed,
            actual_hash=row.row_hash,
        )

    # Verify config_hash
    if reconstructed.config_hash != row.config_hash:
        raise WeatherRuleConfigHashMismatchError(
            expected_hash=reconstructed.config_hash,
            actual_hash=row.config_hash,
        )

    # Verify lifecycle chain
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=stable_key,
        business_version=row.rule_version,
        revision=row.revision,
        business_row_hash=row.row_hash,
        authority_status=row.status,
        authority_consumable_from=row.consumable_from_local_date,
        authority_consumable_to=row.consumable_to_local_date,
        authority_superseded_by_id=row.superseded_by_id,
    )

    return AuthorityLoadResult(
        authority_id=row.id,
        row_hash=row.row_hash,
        status=row.status,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
    )


# ══════════════════════════════════════════════════════════════════════
#  CREATE-OR-LOAD: Run Parameter Package
# ══════════════════════════════════════════════════════════════════════


async def create_or_load_run_parameter_package(
    session: AsyncSession,
    *,
    package_input: Task9RunParameterPackageSemanticInput,
    holiday_calendar: Task9HolidayCalendarSemanticBundle,
    weather_rule: Task9WeatherRuleSemanticInput,
) -> AuthorityCreateResult:
    """Create or load a run-parameter package with mandatory dependencies.

    Before inserting, exact-loads holiday + weather dependencies and verifies:
    - Dependency hashes and status (active or draft within same transaction).
    - Timezone/scope consistency.
    """
    # Exact-load dependencies
    holiday_hash = make_authority_row_hash(holiday_calendar)
    weather_hash = make_authority_row_hash(weather_rule)

    # Verify dependency hashes exist in DB (or will be created in this txn)
    holiday_stable_key = build_holiday_calendar_stable_key(
        Task9HolidayCalendarSemanticInput(
            **holiday_calendar.model_dump(exclude={"dates"}),
        )
    )
    weather_stable_key = build_weather_rule_stable_key(weather_rule)

    # Look up holiday
    holiday_stmt = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.season_id == holiday_calendar.season_id,
        Task9HolidayCalendarVersion.calendar_code == holiday_calendar.calendar_code,
        Task9HolidayCalendarVersion.lifecycle_timezone_name
        == holiday_calendar.lifecycle_timezone_name,
        Task9HolidayCalendarVersion.calendar_version == holiday_calendar.calendar_version,
        Task9HolidayCalendarVersion.revision == holiday_calendar.revision,
    )
    holiday_result = await session.execute(holiday_stmt)
    holiday_row = holiday_result.scalar_one_or_none()
    if holiday_row is None:
        raise DependencyNotFoundError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            authority_stable_key=holiday_stable_key,
        )

    # Verify holiday hash matches
    if holiday_row.row_hash != holiday_hash:
        raise HolidayCalendarHashMismatchError(
            expected_hash=holiday_hash,
            actual_hash=holiday_row.row_hash,
        )

    # Look up weather
    weather_stmt = select(Task9WeatherRuleConfigVersion).where(
        Task9WeatherRuleConfigVersion.rule_code == weather_rule.rule_code,
        Task9WeatherRuleConfigVersion.lifecycle_timezone_name
        == weather_rule.lifecycle_timezone_name,
        Task9WeatherRuleConfigVersion.rule_version == weather_rule.rule_version,
        Task9WeatherRuleConfigVersion.revision == weather_rule.revision,
    )
    weather_result = await session.execute(weather_stmt)
    weather_row = weather_result.scalar_one_or_none()
    if weather_row is None:
        raise DependencyNotFoundError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            authority_stable_key=weather_stable_key,
        )

    if weather_row.row_hash != weather_hash:
        raise WeatherRuleConfigHashMismatchError(
            expected_hash=weather_hash,
            actual_hash=weather_row.row_hash,
        )

    # Build verified weather from PERSISTED columns for canonical hash verification
    from backend.app.harvest_state.authority_schemas import (
        Task9WeatherRuleSemanticInput as WSI,
    )

    try:
        verified_weather = WSI(
            rule_code=weather_row.rule_code,
            rule_version=weather_row.rule_version,
            revision=weather_row.revision,
            lifecycle_timezone_name=weather_row.lifecycle_timezone_name,
            combination_method=weather_row.combination_method,
            minimum_ratio=weather_row.minimum_ratio,
            maximum_ratio=weather_row.maximum_ratio,
            required_feature_ids=weather_row.required_feature_ids,
            feature_rules=weather_row.feature_rules_json,
            missing_feature_policy=weather_row.missing_feature_policy,
            config_hash=weather_row.config_hash,
            effective_from=weather_row.effective_from,
            effective_to=weather_row.effective_to,
            available_at_local_date=weather_row.available_at_local_date,
            consumable_from_local_date=weather_row.consumable_from_local_date,
            consumable_to_local_date=weather_row.consumable_to_local_date,
            superseded_by_id=weather_row.superseded_by_id,
            status=weather_row.status,
            status_changed_at=weather_row.status_changed_at,
            source_system=weather_row.source_system,
            source_record_key=weather_row.source_record_key,
            source_version=weather_row.source_version,
        )
    except ValueError as exc:
        if "WEATHER_RULE_CONFIG_HASH_MISMATCH" in str(exc):
            raise WeatherRuleConfigHashMismatchError(
                expected_hash="recomputed",
                actual_hash=weather_row.config_hash,
            ) from exc
        raise

    # Verify weather canonical hashes
    verified_weather_row_hash = make_authority_row_hash(verified_weather)
    if verified_weather_row_hash != weather_row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            authority_stable_key=weather_stable_key,
            expected_hash=verified_weather_row_hash,
            actual_hash=weather_row.row_hash,
        )
    if verified_weather.config_hash != weather_row.config_hash:
        raise WeatherRuleConfigHashMismatchError(
            expected_hash=verified_weather.config_hash,
            actual_hash=weather_row.config_hash,
        )

    # Verify dependency status is compatible (active or draft)
    dep_entries: list[tuple[Any, AuthorityFamily, str]] = [
        (
            holiday_row,
            AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            holiday_stable_key,
        ),
        (
            weather_row,
            AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            weather_stable_key,
        ),
    ]
    for dep_row, dep_family, dep_key in dep_entries:
        if dep_row.status not in (
            AuthorityStatus.ACTIVE,
            AuthorityStatus.DRAFT,
        ):
            raise RunParameterDependencyStatusConflictError(
                details={
                    "dependency_family": dep_family.value,
                    "dependency_status": dep_row.status,
                    "dependency_stable_key": dep_key,
                }
            )

    # Verify timezone consistency
    pkg_tz = package_input.destination_factory_timezone
    if pkg_tz != holiday_row.lifecycle_timezone_name:
        raise RunParameterDependencyTimezoneConflictError(
            details={
                "package_timezone": pkg_tz,
                "holiday_timezone": holiday_row.lifecycle_timezone_name,
            }
        )
    if pkg_tz != weather_row.lifecycle_timezone_name:
        raise RunParameterDependencyTimezoneConflictError(
            details={
                "package_timezone": pkg_tz,
                "weather_timezone": weather_row.lifecycle_timezone_name,
            }
        )

    # Now compute package hash with verified dependencies
    # Build verified holiday bundle for the canonical builder
    from backend.app.harvest_state.authority_schemas import (
        Task9HolidayCalendarSemanticBundle as HBundle,
    )

    date_stmt = (
        select(Task9HolidayCalendarDate)
        .where(Task9HolidayCalendarDate.holiday_calendar_version_id == holiday_row.id)
        .order_by(
            Task9HolidayCalendarDate.holiday_date,
            Task9HolidayCalendarDate.holiday_code,
        )
    )
    date_result = await session.execute(date_stmt)
    persisted_dates = list(date_result.scalars().all())
    verified_holiday = HBundle(
        season_id=holiday_row.season_id,
        calendar_code=holiday_row.calendar_code,
        calendar_version=holiday_row.calendar_version,
        revision=holiday_row.revision,
        calendar_hash=holiday_row.calendar_hash,
        region_scope=holiday_row.region_scope,
        lifecycle_timezone_name=holiday_row.lifecycle_timezone_name,
        available_at_local_date=holiday_row.available_at_local_date,
        consumable_from_local_date=holiday_row.consumable_from_local_date,
        consumable_to_local_date=holiday_row.consumable_to_local_date,
        superseded_by_id=holiday_row.superseded_by_id,
        status=holiday_row.status,
        status_changed_at=holiday_row.status_changed_at,
        source_system=holiday_row.source_system,
        source_record_key=holiday_row.source_record_key,
        source_version=holiday_row.source_version,
        dates=[
            Task9HolidayCalendarDateSchema(
                holiday_date=d.holiday_date,
                holiday_code=d.holiday_code,
                holiday_name=d.holiday_name,
            )
            for d in persisted_dates
        ],
    )

    # Verify holiday canonical hashes
    unique_holiday_dates = sorted({d.holiday_date for d in persisted_dates})
    expected_cal_hash = make_holiday_calendar_hash(
        holiday_calendar_version=holiday_row.calendar_version,
        holiday_dates=unique_holiday_dates,
    )
    if holiday_row.calendar_hash != expected_cal_hash:
        raise HolidayCalendarHashMismatchError(
            expected_hash=expected_cal_hash,
            actual_hash=holiday_row.calendar_hash,
        )
    verified_holiday_row_hash = make_authority_row_hash(verified_holiday)
    if verified_holiday_row_hash != holiday_row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            authority_stable_key=holiday_stable_key,
            expected_hash=verified_holiday_row_hash,
            actual_hash=holiday_row.row_hash,
        )

    # Verify lifecycle chains for both dependencies
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=holiday_stable_key,
        business_version=holiday_row.calendar_version,
        revision=holiday_row.revision,
        business_row_hash=holiday_row.row_hash,
    )
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=weather_stable_key,
        business_version=weather_row.rule_version,
        revision=weather_row.revision,
        business_row_hash=weather_row.row_hash,
    )

    row_hash = make_authority_row_hash(
        package_input,
        holiday_calendar=verified_holiday,
        weather_rule=verified_weather,
    )
    stable_key = build_run_parameter_package_stable_key(package_input)

    lock_key = _advisory_lock_key(
        AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key,
        package_input.package_version,
        package_input.revision,
    )
    await _acquire_advisory_lock(session, lock_key)

    # Lookup by UQ
    stmt = select(Task9RunParameterPackage).where(
        Task9RunParameterPackage.season_id == package_input.season_id,
        Task9RunParameterPackage.destination_factory_id == package_input.destination_factory_id,
        Task9RunParameterPackage.farm_scope_key == package_input.farm_scope_key,
        Task9RunParameterPackage.package_version == package_input.package_version,
        Task9RunParameterPackage.revision == package_input.revision,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Recompute hash from persisted columns
        existing_holiday_stmt = select(Task9HolidayCalendarVersion).where(
            Task9HolidayCalendarVersion.id == existing.holiday_calendar_version_id
        )
        existing_holiday_result = await session.execute(existing_holiday_stmt)
        existing_holiday = existing_holiday_result.scalar_one_or_none()
        if existing_holiday is None:
            raise AuthorityNotFoundError(
                authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                lookup_key=f"holiday_missing:{existing.id}",
            )

        existing_weather_stmt = select(Task9WeatherRuleConfigVersion).where(
            Task9WeatherRuleConfigVersion.id == existing.weather_rule_config_version_id
        )
        existing_weather_result = await session.execute(existing_weather_stmt)
        existing_weather = existing_weather_result.scalar_one_or_none()
        if existing_weather is None:
            raise AuthorityNotFoundError(
                authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                lookup_key=f"weather_missing:{existing.id}",
            )

        from backend.app.harvest_state.authority_schemas import (
            Task9WeatherRuleSemanticInput as WSI,
        )

        # Rebuild verified holiday for existing
        existing_date_stmt = (
            select(Task9HolidayCalendarDate)
            .where(Task9HolidayCalendarDate.holiday_calendar_version_id == existing_holiday.id)
            .order_by(
                Task9HolidayCalendarDate.holiday_date,
                Task9HolidayCalendarDate.holiday_code,
            )
        )
        existing_date_result = await session.execute(existing_date_stmt)
        existing_persisted_dates = list(existing_date_result.scalars().all())
        verified_existing_holiday = HBundle(
            season_id=existing_holiday.season_id,
            calendar_code=existing_holiday.calendar_code,
            calendar_version=existing_holiday.calendar_version,
            revision=existing_holiday.revision,
            calendar_hash=existing_holiday.calendar_hash,
            region_scope=existing_holiday.region_scope,
            lifecycle_timezone_name=existing_holiday.lifecycle_timezone_name,
            available_at_local_date=existing_holiday.available_at_local_date,
            consumable_from_local_date=existing_holiday.consumable_from_local_date,
            consumable_to_local_date=existing_holiday.consumable_to_local_date,
            superseded_by_id=existing_holiday.superseded_by_id,
            status=existing_holiday.status,
            status_changed_at=existing_holiday.status_changed_at,
            source_system=existing_holiday.source_system,
            source_record_key=existing_holiday.source_record_key,
            source_version=existing_holiday.source_version,
            dates=[
                Task9HolidayCalendarDateSchema(
                    holiday_date=d.holiday_date,
                    holiday_code=d.holiday_code,
                    holiday_name=d.holiday_name,
                )
                for d in existing_persisted_dates
            ],
        )

        verified_existing_weather = WSI(
            rule_code=existing_weather.rule_code,
            rule_version=existing_weather.rule_version,
            revision=existing_weather.revision,
            lifecycle_timezone_name=existing_weather.lifecycle_timezone_name,
            combination_method=existing_weather.combination_method,
            minimum_ratio=existing_weather.minimum_ratio,
            maximum_ratio=existing_weather.maximum_ratio,
            required_feature_ids=existing_weather.required_feature_ids,
            feature_rules=existing_weather.feature_rules_json,
            missing_feature_policy=existing_weather.missing_feature_policy,
            config_hash=existing_weather.config_hash,
            effective_from=existing_weather.effective_from,
            effective_to=existing_weather.effective_to,
            available_at_local_date=existing_weather.available_at_local_date,
            consumable_from_local_date=existing_weather.consumable_from_local_date,
            consumable_to_local_date=existing_weather.consumable_to_local_date,
            superseded_by_id=existing_weather.superseded_by_id,
            status=existing_weather.status,
            status_changed_at=existing_weather.status_changed_at,
            source_system=existing_weather.source_system,
            source_record_key=existing_weather.source_record_key,
            source_version=existing_weather.source_version,
        )

        from backend.app.harvest_state.authority_schemas import (
            Task9RunParameterPackageSemanticInput as RPSI,
        )

        recon_pkg = RPSI(
            season_id=existing.season_id,
            destination_factory_id=existing.destination_factory_id,
            farm_scope_key=existing.farm_scope_key,
            farm_timezone=existing.farm_timezone,
            destination_factory_timezone=existing.destination_factory_timezone,
            harvest_bucket_anchor_local_time=existing.harvest_bucket_anchor_local_time,
            harvest_to_arrival_lag_days=existing.harvest_to_arrival_lag_days,
            package_version=existing.package_version,
            revision=existing.revision,
            effective_from=existing.effective_from,
            effective_to=existing.effective_to,
            available_at_local_date=existing.available_at_local_date,
            consumable_from_local_date=existing.consumable_from_local_date,
            consumable_to_local_date=existing.consumable_to_local_date,
            superseded_by_id=existing.superseded_by_id,
            status=existing.status,
            status_changed_at=existing.status_changed_at,
            source_system=existing.source_system,
            source_record_key=existing.source_record_key,
            source_version=existing.source_version,
        )
        recomputed = make_authority_row_hash(
            recon_pkg,
            holiday_calendar=verified_existing_holiday,
            weather_rule=verified_existing_weather,
        )
        if recomputed != existing.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_stable_key=stable_key,
                expected_hash=recomputed,
                actual_hash=existing.row_hash,
            )
        if row_hash != existing.row_hash:
            raise AuthorityVersionConflictError(
                authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
                authority_stable_key=stable_key,
                existing_hash=existing.row_hash,
                submitted_hash=row_hash,
            )
        return AuthorityCreateResult(
            authority_id=existing.id,
            row_hash=existing.row_hash,
            created=False,
            lifecycle_event_id=None,
        )

    # INSERT
    parent_row = Task9RunParameterPackage(
        season_id=package_input.season_id,
        destination_factory_id=package_input.destination_factory_id,
        farm_scope_key=package_input.farm_scope_key,
        farm_timezone=package_input.farm_timezone,
        destination_factory_timezone=package_input.destination_factory_timezone,
        harvest_bucket_anchor_local_time=package_input.harvest_bucket_anchor_local_time,
        harvest_to_arrival_lag_days=package_input.harvest_to_arrival_lag_days,
        holiday_calendar_version_id=holiday_row.id,
        weather_rule_config_version_id=weather_row.id,
        package_version=package_input.package_version,
        revision=package_input.revision,
        effective_from=package_input.effective_from,
        effective_to=package_input.effective_to,
        available_at_local_date=package_input.available_at_local_date,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime.now(UTC),
        source_system=package_input.source_system,
        source_record_key=package_input.source_record_key,
        source_version=package_input.source_version,
        row_hash=row_hash,
        superseded_by_id=None,
    )
    session.add(parent_row)
    await session.flush()

    event = await _create_initial_draft_event(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=stable_key,
        business_version=package_input.package_version,
        revision=package_input.revision,
        business_row_hash=row_hash,
        available_at=package_input.available_at_local_date,
    )

    return AuthorityCreateResult(
        authority_id=parent_row.id,
        row_hash=row_hash,
        created=True,
        lifecycle_event_id=event.id,
    )


# ══════════════════════════════════════════════════════════════════════
#  EXACT LOAD: Run Parameter Package
# ══════════════════════════════════════════════════════════════════════


async def load_run_parameter_package_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
) -> AuthorityLoadResult:
    """Load a run-parameter package by ID, verify hash and lifecycle."""
    stmt = select(Task9RunParameterPackage).where(Task9RunParameterPackage.id == authority_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            lookup_key=str(authority_id),
        )

    stable_key = _stable_key_from_orm_run_package(row)

    # Exact-load dependencies for hash verification
    holiday_stmt = select(Task9HolidayCalendarVersion).where(
        Task9HolidayCalendarVersion.id == row.holiday_calendar_version_id
    )
    holiday_result = await session.execute(holiday_stmt)
    holiday_row = holiday_result.scalar_one_or_none()
    if holiday_row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            lookup_key=f"holiday_missing:{row.id}",
        )

    weather_stmt = select(Task9WeatherRuleConfigVersion).where(
        Task9WeatherRuleConfigVersion.id == row.weather_rule_config_version_id
    )
    weather_result = await session.execute(weather_stmt)
    weather_row = weather_result.scalar_one_or_none()
    if weather_row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            lookup_key=f"weather_missing:{row.id}",
        )

    from backend.app.harvest_state.authority_schemas import (
        Task9HolidayCalendarSemanticBundle as HBundle,
    )
    from backend.app.harvest_state.authority_schemas import (
        Task9RunParameterPackageSemanticInput as RPSI,
    )
    from backend.app.harvest_state.authority_schemas import (
        Task9WeatherRuleSemanticInput as WSI,
    )

    # Rebuild verified holiday
    date_stmt = (
        select(Task9HolidayCalendarDate)
        .where(Task9HolidayCalendarDate.holiday_calendar_version_id == holiday_row.id)
        .order_by(
            Task9HolidayCalendarDate.holiday_date,
            Task9HolidayCalendarDate.holiday_code,
        )
    )
    date_result = await session.execute(date_stmt)
    persisted_dates = list(date_result.scalars().all())
    verified_holiday = HBundle(
        season_id=holiday_row.season_id,
        calendar_code=holiday_row.calendar_code,
        calendar_version=holiday_row.calendar_version,
        revision=holiday_row.revision,
        calendar_hash=holiday_row.calendar_hash,
        region_scope=holiday_row.region_scope,
        lifecycle_timezone_name=holiday_row.lifecycle_timezone_name,
        available_at_local_date=holiday_row.available_at_local_date,
        consumable_from_local_date=holiday_row.consumable_from_local_date,
        consumable_to_local_date=holiday_row.consumable_to_local_date,
        superseded_by_id=holiday_row.superseded_by_id,
        status=holiday_row.status,
        status_changed_at=holiday_row.status_changed_at,
        source_system=holiday_row.source_system,
        source_record_key=holiday_row.source_record_key,
        source_version=holiday_row.source_version,
        dates=[
            Task9HolidayCalendarDateSchema(
                holiday_date=d.holiday_date,
                holiday_code=d.holiday_code,
                holiday_name=d.holiday_name,
            )
            for d in persisted_dates
        ],
    )

    verified_weather = WSI(
        rule_code=weather_row.rule_code,
        rule_version=weather_row.rule_version,
        revision=weather_row.revision,
        lifecycle_timezone_name=weather_row.lifecycle_timezone_name,
        combination_method=weather_row.combination_method,
        minimum_ratio=weather_row.minimum_ratio,
        maximum_ratio=weather_row.maximum_ratio,
        required_feature_ids=weather_row.required_feature_ids,
        feature_rules=weather_row.feature_rules_json,
        missing_feature_policy=weather_row.missing_feature_policy,
        config_hash=weather_row.config_hash,
        effective_from=weather_row.effective_from,
        effective_to=weather_row.effective_to,
        available_at_local_date=weather_row.available_at_local_date,
        consumable_from_local_date=weather_row.consumable_from_local_date,
        consumable_to_local_date=weather_row.consumable_to_local_date,
        superseded_by_id=weather_row.superseded_by_id,
        status=weather_row.status,
        status_changed_at=weather_row.status_changed_at,
        source_system=weather_row.source_system,
        source_record_key=weather_row.source_record_key,
        source_version=weather_row.source_version,
    )

    recon_pkg = RPSI(
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
    recomputed = make_authority_row_hash(
        recon_pkg,
        holiday_calendar=verified_holiday,
        weather_rule=verified_weather,
    )
    if recomputed != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=stable_key,
            expected_hash=recomputed,
            actual_hash=row.row_hash,
        )

    # Verify lifecycle chain
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=stable_key,
        business_version=row.package_version,
        revision=row.revision,
        business_row_hash=row.row_hash,
        authority_status=row.status,
        authority_consumable_from=row.consumable_from_local_date,
        authority_consumable_to=row.consumable_to_local_date,
        authority_superseded_by_id=row.superseded_by_id,
    )

    return AuthorityLoadResult(
        authority_id=row.id,
        row_hash=row.row_hash,
        status=row.status,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
    )


# ══════════════════════════════════════════════════════════════════════
#  CREATE-OR-LOAD: Initial Inventory Snapshot (bundle)
# ══════════════════════════════════════════════════════════════════════


async def create_or_load_initial_inventory(
    session: AsyncSession,
    *,
    inventory_input: Task9InitialInventorySemanticBundle,
) -> AuthorityBundleCreateResult:
    """Create or load an initial inventory snapshot with its cohorts."""
    snapshot = Task9InitialInventorySemanticInput(
        **inventory_input.model_dump(exclude={"cohorts"}),
    )
    cohorts = inventory_input.cohorts

    row_hash = make_authority_row_hash(inventory_input)
    stable_key = build_initial_inventory_stable_key(snapshot)

    lock_key = _advisory_lock_key(
        AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        stable_key,
        snapshot.snapshot_version,
        snapshot.revision,
    )
    await _acquire_advisory_lock(session, lock_key)

    # Lookup by UQ
    stmt = select(Task9InitialInventorySnapshot).where(
        Task9InitialInventorySnapshot.season_id == snapshot.season_id,
        Task9InitialInventorySnapshot.destination_factory_id == snapshot.destination_factory_id,
        Task9InitialInventorySnapshot.opening_state_date == snapshot.opening_state_date,
        Task9InitialInventorySnapshot.snapshot_version == snapshot.snapshot_version,
        Task9InitialInventorySnapshot.revision == snapshot.revision,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Recompute hash from persisted children
        cohort_stmt = (
            select(Task9InitialInventoryCohort)
            .where(Task9InitialInventoryCohort.initial_inventory_snapshot_id == existing.id)
            .order_by(Task9InitialInventoryCohort.stable_cohort_key)
        )
        cohort_result = await session.execute(cohort_stmt)
        persisted_cohorts = list(cohort_result.scalars().all())
        cohort_schemas = [
            Task9InitialInventoryCohortSchema(
                stable_cohort_key=c.stable_cohort_key,
                forecast_quantile=c.forecast_quantile,
                cohort_date=c.cohort_date,
                farm_id=c.farm_id,
                subfarm_id=c.subfarm_id,
                variety_id=c.variety_id,
                remaining_quantity_kg=c.remaining_quantity_kg,
            )
            for c in persisted_cohorts
        ]
        from backend.app.harvest_state.authority_schemas import (
            Task9InitialInventorySemanticBundle as IBundle,
        )

        recon_bundle = IBundle(
            season_id=existing.season_id,
            destination_factory_id=existing.destination_factory_id,
            opening_state_date=existing.opening_state_date,
            snapshot_version=existing.snapshot_version,
            revision=existing.revision,
            initial_opening_mature_inventory_kg=existing.initial_opening_mature_inventory_kg,
            available_at_local_date=existing.available_at_local_date,
            consumable_from_local_date=existing.consumable_from_local_date,
            consumable_to_local_date=existing.consumable_to_local_date,
            superseded_by_id=existing.superseded_by_id,
            status=existing.status,
            status_changed_at=existing.status_changed_at,
            source_system=existing.source_system,
            source_record_key=existing.source_record_key,
            source_version=existing.source_version,
            cohorts=cohort_schemas,
        )
        recomputed = make_authority_row_hash(recon_bundle)
        if recomputed != existing.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
                authority_stable_key=stable_key,
                expected_hash=recomputed,
                actual_hash=existing.row_hash,
            )
        if row_hash != existing.row_hash:
            raise AuthorityVersionConflictError(
                authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
                authority_stable_key=stable_key,
                existing_hash=existing.row_hash,
                submitted_hash=row_hash,
            )
        return AuthorityBundleCreateResult(
            parent=AuthorityCreateResult(
                authority_id=existing.id,
                row_hash=existing.row_hash,
                created=False,
                lifecycle_event_id=None,
            ),
            child_ids=[c.id for c in persisted_cohorts],
        )

    # INSERT parent
    parent_row = Task9InitialInventorySnapshot(
        season_id=snapshot.season_id,
        destination_factory_id=snapshot.destination_factory_id,
        opening_state_date=snapshot.opening_state_date,
        snapshot_version=snapshot.snapshot_version,
        revision=snapshot.revision,
        initial_opening_mature_inventory_kg=snapshot.initial_opening_mature_inventory_kg,
        available_at_local_date=snapshot.available_at_local_date,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime.now(UTC),
        source_system=snapshot.source_system,
        source_record_key=snapshot.source_record_key,
        source_version=snapshot.source_version,
        row_hash=row_hash,
        superseded_by_id=None,
    )
    session.add(parent_row)
    await session.flush()

    # INSERT children
    for c in sorted(cohorts, key=lambda x: x.stable_cohort_key):
        child_hash = make_authority_row_hash(c, parent_snapshot=snapshot)
        child = Task9InitialInventoryCohort(
            initial_inventory_snapshot_id=parent_row.id,
            stable_cohort_key=c.stable_cohort_key,
            forecast_quantile=c.forecast_quantile.value,
            cohort_date=c.cohort_date,
            farm_id=c.farm_id,
            subfarm_id=c.subfarm_id,
            variety_id=c.variety_id,
            remaining_quantity_kg=c.remaining_quantity_kg,
            row_hash=child_hash,
        )
        session.add(child)
    await session.flush()

    child_stmt = (
        select(Task9InitialInventoryCohort)
        .where(Task9InitialInventoryCohort.initial_inventory_snapshot_id == parent_row.id)
        .order_by(Task9InitialInventoryCohort.stable_cohort_key)
    )
    child_result = await session.execute(child_stmt)
    child_ids = [c.id for c in child_result.scalars().all()]

    event = await _create_initial_draft_event(
        session,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        stable_key=stable_key,
        business_version=snapshot.snapshot_version,
        revision=snapshot.revision,
        business_row_hash=row_hash,
        available_at=snapshot.available_at_local_date,
    )

    return AuthorityBundleCreateResult(
        parent=AuthorityCreateResult(
            authority_id=parent_row.id,
            row_hash=row_hash,
            created=True,
            lifecycle_event_id=event.id,
        ),
        child_ids=child_ids,
    )


# ══════════════════════════════════════════════════════════════════════
#  EXACT LOAD: Initial Inventory Snapshot (bundle)
# ══════════════════════════════════════════════════════════════════════


async def load_initial_inventory_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
) -> AuthorityBundleLoadResult:
    """Load an initial inventory snapshot by ID, verify hashes and lifecycle."""
    stmt = select(Task9InitialInventorySnapshot).where(
        Task9InitialInventorySnapshot.id == authority_id
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
            lookup_key=str(authority_id),
        )

    stable_key = _stable_key_from_orm_initial_inventory(row)

    cohort_stmt = (
        select(Task9InitialInventoryCohort)
        .where(Task9InitialInventoryCohort.initial_inventory_snapshot_id == row.id)
        .order_by(Task9InitialInventoryCohort.stable_cohort_key)
    )
    cohort_result = await session.execute(cohort_stmt)
    persisted_cohorts = list(cohort_result.scalars().all())
    cohort_schemas = [
        Task9InitialInventoryCohortSchema(
            stable_cohort_key=c.stable_cohort_key,
            forecast_quantile=c.forecast_quantile,
            cohort_date=c.cohort_date,
            farm_id=c.farm_id,
            subfarm_id=c.subfarm_id,
            variety_id=c.variety_id,
            remaining_quantity_kg=c.remaining_quantity_kg,
        )
        for c in persisted_cohorts
    ]

    from backend.app.harvest_state.authority_schemas import (
        Task9InitialInventorySemanticBundle as IBundle,
    )

    recon_bundle = IBundle(
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
        cohorts=cohort_schemas,
    )
    recomputed = make_authority_row_hash(recon_bundle)
    if recomputed != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
            authority_stable_key=stable_key,
            expected_hash=recomputed,
            actual_hash=row.row_hash,
        )

    # Verify cohort hashes
    snapshot_input = Task9InitialInventorySemanticInput(
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
    )
    for c, cs in zip(persisted_cohorts, cohort_schemas, strict=True):
        expected_hash = make_authority_row_hash(cs, parent_snapshot=snapshot_input)
        if c.row_hash != expected_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
                authority_stable_key=stable_key,
                expected_hash=expected_hash,
                actual_hash=c.row_hash,
            )

    # Verify lifecycle chain
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT,
        stable_key=stable_key,
        business_version=row.snapshot_version,
        revision=row.revision,
        business_row_hash=row.row_hash,
        authority_status=row.status,
        authority_consumable_from=row.consumable_from_local_date,
        authority_consumable_to=row.consumable_to_local_date,
        authority_superseded_by_id=row.superseded_by_id,
    )

    return AuthorityBundleLoadResult(
        parent=AuthorityLoadResult(
            authority_id=row.id,
            row_hash=row.row_hash,
            status=row.status,
            consumable_from_local_date=row.consumable_from_local_date,
            consumable_to_local_date=row.consumable_to_local_date,
            superseded_by_id=row.superseded_by_id,
        ),
        child_hashes=[c.row_hash for c in persisted_cohorts],
    )


# ══════════════════════════════════════════════════════════════════════
#  CREATE-OR-LOAD: Mature Inventory Loss Authority
# ══════════════════════════════════════════════════════════════════════


async def create_or_load_mature_loss(
    session: AsyncSession,
    *,
    loss_input: Task9MatureLossSemanticInput,
) -> AuthorityCreateResult:
    """Create or load a mature inventory loss authority."""
    row_hash = make_authority_row_hash(loss_input)
    stable_key = build_mature_inventory_loss_stable_key(loss_input)

    lock_key = _advisory_lock_key(
        AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        stable_key,
        loss_input.loss_version,
        loss_input.revision,
    )
    await _acquire_advisory_lock(session, lock_key)

    # Lookup by UQ
    stmt = select(Task9MatureInventoryLossAuthority).where(
        Task9MatureInventoryLossAuthority.season_id == loss_input.season_id,
        Task9MatureInventoryLossAuthority.destination_factory_id
        == loss_input.destination_factory_id,
        Task9MatureInventoryLossAuthority.state_date == loss_input.state_date,
        Task9MatureInventoryLossAuthority.capacity_pool_code == loss_input.capacity_pool_code,
        Task9MatureInventoryLossAuthority.forecast_quantile == loss_input.forecast_quantile.value,
        Task9MatureInventoryLossAuthority.loss_version == loss_input.loss_version,
        Task9MatureInventoryLossAuthority.revision == loss_input.revision,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        from backend.app.harvest_state.authority_schemas import (
            Task9MatureLossSemanticInput as MLSI,
        )

        reconstructed = MLSI(
            season_id=existing.season_id,
            destination_factory_id=existing.destination_factory_id,
            state_date=existing.state_date,
            capacity_pool_code=existing.capacity_pool_code,
            forecast_quantile=existing.forecast_quantile,
            loss_version=existing.loss_version,
            revision=existing.revision,
            mature_inventory_loss_quantity_kg=existing.mature_inventory_loss_quantity_kg,
            available_at_local_date=existing.available_at_local_date,
            consumable_from_local_date=existing.consumable_from_local_date,
            consumable_to_local_date=existing.consumable_to_local_date,
            superseded_by_id=existing.superseded_by_id,
            status=existing.status,
            status_changed_at=existing.status_changed_at,
            source_system=existing.source_system,
            source_record_key=existing.source_record_key,
            source_version=existing.source_version,
        )
        recomputed = make_authority_row_hash(reconstructed)
        if recomputed != existing.row_hash:
            raise AuthorityHashConflictError(
                authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                authority_stable_key=stable_key,
                expected_hash=recomputed,
                actual_hash=existing.row_hash,
            )
        if row_hash != existing.row_hash:
            raise AuthorityVersionConflictError(
                authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
                authority_stable_key=stable_key,
                existing_hash=existing.row_hash,
                submitted_hash=row_hash,
            )
        return AuthorityCreateResult(
            authority_id=existing.id,
            row_hash=existing.row_hash,
            created=False,
            lifecycle_event_id=None,
        )

    # INSERT
    parent_row = Task9MatureInventoryLossAuthority(
        season_id=loss_input.season_id,
        destination_factory_id=loss_input.destination_factory_id,
        state_date=loss_input.state_date,
        capacity_pool_code=loss_input.capacity_pool_code,
        forecast_quantile=loss_input.forecast_quantile.value,
        loss_version=loss_input.loss_version,
        revision=loss_input.revision,
        mature_inventory_loss_quantity_kg=loss_input.mature_inventory_loss_quantity_kg,
        available_at_local_date=loss_input.available_at_local_date,
        consumable_from_local_date=None,
        consumable_to_local_date=None,
        status=AuthorityStatus.DRAFT,
        status_changed_at=datetime.now(UTC),
        source_system=loss_input.source_system,
        source_record_key=loss_input.source_record_key,
        source_version=loss_input.source_version,
        row_hash=row_hash,
        superseded_by_id=None,
    )
    session.add(parent_row)
    await session.flush()

    event = await _create_initial_draft_event(
        session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        stable_key=stable_key,
        business_version=loss_input.loss_version,
        revision=loss_input.revision,
        business_row_hash=row_hash,
        available_at=loss_input.available_at_local_date,
    )

    return AuthorityCreateResult(
        authority_id=parent_row.id,
        row_hash=row_hash,
        created=True,
        lifecycle_event_id=event.id,
    )


# ══════════════════════════════════════════════════════════════════════
#  EXACT LOAD: Mature Inventory Loss Authority
# ══════════════════════════════════════════════════════════════════════


async def load_mature_loss_by_id(
    session: AsyncSession,
    *,
    authority_id: int,
) -> AuthorityLoadResult:
    """Load a mature inventory loss authority by ID, verify hash and lifecycle."""
    stmt = select(Task9MatureInventoryLossAuthority).where(
        Task9MatureInventoryLossAuthority.id == authority_id
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            lookup_key=str(authority_id),
        )

    stable_key = _stable_key_from_orm_mature_loss(row)

    from backend.app.harvest_state.authority_schemas import (
        Task9MatureLossSemanticInput as MLSI,
    )

    reconstructed = MLSI(
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
    recomputed = make_authority_row_hash(reconstructed)
    if recomputed != row.row_hash:
        raise AuthorityHashConflictError(
            authority_family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
            authority_stable_key=stable_key,
            expected_hash=recomputed,
            actual_hash=row.row_hash,
        )

    # Verify lifecycle chain
    await _verify_lifecycle_chain(
        session,
        family=AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY,
        stable_key=stable_key,
        business_version=row.loss_version,
        revision=row.revision,
        business_row_hash=row.row_hash,
        authority_status=row.status,
        authority_consumable_from=row.consumable_from_local_date,
        authority_consumable_to=row.consumable_to_local_date,
        authority_superseded_by_id=row.superseded_by_id,
    )

    return AuthorityLoadResult(
        authority_id=row.id,
        row_hash=row.row_hash,
        status=row.status,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
    )


# ══════════════════════════════════════════════════════════════════════
#  LIFECYCLE TRANSITIONS
# ══════════════════════════════════════════════════════════════════════

# Map family → ORM model class
_FAMILY_MODEL_MAP: dict[AuthorityFamily, type[Base]] = {
    AuthorityFamily.CAPACITY_POOL_DEFINITION: Task9CapacityPoolDefinition,
    AuthorityFamily.DAILY_CAPACITY: Task9DailyCapacityAuthority,
    AuthorityFamily.HOLIDAY_CALENDAR_VERSION: Task9HolidayCalendarVersion,
    AuthorityFamily.WEATHER_RULE_CONFIG_VERSION: Task9WeatherRuleConfigVersion,
    AuthorityFamily.RUN_PARAMETER_PACKAGE: Task9RunParameterPackage,
    AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT: Task9InitialInventorySnapshot,
    AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY: Task9MatureInventoryLossAuthority,
}


async def _load_for_update(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    authority_id: int,
) -> Any:
    """SELECT ... FOR UPDATE on the authority row."""
    model_cls = _FAMILY_MODEL_MAP[family]
    stmt = (
        select(model_cls)
        .where(model_cls.id == authority_id)  # type: ignore[attr-defined]
        .with_for_update()
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthorityNotFoundError(
            authority_family=family,
            lookup_key=str(authority_id),
        )
    return row


async def _resolve_stable_key_and_version(
    family: AuthorityFamily,
    row: Any,
) -> tuple[str, str, int]:
    """Return (stable_key, business_version, revision) for an ORM row."""
    stable_key = _stable_key_from_orm(family, row)
    version = _business_version_from_orm(family, row)
    revision = _revision_from_orm(family, row)
    return stable_key, version, revision


async def _validate_transition(
    current_status: str,
    target_status: str,
    family: AuthorityFamily,
    stable_key: str,
) -> None:
    """Validate that a lifecycle transition is allowed."""
    allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise LifecycleTransitionInvalidError(
            authority_family=family,
            authority_stable_key=stable_key,
            current_status=current_status,
            target_status=target_status,
        )


async def activate_authority(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    authority_id: int,
    activation_boundary: date,
) -> LifecycleTransitionResult:
    """Activate a draft authority.

    1. SELECT ... FOR UPDATE
    2. Validate current status = draft
    3. UPDATE status=active, consumable_from=boundary, status_changed_at=now
    4. Create lifecycle event
    """
    row = await _load_for_update(session, family=family, authority_id=authority_id)
    stable_key, version, revision = await _resolve_stable_key_and_version(family, row)

    await _validate_transition(row.status, AuthorityStatus.ACTIVE, family, stable_key)

    # P0-5: Pre-mutation boundary validation
    if (
        row.available_at_local_date is not None
        and activation_boundary < row.available_at_local_date
    ):
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "activation_boundary_before_available_at",
                "activation_boundary": str(activation_boundary),
                "available_at_local_date": str(row.available_at_local_date),
            },
        )
    if row.consumable_from_local_date is not None:
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "consumable_from_already_set_on_draft",
                "current_consumable_from": str(row.consumable_from_local_date),
            },
        )
    if row.consumable_to_local_date is not None:
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "consumable_to_already_set_on_draft",
                "current_consumable_to": str(row.consumable_to_local_date),
            },
        )
    if row.superseded_by_id is not None:
        raise LifecycleTransitionInvalidError(
            authority_family=family,
            authority_stable_key=stable_key,
            current_status=row.status,
            target_status="active_draft_has_superseded_by",
        )

    old_consumable_from = row.consumable_from_local_date
    old_consumable_to = row.consumable_to_local_date
    now = datetime.now(UTC)

    # Single UPDATE
    row.status = AuthorityStatus.ACTIVE
    row.status_changed_at = now
    row.consumable_from_local_date = activation_boundary
    row.consumable_to_local_date = None  # open interval
    await session.flush()

    seq = await _next_lifecycle_sequence(
        session,
        family=family,
        stable_key=stable_key,
        business_version=version,
        revision=revision,
    )
    event = await _write_lifecycle_event(
        session,
        family=family,
        stable_key=stable_key,
        business_version=version,
        revision=revision,
        business_row_hash=row.row_hash,
        transition_sequence=seq,
        old_status=AuthorityStatus.DRAFT,
        new_status=AuthorityStatus.ACTIVE,
        old_consumable_from=old_consumable_from,
        old_consumable_to=old_consumable_to,
        new_consumable_from=activation_boundary,
        new_consumable_to=None,
        transitioned_at=now,
    )

    return LifecycleTransitionResult(
        authority_id=row.id,
        new_status=AuthorityStatus.ACTIVE,
        lifecycle_event_id=event.id,
        new_consumable_from=activation_boundary,
        new_consumable_to=None,
    )


async def cancel_authority(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    authority_id: int,
) -> LifecycleTransitionResult:
    """Cancel a draft authority."""
    row = await _load_for_update(session, family=family, authority_id=authority_id)
    stable_key, version, revision = await _resolve_stable_key_and_version(family, row)

    await _validate_transition(row.status, AuthorityStatus.CANCELLED, family, stable_key)

    old_consumable_from = row.consumable_from_local_date
    old_consumable_to = row.consumable_to_local_date
    now = datetime.now(UTC)

    row.status = AuthorityStatus.CANCELLED
    row.status_changed_at = now
    row.consumable_from_local_date = None
    row.consumable_to_local_date = None
    await session.flush()

    seq = await _next_lifecycle_sequence(
        session,
        family=family,
        stable_key=stable_key,
        business_version=version,
        revision=revision,
    )
    event = await _write_lifecycle_event(
        session,
        family=family,
        stable_key=stable_key,
        business_version=version,
        revision=revision,
        business_row_hash=row.row_hash,
        transition_sequence=seq,
        old_status=AuthorityStatus.DRAFT,
        new_status=AuthorityStatus.CANCELLED,
        old_consumable_from=old_consumable_from,
        old_consumable_to=old_consumable_to,
        new_consumable_from=None,
        new_consumable_to=None,
        transitioned_at=now,
    )

    return LifecycleTransitionResult(
        authority_id=row.id,
        new_status=AuthorityStatus.CANCELLED,
        lifecycle_event_id=event.id,
        new_consumable_from=None,
        new_consumable_to=None,
    )


async def retire_authority(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    authority_id: int,
    retirement_boundary: date,
) -> LifecycleTransitionResult:
    """Retire an active authority.

    Before retiring holiday or weather, checks for dependency references.
    """
    row = await _load_for_update(session, family=family, authority_id=authority_id)
    stable_key, version, revision = await _resolve_stable_key_and_version(family, row)

    # Dependency protection for holiday/calendar
    if family in (
        AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
    ):
        await _check_dependency_references(
            session,
            dependency_family=family,
            dependency_id=row.id,
        )

    await _validate_transition(row.status, AuthorityStatus.RETIRED, family, stable_key)

    old_consumable_from = row.consumable_from_local_date
    old_consumable_to = row.consumable_to_local_date
    now = datetime.now(UTC)

    # P0-5: Pre-mutation boundary validation
    if old_consumable_from is None:
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "retire_requires_consumable_from",
                "family": family.value,
                "stable_key": stable_key,
            },
        )
    if retirement_boundary <= old_consumable_from:
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "retirement_boundary_not_after_consumable_from",
                "retirement_boundary": str(retirement_boundary),
                "consumable_from": str(old_consumable_from),
            },
        )
    if old_consumable_to is not None:
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "consumable_to_already_set_on_active",
                "current_consumable_to": str(old_consumable_to),
            },
        )
    if row.superseded_by_id is not None:
        raise LifecycleTransitionInvalidError(
            authority_family=family,
            authority_stable_key=stable_key,
            current_status=row.status,
            target_status="retire_active_has_superseded_by",
        )

    row.status = AuthorityStatus.RETIRED
    row.status_changed_at = now
    row.consumable_to_local_date = retirement_boundary
    await session.flush()

    seq = await _next_lifecycle_sequence(
        session,
        family=family,
        stable_key=stable_key,
        business_version=version,
        revision=revision,
    )
    event = await _write_lifecycle_event(
        session,
        family=family,
        stable_key=stable_key,
        business_version=version,
        revision=revision,
        business_row_hash=row.row_hash,
        transition_sequence=seq,
        old_status=AuthorityStatus.ACTIVE,
        new_status=AuthorityStatus.RETIRED,
        old_consumable_from=old_consumable_from,
        old_consumable_to=old_consumable_to,
        new_consumable_from=old_consumable_from,
        new_consumable_to=retirement_boundary,
        transitioned_at=now,
    )

    return LifecycleTransitionResult(
        authority_id=row.id,
        new_status=AuthorityStatus.RETIRED,
        lifecycle_event_id=event.id,
        new_consumable_from=old_consumable_from,
        new_consumable_to=retirement_boundary,
    )


# ══════════════════════════════════════════════════════════════════════
#  SUPERSESSION
# ══════════════════════════════════════════════════════════════════════


async def supersede_authority(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    old_id: int,
    new_input: Any,
    replacement_boundary: date,
    # Bundle extras (optional, used by bundle families)
    new_members: list[Task9CapacityPoolMemberSchema] | None = None,
    new_dates: list[Task9HolidayCalendarDateSchema] | None = None,
    new_cohorts: list[Task9InitialInventoryCohortSchema] | None = None,
    holiday_calendar: Task9HolidayCalendarSemanticBundle | None = None,
    weather_rule: Task9WeatherRuleSemanticInput | None = None,
) -> SupersessionResult:
    """Supersede an active authority with a new draft.

    1. Lock old row (FOR UPDATE).
    2. Verify scope match.
    3. Dependency protection for holiday/weather.
    4. Create new draft + children + initial event.
    5. UPDATE old: status=superseded, superseded_by_id=new.id, consumable_to=boundary.
    6. UPDATE new: status=active, consumable_from=boundary.
    7. Write events for old supersession + new activation.
    """
    # (1) Lock old
    old_row = await _load_for_update(session, family=family, authority_id=old_id)
    old_stable_key, old_version, old_revision = await _resolve_stable_key_and_version(
        family, old_row
    )

    # Validate old is active
    await _validate_transition(old_row.status, AuthorityStatus.SUPERSEDED, family, old_stable_key)

    old_consumable_from = old_row.consumable_from_local_date
    old_consumable_to = old_row.consumable_to_local_date

    # P0-5: Pre-mutation boundary validation
    if old_consumable_from is None:
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "supersede_requires_consumable_from",
                "family": family.value,
                "stable_key": old_stable_key,
            },
        )
    if old_consumable_to is not None:
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "consumable_to_already_set_on_active_for_supersede",
                "current_consumable_to": str(old_consumable_to),
            },
        )
    if replacement_boundary <= old_consumable_from:
        raise AuthorityConsumabilityIntervalInvalidError(
            details={
                "reason": "replacement_boundary_not_after_consumable_from",
                "replacement_boundary": str(replacement_boundary),
                "consumable_from": str(old_consumable_from),
            },
        )

    # (3) Dependency protection
    if family in (
        AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
    ):
        await _check_dependency_references(
            session,
            dependency_family=family,
            dependency_id=old_row.id,
        )

    # (4) Create new draft
    new_result: AuthorityCreateResult | AuthorityBundleCreateResult
    if family == AuthorityFamily.CAPACITY_POOL_DEFINITION:
        bundle = new_input
        if not isinstance(bundle, Task9CapacityPoolDefinitionSemanticBundle):
            bundle = Task9CapacityPoolDefinitionSemanticBundle(**bundle.model_dump())
        new_result = await create_or_load_capacity_pool_definition(session, definition_input=bundle)
    elif family == AuthorityFamily.DAILY_CAPACITY:
        new_result = await create_or_load_daily_capacity(session, daily_input=new_input)
    elif family == AuthorityFamily.HOLIDAY_CALENDAR_VERSION:
        if new_dates is None:
            raise ValueError("new_dates required for holiday calendar supersession")
        from backend.app.harvest_state.authority_schemas import (
            Task9HolidayCalendarSemanticBundle as HBundle,
        )

        if isinstance(new_input, Task9HolidayCalendarSemanticBundle):
            bundle = new_input
        else:
            bundle = HBundle(**new_input.model_dump(), dates=new_dates)
        new_result = await create_or_load_holiday_calendar(session, calendar_input=bundle)
    elif family == AuthorityFamily.WEATHER_RULE_CONFIG_VERSION:
        new_result = await create_or_load_weather_rule(session, weather_input=new_input)
    elif family == AuthorityFamily.RUN_PARAMETER_PACKAGE:
        if holiday_calendar is None or weather_rule is None:
            raise ValueError(
                "holiday_calendar and weather_rule required for run package supersession"
            )
        new_result = await create_or_load_run_parameter_package(
            session,
            package_input=new_input,
            holiday_calendar=holiday_calendar,
            weather_rule=weather_rule,
        )
    elif family == AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT:
        if new_cohorts is None:
            raise ValueError("new_cohorts required for inventory supersession")
        from backend.app.harvest_state.authority_schemas import (
            Task9InitialInventorySemanticBundle as IBundle,
        )

        if isinstance(new_input, Task9InitialInventorySemanticBundle):
            bundle = new_input
        else:
            bundle = IBundle(**new_input.model_dump(), cohorts=new_cohorts)
        new_result = await create_or_load_initial_inventory(session, inventory_input=bundle)
    elif family == AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY:
        new_result = await create_or_load_mature_loss(session, loss_input=new_input)
    else:
        raise ValueError(f"unsupported family for supersession: {family}")

    # If the new authority already existed (idempotent), we still need to
    # link the old to it if it's in draft. But if it was already created
    # and the old is already superseded, this is a no-op.
    new_id = (
        new_result.parent.authority_id
        if isinstance(new_result, AuthorityBundleCreateResult)
        else new_result.authority_id
    )

    # (2) Verify scope match
    old_scope = _extract_scope(family, old_row)
    # We need to load the new row to extract its scope
    new_model_cls = _FAMILY_MODEL_MAP[family]
    new_stmt = select(new_model_cls).where(new_model_cls.id == new_id)  # type: ignore[attr-defined]
    new_db_result = await session.execute(new_stmt)
    new_row: Any = new_db_result.scalar_one_or_none()
    if new_row is None:
        raise AuthorityNotFoundError(
            authority_family=family,
            lookup_key=str(new_id),
        )
    new_scope = _extract_scope(family, new_row)

    # Verify scope keys match (supersession must replace within same scope)
    if old_scope != new_scope:
        raise AuthoritySupersessionScopeConflictError(
            authority_family=family,
            details={"old_scope": str(old_scope), "new_scope": str(new_scope)},
        )

    new_stable_key, new_version, new_revision = await _resolve_stable_key_and_version(
        family, new_row
    )

    now = datetime.now(UTC)

    # P0-5: Verify boundary consistency — old close == new open == replacement_boundary
    # (enforced by the UPDATE logic below; checked here for early typed error)

    # (5) UPDATE old: superseded
    old_row.status = AuthorityStatus.SUPERSEDED
    old_row.status_changed_at = now
    old_row.superseded_by_id = new_id
    old_row.consumable_to_local_date = replacement_boundary
    await session.flush()

    # Write supersession event on old
    old_seq = await _next_lifecycle_sequence(
        session,
        family=family,
        stable_key=old_stable_key,
        business_version=old_version,
        revision=old_revision,
    )
    old_event = await _write_lifecycle_event(
        session,
        family=family,
        stable_key=old_stable_key,
        business_version=old_version,
        revision=old_revision,
        business_row_hash=old_row.row_hash,
        transition_sequence=old_seq,
        old_status=AuthorityStatus.ACTIVE,
        new_status=AuthorityStatus.SUPERSEDED,
        old_consumable_from=old_consumable_from,
        old_consumable_to=old_consumable_to,
        new_consumable_from=old_consumable_from,
        new_consumable_to=replacement_boundary,
        superseded_by_stable_key=new_stable_key,
        superseded_by_business_version=new_version,
        superseded_by_revision=new_revision,
        transitioned_at=now,
    )

    # (6) UPDATE new: active
    new_row.status = AuthorityStatus.ACTIVE
    new_row.status_changed_at = now
    new_row.consumable_from_local_date = replacement_boundary
    new_row.consumable_to_local_date = None
    await session.flush()

    # Write activation event on new
    new_seq = await _next_lifecycle_sequence(
        session,
        family=family,
        stable_key=new_stable_key,
        business_version=new_version,
        revision=new_revision,
    )
    new_event = await _write_lifecycle_event(
        session,
        family=family,
        stable_key=new_stable_key,
        business_version=new_version,
        revision=new_revision,
        business_row_hash=new_row.row_hash,
        transition_sequence=new_seq,
        old_status=AuthorityStatus.DRAFT,
        new_status=AuthorityStatus.ACTIVE,
        old_consumable_from=None,
        old_consumable_to=None,
        new_consumable_from=replacement_boundary,
        new_consumable_to=None,
        transitioned_at=now,
    )

    # Build the result
    new_create: AuthorityCreateResult
    if isinstance(new_result, AuthorityBundleCreateResult):
        new_create = new_result.parent
    elif new_result.created:
        new_create = new_result
    else:
        new_create = AuthorityCreateResult(
            authority_id=new_result.authority_id,
            row_hash=new_result.row_hash,
            created=False,
            lifecycle_event_id=None,
        )

    return SupersessionResult(
        old=LifecycleTransitionResult(
            authority_id=old_id,
            new_status=AuthorityStatus.SUPERSEDED,
            lifecycle_event_id=old_event.id,
            new_consumable_from=old_consumable_from,
            new_consumable_to=replacement_boundary,
        ),
        new=new_create,
        new_activation=LifecycleTransitionResult(
            authority_id=new_id,
            new_status=AuthorityStatus.ACTIVE,
            lifecycle_event_id=new_event.id,
            new_consumable_from=replacement_boundary,
            new_consumable_to=None,
        ),
    )


# ══════════════════════════════════════════════════════════════════════
#  RUN-PACKAGE DEPENDENCY-AWARE REPLACEMENT
# ══════════════════════════════════════════════════════════════════════


async def replace_run_package_with_dependencies(
    session: AsyncSession,
    *,
    old_package_id: int,
    new_package_input: Task9RunParameterPackageSemanticInput,
    new_holiday_input: Task9HolidayCalendarSemanticBundle,
    new_weather_input: Task9WeatherRuleSemanticInput,
    replacement_boundary: date,
) -> SupersessionResult:
    """Replace an entire run-package trio atomically.

    All six lifecycle events (3 old→superseded, 3 new→active) share the
    SAME transition timestamp so the replacement is a single logical
    atomic operation.

    Does NOT call ``supersede_authority()`` or
    ``_check_dependency_references()`` — direct UPDATEs avoid the
    circular dependency-check ordering bug where superseding a holiday
    is blocked by its own (still-active) package reference.
    """
    now = datetime.now(UTC)

    # ── (1) Lock old package FOR UPDATE ──────────────────────────────
    old_pkg = await _load_for_update(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=old_package_id,
    )
    old_pkg_stable_key, old_pkg_version, old_pkg_revision = (
        await _resolve_stable_key_and_version(
            AuthorityFamily.RUN_PARAMETER_PACKAGE, old_pkg
        )
    )

    if old_pkg.status != AuthorityStatus.ACTIVE:
        raise LifecycleTransitionInvalidError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key=old_pkg_stable_key,
            current_status=old_pkg.status,
            target_status=AuthorityStatus.SUPERSEDED,
        )

    old_holiday_id = old_pkg.holiday_calendar_version_id
    old_weather_id = old_pkg.weather_rule_config_version_id

    # Load old dependencies FOR UPDATE
    old_holiday = await _load_for_update(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=old_holiday_id,
    )
    old_weather = await _load_for_update(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=old_weather_id,
    )

    # ── (2) Verify all three are active ──────────────────────────────
    old_holiday_stable_key, old_holiday_version, old_holiday_revision = (
        await _resolve_stable_key_and_version(
            AuthorityFamily.HOLIDAY_CALENDAR_VERSION, old_holiday
        )
    )
    old_weather_stable_key, old_weather_version, old_weather_revision = (
        await _resolve_stable_key_and_version(
            AuthorityFamily.WEATHER_RULE_CONFIG_VERSION, old_weather
        )
    )

    for dep_row, dep_family, dep_key in [
        (old_holiday, AuthorityFamily.HOLIDAY_CALENDAR_VERSION, old_holiday_stable_key),
        (old_weather, AuthorityFamily.WEATHER_RULE_CONFIG_VERSION, old_weather_stable_key),
    ]:
        if dep_row.status != AuthorityStatus.ACTIVE:
            raise RunParameterDependencyStatusConflictError(
                details={
                    "dependency_family": dep_family.value,
                    "dependency_status": dep_row.status,
                    "dependency_stable_key": dep_key,
                }
            )

    # ── (3) Create new holiday as draft ──────────────────────────────
    new_holiday_result = await create_or_load_holiday_calendar(
        session, calendar_input=new_holiday_input
    )
    new_holiday_id = new_holiday_result.parent.authority_id

    # ── (4) Create new weather as draft ──────────────────────────────
    new_weather_result = await create_or_load_weather_rule(
        session, weather_input=new_weather_input
    )
    new_weather_id = new_weather_result.authority_id

    # ── (5) Create new package as draft ──────────────────────────────
    new_pkg_result = await create_or_load_run_parameter_package(
        session,
        package_input=new_package_input,
        holiday_calendar=new_holiday_input,
        weather_rule=new_weather_input,
    )
    new_pkg_id = new_pkg_result.authority_id

    # Reload new rows for stable_key/version/resolution
    new_holiday_row = await _load_for_update(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        authority_id=new_holiday_id,
    )
    new_weather_row = await _load_for_update(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        authority_id=new_weather_id,
    )
    new_pkg_row = await _load_for_update(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        authority_id=new_pkg_id,
    )

    new_holiday_stable_key, new_holiday_version, new_holiday_revision = (
        await _resolve_stable_key_and_version(
            AuthorityFamily.HOLIDAY_CALENDAR_VERSION, new_holiday_row
        )
    )
    new_weather_stable_key, new_weather_version, new_weather_revision = (
        await _resolve_stable_key_and_version(
            AuthorityFamily.WEATHER_RULE_CONFIG_VERSION, new_weather_row
        )
    )
    new_pkg_stable_key, new_pkg_version, new_pkg_revision = (
        await _resolve_stable_key_and_version(
            AuthorityFamily.RUN_PARAMETER_PACKAGE, new_pkg_row
        )
    )

    # ── (6-8) UPDATE old trio: status=superseded ─────────────────────
    old_consumable_from_pkg = old_pkg.consumable_from_local_date
    old_consumable_to_pkg = old_pkg.consumable_to_local_date
    old_consumable_from_hol = old_holiday.consumable_from_local_date
    old_consumable_to_hol = old_holiday.consumable_to_local_date
    old_consumable_from_wx = old_weather.consumable_from_local_date
    old_consumable_to_wx = old_weather.consumable_to_local_date

    old_pkg.status = AuthorityStatus.SUPERSEDED
    old_pkg.status_changed_at = now
    old_pkg.superseded_by_id = new_pkg_id
    old_pkg.consumable_to_local_date = replacement_boundary

    old_holiday.status = AuthorityStatus.SUPERSEDED
    old_holiday.status_changed_at = now
    old_holiday.superseded_by_id = new_holiday_id
    old_holiday.consumable_to_local_date = replacement_boundary

    old_weather.status = AuthorityStatus.SUPERSEDED
    old_weather.status_changed_at = now
    old_weather.superseded_by_id = new_weather_id
    old_weather.consumable_to_local_date = replacement_boundary
    await session.flush()

    # ── (9) Write lifecycle events for old→superseded ────────────────
    old_pkg_seq = await _next_lifecycle_sequence(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=old_pkg_stable_key,
        business_version=old_pkg_version,
        revision=old_pkg_revision,
    )
    await _write_lifecycle_event(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=old_pkg_stable_key,
        business_version=old_pkg_version,
        revision=old_pkg_revision,
        business_row_hash=old_pkg.row_hash,
        transition_sequence=old_pkg_seq,
        old_status=AuthorityStatus.ACTIVE,
        new_status=AuthorityStatus.SUPERSEDED,
        old_consumable_from=old_consumable_from_pkg,
        old_consumable_to=old_consumable_to_pkg,
        new_consumable_from=old_consumable_from_pkg,
        new_consumable_to=replacement_boundary,
        superseded_by_stable_key=new_pkg_stable_key,
        superseded_by_business_version=new_pkg_version,
        superseded_by_revision=new_pkg_revision,
        transitioned_at=now,
    )

    old_hol_seq = await _next_lifecycle_sequence(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=old_holiday_stable_key,
        business_version=old_holiday_version,
        revision=old_holiday_revision,
    )
    await _write_lifecycle_event(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=old_holiday_stable_key,
        business_version=old_holiday_version,
        revision=old_holiday_revision,
        business_row_hash=old_holiday.row_hash,
        transition_sequence=old_hol_seq,
        old_status=AuthorityStatus.ACTIVE,
        new_status=AuthorityStatus.SUPERSEDED,
        old_consumable_from=old_consumable_from_hol,
        old_consumable_to=old_consumable_to_hol,
        new_consumable_from=old_consumable_from_hol,
        new_consumable_to=replacement_boundary,
        superseded_by_stable_key=new_holiday_stable_key,
        superseded_by_business_version=new_holiday_version,
        superseded_by_revision=new_holiday_revision,
        transitioned_at=now,
    )

    old_wx_seq = await _next_lifecycle_sequence(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=old_weather_stable_key,
        business_version=old_weather_version,
        revision=old_weather_revision,
    )
    await _write_lifecycle_event(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=old_weather_stable_key,
        business_version=old_weather_version,
        revision=old_weather_revision,
        business_row_hash=old_weather.row_hash,
        transition_sequence=old_wx_seq,
        old_status=AuthorityStatus.ACTIVE,
        new_status=AuthorityStatus.SUPERSEDED,
        old_consumable_from=old_consumable_from_wx,
        old_consumable_to=old_consumable_to_wx,
        new_consumable_from=old_consumable_from_wx,
        new_consumable_to=replacement_boundary,
        superseded_by_stable_key=new_weather_stable_key,
        superseded_by_business_version=new_weather_version,
        superseded_by_revision=new_weather_revision,
        transitioned_at=now,
    )

    # ── (10-12) UPDATE new trio: status=active ───────────────────────
    new_holiday_row.status = AuthorityStatus.ACTIVE
    new_holiday_row.status_changed_at = now
    new_holiday_row.consumable_from_local_date = replacement_boundary
    new_holiday_row.consumable_to_local_date = None

    new_weather_row.status = AuthorityStatus.ACTIVE
    new_weather_row.status_changed_at = now
    new_weather_row.consumable_from_local_date = replacement_boundary
    new_weather_row.consumable_to_local_date = None

    new_pkg_row.status = AuthorityStatus.ACTIVE
    new_pkg_row.status_changed_at = now
    new_pkg_row.consumable_from_local_date = replacement_boundary
    new_pkg_row.consumable_to_local_date = None
    await session.flush()

    # ── (13) Write lifecycle events for new→active ───────────────────
    new_hol_seq = await _next_lifecycle_sequence(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=new_holiday_stable_key,
        business_version=new_holiday_version,
        revision=new_holiday_revision,
    )
    await _write_lifecycle_event(
        session,
        family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
        stable_key=new_holiday_stable_key,
        business_version=new_holiday_version,
        revision=new_holiday_revision,
        business_row_hash=new_holiday_row.row_hash,
        transition_sequence=new_hol_seq,
        old_status=AuthorityStatus.DRAFT,
        new_status=AuthorityStatus.ACTIVE,
        old_consumable_from=None,
        old_consumable_to=None,
        new_consumable_from=replacement_boundary,
        new_consumable_to=None,
        transitioned_at=now,
    )

    new_wx_seq = await _next_lifecycle_sequence(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=new_weather_stable_key,
        business_version=new_weather_version,
        revision=new_weather_revision,
    )
    await _write_lifecycle_event(
        session,
        family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
        stable_key=new_weather_stable_key,
        business_version=new_weather_version,
        revision=new_weather_revision,
        business_row_hash=new_weather_row.row_hash,
        transition_sequence=new_wx_seq,
        old_status=AuthorityStatus.DRAFT,
        new_status=AuthorityStatus.ACTIVE,
        old_consumable_from=None,
        old_consumable_to=None,
        new_consumable_from=replacement_boundary,
        new_consumable_to=None,
        transitioned_at=now,
    )

    new_pkg_seq = await _next_lifecycle_sequence(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=new_pkg_stable_key,
        business_version=new_pkg_version,
        revision=new_pkg_revision,
    )
    new_pkg_event = await _write_lifecycle_event(
        session,
        family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
        stable_key=new_pkg_stable_key,
        business_version=new_pkg_version,
        revision=new_pkg_revision,
        business_row_hash=new_pkg_row.row_hash,
        transition_sequence=new_pkg_seq,
        old_status=AuthorityStatus.DRAFT,
        new_status=AuthorityStatus.ACTIVE,
        old_consumable_from=None,
        old_consumable_to=None,
        new_consumable_from=replacement_boundary,
        new_consumable_to=None,
        transitioned_at=now,
    )

    # ── (14) Integrity reload and verify ─────────────────────────────
    for check_id, check_family in [
        (old_package_id, AuthorityFamily.RUN_PARAMETER_PACKAGE),
        (old_holiday_id, AuthorityFamily.HOLIDAY_CALENDAR_VERSION),
        (old_weather_id, AuthorityFamily.WEATHER_RULE_CONFIG_VERSION),
        (new_pkg_id, AuthorityFamily.RUN_PARAMETER_PACKAGE),
        (new_holiday_id, AuthorityFamily.HOLIDAY_CALENDAR_VERSION),
        (new_weather_id, AuthorityFamily.WEATHER_RULE_CONFIG_VERSION),
    ]:
        model_cls = _FAMILY_MODEL_MAP[check_family]
        check_stmt = select(model_cls).where(model_cls.id == check_id)  # type: ignore[attr-defined]
        check_result = await session.execute(check_stmt)
        check_row = check_result.scalar_one_or_none()
        if check_row is None:
            raise AuthorityNotFoundError(
                authority_family=check_family,
                lookup_key=str(check_id),
            )

    # Verify old trio is superseded
    if old_pkg.status != AuthorityStatus.SUPERSEDED:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            lookup_key=f"not_superseded:{old_package_id}",
        )
    if old_holiday.status != AuthorityStatus.SUPERSEDED:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            lookup_key=f"not_superseded:{old_holiday_id}",
        )
    if old_weather.status != AuthorityStatus.SUPERSEDED:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            lookup_key=f"not_superseded:{old_weather_id}",
        )

    # Verify new trio is active
    if new_pkg_row.status != AuthorityStatus.ACTIVE:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            lookup_key=f"not_active:{new_pkg_id}",
        )
    if new_holiday_row.status != AuthorityStatus.ACTIVE:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            lookup_key=f"not_active:{new_holiday_id}",
        )
    if new_weather_row.status != AuthorityStatus.ACTIVE:
        raise AuthorityNotFoundError(
            authority_family=AuthorityFamily.WEATHER_RULE_CONFIG_VERSION,
            lookup_key=f"not_active:{new_weather_id}",
        )

    return SupersessionResult(
        old=LifecycleTransitionResult(
            authority_id=old_package_id,
            new_status=AuthorityStatus.SUPERSEDED,
            lifecycle_event_id=old_pkg_seq,
            new_consumable_from=old_consumable_from_pkg,
            new_consumable_to=replacement_boundary,
        ),
        new=AuthorityCreateResult(
            authority_id=new_pkg_id,
            row_hash=new_pkg_row.row_hash,
            created=new_pkg_result.created,
            lifecycle_event_id=None,
        ),
        new_activation=LifecycleTransitionResult(
            authority_id=new_pkg_id,
            new_status=AuthorityStatus.ACTIVE,
            lifecycle_event_id=new_pkg_event.id,
            new_consumable_from=replacement_boundary,
            new_consumable_to=None,
        ),
    )


# ══════════════════════════════════════════════════════════════════════
#  GENERIC EXACT-LOAD SURFACE (P0-7)
# ══════════════════════════════════════════════════════════════════════

# Family → (version column name, revision column name)
_FAMILY_VERSION_COLUMN_NAME: dict[AuthorityFamily, str] = {
    AuthorityFamily.CAPACITY_POOL_DEFINITION: "capacity_pool_version",
    AuthorityFamily.DAILY_CAPACITY: "capacity_pool_version",
    AuthorityFamily.HOLIDAY_CALENDAR_VERSION: "calendar_version",
    AuthorityFamily.WEATHER_RULE_CONFIG_VERSION: "rule_version",
    AuthorityFamily.RUN_PARAMETER_PACKAGE: "package_version",
    AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT: "snapshot_version",
    AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY: "loss_version",
}

_FAMILY_REVISION_COLUMN_NAME: dict[AuthorityFamily, str] = {
    AuthorityFamily.CAPACITY_POOL_DEFINITION: "revision",
    AuthorityFamily.DAILY_CAPACITY: "daily_capacity_revision",
    AuthorityFamily.HOLIDAY_CALENDAR_VERSION: "revision",
    AuthorityFamily.WEATHER_RULE_CONFIG_VERSION: "revision",
    AuthorityFamily.RUN_PARAMETER_PACKAGE: "revision",
    AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT: "revision",
    AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY: "revision",
}


def _AuthorityLoadResult_from_row(row: Any) -> AuthorityLoadResult:
    """Build an AuthorityLoadResult from an ORM row (generic)."""
    return AuthorityLoadResult(
        authority_id=row.id,
        row_hash=row.row_hash,
        status=row.status,
        consumable_from_local_date=row.consumable_from_local_date,
        consumable_to_local_date=row.consumable_to_local_date,
        superseded_by_id=row.superseded_by_id,
    )


async def _load_family_by_id(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    authority_id: int,
) -> AuthorityLoadResult | AuthorityBundleLoadResult:
    """Dispatch to the family-specific load_by_id function."""
    if family == AuthorityFamily.CAPACITY_POOL_DEFINITION:
        return await load_capacity_pool_definition_by_id(
            session, authority_id=authority_id
        )
    if family == AuthorityFamily.DAILY_CAPACITY:
        return await load_daily_capacity_by_id(
            session, authority_id=authority_id
        )
    if family == AuthorityFamily.HOLIDAY_CALENDAR_VERSION:
        return await load_holiday_calendar_by_id(
            session, authority_id=authority_id
        )
    if family == AuthorityFamily.WEATHER_RULE_CONFIG_VERSION:
        return await load_weather_rule_by_id(
            session, authority_id=authority_id
        )
    if family == AuthorityFamily.RUN_PARAMETER_PACKAGE:
        return await load_run_parameter_package_by_id(
            session, authority_id=authority_id
        )
    if family == AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT:
        return await load_initial_inventory_by_id(
            session, authority_id=authority_id
        )
    if family == AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY:
        return await load_mature_loss_by_id(
            session, authority_id=authority_id
        )
    raise ValueError(f"unsupported family for load: {family}")


async def load_authority_by_business_key(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
) -> AuthorityLoadResult | AuthorityBundleLoadResult:
    """Exact-load an authority by its composite business key.

    No as-of filtering, no latest selection, no ranking — the caller
    must supply the exact (stable_key, business_version, revision)
    triple.  Delegates to the family-specific ``load_by_id`` for full
    hash verification and lifecycle chain validation.
    """
    model_cls = _FAMILY_MODEL_MAP[family]
    revision_col_name = _FAMILY_REVISION_COLUMN_NAME[family]
    revision_col = getattr(model_cls, revision_col_name)

    if family == AuthorityFamily.DAILY_CAPACITY:
        # Daily capacity's "business version" is the pool definition's
        # capacity_pool_version, which lives on a joined table.
        stmt = (
            select(model_cls)
            .join(
                Task9CapacityPoolDefinition,
                Task9DailyCapacityAuthority.capacity_pool_definition_id
                == Task9CapacityPoolDefinition.id,
            )
            .where(
                Task9CapacityPoolDefinition.capacity_pool_version == business_version,
                revision_col == revision,
            )
        )
    else:
        version_col_name = _FAMILY_VERSION_COLUMN_NAME[family]
        version_col = getattr(model_cls, version_col_name)
        stmt = select(model_cls).where(
            version_col == business_version,
            revision_col == revision,
        )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    # Filter by stable_key (computed from scope columns)
    matched_row = None
    for row in rows:
        if _stable_key_from_orm(family, row) == stable_key:
            matched_row = row
            break

    if matched_row is None:
        raise AuthorityNotFoundError(
            authority_family=family,
            lookup_key=f"{stable_key}:{business_version}:{revision}",
        )

    return await _load_family_by_id(
        session, family=family, authority_id=matched_row.id  # type: ignore[attr-defined]
    )


async def load_authority_by_persistent_identity(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    stable_key: str,
    business_version: str,
    revision: int,
    row_hash: str,
) -> AuthorityLoadResult | AuthorityBundleLoadResult:
    """Exact-load by business key, then verify the row_hash matches.

    Combines the business-key lookup with a hash identity check so the
    caller can confirm it is loading the exact canonical payload it
    expects (no silent version drift).
    """
    result = await load_authority_by_business_key(
        session,
        family=family,
        stable_key=stable_key,
        business_version=business_version,
        revision=revision,
    )

    # Extract the parent row_hash from the result
    result_hash = (
        result.parent.row_hash
        if isinstance(result, AuthorityBundleLoadResult)
        else result.row_hash
    )
    if result_hash != row_hash:
        raise AuthorityHashConflictError(
            authority_family=family,
            authority_stable_key=stable_key,
            expected_hash=row_hash,
            actual_hash=result_hash,
        )

    return result


async def load_authority_by_row_hash(
    session: AsyncSession,
    *,
    family: AuthorityFamily,
    row_hash: str,
) -> AuthorityLoadResult | AuthorityBundleLoadResult:
    """Exact-load by row hash.

    If multiple rows share the same hash the result is ambiguous →
    ``AUTHORITY_HASH_CONFLICT``.  If no row matches →
    ``AUTHORITY_NOT_FOUND``.
    """
    model_cls = _FAMILY_MODEL_MAP[family]
    stmt = select(model_cls).where(model_cls.row_hash == row_hash)  # type: ignore[attr-defined]
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    if len(rows) == 0:
        raise AuthorityNotFoundError(
            authority_family=family,
            lookup_key=f"row_hash:{row_hash}",
        )
    if len(rows) > 1:
        raise AuthorityHashConflictError(
            authority_family=family,
            expected_hash=row_hash,
            actual_hash=f"ambiguous:{len(rows)}_rows",
        )

    return await _load_family_by_id(
        session, family=family, authority_id=rows[0].id  # type: ignore[attr-defined]
    )
