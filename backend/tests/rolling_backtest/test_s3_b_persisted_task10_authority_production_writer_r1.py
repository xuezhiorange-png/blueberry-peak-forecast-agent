"""Production writer tests for persisted Task 10 authority binding (R1)."""

from __future__ import annotations

import ast
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import backend.app.rolling_backtest.node_orchestration as node_orch
from backend.app.models.core_forecast import CoreForecastRunModel
from backend.app.models.core_forecast_task10_authority_binding import (
    CoreForecastTask10AuthorityBindingModel,
)
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.app.rolling_backtest.orchestration import Task9AuthorityOutcome, Task10AuthorityOutcome
from backend.app.rolling_backtest.persisted_task10_authority_binding import (
    PersistedTask10AuthorityBindingConflictError,
    PersistedTask10AuthorityBindingWriteOutcome,
    write_persisted_task10_authority_binding_from_pinned_lineage,
)
from backend.app.rolling_backtest.schemas import PersistentUpstreamReference, RollingNodeDefinition
from backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader import (
    load_persisted_forecast_binding_authority,
)
from backend.tests.forecast_quality.authority_loader_fixture import (
    CORE_RUN_ID,
    CUTOFF_AT,
    FARM_ID,
    HASH_4,
    HASH_C,
    HASH_D,
    PREDICTION_RUN_ID,
    SUBFARM_ID,
    TASK8_RUN_ID,
    TASK9_RUN_ID,
    VARIETY_ID,
    _fixture_hash,
    seed_canonical_authority_fixture,
)
from backend.tests.forecast_quality.persisted_forecast_authority_fixture_mocks import (
    copy_fixture_rows_to_async_session,
    create_authority_fixture_async_engine,
    ensure_authority_fixture_tables,
    install_authority_fixture_mock_loaders,
    session_rows_from_sync_fixture,
)
from backend.tests.rolling_backtest.test_node_orchestration import _make_config

pytest_plugins = ["backend.tests.forecast_quality.authority_loader_fixture"]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_ROOT = _REPO_ROOT / "backend" / "app"
_BINDING_TABLE = CoreForecastTask10AuthorityBindingModel.__table__
_NODE_MOD = "backend.app.rolling_backtest.node_orchestration"
_BINDING_MOD = "backend.app.rolling_backtest.persisted_task10_authority_binding"


def _ensure_binding_table(sync_connection) -> None:
    _BINDING_TABLE.create(sync_connection, checkfirst=True)


def _make_writer_node_def(*, forecast_cutoff_at=CUTOFF_AT):
    node = RollingNodeDefinition.model_validate(
        {
            "season_id": 2026,
            "node_key": "march_15",
            "as_of_local_date": "2026-03-15",
            "forecast_cutoff_at": forecast_cutoff_at.isoformat().replace("+00:00", "Z"),
            "forecast_start_local_date": "2026-03-16",
            "forecast_end_local_date": "2026-03-31",
            "scope": {
                "destination_factory_ids": {"mode": "include_ids", "ids": [202, 101]},
                "farm_ids": {"mode": "all", "ids": []},
                "subfarm_ids": {"mode": "all", "ids": []},
                "variety_ids": {"mode": "all", "ids": []},
            },
            "upstream_selection_mode": "pinned",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "timezone": "Asia/Shanghai",
            "task10_model_policy": {
                "policy": "historically_available_model",
                "training_run_semantic_identity": "a" * 64,
                "artifact_semantic_identities": ["b" * 64, "c" * 64],
                "authority_visibility_identity": "d" * 64,
            },
            "resolved_upstream_semantic_identities": [],
        }
    )
    return node


def _make_stage_ctx(
    *,
    task9_run_id: int = TASK9_RUN_ID,
    task9_result_hash: str = HASH_C,
    task10_prediction_run_id: int = PREDICTION_RUN_ID,
) -> node_orch._StageContext:
    return node_orch._StageContext(
        attempt_id=100,
        node_id=10,
        run_id=1,
        resolved_inputs={},
        availability_audits={},
        task9_authority=Task9AuthorityOutcome(
            run_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=task9_run_id,
            ),
            result_hash=task9_result_hash,
            mode="reuse",
        ),
        task10_authority=Task10AuthorityOutcome(
            prediction_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=task10_prediction_run_id,
            ),
            input_signature=HASH_4,
            prediction_hash=HASH_D,
            mode="reuse",
        ),
    )


def _prediction_result_mock(*, task9_run_id: int = TASK9_RUN_ID, task9_result_hash: str = HASH_C):
    return SimpleNamespace(
        execution_status="completed",
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        prediction_input_signature=HASH_4,
        prediction_hash=HASH_D,
        input_snapshot={},
    )


async def _run_production_writer_stage(
    session: AsyncSession,
    *,
    ctx: node_orch._StageContext | None = None,
    node=None,
    prediction_result=None,
) -> None:
    ctx = ctx or _make_stage_ctx()
    node = node or _make_writer_node_def()
    if prediction_result is None:
        prediction_result = _prediction_result_mock(
            task9_run_id=ctx.task9_authority.run_reference.reference_value,  # type: ignore[union-attr]
            task9_result_hash=ctx.task9_authority.result_hash,  # type: ignore[union-attr]
        )
    original_get = session.get

    async def _session_get(model, key):
        row = await original_get(model, key)
        if model is ResidualModelPredictionRun and row is not None and row.completed_at is not None:
            if row.completed_at.tzinfo is None:
                row.completed_at = row.completed_at.replace(tzinfo=UTC)
        return row

    session.get = _session_get  # type: ignore[method-assign]
    with patch(
        f"{_NODE_MOD}.load_residual_prediction_run_by_id",
        new=AsyncMock(return_value=prediction_result),
    ):
        await node_orch._stage_execute_task10_prediction(
            session,
            ctx,
            _make_config(),
            node,
        )


@pytest.mark.asyncio
async def test_actual_production_caller_writes_binding(authority_loader_session) -> None:
    """A: ACTUAL_PRODUCTION_CALLER_WRITES_BINDING."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        await _run_production_writer_stage(session)
        await session.commit()
        rows = list(
            await session.scalars(
                select(CoreForecastTask10AuthorityBindingModel).where(
                    CoreForecastTask10AuthorityBindingModel.core_forecast_run_id == CORE_RUN_ID
                )
            )
        )
    await engine.dispose()
    assert len(rows) == 1
    assert rows[0].task10_prediction_run_id == PREDICTION_RUN_ID


@pytest.mark.asyncio
async def test_task10_reference_preexists_writer(authority_loader_session) -> None:
    """B: TASK10_REFERENCE_PREEXISTS_WRITER."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ctx = _make_stage_ctx()
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        with patch(
            f"{_NODE_MOD}.write_persisted_task10_authority_binding_from_pinned_lineage",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    outcome=PersistedTask10AuthorityBindingWriteOutcome.BOUND,
                    core_forecast_run_id=CORE_RUN_ID,
                    task10_prediction_run_id=PREDICTION_RUN_ID,
                    binding_id=1,
                )
            ),
        ) as lineage_writer:
            await _run_production_writer_stage(session, ctx=ctx)
            lineage_writer.assert_awaited_once()
            kwargs = lineage_writer.await_args.kwargs
            assert kwargs["task10_prediction_run_id"] == PREDICTION_RUN_ID
            assert kwargs["task10_prediction_run_id"] == (
                ctx.task10_authority.prediction_reference.reference_value  # type: ignore[union-attr]
            )
    await engine.dispose()


def test_no_task10_discovery_query_in_production_writer_path() -> None:
    """C: NO_TASK10_DISCOVERY_QUERY."""
    node_source = (_APP_ROOT / "rolling_backtest" / "node_orchestration.py").read_text(
        encoding="utf-8"
    )
    binding_source = (
        _APP_ROOT / "rolling_backtest" / "persisted_task10_authority_binding.py"
    ).read_text(encoding="utf-8")
    for label, source, start_marker, end_marker in (
        (
            "node writer",
            node_source,
            "async def _write_persisted_task10_authority_binding_after_reuse",
            "# ── Snapshot builder",
        ),
        (
            "lineage writer",
            binding_source,
            "async def write_persisted_task10_authority_binding_from_pinned_lineage",
            "def lookup_task10_prediction_run_id_sync",
        ),
        (
            "core resolver",
            binding_source,
            "async def resolve_exact_core_forecast_run_ids",
            "async def write_persisted_task10_authority_binding_from_pinned_lineage",
        ),
    ):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        scoped = source[start:end]
        tree = ast.parse(scoped)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"max", "min"}
        lowered = scoped.lower()
        for pattern in ("order_by", "latest", "earliest", "limit 1"):
            assert pattern not in lowered, f"{label} must not contain {pattern}"
        assert "ResidualModelPredictionRun" not in scoped, label


@pytest.mark.asyncio
async def test_exact_task9_lineage_required(authority_loader_session) -> None:
    """D: EXACT_TASK9_LINEAGE_REQUIRED."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        await _run_production_writer_stage(
            session,
            ctx=_make_stage_ctx(task9_result_hash=_fixture_hash("wrong-task9-hash")),
        )
        await session.commit()
        rows = list(await session.scalars(select(CoreForecastTask10AuthorityBindingModel)))
    await engine.dispose()
    assert rows == []


@pytest.mark.asyncio
async def test_exact_task8_from_task9(authority_loader_session) -> None:
    """E: EXACT_TASK8_FROM_TASK9."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        task9_run = await session.get(HarvestStateRun, TASK9_RUN_ID)
        assert task9_run is not None
        task9_run.maturity_forecast_run_id = TASK8_RUN_ID + 999
        await session.flush()
        await _run_production_writer_stage(session)
        await session.commit()
        rows = list(await session.scalars(select(CoreForecastTask10AuthorityBindingModel)))
    await engine.dispose()
    assert rows == []


@pytest.mark.asyncio
async def test_exact_core_resolution(authority_loader_session) -> None:
    """F: EXACT_CORE_RESOLUTION."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        result = await write_persisted_task10_authority_binding_from_pinned_lineage(
            session,
            task10_prediction_run_id=PREDICTION_RUN_ID,
            task8_forecast_run_id=TASK8_RUN_ID,
            task9_harvest_state_run_id=TASK9_RUN_ID,
            task9_result_hash=HASH_C,
            forecast_effective_cutoff_at=CUTOFF_AT,
        )
    await engine.dispose()
    assert result.outcome == PersistedTask10AuthorityBindingWriteOutcome.BOUND
    assert result.core_forecast_run_id == CORE_RUN_ID


@pytest.mark.asyncio
async def test_zero_core_match_fails_closed(authority_loader_session) -> None:
    """G: ZERO_CORE_MATCH_FAILS_CLOSED."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    wrong_cutoff = CUTOFF_AT.replace(hour=5)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        await _run_production_writer_stage(
            session,
            node=_make_writer_node_def(forecast_cutoff_at=wrong_cutoff),
        )
        await session.commit()
        rows = list(await session.scalars(select(CoreForecastTask10AuthorityBindingModel)))
    await engine.dispose()
    assert rows == []


@pytest.mark.asyncio
async def test_multiple_core_match_fails_closed(authority_loader_session) -> None:
    """H: MULTIPLE_CORE_MATCH_FAILS_CLOSED."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        original = await session.get(CoreForecastRunModel, CORE_RUN_ID)
        assert original is not None
        duplicate = CoreForecastRunModel(
            id=CORE_RUN_ID + 1,
            status=original.status,
            run_schema_version=original.run_schema_version,
            request_schema_version=original.request_schema_version,
            date_basis=original.date_basis,
            forecast_input_hash=_fixture_hash("duplicate-core-input"),
            request_hash=_fixture_hash("duplicate-core-request"),
            result_hash=_fixture_hash("duplicate-core-result"),
            retention_policy_snapshot_hash=original.retention_policy_snapshot_hash,
            curve_hash=original.curve_hash,
            metrics_hash=original.metrics_hash,
            code_authority_id=original.code_authority_id,
            code_authority_hash=original.code_authority_hash,
            code_authority_available_at=original.code_authority_available_at,
            forecast_effective_cutoff_at=original.forecast_effective_cutoff_at,
            request_snapshot=dict(original.request_snapshot),
            forecast_season_id=original.forecast_season_id,
            forecast_season_code=original.forecast_season_code,
            forecast_start_date=original.forecast_start_date,
            forecast_end_date=original.forecast_end_date,
            destination_factory_id=original.destination_factory_id,
            task8_forecast_run_id=original.task8_forecast_run_id,
            task8_artifact_hash=original.task8_artifact_hash,
            task9_harvest_state_run_id=original.task9_harvest_state_run_id,
            task9_result_hash=original.task9_result_hash,
            daily_row_count=original.daily_row_count,
            metric_row_count=original.metric_row_count,
            completed_at=original.completed_at,
        )
        session.add(duplicate)
        await session.flush()
        await _run_production_writer_stage(session)
        await session.commit()
        rows = list(await session.scalars(select(CoreForecastTask10AuthorityBindingModel)))
    await engine.dispose()
    assert rows == []


@pytest.mark.asyncio
async def test_correct_binding_idempotent(authority_loader_session) -> None:
    """I: CORRECT_BINDING_IDEMPOTENT."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        await _run_production_writer_stage(session)
        await _run_production_writer_stage(session)
        await session.commit()
        rows = list(
            await session.scalars(
                select(CoreForecastTask10AuthorityBindingModel).where(
                    CoreForecastTask10AuthorityBindingModel.core_forecast_run_id == CORE_RUN_ID
                )
            )
        )
    await engine.dispose()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_conflicting_task10_fails_closed(authority_loader_session) -> None:
    """J: CONFLICTING_TASK10_FAILS_CLOSED."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    duplicate_run = ResidualModelPredictionRun(
        id=9999,
        training_run_id=301,
        task9_run_id=TASK9_RUN_ID,
        task9_result_hash=HASH_C,
        prediction_target_kind="LEGACY_RESIDUAL_CORRECTION",
        execution_status="completed",
        mode="structural_only",
        config_hash=_fixture_hash("duplicate-prediction-run-config"),
        feature_schema_version="task10-features-v1",
        feature_schema_hash=_fixture_hash("duplicate-prediction-run-feature-schema"),
        artifact_hashes=[],
        prediction_input_signature=_fixture_hash("duplicate-prediction-run-input"),
        prediction_hash=_fixture_hash("duplicate-prediction-run-hash"),
        feature_audit={},
        warnings=[],
        blockers=[],
        fallback_reason="fixture-duplicate-structural-only",
        expected_prediction_row_count=1,
        input_snapshot={"training_signature": _fixture_hash("authority-fixture-0")},
        canonical_output={},
        canonical_payload_hash=_fixture_hash("duplicate-prediction-run-payload"),
        completed_at=CUTOFF_AT,
    )
    duplicate_hash = _fixture_hash("duplicate-prediction-run-hash")
    duplicate_input = _fixture_hash("duplicate-prediction-run-input")
    authority_loader_session.add(duplicate_run)
    authority_loader_session.commit()
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    conflict_ctx = node_orch._StageContext(
        attempt_id=100,
        node_id=10,
        run_id=1,
        resolved_inputs={},
        availability_audits={},
        task9_authority=Task9AuthorityOutcome(
            run_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=TASK9_RUN_ID,
            ),
            result_hash=HASH_C,
            mode="reuse",
        ),
        task10_authority=Task10AuthorityOutcome(
            prediction_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=9999,
            ),
            input_signature=duplicate_input,
            prediction_hash=duplicate_hash,
            mode="reuse",
        ),
    )
    conflict_prediction = _prediction_result_mock(
        task9_result_hash=HASH_C,
    )
    conflict_prediction.prediction_input_signature = duplicate_input
    conflict_prediction.prediction_hash = duplicate_hash
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        await session.merge(duplicate_run)
        await _run_production_writer_stage(session)
        with pytest.raises(PersistedTask10AuthorityBindingConflictError):
            await _run_production_writer_stage(
                session,
                ctx=conflict_ctx,
                prediction_result=conflict_prediction,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_core_canonical_identity_unchanged(authority_loader_session) -> None:
    """K: CORE_CANONICAL_IDENTITY_UNCHANGED."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        before = await session.get(CoreForecastRunModel, CORE_RUN_ID)
        assert before is not None
        original_request_hash = before.request_hash
        original_request_snapshot = dict(before.request_snapshot)
        original_result_hash = before.result_hash
        await _run_production_writer_stage(session)
        await session.commit()
        after = await session.get(CoreForecastRunModel, CORE_RUN_ID)
    await engine.dispose()
    assert after is not None
    assert after.request_hash == original_request_hash
    assert after.request_snapshot == original_request_snapshot
    assert after.result_hash == original_result_hash


@pytest.mark.asyncio
async def test_s3_b_consumer_regression(
    authority_loader_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L: S3_B_CONSUMER_REGRESSION."""
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    rows = session_rows_from_sync_fixture(authority_loader_session, fixture=fixture)
    install_authority_fixture_mock_loaders(
        monkeypatch,
        session_rows=rows,
        core_row=core_row,
        task9_member=fixture["member_p50_a"],
        prediction_row=fixture["pred_row_h7_a"],
    )
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        await _run_production_writer_stage(session)
        await session.commit()
        bundle = await load_persisted_forecast_binding_authority(
            session,
            forecast_cutoff_at=CUTOFF_AT,
            task8_forecast_run_id=TASK8_RUN_ID,
            target_date=core_row.date,
            forecast_quantile="P50",
            horizon_days=7,
            farm_id=FARM_ID,
            subfarm_id=SUBFARM_ID,
            variety_id=VARIETY_ID,
            task10_prediction_run_id=PREDICTION_RUN_ID,
        )
    await engine.dispose()
    assert bundle is not None


def test_core_ranking_selector_not_present() -> None:
    binding_source = (
        _APP_ROOT / "rolling_backtest" / "persisted_task10_authority_binding.py"
    ).read_text(encoding="utf-8")
    resolver_start = binding_source.index("async def resolve_exact_core_forecast_run_ids")
    resolver_end = binding_source.index(
        "async def write_persisted_task10_authority_binding_from_pinned_lineage", resolver_start
    )
    resolver_source = binding_source[resolver_start:resolver_end]
    assert "order_by" not in resolver_source.lower()
    assert "limit" not in resolver_source.lower()


def test_production_writer_path_is_node_orchestration() -> None:
    node_source = (_APP_ROOT / "rolling_backtest" / "node_orchestration.py").read_text(
        encoding="utf-8"
    )
    assert "_write_persisted_task10_authority_binding_after_reuse" in node_source
    assert "write_persisted_task10_authority_binding_from_pinned_lineage" in node_source
    stage_start = node_source.index("async def _stage_execute_task10_prediction")
    stage_end = node_source.index("async def _stage_finalize_snapshot", stage_start)
    stage_source = node_source[stage_start:stage_end]
    reuse_index = stage_source.index("_execute_task10_prediction_reuse")
    writer_index = stage_source.index("_write_persisted_task10_authority_binding_after_reuse")
    assert reuse_index < writer_index
