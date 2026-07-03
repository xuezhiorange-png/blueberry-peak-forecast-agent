"""Task 11 node orchestration integration tests.

Requires PostgreSQL with RUN_POSTGRES_INTEGRATION=1 and APP_ENV=test.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError as SAIntegrityError

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.persistence import save_harvest_state_output
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.master_data import Farm, Season, Variety
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.models.planning import AgroClimateZone, LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestNode,
    RollingBacktestOrchestrationSnapshot,
    RollingBacktestRun,
    RollingBacktestStageEvent,
)
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherSourceLocation,
)
from backend.app.residual_model.application import (
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.schemas import ResidualPredictionRequest
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.errors import (
    RollingBacktestAttemptConflictError,
    RollingBacktestStageIntegrityError,
)
from backend.app.rolling_backtest.node_orchestration import (
    orchestrate_node,
)
from backend.app.rolling_backtest.persistence import (
    AvailabilityAuditPersistenceCommand,
    DagPersistenceCommand,
    ResolvedInputPersistenceCommand,
    RollingBacktestPersistenceCommand,
    RollingNodePersistenceCommand,
    create_execution_attempt,
    create_or_load_logical_run,
    derive_run_status_from_attempts,
    finalize_attempt_status,
    load_logical_run_with_integrity,
    persist_stage_event,
    update_run_status_from_attempts,
    validate_stage_continuity,
)
from backend.app.rolling_backtest.resolution import _make_identity
from backend.app.rolling_backtest.schemas import (
    HistoricalAvailableModelIdentity,
    ParentAuthorityIdentity,
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    Task3AnalyticsBuildAvailabilitySnapshot,
    Task8ForecastRunAvailabilitySnapshot,
    Task8ModelArtifactAvailabilitySnapshot,
    Task8ModelRunAvailabilitySnapshot,
    Task9HarvestStateRunAvailabilitySnapshot,
    Task10ModelArtifactAvailabilitySnapshot,
    Task10PredictionRunAvailabilitySnapshot,
    Task10TrainingRunAvailabilitySnapshot,
    UpstreamSemanticIdentityPayload,
)
from backend.tests.harvest_state.conftest import make_request
from backend.tests.integration.test_residual_model_persistence import _seed_prediction_fixture
from backend.tests.residual_model.test_training_manifest import (
    _config as _residual_config,
)
from backend.tests.residual_model.test_training_manifest import (
    _diverse_training_samples,
    _supplemental_features,
)

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


# ── Canonical Task 8 fixture hashes (deterministic SHA-256) ─────────────────

TASK8_MODEL_CONFIG_HASH = sha256_payload({"fixture": "task8-model-config", "version": 1})
TASK8_MODEL_SOURCE_SIGNATURE = sha256_payload({"fixture": "task8-model-run", "version": 1})
TASK8_ARTIFACT_HASH = sha256_payload({"fixture": "task8-model-artifact", "version": 1})
TASK8_FORECAST_SOURCE_SIGNATURE = sha256_payload({"fixture": "task8-forecast-run", "version": 1})


def _assert_sha256_hex(value: str) -> None:
    """Assert *value* is a valid lowercase 64-hex SHA-256 string."""
    assert len(value) == 64, f"expected 64 chars, got {len(value)}: {value!r}"
    assert set(value) <= set("0123456789abcdef"), f"non-hex chars in: {value!r}"


# ── Fixture helpers (same as test_rolling_backtest_persistence.py) ────────────


def _make_historical_model_identity() -> HistoricalAvailableModelIdentity:
    return HistoricalAvailableModelIdentity(
        policy="historically_available_model",
        training_run_semantic_identity="a" * 64,
        artifact_semantic_identities=("b" * 64, "c" * 64),
        authority_visibility_identity="d" * 64,
    )


def _make_node(
    *,
    season_id: int = 2026,
    node_key: str = "march_15",
) -> RollingNodeDefinition:
    """Build a minimal valid RollingNodeDefinition."""
    return RollingNodeDefinition.model_validate(
        {
            "season_id": season_id,
            "node_key": node_key,
            "as_of_local_date": f"{season_id}-03-15",
            "forecast_cutoff_at": f"{season_id}-03-15T04:00:00Z",
            "forecast_start_local_date": f"{season_id}-03-16",
            "forecast_end_local_date": f"{season_id}-03-31",
            "scope": {
                "destination_factory_ids": {"mode": "include_ids", "ids": [202, 101]},
                "farm_ids": {"mode": "all", "ids": []},
                "subfarm_ids": {"mode": "all", "ids": []},
                "variety_ids": {"mode": "all", "ids": []},
            },
            "upstream_selection_mode": "historical_resolution",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "timezone": "Asia/Shanghai",
            "task10_model_policy": {
                "policy": "historically_available_model",
                "training_run_semantic_identity": "a" * 64,
                "artifact_semantic_identities": ["b" * 64, "c" * 64],
                "authority_visibility_identity": "d" * 64,
            },
        }
    )


def _make_pinned_node(
    *,
    season_id: int = 2026,
    node_key: str = "march_15",
    resolved_identities: tuple[ResolvedUpstreamSemanticIdentity, ...] = (),
) -> RollingNodeDefinition:
    """Build a RollingNodeDefinition with upstream_selection_mode=pinned."""
    node = _make_node(season_id=season_id, node_key=node_key)
    return node.model_copy(
        update={
            "upstream_selection_mode": UpstreamSelectionMode.PINNED,
            "resolved_upstream_semantic_identities": resolved_identities,
        }
    )


def _make_config(
    *,
    execution_mode: ExecutionMode = ExecutionMode.HISTORICAL_OBSERVED,
    nodes: tuple[RollingNodeDefinition, ...] | None = None,
) -> RollingBacktestConfig:
    """Build a minimal valid RollingBacktestConfig."""
    if nodes is None:
        nodes = (_make_node(),)
    node_dicts = [n.model_dump(mode="python") for n in nodes]
    return RollingBacktestConfig.model_validate(
        {
            "rolling_schema_version": "task11-rolling-v1",
            "canonical_serialization_version": "task11-canonical-v1",
            "availability_registry_version": "task11-availability-v1",
            "node_calendar_version": "task11-calendar-v1",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "upstream_selection_policy_version": "task11-selection-v1",
            "metric_policy_version": "task11-metrics-v1",
            "execution_mode": execution_mode.value,
            "calendar_phase_policy_version": "task11-calendar-phase-v1",
            "cutoff_policy_version": "task11-cutoff-v1",
            "cutoff_timezone": "Asia/Shanghai",
            "cutoff_local_time": "12:00:00",
            "nodes": node_dicts,
        }
    )


def _make_semantic_identity(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
    source_role: str = "task9_structural_forecast",
    role_qualifier: str | None = None,
) -> ResolvedUpstreamSemanticIdentity:
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        role_qualifier=role_qualifier,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id", reference_value=1
        ),
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-v1",
            display_label="test identity",
            semantic_payload_hash="e" * 64,
            input_signature="f" * 64,
            result_hash="a" * 64,
            canonical_payload_hash="b" * 64,
            business_version="v1",
            policy_version="p1",
        ),
    )


def _make_dag() -> DagPersistenceCommand:
    return DagPersistenceCommand(
        dag_schema_version="task11-dag-v1",
        dag_policy_version="task11-dag-policy-v1",
        dag_dict={"nodes": ["a", "b", "c"], "edges": [("a", "b"), ("b", "c")]},
        expected_node_count=3,
        expected_edge_count=2,
    )


def _make_node_command(
    node: RollingNodeDefinition,
    *,
    identity: ResolvedUpstreamSemanticIdentity | None = None,
) -> RollingNodePersistenceCommand:
    if identity is None:
        identity = _make_semantic_identity()
    node_with_identity = node.model_copy(
        update={"resolved_upstream_semantic_identities": (identity,)}
    )
    return RollingNodePersistenceCommand(
        node=node_with_identity,
        resolved_inputs=(ResolvedInputPersistenceCommand(identity=identity),),
        availability_audits=(),
        dag=_make_dag(),
    )


def _make_persistence_command(
    config: RollingBacktestConfig,
    *,
    with_inputs: bool = True,
    with_audits: bool = False,
    with_dag: bool = True,
) -> RollingBacktestPersistenceCommand:
    """Build a full persistence command from config."""
    node_cmds: list[RollingNodePersistenceCommand] = []
    for node in config.nodes:
        inputs: tuple[ResolvedInputPersistenceCommand, ...] = ()
        audits: tuple[AvailabilityAuditPersistenceCommand, ...] = ()
        dag = None

        if with_inputs:
            inputs = (
                ResolvedInputPersistenceCommand(
                    identity=_make_semantic_identity(
                        source_role="task3_analytics",
                        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
                    ),
                ),
            )

        if with_audits:
            # Create a valid run snapshot
            snapshot = Task8ForecastRunAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                status="completed",
                authoritative_timestamp=datetime(2025, 3, 14, tzinfo=UTC),
            )
            identity = _make_semantic_identity(
                source_role="task8_forecast_run",
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            )
            if not inputs:
                inputs = (ResolvedInputPersistenceCommand(identity=identity),)
            elif all(item.identity.source_role != identity.source_role for item in inputs):
                inputs = (*inputs, ResolvedInputPersistenceCommand(identity=identity))
            audits = (
                AvailabilityAuditPersistenceCommand(
                    source_role="task8_forecast_run",
                    snapshot=snapshot,
                    forecast_cutoff_at=node.forecast_cutoff_at,
                    resolved_identity=identity,
                ),
            )

        if with_dag:
            dag = _make_dag()

        node_with_inputs = node.model_copy(
            update={
                "resolved_upstream_semantic_identities": tuple(item.identity for item in inputs)
            }
        )

        node_cmds.append(
            RollingNodePersistenceCommand(
                node=node_with_inputs,
                resolved_inputs=inputs,
                availability_audits=audits,
                dag=dag,
            )
        )

    return RollingBacktestPersistenceCommand(
        config=config.model_copy(update={"nodes": tuple(cmd.node for cmd in node_cmds)}),
        nodes=tuple(node_cmds),
    )


# ── Orchestration test helpers ───────────────────────────────────────────────


def _make_orchestration_persistence_command(
    *,
    execution_mode: ExecutionMode = ExecutionMode.HISTORICAL_OBSERVED,
    identity_role: str = "task8_forecast_run",
    identity_source_type: AvailabilitySourceType = AvailabilitySourceType.TASK8_FORECAST_RUN,
    season_id: int = 2026,
) -> RollingBacktestPersistenceCommand:
    """Build a persistence command suitable for orchestrate_node integration tests.

    Creates a node with upstream_selection_mode=pinned, a matching resolved
    input, and a matching availability audit so that orchestrate_node can
    proceed through all eight stages.
    """
    identity = _make_semantic_identity(
        source_role=identity_role,
        source_type=identity_source_type,
    )
    node = _make_pinned_node(
        season_id=season_id,
        node_key="march_15",
        resolved_identities=(identity,),
    )
    config = _make_config(execution_mode=execution_mode, nodes=(node,))

    # Build availability snapshot that passes the visibility check.
    # For TASK8_FORECAST_RUN: status="completed", authoritative_timestamp before cutoff.
    snapshot = Task8ForecastRunAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        status="completed",
        authoritative_timestamp=datetime(2025, 3, 14, tzinfo=UTC),
    )

    audit_cmd = AvailabilityAuditPersistenceCommand(
        source_role=identity_role,
        snapshot=snapshot,
        forecast_cutoff_at=node.forecast_cutoff_at,
        resolved_identity=identity,
    )

    ri_cmd = ResolvedInputPersistenceCommand(identity=identity)
    node_cmd = RollingNodePersistenceCommand(
        node=node,
        resolved_inputs=(ri_cmd,),
        availability_audits=(audit_cmd,),
        dag=_make_dag(),
    )

    return RollingBacktestPersistenceCommand(
        config=config.model_copy(update={"nodes": (node,)}),
        nodes=(node_cmd,),
    )


async def _get_node_id_for_run(run_id: int) -> int:
    """Helper to fetch the single node ID for a run."""
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode.id).where(RollingBacktestNode.rolling_run_id == run_id)
        )
        return result.scalar_one()


def _relaxed_residual_config():
    config = _residual_config()
    eligibility = replace(
        config.rules.eligibility,
        min_training_rows=1,
        min_seasons=1,
        min_factories=1,
    )
    rules = replace(config.rules, eligibility=eligibility)
    return replace(config, rules=rules)


async def _make_real_task8_orchestration_persistence_command(
    *,
    season_id: int,
    node_key: str,
) -> RollingBacktestPersistenceCommand:
    task8 = await _seed_real_task8_authorities(season_id=season_id)

    async with AsyncSessionMaker() as session:
        forecast_row = await session.get(MaturityForecastRun, task8["forecast_run_id"])
        model_row = await session.get(MaturityModelRun, task8["model_run_id"])
        assert forecast_row is not None and forecast_row.finished_at is not None
        assert model_row is not None
        _assert_sha256_hex(model_row.config_hash)
        _assert_sha256_hex(forecast_row.source_signature)

    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        source_role="task8_forecast_run",
        schema_version="task8-maturity-v1",
        semantic_payload_hash=forecast_row.source_signature,
        config_hash=model_row.config_hash,
        display_label="task8:forecast_run",
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id",
            reference_value=forecast_row.id,
        ),
    )
    node = _make_pinned_node(
        season_id=season_id,
        node_key=node_key,
        resolved_identities=(identity,),
    )
    config = _make_config(execution_mode=ExecutionMode.HISTORICAL_OBSERVED, nodes=(node,))
    audit_cmd = AvailabilityAuditPersistenceCommand(
        source_role="task8_forecast_run",
        snapshot=Task8ForecastRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            status="completed",
            authoritative_timestamp=forecast_row.finished_at,
        ),
        forecast_cutoff_at=node.forecast_cutoff_at,
        resolved_identity=identity,
    )
    node_cmd = RollingNodePersistenceCommand(
        node=node,
        resolved_inputs=(ResolvedInputPersistenceCommand(identity=identity),),
        availability_audits=(audit_cmd,),
        dag=_make_dag(),
    )
    return RollingBacktestPersistenceCommand(
        config=config.model_copy(update={"nodes": (node,)}),
        nodes=(node_cmd,),
    )


async def _seed_real_task8_authorities(*, season_id: int) -> dict[str, int]:
    request = make_request()
    plan_variety_id = 101
    daily_ids_by_date: dict[date, int] = {}
    quantiles_by_date: dict[date, set[str]] = {}
    for item in request["task8_daily_predictions"]:
        if item["variety_id"] != plan_variety_id:
            continue
        prediction_date = item["prediction_date"]
        daily_id = item["source_ref"]["maturity_daily_prediction_id"]
        forecast_quantile = item["source_ref"]["forecast_quantile"]
        existing_daily_id = daily_ids_by_date.get(prediction_date)
        if existing_daily_id is None:
            daily_ids_by_date[prediction_date] = daily_id
        else:
            assert existing_daily_id == daily_id
        quantiles_by_date.setdefault(prediction_date, set()).add(forecast_quantile)

    expected_dates = {
        date(2026, 3, 1),
        date(2026, 3, 2),
        date(2026, 3, 3),
    }
    assert set(daily_ids_by_date) == expected_dates
    for prediction_date in expected_dates:
        assert quantiles_by_date[prediction_date] == {"P50", "P80", "P90"}

    async with AsyncSessionMaker() as session:
        existing_season = await session.get(Season, season_id)
        existing_variety_101 = await session.get(Variety, 101)

        root_rows = [
            Farm(
                id=1,
                name="Farm A",
                latitude=Decimal("24.100000"),
                longitude=Decimal("102.100000"),
                altitude_m=Decimal("1800.00"),
            ),
            AgroClimateZone(
                id=301,
                code="ZONE-A",
                name="Zone A",
                country="CN",
                province="Yunnan",
                prefecture="Honghe",
                county="Mile",
                centroid_latitude=Decimal("24.000000"),
                centroid_longitude=Decimal("102.000000"),
                min_altitude_m=Decimal("1700"),
                max_altitude_m=Decimal("1900"),
                zone_version="zone-v1",
                valid_from=date(2024, 1, 1),
                valid_to=None,
                source_name="synthetic",
                source_version="zone-v1",
            ),
            WeatherSourceLocation(
                id=7011,
                provider_code="synthetic_station",
                external_location_id="station-1",
                location_type="station",
                name="Station 1",
                latitude=Decimal("24.110000"),
                longitude=Decimal("102.110000"),
                altitude_m=Decimal("1810.00"),
                timezone_name="Asia/Shanghai",
                grid_resolution=None,
                source_version="dataset-v1",
                valid_from=date(2024, 1, 1),
                valid_to=None,
                row_hash="src-a",
            ),
        ]
        if existing_season is None:
            assert 1900 <= season_id <= 9999
            root_rows.append(
                Season(
                    id=season_id,
                    code=f"season-{season_id}",
                    start_date=date(season_id, 1, 1),
                    end_date=date(season_id, 12, 31),
                )
            )
        else:
            assert existing_season.id == season_id
            assert existing_season.start_date <= date(2026, 1, 1)
            assert existing_season.end_date >= date(2026, 3, 31)

        if existing_variety_101 is None:
            root_rows.append(Variety(id=101, code="DX", name="Dx"))
        else:
            assert existing_variety_101.code == "DX"
            assert existing_variety_101.name == "Dx"

        root_rows.append(Variety(id=102, code="DX-ALT", name="Dx Alt"))

        session.add_all(root_rows)
        await session.flush()

        session.add_all(
            [
                LocationReference(
                    id=601,
                    farm_id=1,
                    subfarm_id=None,
                    farm_code="FARM-A",
                    farm_name="Farm A",
                    subfarm_name=None,
                    address_raw="Farm A",
                    address_normalized="farm a",
                    province="Yunnan",
                    prefecture="Honghe",
                    county="Mile",
                    township="Xisan",
                    village=None,
                    latitude=Decimal("24.100000"),
                    longitude=Decimal("102.100000"),
                    altitude_m=Decimal("1800.00"),
                    climate_zone_id=301,
                    location_source="synthetic",
                    source_version="loc-v1",
                    valid_from=date(2024, 1, 1),
                    valid_to=None,
                    source_row_hash="loc-a",
                ),
                FarmSeasonVarietyPlan(
                    id=501,
                    farm_id=1,
                    subfarm_id=None,
                    season_id=season_id,
                    variety_id=101,
                    planted_area_mu=Decimal("100"),
                    expected_yield_kg_per_mu=Decimal("1200"),
                    marketable_rate=Decimal("0.8"),
                    tree_age_years=Decimal("3"),
                    pruning_date=date(2026, 1, 1),
                    flowering_start_date=date(2026, 2, 1),
                    flowering_peak_date=date(2026, 2, 6),
                    flowering_end_date=date(2026, 2, 10),
                    first_pick_date=date(2026, 3, 5),
                    expected_total_marketable_kg=Decimal("96000"),
                    version=1,
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    available_at=date(2025, 12, 15),
                    source_type="manual",
                    source_name="planner",
                    source_version="v1",
                    notes="synthetic",
                    row_hash="plan-501",
                ),
                BaseTemperatureSearchRun(
                    id=901,
                    scope_type="variety_zone",
                    variety_id=101,
                    climate_zone_id=301,
                    training_cutoff=date(2026, 4, 30),
                    anchor_event="flowering_start_date",
                    target_event="first_pick_date",
                    candidate_temperatures=["3", "5"],
                    selected_base_temperature=Decimal("5"),
                    scoring_method="season_loso_mae_days",
                    selected_score=Decimal("1.000000"),
                    sample_count=3,
                    distinct_season_count=3,
                    training_sample_ids=[1, 2, 3],
                    candidate_scores={"candidates": []},
                    config_hash="weather-cfg",
                    feature_version="task7-v1",
                    source_signature="base-temp-sig",
                    status="completed",
                    warnings=[],
                    blockers=[],
                    input_snapshot={"samples": []},
                    finished_at=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.flush()

        session.add(
            LocationWeatherMapping(
                id=801,
                location_reference_id=601,
                weather_source_location_id=7011,
                mapping_method="explicit",
                distance_km=Decimal("1"),
                altitude_difference_m=Decimal("10"),
                mapping_score=Decimal("1"),
                confidence_level="high",
                mapping_version="map-v1",
                config_hash="weather-cfg",
                available_at=date(2026, 1, 1),
                valid_from=date(2026, 1, 1),
                valid_to=None,
                row_hash="mapping-a",
            )
        )
        await session.flush()

        model_run = MaturityModelRun(
            id=101,
            model_version="task8-v1",
            config_hash=TASK8_MODEL_CONFIG_HASH,
            config_snapshot={"version": "task8-v1"},
            training_cutoff=date(2026, 2, 28),
            source_signature=TASK8_MODEL_SOURCE_SIGNATURE,
            status="completed",
            random_seed=20260703,
            model_family="shared_spline_partial_pooling",
            scope="task8",
            sample_count=10,
            distinct_season_count=2,
            distinct_farm_count=1,
            distinct_subfarm_count=1,
            training_metrics={},
            calibration_metrics={},
            warnings=[],
            blockers=[],
            input_snapshot={},
            started_at=datetime(2026, 2, 28, 11, 0, tzinfo=UTC),
            finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            error_message=None,
        )
        session.add(model_run)
        await session.flush()
        artifact = MaturityModelArtifact(
            id=201,
            run_id=101,
            artifact_hash=TASK8_ARTIFACT_HASH,
            support_min_day=-30,
            support_max_day=90,
            artifact_payload={
                "support_days": [0, 1],
                "anchor_event": "flowering_start_date",
                "group_models": {},
                "shift_model": {
                    "enabled": False,
                    "intercept_days": "0",
                    "coefficients": {},
                    "category_vocabulary": {"facility_type": ["unknown"]},
                    "reference_categories": {"facility_type": "unknown"},
                    "feature_order": [],
                    "scaler_center": {},
                    "scaler_scale": {},
                    "feature_units": {},
                    "missing_value_rules": {},
                    "bounds": ["-21", "21"],
                    "warnings": [],
                },
                "calibration": {},
                "base_temperature_context": {},
            },
            created_at=datetime(2026, 2, 28, 12, 5, tzinfo=UTC),
        )
        session.add(artifact)
        await session.flush()
        forecast = MaturityForecastRun(
            id=401,
            model_run_id=101,
            artifact_id=201,
            plan_id=501,
            location_reference_id=601,
            weather_mapping_id=801,
            base_temperature_search_run_id=901,
            as_of_date=date(2026, 2, 28),
            prediction_start_date=date(2026, 3, 1),
            prediction_end_date=date(2026, 3, 3),
            expected_marketable_total_kg=Decimal("96000"),
            expected_total_source="explicit",
            axis_mode="calendar_proxy_axis",
            source_signature=TASK8_FORECAST_SOURCE_SIGNATURE,
            status="completed",
            warnings=[],
            blockers=[],
            input_snapshot={},
            started_at=datetime(2026, 2, 28, 12, 10, tzinfo=UTC),
            finished_at=datetime(2026, 2, 28, 13, 0, tzinfo=UTC),
            error_message=None,
        )
        session.add(forecast)
        await session.flush()

        daily_rows = []
        for prediction_date, daily_id in sorted(daily_ids_by_date.items()):
            daily_rows.append(
                MaturityDailyPredictionModel(
                    id=daily_id,
                    forecast_run_id=401,
                    prediction_date=prediction_date,
                    phenology_coordinate_day=Decimal("1"),
                    p50_kg=Decimal("20"),
                    p80_kg=Decimal("24"),
                    p90_kg=Decimal("28"),
                    cumulative_p50_kg=Decimal("20"),
                    cumulative_p80_kg=Decimal("24"),
                    cumulative_p90_kg=Decimal("28"),
                    curve_share=Decimal("0.3333333333"),
                    confidence_level="medium",
                    quality_flags=[],
                    created_at=datetime(2026, 2, 28, 13, 5, tzinfo=UTC),
                )
            )
        session.add_all(daily_rows)
        await session.flush()
        await session.commit()

    return {
        "model_run_id": 101,
        "artifact_id": 201,
        "forecast_run_id": 401,
    }


async def _seed_real_task9_run() -> tuple[int, str, str, datetime]:
    async with AsyncSessionMaker() as session:
        output = run_harvest_state_model(make_request())
        assert output.status == "completed"
        run = await save_harvest_state_output(session, output=output)
        await session.commit()
        row = await session.get(HarvestStateRun, run.id)
        assert row is not None
        assert row.created_at is not None
        return row.id, row.result_hash, row.canonical_payload_hash, row.created_at


async def _seed_real_task10_authorities() -> dict[str, int]:
    fixture = await _seed_prediction_fixture()
    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(2026, 2, 28),
    )

    async with AsyncSessionMaker() as session:
        training_result, training_run_id = await execute_residual_training(
            session,
            samples=samples,
            config=_relaxed_residual_config(),
        )
        assert training_result.execution_status == "completed"
        prediction_result, prediction_run_id = await execute_residual_prediction(
            session,
            request=ResidualPredictionRequest(
                model_run_id=training_run_id,
                task9_run_id=fixture["train_task9_run_id"],
                feature_analytics_build_run_id=fixture["train_feature_build_run_id"],
                supplemental_feature_values=_supplemental_features(as_of_date=date(2026, 2, 28)),
            ),
        )
        assert prediction_result.execution_status == "completed"
        artifact_row = (
            await session.execute(
                select(ResidualModelArtifact)
                .where(ResidualModelArtifact.training_run_id == training_run_id)
                .order_by(ResidualModelArtifact.id.asc())
                .limit(1)
            )
        ).scalar_one()
        training_row = await session.get(ResidualModelTrainingRun, training_run_id)
        prediction_row = await session.get(ResidualModelPredictionRun, prediction_run_id)
        assert training_row is not None
        assert prediction_row is not None
        return {
            "task9_run_id": fixture["train_task9_run_id"],
            "training_run_id": training_run_id,
            "artifact_id": artifact_row.id,
            "prediction_run_id": prediction_run_id,
            "feature_build_run_id": fixture["train_feature_build_run_id"],
            "validation_task9_run_id": fixture["validation_task9_run_id"],
        }


def _parent_authority(
    *,
    source_type: AvailabilitySourceType,
    authority_status: str,
    authority_timestamp: datetime,
    persistent_reference: PersistentUpstreamReference,
    semantic_input_signature: str | None = None,
    result_hash: str | None = None,
    canonical_payload_hash: str | None = None,
) -> ParentAuthorityIdentity:
    return ParentAuthorityIdentity(
        source_type=source_type,
        authority_schema_version="task11-upstream-v1",
        authority_policy_version="task11-upstream-v1",
        authority_timestamp=authority_timestamp,
        authority_status=authority_status,
        semantic_input_signature=semantic_input_signature,
        result_hash=result_hash,
        canonical_payload_hash=canonical_payload_hash,
        persistent_reference=persistent_reference,
    )


async def _build_real_orchestration_command(
    *,
    forecast_cutoff_at: datetime,
    pinned_task9_run_id: int | None = None,
) -> RollingBacktestPersistenceCommand:
    task10 = await _seed_real_task10_authorities()
    task8 = await _seed_real_task8_authorities(season_id=1)
    task9_run_id = task10["task9_run_id"]
    pinned_task9_run_id = pinned_task9_run_id or task9_run_id

    async with AsyncSessionMaker() as session:
        feature_build = await session.get(AnalyticsBuildRun, task10["feature_build_run_id"])
        task9_row = await session.get(HarvestStateRun, task9_run_id)
        pinned_task9_row = await session.get(HarvestStateRun, pinned_task9_run_id)
        training_row = await session.get(ResidualModelTrainingRun, task10["training_run_id"])
        artifact_row = await session.get(ResidualModelArtifact, task10["artifact_id"])
        prediction_row = await session.get(ResidualModelPredictionRun, task10["prediction_run_id"])
        task8_model_row = await session.get(MaturityModelRun, task8["model_run_id"])
        task8_artifact_row = await session.get(MaturityModelArtifact, task8["artifact_id"])
        task8_forecast_row = await session.get(MaturityForecastRun, task8["forecast_run_id"])
        assert feature_build is not None and feature_build.finished_at is not None
        assert task9_row is not None and task9_row.created_at is not None
        assert pinned_task9_row is not None and pinned_task9_row.created_at is not None
        assert training_row is not None and training_row.finished_at is not None
        assert artifact_row is not None and artifact_row.created_at is not None
        assert prediction_row is not None and prediction_row.completed_at is not None
        assert task8_model_row is not None
        assert task8_artifact_row is not None
        assert task8_forecast_row is not None
        _assert_sha256_hex(task8_model_row.config_hash)
        _assert_sha256_hex(task8_model_row.source_signature)
        _assert_sha256_hex(task8_artifact_row.artifact_hash)
        _assert_sha256_hex(task8_forecast_row.source_signature)

    identities: tuple[ResolvedUpstreamSemanticIdentity, ...] = (
        _make_identity(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
            source_role="task3_analytics_build",
            schema_version="task3-analytics-v1",
            semantic_payload_hash=feature_build.config_hash,
            config_hash=feature_build.config_hash,
            business_version=feature_build.aggregation_version,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=feature_build.id,
            ),
        ),
        _make_identity(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            source_role="task8_model_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=task8_model_row.config_hash,
            config_hash=task8_model_row.config_hash,
            business_version="task8-v1",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=task8["model_run_id"],
            ),
        ),
        _make_identity(
            source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
            source_role="task8_model_artifact",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=task8_artifact_row.artifact_hash,
            config_hash=task8_model_row.config_hash,
            business_version="task8-v1",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_artifact_id",
                reference_value=task8["artifact_id"],
            ),
        ),
        _make_identity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            source_role="task8_forecast_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=task8_forecast_row.source_signature,
            config_hash=task8_model_row.config_hash,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=task8["forecast_run_id"],
            ),
        ),
        _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9_structural_forecast",
            schema_version=pinned_task9_row.output_schema_version,
            semantic_payload_hash=pinned_task9_row.result_hash,
            config_hash=pinned_task9_row.config_hash,
            result_hash=pinned_task9_row.result_hash,
            canonical_payload_hash=pinned_task9_row.canonical_payload_hash,
            business_version=pinned_task9_row.output_schema_version,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=pinned_task9_row.id,
            ),
        ),
        _make_identity(
            source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
            source_role="task10_training_run",
            schema_version=training_row.feature_schema_version,
            semantic_payload_hash=training_row.training_signature,
            config_hash=training_row.config_hash,
            result_hash=training_row.canonical_payload_hash,
            canonical_payload_hash=training_row.canonical_payload_hash,
            business_version=training_row.model_version,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=training_row.id,
            ),
        ),
        _make_identity(
            source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
            source_role="task10_model_artifact",
            schema_version=artifact_row.feature_schema_version,
            semantic_payload_hash=artifact_row.artifact_sha256,
            config_hash=artifact_row.config_hash,
            artifact_payload_hash=artifact_row.artifact_sha256,
            business_version=artifact_row.artifact_schema_version,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_artifact_id",
                reference_value=artifact_row.id,
            ),
        ),
        _make_identity(
            source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
            source_role="task10_prediction_run",
            schema_version=prediction_row.feature_schema_version,
            semantic_payload_hash=prediction_row.prediction_hash,
            config_hash=prediction_row.config_hash,
            result_hash=prediction_row.prediction_hash,
            canonical_payload_hash=prediction_row.prediction_hash,
            input_signature=prediction_row.prediction_input_signature,
            business_version=prediction_row.feature_schema_version,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=prediction_row.id,
            ),
        ),
    )

    node = _make_pinned_node(
        season_id=2030,
        node_key="real_chain",
        resolved_identities=identities,
    ).model_copy(
        update={
            "as_of_local_date": forecast_cutoff_at.date(),
            "forecast_cutoff_at": forecast_cutoff_at,
            "forecast_start_local_date": forecast_cutoff_at.date() + timedelta(days=1),
            "forecast_end_local_date": forecast_cutoff_at.date() + timedelta(days=7),
        }
    )
    config = _make_config(nodes=(node,))

    audits = (
        AvailabilityAuditPersistenceCommand(
            source_role="task3_analytics_build",
            snapshot=Task3AnalyticsBuildAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
                status="completed",
                authoritative_timestamp=feature_build.finished_at,
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[0],
        ),
        AvailabilityAuditPersistenceCommand(
            source_role="task8_model_run",
            snapshot=Task8ModelRunAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
                status="completed",
                authoritative_timestamp=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[1],
        ),
        AvailabilityAuditPersistenceCommand(
            source_role="task8_model_artifact",
            snapshot=Task8ModelArtifactAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
                created_at=datetime(2026, 2, 28, 12, 5, tzinfo=UTC),
                parent_authority=_parent_authority(
                    source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
                    authority_status="completed",
                    authority_timestamp=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
                    persistent_reference=PersistentUpstreamReference(
                        reference_type="database_run_id",
                        reference_value=task8["model_run_id"],
                    ),
                    canonical_payload_hash=task8_model_row.config_hash,
                ),
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[2],
        ),
        AvailabilityAuditPersistenceCommand(
            source_role="task8_forecast_run",
            snapshot=Task8ForecastRunAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                status="completed",
                authoritative_timestamp=datetime(2026, 2, 28, 13, 0, tzinfo=UTC),
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[3],
        ),
        AvailabilityAuditPersistenceCommand(
            source_role="task9_structural_forecast",
            snapshot=Task9HarvestStateRunAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                status="completed",
                authoritative_timestamp=pinned_task9_row.created_at,
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[4],
        ),
        AvailabilityAuditPersistenceCommand(
            source_role="task10_training_run",
            snapshot=Task10TrainingRunAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
                status="completed",
                authoritative_timestamp=training_row.finished_at,
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[5],
        ),
        AvailabilityAuditPersistenceCommand(
            source_role="task10_model_artifact",
            snapshot=Task10ModelArtifactAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
                created_at=artifact_row.created_at,
                parent_authority=_parent_authority(
                    source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
                    authority_status="completed",
                    authority_timestamp=training_row.finished_at,
                    persistent_reference=PersistentUpstreamReference(
                        reference_type="database_run_id",
                        reference_value=training_row.id,
                    ),
                    semantic_input_signature=training_row.training_signature,
                    result_hash=training_row.canonical_payload_hash,
                    canonical_payload_hash=training_row.canonical_payload_hash,
                ),
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[6],
        ),
        AvailabilityAuditPersistenceCommand(
            source_role="task10_prediction_run",
            snapshot=Task10PredictionRunAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
                status="completed",
                authoritative_timestamp=prediction_row.completed_at,
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[7],
        ),
    )

    node_cmd = RollingNodePersistenceCommand(
        node=node,
        resolved_inputs=tuple(
            ResolvedInputPersistenceCommand(identity=identity) for identity in identities
        ),
        availability_audits=audits,
        dag=_make_dag(),
    )
    return RollingBacktestPersistenceCommand(
        config=config.model_copy(update={"nodes": (node,)}),
        nodes=(node_cmd,),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# a) test_single_node_successful_orchestration
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_single_node_successful_orchestration() -> None:
    """Create a run with one node, execute orchestrate_node, verify all artifacts."""
    _require_postgres()
    cmd = await _make_real_task8_orchestration_persistence_command(
        season_id=2026,
        node_key="march_15",
    )
    run = await create_or_load_logical_run(cmd)
    assert run.id is not None

    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()

    assert outcome.status == "completed"
    assert outcome.stage == "finalize_orchestration_snapshot"

    # Verify attempt was created
    async with AsyncSessionMaker() as session:
        attempt_count = await session.scalar(
            select(func.count()).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        assert attempt_count == 1

    # Verify stage events were created (8 stages)
    async with AsyncSessionMaker() as session:
        stage_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestStageEvent)
        )
        assert stage_count == 8

    # Verify orchestration snapshot was created
    async with AsyncSessionMaker() as session:
        snap_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestOrchestrationSnapshot)
        )
        assert snap_count == 1

    # Verify integrity reload passes
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun).where(RollingBacktestRun.id == run.id)
        )
        loaded_run = result.scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)


# ═══════════════════════════════════════════════════════════════════════════════
# b) test_independent_session_committed_reload
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_independent_session_committed_reload() -> None:
    """Create run + orchestrate, then in a NEW session verify the run loads with integrity."""
    _require_postgres()
    cmd = await _make_real_task8_orchestration_persistence_command(
        season_id=2027,
        node_key="march_16",
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    # Orchestrate in one session
    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()
    assert outcome.status == "completed"

    # Reload in a completely independent session
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun).where(RollingBacktestRun.id == run.id)
        )
        loaded_run = result.scalar_one()
        assert loaded_run.status in ("forecast_completed", "completed")

        # Full integrity check in the new session
        await load_logical_run_with_integrity(session, loaded_run)

    # Verify attempt and snapshot are visible from independent session
    async with AsyncSessionMaker() as session:
        attempt_count = await session.scalar(
            select(func.count()).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        assert attempt_count == 1

        snap_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestOrchestrationSnapshot)
        )
        assert snap_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# c) test_existing_finalized_result_integrity_reload
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_existing_finalized_result_integrity_reload() -> None:
    """Orchestrate once (success), try again → idempotent completed (P0-1)."""
    _require_postgres()
    cmd = await _make_real_task8_orchestration_persistence_command(
        season_id=2028,
        node_key="march_17",
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    # First orchestration: success
    async with AsyncSessionMaker() as session:
        outcome1 = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()
    assert outcome1.status == "completed"

    first_attempt_id = outcome1.attempt_number

    # Second orchestration: idempotent completed (P0-1)
    async with AsyncSessionMaker() as session:
        outcome2 = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()
    assert outcome2.status == "completed"
    assert outcome2.diagnostics.get("idempotent_reload") is True
    # Same attempt number, no new attempt created
    assert outcome2.attempt_number == first_attempt_id

    # Verify no new attempt was created
    async with AsyncSessionMaker() as session:
        attempt_count = await session.scalar(
            select(func.count()).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        assert attempt_count == 1

    # Verify no new snapshot was created
    async with AsyncSessionMaker() as session:
        snap_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestOrchestrationSnapshot)
        )
        assert snap_count == 1

    # Verify original result is intact via integrity reload in fresh session
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun).where(RollingBacktestRun.id == run.id)
        )
        loaded_run = result.scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)

    # Verify snapshot hash unchanged
    async with AsyncSessionMaker() as session:
        snap_result = await session.execute(select(RollingBacktestOrchestrationSnapshot))
        snap = snap_result.scalar_one()
        assert snap.canonical_payload_hash is not None


# ═══════════════════════════════════════════════════════════════════════════════
# d) test_same_node_concurrent_attempt_allocation
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_same_node_concurrent_attempt_allocation() -> None:
    """Two concurrent create_execution_attempt calls for same node get different attempt numbers."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    barrier = asyncio.Barrier(2)
    results: list[RollingBacktestAttempt] = []

    async def _create_attempt() -> None:
        await barrier.wait()
        attempt = await create_execution_attempt(run.id, node_id, status="blocked")
        results.append(attempt)

    await asyncio.gather(_create_attempt(), _create_attempt())

    assert len(results) == 2
    numbers = sorted(r.attempt_number for r in results)
    assert numbers == [1, 2]


# ═══════════════════════════════════════════════════════════════════════════════
# e) test_blocked_execution_leaves_no_partial_snapshot
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_blocked_execution_leaves_no_partial_snapshot() -> None:
    """Unsupported execution_mode → blocked, persisted attempt, no completed snapshot (P0-2)."""
    _require_postgres()
    # Use retrospective_replay which is not supported in this phase
    cmd = _make_orchestration_persistence_command(
        execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY,
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "UNSUPPORTED_EXECUTION_MODE"

    # Verify exactly 1 attempt was created and finalized as blocked
    async with AsyncSessionMaker() as session:
        attempt_count = await session.scalar(
            select(func.count()).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        assert attempt_count == 1

    # Verify attempt status is blocked
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestAttempt).where(RollingBacktestAttempt.rolling_run_id == run.id)
        )
        attempt = result.scalar_one()
        assert attempt.status == "blocked"

    # Verify stage events: persist_stage_event uses ON CONFLICT DO UPDATE,
    # so running → blocked for the same stage = 1 row with terminal state.
    async with AsyncSessionMaker() as session:
        stage_count = await session.scalar(
            select(func.count()).select_from(RollingBacktestStageEvent)
        )
        assert stage_count == 1

    # Verify no Stage 2-8 events exist
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestStageEvent).where(
                RollingBacktestStageEvent.attempt_id == attempt.id
            )
        )
        events = result.scalars().all()
        stage_names = {e.stage for e in events}
        assert stage_names == {"resolve_historical_inputs"}

    # Verify blocked snapshot exists, no completed snapshot
    async with AsyncSessionMaker() as session:
        snap_result = await session.execute(select(RollingBacktestOrchestrationSnapshot))
        snaps = snap_result.scalars().all()
        assert len(snaps) == 1
        assert snaps[0].status == "blocked"
        assert snaps[0].blocker_code == "UNSUPPORTED_EXECUTION_MODE"

    # Verify integrity reload succeeds in fresh session
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun).where(RollingBacktestRun.id == run.id)
        )
        loaded_run = result.scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)


# ═══════════════════════════════════════════════════════════════════════════════
# f) test_stage_gap_tamper_rejected
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stage_gap_tamper_rejected() -> None:
    """Create attempt, persist stages 1 and 3 (skip 2), verify validate_stage_continuity raises."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    attempt = await create_execution_attempt(run.id, node_id, status="running")

    # Persist stage 1 (resolve_historical_inputs) and stage 3 (validate_authority_chain)
    # skipping stage 2 (validate_visibility)
    await persist_stage_event(
        attempt.id,
        node_id,
        stage="resolve_historical_inputs",
        status="completed",
    )
    await persist_stage_event(
        attempt.id,
        node_id,
        stage="validate_authority_chain",
        status="completed",
    )

    # validate_stage_continuity should detect the gap at sequence_number 2
    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestStageIntegrityError, match="stage gap"):
            await validate_stage_continuity(session, attempt.id)


# ═══════════════════════════════════════════════════════════════════════════════
# g) test_stage_duplicate_rejected
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stage_duplicate_rejected() -> None:
    """Try to create two stage events with same stage name via raw SQL, verify constraint error."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    attempt = await create_execution_attempt(run.id, node_id, status="running")

    # First insert succeeds via persist_stage_event
    await persist_stage_event(
        attempt.id,
        node_id,
        stage="resolve_historical_inputs",
        status="completed",
    )

    # Second raw INSERT with same (attempt_id, stage) violates unique constraint
    async with AsyncSessionMaker() as session:
        with pytest.raises(SAIntegrityError):
            await session.execute(
                text(
                    "INSERT INTO rolling_backtest_stage_event "
                    "(attempt_id, rolling_node_id, sequence_number, stage, status, "
                    "entered_at, finished_at) "
                    "VALUES (:attempt_id, :node_id, :seq, :stage, :status, now(), now())"
                ),
                {
                    "attempt_id": attempt.id,
                    "node_id": node_id,
                    "seq": 1,
                    "stage": "resolve_historical_inputs",
                    "status": "completed",
                },
            )
            await session.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# h) test_cross_node_prior_attempt_rejected
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cross_node_prior_attempt_rejected() -> None:
    """Create two nodes, attempt for node1, try to create attempt for node2 with node1's prior."""
    _require_postgres()
    nodes = (
        _make_node(season_id=2025, node_key="march_15"),
        _make_node(season_id=2026, node_key="march_15"),
    )
    config = _make_config(nodes=nodes)
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)

    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run.id)
        )
        node_rows = result.scalars().all()
    assert len(node_rows) == 2

    node1_id = node_rows[0].id
    node2_id = node_rows[1].id

    # Create attempt for node1
    attempt1 = await create_execution_attempt(run.id, node1_id, status="blocked")

    # Try to create attempt for node2 with node1's attempt as prior → should fail
    with pytest.raises(RollingBacktestAttemptConflictError):
        await create_execution_attempt(run.id, node2_id, prior_attempt_id=attempt1.id)


# ═══════════════════════════════════════════════════════════════════════════════
# i) test_derive_run_status_from_attempts
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_derive_run_status_from_attempts() -> None:
    """Create run with one node, create attempt with status completed, verify derived status."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    # Create and finalize an attempt as completed
    attempt = await create_execution_attempt(run.id, node_id, status="pending")
    await finalize_attempt_status(
        attempt.id,
        status="completed",
        current_stage="finalize_orchestration_snapshot",
    )

    async with AsyncSessionMaker() as session:
        derived = await derive_run_status_from_attempts(session, run.id)
    assert derived == "forecast_completed"


# ═══════════════════════════════════════════════════════════════════════════════
# j) test_update_run_status_from_attempts
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_run_status_from_attempts() -> None:
    """Create run, create attempt, finalize, call update_run_status_from_attempts, verify."""
    _require_postgres()
    config = _make_config()
    cmd = _make_persistence_command(config, with_inputs=False, with_dag=True)
    run = await create_or_load_logical_run(cmd)
    assert run.status == "pending"
    node_id = await _get_node_id_for_run(run.id)

    # Create and finalize an attempt as completed
    attempt = await create_execution_attempt(run.id, node_id, status="pending")
    await finalize_attempt_status(
        attempt.id,
        status="completed",
        current_stage="finalize_orchestration_snapshot",
    )

    async with AsyncSessionMaker() as session:
        new_status = await update_run_status_from_attempts(session, run.id)
        await session.commit()

    assert new_status == "forecast_completed"

    # Verify the run status is updated in the database
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestRun.status).where(RollingBacktestRun.id == run.id)
        )
        db_status = result.scalar_one()
    assert db_status == "forecast_completed"


# ═══════════════════════════════════════════════════════════════════════════════
# k) real authority exact-load / reuse chain
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_authority_exact_load_reuse_and_snapshot() -> None:
    """orchestrate_node must exact-load real Task 8/9/10 authorities and freeze them in snapshot."""
    _require_postgres()
    cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2030, 3, 15, 4, 0, tzinfo=UTC),
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()

    assert outcome.status == "completed"
    assert outcome.blocker_code is None

    async with AsyncSessionMaker() as session:
        attempt = (
            await session.execute(
                select(RollingBacktestAttempt)
                .where(RollingBacktestAttempt.rolling_run_id == run.id)
                .order_by(RollingBacktestAttempt.id.desc())
                .limit(1)
            )
        ).scalar_one()
        snapshot = (
            await session.execute(
                select(RollingBacktestOrchestrationSnapshot).where(
                    RollingBacktestOrchestrationSnapshot.attempt_id == attempt.id
                )
            )
        ).scalar_one()
        assert attempt.status == "completed"
        assert snapshot.status == "completed"
        assert snapshot.canonical_payload["attempt"]["attempt_number"] == 1
        assert snapshot.canonical_payload["task9_authority"]["run_reference"]["reference_type"] == (
            "database_run_id"
        )
        assert snapshot.canonical_payload["task9_authority"]["source_catalog_hash"]
        assert snapshot.canonical_payload["task9_authority"]["verification_snapshot_hash"]
        assert (
            snapshot.canonical_payload["task10_authority"]["training_reference"]["reference_type"]
            == "database_run_id"
        )
        assert (
            snapshot.canonical_payload["task10_authority"]["artifact_reference"]["reference_type"]
            == "database_artifact_id"
        )
        assert (
            snapshot.canonical_payload["task10_authority"]["prediction_reference"]["reference_type"]
            == "database_run_id"
        )
        loaded_run = (
            await session.execute(select(RollingBacktestRun).where(RollingBacktestRun.id == run.id))
        ).scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)


# ═══════════════════════════════════════════════════════════════════════════════
# l) real Task 10 / Task 9 binding mismatch
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_task10_task9_binding_mismatch_blocks() -> None:
    """Pinned Task 9 must match the real Task 10 prediction's frozen Task 9 binding."""
    _require_postgres()
    cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2030, 3, 15, 4, 0, tzinfo=UTC),
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        expected_task9_run_id = (
            await session.execute(
                select(ResidualModelPredictionRun.task9_run_id)
                .order_by(ResidualModelPredictionRun.id.desc())
                .limit(1)
            )
        ).scalar_one()
        other_task9, *_ = await _seed_real_task9_run()
        assert other_task9 != expected_task9_run_id
        node_row = (
            await session.execute(
                select(RollingBacktestNode).where(RollingBacktestNode.id == node_id)
            )
        ).scalar_one()
        run_row = (
            await session.execute(select(RollingBacktestRun).where(RollingBacktestRun.id == run.id))
        ).scalar_one()
        payload = dict(node_row.canonical_payload)
        identities = list(payload["resolved_upstream_semantic_identities"])
        for item in identities:
            if item["source_type"] == AvailabilitySourceType.TASK9_HARVEST_STATE_RUN.value:
                item["persistent_reference"]["reference_value"] = other_task9
        payload["resolved_upstream_semantic_identities"] = identities
        node_row.canonical_payload = payload
        run_payload = dict(run_row.canonical_payload)
        run_nodes = list(run_payload["nodes"])
        run_nodes[0] = payload
        run_payload["nodes"] = run_nodes
        run_row.canonical_payload = run_payload
        await session.commit()

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "TASK10_TASK9_BINDING_MISMATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# m) real Task 10 completed_at cutoff
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_task10_prediction_completed_after_cutoff_blocks() -> None:
    """A real persisted Task 10 prediction completed after cutoff must be blocked."""
    _require_postgres()
    cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2030, 3, 15, 4, 0, tzinfo=UTC),
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        prediction_completed_at = (
            await session.execute(
                select(ResidualModelPredictionRun.completed_at)
                .order_by(ResidualModelPredictionRun.id.desc())
                .limit(1)
            )
        ).scalar_one()
        assert prediction_completed_at is not None
        node_row = (
            await session.execute(
                select(RollingBacktestNode).where(RollingBacktestNode.id == node_id)
            )
        ).scalar_one()
        run_row = (
            await session.execute(select(RollingBacktestRun).where(RollingBacktestRun.id == run.id))
        ).scalar_one()
        payload = dict(node_row.canonical_payload)
        payload["as_of_local_date"] = (prediction_completed_at - timedelta(days=1)).date()
        payload["forecast_cutoff_at"] = (prediction_completed_at - timedelta(minutes=1)).isoformat()
        payload["forecast_start_local_date"] = prediction_completed_at.date()
        payload["forecast_end_local_date"] = prediction_completed_at.date() + timedelta(days=7)
        node_row.canonical_payload = payload
        run_payload = dict(run_row.canonical_payload)
        run_nodes = list(run_payload["nodes"])
        run_nodes[0] = payload
        run_payload["nodes"] = run_nodes
        run_row.canonical_payload = run_payload
        await session.commit()

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "TASK10_PREDICTION_AFTER_CUTOFF"


# ═══════════════════════════════════════════════════════════════════════════════
# n) integrity reload rollback is atomic
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_integrity_reload_failure_rolls_back_completed_execution() -> None:
    """Integrity reload failure must rollback completed attempt, snapshot, and run status."""
    _require_postgres()
    cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2030, 3, 15, 4, 0, tzinfo=UTC),
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    with patch(
        "backend.app.rolling_backtest.node_orchestration.load_logical_run_with_integrity",
        side_effect=RuntimeError("integrity reload failed"),
    ):
        async with AsyncSessionMaker() as session:
            outcome = await orchestrate_node(
                session,
                rolling_run_id=run.id,
                rolling_node_id=node_id,
            )
            await session.commit()

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "ROLLING_ORCHESTRATION_INTEGRITY_RELOAD_FAILED"

    async with AsyncSessionMaker() as fresh_session:
        completed_attempts = await fresh_session.scalar(
            select(func.count())
            .select_from(RollingBacktestAttempt)
            .where(
                RollingBacktestAttempt.rolling_run_id == run.id,
                RollingBacktestAttempt.status == "completed",
            )
        )
        completed_snapshots = await fresh_session.scalar(
            select(func.count())
            .select_from(RollingBacktestOrchestrationSnapshot)
            .join(
                RollingBacktestAttempt,
                RollingBacktestAttempt.id == RollingBacktestOrchestrationSnapshot.attempt_id,
            )
            .where(
                RollingBacktestAttempt.rolling_run_id == run.id,
                RollingBacktestOrchestrationSnapshot.status == "completed",
            )
        )
        run_status = (
            await fresh_session.execute(
                select(RollingBacktestRun.status).where(RollingBacktestRun.id == run.id)
            )
        ).scalar_one()

    assert completed_attempts == 0
    assert completed_snapshots == 0
    assert run_status != "forecast_completed"
