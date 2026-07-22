"""PostgreSQL acceptance for the V0.2-S2 binding projection."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestBindingRow,
    RollingBacktestManifest,
    RollingBacktestNode,
    RollingBacktestRun,
)
from backend.app.rolling_backtest.errors import RollingBacktestIdentityConflictError
from backend.app.rolling_backtest.orchestration import run_s2_historical_binding
from backend.app.rolling_backtest.schemas import (
    S2ActualLabelAuthority,
    S2ForecastAuthorityBundle,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingCandidate,
)
from backend.app.rolling_backtest.signatures import s2_request_hash

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

_CUTOFF = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
_LABEL_CUTOFF = datetime(2026, 3, 5, 4, 0, tzinfo=UTC)


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _request(suffix: str = "default") -> S2HistoricalBacktestRequest:
    return S2HistoricalBacktestRequest(
        season_business_keys=(f"season:2026:{suffix}",),
        farm_business_keys=(f"farm:alpha:{suffix}",),
        subfarm_business_keys=(f"subfarm:alpha-1:{suffix}",),
        variety_business_keys=(f"variety:legacy:{suffix}",),
        master_identity_resolver_version="master-v1",
        mapping_policy_version="mapping-v1",
        resolved_identity_snapshot_hash="a" * 64,
        authority_selection_policy_version="authority-v1",
        forecast_cutoff_at=_CUTOFF,
        label_observation_cutoff_at=_LABEL_CUTOFF,
        label_visibility_mode="AS_OF_EVALUATION",
        requested_horizons_days=(7, 14, 21),
    )


def _candidates(
    request: S2HistoricalBacktestRequest,
    *,
    with_labels: bool = True,
) -> tuple[S2HistoricalBindingCandidate, ...]:
    result: list[S2HistoricalBindingCandidate] = []
    for horizon in (7, 14, 21):
        actual = (
            S2ActualLabelAuthority(
                label_snapshot_identity_hash=f"{horizon + 10:064x}",
                label_row_identity_hash=f"{horizon + 30:064x}",
                label_winner_identity_hash=f"{horizon + 40:064x}",
                source_identity_hash=f"{horizon + 20:064x}",
                actual_source_identity_hash=f"{horizon + 50:064x}",
                target_date=_CUTOFF.date() + timedelta(days=horizon),
                season_business_key=request.season_business_keys[0],
                farm_business_key=request.farm_business_keys[0],
                subfarm_business_key=request.subfarm_business_keys[0],
                variety_business_key=request.variety_business_keys[0],
                business_grain_hash=f"{horizon + 60:064x}",
                revision_or_winner_evidence={"revision": horizon},
                observed_weight_kg=Decimal("12.500000"),
                visibility_timestamp=_LABEL_CUTOFF,
                physical_alignment_status="VERIFIED",
            )
            if with_labels
            else None
        )
        result.append(
            S2HistoricalBindingCandidate(
                horizon_days=horizon,
                target_date=_CUTOFF.date() + timedelta(days=horizon),
                forecast_cutoff_at=_CUTOFF,
                forecast_value_kg=Decimal(horizon),
                forecast_authority=S2ForecastAuthorityBundle(
                    forecast_run_identity_hash=f"{horizon:064x}",
                    daily_row_identity_hash=f"{horizon + 1:064x}",
                    task9_authority_identity_hash="c" * 64,
                    task10_authority_identity_hash="d" * 64,
                    forecast_code_identity="code-v1",
                    model_identity="model-v1",
                    parameter_identity="parameter-v1",
                    data_identity="data-v1",
                    available_at=_CUTOFF,
                ),
                actual_label=actual,
                authority_verification="SYNTHETIC_ENGINEERING",
            )
        )
    return tuple(result)


async def _counts(session, request_hash: str | None = None) -> dict[str, int]:
    run_filter = (
        RollingBacktestRun.backtest_request_hash == request_hash
        if request_hash is not None
        else RollingBacktestRun.s2_contract_version.is_not(None)
    )
    return {
        "run": int(
            await session.scalar(
                select(func.count()).select_from(RollingBacktestRun).where(run_filter)
            )
        ),
        "node": int(
            await session.scalar(
                select(func.count())
                .select_from(RollingBacktestNode)
                .join(
                    RollingBacktestRun, RollingBacktestRun.id == RollingBacktestNode.rolling_run_id
                )
                .where(run_filter)
                .where(RollingBacktestNode.node_key == "s2-single-node")
            )
        ),
        "binding": int(
            await session.scalar(
                select(func.count())
                .select_from(RollingBacktestBindingRow)
                .join(
                    RollingBacktestRun,
                    RollingBacktestRun.id == RollingBacktestBindingRow.rolling_run_id,
                )
                .where(run_filter)
            )
        ),
        "manifest": int(
            await session.scalar(
                select(func.count())
                .select_from(RollingBacktestManifest)
                .join(
                    RollingBacktestRun,
                    RollingBacktestRun.id == RollingBacktestManifest.rolling_run_id,
                )
                .where(run_filter)
            )
        ),
    }


async def test_s2_postgres_persistence_round_trip_and_idempotent_replay() -> None:
    _require_postgres()
    request = _request()
    async with AsyncSessionMaker() as session:
        run = await run_s2_historical_binding(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        run_id = run.id
        await session.commit()

    async with AsyncSessionMaker() as fresh_session:
        loaded = await fresh_session.get(RollingBacktestRun, run_id)
        assert loaded is not None
        assert loaded.s2_contract_version == "v0.2-s2-historical-binding-v1"
        assert loaded.s2_node_count == 1
        assert loaded.forecast_cutoff_at == _CUTOFF
        assert loaded.label_observation_cutoff_at == _LABEL_CUTOFF
        assert loaded.backtest_request_hash is not None
        rows = (
            (
                await fresh_session.execute(
                    select(RollingBacktestBindingRow)
                    .where(RollingBacktestBindingRow.rolling_run_id == run_id)
                    .order_by(RollingBacktestBindingRow.horizon_days)
                )
            )
            .scalars()
            .all()
        )
        assert [row.horizon_days for row in rows] == [7, 14, 21]
        assert all(row.actual_value_kg == Decimal("12.500000") for row in rows)
        first_counts = await _counts(fresh_session, s2_request_hash(request))

        replay = await run_s2_historical_binding(
            fresh_session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        assert replay.id == run_id
        assert await _counts(fresh_session) == first_counts


async def test_s2_missing_labels_are_persisted_as_exclusions_without_zero_fill() -> None:
    _require_postgres()
    request = _request("missing-labels")
    async with AsyncSessionMaker() as session:
        run = await run_s2_historical_binding(
            session,
            request=request,
            candidates=_candidates(request, with_labels=False),
            season_id=2026,
        )
        await session.commit()
        rows = (
            (
                await session.execute(
                    select(RollingBacktestBindingRow).where(
                        RollingBacktestBindingRow.rolling_run_id == run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 3
        assert all(row.row_status == "EXCLUDED" for row in rows)
        assert all(row.actual_value_kg is None for row in rows)
        assert all(row.reason_code == "NO_APPROVED_REAL_DATA" for row in rows)


def _sqlstate(error: DBAPIError) -> str | None:
    original = error.orig
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


async def _assert_immutable(
    statement: str,
    run_id: int,
    *,
    expected_message: str = "rolling-backtest S2 evidence row is immutable",
) -> None:
    async with AsyncSessionMaker() as session:
        try:
            await session.execute(text(statement), {"run_id": run_id})
            await session.commit()
        except DBAPIError as exc:
            assert _sqlstate(exc) == "23514"
            assert expected_message in str(exc)
            await session.rollback()
        else:
            raise AssertionError("immutable evidence mutation unexpectedly succeeded")


async def test_s2_manifest_and_binding_rows_are_immutable() -> None:
    _require_postgres()
    request = _request("immutable")
    async with AsyncSessionMaker() as session:
        run = await run_s2_historical_binding(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        await session.commit()
        run_id = run.id
    await _assert_immutable(
        "UPDATE rolling_backtest_manifest SET manifest_schema_version = 'drift' "
        "WHERE rolling_run_id = :run_id",
        run_id,
    )
    await _assert_immutable(
        "DELETE FROM rolling_backtest_binding_row WHERE rolling_run_id = :run_id",
        run_id,
    )
    await _assert_immutable(
        "UPDATE rolling_backtest_binding_row SET forecast_value_kg = 999 "
        "WHERE rolling_run_id = :run_id",
        run_id,
    )
    await _assert_immutable(
        "INSERT INTO rolling_backtest_binding_row ("
        "rolling_run_id, rolling_node_id, horizon_days, target_date, "
        "forecast_cutoff_at, label_observation_cutoff_at, label_visibility_mode, "
        "physical_alignment_status, row_status, reason_code, forecast_row_identity_hash, "
        "actual_label_row_identity_hash, forecast_value_kg, actual_value_kg, canonical_payload, "
        "binding_key_hash, binding_row_hash) "
        "SELECT rolling_run_id, rolling_node_id, horizon_days, target_date, "
        "forecast_cutoff_at, label_observation_cutoff_at, label_visibility_mode, "
        "physical_alignment_status, row_status, reason_code, forecast_row_identity_hash, "
        "actual_label_row_identity_hash, forecast_value_kg, actual_value_kg, canonical_payload, "
        "binding_key_hash, binding_row_hash "
        "FROM rolling_backtest_binding_row WHERE rolling_run_id = :run_id LIMIT 1",
        run_id,
        expected_message="cannot be inserted after manifest seal",
    )


async def test_s2_caller_rollback_leaves_no_final_evidence() -> None:
    _require_postgres()
    request = _request("rollback")
    async with AsyncSessionMaker() as session:
        await run_s2_historical_binding(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        await session.rollback()

    async with AsyncSessionMaker() as fresh_session:
        assert await _counts(fresh_session, s2_request_hash(request)) == {
            "run": 0,
            "node": 0,
            "binding": 0,
            "manifest": 0,
        }


async def test_s2_replay_rejects_persisted_node_cutoff_drift() -> None:
    _require_postgres()
    request = _request("cutoff-drift")
    async with AsyncSessionMaker() as session:
        run = await run_s2_historical_binding(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        await session.commit()
        node = await session.scalar(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run.id)
        )
        assert node is not None
        node.forecast_cutoff_at = _CUTOFF + timedelta(seconds=1)
        with pytest.raises(RollingBacktestIdentityConflictError, match="cutoff drift"):
            await run_s2_historical_binding(
                session,
                request=request,
                candidates=_candidates(request),
                season_id=2026,
            )
        await session.rollback()
