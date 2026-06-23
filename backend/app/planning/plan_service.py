from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.planning.json_types import canonical_json_value
from backend.app.planning.plan_config import ProductionPlanConfig
from backend.app.planning.plan_hashing import plan_row_hash
from backend.app.planning.plan_repository import (
    acquire_production_plan_lock,
    create_plan,
    create_replacement_plan,
    get_farm,
    get_plan_by_id,
    get_plan_by_row_hash,
    get_season,
    get_subfarm,
    get_variety,
    list_plan_versions_by_key,
)
from backend.app.planning.plan_schemas import (
    ProductionPlanIntervalConflictError,
    ProductionPlanMutationResult,
    ProductionPlanNotFoundError,
    ProductionPlanRecord,
    ProductionPlanUnavailableError,
    ProductionPlanValidationError,
    ProductionPlanVersionConflictError,
)


def _decimal_value(value: Decimal | int | float | str | None, *, field: str) -> Decimal:
    if value is None:
        raise ProductionPlanValidationError(f"{field} is required")
    if isinstance(value, Decimal):
        parsed = value
    else:
        try:
            parsed = Decimal(str(value))
        except InvalidOperation as exc:
            raise ProductionPlanValidationError(f"{field} must be a valid decimal") from exc
    if not parsed.is_finite():
        raise ProductionPlanValidationError(f"{field} must be finite")
    return parsed


def _optional_decimal_value(
    value: Decimal | int | float | str | None,
    *,
    field: str,
) -> Decimal | None:
    if value is None:
        return None
    return _decimal_value(value, field=field)


def _date_value(value: date | str | None, *, field: str) -> date:
    if value is None:
        raise ProductionPlanValidationError(f"{field} is required")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ProductionPlanValidationError(f"{field} must be an ISO date") from exc
    raise ProductionPlanValidationError(f"{field} must be an ISO date")


def _optional_date_value(value: date | str | None, *, field: str) -> date | None:
    if value is None:
        return None
    return _date_value(value, field=field)


def _validate_non_negative(value: Decimal, *, field: str) -> None:
    if value < 0:
        raise ProductionPlanValidationError(f"{field} must be greater than or equal to 0")


def _validate_rate(value: Decimal) -> None:
    if value < 0 or value > 1:
        raise ProductionPlanValidationError("marketable_rate must be between 0 and 1")


def _validate_dates(
    *,
    effective_from: date,
    effective_to: date | None,
    flowering_start_date: date | None,
    flowering_peak_date: date | None,
    flowering_end_date: date | None,
) -> None:
    if effective_to is not None and effective_to <= effective_from:
        raise ProductionPlanValidationError("effective_to must be later than effective_from")
    if (
        flowering_start_date is not None
        and flowering_peak_date is not None
        and flowering_start_date > flowering_peak_date
    ):
        raise ProductionPlanValidationError(
            "flowering_start_date must be less than or equal to flowering_peak_date"
        )
    if (
        flowering_peak_date is not None
        and flowering_end_date is not None
        and flowering_peak_date > flowering_end_date
    ):
        raise ProductionPlanValidationError(
            "flowering_peak_date must be less than or equal to flowering_end_date"
        )


def _derived_total(
    *,
    planted_area_mu: Decimal,
    expected_yield_kg_per_mu: Decimal,
    marketable_rate: Decimal,
) -> Decimal:
    return planted_area_mu * expected_yield_kg_per_mu * marketable_rate


def _difference_warning(
    *,
    explicit_total: Decimal | None,
    derived_total: Decimal,
    config: ProductionPlanConfig,
) -> tuple[Decimal | None, tuple[str, ...]]:
    if explicit_total is None:
        return None, ()
    difference = explicit_total - derived_total
    if abs(difference) > config.rules.explicit_total_tolerance_kg:
        if config.rules.explicit_total_mismatch_behavior == "reject":
            raise ProductionPlanValidationError(
                "expected_total_marketable_kg differs from derived total beyond tolerance"
            )
        return difference, ("expected_total_marketable_kg_diff_exceeds_tolerance",)
    return difference, ()


def _interval_contains(
    *,
    as_of_date: date,
    effective_from: date,
    effective_to: date | None,
) -> bool:
    if as_of_date < effective_from:
        return False
    if effective_to is not None and as_of_date >= effective_to:
        return False
    return True


def _intervals_overlap(
    *,
    start_a: date,
    end_a: date | None,
    start_b: date,
    end_b: date | None,
) -> bool:
    left = start_a < end_b if end_b is not None else True
    right = start_b < end_a if end_a is not None else True
    return left and right


async def _validate_master_data(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
) -> tuple[str, str, str, str | None, str]:
    farm = await get_farm(session, farm_id=farm_id)
    if farm is None:
        raise ProductionPlanValidationError("farm not found")
    season = await get_season(session, season_id=season_id)
    if season is None:
        raise ProductionPlanValidationError("season not found")
    variety = await get_variety(session, variety_id=variety_id)
    if variety is None:
        raise ProductionPlanValidationError("variety not found")
    subfarm_name: str | None = None
    if subfarm_id is not None:
        subfarm = await get_subfarm(session, subfarm_id=subfarm_id)
        if subfarm is None:
            raise ProductionPlanValidationError("subfarm not found")
        if subfarm.farm_id != farm_id:
            raise ProductionPlanValidationError("subfarm does not belong to farm")
        subfarm_name = subfarm.name
    return farm.name, season.code, variety.code, subfarm_name, variety.name


def _build_row_hash_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "farm_id",
            "subfarm_id",
            "season_id",
            "variety_id",
            "planted_area_mu",
            "expected_yield_kg_per_mu",
            "marketable_rate",
            "tree_age_years",
            "pruning_date",
            "flowering_start_date",
            "flowering_peak_date",
            "flowering_end_date",
            "first_pick_date",
            "expected_total_marketable_kg",
            "version",
            "effective_from",
            "effective_to",
            "available_at",
            "source_type",
            "source_name",
            "source_version",
            "notes",
        )
    }


async def _build_record(
    session: AsyncSession,
    *,
    plan: FarmSeasonVarietyPlan,
    warnings: tuple[str, ...],
) -> ProductionPlanRecord:
    farm_name, season_code, variety_code, subfarm_name, variety_name = await _validate_master_data(
        session,
        farm_id=plan.farm_id,
        subfarm_id=plan.subfarm_id,
        season_id=plan.season_id,
        variety_id=plan.variety_id,
    )
    derived_total = _derived_total(
        planted_area_mu=plan.planted_area_mu,
        expected_yield_kg_per_mu=plan.expected_yield_kg_per_mu,
        marketable_rate=plan.marketable_rate,
    )
    difference = (
        None
        if plan.expected_total_marketable_kg is None
        else plan.expected_total_marketable_kg - derived_total
    )
    return ProductionPlanRecord(
        id=plan.id,
        farm_id=plan.farm_id,
        farm_name=farm_name,
        subfarm_id=plan.subfarm_id,
        subfarm_name=subfarm_name,
        season_id=plan.season_id,
        season_code=season_code,
        variety_id=plan.variety_id,
        variety_code=variety_code,
        variety_name=variety_name,
        planted_area_mu=plan.planted_area_mu,
        expected_yield_kg_per_mu=plan.expected_yield_kg_per_mu,
        marketable_rate=plan.marketable_rate,
        tree_age_years=plan.tree_age_years,
        pruning_date=plan.pruning_date,
        flowering_start_date=plan.flowering_start_date,
        flowering_peak_date=plan.flowering_peak_date,
        flowering_end_date=plan.flowering_end_date,
        first_pick_date=plan.first_pick_date,
        expected_total_marketable_kg=plan.expected_total_marketable_kg,
        derived_total_marketable_kg=derived_total,
        total_difference_kg=difference,
        version=plan.version,
        effective_from=plan.effective_from,
        effective_to=plan.effective_to,
        available_at=plan.available_at,
        source_type=plan.source_type,
        source_name=plan.source_name,
        source_version=plan.source_version,
        notes=plan.notes,
        row_hash=plan.row_hash,
        warnings=warnings,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _plan_payload(record: ProductionPlanRecord) -> dict[str, Any]:
    return {
        "plan_id": record.id,
        "farm_id": record.farm_id,
        "farm_name": record.farm_name,
        "subfarm_id": record.subfarm_id,
        "subfarm_name": record.subfarm_name,
        "season_id": record.season_id,
        "season_code": record.season_code,
        "variety_id": record.variety_id,
        "variety_code": record.variety_code,
        "variety_name": record.variety_name,
        "planted_area_mu": record.planted_area_mu,
        "expected_yield_kg_per_mu": record.expected_yield_kg_per_mu,
        "marketable_rate": record.marketable_rate,
        "tree_age_years": record.tree_age_years,
        "pruning_date": record.pruning_date,
        "flowering_start_date": record.flowering_start_date,
        "flowering_peak_date": record.flowering_peak_date,
        "flowering_end_date": record.flowering_end_date,
        "first_pick_date": record.first_pick_date,
        "expected_total_marketable_kg": record.expected_total_marketable_kg,
        "derived_total_marketable_kg": record.derived_total_marketable_kg,
        "total_difference_kg": record.total_difference_kg,
        "version": record.version,
        "effective_from": record.effective_from,
        "effective_to": record.effective_to,
        "available_at": record.available_at,
        "source_type": record.source_type,
        "source_name": record.source_name,
        "source_version": record.source_version,
        "notes": record.notes,
        "row_hash": record.row_hash,
        "warnings": list(record.warnings),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _canonical_payload(record: ProductionPlanRecord) -> dict[str, Any]:
    payload = canonical_json_value(_plan_payload(record))
    if not isinstance(payload, dict):
        raise TypeError("production plan payload must canonicalize to a JSON object")
    return payload


async def _validate_overlap(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
    effective_from: date,
    effective_to: date | None,
    exclude_plan_ids: set[int] | None = None,
) -> None:
    existing = await list_plan_versions_by_key(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        season_id=season_id,
        variety_id=variety_id,
    )
    excluded = exclude_plan_ids or set()
    for row in existing:
        if row.id in excluded:
            continue
        if _intervals_overlap(
            start_a=effective_from,
            end_a=effective_to,
            start_b=row.effective_from,
            end_b=row.effective_to,
        ):
            raise ProductionPlanIntervalConflictError(
                "effective interval overlaps with existing version"
            )


async def _prepare_plan_inputs(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    config: ProductionPlanConfig,
    existing_rows: list[FarmSeasonVarietyPlan],
    excluded_plan_ids: set[int] | None = None,
    allow_existing_row_hash: bool = True,
) -> tuple[FarmSeasonVarietyPlan | None, str, tuple[str, ...], bool]:
    excluded = excluded_plan_ids or set()
    farm_id = int(payload["farm_id"])
    subfarm_id = int(payload["subfarm_id"]) if payload.get("subfarm_id") is not None else None
    season_id = int(payload["season_id"])
    variety_id = int(payload["variety_id"])
    planted_area_mu = _decimal_value(payload.get("planted_area_mu"), field="planted_area_mu")
    expected_yield_kg_per_mu = _decimal_value(
        payload.get("expected_yield_kg_per_mu"),
        field="expected_yield_kg_per_mu",
    )
    marketable_rate = _decimal_value(payload.get("marketable_rate"), field="marketable_rate")
    tree_age_years = _optional_decimal_value(payload.get("tree_age_years"), field="tree_age_years")
    expected_total_marketable_kg = _optional_decimal_value(
        payload.get("expected_total_marketable_kg"),
        field="expected_total_marketable_kg",
    )
    version = int(payload["version"])
    effective_from = _date_value(payload.get("effective_from"), field="effective_from")
    effective_to = _optional_date_value(payload.get("effective_to"), field="effective_to")
    available_at = _date_value(payload.get("available_at"), field="available_at")
    source_type = str(payload["source_type"])
    source_name = cast(str | None, payload.get("source_name"))
    source_version = cast(str | None, payload.get("source_version"))
    notes = cast(str | None, payload.get("notes"))
    pruning_date = _optional_date_value(payload.get("pruning_date"), field="pruning_date")
    flowering_start_date = _optional_date_value(
        payload.get("flowering_start_date"),
        field="flowering_start_date",
    )
    flowering_peak_date = _optional_date_value(
        payload.get("flowering_peak_date"),
        field="flowering_peak_date",
    )
    flowering_end_date = _optional_date_value(
        payload.get("flowering_end_date"),
        field="flowering_end_date",
    )
    first_pick_date = _optional_date_value(
        payload.get("first_pick_date"),
        field="first_pick_date",
    )

    _validate_non_negative(planted_area_mu, field="planted_area_mu")
    _validate_non_negative(expected_yield_kg_per_mu, field="expected_yield_kg_per_mu")
    if expected_total_marketable_kg is not None:
        _validate_non_negative(
            expected_total_marketable_kg,
            field="expected_total_marketable_kg",
        )
    if tree_age_years is not None:
        _validate_non_negative(tree_age_years, field="tree_age_years")
    _validate_rate(marketable_rate)
    _validate_dates(
        effective_from=effective_from,
        effective_to=effective_to,
        flowering_start_date=flowering_start_date,
        flowering_peak_date=flowering_peak_date,
        flowering_end_date=flowering_end_date,
    )
    await _validate_master_data(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        season_id=season_id,
        variety_id=variety_id,
    )
    derived_total = _derived_total(
        planted_area_mu=planted_area_mu,
        expected_yield_kg_per_mu=expected_yield_kg_per_mu,
        marketable_rate=marketable_rate,
    )
    _, warnings = _difference_warning(
        explicit_total=expected_total_marketable_kg,
        derived_total=derived_total,
        config=config,
    )
    row_hash = plan_row_hash(
        _build_row_hash_payload(
            {
                "farm_id": farm_id,
                "subfarm_id": subfarm_id,
                "season_id": season_id,
                "variety_id": variety_id,
                "planted_area_mu": planted_area_mu,
                "expected_yield_kg_per_mu": expected_yield_kg_per_mu,
                "marketable_rate": marketable_rate,
                "tree_age_years": tree_age_years,
                "pruning_date": pruning_date,
                "flowering_start_date": flowering_start_date,
                "flowering_peak_date": flowering_peak_date,
                "flowering_end_date": flowering_end_date,
                "first_pick_date": first_pick_date,
                "expected_total_marketable_kg": expected_total_marketable_kg,
                "version": version,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "available_at": available_at,
                "source_type": source_type,
                "source_name": source_name,
                "source_version": source_version,
                "notes": notes,
            }
        )
    )
    existing_row = await get_plan_by_row_hash(session, row_hash=row_hash)
    if existing_row is not None and existing_row.id not in excluded:
        if allow_existing_row_hash:
            return None, row_hash, warnings, False
        raise ProductionPlanVersionConflictError("row hash already exists")

    for row in existing_rows:
        if row.id in excluded:
            continue
        if row.version == version:
            raise ProductionPlanVersionConflictError("version already exists for business key")
        if _intervals_overlap(
            start_a=effective_from,
            end_a=effective_to,
            start_b=row.effective_from,
            end_b=row.effective_to,
        ):
            raise ProductionPlanIntervalConflictError(
                "effective interval overlaps with existing version"
            )

    return (
        FarmSeasonVarietyPlan(
            farm_id=farm_id,
            subfarm_id=subfarm_id,
            season_id=season_id,
            variety_id=variety_id,
            planted_area_mu=planted_area_mu,
            expected_yield_kg_per_mu=expected_yield_kg_per_mu,
            marketable_rate=marketable_rate,
            tree_age_years=tree_age_years,
            pruning_date=pruning_date,
            flowering_start_date=flowering_start_date,
            flowering_peak_date=flowering_peak_date,
            flowering_end_date=flowering_end_date,
            first_pick_date=first_pick_date,
            expected_total_marketable_kg=expected_total_marketable_kg,
            version=version,
            effective_from=effective_from,
            effective_to=effective_to,
            available_at=available_at,
            source_type=source_type,
            source_name=source_name,
            source_version=source_version,
            notes=notes,
            row_hash=row_hash,
        ),
        row_hash,
        warnings,
        True,
    )


def _conflict_from_db_error(exc: Exception) -> Exception | None:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    message = str(getattr(exc, "orig", exc)).lower()
    if sqlstate == "40001":
        return ProductionPlanIntervalConflictError("concurrent production plan write conflict")
    if sqlstate == "23P01":
        return ProductionPlanIntervalConflictError(
            "effective interval overlaps with existing version"
        )
    if sqlstate == "23505":
        if "row_hash" in message:
            return ProductionPlanVersionConflictError("row hash already exists")
        if "version" in message or "uq_farm_season_variety_plan_version" in message:
            return ProductionPlanVersionConflictError("version already exists for business key")
        return ProductionPlanVersionConflictError("concurrent production plan write conflict")
    if isinstance(exc, IntegrityError):
        return ProductionPlanVersionConflictError("concurrent production plan write conflict")
    return None


async def create_plan_version(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    config: ProductionPlanConfig,
) -> ProductionPlanMutationResult:
    farm_id = int(payload["farm_id"])
    subfarm_id = int(payload["subfarm_id"]) if payload.get("subfarm_id") is not None else None
    season_id = int(payload["season_id"])
    variety_id = int(payload["variety_id"])
    try:
        async with session.begin():
            await acquire_production_plan_lock(
                session,
                farm_id=farm_id,
                subfarm_id=subfarm_id,
                season_id=season_id,
                variety_id=variety_id,
            )
            existing_rows = await list_plan_versions_by_key(
                session,
                farm_id=farm_id,
                subfarm_id=subfarm_id,
                season_id=season_id,
                variety_id=variety_id,
                for_update=True,
            )
            plan, row_hash, warnings, created_flag = await _prepare_plan_inputs(
                session,
                payload=payload,
                config=config,
                existing_rows=existing_rows,
            )
            if plan is None:
                existing_row = await get_plan_by_row_hash(session, row_hash=row_hash)
                if existing_row is None:
                    raise ProductionPlanNotFoundError("existing plan not found for row_hash")
                return ProductionPlanMutationResult(
                    record=await _build_record(session, plan=existing_row, warnings=warnings),
                    created=False,
                )
            created = await create_plan(session, plan=plan)
            return ProductionPlanMutationResult(
                record=await _build_record(session, plan=created, warnings=warnings),
                created=created_flag,
            )
    except (IntegrityError, DBAPIError) as exc:
        await session.rollback()
        translated = _conflict_from_db_error(exc)
        if translated is not None:
            raise translated from exc
        raise


async def get_plan_version(
    session: AsyncSession,
    *,
    plan_id: int,
    config: ProductionPlanConfig,
) -> ProductionPlanRecord:
    del config
    plan = await get_plan_by_id(session, plan_id=plan_id)
    if plan is None:
        raise ProductionPlanNotFoundError("plan not found")
    return await _build_record(session, plan=plan, warnings=())


async def list_plan_versions(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
    config: ProductionPlanConfig,
) -> list[ProductionPlanRecord]:
    del config
    rows = await list_plan_versions_by_key(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        season_id=season_id,
        variety_id=variety_id,
    )
    return [await _build_record(session, plan=row, warnings=()) for row in rows]


async def get_effective_plan(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
    as_of_date: date,
    config: ProductionPlanConfig,
) -> ProductionPlanRecord:
    del config
    rows = await list_plan_versions_by_key(
        session,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        season_id=season_id,
        variety_id=variety_id,
    )
    visible = [
        row
        for row in rows
        if row.available_at <= as_of_date
        and _interval_contains(
            as_of_date=as_of_date,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
        )
    ]
    if not visible:
        raise ProductionPlanUnavailableError("effective plan not found")
    if len(visible) > 1:
        raise ProductionPlanIntervalConflictError("multiple effective versions found")
    return await _build_record(session, plan=visible[0], warnings=())


async def create_replacement_version(
    session: AsyncSession,
    *,
    plan_id: int,
    payload: dict[str, Any],
    config: ProductionPlanConfig,
) -> ProductionPlanMutationResult:
    payload_subfarm_id = (
        int(payload["subfarm_id"]) if payload.get("subfarm_id") is not None else None
    )
    farm_id = int(payload["farm_id"])
    season_id = int(payload["season_id"])
    variety_id = int(payload["variety_id"])
    new_effective_from = _date_value(payload.get("effective_from"), field="effective_from")
    try:
        async with session.begin():
            await acquire_production_plan_lock(
                session,
                farm_id=farm_id,
                subfarm_id=payload_subfarm_id,
                season_id=season_id,
                variety_id=variety_id,
            )
            current = await get_plan_by_id(session, plan_id=plan_id, for_update=True)
            if current is None:
                raise ProductionPlanNotFoundError("plan not found")
            if farm_id != current.farm_id:
                raise ProductionPlanValidationError("replacement farm_id must match current plan")
            if payload_subfarm_id != current.subfarm_id:
                raise ProductionPlanValidationError(
                    "replacement subfarm_id must match current plan"
                )
            if season_id != current.season_id:
                raise ProductionPlanValidationError(
                    "replacement season_id must match current plan"
                )
            if variety_id != current.variety_id:
                raise ProductionPlanValidationError(
                    "replacement variety_id must match current plan"
                )
            if current.effective_to is not None:
                raise ProductionPlanIntervalConflictError(
                    "current plan is no longer open for replacement"
                )
            if new_effective_from <= current.effective_from:
                raise ProductionPlanValidationError(
                    "replacement effective_from must be later than current effective_from"
                )
            existing_rows = await list_plan_versions_by_key(
                session,
                farm_id=current.farm_id,
                subfarm_id=current.subfarm_id,
                season_id=current.season_id,
                variety_id=current.variety_id,
                for_update=True,
            )
            plan, _, warnings, created_flag = await _prepare_plan_inputs(
                session,
                payload=payload,
                config=config,
                existing_rows=existing_rows,
                excluded_plan_ids={current.id},
                allow_existing_row_hash=False,
            )
            if plan is None:
                raise ProductionPlanVersionConflictError("replacement row already exists")
            replaced = await create_replacement_plan(
                session,
                current_plan_id=current.id,
                current_effective_to=new_effective_from,
                new_plan=plan,
            )
            return ProductionPlanMutationResult(
                record=await _build_record(session, plan=replaced, warnings=warnings),
                created=created_flag,
            )
    except (IntegrityError, DBAPIError) as exc:
        await session.rollback()
        translated = _conflict_from_db_error(exc)
        if translated is not None:
            raise translated from exc
        raise
