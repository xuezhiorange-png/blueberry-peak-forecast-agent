"""Runtime-calendar adapter of the frozen Harvest State V1 window block.

No source access, season admission, imputation or prediction. Callers supply an
authoritative calendar. The historical module stays byte-for-byte unchanged.
The aggregation block below is verbatim V1 (only boundary.start becomes start),
not a second feature method; fixed-source golden tests guard exact equivalence.
"""

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal, localcontext

from backend.app.area_yield.v015_harvest_state import FEATURES


def window_values(
    prior: Mapping[date, Decimal | None], start: date, cutoff: date
) -> tuple[dict[str, str | None], dict[str, int], set[str]]:
    vector, audit, reasons = {}, {}, set()
    with localcontext() as ctx:
        ctx.prec = 50
        for feature, length in zip(FEATURES, (7, 14, 28, None), strict=True):
            first = cutoff - timedelta(days=length) if length else start
            days = [first + timedelta(days=i) for i in range((cutoff - first).days)]
            missing = sum(prior.get(d) is None for d in days)
            key = feature.replace("_harvest_kg", "_missing_count")
            audit[key] = missing
            vector[feature] = (
                None
                if missing
                else str(sum((v for d in days if (v := prior[d]) is not None), Decimal(0)))
            )
            if first < start:
                reasons.add("HARVEST_STATE_INCOMPLETE_PRIOR_WINDOW")
    return vector, audit, reasons
