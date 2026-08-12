from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.residual_model.enums import ForecastInputSourceClass
from backend.app.residual_model.schemas import FeatureValue

PLANNING_FEATURE_NAMES = frozenset({"destination_factory_category"})
PLANNING_SOURCE_CLASS = ForecastInputSourceClass.PRODUCTION_PLAN_EFFECTIVE_VERSION.value
PLANNING_VISIBILITY_POLICY_VERSION = "v0-3-s1-forecast-input-pit-visibility-v1"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class PlanningFeatureAuthorityError(ValueError):
    """Raised when a Planning feature is not bound to an effective persisted plan."""


def _error(feature_name: str, detail: str) -> PlanningFeatureAuthorityError:
    return PlanningFeatureAuthorityError(f"{feature_name}: {detail}")


def _positive_int(feature: FeatureValue, *, key: str) -> int:
    value = feature.source_ref.get(key)
    if type(value) is not int or value < 1:
        raise _error(feature.feature_name, f"{key} is required and must be a positive integer")
    return value


def _required_scope(feature: FeatureValue, *, key: str) -> int | None:
    value = feature.source_ref.get(key)
    if key == "subfarm_id" and value is None:
        return None
    if type(value) is not int or value < 1:
        raise _error(feature.feature_name, f"{key} is required and must be a positive integer")
    return value


def _required_row_hash(feature: FeatureValue) -> str:
    value = feature.source_ref.get("plan_row_hash")
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise _error(
            feature.feature_name, "plan_row_hash is required and must be lowercase SHA-256"
        )
    return value


def _interval_contains(*, as_of_date: date, row: FarmSeasonVarietyPlan) -> bool:
    return row.effective_from <= as_of_date and (
        row.effective_to is None or as_of_date < row.effective_to
    )


async def _load_effective_plan(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
    as_of_date: date,
) -> FarmSeasonVarietyPlan:
    statement = select(FarmSeasonVarietyPlan).where(
        FarmSeasonVarietyPlan.farm_id == farm_id,
        FarmSeasonVarietyPlan.season_id == season_id,
        FarmSeasonVarietyPlan.variety_id == variety_id,
    )
    if subfarm_id is None:
        statement = statement.where(FarmSeasonVarietyPlan.subfarm_id.is_(None))
    else:
        statement = statement.where(FarmSeasonVarietyPlan.subfarm_id == subfarm_id)
    rows = list((await session.scalars(statement)).all())
    visible = [
        row
        for row in rows
        if row.available_at <= as_of_date and _interval_contains(as_of_date=as_of_date, row=row)
    ]
    if not visible:
        raise PlanningFeatureAuthorityError("effective persisted production plan was not found")
    if len(visible) != 1:
        raise PlanningFeatureAuthorityError(
            "multiple effective persisted production plan versions were found"
        )
    return visible[0]


async def bind_planning_feature_authority(
    session: AsyncSession,
    *,
    feature_values: Sequence[FeatureValue],
    as_of_date: date,
) -> tuple[FeatureValue, ...]:
    """Bind Planning supplemental provenance to the persisted effective plan.

    The feature value remains the caller-provided category because the current
    production-plan row has no destination-category column.  Only persisted
    plan identity, scope, version, row hash, availability, and effective
    interval are authoritative here; a caller cannot substitute a later or
    different plan by forging FeatureValue timestamps.
    """

    bound: list[FeatureValue] = []
    for feature in feature_values:
        if feature.feature_name not in PLANNING_FEATURE_NAMES:
            bound.append(feature)
            continue

        plan_id = _positive_int(feature, key="plan_id")
        plan_version = _positive_int(feature, key="plan_version")
        plan_row_hash = _required_row_hash(feature)
        farm_id = _positive_int(feature, key="farm_id")
        subfarm_id = _required_scope(feature, key="subfarm_id")
        season_id = _positive_int(feature, key="season_id")
        variety_id = _positive_int(feature, key="variety_id")

        persisted = await session.get(FarmSeasonVarietyPlan, plan_id)
        if persisted is None:
            raise _error(feature.feature_name, "persisted plan_id was not found")
        if (
            persisted.farm_id != farm_id
            or persisted.subfarm_id != subfarm_id
            or persisted.season_id != season_id
            or persisted.variety_id != variety_id
        ):
            raise _error(feature.feature_name, "plan scope does not match the persisted plan")
        if persisted.version != plan_version:
            raise _error(feature.feature_name, "plan_version does not match the persisted plan")
        if persisted.row_hash != plan_row_hash:
            raise _error(feature.feature_name, "plan_row_hash does not match the persisted plan")

        effective = await _load_effective_plan(
            session,
            farm_id=farm_id,
            subfarm_id=subfarm_id,
            season_id=season_id,
            variety_id=variety_id,
            as_of_date=as_of_date,
        )
        if effective.id != persisted.id:
            raise _error(
                feature.feature_name,
                "referenced plan is not the effective plan at the Task 9 as-of date",
            )

        source_version = persisted.source_version or f"production-plan-v{persisted.version}"
        bound.append(
            feature.model_copy(
                update={
                    "source_ref": {
                        "source_class": PLANNING_SOURCE_CLASS,
                        "visibility_policy_version": PLANNING_VISIBILITY_POLICY_VERSION,
                        "plan_id": persisted.id,
                        "plan_version": persisted.version,
                        "plan_row_hash": persisted.row_hash,
                        "farm_id": persisted.farm_id,
                        "subfarm_id": persisted.subfarm_id,
                        "season_id": persisted.season_id,
                        "variety_id": persisted.variety_id,
                        "plan_available_at": persisted.available_at,
                        "plan_effective_from": persisted.effective_from,
                        "plan_effective_to": persisted.effective_to,
                        "plan_source_version": persisted.source_version,
                    },
                    "source_version": source_version,
                }
            )
        )
    return tuple(bound)
