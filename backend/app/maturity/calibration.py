from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np

from backend.app.maturity.config import MaturityCurveConfig
from backend.app.maturity.schemas import GroupCurveArtifact, ResolvedTrainingSample


def empirical_quantile(values: list[Decimal], quantile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    array = np.asarray([float(item) for item in values], dtype=float)
    result = float(np.quantile(array, float(quantile), method="linear"))
    return Decimal(f"{result:.6f}")


def calibration_payload(
    *,
    resolved_samples: list[ResolvedTrainingSample],
    artifacts: dict[str, GroupCurveArtifact],
    support_days: tuple[int, ...],
    config: MaturityCurveConfig,
) -> dict[str, Any]:
    residuals: list[Decimal] = []
    for sample in resolved_samples:
        climate_zone_key = (
            f"zone:{sample.climate_zone_id}|variety:{sample.manifest_row.variety_id}"
        )
        province_key = (
            f"province:{sample.province}|variety:{sample.manifest_row.variety_id}"
        )
        global_key = f"variety:{sample.manifest_row.variety_id}"
        artifact = (
            artifacts.get(climate_zone_key)
            or artifacts.get(province_key)
            or artifacts.get(global_key)
        )
        if artifact is None:
            continue
        predicted_map = {
            rel_day: share
            for rel_day, share in zip(
                support_days,
                artifact.density,
                strict=True,
            )
        }
        actual_map = {rel_day: share for rel_day, share in sample.density_points}
        for rel_day, actual_share in actual_map.items():
            residuals.append(abs(actual_share - predicted_map.get(rel_day, Decimal("0"))))
    p80_margin_share = empirical_quantile(
        residuals,
        config.rules.intervals.p80_quantile,
    )
    p90_margin_share = empirical_quantile(
        residuals,
        config.rules.intervals.p90_quantile,
    )
    warnings: list[str] = []
    if len(residuals) < 10:
        warnings.append("uncalibrated_interval")
        p80_margin_share *= config.rules.intervals.uncalibrated_widening_factor
        p90_margin_share *= config.rules.intervals.uncalibrated_widening_factor
    return {
        "p80_margin_share": p80_margin_share.quantize(Decimal("0.000001")),
        "p90_margin_share": p90_margin_share.quantize(Decimal("0.000001")),
        "residual_count": len(residuals),
        "warnings": warnings,
    }
