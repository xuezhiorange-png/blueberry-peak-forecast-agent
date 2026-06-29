from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.canonical import make_source_ref_hash
from backend.app.harvest_state.schemas import (
    SourceRefCatalogEntry,
    Task8PredictionSourceRef,
    Task8PredictionVerificationSnapshot,
)
from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.models.planning import AgroClimateZone, LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherSourceLocation,
)
from backend.app.rolling_backtest.enums import Task10ModelPolicy, UpstreamSelectionMode
from backend.app.rolling_backtest.orchestration import _validate_source_ref_catalog
from backend.app.rolling_backtest.schemas import (
    HistoricalAvailableModelIdentity,
    RollingNodeDefinition,
    RollingNodeScope,
)


def _make_test_node() -> RollingNodeDefinition:
    """Build a minimal RollingNodeDefinition for catalog validation tests."""
    from backend.app.rolling_backtest.enums import ScopeMode
    from backend.app.rolling_backtest.schemas import ScopeSelector

    return RollingNodeDefinition(
        season_id=2026,
        node_key="march_15",
        as_of_local_date=date(2026, 3, 15),
        forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        forecast_start_local_date=date(2026, 3, 16),
        forecast_end_local_date=date(2026, 3, 31),
        scope=RollingNodeScope(
            destination_factory_ids=ScopeSelector(mode=ScopeMode.INCLUDE_IDS, ids=(1,)),
            farm_ids=ScopeSelector(mode=ScopeMode.ALL),
            variety_ids=ScopeSelector(mode=ScopeMode.ALL),
        ),
        upstream_selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION,
        forecast_horizon_policy_version="test-v1",
        timezone="Asia/Shanghai",
        task10_model_policy=HistoricalAvailableModelIdentity(
            policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
            training_run_semantic_identity="1" * 64,
            artifact_semantic_identities=("2" * 64,),
            authority_visibility_identity="3" * 64,
        ),
        resolved_upstream_semantic_identities=(),
    )

pytestmark = pytest.mark.integration


def _resolved_task8_authorities() -> list[SimpleNamespace]:
    def _resolved(
        *,
        source_role: str,
        source_type: str,
        reference_value: int,
        result_hash: str,
        config_hash: str | None = None,
        business_version: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            source_role=source_role,
            source_type=SimpleNamespace(value=source_type),
            resolved=SimpleNamespace(
                persistent_reference=SimpleNamespace(reference_value=reference_value),
                business_version=business_version,
                canonical_payload_hash=result_hash,
                semantic_identity=SimpleNamespace(
                    semantic=SimpleNamespace(config_hash=config_hash)
                ),
            ),
        )

    return [
        _resolved(
            source_role="task8_model_run",
            source_type="task8_model_run",
            reference_value=1,
            result_hash="2" * 64,
            config_hash="a" * 64,
            business_version="task8-v1",
        ),
        _resolved(
            source_role="task8_model_artifact",
            source_type="task8_model_artifact",
            reference_value=1,
            result_hash="c" * 64,
        ),
        _resolved(
            source_role="task8_forecast_run",
            source_type="task8_forecast_run",
            reference_value=1,
            result_hash="5" * 64,
        ),
        _resolved(
            source_role="task8_daily_prediction",
            source_type="task8_daily_prediction",
            reference_value=1,
            result_hash="7" * 64,
        ),
        _resolved(
            source_role="task7_weather_observation",
            source_type="task7_weather_observation",
            reference_value=1,
            result_hash="m" * 64,
            business_version="map-v1",
        ),
    ]


async def _seed_catalog_fixture(
    *, p80_override: Decimal | None = None
) -> tuple[
    SourceRefCatalogEntry,
    dict[str, object],
]:
    async with AsyncSessionMaker() as session:
        season = Season(code="S2026", start_date=date(2026, 1, 1), end_date=date(2026, 5, 31))
        farm = Farm(name="Farm A")
        variety = Variety(code="V1", name="Variety 1")
        session.add_all([season, farm, variety])
        await session.flush()

        subfarm = Subfarm(farm_id=farm.id, name="Block 1")
        zone = AgroClimateZone(
            code="Z1",
            name="Zone 1",
            country="CN",
            province="YN",
            prefecture=None,
            county=None,
            centroid_latitude=Decimal("24"),
            centroid_longitude=Decimal("102"),
            min_altitude_m=None,
            max_altitude_m=None,
            zone_version="zone-v1",
            valid_from=date(2020, 1, 1),
            valid_to=None,
            source_name="seed",
            source_version="zone-v1",
        )
        session.add_all([subfarm, zone])
        await session.flush()

        plan = FarmSeasonVarietyPlan(
            farm_id=farm.id,
            subfarm_id=subfarm.id,
            season_id=season.id,
            variety_id=variety.id,
            planted_area_mu=Decimal("10"),
            expected_yield_kg_per_mu=Decimal("100"),
            marketable_rate=Decimal("0.8"),
            tree_age_years=None,
            pruning_date=None,
            flowering_start_date=None,
            flowering_peak_date=None,
            flowering_end_date=None,
            first_pick_date=None,
            expected_total_marketable_kg=Decimal("800"),
            version=1,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            available_at=date(2026, 1, 1),
            source_type="manual",
            source_name="planner",
            source_version="v1",
            notes=None,
            row_hash="p" * 64,
        )
        location = LocationReference(
            farm_id=farm.id,
            subfarm_id=subfarm.id,
            farm_code=None,
            farm_name=farm.name,
            subfarm_name=subfarm.name,
            address_raw="A",
            address_normalized="A",
            province="YN",
            prefecture=None,
            county=None,
            township=None,
            village=None,
            latitude=Decimal("24"),
            longitude=Decimal("102"),
            altitude_m=None,
            climate_zone_id=zone.id,
            location_source="manual",
            source_version="loc-v1",
            valid_from=date(2026, 1, 1),
            valid_to=None,
            source_row_hash="l" * 64,
        )
        weather_source = WeatherSourceLocation(
            provider_code="cma",
            external_location_id="station-1",
            location_type="station",
            name="Station 1",
            latitude=Decimal("24"),
            longitude=Decimal("102"),
            altitude_m=None,
            timezone_name="Asia/Shanghai",
            grid_resolution=None,
            source_version="wx-v1",
            valid_from=date(2020, 1, 1),
            valid_to=None,
            row_hash="w" * 64,
        )
        session.add_all([plan, location, weather_source])
        await session.flush()

        mapping = LocationWeatherMapping(
            location_reference_id=location.id,
            weather_source_location_id=weather_source.id,
            mapping_method="explicit",
            distance_km=Decimal("1"),
            altitude_difference_m=Decimal("0"),
            mapping_score=Decimal("1"),
            confidence_level="high",
            mapping_version="map-v1",
            config_hash="cfg-map",
            available_at=date(2026, 3, 1),
            valid_from=date(2026, 3, 1),
            valid_to=None,
            row_hash="m" * 64,
        )
        base_temp = BaseTemperatureSearchRun(
            scope_type="variety_zone",
            variety_id=variety.id,
            climate_zone_id=zone.id,
            training_cutoff=date(2026, 3, 10),
            anchor_event="flowering_start_date",
            target_event="first_pick_date",
            candidate_temperatures=["3", "5"],
            selected_base_temperature=Decimal("5"),
            scoring_method="season_loso_mae_days",
            selected_score=Decimal("1"),
            sample_count=3,
            distinct_season_count=3,
            training_sample_ids=[1, 2, 3],
            candidate_scores={"candidates": []},
            config_hash="bt" * 32,
            feature_version="task7-v1",
            source_signature="e" * 64,
            status="completed",
            warnings=[],
            blockers=[],
            input_snapshot={"samples": []},
            finished_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        )
        session.add_all([mapping, base_temp])
        await session.flush()

        model_run = MaturityModelRun(
            model_version="task8-v1",
            config_hash="a" * 64,
            config_snapshot={"v": 1},
            training_cutoff=date(2026, 3, 1),
            source_signature="b" * 64,
            status="completed",
            random_seed=7,
            model_family="hist_gradient_boosting",
            scope="farm_variety",
            sample_count=10,
            distinct_season_count=2,
            distinct_farm_count=1,
            distinct_subfarm_count=1,
            training_metrics={},
            calibration_metrics={},
            warnings=[],
            blockers=[],
            input_snapshot={},
            finished_at=datetime(2026, 3, 10, 10, 0, tzinfo=UTC),
        )
        session.add(model_run)
        await session.flush()
        artifact = MaturityModelArtifact(
            run_id=model_run.id,
            artifact_hash="c" * 64,
            support_min_day=1,
            support_max_day=120,
            artifact_payload={},
        )
        session.add(artifact)
        await session.flush()
        forecast_run = MaturityForecastRun(
            model_run_id=model_run.id,
            artifact_id=artifact.id,
            plan_id=plan.id,
            location_reference_id=location.id,
            weather_mapping_id=mapping.id,
            base_temperature_search_run_id=base_temp.id,
            as_of_date=date(2026, 3, 15),
            prediction_start_date=date(2026, 3, 16),
            prediction_end_date=date(2026, 3, 31),
            expected_marketable_total_kg=Decimal("800"),
            expected_total_source="plan",
            axis_mode="calendar_proxy_axis",
            source_signature="d" * 64,
            status="completed",
            warnings=[],
            blockers=[],
            input_snapshot={},
            finished_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        )
        session.add(forecast_run)
        await session.flush()
        daily = MaturityDailyPredictionModel(
            forecast_run_id=forecast_run.id,
            prediction_date=date(2026, 3, 16),
            phenology_coordinate_day=Decimal("1"),
            p50_kg=Decimal("10"),
            p80_kg=p80_override if p80_override is not None else Decimal("12"),
            p90_kg=Decimal("14"),
            cumulative_p50_kg=Decimal("10"),
            cumulative_p80_kg=Decimal("12"),
            cumulative_p90_kg=Decimal("14"),
            curve_share=Decimal("0.1"),
            confidence_level="medium",
            quality_flags=[],
        )
        session.add(daily)
        await session.commit()

        source_ref = Task8PredictionSourceRef.model_validate(
            {
                "maturity_model_run_id": model_run.id,
                "maturity_model_version": "task8-v1",
                "maturity_model_config_hash": "a" * 64,
                "maturity_model_source_signature": "b" * 64,
                "maturity_model_artifact_id": artifact.id,
                "maturity_model_artifact_hash": "c" * 64,
                "maturity_forecast_run_id": forecast_run.id,
                "maturity_forecast_source_signature": "d" * 64,
                "maturity_forecast_as_of_date": "2026-03-15",
                "maturity_daily_prediction_id": daily.id,
                "prediction_date": "2026-03-16",
                "forecast_quantile": "P80",
                "source_quantity_kg": "12",
                "plan_id": plan.id,
                "location_reference_id": location.id,
                "weather_mapping_id": mapping.id,
                "base_temperature_search_run_id": base_temp.id,
            }
        )
        verification = Task8PredictionVerificationSnapshot.model_validate(
            {
                "maturity_model_run_id": model_run.id,
                "maturity_model_version": "task8-v1",
                "maturity_model_config_hash": "a" * 64,
                "maturity_model_source_signature": "b" * 64,
                "maturity_model_artifact_id": artifact.id,
                "maturity_model_artifact_run_id": model_run.id,
                "maturity_model_artifact_hash": "c" * 64,
                "maturity_forecast_run_id": forecast_run.id,
                "maturity_forecast_run_status": "completed",
                "maturity_forecast_model_run_id": model_run.id,
                "maturity_forecast_artifact_id": artifact.id,
                "maturity_forecast_source_signature": "d" * 64,
                "maturity_forecast_as_of_date": "2026-03-15",
                "maturity_forecast_prediction_start_date": "2026-03-16",
                "maturity_forecast_prediction_end_date": "2026-03-31",
                "maturity_daily_prediction_id": daily.id,
                "maturity_daily_prediction_forecast_run_id": forecast_run.id,
                "prediction_date": "2026-03-16",
                "farm_id": farm.id,
                "subfarm_id": subfarm.id,
                "variety_id": variety.id,
                "plan_id": plan.id,
                "location_reference_id": location.id,
                "p50_kg": "10",
                "p80_kg": "12",
                "p90_kg": "14",
            }
        )
        payload = source_ref.model_dump(mode="python")
        entry = SourceRefCatalogEntry(
            source_ref_hash=make_source_ref_hash(payload),
            source_ref_type=source_ref.source_ref_type,
            source_ref_schema_version=source_ref.source_ref_schema_version,
            source_ref_payload=payload,
        )
        snapshot = {
            "prediction_date": verification.prediction_date,
            "farm_id": verification.farm_id,
            "subfarm_id": verification.subfarm_id,
            "variety_id": verification.variety_id,
            "source_ref_hash": entry.source_ref_hash,
            "verification_snapshot": verification.model_dump(mode="python"),
        }
        return entry, snapshot


@pytest.mark.asyncio
async def test_catalog_authority_valid_orm_chain_passes() -> None:
    entry, snapshot = await _seed_catalog_fixture()

    async with AsyncSessionMaker() as session:
        result = await _validate_source_ref_catalog(
            session=session,
            catalog=[entry],
            resolutions=_resolved_task8_authorities(),  # type: ignore[arg-type]
            input_snapshot_task8_predictions=[snapshot],
        )

    assert result["blocked"] is False


@pytest.mark.asyncio
async def test_catalog_authority_orm_quantile_mismatch_blocks() -> None:
    entry, snapshot = await _seed_catalog_fixture(p80_override=Decimal("999"))

    async with AsyncSessionMaker() as session:
        result = await _validate_source_ref_catalog(
            session=session,
            catalog=[entry],
            resolutions=_resolved_task8_authorities(),  # type: ignore[arg-type]
            input_snapshot_task8_predictions=[snapshot],
        )

    assert result["blocked"] is True
    assert "p80_kg" in str(result["reason"])
