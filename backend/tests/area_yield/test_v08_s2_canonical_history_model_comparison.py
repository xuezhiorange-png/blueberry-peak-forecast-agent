"""Contract tests for the V0.8-S2 frozen-history OOT comparison."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.area_yield.v08_s2_model_comparison import (
    ModelComparisonContractError,
    actual_total_metric,
    common_base_scope,
    daily_metrics,
    seal_daily_predictions,
    strict_historical_area_authorized,
    sum_known_mapped_subtotals,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_unknown_is_excluded_and_confirmed_zero_is_preserved() -> None:
    rows = [
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "KNOWN_MAPPED_SUBTOTAL",
            "mapped_observed_subtotal_kg": "12.5",
        },
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "CONFIRMED_ZERO",
            "mapped_observed_subtotal_kg": "0",
        },
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "UNKNOWN",
            "mapped_observed_subtotal_kg": "",
        },
    ]

    assert sum_known_mapped_subtotals(rows, included_seasons={"2023-2024"}) == {
        ("base-a", "2023-2024"): Decimal("12.5")
    }


def test_unknown_numeric_value_fails_closed_instead_of_becoming_zero() -> None:
    with pytest.raises(ModelComparisonContractError, match="UNKNOWN_QUANTITY_MUST_REMAIN_NULL"):
        sum_known_mapped_subtotals(
            [
                {
                    "base_id": "base-a",
                    "season": "2023-2024",
                    "quantity_status": "UNKNOWN",
                    "mapped_observed_subtotal_kg": "0",
                }
            ],
            included_seasons={"2023-2024"},
        )


def test_reference_area_is_not_strict_historical_actual_area() -> None:
    assert not strict_historical_area_authorized(
        {
            "historical_actual_productive_area_status": "NOT_ESTABLISHED",
            "historical_actual_productive_area_mu": "",
            "area_semantics": "REFERENCE_AREA_ONLY",
        }
    )
    assert strict_historical_area_authorized(
        {
            "historical_actual_productive_area_status": "BUSINESS_CONFIRMED_SOURCE_LABEL_BOUND",
            "historical_actual_productive_area_mu": "25.0",
            "area_semantics": "REFERENCE_AREA_ONLY",
        }
    )


def test_common_scope_requires_both_models_and_registry_identity() -> None:
    scope = common_base_scope(
        v07_yield_by_base={"b1": Decimal("1"), "b2": Decimal("2")},
        canonical_history_by_base={"b1": Decimal("3"), "b3": Decimal("4")},
        registry_base_ids={"b1", "b2", "b3"},
    )
    assert scope == ["b1"]


def test_daily_metrics_do_not_score_unknown_and_do_score_authorized_zero() -> None:
    metrics = daily_metrics(
        [
            {
                "actual_status": "KNOWN_MAPPED_SUBTOTAL",
                "actual_quantity_kg": "8",
                "predicted_quantity_kg": "10",
            },
            {
                "actual_status": "CONFIRMED_ZERO",
                "actual_quantity_kg": "0",
                "predicted_quantity_kg": "2",
            },
            {
                "actual_status": "UNKNOWN",
                "actual_quantity_kg": "",
                "predicted_quantity_kg": "999",
            },
        ]
    )

    assert metrics["scored_row_count"] == 2
    assert metrics["unknown_row_count"] == 1
    assert metrics["actual_kg"] == "8"
    assert metrics["absolute_error_kg"] == "4"
    assert metrics["daily_wape"] == "0.5"
    assert metrics["daily_mae_kg"] == "2"
    assert metrics["daily_bias_kg_per_row"] == "2"


def test_daily_wape_is_pooled_and_zero_denominator_is_explicit() -> None:
    metrics = daily_metrics(
        [
            {
                "actual_status": "KNOWN_MAPPED_SUBTOTAL",
                "actual_quantity_kg": "100",
                "predicted_quantity_kg": "80",
            },
            {
                "actual_status": "KNOWN_MAPPED_SUBTOTAL",
                "actual_quantity_kg": "10",
                "predicted_quantity_kg": "20",
            },
        ]
    )
    assert metrics["daily_wape"] == format(Decimal("30") / Decimal("110"), "f")

    zero_denominator = daily_metrics(
        [
            {
                "actual_status": "CONFIRMED_ZERO",
                "actual_quantity_kg": "0",
                "predicted_quantity_kg": "1",
            }
        ]
    )
    assert zero_denominator["daily_wape"] == "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"


def test_season_total_metrics_are_pooled_and_signed_bias_is_retained() -> None:
    metrics = actual_total_metric(
        predicted_totals=[Decimal("80"), Decimal("20")],
        actual_totals=[Decimal("100"), Decimal("10")],
    )
    assert metrics["season_total_wape"] == format(Decimal("30") / Decimal("110"), "f")
    assert metrics["season_total_mae_kg"] == "15"
    assert metrics["season_total_bias_kg_per_base"] == "-5"


def test_model_predictions_are_sealed_without_validation_labels() -> None:
    model_config = json.loads(
        (REPO_ROOT / "configs/v0_5_area_forecast_model_v1.json").read_text(encoding="utf-8")
    )
    registry = {
        "base-a": {
            "base_id": "base-a",
            "canonical_base_name": "基地 A",
            "productive_area_mu": "100",
        }
    }
    args = {
        "fold_id": "FOLD_A",
        "model_id": "V0_8_CANONICAL_HISTORY_CANDIDATE",
        "season": "2024-2025",
        "prior_season": "2023-2024",
        "base_scope": ["base-a"],
        "yield_by_base": {"base-a": Decimal("100")},
        "registry_by_id": registry,
        "temporal_model": model_config["temporal_model"],
        "boundary": business_boundary("2024-2025"),
    }

    first_rows, _, first_hash = seal_daily_predictions(**args)
    # Validation labels are deliberately not arguments to the prediction API.
    changed_validation_actual = {"base-a": Decimal("999999999")}
    second_rows, _, second_hash = seal_daily_predictions(**args)

    assert changed_validation_actual
    assert first_rows == second_rows
    assert first_hash == second_hash == digest(first_rows)


def test_actual_total_no_authority_is_not_zero() -> None:
    metrics = actual_total_metric(predicted_totals=[], actual_totals=[])
    assert metrics == {
        "status": "NOT_COMPUTABLE_NO_COMPLETE_ACTUAL_TOTAL_AUTHORITY_IN_COMMON_SCOPE",
        "base_season_count": 0,
    }


def test_published_s2_evidence_preserves_scope_and_metric_conclusions() -> None:
    evidence = json.loads(
        (
            REPO_ROOT
            / "docs/v0-8/evidence/s2-canonical-history-model-retrain-and-oot-comparison-r1.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["result"] == "INSUFFICIENT_STRICT_AUTHORITY_FOR_COMPARISON"
    assert evidence["strict_area_lane"]["training_feasible"] is False
    assert evidence["strict_area_lane"]["training_base_season_count"] == 0
    assert evidence["exploratory_lane"]["lane"] == "EXPLORATORY_REFERENCE_AREA"
    assert evidence["exploratory_lane"]["production_eligible"] is False
    assert evidence["prediction_integrity"]["unknown_is_zero"] is False
    assert evidence["prediction_integrity"]["validation_label_leakage"] is False
    assert evidence["combined_oot"]["daily"]["v08_minus_v07_wape"] == (
        "-0.0357476518500845057571150971"
    )
    assert evidence["combined_oot"]["season_total"]["v08_minus_v07_wape"] == (
        "0.4645426603883874617891471978"
    )
    assert evidence["combined_oot"]["single_day_peak"] == (
        "NOT_COMPUTABLE_NO_FROZEN_PEAK_AUTHORITY"
    )
    assert evidence["combined_oot"]["rolling_7day_peak"] == (
        "NOT_COMPUTABLE_NO_FROZEN_ROLLING7_AUTHORITY"
    )
