from __future__ import annotations

from decimal import Decimal


def test_residual_label_calculation() -> None:
    from backend.app.residual_model.projection import calculate_residual_label

    assert calculate_residual_label(
        observed_effective_receipt_kg=Decimal("120"),
        structural_arrival_p50_kg=Decimal("100"),
    ) == Decimal("20")


def test_nonnegative_and_monotonic_projection() -> None:
    from backend.app.residual_model.projection import project_corrected_quantiles

    projected = project_corrected_quantiles(
        structural_arrival_p50_kg=Decimal("100"),
        predicted_residual_p50_kg=Decimal("-200"),
        predicted_residual_p80_kg=Decimal("-50"),
        predicted_residual_p90_kg=Decimal("-120"),
    )

    assert projected.corrected_p50_kg == Decimal("0")
    assert projected.corrected_p50_kg <= projected.corrected_p80_kg <= projected.corrected_p90_kg
    assert projected.nonnegative_projection_applied is True
    assert projected.quantile_projection_applied is True
