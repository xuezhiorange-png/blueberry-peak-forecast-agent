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
    complete_season_training_totals,
    daily_metrics,
    seal_daily_predictions,
    strict_historical_area_authorized,
    sum_known_mapped_subtotals,
)
from scripts.run_v0_8_s2_canonical_history_model_comparison import _canonical_training_rows

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_unknown_is_excluded_and_confirmed_zero_is_preserved() -> None:
    rows = [
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "KNOWN_MAPPED_SUBTOTAL",
            "mapped_observed_subtotal_kg": "12.5",
            "quantity_completeness_status": "COMPLETE_MAPPED_MEMBERS",
        },
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "CONFIRMED_ZERO",
            "mapped_observed_subtotal_kg": "0",
            "quantity_completeness_status": "AUTHORIZED_ZERO",
        },
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "UNKNOWN",
            "mapped_observed_subtotal_kg": "",
            "quantity_completeness_status": "UNKNOWN_NOT_ZERO_FILLED",
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
                    "quantity_completeness_status": "UNKNOWN_NOT_ZERO_FILLED",
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
                "quantity_completeness_status": "COMPLETE_MAPPED_MEMBERS",
            },
            {
                "actual_status": "CONFIRMED_ZERO",
                "actual_quantity_kg": "0",
                "predicted_quantity_kg": "2",
                "quantity_completeness_status": "COMPLETE_SOURCE_ROWS_ZERO",
            },
            {
                "actual_status": "UNKNOWN",
                "actual_quantity_kg": "",
                "predicted_quantity_kg": "999",
                "quantity_completeness_status": "UNKNOWN_NOT_ZERO_FILLED",
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
    assert metrics["partial_row_count"] == 0


def test_daily_wape_is_pooled_and_zero_denominator_is_explicit() -> None:
    metrics = daily_metrics(
        [
            {
                "actual_status": "KNOWN_MAPPED_SUBTOTAL",
                "actual_quantity_kg": "100",
                "predicted_quantity_kg": "80",
                "quantity_completeness_status": "COMPLETE_MAPPED_MEMBERS",
            },
            {
                "actual_status": "KNOWN_MAPPED_SUBTOTAL",
                "actual_quantity_kg": "10",
                "predicted_quantity_kg": "20",
                "quantity_completeness_status": "COMPLETE_MAPPED_MEMBERS",
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
                "quantity_completeness_status": "AUTHORIZED_ZERO",
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


def test_partial_known_subtotal_is_excluded_from_daily_scoring() -> None:
    metrics = daily_metrics(
        [
            {
                "actual_status": "KNOWN_MAPPED_SUBTOTAL",
                "quantity_completeness_status": "PARTIAL_KNOWN_SUBTOTAL",
                "actual_quantity_kg": "100",
                "predicted_quantity_kg": "100",
            }
        ]
    )

    assert metrics["scored_row_count"] == 0
    assert metrics["partial_row_count"] == 1
    assert metrics["unknown_row_count"] == 0
    assert metrics["status"] == "NOT_COMPUTABLE_NO_COMPLETE_ACTUAL_ROWS"


def test_complete_mapped_members_are_eligible_for_daily_scoring() -> None:
    metrics = daily_metrics(
        [
            {
                "actual_status": "KNOWN_MAPPED_SUBTOTAL",
                "quantity_completeness_status": "COMPLETE_MAPPED_MEMBERS",
                "actual_quantity_kg": "100",
                "predicted_quantity_kg": "100",
            }
        ]
    )

    assert metrics["scored_row_count"] == 1
    assert metrics["partial_row_count"] == 0
    assert metrics["daily_wape"] == "0"


def test_unknown_daily_actual_is_excluded_and_must_have_no_numeric_value() -> None:
    metrics = daily_metrics(
        [
            {
                "actual_status": "UNKNOWN",
                "quantity_completeness_status": "UNKNOWN_NOT_ZERO_FILLED",
                "actual_quantity_kg": "",
                "predicted_quantity_kg": "100",
            }
        ]
    )

    assert metrics["scored_row_count"] == 0
    assert metrics["unknown_row_count"] == 1
    assert metrics["partial_row_count"] == 0


@pytest.mark.parametrize("completeness", ["COMPLETE_SOURCE_ROWS_ZERO", "AUTHORIZED_ZERO"])
def test_authorized_confirmed_zero_remains_daily_scoreable(completeness: str) -> None:
    metrics = daily_metrics(
        [
            {
                "actual_status": "CONFIRMED_ZERO",
                "quantity_completeness_status": completeness,
                "actual_quantity_kg": "0",
                "predicted_quantity_kg": "0",
            }
        ]
    )

    assert metrics["scored_row_count"] == 1
    assert metrics["daily_mae_kg"] == "0"


def test_partial_daily_subtotal_is_not_promoted_into_training_season_sum() -> None:
    daily_rows = [
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "KNOWN_MAPPED_SUBTOTAL",
            "quantity_completeness_status": "COMPLETE_MAPPED_MEMBERS",
            "mapped_observed_subtotal_kg": "100",
        },
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "KNOWN_MAPPED_SUBTOTAL",
            "quantity_completeness_status": "PARTIAL_KNOWN_SUBTOTAL",
            "mapped_observed_subtotal_kg": "50",
        },
    ]

    assert sum_known_mapped_subtotals(daily_rows, included_seasons={"2023-2024"}) == {
        ("base-a", "2023-2024"): Decimal("100")
    }
    assert (
        complete_season_training_totals(
            [
                {
                    "base_id": "base-a",
                    "season": "2023-2024",
                    "business_total_coverage_status": "NOT_ESTABLISHED_NO_FROZEN_TOTAL_AUTHORITY",
                    "season_total_complete": "false",
                    "business_window_mapped_quantity_kg": "150",
                }
            ],
            included_seasons={"2023-2024"},
        )
        == {}
    )


def test_canonical_daily_training_rows_exclude_partial_subtotals() -> None:
    rows = _canonical_training_rows(
        [
            {
                "base_id": "base-a",
                "season": "2023-2024",
                "date": "2023-07-01",
                "quantity_status": "KNOWN_MAPPED_SUBTOTAL",
                "quantity_completeness_status": "COMPLETE_MAPPED_MEMBERS",
                "mapped_observed_subtotal_kg": "100",
            },
            {
                "base_id": "base-a",
                "season": "2023-2024",
                "date": "2023-07-02",
                "quantity_status": "KNOWN_MAPPED_SUBTOTAL",
                "quantity_completeness_status": "PARTIAL_KNOWN_SUBTOTAL",
                "mapped_observed_subtotal_kg": "50",
            },
            {
                "base_id": "base-a",
                "season": "2023-2024",
                "date": "2023-07-03",
                "quantity_status": "CONFIRMED_ZERO",
                "quantity_completeness_status": "AUTHORIZED_ZERO",
                "mapped_observed_subtotal_kg": "0",
            },
            {
                "base_id": "base-a",
                "season": "2023-2024",
                "date": "2023-07-04",
                "quantity_status": "UNKNOWN",
                "quantity_completeness_status": "UNKNOWN_NOT_ZERO_FILLED",
                "mapped_observed_subtotal_kg": "",
            },
        ],
        {"base-a": {"base_id": "base-a"}},
    )

    assert [row["observed_harvest_kg"] for row in rows] == ["100", "0"]


def test_incomplete_season_total_is_not_built_from_many_complete_days() -> None:
    daily_rows = [
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "quantity_status": "KNOWN_MAPPED_SUBTOTAL",
            "quantity_completeness_status": "COMPLETE_MAPPED_MEMBERS",
            "mapped_observed_subtotal_kg": "100",
        }
        for _ in range(200)
    ]
    quality_row = {
        "base_id": "base-a",
        "season": "2023-2024",
        "business_total_coverage_status": "NOT_ESTABLISHED_NO_FROZEN_TOTAL_AUTHORITY",
        "season_total_complete": "false",
        "business_window_mapped_quantity_kg": "10000",
    }

    assert complete_season_training_totals([quality_row], included_seasons={"2023-2024"}) == {}
    assert sum_known_mapped_subtotals(daily_rows, included_seasons={"2023-2024"}) == {
        ("base-a", "2023-2024"): Decimal("20000")
    }


def test_complete_business_season_total_is_eligible_for_exploratory_training() -> None:
    quality_row = {
        "base_id": "base-a",
        "season": "2023-2024",
        "business_total_coverage_status": "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE",
        "season_total_complete": "true",
        "business_window_mapped_quantity_kg": "10000.25",
    }

    assert complete_season_training_totals([quality_row], included_seasons={"2023-2024"}) == {
        ("base-a", "2023-2024"): Decimal("10000.25")
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
    assert evidence["exploratory_lane"]["total_model_training_feasible"] is False
    assert evidence["exploratory_lane"]["complete_training_base_season_count"] == 0
    assert evidence["exploratory_lane"]["candidate_model_trained"] is False
    assert evidence["integrity"]["unknown_is_zero"] is False
    assert evidence["integrity"]["validation_label_leakage"] is False
    assert evidence["daily_actual_eligibility_policy"]["missing_or_unknown_filled_as_zero"] is False
    assert evidence["common_oot"]["candidate_daily_row_count"] == 11797
    assert evidence["common_oot"]["complete_daily_scored_row_count"] == 7976
    assert evidence["common_oot"]["partial_known_subtotal_row_count"] == 1718
    assert evidence["common_oot"]["unknown_daily_row_count"] == 2103
    assert evidence["common_oot"]["complete_daily_evaluation_dataset_sha256"] == (
        "f5dc421b4346514fef0e5f9fded42cd56f69e0cdf8a3807dca86e026d016f080"
    )
    assert evidence["combined_oot"]["daily"]["v07_wape"] == ("0.7195790799353937948127680318")
    assert evidence["combined_oot"]["daily"]["v08_wape"] == "NOT_COMPUTABLE"
    assert evidence["combined_oot"]["daily"]["v08_minus_v07_wape"] == "NOT_COMPUTABLE"
    assert evidence["combined_oot"]["season_total"]["v08_minus_v07_wape"] == ("NOT_COMPUTABLE")
    assert (
        evidence["superseded_prior_results"]["previous_exploratory_daily_wape_comparison_status"]
        == "PREVIOUS_EXPLORATORY_DAILY_WAPE_COMPARISON_INVALIDATED"
    )
    assert evidence["superseded_prior_results"]["previous_daily_improvement_claim_valid"] is False
    assert evidence["superseded_prior_results"]["previous_v08_season_total_status"] == (
        "SUPERSEDED_NONAUTHORITATIVE_PRIOR_EXPLORATORY_RESULT"
    )
    assert evidence["determinism"]["independent_replay_count"] == 2
    assert evidence["determinism"]["private_manifest_hash_match"] is True
    assert evidence["combined_oot"]["single_day_peak"] == (
        "NOT_COMPUTABLE_NO_FROZEN_PEAK_AUTHORITY"
    )
    assert evidence["combined_oot"]["rolling_7day_peak"] == (
        "NOT_COMPUTABLE_NO_FROZEN_ROLLING7_AUTHORITY"
    )
