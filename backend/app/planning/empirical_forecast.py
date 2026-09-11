"""Acceptance empirical maturity -> canonical Task9 -> persisted point forecast.

No spline artifact or physiological maturity assertion is manufactured here.
The three Task9 scenarios are identical point scenarios, not calibrated intervals.
"""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.metrics import compute_point_series_metrics
from backend.app.harvest_state.application import (
    execute_harvest_state_run,
    get_harvest_state_run_by_id,
)
from backend.app.harvest_state.canonical import sha256_hex
from backend.app.harvest_state.schemas import Task9ARequest
from backend.app.models.empirical_forecast import EmpiricalForecastRun
from backend.app.planning.empirical_authority import load_empirical_authority


class EmpiricalForecastCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maturity_authority_type: Literal["HISTORICAL_CALIBRATION"]
    authority_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class EmpiricalForecastResponse(BaseModel):
    maturity_authority_type: Literal["HISTORICAL_CALIBRATION"] = "HISTORICAL_CALIBRATION"
    run_id: int
    status: Literal["COMPLETED"] = "COMPLETED"
    result_hash: str
    payload: dict[str, Any]


def build_empirical_task9_request(authority: dict[str, Any]) -> Task9ARequest:
    curve, scope = authority["curve"], authority["scope"]
    authority_hash = sha256_hex(authority)
    policy = authority["operational_policy"]
    version = curve["policy_version"]

    def ref(code: str) -> dict[str, Any]:
        return dict(
            source_ref_type="PARAMETER_SOURCE",
            parameter_code=code,
            source_system="ACCEPTANCE_BASELINE_POLICY",
            source_record_key=code,
            source_version=version,
            source_row_hash=sha256_hex(
                {"authority": authority_hash, "code": code, "policy": policy}
            ),
            available_at=curve["as_of"],
            as_of_date=curve["as_of"],
        )

    capacity, losses, predictions = [], [], []
    for day in curve["days"]:
        capacity.append(
            dict(
                capacity_date=day["date"],
                capacity_pool_id="farm-aggregate",
                capacity_input_mode="DIRECT_CAPACITY",
                direct_nominal_capacity_kg_per_day=curve["capacity_kg_per_day"],
                labor_availability_ratio="1",
                operational_efficiency_ratio="1",
                capacity_parameter_source_refs=[
                    ref(c)
                    for c in (
                        "DIRECT_NOMINAL_CAPACITY",
                        "LABOR_AVAILABILITY_RATIO",
                        "OPERATIONAL_EFFICIENCY_RATIO",
                    )
                ],
            )
        )
        for quantile in ("P50", "P80", "P90"):
            losses.append(
                dict(
                    state_date=day["date"],
                    capacity_pool_id="farm-aggregate",
                    forecast_quantile=quantile,
                    mature_inventory_loss_quantity_kg="0",
                    source_ref=ref("MATURE_INVENTORY_LOSS"),
                )
            )
            predictions.append(
                dict(
                    prediction_date=day["date"],
                    farm_id=scope["farm_id"],
                    subfarm_id=None,
                    variety_id=scope["variety_id"],
                    source_ref=dict(
                        source_ref_type="EMPIRICAL_CALIBRATION_FORECAST",
                        authority_hash=authority_hash,
                        curve_hash=curve["curve_hash"],
                        available_at=curve["as_of"],
                        prediction_date=day["date"],
                        forecast_quantile=quantile,
                        source_quantity_kg=day["supply_kg"],
                    ),
                )
            )
    return Task9ARequest.model_validate(
        dict(
            forecast_season_identity=authority["season"],
            as_of_date=curve["as_of"],
            forecast_start_date=curve["forecast_start"],
            forecast_end_date=curve["forecast_end"],
            forecast_quantiles=["P50", "P80", "P90"],
            destination_factory_id=scope["factory_id"],
            farm_timezone="Asia/Shanghai",
            destination_factory_timezone="Asia/Shanghai",
            harvest_bucket_anchor_local_time="12:00:00",
            harvest_to_arrival_lag_days=0,
            holiday_calendar_version=version,
            holiday_calendar_hash=sha256_hex(
                dict(holiday_calendar_version=version, holiday_dates=[])
            ),
            holiday_dates=[],
            weather_rule_config=dict(
                version=version,
                required_feature_ids=[],
                feature_rules=[],
                combination_method="MULTIPLY",
                minimum_ratio="1",
                maximum_ratio="1",
                missing_feature_policy="BLOCK",
            ),
            run_parameter_source_refs=[
                ref(c)
                for c in (
                    "HOLIDAY_CALENDAR",
                    "WEATHER_RULE_CONFIG",
                    "HARVEST_TO_ARRIVAL_LAG",
                    "TIMEZONE_CONFIG",
                    "HARVEST_BUCKET_ANCHOR_TIME",
                )
            ],
            capacity_pools=[
                dict(
                    capacity_pool_id="farm-aggregate",
                    capacity_pool_grain="FARM",
                    members=[
                        dict(
                            farm_id=scope["farm_id"],
                            subfarm_id=None,
                            variety_id=scope["variety_id"],
                        )
                    ],
                )
            ],
            daily_capacity_inputs=capacity,
            daily_weather_features=[],
            task8_daily_predictions=[],
            empirical_daily_predictions=predictions,
            initial_inventory_cohorts=[],
            initial_opening_mature_inventory_kg="0",
            mature_inventory_loss_inputs=losses,
        )
    )


async def create_empirical_forecast(
    session: AsyncSession, request: EmpiricalForecastCreateRequest, *, actor_identity: str
) -> EmpiricalForecastResponse:
    authority = await load_empirical_authority(session, request.authority_hash)
    task9 = await execute_harvest_state_run(
        session, request=build_empirical_task9_request(authority)
    )
    if task9.output.status != "completed":
        raise ValueError(f"empirical Task9 blocked: {task9.output.model_dump(mode='json')}")
    rows = [r for r in task9.output.daily_pool_state_rows if r.forecast_quantile == "P50"]
    if not rows or not all(
        r.mass_balance_passed
        and r.capacity_constraint_passed
        and r.continuity_passed
        and r.arrival_quantity_kg == r.harvested_quantity_kg
        for r in rows
    ):
        raise ValueError("empirical forecast state invariants failed")
    metrics = compute_point_series_metrics(
        [(r.state_date, int(r.harvested_quantity_kg * Decimal(1000000))) for r in rows], "P50"
    )
    payload = dict(
        authority_hash=request.authority_hash,
        actor_identity=actor_identity,
        task9_result_hash=task9.result_hash,
        uncertainty_status=authority["curve"]["uncertainty_status"],
        metrics=metrics.model_dump(mode="json"),
        daily_rows=[r.model_dump(mode="json") for r in rows],
    )
    result_hash = sha256_hex(payload)
    existing = await session.scalar(
        select(EmpiricalForecastRun).where(EmpiricalForecastRun.result_hash == result_hash)
    )
    if existing is None:
        existing = EmpiricalForecastRun(
            authority_hash=request.authority_hash,
            task9_run_id=task9.run_id,
            result_hash=result_hash,
            payload=payload,
        )
        session.add(existing)
        await session.flush()
    return EmpiricalForecastResponse(run_id=existing.id, result_hash=result_hash, payload=payload)


async def read_empirical_forecast(session: AsyncSession, run_id: int) -> EmpiricalForecastResponse:
    row = await session.get(EmpiricalForecastRun, run_id)
    if row is None or sha256_hex(row.payload) != row.result_hash:
        raise ValueError("empirical forecast missing or corrupt")
    await load_empirical_authority(session, row.authority_hash)
    task9 = await get_harvest_state_run_by_id(session, run_id=row.task9_run_id)
    if task9.result_hash != row.payload["task9_result_hash"]:
        raise ValueError("empirical Task9 readback mismatch")
    return EmpiricalForecastResponse(
        run_id=row.id, result_hash=row.result_hash, payload=row.payload
    )
