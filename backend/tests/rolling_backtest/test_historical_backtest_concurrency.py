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
from backend.app.rolling_backtest.orchestration import build_s2_binding_rows
from backend.app.rolling_backtest.persistence import persist_s2_historical_binding
from backend.app.rolling_backtest.schemas import (
    S2ActualLabelAuthority,
    S2ForecastAuthorityBundle,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingCandidate,
    s2_business_grain_hash,
    s2_physical_alignment_evidence_hash,
)

pytestmark = [pytest.mark.postgres, pytest.mark.postgres_concurrency, pytest.mark.concurrency]

_CUTOFF = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
_LABEL_CUTOFF = datetime(2026, 3, 5, 4, 0, tzinfo=UTC)


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _request(suffix: str = "concurrency") -> S2HistoricalBacktestRequest:
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
        requested_horizons_days=(7,),
    )


def _candidate(
    *, forecast_value: Decimal = Decimal("7")
) -> tuple[S2HistoricalBindingCandidate, ...]:
    return (
        S2HistoricalBindingCandidate(
            season_id=2026,
            season_business_key="season:2026:concurrency",
            farm_business_key="farm:alpha:concurrency",
            subfarm_business_key="subfarm:alpha-1:concurrency",
            variety_business_key="variety:legacy:concurrency",
            forecast_quantile="P50",
            horizon_days=7,
            target_date=_CUTOFF.date() + timedelta(days=7),
            forecast_cutoff_at=_CUTOFF,
            forecast_value_kg=forecast_value,
            forecast_authority=S2ForecastAuthorityBundle(
                forecast_run_identity_hash="1" * 64,
                daily_row_identity_hash="2" * 64,
                task9_authority_identity_hash="3" * 64,
                task9_member_identity_hash="5" * 64,
                task10_authority_identity_hash="4" * 64,
                task10_model_identity_hash="6" * 64,
                task10_replay_identity_hash="7" * 64,
                task10_prediction_row_identity_hash="8" * 64,
                historical_code_authority_id=901,
                forecast_code_identity="9" * 64,
                historical_code_identity="a" * 40,
                build_artifact_hash="b" * 64,
                config_bundle_hash="e" * 64,
                model_identity="model-v1",
                parameter_identity="parameter-v1",
                data_identity="data-v1",
                available_at=_CUTOFF,
                task10_model_available_at=_CUTOFF,
                historical_code_available_at=_CUTOFF,
            ),
            actual_label=S2ActualLabelAuthority(
                label_snapshot_identity_hash="5" * 64,
                label_resolution_status="EXACT_LABEL",
                label_row_identity_hash="7" * 64,
                label_winner_identity_hash="8" * 64,
                label_winner_set_identity_hash="b" * 64,
                source_identity_hash="6" * 64,
                actual_source_identity_hash="9" * 64,
                target_date=_CUTOFF.date() + timedelta(days=7),
                season_business_key="season:2026:concurrency",
                farm_business_key="farm:alpha:concurrency",
                subfarm_business_key="subfarm:alpha-1:concurrency",
                variety_business_key="variety:legacy:concurrency",
                business_grain_hash=s2_business_grain_hash(
                    season_business_key="season:2026:concurrency",
                    farm_business_key="farm:alpha:concurrency",
                    subfarm_business_key="subfarm:alpha-1:concurrency",
                    variety_business_key="variety:legacy:concurrency",
                    target_date=_CUTOFF.date() + timedelta(days=7),
                ),
                revision_or_winner_evidence={"revision": 1},
                observed_weight_kg=Decimal("8.000000"),
                visibility_timestamp=_LABEL_CUTOFF,
                forecast_physical_event="TEST_FARM_PICK_EQUIVALENT",
                actual_physical_event="TEST_FARM_PICK_EQUIVALENT",
                forecast_quantity_basis="TEST_EQUIVALENT_KG",
                actual_quantity_basis="TEST_EQUIVALENT_KG",
                unit="kg",
                loss_boundary_policy_version="test-only-equivalent-loss-boundary-v1",
                physical_alignment_policy_version="test-only-synthetic-alignment-v1",
                physical_alignment_evidence_hash=s2_physical_alignment_evidence_hash(
                    forecast_physical_event="TEST_FARM_PICK_EQUIVALENT",
                    actual_physical_event="TEST_FARM_PICK_EQUIVALENT",
                    forecast_quantity_basis="TEST_EQUIVALENT_KG",
                    actual_quantity_basis="TEST_EQUIVALENT_KG",
                    unit="kg",
                    loss_boundary_policy_version="test-only-equivalent-loss-boundary-v1",
                    physical_alignment_policy_version="test-only-synthetic-alignment-v1",
                    physical_alignment_status="VERIFIED",
                ),
                physical_alignment_status="VERIFIED",
            ),
            authority_verification="SYNTHETIC_ENGINEERING",
        ),
    )


async def _invoke() -> int:
    async with AsyncSessionMaker() as session:
        request = _request()
        run = await persist_s2_historical_binding(
            session,
            request=request,
            rows=build_s2_binding_rows(request, _candidate()),
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


async def test_same_binding_key_different_evidence_is_rejected() -> None:
    _require_postgres()
    await _invoke()
    async with AsyncSessionMaker() as session:
        with pytest.raises(RollingBacktestIdentityConflictError):
            request = _request()
            await persist_s2_historical_binding(
                session,
                request=request,
                rows=build_s2_binding_rows(
                    request,
                    _candidate(forecast_value=Decimal("999")),
                ),
            )
        await session.rollback()
