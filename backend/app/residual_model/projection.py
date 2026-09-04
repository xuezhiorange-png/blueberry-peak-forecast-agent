from __future__ import annotations

from decimal import Decimal

from backend.app.residual_model.enums import ProjectionReason
from backend.app.residual_model.schemas import ProjectionResult


def _quantile_crossing_count(
    *,
    p50: Decimal,
    p80: Decimal,
    p90: Decimal,
) -> int:
    ordered = sorted((p50, p80, p90))
    return int((p50, p80, p90) != tuple(ordered))


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


def project_final_target_quantiles(
    *,
    predicted_p50_kg: Decimal,
    predicted_p80_kg: Decimal,
    predicted_p90_kg: Decimal,
) -> ProjectionResult:
    """Deterministic nonnegative monotonic projection on direct final-target kg."""

    raw_p50 = predicted_p50_kg
    raw_p80 = predicted_p80_kg
    raw_p90 = predicted_p90_kg
    raw_crossing_count = _quantile_crossing_count(p50=raw_p50, p80=raw_p80, p90=raw_p90)
    reasons: list[ProjectionReason] = []
    nonnegative_projection_count = 0

    clamped_p50 = max(Decimal("0"), raw_p50)
    clamped_p80 = max(Decimal("0"), raw_p80)
    clamped_p90 = max(Decimal("0"), raw_p90)
    if (clamped_p50, clamped_p80, clamped_p90) != (raw_p50, raw_p80, raw_p90):
        nonnegative_projection_count += sum(
            1
            for raw, clamped in zip(
                (raw_p50, raw_p80, raw_p90),
                (clamped_p50, clamped_p80, clamped_p90),
                strict=True,
            )
            if raw != clamped
        )
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
    final_crossing_count = _quantile_crossing_count(
        p50=projected_p50,
        p80=projected_p80,
        p90=projected_p90,
    )

    return ProjectionResult(
        raw_p50_kg=raw_p50,
        raw_p80_kg=raw_p80,
        raw_p90_kg=raw_p90,
        corrected_p50_kg=projected_p50,
        corrected_p80_kg=projected_p80,
        corrected_p90_kg=projected_p90,
        nonnegative_projection_applied=nonnegative_projection_count > 0,
        quantile_projection_applied=monotonic_applied,
        projection_reasons=reasons,
        raw_crossing_count=raw_crossing_count,
        final_crossing_count=final_crossing_count,
        nonnegative_projection_count=nonnegative_projection_count,
    )
