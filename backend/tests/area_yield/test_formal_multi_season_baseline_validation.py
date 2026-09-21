import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.area_yield.base_product import AreaForecastProductRequest, forecast_base_area
from backend.app.area_yield.base_product_authority import load_base_product_authority
from backend.app.area_yield.formal_multi_season_validation import (
    ActualDay,
    FormalValidationError,
    actual_rows_from_mapping,
    aggregate_fold_scores,
    business_boundary,
    business_calendar,
    fit_total_model,
    pooled_wape,
    predict_daily_curve,
    predict_total,
    score_daily_series,
    seal_prediction_rows,
)


@pytest.mark.unit
def test_prediction_seal_does_not_accept_or_read_validation_labels() -> None:
    model = fit_total_model(
        [
            {
                "base_id": "base_a",
                "season": "2023-2024",
                "quantity_kg": "100",
                "reference_area_mu": "10",
                "area_status": "FROZEN_ACCEPTED_PROXY",
            }
        ]
    )
    scope = [{"base_id": "base_a", "canonical_base_name": "A", "productive_area_mu": "10"}]
    temporal = {
        "feature_mean": [0.0] * 10,
        "feature_scale": [1.0] * 10,
        "coefficients": [1.0] + [0.0] * 10,
    }
    sealed = seal_prediction_rows(
        fold_id="A",
        train_seasons=["2023-2024"],
        validation_season="2024-2025",
        base_scope=scope,
        model=model,
        temporal_model=temporal,
        registry_file_sha256="r" * 64,
        temporal_artifact_sha256="t" * 64,
        training_input_hash="i" * 64,
    )
    assert sealed["manifest"]["validation_labels_read"] is False
    assert sealed["manifest"]["prediction_sealed_before_validation_label_scoring"] is True
    first_hash = sealed["manifest"]["prediction_hash"]
    actual_a = [
        ActualDay(day, Decimal("1"), "KNOWN_MAPPED_SUBTOTAL", "a" * 64)
        for day in business_calendar("2024-2025")
    ]
    actual_b = [
        ActualDay(day, Decimal("9"), "KNOWN_MAPPED_SUBTOTAL", "b" * 64)
        for day in business_calendar("2024-2025")
    ]
    scored_a = score_daily_series(
        predicted_daily=sealed["predictions"][0]["predicted_daily"], actual_daily=actual_a
    )
    scored_b = score_daily_series(
        predicted_daily=sealed["predictions"][0]["predicted_daily"], actual_daily=actual_b
    )
    assert first_hash == sealed["manifest"]["prediction_hash"]
    assert scored_a["daily"]["pooled_wape"] != scored_b["daily"]["pooled_wape"]


@pytest.mark.unit
def test_missing_actual_is_not_zero_and_confirmed_zero_is_comparable() -> None:
    days = business_calendar("2024-2025")
    predicted = [
        {"date": day.isoformat(), "predicted_quantity_kg": "1", "normalized_share": "0"}
        for day in days
    ]
    actual = [ActualDay(day, Decimal("0"), "CONFIRMED_ZERO", "a" * 64) for day in days]
    actual[3] = ActualDay(days[3], None, "UNKNOWN_MISSING", "a" * 64)
    result = score_daily_series(predicted_daily=predicted, actual_daily=actual)
    assert result["known_row_count"] == len(days) - 1
    assert result["unknown_row_count"] == 1
    assert result["coverage_status"] == "PARTIAL"
    assert result["season_total"]["status"].startswith("NOT_COMPUTABLE")


@pytest.mark.unit
def test_pooled_wape_is_not_macro_run_wape() -> None:
    pooled = pooled_wape([Decimal("10"), Decimal("10")], [Decimal("100"), Decimal("1000")])
    macro = (Decimal("10") / Decimal("100") + Decimal("10") / Decimal("1000")) / 2
    assert pooled == Decimal("20") / Decimal("1100")
    assert pooled != macro


@pytest.mark.unit
def test_fold_aggregate_uses_pooled_daily_numerator_and_denominator() -> None:
    base_scores = [
        {
            "daily": {"status": "COMPUTABLE", "comparable_row_count": 1},
            "_daily_abs_error_kg": "10",
            "_daily_actual_kg": "100",
            "season_total": {"status": "NOT_COMPUTABLE"},
            "single_day_peak": {"status": "NOT_COMPUTABLE"},
            "rolling7": {"status": "NOT_COMPUTABLE"},
        },
        {
            "daily": {"status": "COMPUTABLE", "comparable_row_count": 1},
            "_daily_abs_error_kg": "10",
            "_daily_actual_kg": "1000",
            "season_total": {"status": "NOT_COMPUTABLE"},
            "single_day_peak": {"status": "NOT_COMPUTABLE"},
            "rolling7": {"status": "NOT_COMPUTABLE"},
        },
    ]
    result = aggregate_fold_scores(base_scores)
    assert result["daily"]["pooled_wape"] == "0.01818181818181818181818181818"
    assert result["daily"]["pooled_wape"] != "0.055"


@pytest.mark.unit
def test_partial_actual_does_not_create_a_rolling_window() -> None:
    days = business_calendar("2024-2025")
    predicted = [
        {"date": day.isoformat(), "predicted_quantity_kg": "1", "normalized_share": "0"}
        for day in days
    ]
    actual = [ActualDay(day, Decimal("1"), "KNOWN_MAPPED_SUBTOTAL", "a" * 64) for day in days]
    actual[6] = ActualDay(days[6], None, "UNKNOWN_GLOBAL_NO_RECORD", "a" * 64)
    result = score_daily_series(predicted_daily=predicted, actual_daily=actual)
    assert result["rolling7"]["status"] == "NOT_COMPUTABLE_PARTIAL_ACTUAL_COVERAGE"


@pytest.mark.unit
def test_business_calendar_is_frozen_and_deterministic() -> None:
    first = business_calendar("2024-2025")
    second = business_calendar("2024-2025")
    assert first == second
    assert first[0] == date(2024, 7, 1)
    assert first[-1] == date(2025, 4, 15)
    assert len(first) == 289


@pytest.mark.unit
def test_immediate_prior_model_fails_closed_without_global_fallback() -> None:
    model = fit_total_model(
        [
            {
                "base_id": "base_a",
                "season": "2023-2024",
                "quantity_kg": "100",
                "reference_area_mu": "10",
            }
        ],
        prior_season="2023-2024",
    )
    with pytest.raises(FormalValidationError, match="PRIOR_SEASON_HISTORY_MISSING"):
        predict_total(model, "unseen-base", Decimal("10"))


@pytest.mark.unit
def test_model_fit_rejects_non_immediate_prior_or_mixed_training_history() -> None:
    with pytest.raises(FormalValidationError, match="NON_IMMEDIATE_PRIOR_TRAINING_SAMPLE"):
        fit_total_model(
            [
                {
                    "base_id": "base_a",
                    "season": "2023-2024",
                    "quantity_kg": "100",
                    "reference_area_mu": "10",
                }
            ],
            prior_season="2024-2025",
        )


@pytest.mark.unit
def test_2025_2026_boundary_excludes_preseason_and_postseason_dates() -> None:
    boundary = business_boundary("2025-2026")
    assert boundary.start == date(2025, 7, 22)
    assert boundary.end == date(2026, 4, 15)
    assert len(business_calendar("2025-2026", boundary)) == 268
    temporal = {
        "feature_mean": [0.0] * 10,
        "feature_scale": [1.0] * 10,
        "coefficients": [1.0] + [0.0] * 10,
    }
    curve = predict_daily_curve(
        season="2025-2026",
        reference_area_mu=Decimal("10"),
        predicted_total_kg=Decimal("100"),
        temporal_model=temporal,
        boundary=boundary,
    )
    assert curve[0]["date"] == "2025-07-22"
    assert curve[-1]["date"] == "2026-04-15"
    assert "2025-07-01" not in {row["date"] for row in curve}
    assert "2026-04-16" not in {row["date"] for row in curve}


@pytest.mark.unit
def test_actual_mapping_uses_frozen_2025_2026_business_window() -> None:
    boundary = business_boundary("2025-2026")
    base_id = "base_a"
    source_hash = "a" * 64
    raw_rows = [
        {"date": date(2025, 7, 1), "farm": "Farm A", "quantity": "99"},
        {"date": date(2025, 7, 22), "farm": "Farm A", "quantity": "7"},
        {"date": date(2026, 4, 15), "farm": "Farm A", "quantity": "8"},
        {"date": date(2026, 4, 16), "farm": "Farm A", "quantity": "88"},
    ]
    rows = actual_rows_from_mapping(
        season="2025-2026",
        raw_rows=raw_rows,
        label_to_base={("2025-2026", "Farm A"): base_id},
        candidate_bases_by_label={},
        base_scope=[{"base_id": base_id}],
        source_hash=source_hash,
        boundary=boundary,
    )[base_id]
    by_date = {row.day: row for row in rows}
    assert by_date[date(2025, 7, 22)].quantity_kg == Decimal("7")
    assert by_date[date(2026, 4, 15)].quantity_kg == Decimal("8")
    assert date(2025, 7, 1) not in by_date
    assert date(2026, 4, 16) not in by_date


@pytest.mark.unit
def test_formal_total_matches_frozen_product_authority() -> None:
    authority = load_base_product_authority()
    registry = json.loads(
        Path("configs/v0_5_base_reference_registry_v1.json").read_text(encoding="utf-8")
    )
    history = authority.history[0]
    base = next(row for row in registry["bases"] if row["base_id"] == history["base_id"])
    model = fit_total_model(
        [
            {
                "base_id": history["base_id"],
                "season": history["season"],
                "quantity_kg": history["harvest_total_kg"],
                "reference_area_mu": base["productive_area_mu"],
            }
        ],
        prior_season=history["season"],
    )
    formal_total = predict_total(
        model, history["base_id"], Decimal(str(base["productive_area_mu"]))
    )["predicted_season_total_kg"]
    product = forecast_base_area(
        AreaForecastProductRequest(
            base_id=history["base_id"],
            target_area_mu=str(base["productive_area_mu"]),
            target_season="2024-2025",
            forecast_mode="STRICT",
        ),
        authority,
    )
    assert formal_total == product.predicted_season_total_kg
