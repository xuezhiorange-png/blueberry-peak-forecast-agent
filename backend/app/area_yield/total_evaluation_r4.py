"""Equal-farm total/yield metrics, separate kg-weighted business diagnostic."""

from decimal import Decimal
from statistics import median

from backend.app.area_yield.total_yield_r4 import emit, positive


def compare(actual: dict[str, str], prediction: dict[str, str]) -> dict[str, str]:
    ay, py = positive(actual["yield_kg_per_mu"]), positive(prediction["predicted_yield_kg_per_mu"])
    at, pt = positive(actual["total_kg"]), positive(prediction["predicted_season_total_kg"])
    return {
        "farm": actual["farm"],
        "area_mu": actual["area_mu"],
        "actual_yield": str(ay),
        "predicted_yield": str(py),
        "yield_abs_error": emit(abs(py - ay)),
        "yield_rel_error": emit(abs(py - ay) / ay),
        "actual_total": str(at),
        "predicted_total": str(pt),
        "total_abs_error": emit(abs(pt - at)),
        "total_rel_error": emit(abs(pt - at) / at),
    }


def aggregate(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows or len({r["farm"] for r in rows}) != len(rows):
        raise ValueError("nonempty unique farm set required")

    def values(key: str) -> list[Decimal]:
        return [Decimal(r[key]) for r in rows]

    def mean(key: str) -> Decimal:
        return sum(values(key), Decimal(0)) / len(rows)

    rel = sorted(values("total_rel_error"))
    position = Decimal("0.9") * (len(rel) - 1)
    lo = int(position)
    fraction = position - lo
    p90 = rel[lo] + fraction * (rel[min(lo + 1, len(rel) - 1)] - rel[lo])
    return {
        "farm_count": str(len(rows)),
        "yield_mae": emit(mean("yield_abs_error")),
        "yield_mape": emit(mean("yield_rel_error")),
        "yield_wape": emit(
            sum(values("yield_abs_error"), Decimal(0)) / sum(values("actual_yield"), Decimal(0))
        ),
        "total_rel_median": emit(median(rel)),
        "total_rel_mean": emit(mean("total_rel_error")),
        "total_rel_p90": emit(p90),
        "kg_weighted_wape_diagnostic": emit(
            sum(values("total_abs_error"), Decimal(0)) / sum(values("actual_total"), Decimal(0))
        ),
    }
