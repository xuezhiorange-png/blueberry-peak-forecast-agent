"""Live obtain for PIT-visible incumbent daily forecast curve providers.

Discovery: the incumbent replay identity postgres read exposes only replay
grains (model, cutoff, quantile) and explicitly forbids kg / daily_curve
columns. No lawful production IncumbentDailyCurveProvider exists yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle
from backend.app.s3_daily_rowset.forecast_port import IncumbentDailyCurveProvider

LAWFUL_PIT_VISIBLE_INCUMBENT_DAILY_FORECAST_VALUE_SOURCE = "NONE"


@dataclass(frozen=True, slots=True)
class LiveIncumbentForecastDailyCurveObtainResult:
    obtained: bool
    provider: IncumbentDailyCurveProvider | None = None
    forecast_binding_authority: S2ForecastAuthorityBundle | None = None


def obtain_live_incumbent_forecast_daily_curve_provider() -> (
    LiveIncumbentForecastDailyCurveObtainResult
):
    """Return a lawful PIT-visible daily curve provider when one is bound.

    Fail-closed: returns ``obtained=False`` when no production adapter exists.
    """

    return LiveIncumbentForecastDailyCurveObtainResult(obtained=False, provider=None)
