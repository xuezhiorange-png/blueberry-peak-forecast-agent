"""Isolated total-yield primitives. Real area bindings require reviewed source facts.

No area inference, season-specific denominator, geographic fallback or shape fitting.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from statistics import median
from typing import Any

from backend.app.area_yield.data import digest


def positive(value: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("authority number must be a decimal string")
    number = Decimal(value)
    if not number.is_finite() or number <= 0:
        raise ValueError("number must be positive finite")
    return number


def emit(number: Decimal) -> str:
    return str(number.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN))


@dataclass(frozen=True)
class Area:
    farm: str
    value: str
    basis: str
    source_reference: str
    source_hash: str
    scope: str
    productive_semantics_confirmed: bool

    def validate(self, farm: str) -> Decimal:
        if self.farm != farm or self.scope != "FARM":
            raise ValueError("farm scope mismatch")
        if self.basis not in {
            "MEASURED",
            "BUSINESS_REPORTED",
            "AUTHORIZED_CALIBRATION",
            "BUSINESS_CONFIRMED",
        }:
            raise ValueError("unapproved area basis")
        if not self.productive_semantics_confirmed or not self.source_reference:
            raise ValueError("productive area authority not established")
        if len(self.source_hash) != 64 or any(
            c not in "0123456789abcdef" for c in self.source_hash
        ):
            raise ValueError("source hash required")
        return positive(self.value)


def sample(area: Area, farm: str, season: str, total: str, completeness: str) -> dict[str, str]:
    denominator = area.validate(farm)
    if completeness not in {"COMPLETE", "STRICT_ELIGIBLE"}:
        raise ValueError("complete season required")
    if season not in {"2023-2024", "2024-2025"}:
        raise ValueError("unauthorized season")
    return {
        "farm": farm,
        "season": season,
        "total_kg": str(positive(total)),
        "area_mu": str(denominator),
        "yield_kg_per_mu": emit(positive(total) / denominator),
        "area_basis": area.basis,
        "source_hash": area.source_hash,
        "completeness": completeness,
    }


def fit(rows: list[dict[str, str]]) -> dict[str, Any]:
    if not rows or any(r["season"] != "2023-2024" for r in rows):
        raise ValueError("only 23~24 training allowed")
    if len({r["farm"] for r in rows}) != len(rows):
        raise ValueError("duplicate farm-season")
    if any(r["completeness"] not in {"STRICT_ELIGIBLE", "COMPLETE"} for r in rows):
        raise ValueError("incomplete training season")
    yields = {
        r["farm"]: emit(positive(r["total_kg"]) / positive(r["area_mu"]))
        for r in sorted(rows, key=lambda r: r["farm"])
    }
    result: dict[str, Any] = {
        "model_version": "total-yield-r4-v1",
        "training_season": "2023-2024",
        "global_yield": emit(median([Decimal(v) for v in yields.values()])),
        "farm_yields": yields,
        "training_hash": digest(sorted(rows, key=lambda r: r["farm"])),
        "unknown_farm_policy": "FAIL_CLOSED",
    }
    result["hash"] = digest(result)
    return result


def predict_total(
    model: dict[str, Any], requested_area_mu: str, farm: str, kind: str
) -> dict[str, str]:
    if digest({k: v for k, v in model.items() if k != "hash"}) != model["hash"]:
        raise ValueError("model hash mismatch")
    area = positive(requested_area_mu)
    if kind not in {"global", "prior"}:
        raise ValueError("unknown model")
    if kind == "prior" and farm not in model["farm_yields"]:
        raise ValueError("unknown farm; no implicit fallback")
    value = positive(model["global_yield"] if kind == "global" else model["farm_yields"][farm])
    return {
        "predicted_yield_kg_per_mu": emit(value),
        "requested_area_mu": str(area),
        "predicted_season_total_kg": emit(area * value),
        "model_version": model["model_version"],
        "model_basis": kind,
        "training_season": model["training_season"],
        "limitations": "LINEAR_BUSINESS_ASSUMPTION_NOT_AREA_EXTRAPOLATION_VALIDATION",
    }
