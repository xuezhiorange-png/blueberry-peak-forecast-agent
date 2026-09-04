"""R4 reference-driven canonical binding tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.models.core_forecast import CoreForecastDailyRowModel
from backend.app.rolling_backtest.orchestration import resolve_s2_persisted_authorities
from backend.app.rolling_backtest.persisted_forecast_authority import (
    MATERIAL_S2_FORECAST_AUTHORITY_BUNDLE_FIELDS,
    PersistedForecastAuthorityRefs,
    assert_full_s2_forecast_authority_bundle_equivalence,
    build_canonical_s2_forecast_authority_bundle,
    validate_persisted_forecast_authority_chain,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader import (
    load_persisted_forecast_binding_authority,
)
from backend.tests.forecast_quality.authority_loader_fixture import (
    CODE_AUTHORITY_ID,
    CORE_RUN_ID,
    CUTOFF_AT,
    FARM_ID,
    PREDICTION_RUN_ID,
    SUBFARM_ID,
    TASK8_RUN_ID,
    TASK9_RUN_ID,
    VARIETY_ID,
    _fixture_hash,
    _prediction_row,
    seed_canonical_authority_fixture,
)
from backend.tests.forecast_quality.persisted_forecast_authority_fixture_mocks import (
    copy_fixture_rows_to_async_session,
    create_authority_fixture_async_engine,
    ensure_authority_fixture_tables,
    install_authority_fixture_mock_loaders,
    session_rows_from_sync_fixture,
)
from backend.tests.rolling_backtest.test_historical_backtest_contracts import (
    _install_persisted_authority_fixture,
)

pytest_plugins = ["backend.tests.forecast_quality.authority_loader_fixture"]


class _RecordingAsyncSession:
    async def get(self, model: type[object], identity: int) -> object | None:
        return None

    async def scalars(self, _statement: object) -> object:
        class _Result:
            def all(self_inner) -> list[object]:
                return []

        return _Result()


@pytest.mark.asyncio
async def test_existing_s2_uses_shared_forecast_authority_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(monkeypatch)
    shared = AsyncMock(return_value=object())
    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration.validate_persisted_forecast_authority_chain",
        shared,
    )
    await resolve_s2_persisted_authorities(session, request=request, candidates=(candidate,))
    shared.assert_awaited_once()


@pytest.mark.asyncio
async def test_s3_b_uses_same_shared_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    shared = AsyncMock()
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader.validate_persisted_forecast_authority_chain",
        shared,
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader.resolve_persisted_forecast_binding_refs",
        AsyncMock(
            return_value=PersistedForecastAuthorityRefs(
                core_forecast_run_id=CORE_RUN_ID,
                core_forecast_daily_row_id=2001,
                task9_run_id=TASK9_RUN_ID,
                task10_prediction_run_id=PREDICTION_RUN_ID,
            )
        ),
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader.build_canonical_s2_forecast_authority_bundle",
        lambda _resolution: __import__(
            "backend.app.rolling_backtest.schemas", fromlist=["S2ForecastAuthorityBundle"]
        ).S2ForecastAuthorityBundle(
            forecast_run_identity_hash="a" * 64,
            daily_row_identity_hash="b" * 64,
            task9_authority_identity_hash="c" * 64,
            task9_member_identity_hash="d" * 64,
            task10_authority_identity_hash="e" * 64,
            task10_model_identity_hash="f" * 64,
            task10_replay_identity_hash="0" * 64,
            task10_prediction_row_identity_hash="1" * 64,
            historical_code_authority_id=1,
            forecast_code_identity="2" * 64,
            historical_code_identity="a" * 40,
            build_artifact_hash="3" * 64,
            config_bundle_hash="4" * 64,
            model_identity="5" * 64,
            parameter_identity="6" * 64,
            data_identity="7" * 64,
            available_at=CUTOFF_AT,
            task10_model_available_at=CUTOFF_AT,
            historical_code_available_at=CUTOFF_AT,
        ),
    )
    await load_persisted_forecast_binding_authority(
        _RecordingAsyncSession(),
        forecast_cutoff_at=CUTOFF_AT,
        task8_forecast_run_id=TASK8_RUN_ID,
        target_date=__import__("datetime").date(2026, 3, 7),
        forecast_quantile="P50",
        horizon_days=7,
        farm_id=FARM_ID,
        subfarm_id=SUBFARM_ID,
        variety_id=VARIETY_ID,
        task10_prediction_run_id=PREDICTION_RUN_ID,
    )
    shared.assert_awaited_once()


def test_real_existing_s2_canonical_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    session, request, candidate = _install_persisted_authority_fixture(monkeypatch)
    resolved = asyncio.run(
        resolve_s2_persisted_authorities(
            session,
            request=request,
            candidates=(candidate,),
        )
    )
    assert len(resolved) == 1
    assert resolved[0].authority_verification == "PERSISTED"
    assert resolved[0].forecast_authority == candidate.forecast_authority


@pytest.mark.asyncio
async def test_full_bundle_equivalence_with_shared_validator(
    authority_loader_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
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
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        resolution = await validate_persisted_forecast_authority_chain(
            session,
            refs=PersistedForecastAuthorityRefs(
                core_forecast_run_id=CORE_RUN_ID,
                core_forecast_daily_row_id=core_row.id,
                task9_run_id=TASK9_RUN_ID,
                task10_prediction_run_id=PREDICTION_RUN_ID,
            ),
            forecast_cutoff_at=CUTOFF_AT,
            target_date=core_row.date,
            horizon_days=7,
        )
        bundle = build_canonical_s2_forecast_authority_bundle(resolution)
        loaded = await load_persisted_forecast_binding_authority(
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
    assert loaded is not None
    assert_full_s2_forecast_authority_bundle_equivalence(bundle, loaded)
    for field_name in MATERIAL_S2_FORECAST_AUTHORITY_BUNDLE_FIELDS:
        assert getattr(bundle, field_name) == getattr(loaded, field_name)


@pytest.mark.asyncio
async def test_task10_exact_reference_binding(
    authority_loader_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    rows = session_rows_from_sync_fixture(authority_loader_session, fixture=fixture)
    evaluate_calls: list[int] = []

    async def _evaluate_task10(
        _session: object,
        *,
        binding_context: object,
        prediction_input: object,
        requested_policy: object,
    ) -> object:
        evaluate_calls.append(prediction_input.persistent_reference.reference_value)
        from types import SimpleNamespace

        return SimpleNamespace(prediction_run_id=PREDICTION_RUN_ID)

    install_authority_fixture_mock_loaders(
        monkeypatch,
        session_rows=rows,
        core_row=core_row,
        task9_member=fixture["member_p50_a"],
        prediction_row=fixture["pred_row_h7_a"],
    )
    monkeypatch.setattr(
        "backend.app.rolling_backtest.replay_task10_binding.evaluate_replay_task10_binding",
        _evaluate_task10,
    )
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
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
    assert evaluate_calls == [PREDICTION_RUN_ID]


@pytest.mark.asyncio
async def test_multiple_task10_runs_one_usable_still_fails_closed_without_reference(
    authority_loader_session,
) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
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
    second_row = _prediction_row(
        row_id=4999,
        prediction_run_id=9999,
        target_date=core_row.date,
        horizon_days=7,
        row_hash=_fixture_hash("prediction-row-duplicate"),
    )
    authority_loader_session.add_all([duplicate_run, second_row])
    authority_loader_session.commit()
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        assert (
            await load_persisted_forecast_binding_authority(
                session,
                forecast_cutoff_at=CUTOFF_AT,
                task8_forecast_run_id=TASK8_RUN_ID,
                target_date=core_row.date,
                forecast_quantile="P50",
                horizon_days=7,
                farm_id=FARM_ID,
                subfarm_id=SUBFARM_ID,
                variety_id=VARIETY_ID,
                task10_prediction_run_id=None,
            )
            is None
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_wrong_pinned_task10_run_fails_closed(
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
        replay_binding_prediction_run_id=9999,
    )
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        assert (
            await load_persisted_forecast_binding_authority(
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
            is None
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_task9_integrity_loader_drift_fails_closed(
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

    async def _load_task9_drifted(_session: object, *, run_id: int) -> object | None:
        from types import SimpleNamespace

        return SimpleNamespace(
            result_hash=rows[("HarvestStateRun", TASK9_RUN_ID)].result_hash,
            status="completed",
            daily_member_state_rows=(
                SimpleNamespace(
                    state_date=core_row.date,
                    forecast_quantile="P80",
                    farm_id=core_row.farm_id,
                    subfarm_id=core_row.subfarm_id,
                    variety_id=core_row.variety_id,
                    destination_factory_id=core_row.destination_factory_id,
                ),
            ),
        )

    monkeypatch.setattr(
        "backend.app.harvest_state.persistence.load_harvest_state_output_by_id",
        _load_task9_drifted,
    )
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        with pytest.raises(ValueError, match="integrity loader did not resolve one exact member"):
            await validate_persisted_forecast_authority_chain(
                session,
                refs=PersistedForecastAuthorityRefs(
                    core_forecast_run_id=CORE_RUN_ID,
                    core_forecast_daily_row_id=core_row.id,
                    task9_run_id=TASK9_RUN_ID,
                    task10_prediction_run_id=PREDICTION_RUN_ID,
                ),
                forecast_cutoff_at=CUTOFF_AT,
                target_date=core_row.date,
                horizon_days=7,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_core_forecast_integrity_drift_fails_closed(
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

    class _CorePersistence:
        def __init__(self, _session: object) -> None:
            pass

        async def load_complete_run(self, run_id: int) -> object | None:
            from types import SimpleNamespace

            core_run_row = rows[("CoreForecastRunModel", CORE_RUN_ID)]
            return SimpleNamespace(
                run=SimpleNamespace(run_id=CORE_RUN_ID, result_hash="drifted"),
                daily_curve=SimpleNamespace(rows=(SimpleNamespace(row_hash=core_row.row_hash),)),
                code_authority=SimpleNamespace(
                    authority_id=CODE_AUTHORITY_ID,
                    authority_hash=core_run_row.code_authority_hash,
                    source_commit_sha="a" * 40,
                    build_artifact_hash="b" * 64,
                    config_bundle_hash="c" * 64,
                    available_at=CUTOFF_AT,
                ),
            )

    monkeypatch.setattr(
        "backend.app.core_forecast.persistence.CoreForecastRunRepository",
        _CorePersistence,
    )
    engine = create_authority_fixture_async_engine()
    await ensure_authority_fixture_tables(engine)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await copy_fixture_rows_to_async_session(authority_loader_session, session, fixture=fixture)
        with pytest.raises(ValueError, match="canonical persisted-authority binding"):
            await validate_persisted_forecast_authority_chain(
                session,
                refs=PersistedForecastAuthorityRefs(
                    core_forecast_run_id=CORE_RUN_ID,
                    core_forecast_daily_row_id=core_row.id,
                    task9_run_id=TASK9_RUN_ID,
                    task10_prediction_run_id=PREDICTION_RUN_ID,
                ),
                forecast_cutoff_at=CUTOFF_AT,
                target_date=core_row.date,
                horizon_days=7,
            )
    await engine.dispose()
