from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from backend.app.maturity.schemas import (
    MaturityDailyPrediction,
    MaturityModelExecutionResult,
)
from backend.app.maturity.service import (
    _artifact_payload,
    _forecast_source_signature,
    _model_run_status_value,
    _training_source_signature,
)


def test_training_source_signature_is_order_invariant_and_keeps_excluded_rows() -> None:
    manifest_a = [
        {
            "plan_id": 2,
            "include": False,
            "sample_weight": Decimal("1"),
            "exclusion_reason": "manual",
        },
        {
            "plan_id": 1,
            "include": True,
            "sample_weight": Decimal("2"),
            "exclusion_reason": None,
        },
    ]
    manifest_b = list(reversed(manifest_a))

    signature_a = _training_source_signature(
        manifest_rows=manifest_a,
        training_cutoff=date(2026, 4, 30),
        config_hash="cfg",
        model_version="task8-v1",
        random_seed=20260624,
    )
    signature_b = _training_source_signature(
        manifest_rows=manifest_b,
        training_cutoff=date(2026, 4, 30),
        config_hash="cfg",
        model_version="task8-v1",
        random_seed=20260624,
    )

    assert signature_a == signature_b


def test_forecast_source_signature_changes_when_observation_fingerprint_changes() -> None:
    common = {
        "plan_id": 1,
        "plan_version": 3,
        "mapping_row_hash": "mapping-a",
        "base_temperature_search_run_id": 5,
        "base_temperature_source_signature": "base-temp-a",
        "selected_base_temperature": Decimal("5"),
        "config_hash": "cfg",
        "model_version": "task8-v1",
        "artifact_hash": "artifact-a",
        "as_of_date": date(2026, 3, 1),
        "prediction_start_date": date(2026, 3, 1),
        "prediction_end_date": date(2026, 3, 7),
    }
    signature_a = _forecast_source_signature(
        observation_fingerprint=[
            {
                "observation_date": date(2026, 2, 28),
                "observation_id": 1,
                "row_hash": "obs-a",
                "available_at": date(2026, 3, 1),
                "source_version": "v1",
                "weather_source_location_id": 10,
            }
        ],
        **common,
    )
    signature_b = _forecast_source_signature(
        observation_fingerprint=[
            {
                "observation_date": date(2026, 2, 28),
                "observation_id": 2,
                "row_hash": "obs-b",
                "available_at": date(2026, 3, 1),
                "source_version": "v2",
                "weather_source_location_id": 10,
            }
        ],
        **common,
    )

    assert signature_a != signature_b


def test_model_run_status_value_preserves_failed_and_unavailable() -> None:
    assert _model_run_status_value("running") == "running"
    assert _model_run_status_value("completed") == "completed"
    assert _model_run_status_value("failed") == "failed"
    assert _model_run_status_value("unavailable") == "unavailable"
    with pytest.raises(ValueError, match="unsupported persisted run status"):
        _model_run_status_value("skipped")


def test_artifact_payload_is_json_native() -> None:
    payload = _artifact_payload(
        {
            "model_family": "shared_spline",
            "support_days": (-1, 0, 1),
            "group_models": {
                "zone:1|variety:2": {
                    "density": [Decimal("0.2"), Decimal("0.5"), Decimal("0.3")],
                    "peak_day": Decimal("0"),
                    "sample_count": 3,
                }
            },
            "created_for": date(2026, 6, 24),
        }
    )

    assert payload["group_models"]["zone:1|variety:2"]["density"] == ["0.2", "0.5", "0.3"]
    assert payload["created_for"] == "2026-06-24"
    json.dumps(payload)


def test_execution_result_keeps_daily_prediction_dataclasses() -> None:
    result = MaturityModelExecutionResult(
        status="completed",
        run_id=1,
        source_signature="sig",
        config_hash="cfg",
        model_version="task8-v1",
        model_family="shared_spline",
        sample_count=3,
        distinct_season_count=2,
        distinct_farm_count=2,
        distinct_subfarm_count=1,
        warnings=(),
        blockers=(),
        training_metrics={},
        calibration_metrics={},
        artifact={},
        input_snapshot={},
    )
    prediction = MaturityDailyPrediction(
        prediction_date=date(2026, 3, 1),
        phenology_coordinate_day=Decimal("0"),
        p50_kg=Decimal("100"),
        p80_kg=Decimal("120"),
        p90_kg=Decimal("130"),
        cumulative_p50_kg=Decimal("100"),
        cumulative_p80_kg=Decimal("120"),
        cumulative_p90_kg=Decimal("130"),
        curve_share=Decimal("0.1"),
        confidence_level="medium",
        quality_flags=("ok",),
    )

    assert result.status == "completed"
    assert isinstance(prediction.p50_kg, Decimal)
