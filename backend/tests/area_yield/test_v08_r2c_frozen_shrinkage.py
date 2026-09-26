from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, localcontext

import pytest

from backend.app.area_yield.v08_r2c_frozen_shrinkage import (
    R2CExperimentError,
    build_shrinkage_model,
    daily_predictions_from_frozen_shape,
    error_metrics,
    predict_shrunk_total,
    predict_shrunk_yield,
    shrinkage_weight,
    validate_training_cohort,
    verify_daily_sum,
)


def _training_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(15):
        base_id = f"B{index:02d}"
        area = Decimal(100 + index)
        yield_value = Decimal(500 + 20 * index)
        rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": base_id,
                "season": "2023-2024",
                "area_mu": str(area),
                "season_total_quantity_kg": str(area * yield_value),
                "strict_training_eligible": "true",
            }
        )
    for index in range(22):
        base_id = f"B{index:02d}" if index < 11 else f"C{index - 11:02d}"
        area = Decimal(120 + index)
        yield_value = Decimal(550 + 15 * index)
        rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": base_id,
                "season": "2024-2025",
                "area_mu": str(area),
                "season_total_quantity_kg": str(area * yield_value),
                "strict_training_eligible": "true",
            }
        )
    return rows


def test_frozen_training_cohort_is_37_rows_and_15_22_split() -> None:
    assert validate_training_cohort(_training_rows()) == {
        "row_count": 37,
        "season_counts": {"2023-2024": 15, "2024-2025": 22},
        "unique_base_count": 26,
        "blocked_rows_included": 0,
    }


def test_duplicate_or_blocked_training_rows_fail_closed() -> None:
    rows = _training_rows()
    with pytest.raises(R2CExperimentError, match="DUPLICATE_TRAINING_BASE_SEASON"):
        validate_training_cohort([*rows, rows[0]])
    blocked = [dict(row) for row in rows]
    blocked[0]["strict_training_eligible"] = "false"
    with pytest.raises(R2CExperimentError, match="BLOCKED_TRAINING_ROW_INCLUDED"):
        validate_training_cohort(blocked)


def test_2025_2026_training_row_is_rejected() -> None:
    row = {
        "base_id": "B",
        "canonical_base_name": "B",
        "season": "2025-2026",
        "area_mu": "100",
        "season_total_quantity_kg": "100000",
        "strict_training_eligible": "true",
    }
    with pytest.raises(R2CExperimentError, match="BENCHMARK_SEASON_FORBIDDEN_IN_TRAINING"):
        validate_training_cohort([row])


def test_global_yield_is_area_weighted_from_all_37_training_rows() -> None:
    rows = _training_rows()
    model = build_shrinkage_model(rows, "a" * 64)
    quantity = sum(Decimal(row["season_total_quantity_kg"]) for row in rows)
    area = sum(Decimal(row["area_mu"]) for row in rows)
    with localcontext() as context:
        context.prec = 40
        expected = quantity / area
    assert Decimal(model["global_yield_kg_per_mu"]) == expected
    assert model["training_row_count"] == 37
    assert model["lambda"] == "1"


def test_base_mean_uses_arithmetic_mean_of_season_yields() -> None:
    rows = _training_rows()
    model = build_shrinkage_model(rows, "a" * 64)
    b00 = [row for row in rows if row["base_id"] == "B00"]
    season_yields = [
        Decimal(row["season_total_quantity_kg"]) / Decimal(row["area_mu"]) for row in b00
    ]
    expected = sum(season_yields) / Decimal(len(season_yields))
    assert Decimal(model["base_yield_kg_per_mu"]["B00"]) == expected
    assert model["base_mean_yield_policy"] == (
        "ARITHMETIC_MEAN_OF_ELIGIBLE_BASE_SEASON_YIELDS_KG_PER_MU"
    )


@pytest.mark.parametrize(
    ("support", "expected"),
    [
        (0, Decimal("0")),
        (1, Decimal("0.5")),
        (2, Decimal(2) / Decimal(3)),
    ],
)
def test_lambda_one_weights_for_support_zero_one_two(support: int, expected: Decimal) -> None:
    if support == 2:
        with localcontext() as context:
            context.prec = 60
            expected = Decimal(2) / Decimal(3)
    assert shrinkage_weight(support, Decimal("1")) == expected


def test_lambda_is_pinned_and_cannot_be_overridden() -> None:
    with pytest.raises(R2CExperimentError, match="LAMBDA_NOT_FROZEN_TO_ONE"):
        build_shrinkage_model(_training_rows(), "a" * 64, lambda_value=Decimal("0.5"))


def test_support_zero_is_exact_global_yield_fallback() -> None:
    model = build_shrinkage_model(_training_rows(), "a" * 64)
    assert predict_shrunk_yield(model, "NEVER_SEEN") == Decimal(model["global_yield_kg_per_mu"])
    assert (
        predict_shrunk_total(model, "NEVER_SEEN", Decimal("500"))["predicted_total_kg"]
        == predict_shrunk_total(model, "__GLOBAL__", Decimal("500"))["predicted_total_kg"]
    )


def test_support_one_uses_half_base_and_half_global() -> None:
    model = build_shrinkage_model(_training_rows(), "a" * 64)
    with localcontext() as context:
        context.prec = 40
        expected = Decimal("0.5") * Decimal(model["base_yield_kg_per_mu"]["C00"]) + Decimal(
            "0.5"
        ) * Decimal(model["global_yield_kg_per_mu"])
    assert predict_shrunk_yield(model, "C00") == expected


def test_prediction_total_is_area_scaled_and_six_decimal_quantized() -> None:
    model = build_shrinkage_model(_training_rows(), "a" * 64)
    prediction = predict_shrunk_total(model, "B00", Decimal("123.456789"))
    assert Decimal(prediction["predicted_total_kg"]).as_tuple().exponent == -6
    assert Decimal(prediction["predicted_total_kg"]) == (
        Decimal(prediction["predicted_yield_kg_per_mu"]) * Decimal("123.456789")
    ).quantize(Decimal("0.000001"))


def test_model_artifact_is_training_only_and_deterministic() -> None:
    rows = _training_rows()
    first = build_shrinkage_model(rows, "a" * 64)
    second = build_shrinkage_model(rows, "a" * 64)
    assert first == second
    assert "2025-2026" not in first["training_seasons"]
    assert "benchmark_actual" not in first
    assert first["benchmark_labels_used"] is False


def test_stage_b_shared_shape_keeps_peak_dates_under_positive_rescaling() -> None:
    from backend.app.area_yield.v08_s8_training_backtest import derive_peaks

    start = date(2025, 7, 22)
    shape = [Decimal("0.01"), Decimal("0.02"), Decimal("0.07")]
    shape.extend([Decimal("0")] * 4)
    rows_a = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "predicted_daily_quantity_kg": str(Decimal(100) * share),
        }
        for index, share in enumerate(shape)
    ]
    rows_b = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "predicted_daily_quantity_kg": str(Decimal(700) * share),
        }
        for index, share in enumerate(shape)
    ]
    assert (
        derive_peaks(rows_a)["single_day_peak_date"] == derive_peaks(rows_b)["single_day_peak_date"]
    )


def test_wape_uses_fixed_cohort_and_actual_denominator() -> None:
    metrics = error_metrics([Decimal("100"), Decimal("300")], [Decimal("110"), Decimal("330")])
    assert Decimal(metrics["wape"]) == Decimal("40") / Decimal("400")
    assert metrics["n"] == 2


def _frozen_shape() -> list[dict[str, str]]:
    from datetime import date

    start = date(2025, 7, 22)
    shares = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
    return [
        {
            "base_id": "B00",
            "season": "2025-2026",
            "date": (start + timedelta(days=index)).isoformat(),
            "predicted_share": str(share),
        }
        for index, share in enumerate(shares)
    ]


def test_daily_scaling_reuses_pinned_shape_and_reconciles_to_total(monkeypatch) -> None:
    from backend.app.area_yield import v08_r2_stage_a
    from backend.app.area_yield import v08_r2c_frozen_shrinkage as r2c

    shape = _frozen_shape()
    shape_hash = v08_r2_stage_a.stage_b_shape_hash(shape)
    monkeypatch.setattr(r2c, "EXPECTED_STAGE_B_SHAPE_SHA256", shape_hash)
    totals = [
        {
            "base_id": "B00",
            "canonical_base_name": "B00",
            "target_area_mu": "100",
            "predicted_season_total_kg": "1234.567890",
        }
    ]
    daily = daily_predictions_from_frozen_shape(
        totals,
        shape,
        model_id="R2C",
        model_artifact_sha256="a" * 64,
    )
    assert verify_daily_sum(daily, {"B00": Decimal("1234.567890")}) == 1
    assert [row["predicted_share"] for row in daily] == [row["predicted_share"] for row in shape]
    assert all("actual" not in " ".join(row).lower() for row in daily)


def test_daily_scaling_fails_closed_on_stage_b_hash_drift(monkeypatch) -> None:
    from backend.app.area_yield import v08_r2c_frozen_shrinkage as r2c

    monkeypatch.setattr(r2c, "EXPECTED_STAGE_B_SHAPE_SHA256", "0" * 64)
    with pytest.raises(R2CExperimentError, match="BLOCKED_STAGE_B_DRIFT"):
        daily_predictions_from_frozen_shape(
            [
                {
                    "base_id": "B00",
                    "canonical_base_name": "B00",
                    "target_area_mu": "100",
                    "predicted_season_total_kg": "1000",
                }
            ],
            _frozen_shape(),
            model_id="R2C",
            model_artifact_sha256="a" * 64,
        )


def test_daily_scaling_rejects_missing_base_shape(monkeypatch) -> None:
    from backend.app.area_yield import v08_r2_stage_a
    from backend.app.area_yield import v08_r2c_frozen_shrinkage as r2c

    shape = _frozen_shape()
    monkeypatch.setattr(
        r2c, "EXPECTED_STAGE_B_SHAPE_SHA256", v08_r2_stage_a.stage_b_shape_hash(shape)
    )
    with pytest.raises(R2CExperimentError, match="FROZEN_SHAPE_COHORT_MISMATCH"):
        daily_predictions_from_frozen_shape(
            [
                {
                    "base_id": "B01",
                    "canonical_base_name": "B01",
                    "target_area_mu": "100",
                    "predicted_season_total_kg": "1000",
                }
            ],
            shape,
            model_id="R2C",
            model_artifact_sha256="a" * 64,
        )


def test_support_zero_parity_fails_closed_when_predictions_differ() -> None:
    from backend.app.area_yield.v08_r2c_frozen_shrinkage import validate_support_zero_parity

    rows = [{"support_count": "0", "global": "100", "r2c": "100.000001"}]
    with pytest.raises(R2CExperimentError, match="SUPPORT_ZERO_GLOBAL_PREDICTION_PARITY_FAILED"):
        validate_support_zero_parity(rows, global_key="global", shrinkage_key="r2c")
