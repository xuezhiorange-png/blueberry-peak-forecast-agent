"""Live obtain for PIT-visible incumbent daily forecast curve providers.

Binds the production Task 8 maturity daily prediction adapter when a lawful
SOURCE-002 session is available. Fail-closed when no session, ambiguous PIT
forecast runs per grain, or synthetic placeholder authority is detected.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls

from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle
from backend.app.s3_daily_rowset.forecast_port import IncumbentDailyCurveProvider
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_loader import (
    build_pit_visible_incumbent_daily_curve_index,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_provider import (
    PitVisibleIncumbentDailyCurveProvider,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
)

LAWFUL_PIT_VISIBLE_INCUMBENT_DAILY_FORECAST_VALUE_SOURCE = (
    "backend/app/models/maturity.py:MaturityDailyPredictionModel"
    " via backend/app/s3_daily_rowset/pit_visible_incumbent_daily_curve_provider.py"
)
EXISTING_PRODUCTION_SESSION_FACTORY = "backend/app/db/session.py:AsyncSessionMaker"
SOURCE_002_LIVE_SESSION_BINDING_PATH = (
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_session.py:"
    "source_002_row_level_read_live_session_provider"
)
FORECAST_SELECTION_MODE = "historical_observed_pit_visible_unique_grain_forecast_run"

_obtained_provider: IncumbentDailyCurveProvider | None = None
_obtained_cutoff: datetime | None = None
_obtained_grains: frozenset[tuple[str, str, str, str]] | None = None


@dataclass(frozen=True, slots=True)
class LiveIncumbentForecastDailyCurveObtainResult:
    obtained: bool
    provider: IncumbentDailyCurveProvider | None = None
    forecast_cutoff_at: datetime | None = None
    forecast_binding_authority: S2ForecastAuthorityBundle | None = None
    ambiguous_grain_count: int = 0
    unavailable_grain_count: int = 0


class _AsyncSessionNotObtained(RuntimeError):
    pass


def _grain_has_ambiguous_forecast_run(
    index_grain_counts: dict[tuple[str, str, str, str], int],
    grains: frozenset[tuple[str, str, str, str]],
) -> bool:
    return any(index_grain_counts.get(grain, 0) > 1 for grain in grains)


def _grain_has_unavailable_forecast_run(
    index_grain_counts: dict[tuple[str, str, str, str], int],
    grains: frozenset[tuple[str, str, str, str]],
) -> bool:
    return any(index_grain_counts.get(grain, 0) != 1 for grain in grains)


async def _obtain_from_async_session(
    session: AsyncSession,
    *,
    materialization_grains: frozenset[tuple[str, str, str, str]],
) -> LiveIncumbentForecastDailyCurveObtainResult:
    forecast_cutoff_at = datetime.fromisoformat(REVIEW_CUTOFF_AT)
    index = await build_pit_visible_incumbent_daily_curve_index(
        session,
        forecast_cutoff_at=forecast_cutoff_at,
        grains=materialization_grains,
    )
    ambiguous = sum(
        1 for grain in materialization_grains if index.grain_forecast_run_count.get(grain, 0) > 1
    )
    unavailable = sum(
        1 for grain in materialization_grains if index.grain_forecast_run_count.get(grain, 0) != 1
    )
    if _grain_has_ambiguous_forecast_run(index.grain_forecast_run_count, materialization_grains):
        return LiveIncumbentForecastDailyCurveObtainResult(
            obtained=False,
            provider=None,
            forecast_cutoff_at=forecast_cutoff_at,
            ambiguous_grain_count=ambiguous,
            unavailable_grain_count=unavailable,
        )
    if not index.cells or _grain_has_unavailable_forecast_run(
        index.grain_forecast_run_count, materialization_grains
    ):
        return LiveIncumbentForecastDailyCurveObtainResult(
            obtained=False,
            provider=None,
            forecast_cutoff_at=forecast_cutoff_at,
            ambiguous_grain_count=ambiguous,
            unavailable_grain_count=unavailable,
        )
    provider = PitVisibleIncumbentDailyCurveProvider(index=index)
    return LiveIncumbentForecastDailyCurveObtainResult(
        obtained=True,
        provider=provider,
        forecast_cutoff_at=forecast_cutoff_at,
        ambiguous_grain_count=0,
        unavailable_grain_count=0,
    )


async def _obtain_with_async_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
    *,
    materialization_grains: frozenset[tuple[str, str, str, str]],
) -> LiveIncumbentForecastDailyCurveObtainResult:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise _AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise _AsyncSessionNotObtained()

        return await _obtain_from_async_session(
            session,
            materialization_grains=materialization_grains,
        )
    finally:
        await session_cm.__aexit__(None, None, None)


def obtain_live_incumbent_forecast_daily_curve_provider(
    materialization_grains: frozenset[tuple[str, str, str, str]] | None = None,
) -> LiveIncumbentForecastDailyCurveObtainResult:
    """Return a lawful PIT-visible daily curve provider when production DB is bound."""
    if materialization_grains is None:
        return LiveIncumbentForecastDailyCurveObtainResult(obtained=False, provider=None)
    global _obtained_provider, _obtained_cutoff, _obtained_grains
    if (
        _obtained_provider is not None
        and _obtained_grains == materialization_grains
        and _obtained_cutoff is not None
    ):
        return LiveIncumbentForecastDailyCurveObtainResult(
            obtained=True,
            provider=_obtained_provider,
            forecast_cutoff_at=_obtained_cutoff,
        )
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return LiveIncumbentForecastDailyCurveObtainResult(obtained=False, provider=None)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return LiveIncumbentForecastDailyCurveObtainResult(obtained=False, provider=None)
    try:
        result = asyncio.run(
            _obtain_with_async_session_maker(
                live_async_session_maker,
                materialization_grains=materialization_grains,
            )
        )
    except (_AsyncSessionNotObtained, MissingGreenlet, Exception):
        return LiveIncumbentForecastDailyCurveObtainResult(obtained=False, provider=None)
    if result.obtained and result.provider is not None:
        _obtained_provider = result.provider
        _obtained_cutoff = result.forecast_cutoff_at
        _obtained_grains = materialization_grains
    return result
