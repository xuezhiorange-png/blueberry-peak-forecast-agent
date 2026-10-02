"""Docs-only scope assertions; no model, private data, training or inference."""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCOPE = ROOT / "docs/v0-12/evidence/v0.12.0-scope-freeze-r1.json"
PLAN = ROOT / "docs/v0-12/v0.12.0-version-plan-and-scope-freeze.md"
pytestmark = pytest.mark.contract


def scope() -> dict[str, Any]:
    value = json.loads(SCOPE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_version_identity_and_prior_lifecycle_boundaries() -> None:
    data = scope()
    assert data["VERSION"] == "0.12.0"
    assert data["VERSION_NAME"] == "AREA_BASED_YIELD_MODEL_RESEARCH_AND_VALIDATION"
    assert data["RELEASE_CLASS"] == "RESEARCH_VERSION"
    assert data["V0_12_IS_V0_11_CONTINUATION"] is False
    assert data["V0_11_REOPEN_AUTHORIZED"] is False
    assert data["prior_versions"]["V0_10_LIFECYCLE"] == "CLOSED_WITH_ORIGINAL_GATE_INCOMPLETE"
    assert data["prior_versions"]["V0_11_LIFECYCLE"] == ("CLOSED_ENGINEERING_DELIVERED_NOT_ISSUED")


def test_scale_window_and_complete_calendar_peak_definition() -> None:
    data = scope()
    assert data["PRIMARY_SCALE_INPUT"] == "target_area_mu"
    assert data["inputs"] == ["target_area_mu", "target_season", "applicable_base_or_farm_context"]
    assert data["TARGET_WINDOW"] == "JULY_01_TO_APRIL_15_FROZEN_BUSINESS_WINDOW"
    assert data["NATURAL_FULL_SEASON_CLAIM"] is False
    assert data["ROLLING_7DAY_DEFINITION"] == "MAX_CUMULATIVE_COMPLETE_7_CONSECUTIVE_CALENDAR_DAYS"
    assert data["PEAK_TIE_RULE"] == "EARLIEST_DATE"
    assert data["BASE_CONTEXT_USES"] == [
        "DATA_ASSOCIATION",
        "APPLICABILITY",
        "COVERAGE_EXTRAPOLATION",
    ]
    assert data["COPY_HISTORICAL_FARM_TOTAL_AS_FORECAST"] is False


def test_comparator_is_not_the_legacy_m0_identity() -> None:
    data = scope()
    comparator = data["comparator"]
    assert comparator["id"] == "V0_12_COMPARATOR_BASELINE"
    assert comparator["id"] != data["V0_10_V0_11_REFERENCE_BASELINE"]
    assert comparator["total_formula"] == (
        "target_area_mu * sum(train_total_kg) / sum(train_area_mu)"
    )
    assert comparator["shape_rule"] == "EQUAL_BASE_SEASON_MEAN_NORMALIZED_DAILY_SHARE_BY_MONTH_DAY"
    assert comparator["statistics_source"] == "CORRESPONDING_TRAINING_FOLD_ONLY"
    assert comparator["artifact_renamed_this_task"] is False


def test_admission_is_frozen_evidence_not_integration() -> None:
    data = scope()
    assert data["PR_659_ADMISSION_STATUS"] == "ADMITTED_AS_EXISTING_R1_RESEARCH_EVIDENCE"
    assert data["PR_659_PROPOSED_ROLE"] == "V0_12_R1_AREA_MODEL_RESEARCH_BASELINE"
    assert data["PR_659_IS_VERSION_COMPLETION_EVIDENCE"] is False
    assert data["PR_659_HEAD"] == "76b9e86c24cdd99be23b20e15eb895173ac26671"
    assert data["PR_659_MODIFIED"] is False
    fold = data["admitted_evidence"]["fold"]
    assert fold == {
        "train_seasons": ["2023-2024"],
        "train_count": 15,
        "test_season": "2024-2025",
        "test_count": 22,
        "fold_count": 1,
    }
    assert data["admitted_evidence"]["new_execution"] is False
    for item in data["admitted_evidence"]["sources"]:
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])


def test_original_metrics_and_unchanged_timing_are_retained() -> None:
    metrics = scope()["admitted_evidence"]["metrics"]
    expected = {
        "season_total_wape_percent": ("45.0910", "41.7458"),
        "daily_wape_percent": ("77.0660", "73.1543"),
        "single_peak_quantity_mae_kg": ("7233.920555", "6572.139398"),
        "rolling_7day_peak_quantity_mae_kg": ("48318.586215", "45003.802717"),
        "shape_micro_wape": ("0.632252", "0.632252"),
        "single_peak_date_mae_days": ("21.818182", "21.818182"),
        "rolling_7day_start_date_mae_days": ("22.318182", "22.318182"),
    }
    for key, (baseline, candidate) in expected.items():
        assert metrics[key] == {"baseline": baseline, "candidate": candidate}
    assert Decimal(metrics["season_total_wape_percent"]["baseline"]) - Decimal(
        metrics["season_total_wape_percent"]["candidate"]
    ) == Decimal("3.3452")


@pytest.mark.parametrize(
    "field",
    [
        "V0_12_S1_AUTHORIZED",
        "V0_12_S2_AUTHORIZED",
        "V0_12_VERSION_COMPLETE",
        "PRODUCTION_USE_APPROVED",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PR_659_STABLE_GAIN",
        "PR_659_TEMPORAL_SHAPE_GAIN",
        "PR_659_NEW_BLIND_VALIDATION",
        "PR_659_PROSPECTIVE_VALIDATION",
        "WEATHER_IN_SCOPE",
        "FUTURE_PRODUCTION_PLAN_IN_SCOPE",
        "VARIETY_LEVEL_FORECAST_REQUIRED",
        "MULTI_FACTORY_ROUTING_IN_SCOPE",
        "FACTORY_CAPACITY_OPTIMIZATION_IN_SCOPE",
        "PEAK_SHAVING_IN_SCOPE",
        "TRANSPORT_SCHEDULING_IN_SCOPE",
        "UI_IN_SCOPE",
        "MODEL_TRAINING_EXECUTED",
        "NEW_BACKTEST_EXECUTED",
        "NEW_PREDICTION_EXECUTED",
        "REPOSITORY_PRODUCTION_CODE_CHANGED",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "TAG_CREATED",
        "RELEASE_CREATED",
        "AUTO_MERGE",
    ],
)
def test_no_implicit_scope_or_promotion(field: str) -> None:
    assert scope()[field] is False


def test_new_information_gate_and_locked_future_scoring() -> None:
    data = scope()
    assert data["NO_FURTHER_UNBOUNDED_SEARCH_ON_CONSUMED_2023_2025"] is True
    assert data["NEW_INFORMATION_REQUIRED_FOR_FURTHER_MODEL_RESEARCH"] is True
    assert len(data["new_information"]["qualifying_categories"]) == 4
    assert len(data["new_information"]["nonqualifying_categories"]) == 5
    assert set(data["future_issuance_required_fields"]) == {
        "request_id",
        "target_area_mu",
        "target_season",
        "Base/Farm",
        "model_id",
        "artifact_hash",
        "config_hash",
        "issued_at",
        "daily_curve",
        "season_total",
        "single_peak",
        "rolling_7day_peak",
        "prediction_hash",
    }
    assert data["locked_scoring_forbids"] == [
        "retrain",
        "retune",
        "switch_model",
        "reshape_prediction",
        "rewrite_issued_result",
    ]
    assert data["BUSINESS_ACCURACY_THRESHOLD_STATUS"] == "NOT_ESTABLISHED"


def test_plan_covers_stages_and_negative_closeout() -> None:
    data = scope()
    text = PLAN.read_text(encoding="utf-8")
    for token in [
        "V0.12-S0",
        "V0.12-S1",
        "V0.12-S2",
        "VERSION_COMPLETE=false",
        "RESEARCH_CLOSEOUT_STABLE_GAIN",
        "RESEARCH_CLOSEOUT_NO_STABLE_GAIN",
    ]:
        assert token in text
    assert len(data["completion_requirements"]) == 10
    assert data["research_closeout_options"] == [
        "RESEARCH_CLOSEOUT_STABLE_GAIN",
        "RESEARCH_CLOSEOUT_NO_STABLE_GAIN",
    ]
    assert data["admitted_evidence"]["training_area_range_mu"] == ["216", "2548"]
    assert data["AREA_EXTRAPOLATION_VALIDATED"] is False
