"""PostgreSQL production replay for the V0.1-S2 projection boundary."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.schemas import (
    CompleteDailyMarketableCurveRequest,
    MarketableRetentionPolicyEntry,
    MarketableRetentionPolicySnapshot,
)
from backend.app.core_forecast.service import compose_complete_daily_marketable_curve
from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel, HarvestStateRun
from backend.app.models.master_data import Factory, Farm, Season, Subfarm, Variety
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.models.planning import LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan

FIXTURE_DIR = Path("backend/tests/fixtures/v0_1_complete_season_case_01")
INPUT = json.loads((FIXTURE_DIR / "input.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIXTURE_DIR / "expected_daily.json").read_text(encoding="utf-8"))["rows"]

TASK8_RUN_ID = 810001
TASK8_MODEL_RUN_ID = 810000
TASK8_ARTIFACT_ID = 810010
TASK9_RUN_ID = 910001
SEASON_ID = 2026
FACTORY_ID = 9101
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def _hash(seed: str) -> str:
    return (seed[0] * 64) if seed else HASH_C


def _request() -> CompleteDailyMarketableCurveRequest:
    scopes = sorted(
        {(row["farm_id"], row["subfarm_id"], row["variety_id"]) for row in INPUT["daily_inputs"]}
    )
    season = INPUT["season"]
    return CompleteDailyMarketableCurveRequest(
        forecast_season_id=SEASON_ID,
        forecast_season_code=season["season_code"],
        forecast_start_date=date.fromisoformat(season["forecast_start_date"]),
        forecast_end_date=date.fromisoformat(season["forecast_end_date"]),
        destination_factory_id=FACTORY_ID,
        task8_forecast_run_id=TASK8_RUN_ID,
        task9_harvest_state_run_id=TASK9_RUN_ID,
        scopes=tuple(
            {"farm_id": farm, "subfarm_id": subfarm, "variety_id": variety}
            for farm, subfarm, variety in scopes
        ),
    )


def _policy() -> MarketableRetentionPolicySnapshot:
    return MarketableRetentionPolicySnapshot(
        entries=tuple(
            MarketableRetentionPolicyEntry(
                forecast_season_id=SEASON_ID,
                forecast_season_code=entry["season_code"],
                farm_id=entry["farm_id"],
                subfarm_id=entry["subfarm_id"],
                variety_id=entry["variety_id"],
                sorting_retention_rate=entry["sorting_retention_rate"],
                postharvest_retention_rate=entry["postharvest_retention_rate"],
                source=entry["source"],
                version=entry["version"],
                hash=entry["hash"],
            )
            for entry in INPUT["marketable_retention_policy"]
        )
    )


def _seed_task8_rows() -> list[MaturityDailyPredictionModel]:
    by_day_quantile: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for row in INPUT["daily_inputs"]:
        by_day_quantile[(row["date"], row["forecast_quantile"])] += Decimal(
            row["natural_maturity_supply_kg"]
        )

    cumulative = {"P50": Decimal("0"), "P80": Decimal("0"), "P90": Decimal("0")}
    rows: list[MaturityDailyPredictionModel] = []
    start = date.fromisoformat(INPUT["season"]["forecast_start_date"])
    for offset in range(90):
        current_date = start + timedelta(days=offset)
        values = {
            quantile: by_day_quantile[(current_date.isoformat(), quantile)]
            for quantile in ("P50", "P80", "P90")
        }
        for quantile, value in values.items():
            cumulative[quantile] += value
        rows.append(
            MaturityDailyPredictionModel(
                forecast_run_id=TASK8_RUN_ID,
                prediction_date=current_date,
                phenology_coordinate_day=Decimal(offset + 1),
                p50_kg=values["P50"],
                p80_kg=values["P80"],
                p90_kg=values["P90"],
                cumulative_p50_kg=cumulative["P50"],
                cumulative_p80_kg=cumulative["P80"],
                cumulative_p90_kg=cumulative["P90"],
                curve_share=Decimal("0.0100000000"),
                confidence_level="HIGH",
                quality_flags=[],
            )
        )
    return rows


def _seed_member_rows() -> list[HarvestStateDailyMemberRowModel]:
    rows: list[HarvestStateDailyMemberRowModel] = []
    for source in INPUT["daily_inputs"]:
        rows.append(
            HarvestStateDailyMemberRowModel(
                harvest_state_run_id=TASK9_RUN_ID,
                state_date=date.fromisoformat(source["date"]),
                forecast_quantile=source["forecast_quantile"],
                capacity_pool_id=(f"s2-fixture-{source['subfarm_id']}-{source['variety_id']}"),
                capacity_pool_grain="SUBFARM_VARIETY",
                capacity_pool_membership_hash=HASH_C,
                farm_id=source["farm_id"],
                subfarm_id=source["subfarm_id"],
                subfarm_identity_key=str(source["subfarm_id"]),
                variety_id=source["variety_id"],
                destination_factory_id=source["destination_factory_id"],
                opening_mature_inventory_kg=Decimal(source["opening_mature_inventory_kg"]),
                natural_maturity_supply_kg=Decimal(source["natural_maturity_supply_kg"]),
                available_mature_quantity_kg=Decimal(source["available_mature_quantity_kg"]),
                mature_inventory_loss_quantity_kg=Decimal(
                    source["mature_inventory_loss_quantity_kg"]
                ),
                harvestable_mature_quantity_kg=Decimal(source["harvestable_mature_quantity_kg"]),
                allocated_harvest_capacity_kg=Decimal(source["effective_harvest_capacity_kg"]),
                harvested_quantity_kg=Decimal(source["model_harvested_marketable_quantity_kg"]),
                closing_mature_inventory_kg=Decimal(source["closing_mature_inventory_kg"]),
                unharvested_backlog_kg=Decimal(source["unharvested_backlog_kg"]),
                arrival_quantity_kg=Decimal(source["model_harvested_marketable_quantity_kg"]),
                opening_cohort_count=0,
                closing_cohort_count=0,
                cohort_source_ref_hashes=[],
            )
        )
    return rows


async def _seed_authorities(session: AsyncSession) -> None:
    season_data = INPUT["season"]
    season = Season(
        id=SEASON_ID,
        code=season_data["season_code"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    farm = Farm(id=101, name="s2-fixture-farm")
    subfarms = [
        Subfarm(id=1101, farm_id=101, name="s2-fixture-east"),
        Subfarm(id=1102, farm_id=101, name="s2-fixture-west"),
    ]
    varieties = [
        Variety(id=2101, code="S2-VAR-A", name="s2-fixture-variety-a"),
        Variety(id=2102, code="S2-VAR-B", name="s2-fixture-variety-b"),
    ]
    factory = Factory(id=FACTORY_ID, code="S2-FIXTURE", name="s2-fixture-factory")
    location = LocationReference(
        id=3101,
        farm_id=101,
        subfarm_id=1101,
        address_normalized="s2-fixture-location",
        latitude=Decimal("24.400000"),
        longitude=Decimal("103.400000"),
        location_source="s2-fixture",
        source_version="s2-fixture-v1",
        valid_from=date(2026, 1, 1),
        source_row_hash=HASH_D,
    )
    plan = FarmSeasonVarietyPlan(
        id=3201,
        farm_id=101,
        subfarm_id=1101,
        season_id=SEASON_ID,
        variety_id=2101,
        planted_area_mu=Decimal("10.000000"),
        expected_yield_kg_per_mu=Decimal("25000.000000"),
        marketable_rate=Decimal("0.8000000000"),
        version=1,
        effective_from=date(2026, 1, 1),
        available_at=date(2026, 1, 1),
        source_type="s2-fixture",
        source_name="s2-fixture",
        source_version="s2-fixture-v1",
        row_hash=HASH_A,
    )
    model_run = MaturityModelRun(
        id=TASK8_MODEL_RUN_ID,
        model_version="s2-fixture-task8-v1",
        config_hash=HASH_D,
        config_snapshot={"fixture": "v0_1_complete_season_case_01"},
        training_cutoff=date(2025, 12, 31),
        source_signature=_hash("e"),
        status="completed",
        random_seed=1,
        model_family="s2-fixture",
        scope="s2-fixture",
        sample_count=1,
        distinct_season_count=1,
        distinct_farm_count=1,
        distinct_subfarm_count=2,
        training_metrics={},
        calibration_metrics={},
        warnings=[],
        blockers=[],
        input_snapshot={},
    )
    artifact = MaturityModelArtifact(
        id=TASK8_ARTIFACT_ID,
        run_id=TASK8_MODEL_RUN_ID,
        artifact_hash=HASH_A,
        support_min_day=1,
        support_max_day=90,
        artifact_payload={"fixture": "v0_1_complete_season_case_01"},
    )
    start = date.fromisoformat(season_data["forecast_start_date"])
    end = date.fromisoformat(season_data["forecast_end_date"])
    forecast = MaturityForecastRun(
        id=TASK8_RUN_ID,
        model_run_id=TASK8_MODEL_RUN_ID,
        artifact_id=TASK8_ARTIFACT_ID,
        plan_id=plan.id,
        location_reference_id=location.id,
        as_of_date=date(2026, 2, 28),
        prediction_start_date=start,
        prediction_end_date=end,
        expected_marketable_total_kg=Decimal("100000.000000"),
        expected_total_source="s2-fixture",
        axis_mode="calendar_proxy_axis",
        source_signature=_hash("f"),
        status="completed",
        warnings=[],
        blockers=[],
        input_snapshot={},
    )
    task9 = HarvestStateRun(
        id=TASK9_RUN_ID,
        status="completed",
        output_schema_version="task9a-output-v2",
        result_hash_schema_version="task9a-result-hash-v2",
        resolved_parameter_snapshot_schema_version="task9a-resolved-parameters-v1",
        source_ref_schema_version="task9a-source-ref-v1",
        stable_cohort_key_schema_version="task9a-cohort-key-v1",
        input_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        canonical_output={},
        config_hash=HASH_D,
        result_hash=HASH_B,
        canonical_payload_hash=HASH_C,
        forecast_start_date=start,
        forecast_end_date=end,
        as_of_date=date(2026, 2, 28),
        destination_factory_id=FACTORY_ID,
        forecast_season_id=SEASON_ID,
        pool_row_count=0,
        member_row_count=1080,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_model_run_id=TASK8_MODEL_RUN_ID,
        maturity_model_version=model_run.model_version,
        maturity_model_config_hash=model_run.config_hash,
        maturity_model_source_signature=model_run.source_signature,
        maturity_model_artifact_id=TASK8_ARTIFACT_ID,
        maturity_model_artifact_hash=HASH_A,
        maturity_forecast_run_id=TASK8_RUN_ID,
        maturity_forecast_source_signature=forecast.source_signature,
        is_replay=False,
    )
    session.add_all([season, farm, *subfarms, *varieties, factory, location, plan, model_run])
    await session.flush()
    session.add(artifact)
    await session.flush()
    session.add(forecast)
    await session.flush()
    session.add(task9)
    await session.flush()
    session.add_all(_seed_task8_rows())
    session.add_all(_seed_member_rows())
    await session.flush()


@pytest.mark.integration
@pytest.mark.postgres
@pytest.mark.task8
@pytest.mark.task9
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="LOCAL_POSTGRES_NOT_AVAILABLE",
)
async def test_postgres_projection_replays_complete_season_fixture(
    transactional_pg_session: AsyncSession,
) -> None:
    await _seed_authorities(transactional_pg_session)
    result = await compose_complete_daily_marketable_curve(
        transactional_pg_session,
        request=_request(),
        retention_policy=_policy(),
    )

    assert result.status == "COMPLETED"
    assert result.blockers == ()
    actual = [row.model_dump(mode="json") for row in result.rows]
    assert actual == EXPECTED
    assert len(actual) == 1080
