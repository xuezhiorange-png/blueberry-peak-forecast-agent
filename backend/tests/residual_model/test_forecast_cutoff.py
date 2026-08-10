from __future__ import annotations

from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_replay_cutoff_resolver_uses_persisted_exact_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.residual_model.forecast_cutoff import resolve_forecast_cutoff_at

    exact_cutoff = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)

    async def _get_run(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(
            is_replay=True,
            forecast_effective_cutoff_at=exact_cutoff,
        )

    monkeypatch.setattr(
        "backend.app.residual_model.forecast_cutoff.get_harvest_state_run",
        _get_run,
    )

    resolved = await resolve_forecast_cutoff_at(
        object(),
        task9_run_id=17,
        as_of_date=date(2026, 3, 1),
    )

    assert resolved == exact_cutoff


@pytest.mark.asyncio
async def test_replay_cutoff_resolver_fails_closed_when_exact_cutoff_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.residual_model.forecast_cutoff import (
        ForecastCutoffResolutionError,
        resolve_forecast_cutoff_at,
    )

    async def _get_run(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(is_replay=True, forecast_effective_cutoff_at=None)

    monkeypatch.setattr(
        "backend.app.residual_model.forecast_cutoff.get_harvest_state_run",
        _get_run,
    )

    with pytest.raises(
        ForecastCutoffResolutionError,
        match="REPLAY_FORECAST_EFFECTIVE_CUTOFF_MISSING",
    ) as exc_info:
        await resolve_forecast_cutoff_at(
            object(),
            task9_run_id=17,
            as_of_date=date(2026, 3, 1),
        )

    assert exc_info.value.code == "REPLAY_FORECAST_EFFECTIVE_CUTOFF_MISSING"


@pytest.mark.asyncio
async def test_non_replay_cutoff_resolver_retains_legacy_eod_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.residual_model.forecast_cutoff import resolve_forecast_cutoff_at

    async def _get_run(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(is_replay=False, forecast_effective_cutoff_at=None)

    monkeypatch.setattr(
        "backend.app.residual_model.forecast_cutoff.get_harvest_state_run",
        _get_run,
    )

    resolved = await resolve_forecast_cutoff_at(
        object(),
        task9_run_id=17,
        as_of_date=date(2026, 3, 1),
    )

    assert resolved == datetime.combine(date(2026, 3, 1), time.max, tzinfo=UTC)


@pytest.mark.asyncio
async def test_exact_cutoff_takes_precedence_for_non_replay_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.residual_model.forecast_cutoff import resolve_forecast_cutoff_at

    exact_cutoff = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)

    async def _get_run(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(
            is_replay=False,
            forecast_effective_cutoff_at=exact_cutoff,
        )

    monkeypatch.setattr(
        "backend.app.residual_model.forecast_cutoff.get_harvest_state_run",
        _get_run,
    )

    resolved = await resolve_forecast_cutoff_at(
        object(),
        task9_run_id=17,
        as_of_date=date(2026, 3, 1),
    )

    assert resolved == exact_cutoff
