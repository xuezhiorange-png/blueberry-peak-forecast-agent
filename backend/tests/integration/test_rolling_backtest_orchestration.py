"""Task 11 node orchestration integration tests.

Requires PostgreSQL with RUN_POSTGRES_INTEGRATION=1 and APP_ENV=test.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError as SAIntegrityError

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.master_data import Farm, Season, Subfarm, Variety
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
    _task8_daily_prediction_payload_hash,
    orchestrate_node,
)
from backend.app.rolling_backtest.orchestration import OrchestrationStage
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
    Task3SourceVisibilityIdentity,
    Task8DailyPredictionAvailabilitySnapshot,
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
        resolved_inputs=(
            ResolvedInputPersistenceCommand(
                identity=identity,
                persistent_reference=identity.persistent_reference,
            ),
        ),
        availability_audits=(),
        dag=_make_dag(),
    )


def _revalidated_config(
    config: RollingBacktestConfig,
    *,
    nodes: tuple[RollingNodeDefinition, ...],
) -> RollingBacktestConfig:
    payload = config.model_dump(mode="python")
    payload["nodes"] = [node.model_dump(mode="python") for node in nodes]
    return RollingBacktestConfig.model_validate(payload)


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
                    persistent_reference=None,
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
                inputs = (
                    ResolvedInputPersistenceCommand(
                        identity=identity,
                        persistent_reference=identity.persistent_reference,
                    ),
                )
            elif all(item.identity.source_role != identity.source_role for item in inputs):
                inputs = (
                    *inputs,
                    ResolvedInputPersistenceCommand(
                        identity=identity,
                        persistent_reference=identity.persistent_reference,
                    ),
                )
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

    validated_config = _revalidated_config(
        config,
        nodes=tuple(cmd.node for cmd in node_cmds),
    )
    return RollingBacktestPersistenceCommand(config=validated_config, nodes=tuple(node_cmds))


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
    ).model_copy(
        update={
            "persistent_reference": PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=42,
            )
        }
    )
    node = _make_pinned_node(
        season_id=season_id,
        node_key="march_15",
        resolved_identities=(identity,),
    )
    config = _make_config(execution_mode=execution_mode, nodes=(node,))
    validated_node = config.nodes[0]
    validated_identity = validated_node.resolved_upstream_semantic_identities[0]

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
        forecast_cutoff_at=validated_node.forecast_cutoff_at,
        resolved_identity=validated_identity,
    )

    ri_cmd = ResolvedInputPersistenceCommand(
        identity=validated_identity,
        persistent_reference=validated_identity.persistent_reference,
    )
    node_cmd = RollingNodePersistenceCommand(
        node=validated_node,
        resolved_inputs=(ri_cmd,),
        availability_audits=(audit_cmd,),
        dag=_make_dag(),
    )

    return RollingBacktestPersistenceCommand(config=config, nodes=(node_cmd,))


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
        input_signature=forecast_row.source_signature,
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
    validated_node = config.nodes[0]
    validated_identity = validated_node.resolved_upstream_semantic_identities[0]
    audit_cmd = AvailabilityAuditPersistenceCommand(
        source_role="task8_forecast_run",
        snapshot=Task8ForecastRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            status="completed",
            authoritative_timestamp=forecast_row.finished_at,
        ),
        forecast_cutoff_at=validated_node.forecast_cutoff_at,
        resolved_identity=validated_identity,
    )
    node_cmd = RollingNodePersistenceCommand(
        node=validated_node,
        resolved_inputs=(
            ResolvedInputPersistenceCommand(
                identity=validated_identity,
                persistent_reference=validated_identity.persistent_reference,
            ),
        ),
        availability_audits=(audit_cmd,),
        dag=_make_dag(),
    )
    return RollingBacktestPersistenceCommand(config=config, nodes=(node_cmd,))


async def _seed_real_task8_authorities(*, season_id: int) -> dict[str, Any]:
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
        existing_farm = await session.get(Farm, 1)
        existing_season = await session.get(Season, season_id)
        existing_subfarm = await session.get(Subfarm, 11)
        existing_variety_101 = await session.get(Variety, 101)
        existing_zone = await session.get(AgroClimateZone, 301)
        existing_weather_source = await session.get(WeatherSourceLocation, 7011)

        root_rows = []
        if existing_farm is None:
            root_rows.append(
                Farm(
                    id=1,
                    name="Farm A",
                    latitude=Decimal("24.100000"),
                    longitude=Decimal("102.100000"),
                    altitude_m=Decimal("1800.00"),
                )
            )
        else:
            assert existing_farm.id == 1
            assert existing_farm.name == "Farm A"
        if existing_zone is None:
            root_rows.append(
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
                )
            )
        else:
            assert existing_zone.id == 301
            assert existing_zone.code == "ZONE-A"
        if existing_weather_source is None:
            root_rows.append(
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
                )
            )
        else:
            assert existing_weather_source.id == 7011
            assert existing_weather_source.timezone_name == "Asia/Shanghai"
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

        session.add_all(root_rows)
        await session.flush()

        if existing_subfarm is None:
            session.add(
                Subfarm(
                    id=11,
                    farm_id=1,
                    name="Block 11",
                    altitude_m=Decimal("1800.00"),
                )
            )
            await session.flush()
            persisted_subfarm = await session.get(Subfarm, 11)
        else:
            persisted_subfarm = existing_subfarm
        assert persisted_subfarm is not None
        assert persisted_subfarm.id == 11
        assert persisted_subfarm.farm_id == 1

        session.add_all(
            [
                LocationReference(
                    id=601,
                    farm_id=1,
                    subfarm_id=11,
                    farm_code="FARM-A",
                    farm_name="Farm A",
                    subfarm_name="Block 11",
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
                    subfarm_id=11,
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
        "season_id": season_id,
        "farm_id": 1,
        "subfarm_id": 11,
        "variety_id": 101,
        "plan_id": 501,
        "location_reference_id": 601,
        "weather_mapping_id": 801,
        "base_temperature_search_run_id": 901,
        "model_run_id": 101,
        "model_version": "task8-v1",
        "artifact_id": 201,
        "artifact_run_id": 101,
        "forecast_run_id": 401,
        "forecast_run_status": "completed",
        "forecast_as_of_date": date(2026, 2, 28),
        "prediction_start_date": date(2026, 3, 1),
        "prediction_end_date": date(2026, 3, 3),
        "daily_predictions_by_date": {
            prediction_date: {
                "id": daily_id,
                "p50_kg": Decimal("20"),
                "p80_kg": Decimal("24"),
                "p90_kg": Decimal("28"),
                "created_at": datetime(2026, 2, 28, 13, 5, tzinfo=UTC),
            }
            for prediction_date, daily_id in sorted(daily_ids_by_date.items())
        },
    }


async def _seed_real_task10_authorities(
    *,
    task8_authority: dict[str, Any] | None = None,
) -> dict[str, int]:
    fixture = await _seed_prediction_fixture(task8_authority=task8_authority)
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


def _task3_source_visibility(
    feature_build: AnalyticsBuildRun,
    *,
    forecast_cutoff_at: datetime,
) -> Task3SourceVisibilityIdentity:
    assert feature_build.finished_at is not None
    visible_through_at = min(feature_build.finished_at, forecast_cutoff_at)
    visibility_manifest_hash = sha256_payload(
        {
            "visibility_policy_version": "task11-task3-source-visibility-v1",
            "source_max_raw_id": feature_build.source_max_raw_id,
            "aggregation_version": feature_build.aggregation_version,
            "config_hash": feature_build.config_hash,
            "visible_through_at": visible_through_at,
        }
    )
    return Task3SourceVisibilityIdentity(
        visibility_policy_version="task11-task3-source-visibility-v1",
        source_max_raw_id=feature_build.source_max_raw_id,
        aggregation_version=feature_build.aggregation_version,
        config_hash=feature_build.config_hash,
        visibility_manifest_hash=visibility_manifest_hash,
        visible_through_at=visible_through_at,
    )


async def _build_real_orchestration_command(
    *,
    forecast_cutoff_at: datetime,
    pinned_task9_variant: str = "training",
) -> RollingBacktestPersistenceCommand:
    assert forecast_cutoff_at.year == 2026
    task8 = await _seed_real_task8_authorities(season_id=2026)
    task8_authority = {
        "season_id": task8["season_id"],
        "farm_id": task8["farm_id"],
        "subfarm_id": task8["subfarm_id"],
        "variety_id": task8["variety_id"],
        "plan_id": task8["plan_id"],
        "location_reference_id": task8["location_reference_id"],
        "weather_mapping_id": task8["weather_mapping_id"],
        "base_temperature_search_run_id": task8["base_temperature_search_run_id"],
        "model_run_id": task8["model_run_id"],
        "model_version": task8["model_version"],
        "model_config_hash": TASK8_MODEL_CONFIG_HASH,
        "model_source_signature": TASK8_MODEL_SOURCE_SIGNATURE,
        "artifact_id": task8["artifact_id"],
        "artifact_run_id": task8["artifact_run_id"],
        "artifact_hash": TASK8_ARTIFACT_HASH,
        "forecast_run_id": task8["forecast_run_id"],
        "forecast_run_status": task8["forecast_run_status"],
        "forecast_source_signature": TASK8_FORECAST_SOURCE_SIGNATURE,
        "forecast_as_of_date": task8["forecast_as_of_date"],
        "prediction_start_date": task8["prediction_start_date"],
        "prediction_end_date": task8["prediction_end_date"],
        "daily_predictions_by_date": task8["daily_predictions_by_date"],
    }
    task10 = await _seed_real_task10_authorities(task8_authority=task8_authority)
    task9_run_id = task10["task9_run_id"]
    if pinned_task9_variant == "training":
        pinned_task9_run_id = task10["task9_run_id"]
    elif pinned_task9_variant == "validation":
        pinned_task9_run_id = task10["validation_task9_run_id"]
    else:
        raise AssertionError(f"unsupported pinned_task9_variant={pinned_task9_variant}")

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

        # ── Fixture parity: Task 9 envelope must match real Task 8 DB rows ──
        task9_input = task9_row.input_snapshot
        t8_preds = task9_input["task8_daily_predictions"]
        assert len(t8_preds) == 9
        first_vs = t8_preds[0]["verification_snapshot"]
        assert first_vs["maturity_model_run_id"] == task8_model_row.id
        assert first_vs["maturity_model_version"] == task8["model_version"]
        assert first_vs["maturity_model_config_hash"] == task8_model_row.config_hash
        assert first_vs["maturity_model_source_signature"] == task8_model_row.source_signature
        assert first_vs["maturity_model_artifact_id"] == task8_artifact_row.id
        assert first_vs["maturity_model_artifact_hash"] == task8_artifact_row.artifact_hash
        assert first_vs["maturity_forecast_run_id"] == task8_forecast_row.id
        assert first_vs["maturity_forecast_source_signature"] == task8_forecast_row.source_signature
        assert first_vs["plan_id"] == task8["plan_id"]
        assert first_vs["location_reference_id"] == task8["location_reference_id"]
        assert first_vs["farm_id"] == task8["farm_id"]
        assert first_vs["subfarm_id"] == task8["subfarm_id"]
        assert first_vs["variety_id"] == task8["variety_id"]

        task9_daily_ids = {
            item["verification_snapshot"]["maturity_daily_prediction_id"] for item in t8_preds
        }
        db_daily_ids = {payload["id"] for payload in task8["daily_predictions_by_date"].values()}
        expected_dates = set(task8["daily_predictions_by_date"])
        assert db_daily_ids == task9_daily_ids, (
            f"Task 8 DB daily IDs {db_daily_ids} != Task 9 daily IDs {task9_daily_ids}"
        )
        entry_count_by_date: dict[date, int] = {}
        task9_daily_ids_by_date: dict[date, set[int]] = {}
        varieties_in_task9 = {item.get("variety_id") for item in t8_preds}
        assert varieties_in_task9 == {101}, f"expected only variety 101, got {varieties_in_task9}"
        for item in t8_preds:
            source_ref_hash = item["source_ref_hash"]
            verification = item["verification_snapshot"]
            expected_daily = task8["daily_predictions_by_date"][item["prediction_date"]]
            assert len(source_ref_hash) == 64
            entry_count_by_date[item["prediction_date"]] = (
                entry_count_by_date.get(item["prediction_date"], 0) + 1
            )
            task9_daily_ids_by_date.setdefault(item["prediction_date"], set()).add(
                verification["maturity_daily_prediction_id"]
            )
            assert verification["maturity_daily_prediction_id"] == expected_daily["id"]
            assert (
                verification["maturity_daily_prediction_forecast_run_id"]
                == task8["forecast_run_id"]
            )
            assert verification["maturity_forecast_run_id"] == task8["forecast_run_id"]
            assert verification["maturity_model_run_id"] == task8["model_run_id"]
            assert verification["maturity_model_artifact_id"] == task8["artifact_id"]
            assert verification["plan_id"] == task8["plan_id"]
            assert verification["location_reference_id"] == task8["location_reference_id"]
            assert verification["farm_id"] == task8["farm_id"]
            assert verification["subfarm_id"] == task8["subfarm_id"]
            assert verification["variety_id"] == task8["variety_id"]
            assert verification["p50_kg"] == expected_daily["p50_kg"]
            assert verification["p80_kg"] == expected_daily["p80_kg"]
            assert verification["p90_kg"] == expected_daily["p90_kg"]
        assert set(entry_count_by_date) == expected_dates
        for prediction_date in expected_dates:
            assert entry_count_by_date[prediction_date] == 3
            assert task9_daily_ids_by_date[prediction_date] == {
                task8["daily_predictions_by_date"][prediction_date]["id"]
            }

    identity_items: list[ResolvedUpstreamSemanticIdentity] = [
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
            input_signature=task8_forecast_row.source_signature,
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
    ]
    daily_audits: list[AvailabilityAuditPersistenceCommand] = []
    forecast_parent = _parent_authority(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        authority_status="completed",
        authority_timestamp=datetime(2026, 2, 28, 13, 0, tzinfo=UTC),
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id",
            reference_value=task8["forecast_run_id"],
        ),
        semantic_input_signature=task8_forecast_row.source_signature,
        canonical_payload_hash=task8_forecast_row.source_signature,
    )
    for prediction_date, daily_payload in sorted(task8["daily_predictions_by_date"].items()):
        daily_row = await session.get(MaturityDailyPredictionModel, daily_payload["id"])
        assert daily_row is not None
        daily_hash = _task8_daily_prediction_payload_hash(
            daily_row,
            forecast_source_signature=task8_forecast_row.source_signature,
        )
        source_role = f"task8_daily_prediction:{prediction_date.isoformat()}"
        identity_items.append(
            _make_identity(
                source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
                source_role=source_role,
                schema_version="task8-maturity-v1",
                semantic_payload_hash=daily_hash,
                input_signature=task8_forecast_row.source_signature,
                canonical_payload_hash=daily_hash,
                business_version="task8-v1",
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_row_id",
                    reference_value=daily_row.id,
                ),
            )
        )
        daily_audits.append(
            AvailabilityAuditPersistenceCommand(
                source_role=source_role,
                snapshot=Task8DailyPredictionAvailabilitySnapshot(
                    source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
                    prediction_date=prediction_date,
                    created_at=daily_payload["created_at"],
                    parent_authority=forecast_parent,
                ),
                forecast_cutoff_at=forecast_cutoff_at,
                resolved_identity=identity_items[-1],
            )
        )

    identities = tuple(identity_items)

    node = _make_pinned_node(
        season_id=2026,
        node_key="march_15",
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
                task3_source_visibility=_task3_source_visibility(
                    feature_build,
                    forecast_cutoff_at=node.forecast_cutoff_at,
                ),
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
        *daily_audits,
    )

    validated_node = config.nodes[0]
    task3_snapshot = audits[0].snapshot
    assert task3_snapshot.task3_source_visibility is not None
    assert task3_snapshot.task3_source_visibility.visible_through_at <= node.forecast_cutoff_at
    assert (
        task3_snapshot.task3_source_visibility.aggregation_version
        == feature_build.aggregation_version
    )
    assert task3_snapshot.task3_source_visibility.config_hash == feature_build.config_hash
    assert len(task3_snapshot.task3_source_visibility.visibility_manifest_hash) == 64
    validated_identity_by_role = {
        identity.source_role: identity
        for identity in validated_node.resolved_upstream_semantic_identities
    }
    validated_audits = tuple(
        replace(audit, resolved_identity=validated_identity_by_role[audit.source_role])
        for audit in audits
    )
    node_cmd = RollingNodePersistenceCommand(
        node=validated_node,
        resolved_inputs=tuple(
            ResolvedInputPersistenceCommand(
                identity=identity,
                persistent_reference=identity.persistent_reference,
            )
            for identity in validated_node.resolved_upstream_semantic_identities
        ),
        availability_audits=validated_audits,
        dag=_make_dag(),
    )
    return RollingBacktestPersistenceCommand(config=config, nodes=(node_cmd,))


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

    assert outcome.status == "completed", (
        outcome.blocker_code,
        outcome.stage,
        outcome.diagnostics,
    )
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
        node_key="march_15",
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
    assert outcome.status == "completed", (
        outcome.blocker_code,
        outcome.stage,
        outcome.diagnostics,
    )

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
        node_key="march_15",
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
    assert outcome1.status == "completed", (
        outcome1.blocker_code,
        outcome1.stage,
        outcome1.diagnostics,
    )

    first_attempt_id = outcome1.attempt_number

    # Second orchestration: idempotent completed (P0-1)
    async with AsyncSessionMaker() as session:
        outcome2 = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()
    assert outcome2.status == "completed", (
        outcome2.blocker_code,
        outcome2.stage,
        outcome2.diagnostics,
    )
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
        forecast_cutoff_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
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

    assert outcome.status == "completed", (
        outcome.blocker_code,
        outcome.stage,
        outcome.diagnostics,
    )
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
        task8_authorities = snapshot.canonical_payload["task8_authorities"]
        snapshot_daily_entries = [
            payload
            for payload in task8_authorities.values()
            if payload["source_type"] == "task8_daily_prediction"
        ]
        assert len(snapshot_daily_entries) == 3
        snapshot_daily_ids = {
            entry["persistent_reference"]["reference_value"] for entry in snapshot_daily_entries
        }
        assert {
            entry["persistent_reference"]["reference_type"] for entry in snapshot_daily_entries
        } == {"database_row_id"}
        assert {entry["source_role"] for entry in snapshot_daily_entries} == {
            "task8_daily_prediction:2026-03-01",
            "task8_daily_prediction:2026-03-02",
            "task8_daily_prediction:2026-03-03",
        }
        task9_run_id = snapshot.canonical_payload["task9_authority"]["run_reference"][
            "reference_value"
        ]
        task9_row = await session.get(HarvestStateRun, task9_run_id)
        assert task9_row is not None
        task9_daily_ids = {
            item["verification_snapshot"]["maturity_daily_prediction_id"]
            for item in task9_row.input_snapshot["task8_daily_predictions"]
        }
        db_daily_ids = set(
            (
                await session.execute(
                    select(MaturityDailyPredictionModel.id).where(
                        MaturityDailyPredictionModel.forecast_run_id == 401
                    )
                )
            )
            .scalars()
            .all()
        )
        assert db_daily_ids == task9_daily_ids == snapshot_daily_ids
        loaded_run = (
            await session.execute(select(RollingBacktestRun).where(RollingBacktestRun.id == run.id))
        ).scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)


@pytest.mark.asyncio
async def test_cross_season_task8_authority_blocks() -> None:
    """Pinned Task 8/9 authorities from season 2026 must block a season-2027 node."""
    _require_postgres()
    base_cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
    )
    cross_node_payload = base_cmd.config.nodes[0].model_dump(mode="python")
    cross_node_payload.update(
        {
            "season_id": 2027,
            "as_of_local_date": date(2027, 3, 15),
            "forecast_cutoff_at": datetime(2027, 3, 15, 4, 0, tzinfo=UTC),
            "forecast_start_local_date": date(2027, 3, 16),
            "forecast_end_local_date": date(2027, 3, 31),
        }
    )
    cross_node = RollingNodeDefinition.model_validate(cross_node_payload)
    cross_config = RollingBacktestConfig.model_validate(
        {
            **base_cmd.config.model_dump(mode="python"),
            "nodes": (cross_node.model_dump(mode="python"),),
        }
    )
    validated_node = cross_config.nodes[0]
    validated_identity_by_role = {
        identity.source_role: identity
        for identity in validated_node.resolved_upstream_semantic_identities
    }
    base_node_cmd = base_cmd.nodes[0]
    cross_node_cmd = RollingNodePersistenceCommand(
        node=validated_node,
        resolved_inputs=tuple(
            ResolvedInputPersistenceCommand(
                identity=validated_identity_by_role[item.identity.source_role],
                persistent_reference=item.persistent_reference,
            )
            for item in base_node_cmd.resolved_inputs
        ),
        availability_audits=tuple(
            replace(
                audit,
                forecast_cutoff_at=validated_node.forecast_cutoff_at,
                resolved_identity=validated_identity_by_role[audit.source_role],
            )
            for audit in base_node_cmd.availability_audits
        ),
        dag=base_node_cmd.dag,
    )
    cross_cmd = RollingBacktestPersistenceCommand(config=cross_config, nodes=(cross_node_cmd,))
    run = await create_or_load_logical_run(cross_cmd)
    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=run.id,
            rolling_node_id=node_id,
        )
        await session.commit()

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "PINNED_SOURCE_SCOPE_MISMATCH"
    assert outcome.stage == OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value
    assert "2027" in str(outcome.diagnostics)
    assert "2026" in str(outcome.diagnostics)


# ═══════════════════════════════════════════════════════════════════════════════
# l) real Task 10 / Task 9 binding mismatch
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_task10_task9_binding_mismatch_blocks() -> None:
    """Pinned Task 9 must match the real Task 10 prediction's frozen Task 9 binding."""
    _require_postgres()
    forecast_cutoff_at = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=forecast_cutoff_at,
        pinned_task9_variant="validation",
    )
    pinned_task9_identity = next(
        identity
        for identity in cmd.config.nodes[0].resolved_upstream_semantic_identities
        if identity.source_role == "task9_structural_forecast"
    )
    pinned_task9_run_id = pinned_task9_identity.persistent_reference.reference_value
    assert isinstance(pinned_task9_run_id, int)

    async with AsyncSessionMaker() as session:
        prediction_task9_run_id = (
            await session.execute(
                select(ResidualModelPredictionRun.task9_run_id)
                .order_by(ResidualModelPredictionRun.id.desc())
                .limit(1)
            )
        ).scalar_one()
        prediction_task9_row = await session.get(HarvestStateRun, prediction_task9_run_id)
        validation_task9_row = await session.get(HarvestStateRun, pinned_task9_run_id)
        assert prediction_task9_row is not None
        assert validation_task9_row is not None
        assert pinned_task9_run_id != prediction_task9_run_id
        assert validation_task9_row.result_hash != prediction_task9_row.result_hash
        assert (
            validation_task9_row.canonical_payload_hash
            != prediction_task9_row.canonical_payload_hash
        )
    mismatched_run = await create_or_load_logical_run(cmd)
    mismatched_node_id = await _get_node_id_for_run(mismatched_run.id)

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=mismatched_run.id,
            rolling_node_id=mismatched_node_id,
        )
        await session.commit()

    assert outcome.status == "blocked"
    assert outcome.blocker_code == "TASK10_TASK9_BINDING_MISMATCH"
    assert outcome.stage == OrchestrationStage.RESOLVE_OR_TRAIN_TASK10.value


# ═══════════════════════════════════════════════════════════════════════════════
# m) real Task 10 completed_at cutoff
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_task10_prediction_completed_after_cutoff_blocks() -> None:
    """A real persisted Task 10 prediction completed after cutoff must be blocked."""
    _require_postgres()
    cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
    )
    run = await create_or_load_logical_run(cmd)
    node_id = await _get_node_id_for_run(run.id)

    async with AsyncSessionMaker() as session:
        prediction_run_id = (
            await session.execute(
                select(ResidualModelPredictionRun.id)
                .order_by(ResidualModelPredictionRun.id.desc())
                .limit(1)
            )
        ).scalar_one()
        node_row = (
            await session.execute(
                select(RollingBacktestNode).where(RollingBacktestNode.id == node_id)
            )
        ).scalar_one()
        prediction_row = await session.get(ResidualModelPredictionRun, prediction_run_id)
        assert prediction_row is not None
        prediction_row.completed_at = node_row.forecast_cutoff_at + timedelta(minutes=1)
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
    assert outcome.stage == "resolve_or_train_task10"

    async with AsyncSessionMaker() as session:
        attempt = (
            await session.execute(
                select(RollingBacktestAttempt)
                .where(RollingBacktestAttempt.rolling_run_id == run.id)
                .order_by(RollingBacktestAttempt.attempt_number.desc())
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
        events = (
            (
                await session.execute(
                    select(RollingBacktestStageEvent)
                    .where(RollingBacktestStageEvent.attempt_id == attempt.id)
                    .order_by(RollingBacktestStageEvent.sequence_number.asc())
                )
            )
            .scalars()
            .all()
        )

    assert attempt.current_stage == "resolve_or_train_task10"
    assert snapshot.terminal_stage == "resolve_or_train_task10"
    assert [event.stage for event in events] == [
        "resolve_historical_inputs",
        "validate_visibility",
        "validate_authority_chain",
        "resolve_or_replay_task8",
        "resolve_or_replay_task9",
        "resolve_or_train_task10",
    ]
    assert [event.status for event in events[:-1]] == ["completed"] * 5
    assert events[-1].status == "blocked"


# ═══════════════════════════════════════════════════════════════════════════════
# n) integrity reload rollback is atomic
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_integrity_reload_failure_rolls_back_completed_execution() -> None:
    """Integrity reload failure must rollback completed attempt, snapshot, and run status."""
    _require_postgres()
    cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
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
