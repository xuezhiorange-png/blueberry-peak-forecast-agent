"""PostgreSQL concurrency acceptance for the S2 idempotency ledger."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestBindingRow,
    RollingBacktestManifest,
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

pytestmark = [pytest.mark.postgres, pytest.mark.postgres_concurrency, pytest.mark.concurrency]

_CUTOFF = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
_LABEL_CUTOFF = datetime(2026, 3, 5, 4, 0, tzinfo=UTC)


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _request() -> S2HistoricalBacktestRequest:
    return S2HistoricalBacktestRequest(
        season_business_keys=("season:2026",),
        farm_business_keys=("farm:alpha",),
        subfarm_business_keys=("subfarm:alpha-1",),
        variety_business_keys=("variety:legacy",),
        master_identity_resolver_version="master-v1",
        mapping_policy_version="mapping-v1",
        resolved_identity_snapshot_hash="a" * 64,
        authority_selection_policy_version="authority-v1",
        single_node_identity_hash="b" * 64,
        forecast_cutoff_at=_CUTOFF,
        label_observation_cutoff_at=_LABEL_CUTOFF,
        label_visibility_mode="AS_OF_EVALUATION",
        requested_horizons_days=(7,),
    )


def _candidate(
    *, forecast_value: Decimal = Decimal("7")
) -> tuple[S2HistoricalBindingCandidate, ...]:
    return (
        S2HistoricalBindingCandidate(
            horizon_days=7,
            target_date=_CUTOFF.date() + timedelta(days=7),
            forecast_cutoff_at=_CUTOFF,
            forecast_value_kg=forecast_value,
            forecast_authority=S2ForecastAuthorityBundle(
                forecast_run_identity_hash="1" * 64,
                daily_row_identity_hash="2" * 64,
                task9_authority_identity_hash="3" * 64,
                task10_authority_identity_hash="4" * 64,
                forecast_code_identity="code-v1",
                model_identity="model-v1",
                parameter_identity="parameter-v1",
                data_identity="data-v1",
                available_at=_CUTOFF,
            ),
            actual_label=S2ActualLabelAuthority(
                label_snapshot_identity_hash="5" * 64,
                source_identity_hash="6" * 64,
                observed_weight_kg=Decimal("8.000000"),
                visibility_timestamp=_LABEL_CUTOFF,
                physical_alignment_status="VERIFIED",
            ),
        ),
    )


async def _invoke() -> int:
    async with AsyncSessionMaker() as session:
        run = await run_s2_historical_binding(
            session,
            request=_request(),
            candidates=_candidate(),
            season_id=2026,
        )
        await session.commit()
        return run.id


async def test_same_s2_request_converges_under_concurrent_sessions() -> None:
    _require_postgres()
    first, second = await asyncio.gather(_invoke(), _invoke())
    assert first == second

    async with AsyncSessionMaker() as session:
        assert await session.scalar(select(func.count()).select_from(RollingBacktestRun)) == 1
        assert await session.scalar(select(func.count()).select_from(RollingBacktestManifest)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(RollingBacktestBindingRow)) == 1
        )


async def test_same_request_with_evidence_drift_is_rejected() -> None:
    _require_postgres()
    await _invoke()
    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestIdentityConflictError):
            await run_s2_historical_binding(
                session,
                request=_request(),
                candidates=_candidate(forecast_value=Decimal("999")),
                season_id=2026,
            )
        await session.rollback()
