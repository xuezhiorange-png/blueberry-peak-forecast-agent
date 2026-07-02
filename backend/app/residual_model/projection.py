from __future__ import annotations

from decimal import Decimal

from backend.app.residual_model.enums import ProjectionReason
from backend.app.residual_model.schemas import ProjectionResult


def calculate_residual_label(
    *,
    observed_effective_receipt_kg: Decimal,
    structural_arrival_p50_kg: Decimal,
) -> Decimal:
    return observed_effective_receipt_kg - structural_arrival_p50_kg


def project_corrected_quantiles(
    *,
    structural_arrival_p50_kg: Decimal,
    predicted_residual_p50_kg: Decimal,
    predicted_residual_p80_kg: Decimal,
    predicted_residual_p90_kg: Decimal,
) -> ProjectionResult:
    raw_p50 = structural_arrival_p50_kg + predicted_residual_p50_kg
    raw_p80 = structural_arrival_p50_kg + predicted_residual_p80_kg
    raw_p90 = structural_arrival_p50_kg + predicted_residual_p90_kg
    reasons: list[ProjectionReason] = []

    clamped_p50 = max(Decimal("0"), raw_p50)
    clamped_p80 = max(Decimal("0"), raw_p80)
    clamped_p90 = max(Decimal("0"), raw_p90)
    nonnegative_applied = (clamped_p50, clamped_p80, clamped_p90) != (raw_p50, raw_p80, raw_p90)
    if nonnegative_applied:
        reasons.append(ProjectionReason.NONNEGATIVE_CLAMP)

    projected_p50 = clamped_p50
    projected_p80 = max(projected_p50, clamped_p80)
    projected_p90 = max(projected_p80, clamped_p90)
    monotonic_applied = (projected_p50, projected_p80, projected_p90) != (
        clamped_p50,
        clamped_p80,
        clamped_p90,
    )
    if monotonic_applied:
        reasons.append(ProjectionReason.QUANTILE_MONOTONIC)

    return ProjectionResult(
        raw_p50_kg=raw_p50,
        raw_p80_kg=raw_p80,
        raw_p90_kg=raw_p90,
        corrected_p50_kg=projected_p50,
        corrected_p80_kg=projected_p80,
        corrected_p90_kg=projected_p90,
        nonnegative_projection_applied=nonnegative_applied,
        quantile_projection_applied=monotonic_applied,
        projection_reasons=reasons,
    )
