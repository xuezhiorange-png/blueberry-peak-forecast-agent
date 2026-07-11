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
from zoneinfo import ZoneInfo

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
    DefaultNodeKey,
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
TASK11_FEBRUARY_END_CUTOFF_HOUR_UTC = 4


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
    request = make_request(season_id=season_id)
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
        date(season_id, 3, 1),
        date(season_id, 3, 2),
        date(season_id, 3, 3),
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
            assert existing_season.start_date <= date(season_id, 1, 1)
            assert existing_season.end_date >= date(season_id, 3, 31)

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

        # All Task 8 authority rows use fixed, deterministic IDs so the
        # authority identity is stable across the rolling-backtest
        # contract. `_seed_real_task8_authorities` is called more than
        # once within a single test function (e.g. historical_resolution
        # paths first call `_build_real_orchestration_command` to lay
        # down the canonical authorities, then call it again via
        # `_build_real_historical_resolution_command` to compose the
        # pinned identity set). A bare `session.add(...)` on the second
        # call would raise UniqueViolationError on the primary key, so
        # each row below is gated on an existence probe that mirrors
        # the Farm / Zone / WeatherSourceLocation / Season / Variety /
        # Subfarm blocks above. When the row already exists we still
        # assert the deterministic identity fields are intact so a
        # mis-seeded prior test cannot silently leak into this fixture.
        existing_location_reference = await session.get(LocationReference, 601)
        if existing_location_reference is None:
            session.add(
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
                )
            )
            await session.flush()
        else:
            assert existing_location_reference.id == 601
            assert existing_location_reference.farm_id == 1
            assert existing_location_reference.subfarm_id == 11
            assert existing_location_reference.source_row_hash == "loc-a"

        existing_plan = await session.get(FarmSeasonVarietyPlan, 501)
        if existing_plan is None:
            session.add(
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
                    pruning_date=date(season_id, 1, 1),
                    flowering_start_date=date(season_id, 2, 1),
                    flowering_peak_date=date(season_id, 2, 6),
                    flowering_end_date=date(season_id, 2, 10),
                    first_pick_date=date(season_id, 3, 5),
                    expected_total_marketable_kg=Decimal("96000"),
                    version=1,
                    effective_from=date(season_id, 1, 1),
                    effective_to=None,
                    available_at=date(2025, 12, 15),
                    source_type="manual",
                    source_name="planner",
                    source_version="v1",
                    notes="synthetic",
                    row_hash="plan-501",
                )
            )
            await session.flush()
        else:
            assert existing_plan.id == 501
            assert existing_plan.farm_id == 1
            assert existing_plan.subfarm_id == 11
            assert existing_plan.season_id == season_id
            assert existing_plan.variety_id == 101
            assert existing_plan.row_hash == "plan-501"

        existing_base_temp = await session.get(BaseTemperatureSearchRun, 901)
        if existing_base_temp is None:
            session.add(
                BaseTemperatureSearchRun(
                    id=901,
                    scope_type="variety_zone",
                    variety_id=101,
                    climate_zone_id=301,
                    training_cutoff=date(season_id, 4, 30),
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
                    finished_at=datetime(season_id, 2, 20, 12, 0, tzinfo=UTC),
                )
            )
            await session.flush()
        else:
            assert existing_base_temp.id == 901
            assert existing_base_temp.variety_id == 101
            assert existing_base_temp.climate_zone_id == 301
            assert existing_base_temp.source_signature == "base-temp-sig"

        existing_weather_mapping = await session.get(LocationWeatherMapping, 801)
        if existing_weather_mapping is None:
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
                    available_at=date(season_id, 1, 1),
                    valid_from=date(season_id, 1, 1),
                    valid_to=None,
                    row_hash="mapping-a",
                )
            )
            await session.flush()
        else:
            assert existing_weather_mapping.id == 801
            assert existing_weather_mapping.location_reference_id == 601
            assert existing_weather_mapping.weather_source_location_id == 7011

        existing_model_run = await session.get(MaturityModelRun, 101)
        if existing_model_run is None:
            model_run = MaturityModelRun(
                id=101,
                model_version="task8-v1",
                config_hash=TASK8_MODEL_CONFIG_HASH,
                config_snapshot={"version": "task8-v1"},
                training_cutoff=date(season_id, 2, 28),
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
                started_at=datetime(season_id, 2, 28, 2, 0, tzinfo=UTC),
                finished_at=datetime(season_id, 2, 28, 3, 0, tzinfo=UTC),
                error_message=None,
            )
            session.add(model_run)
            await session.flush()
        else:
            assert existing_model_run.id == 101
            assert existing_model_run.model_version == "task8-v1"
            _assert_sha256_hex(existing_model_run.config_hash)
            _assert_sha256_hex(existing_model_run.source_signature)
            assert existing_model_run.status == "completed"

        existing_model_artifact = await session.get(MaturityModelArtifact, 201)
        if existing_model_artifact is None:
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
                created_at=datetime(season_id, 2, 28, 3, 5, tzinfo=UTC),
            )
            session.add(artifact)
            await session.flush()
        else:
            assert existing_model_artifact.id == 201
            assert existing_model_artifact.run_id == 101
            _assert_sha256_hex(existing_model_artifact.artifact_hash)

        existing_forecast_run = await session.get(MaturityForecastRun, 401)
        if existing_forecast_run is None:
            forecast = MaturityForecastRun(
                id=401,
                model_run_id=101,
                artifact_id=201,
                plan_id=501,
                location_reference_id=601,
                weather_mapping_id=801,
                base_temperature_search_run_id=901,
                as_of_date=date(season_id, 2, 28),
                prediction_start_date=date(season_id, 3, 1),
                prediction_end_date=date(season_id, 3, 3),
                expected_marketable_total_kg=Decimal("96000"),
                expected_total_source="explicit",
                axis_mode="calendar_proxy_axis",
                source_signature=TASK8_FORECAST_SOURCE_SIGNATURE,
                status="completed",
                warnings=[],
                blockers=[],
                input_snapshot={},
                started_at=datetime(season_id, 2, 28, 3, 10, tzinfo=UTC),
                finished_at=datetime(season_id, 2, 28, 3, 30, tzinfo=UTC),
                error_message=None,
            )
            session.add(forecast)
            await session.flush()
        else:
            assert existing_forecast_run.id == 401
            assert existing_forecast_run.model_run_id == 101
            assert existing_forecast_run.artifact_id == 201
            assert existing_forecast_run.plan_id == 501
            assert existing_forecast_run.location_reference_id == 601
            assert existing_forecast_run.weather_mapping_id == 801
            assert existing_forecast_run.base_temperature_search_run_id == 901
            assert existing_forecast_run.status == "completed"
            _assert_sha256_hex(existing_forecast_run.source_signature)

        # Daily prediction rows are keyed on per-date IDs derived from
        # the make_request() fixture. Insert only the missing dates so
        # a repeated seed call cannot violate the row_hash contract or
        # double-write completed forecast children.
        for prediction_date, daily_id in sorted(daily_ids_by_date.items()):
            existing_daily = await session.get(MaturityDailyPredictionModel, daily_id)
            if existing_daily is not None:
                assert existing_daily.forecast_run_id == 401
                assert existing_daily.prediction_date == prediction_date
                continue
            session.add(
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
                    created_at=datetime(season_id, 2, 28, 3, 35, tzinfo=UTC),
                )
            )
            await session.flush()
        await session.commit()
        # Explicit close so the connection returns to the pool fully
        # reset. See the comment in _seed_real_task10_authorities.
        await session.close()

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
        "forecast_as_of_date": date(season_id, 2, 28),
        "prediction_start_date": date(season_id, 3, 1),
        "prediction_end_date": date(season_id, 3, 3),
        "daily_predictions_by_date": {
            prediction_date: {
                "id": daily_id,
                "p50_kg": Decimal("20"),
                "p80_kg": Decimal("24"),
                "p90_kg": Decimal("28"),
                "created_at": datetime(season_id, 2, 28, 3, 35, tzinfo=UTC),
            }
            for prediction_date, daily_id in sorted(daily_ids_by_date.items())
        },
    }


async def _seed_real_task10_authorities(
    *,
    task8_authority: dict[str, Any] | None = None,
    analytics_season_id: int | None = None,
    feature_build_finished_at: datetime | None = None,
) -> dict[str, int]:
    # Re-anchor the diverse-training-samples as_of_date to the same
    # season as the request payload so the manifest builder's
    # `date_outside_build_season` exclusion does not drop any
    # structural row. When `analytics_season_id` is None the legacy
    # 2026 fixture is used.
    fixture_season_id_for_samples = analytics_season_id if analytics_season_id is not None else 2026

    # Idempotency guard: a single test can call this helper more than
    # once when it composes `_build_real_orchestration_command` with
    # `_build_real_historical_resolution_command`. The historical path
    # then runs SQL `resolve_historical` over every HarvestStateRun
    # whose created_at <= forecast_cutoff_at, ordered by created_at
    # desc. If a second call re-creates the train task9 run, the
    # resolved Task 9 reference would point at the *newer* run while
    # the previously-persisted residual prediction still binds the
    # earlier run, and the stage-6 `_resolve_task10_reuse` contract
    # `prediction.task9_run_id == ctx.task9_authority.reference_value`
    # would fail with TASK10_TASK9_BINDING_MISMATCH. Detect an
    # existing trio (one train task9, one completed training run,
    # one completed prediction run) and return it instead of seeding
    # fresh data so the historical resolver still sees the same
    # authority chain. The conftest.py autouse fixture already
    # truncates these tables between tests, so reuse only happens
    # within a single test invocation.
    async with AsyncSessionMaker() as session:
        existing_prediction = (
            await session.execute(
                select(ResidualModelPredictionRun)
                .where(ResidualModelPredictionRun.completed_at.is_not(None))
                .order_by(
                    ResidualModelPredictionRun.completed_at.asc().nullslast(),
                    ResidualModelPredictionRun.id.asc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    if existing_prediction is not None:
        # Reuse the existing authority chain. The latest existing
        # train task9 is the one bound to the existing prediction
        # (its task9_run_id FK is what stage 6 checks), so we anchor
        # on it instead of `created_at desc` to stay deterministic.
        # Do NOT mutate HarvestStateRun.created_at here: tests such as
        # `test_historical_resolution_task9_same_priority_conflict_blocks`
        # deliberately rewrite created_at to surface ambiguity, and a
        # fixture-driven rewrite here would silently re-order the
        # candidates and break that contract.
        async with AsyncSessionMaker() as session:
            train_task9 = await session.get(HarvestStateRun, existing_prediction.task9_run_id)
            assert train_task9 is not None, (
                "idempotent task10 fixture detected a prediction_run "
                "whose task9_run_id row is missing"
            )
            training_run = await session.get(
                ResidualModelTrainingRun, existing_prediction.training_run_id
            )
            assert training_run is not None
            artifact_row = (
                await session.execute(
                    select(ResidualModelArtifact)
                    .where(
                        ResidualModelArtifact.training_run_id == existing_prediction.training_run_id
                    )
                    .order_by(ResidualModelArtifact.id.asc())
                    .limit(1)
                )
            ).scalar_one()
            other_task9_rows = (
                (
                    await session.execute(
                        select(HarvestStateRun).where(HarvestStateRun.id != train_task9.id)
                    )
                )
                .scalars()
                .all()
            )
            validation_task9 = other_task9_rows[0] if other_task9_rows else None
            feature_build_row = (
                await session.execute(
                    select(AnalyticsBuildRun).order_by(AnalyticsBuildRun.id.asc()).limit(1)
                )
            ).scalar_one_or_none()
            assert feature_build_row is not None
        if feature_build_finished_at is not None:
            async with AsyncSessionMaker() as session:
                feature_build = await session.get(AnalyticsBuildRun, feature_build_row.id)
                if feature_build is not None:
                    feature_build.finished_at = feature_build_finished_at
                    await session.commit()
        return {
            "task9_run_id": train_task9.id,
            "training_run_id": training_run.id,
            "artifact_id": artifact_row.id,
            "prediction_run_id": existing_prediction.id,
            "feature_build_run_id": feature_build_row.id,
            "validation_task9_run_id": (
                validation_task9.id if validation_task9 is not None else train_task9.id
            ),
        }

    fixture = await _seed_prediction_fixture(
        task8_authority=task8_authority, analytics_season_id=analytics_season_id
    )
    if feature_build_finished_at is not None:
        async with AsyncSessionMaker() as session:
            feature_build = await session.get(
                AnalyticsBuildRun,
                fixture["train_feature_build_run_id"],
            )
            assert feature_build is not None
            feature_build.finished_at = feature_build_finished_at
            await session.commit()

    samples = _diverse_training_samples(
        task9_run_id=fixture["train_task9_run_id"],
        label_build_run_id=fixture["train_label_build_run_id"],
        feature_build_run_id=fixture["train_feature_build_run_id"],
        validation_task9_run_id=fixture["validation_task9_run_id"],
        validation_label_build_run_id=fixture["validation_label_build_run_id"],
        validation_feature_build_run_id=fixture["validation_feature_build_run_id"],
        as_of_date=date(fixture_season_id_for_samples, 2, 28),
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
                supplemental_feature_values=_supplemental_features(
                    as_of_date=date(fixture_season_id_for_samples, 2, 28)
                ),
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
        # Explicit commit before exiting the async with. Without this, the
        # async with's auto-close may roll back the training and prediction
        # rows, leaving the next test to see leftover connection state.
        await session.commit()
        # Explicit close so the connection returns to the pool with a
        # fully-reset transaction state. Without this, asyncpg may hand
        # the same connection to the next test's TRUNCATE session in
        # idle-in-transaction state, blocking the next test's setup
        # truncate for the full 2s lock_timeout window and cascading
        # LockNotAvailableError failures through the rest of the run.
        await session.close()
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
    # forecast_cutoff_at must be strictly AFTER the test runtime so the
    # Task 10 artifact audit's parent_authority_timestamp (set to the
    # actual training finished_at = datetime.now(UTC)) is not blocked
    # by PARENT_AUTHORITY_REQUIRED. The forecast_cutoff_at year has no
    # semantic relationship to the analytical season — it only acts as
    # the wall-clock audit threshold.
    assert forecast_cutoff_at > datetime(2026, 7, 1, tzinfo=UTC), (
        f"forecast_cutoff_at must be in the future relative to test "
        f"runtime (2026-07-04) to avoid parent_authority_timestamp > "
        f"cutoff; got {forecast_cutoff_at.isoformat()}"
    )
    # The Task 8 / Task 3 / Task 9 fixture helpers carry hardcoded
    # 2026-dated forecast_start_date / state_date / as_of_date (e.g.
    # make_request() in tests/harvest_state/conftest.py hardcodes
    # 2026-03-01..03 forecast_dates and 2026-02-28 as_of_date). The
    # analytics season MUST therefore match the date the fixture
    # helpers use — otherwise the manifest builder drops every
    # structural row as `date_outside_build_season` and training
    # returns BLOCKED with `no_included_training_rows`. Pin
    # fixture_season_id to the year the helper fixtures are anchored
    # on. The future-season fixture uses fixture_season_id=2099 to
    # satisfy the Pydantic schema's
    # `forecast_cutoff_at.local_date() == as_of_local_date` cross-
    # check on a MARCH_15 node_key with a forecast_cutoff_at that must
    # remain in the future (>= 2026-07-01) for the parent authority
    # audit. All fixture helper date fields are expressed in terms of
    # fixture_season_id so the analytical season and the fixture
    # helper dates stay co-anchored (no post-seed SQL shift required).
    fixture_season_id = 2099
    task8 = await _seed_real_task8_authorities(season_id=fixture_season_id)
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
    task10 = await _seed_real_task10_authorities(
        task8_authority=task8_authority,
        analytics_season_id=fixture_season_id,
        feature_build_finished_at=datetime(
            fixture_season_id,
            2,
            28,
            TASK11_FEBRUARY_END_CUTOFF_HOUR_UTC,
            tzinfo=UTC,
        ),
    )
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
            prediction_date = item["prediction_date"]
            if isinstance(prediction_date, str):
                prediction_date = date.fromisoformat(prediction_date)
            source_ref_hash = item["source_ref_hash"]
            verification = item["verification_snapshot"]
            expected_daily = task8["daily_predictions_by_date"][prediction_date]
            assert len(source_ref_hash) == 64
            entry_count_by_date[prediction_date] = entry_count_by_date.get(prediction_date, 0) + 1
            task9_daily_ids_by_date.setdefault(prediction_date, set()).add(
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
            assert Decimal(str(verification["p50_kg"])) == expected_daily["p50_kg"]
            assert Decimal(str(verification["p80_kg"])) == expected_daily["p80_kg"]
            assert Decimal(str(verification["p90_kg"])) == expected_daily["p90_kg"]
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
        authority_timestamp=datetime(fixture_season_id, 2, 28, 13, 0, tzinfo=UTC),
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

    # Pin as_of_local_date and the forecast window to the analytical
    # season (fixture_season_id=2026) rather than forecast_cutoff_at's
    # wall-clock date. The schema's _validate_dates model_validator
    # requires node_key (MARCH_15) to match
    # `date(season_id, 3, 15)` exactly, and Task 8 / Task 9 fixture
    # dates (make_request()) are all anchored in 2026. forecast_cutoff_at
    # still drives parent_authority_timestamp audit and is intentionally
    # future-dated (>= 2026-07-01) to remain ahead of the training
    # finished_at wall clock.
    as_of_local_date = date(fixture_season_id, 3, 15)
    node = _make_pinned_node(
        season_id=fixture_season_id,
        node_key="march_15",
        resolved_identities=identities,
    ).model_copy(
        update={
            "as_of_local_date": as_of_local_date,
            "forecast_cutoff_at": forecast_cutoff_at,
            "forecast_start_local_date": as_of_local_date + timedelta(days=1),
            "forecast_end_local_date": as_of_local_date + timedelta(days=7),
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
                authoritative_timestamp=datetime(fixture_season_id, 2, 28, 12, 0, tzinfo=UTC),
            ),
            forecast_cutoff_at=node.forecast_cutoff_at,
            resolved_identity=identities[1],
        ),
        AvailabilityAuditPersistenceCommand(
            source_role="task8_model_artifact",
            snapshot=Task8ModelArtifactAvailabilitySnapshot(
                source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
                created_at=datetime(fixture_season_id, 2, 28, 12, 5, tzinfo=UTC),
                parent_authority=_parent_authority(
                    source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
                    authority_status="completed",
                    authority_timestamp=datetime(fixture_season_id, 2, 28, 12, 0, tzinfo=UTC),
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
                authoritative_timestamp=datetime(fixture_season_id, 2, 28, 13, 0, tzinfo=UTC),
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


async def _build_real_historical_resolution_command(
    *,
    forecast_cutoff_at: datetime,
    source_roles: tuple[str, ...] | None = None,
) -> RollingBacktestPersistenceCommand:
    pinned_cmd = await _build_real_orchestration_command(forecast_cutoff_at=forecast_cutoff_at)
    pinned_node = pinned_cmd.config.nodes[0]
    all_identities = pinned_node.resolved_upstream_semantic_identities
    if source_roles is not None:
        requested_identities = tuple(
            identity for identity in all_identities if identity.source_role in source_roles
        )
    else:
        # Residual training persists one artifact row per quantile label.
        # The generic task10_model_artifact role is therefore intentionally
        # ambiguous under historical resolution unless a more specific role
        # contract exists. Keep the success-path fixture focused on the
        # deterministic Task 10 authorities (training + prediction) and let
        # explicit task10_model_artifact requests continue to surface the
        # ambiguity blocker instead of silently selecting by row ordering.
        requested_identities = tuple(
            identity
            for identity in all_identities
            if identity.source_role != "task10_model_artifact"
        )

    historical_identities = tuple(
        identity.model_copy(update={"persistent_reference": None})
        for identity in requested_identities
    )
    historical_node_updates: dict[str, Any] = {
        "upstream_selection_mode": UpstreamSelectionMode.HISTORICAL_RESOLUTION,
        "resolved_upstream_semantic_identities": historical_identities,
    }
    if any(
        identity.source_role.startswith("task8_daily_prediction:")
        for identity in historical_identities
    ):
        season_id = pinned_node.season_id
        # The Task 8 daily prediction fixture (see
        # tests/harvest_state/conftest.py::make_request) anchors the
        # observed daily predictions on
        # {season_id}-03-01 .. {season_id}-03-03 with the forecast
        # anchored at {season_id}-02-28 03:30 UTC. Under historical
        # resolution the daily prediction authority enforces
        # `prediction_date <= as_of_local_date` (see
        # AvailabilityBlockerCode.OBSERVATION_DATE_AFTER_CUTOFF in
        # availability.py), which is incompatible with the FEBRUARY_END
        # node whose as_of_local_date = {season_id}-02-28 — the daily
        # predictions would all be rejected. Drop the daily identities
        # from the success-path identity set so the historical resolver
        # still sees the canonical Task 8 forecast_run authority (whose
        # audit chain is `authoritative_timestamp <= forecast_cutoff_at`
        # and does not involve as_of_local_date). The ambiguity coverage
        # for `task10_model_artifact` is preserved separately above.
        historical_identities = tuple(
            identity
            for identity in historical_identities
            if not identity.source_role.startswith("task8_daily_prediction:")
        )
        historical_node_updates["resolved_upstream_semantic_identities"] = historical_identities
        february_end_cutoff_at = datetime.combine(
            date(season_id, 2, 28),
            pinned_cmd.config.cutoff_local_time,
            tzinfo=ZoneInfo(pinned_cmd.config.cutoff_timezone),
        ).astimezone(UTC)
        historical_node_updates.update(
            {
                "node_key": DefaultNodeKey.FEBRUARY_END,
                "as_of_local_date": date(season_id, 2, 28),
                "forecast_cutoff_at": february_end_cutoff_at,
                "forecast_start_local_date": date(season_id, 3, 1),
                "forecast_end_local_date": date(season_id, 3, 7),
            }
        )
    historical_node = pinned_node.model_copy(update=historical_node_updates)
    config = _make_config(
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        nodes=(historical_node,),
    )
    validated_node = config.nodes[0]
    node_cmd = RollingNodePersistenceCommand(
        node=validated_node,
        resolved_inputs=tuple(
            ResolvedInputPersistenceCommand(
                identity=identity,
                persistent_reference=None,
            )
            for identity in validated_node.resolved_upstream_semantic_identities
        ),
        availability_audits=(),
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
    fixture_season_id = 2099
    _require_postgres()
    cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
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
            f"task8_daily_prediction:{fixture_season_id}-03-01",
            f"task8_daily_prediction:{fixture_season_id}-03-02",
            f"task8_daily_prediction:{fixture_season_id}-03-03",
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
async def test_historical_resolution_real_chain_success_and_snapshot() -> None:
    """Historical resolution must select real persisted Task 8/9/10 authorities and complete."""
    _require_postgres()
    cmd = await _build_real_historical_resolution_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
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
        assert snapshot.canonical_payload["upstream_selection_mode"] == "historical_resolution"
        assert snapshot.canonical_payload["task9_authority"]["run_reference"]["reference_type"] == (
            "database_run_id"
        )
        assert (
            snapshot.canonical_payload["task10_authority"]["prediction_reference"]["reference_type"]
            == "database_run_id"
        )
        loaded_run = (
            await session.execute(select(RollingBacktestRun).where(RollingBacktestRun.id == run.id))
        ).scalar_one()
        await load_logical_run_with_integrity(session, loaded_run)


@pytest.mark.asyncio
async def test_historical_resolution_task9_latest_visible_candidate_selected() -> None:
    """Historical resolution must deterministically select the latest visible Task 9 candidate."""
    _require_postgres()
    await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
    )
    async with AsyncSessionMaker() as session:
        training_row = await session.get(HarvestStateRun, 1)
        if training_row is None:
            training_row = (
                await session.execute(
                    select(HarvestStateRun).order_by(HarvestStateRun.id.asc()).limit(1)
                )
            ).scalar_one()
        task9_rows = (
            (
                await session.execute(
                    select(HarvestStateRun).order_by(
                        HarvestStateRun.created_at.asc(), HarvestStateRun.id.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(task9_rows) >= 2
        expected = max(task9_rows, key=lambda row: (row.created_at, row.output_schema_version))
        expected_id = expected.id

    cmd = await _build_real_historical_resolution_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
        source_roles=("task9_structural_forecast",),
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
    assert outcome.task9_authority is not None
    assert outcome.task9_authority.run_reference is not None
    assert outcome.task9_authority.run_reference.reference_value == expected_id


@pytest.mark.asyncio
async def test_historical_resolution_task9_same_priority_conflict_blocks() -> None:
    """Same-priority conflicting Task 9 candidates must block as ambiguous."""
    _require_postgres()
    _ = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
    )
    async with AsyncSessionMaker() as session:
        task9_rows = (
            (
                await session.execute(
                    select(HarvestStateRun).order_by(
                        HarvestStateRun.created_at.asc(), HarvestStateRun.id.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(task9_rows) >= 2
        first, second = task9_rows[0], task9_rows[1]
        second.created_at = first.created_at
        await session.commit()

    cmd = await _build_real_historical_resolution_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
        source_roles=("task9_structural_forecast",),
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
    assert outcome.blocker_code == "ambiguous_historical_candidate"


@pytest.mark.asyncio
async def test_historical_resolution_task10_invisible_by_cutoff_blocks() -> None:
    """When only Task 10 prediction candidates are after cutoff, block as not visible."""
    _require_postgres()
    await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
    )
    async with AsyncSessionMaker() as session:
        prediction_row = (
            await session.execute(
                select(ResidualModelPredictionRun)
                .order_by(ResidualModelPredictionRun.completed_at.desc())
                .limit(1)
            )
        ).scalar_one()
        assert prediction_row.completed_at is not None
        # Rewrite the prediction wall clock into the {season_id}=2099
        # audit window so the subsequent cutoff below satisfies the
        # RollingNodeDefinition pydantic invariant
        # `forecast_cutoff_at.local_date == as_of_local_date`
        # (as_of_local_date is fixed at {season_id}-03-15 by the
        # MARCH_15 node_key the helper fabricates). Move completed_at
        # 1 hour past the audit cutoff so historical resolution
        # filters it out via SQL `completed_at <= forecast_cutoff_at`.
        prediction_row.completed_at = datetime(2099, 3, 15, 4, 1, tzinfo=UTC)
        await session.commit()
        # Cutoff sits 1 minute before the rewritten completed_at, on
        # the same local date as as_of_local_date so the config
        # validation passes. Because prediction.completed_at >
        # forecast_cutoff_at, the historical resolver must surface
        # `historical_source_not_visible` for the task10_prediction_run
        # authority, not a reused row.
        cutoff = prediction_row.completed_at - timedelta(minutes=1)

    cmd = await _build_real_historical_resolution_command(
        forecast_cutoff_at=cutoff,
        source_roles=("task10_prediction_run",),
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
    assert outcome.blocker_code == "historical_source_not_visible"


@pytest.mark.asyncio
async def test_cross_season_task8_authority_blocks() -> None:
    """Pinned Task 8/9 authorities from the fixture season must block a different season node."""
    fixture_season_id = 2099
    _require_postgres()
    base_cmd = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
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

    assert outcome.status == "blocked", (
        outcome.blocker_code,
        outcome.stage,
        outcome.diagnostics,
    )
    assert outcome.blocker_code == "PINNED_SOURCE_SCOPE_MISMATCH"
    assert outcome.stage == OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value
    assert "2027" in str(outcome.diagnostics)
    assert str(fixture_season_id) in str(outcome.diagnostics)


# ═══════════════════════════════════════════════════════════════════════════════
# l) real Task 10 / Task 9 binding mismatch
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_task10_task9_binding_mismatch_blocks() -> None:
    """Pinned Task 9 must match the real Task 10 prediction's frozen Task 9 binding."""
    _require_postgres()
    forecast_cutoff_at = datetime(2099, 3, 15, 4, 0, tzinfo=UTC)
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
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
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
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC),
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


# CI's PostgreSQL domain shard uses an explicit file list. Re-export the
# TASK-012 E2 evidence here so that shard executes the dedicated PG tests
# without changing workflow ownership.
from backend.tests.integration.test_task012_slice_e2_postgres import (  # noqa: E402, F401, I001
    test_postgres_slice_e2_changed_dataset_blocks_before_training,
    test_postgres_slice_e2_concurrent_exact_requests_share_persisted_result,
    test_postgres_slice_e2_non_replay_task9_authority_blocks,
    test_postgres_slice_e2_same_key_conflict_is_durable,
    test_postgres_slice_e2_task9_hash_mismatch_blocks,
    test_postgres_slice_e2_real_success_and_fresh_reload,
)


# ---------------------------------------------------------------------------
# TASK-012 Slice E3 HTTP API — PostgreSQL contracts (22 nodes)
#
# All 22 test functions below were migrated from
# ``test_task012_slice_e3_postgres.py`` (deleted) into the domain-2
# owned file so that pytest collection, the PR ``postgres-domain-2``
# shard, and the ``main`` ``full-suite-canary`` shard each execute
# every E3 contract exactly once. The HTTP transport is exercised
# through ``ASGITransport(create_app())`` against the real PostgreSQL
# database and the real Slice E2 application service. No fake response,
# no dict reconstruction.
# ---------------------------------------------------------------------------

from collections.abc import AsyncIterator  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from backend.app.main import create_app  # noqa: E402
from backend.app.rolling_backtest.replay_trained_service import (  # noqa: E402
    ReplayTrainedExecutionRequest,
)
from backend.tests.integration._e3_fixtures import (  # noqa: E402
    make_replay_trained_request,
    post_via_service,
    require_postgres,
)

# Mark every E3 node as PG integration so ``RUN_POSTGRES_INTEGRATION=1``
# gates collection in environments without a live PostgreSQL instance.
pytestmark = pytest.mark.integration


@pytest.fixture
async def e3_client() -> AsyncIterator[httpx.AsyncClient]:
    require_postgres()
    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


def _first_execution_body(idempotency_key: str) -> dict[str, object]:
    """Build a complete valid POST body.

    Used by tests that mutate a single field on a copy of the body so
    that the failure message exposes the real schema violation, not a
    cascade of "missing required field" errors.
    """
    raise RuntimeError("async helper — use await _first_execution_body_async")


async def _first_execution_body_async(*, idempotency_key: str) -> dict[str, object]:
    request = await make_replay_trained_request(idempotency_key=idempotency_key)
    body = request.to_payload()
    body["idempotency_key"] = idempotency_key
    return body  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# POST contracts (6 nodes)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_postgres_post_first_execution_returns_201_and_persists(
    e3_client: httpx.AsyncClient,
) -> None:
    body = await _first_execution_body_async(idempotency_key="task12-e3-post-201")
    response = await e3_client.post(
        "/api/v1/rolling-backtest/replay-trained-predictions", json=body
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["disposition"] == "created"
    assert payload["prediction_run_id"] > 0
    assert payload["model_policy"] == "replay_trained_model"
    assert payload["audit_identity"]
    assert payload["task9_run_id"] == body["task9_run_id"]
    assert payload["idempotency_key"] == "task12-e3-post-201"

    async with AsyncSessionMaker() as session:
        row = await session.get(ResidualModelPredictionRun, payload["prediction_run_id"])
        assert row is not None
        context = row.input_snapshot["task12_replay"]
        assert context["idempotency_key"] == "task12-e3-post-201"
        assert row.typed_attempt["task12_replay"]["audit_identity"] == payload["audit_identity"]


@pytest.mark.integration
async def test_postgres_post_exact_replay_returns_200_with_same_envelope(
    e3_client: httpx.AsyncClient,
) -> None:
    body = await _first_execution_body_async(idempotency_key="task12-e3-post-200")

    first = await e3_client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert first.status_code == 201, first.text
    first_payload = first.json()
    assert first_payload["disposition"] == "created"

    second = await e3_client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["disposition"] == "idempotent_replay"
    for key, value in first_payload.items():
        if key == "disposition":
            continue
        assert second_payload.get(key) == value, (key, value, second_payload.get(key))

    async with AsyncSessionMaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ResidualModelPredictionRun)
            .where(
                ResidualModelPredictionRun.input_snapshot["task12_replay"][
                    "idempotency_key"
                ].as_string()
                == "task12-e3-post-200"
            )
        )
        assert count == 1


@pytest.mark.integration
async def test_postgres_post_idempotency_conflict_returns_409(
    e3_client: httpx.AsyncClient,
) -> None:
    body = await _first_execution_body_async(idempotency_key="task12-e3-post-409")

    first = await e3_client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert first.status_code == 201, first.text

    body["caller_identity"] = "integration:different-caller"
    second = await e3_client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
    assert second.status_code == 409, second.text
    body_payload = second.json()
    assert body_payload["error"]["code"] == "TASK012_REPLAY_TRAINED_CONFLICT"
    assert body_payload["error"]["identity"]["mismatched_fields"] == [
        "idempotency_key_payload_mismatch"
    ]


@pytest.mark.integration
async def test_postgres_post_invalid_request_returns_422(
    e3_client: httpx.AsyncClient,
) -> None:
    body = await _first_execution_body_async(idempotency_key="task12-e3-post-422")
    del body["task9_result_hash"]  # remove one required field to force 422
    response = await e3_client.post(
        "/api/v1/rolling-backtest/replay-trained-predictions", json=body
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "TASK012_REPLAY_TRAINED_INPUT_INVALID"


# POST authority 404 / 409 split (replaces the old single 409 test).
# Per Slice E3 §4: Task 9 run missing → 404 not-found; is_replay=False
# or result-hash mismatch → 409 conflict. The HTTP layer MUST
# distinguish "authority not present" (404) from "authority present
# but rejected" (409).


@pytest.mark.integration
async def test_postgres_post_task9_authority_missing_returns_404(
    e3_client: httpx.AsyncClient,
) -> None:
    request = await make_replay_trained_request(idempotency_key="task12-e3-authority-404")
    async with AsyncSessionMaker() as session:
        run = await session.get(HarvestStateRun, request.task9_run_id)
        assert run is not None
        # Mark the Task 9 run as the *referenced* authority but with a
        # deleted state by re-using the run id after wiping its
        # authority fields. The application loader is given no way to
        # reconstruct the original; it must report not-found.
        await session.delete(run)
        await session.commit()

    body = request.to_payload()
    body["idempotency_key"] = "task12-e3-authority-404"
    response = await e3_client.post(
        "/api/v1/rolling-backtest/replay-trained-predictions", json=body
    )
    assert response.status_code == 404, response.text
    payload = response.json()
    assert payload["error"]["code"] == "TASK012_REPLAY_TRAINED_NOT_FOUND"
    assert payload["error"]["identity"]["prediction_run_id"] is None


@pytest.mark.integration
async def test_postgres_post_task9_authority_not_replay_returns_409_blocker(
    e3_client: httpx.AsyncClient,
) -> None:
    request = await make_replay_trained_request(idempotency_key="task12-e3-authority-409a")
    async with AsyncSessionMaker() as session:
        run = await session.get(HarvestStateRun, request.task9_run_id)
        assert run is not None
        run.is_replay = False
        run.forecast_effective_cutoff_at = None
        run.replay_executed_at = None
        run.replay_code_version = None
        run.replay_run_correlation_id = None
        await session.commit()

    body = request.to_payload()
    body["idempotency_key"] = "task12-e3-authority-409a"
    response = await e3_client.post(
        "/api/v1/rolling-backtest/replay-trained-predictions", json=body
    )
    assert response.status_code == 409, response.text
    payload = response.json()
    assert payload["error"]["code"] == "TASK012_REPLAY_TRAINED_BLOCKED"
    assert (
        "task9_replay_run_missing_or_not_replay"
        in payload["error"]["identity"]["mismatched_fields"]
    )


@pytest.mark.integration
async def test_postgres_post_task9_authority_hash_mismatch_returns_409_blocker(
    e3_client: httpx.AsyncClient,
) -> None:
    request = await make_replay_trained_request(idempotency_key="task12-e3-authority-409b")
    body = request.to_payload()
    body["idempotency_key"] = "task12-e3-authority-409b"
    # Mutate exactly the result-hash field; this is the cross-run
    # identity mismatch the spec requires to be a 409 blocker, not a
    # 404 (the authority exists, the request is rejected).
    body["task9_result_hash"] = "f" * 64

    response = await e3_client.post(
        "/api/v1/rolling-backtest/replay-trained-predictions", json=body
    )
    assert response.status_code == 409, response.text
    payload = response.json()
    assert payload["error"]["code"] == "TASK012_REPLAY_TRAINED_BLOCKED"
    assert "task9_result_hash_mismatch" in payload["error"]["identity"]["mismatched_fields"]


# ---------------------------------------------------------------------------
# GET contracts (4 nodes)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_postgres_get_exact_prediction_returns_200_with_persisted_identity(
    e3_client: httpx.AsyncClient,
) -> None:
    request = await make_replay_trained_request(idempotency_key="task12-e3-get-200")
    prediction_run_id = await post_via_service(request)

    response = await e3_client.get(
        f"/api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}"
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["prediction_run_id"] == prediction_run_id
    assert payload["model_policy"] == "replay_trained_model"
    assert payload["task9_run_id"] == request.task9_run_id
    assert payload["audit_identity"]


@pytest.mark.integration
async def test_postgres_get_missing_prediction_returns_404(
    e3_client: httpx.AsyncClient,
) -> None:
    response = await e3_client.get("/api/v1/rolling-backtest/replay-trained-predictions/999999")
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_NOT_FOUND"
    assert body["error"]["identity"]["prediction_run_id"] == 999999


@pytest.mark.integration
async def test_postgres_get_does_not_re_execute_or_mutate_state(
    e3_client: httpx.AsyncClient,
) -> None:
    request = await make_replay_trained_request(idempotency_key="task12-e3-get-noop")
    prediction_run_id = await post_via_service(request)

    async with AsyncSessionMaker() as session:
        before_count = await session.scalar(
            select(func.count()).select_from(ResidualModelPredictionRun)
        )

    for _ in range(3):
        response = await e3_client.get(
            f"/api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}"
        )
        assert response.status_code == 200

    async with AsyncSessionMaker() as session:
        after_count = await session.scalar(
            select(func.count()).select_from(ResidualModelPredictionRun)
        )
    assert before_count == after_count


@pytest.mark.integration
async def test_postgres_get_rejects_no_implicit_latest_or_current(
    e3_client: httpx.AsyncClient,
) -> None:
    response = await e3_client.get("/api/v1/rolling-backtest/replay-trained-predictions/latest")
    assert response.status_code in (404, 422)


# ---------------------------------------------------------------------------
# Concurrency contract (1 node)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_postgres_concurrent_post_returns_one_201_and_one_200_with_same_identity(
    e3_client: httpx.AsyncClient,
) -> None:
    body = await _first_execution_body_async(idempotency_key="task12-e3-concurrent")

    async def _post() -> httpx.Response:
        local_client = httpx.AsyncClient(
            transport=ASGITransport(app=e3_client._transport.app),  # type: ignore[attr-defined]
            base_url="http://test",
        )
        try:
            return await local_client.post(
                "/api/v1/rolling-backtest/replay-trained-predictions", json=body
            )
        finally:
            await local_client.aclose()

    import asyncio

    responses = await asyncio.gather(_post(), _post())
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 201], (
        f"expected exactly one 201 and one 200; got {statuses}: {[r.text for r in responses]}"
    )

    payload_by_status: dict[int, dict[str, object]] = {r.status_code: r.json() for r in responses}
    created = payload_by_status[201]
    replay = payload_by_status[200]
    assert created["disposition"] == "created"
    assert replay["disposition"] == "idempotent_replay"
    assert created["prediction_run_id"] == replay["prediction_run_id"], (
        created["prediction_run_id"],
        replay["prediction_run_id"],
    )
    for key, value in created.items():
        if key == "disposition":
            continue
        assert replay.get(key) == value, (key, value, replay.get(key))

    async with AsyncSessionMaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ResidualModelPredictionRun)
            .where(
                ResidualModelPredictionRun.input_snapshot["task12_replay"][
                    "idempotency_key"
                ].as_string()
                == "task12-e3-concurrent"
            )
        )
    assert count == 1


# ---------------------------------------------------------------------------
# GET corruption PostgreSQL tests (10 nodes)
#
# The application-level loader
# ``load_replay_trained_prediction(session, prediction_run_id)`` is
# fail-closed: every required field MUST be present in the persisted
# row, and any required field that is missing, malformed, or
# mismatched-against-redeterminism produces a stable 500 envelope.
# ---------------------------------------------------------------------------


async def _seed_known_prediction(
    *, idempotency_key: str
) -> tuple[int, ReplayTrainedExecutionRequest]:
    request = await make_replay_trained_request(idempotency_key=idempotency_key)
    prediction_run_id = await post_via_service(request)
    return prediction_run_id, request


def _corrupt_input_snapshot(
    prediction_run_id: int, *, drop: str | None = None, replace: dict | None = None
) -> None:
    async def _do() -> None:
        async with AsyncSessionMaker() as session:
            row = await session.get(ResidualModelPredictionRun, prediction_run_id)
            assert row is not None
            snapshot = dict(row.input_snapshot)
            task12 = dict(snapshot["task12_replay"])
            if drop is not None:
                task12.pop(drop, None)
            if replace is not None:
                task12.update(replace)
            snapshot["task12_replay"] = task12
            row.input_snapshot = snapshot
            await session.commit()

    import asyncio

    asyncio.run(_do())


def _corrupt_typed_attempt(
    prediction_run_id: int, *, drop: str | None = None, replace: dict | None = None
) -> None:
    async def _do() -> None:
        async with AsyncSessionMaker() as session:
            row = await session.get(ResidualModelPredictionRun, prediction_run_id)
            assert row is not None
            typed = dict(row.typed_attempt)
            task12 = dict(typed.get("task12_replay", {}))
            if drop is not None:
                task12.pop(drop, None)
            if replace is not None:
                task12.update(replace)
            typed["task12_replay"] = task12
            row.typed_attempt = typed
            await session.commit()

    import asyncio

    asyncio.run(_do())


async def _expect_500(e3_client: httpx.AsyncClient, prediction_run_id: int) -> None:
    response = await e3_client.get(
        f"/api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}"
    )
    assert response.status_code == 500, response.text
    body = response.json()
    assert body["error"]["code"] == "TASK012_REPLAY_TRAINED_INTEGRITY"


@pytest.mark.integration
async def test_postgres_get_corruption_missing_request_payload_hash(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-rph")
    _corrupt_input_snapshot(pid, drop="request_payload_hash")
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_missing_model_policy(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-mp")
    _corrupt_input_snapshot(pid, drop="model_policy")
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_missing_task9_run_id(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-t9id")
    _corrupt_input_snapshot(pid, drop="task9_run_id")
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_missing_training_manifest_hash(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-tmh")
    _corrupt_input_snapshot(pid, drop="training_manifest_hash")
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_malformed_model_artifact_hash(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-mah")
    _corrupt_input_snapshot(pid, replace={"model_artifact_hash": "not-a-hash"})
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_wrong_model_policy(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-wmp")
    _corrupt_input_snapshot(pid, replace={"model_policy": "historically_available_model"})
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_prediction_hash_mismatch(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-phm")

    # The prediction hash lives on the row itself (canonical_payload_hash).
    async def _do() -> None:
        async with AsyncSessionMaker() as session:
            row = await session.get(ResidualModelPredictionRun, pid)
            assert row is not None
            row.canonical_payload_hash = "0" * 64  # wrong but well-formed
            await session.commit()

    import asyncio

    asyncio.run(_do())
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_missing_typed_audit_context(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-tac")
    _corrupt_typed_attempt(pid, drop="task12_replay")
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_missing_audit_identity(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-ai")
    _corrupt_typed_attempt(pid, drop="audit_identity")
    await _expect_500(e3_client, pid)


@pytest.mark.integration
async def test_postgres_get_corruption_audit_identity_mismatch(
    e3_client: httpx.AsyncClient,
) -> None:
    pid, _ = await _seed_known_prediction(idempotency_key="task12-e3-corrupt-aim")
    _corrupt_typed_attempt(pid, replace={"audit_identity": "deadbeef" * 8})
    await _expect_500(e3_client, pid)
