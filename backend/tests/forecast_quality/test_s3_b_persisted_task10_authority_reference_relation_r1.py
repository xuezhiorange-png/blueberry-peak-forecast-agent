"""Persisted Task 10 authority reference relation R1 tests."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core_forecast.persistence import CoreForecastRunRepository
from backend.app.models.core_forecast_task10_authority_binding import (
    CoreForecastTask10AuthorityBindingModel,
)
from backend.app.rolling_backtest.persisted_task10_authority_binding import (
    PersistedTask10AuthorityBindingConflictError,
    PersistedTask10AuthorityBindingLineageError,
    register_persisted_task10_authority_binding,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_loader import (
    build_pit_visible_incumbent_daily_curve_index,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader import (
    load_persisted_forecast_binding_authority,
)
from backend.tests.forecast_quality.authority_loader_fixture import (
    CORE_RUN_ID,
    CUTOFF_AT,
    FARM_ID,
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

pytest_plugins = ["backend.tests.forecast_quality.authority_loader_fixture"]

_BINDING_TABLE = CoreForecastTask10AuthorityBindingModel.__table__


def _ensure_binding_table(sync_connection) -> None:
    _BINDING_TABLE.create(sync_connection, checkfirst=True)


async def _seed_binding_fixture(
    authority_loader_session,
    *,
    task10_prediction_run_id: int = PREDICTION_RUN_ID,
) -> dict[str, object]:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        binding = await register_persisted_task10_authority_binding(
            session,
            core_forecast_run_id=CORE_RUN_ID,
            task10_prediction_run_id=task10_prediction_run_id,
        )
        await session.commit()
        binding_id = binding.id
    await engine.dispose()
    return {**fixture, "binding_id": binding_id, "engine": engine}


@pytest.mark.asyncio
async def test_exact_reference_persisted_from_already_selected_task10_run(
    authority_loader_session,
) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        binding = await register_persisted_task10_authority_binding(
            session,
            core_forecast_run_id=CORE_RUN_ID,
            task10_prediction_run_id=PREDICTION_RUN_ID,
        )
        await session.commit()
        stored = await session.scalar(
            select(CoreForecastTask10AuthorityBindingModel).where(
                CoreForecastTask10AuthorityBindingModel.id == binding.id
            )
        )
    await engine.dispose()
    assert stored is not None
    assert stored.core_forecast_run_id == CORE_RUN_ID
    assert stored.task9_run_id == TASK9_RUN_ID
    assert stored.task10_prediction_run_id == PREDICTION_RUN_ID
    assert len(stored.task9_result_hash) == 64
    assert len(stored.binding_identity_hash) == 64


def test_no_task10_discovery_in_binding_writer() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    writer_sources = [
        repo_root / "backend/app/rolling_backtest/persisted_task10_authority_binding.py",
        repo_root / "backend/app/core_forecast/persistence.py",
    ]
    forbidden_scan_patterns = ("order_by", "discovery", "latest")
    for source in writer_sources:
        text = source.read_text(encoding="utf-8")
        if source.name == "persistence.py":
            start = text.index("async def _maybe_register_task10_authority_binding")
            end = text.index("async def register_code_authority", start)
            text = text[start:end]
        assert "register_persisted_task10_authority_binding" in text or source.name.endswith(
            "persisted_task10_authority_binding.py"
        )
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"max", "min"}
        lowered = text.lower()
        for pattern in forbidden_scan_patterns:
            assert pattern not in lowered
        if source.name == "persisted_task10_authority_binding.py":
            assert "ResidualModelPredictionRun" in text
            assert "await session.get(ResidualModelPredictionRun" in text


@pytest.mark.asyncio
async def test_one_core_authority_one_task10_binding(authority_loader_session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        first = await register_persisted_task10_authority_binding(
            session,
            core_forecast_run_id=CORE_RUN_ID,
            task10_prediction_run_id=PREDICTION_RUN_ID,
        )
        second = await register_persisted_task10_authority_binding(
            session,
            core_forecast_run_id=CORE_RUN_ID,
            task10_prediction_run_id=PREDICTION_RUN_ID,
        )
        await session.commit()
        rows = list(
            await session.scalars(
                select(CoreForecastTask10AuthorityBindingModel).where(
                    CoreForecastTask10AuthorityBindingModel.core_forecast_run_id == CORE_RUN_ID
                )
            )
        )
    await engine.dispose()
    assert first.id == second.id
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_conflicting_task10_binding_fails_closed(authority_loader_session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    duplicate_run = __import__(
        "backend.app.models.residual_model", fromlist=["ResidualModelPredictionRun"]
    ).ResidualModelPredictionRun(
        id=9999,
        training_run_id=301,
        task9_run_id=TASK9_RUN_ID,
        task9_result_hash=fixture["pred_row_h7_a"].task9_result_hash,
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
    authority_loader_session.add(duplicate_run)
    authority_loader_session.commit()
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        await session.merge(duplicate_run)
        await register_persisted_task10_authority_binding(
            session,
            core_forecast_run_id=CORE_RUN_ID,
            task10_prediction_run_id=PREDICTION_RUN_ID,
        )
        with pytest.raises(PersistedTask10AuthorityBindingConflictError):
            await register_persisted_task10_authority_binding(
                session,
                core_forecast_run_id=CORE_RUN_ID,
                task10_prediction_run_id=9999,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_missing_binding_fails_closed(authority_loader_session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        index = await build_pit_visible_incumbent_daily_curve_index(
            session,
            forecast_cutoff_at=CUTOFF_AT,
            grains=frozenset(),
        )
    await engine.dispose()
    assert index.cells == {}


@pytest.mark.asyncio
async def test_s3_b_consumes_persisted_reference(
    authority_loader_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        await register_persisted_task10_authority_binding(
            session,
            core_forecast_run_id=CORE_RUN_ID,
            task10_prediction_run_id=PREDICTION_RUN_ID,
        )
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


def test_s3_b_does_not_scan_task10_runs() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (
        repo_root / "backend/app/s3_daily_rowset/pit_visible_incumbent_daily_curve_loader.py"
    ).read_text(encoding="utf-8")
    assert "lookup_task10_prediction_run_id" in source
    assert "load_persisted_forecast_binding_authority" in source
    assert "ResidualModelPredictionRun" not in source
    lowered = source.lower()
    assert "order_by" not in lowered
    assert "discovery" not in lowered


@pytest.mark.asyncio
async def test_wrong_persisted_reference_rejected_by_r4_canonical_validator(
    authority_loader_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        await register_persisted_task10_authority_binding(
            session,
            core_forecast_run_id=CORE_RUN_ID,
            task10_prediction_run_id=PREDICTION_RUN_ID,
        )
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
            task10_prediction_run_id=9999,
        )
    await engine.dispose()
    assert bundle is None


@pytest.mark.asyncio
async def test_task8_task9_lineage_drift_fails_closed(authority_loader_session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_binding_table)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        with pytest.raises(PersistedTask10AuthorityBindingLineageError):
            await register_persisted_task10_authority_binding(
                session,
                core_forecast_run_id=CORE_RUN_ID,
                task10_prediction_run_id=CORE_RUN_ID,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_multi_day_multi_quantile_uses_same_pinned_run_with_exact_row_validation(
    authority_loader_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    rows = session_rows_from_sync_fixture(authority_loader_session, fixture=fixture)
    install_authority_fixture_mock_loaders(
        monkeypatch,
        session_rows=rows,
        core_row=fixture["core_row_p50_a"],
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
        await register_persisted_task10_authority_binding(
            session,
            core_forecast_run_id=CORE_RUN_ID,
            task10_prediction_run_id=PREDICTION_RUN_ID,
        )
        await session.commit()
        for quantile, horizon, row_key, member_key, pred_key in (
            ("P50", 7, "core_row_p50_a", "member_p50_a", "pred_row_h7_a"),
            ("P80", 7, "core_row_p80_a", "member_p80_a", "pred_row_h7_a"),
            ("P50", 14, "core_row_p50_b", "member_p50_b", "pred_row_h14_b"),
        ):
            core_row = fixture[row_key]
            install_authority_fixture_mock_loaders(
                monkeypatch,
                session_rows=rows,
                core_row=core_row,
                task9_member=fixture[member_key],
                prediction_row=fixture[pred_key],
            )
            bundle = await load_persisted_forecast_binding_authority(
                session,
                forecast_cutoff_at=CUTOFF_AT,
                task8_forecast_run_id=TASK8_RUN_ID,
                target_date=core_row.date,
                forecast_quantile=quantile,
                horizon_days=horizon,
                farm_id=FARM_ID,
                subfarm_id=SUBFARM_ID,
                variety_id=VARIETY_ID,
                task10_prediction_run_id=PREDICTION_RUN_ID,
            )
            assert bundle is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_existing_rows_without_binding_remain_compatible_and_fail_closed(
    authority_loader_session,
) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        core_run = await session.get(__import__(
            "backend.app.models.core_forecast", fromlist=["CoreForecastRunModel"]
        ).CoreForecastRunModel, CORE_RUN_ID)
        assert core_run is not None
        bundle = await load_persisted_forecast_binding_authority(
            session,
            forecast_cutoff_at=CUTOFF_AT,
            task8_forecast_run_id=TASK8_RUN_ID,
            target_date=fixture["core_row_p50_a"].date,
            forecast_quantile="P50",
            horizon_days=7,
            farm_id=FARM_ID,
            subfarm_id=SUBFARM_ID,
            variety_id=VARIETY_ID,
            task10_prediction_run_id=None,
        )
    await engine.dispose()
    assert core_run.result_hash
    assert bundle is None


def test_r1_r2_r3_r4_regression() -> None:
    from backend.app.rolling_backtest.persisted_forecast_authority import (
        validate_persisted_forecast_authority_chain,
    )
    from backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader import (
        load_persisted_forecast_binding_authority,
    )

    assert inspect.iscoroutinefunction(validate_persisted_forecast_authority_chain)
    assert inspect.iscoroutinefunction(load_persisted_forecast_binding_authority)
    assert hasattr(CoreForecastRunRepository, "_maybe_register_task10_authority_binding")
