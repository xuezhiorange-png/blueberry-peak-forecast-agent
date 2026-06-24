from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.maturity.config import load_maturity_curve_config
from backend.app.maturity.schemas import (
    GroupCurveArtifact,
    MaturityDailyPrediction,
    MaturityManifestRow,
    MaturityModelExecutionResult,
    ResolvedTrainingSample,
    ShiftModelArtifact,
    TrainingDensityPoint,
)
from backend.app.maturity.service import (
    _artifact_payload,
    _build_group_curves,
    _build_shift_model,
    _calibration_payload,
    _forecast_axis_payload,
    _forecast_source_signature,
    _model_artifact_payload,
    _model_run_status_value,
    _predict_shift_days,
    _support_days,
    _training_source_signature,
)


def _config():
    repo_root = Path(__file__).resolve().parents[3]
    return load_maturity_curve_config(
        repo_root / "configs/maturity_curve.yaml"
    )


def _sample(
    *,
    season_code: str,
    climate_zone_id: int = 1,
    province: str = "Yunnan",
    variety_id: int = 1,
    facility_type: str = "open_field",
    altitude_m: Decimal | None = Decimal("1800"),
    tree_age_years: Decimal | None = Decimal("3"),
    pruning_offset_days: Decimal | None = Decimal("0"),
    flowering_peak_offset_days: Decimal | None = Decimal("36"),
    first_pick_offset_days: Decimal | None = Decimal("63"),
    proxy_peak_day: int = 5,
    sample_weight: Decimal = Decimal("1"),
    base_temperature: Decimal = Decimal("5"),
) -> ResolvedTrainingSample:
    manifest_row = MaturityManifestRow(
        season_id=1,
        analytics_build_run_id=101,
        farm_key=f"farm-{season_code}",
        farm_id=1,
        subfarm_key="__UNKNOWN_SUBFARM__",
        subfarm_id=None,
        variety_id=variety_id,
        location_reference_id=11,
        production_plan_id=201,
        base_temperature_search_run_id=301,
        anchor_event="flowering_start_date",
        facility_type=facility_type,
        include=True,
        sample_weight=sample_weight,
    )
    training_points = []
    for rel_day in range(0, 10):
        share = Decimal("0.05")
        if rel_day == proxy_peak_day:
            share = Decimal("0.55")
        training_points.append(
            TrainingDensityPoint(
                relative_day=rel_day,
                proxy_share=share,
                loss_weight=sample_weight,
                disturbance_reason=None,
                included_in_loss=True,
            )
        )
    return ResolvedTrainingSample(
        manifest_row=manifest_row,
        season_code=season_code,
        season_end_date=date(2026, 4, 30),
        climate_zone_id=climate_zone_id,
        province=province,
        altitude_m=altitude_m,
        tree_age_years=tree_age_years,
        anchor_date=date(2026, 2, 1),
        expected_total_kg=Decimal("96000"),
        expected_total_source="explicit",
        plan_id=201,
        plan_version=1,
        plan_row_hash=f"plan-{season_code}",
        plan_available_at=date(2025, 12, 1),
        plan_effective_from=date(2026, 1, 1),
        plan_effective_to=None,
        mapping_row_hash=f"mapping-{season_code}",
        location_reference_source_hash=f"loc-{season_code}",
        analytics_build_run_finished_at=date(2026, 4, 30),
        analytics_provenance={"build_run_id": 101},
        fact_row_fingerprint=(
            {
                "id": 1,
                "receipt_date": date(2026, 2, 1),
                "factory_id": 1,
                "farm_key": manifest_row.farm_key,
                "subfarm_key": manifest_row.subfarm_key,
                "variety_id": variety_id,
                "weight_kg": Decimal("100"),
                "source_row_count": 1,
                "holiday_codes": [],
                "is_spring_festival": False,
                "created_at": date(2026, 4, 30),
            },
        ),
        base_temperature_source_signature=f"base-temp-{climate_zone_id}-{variety_id}",
        base_temperature_training_cutoff=date(2026, 4, 30),
        base_temperature_feature_version="task7-v1",
        base_temperature_config_hash="weather-cfg",
        selected_base_temperature=base_temperature,
        observation_fingerprint=(
            {
                "observation_date": date(2026, 2, 1),
                "observation_id": 1,
                "row_hash": f"obs-{season_code}",
                "available_at": date(2026, 4, 30),
                "source_version": "v1",
                "weather_source_location_id": 99,
            },
        ),
        holiday_summary={},
        density_points=tuple(
            (item.relative_day, item.proxy_share) for item in training_points
        ),
        training_points=tuple(training_points),
        feature_values={
            "altitude_m": altitude_m,
            "tree_age_years": tree_age_years,
            "facility_type": facility_type,
            "pruning_offset_days": pruning_offset_days,
            "flowering_peak_offset_days": flowering_peak_offset_days,
            "first_pick_offset_days": first_pick_offset_days,
        },
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


def test_training_source_signature_changes_when_provenance_changes() -> None:
    manifest = [
        {
            "season_id": 1,
            "include": True,
            "sample_weight": Decimal("1"),
            "analytics_provenance": {"source_max_raw_id": 100},
            "fact_row_fingerprint": [{"id": 1, "receipt_date": date(2026, 2, 1)}],
        }
    ]

    signature_a = _training_source_signature(
        manifest_rows=manifest,
        training_cutoff=date(2026, 4, 30),
        config_hash="cfg",
        model_version="task8-v1",
        random_seed=20260624,
    )
    signature_b = _training_source_signature(
        manifest_rows=[
            {
                **manifest[0],
                "analytics_provenance": {"source_max_raw_id": 101},
            }
        ],
        training_cutoff=date(2026, 4, 30),
        config_hash="cfg",
        model_version="task8-v1",
        random_seed=20260624,
    )

    assert signature_a != signature_b


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
        "expected_marketable_total_kg": Decimal("96000"),
        "expected_total_source": "explicit",
        "facility_type": "open_field",
        "altitude_m": Decimal("1800"),
        "tree_age_years": Decimal("3"),
        "pruning_offset_days": Decimal("0"),
        "flowering_peak_offset_days": Decimal("36"),
        "first_pick_offset_days": Decimal("63"),
        "shift_feature_snapshot": {"facility_type": "open_field"},
        "predicted_shift_days": Decimal("0"),
        "selected_group_model_key": "zone:1|variety:1",
        "fallback_level": "climate_zone_variety",
        "axis_mode": "calendar_proxy_axis",
        "axis_snapshot": {"phase_correction_days": "0"},
        "plan_row_hash": "plan-a",
        "location_reference_source_hash": "loc-a",
        "base_temperature_context": {"zone:1|variety:1": {"run_id": 5}},
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


def test_forecast_source_signature_changes_when_total_or_facility_changes() -> None:
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
        "observation_fingerprint": [],
        "altitude_m": Decimal("1800"),
        "tree_age_years": Decimal("3"),
        "pruning_offset_days": Decimal("0"),
        "flowering_peak_offset_days": Decimal("36"),
        "first_pick_offset_days": Decimal("63"),
        "shift_feature_snapshot": {"facility_type": "open_field"},
        "predicted_shift_days": Decimal("0"),
        "selected_group_model_key": "zone:1|variety:1",
        "fallback_level": "climate_zone_variety",
        "axis_mode": "calendar_proxy_axis",
        "axis_snapshot": {"phase_correction_days": "0"},
        "plan_row_hash": "plan-a",
        "location_reference_source_hash": "loc-a",
        "base_temperature_context": {"zone:1|variety:1": {"run_id": 5}},
    }
    signature_a = _forecast_source_signature(
        expected_marketable_total_kg=Decimal("96000"),
        expected_total_source="explicit",
        facility_type="open_field",
        **common,
    )
    signature_b = _forecast_source_signature(
        expected_marketable_total_kg=Decimal("97000"),
        expected_total_source="explicit",
        facility_type="open_field",
        **common,
    )
    signature_c = _forecast_source_signature(
        expected_marketable_total_kg=Decimal("96000"),
        expected_total_source="explicit",
        facility_type="tunnel",
        **common,
    )
    signature_d = _forecast_source_signature(
        expected_marketable_total_kg=Decimal("96000"),
        expected_total_source="derived_from_task6_plan",
        facility_type="open_field",
        **common,
    )

    assert signature_a != signature_b
    assert signature_a != signature_c
    assert signature_a != signature_d


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


def test_disturbance_weight_changes_group_curve_artifact() -> None:
    config = _config()
    weighted = _sample(season_code="2026-2027")
    weighted_points = []
    for point in weighted.training_points:
        if point.relative_day == 5:
            weighted_points.append(
                replace(
                    point,
                    loss_weight=Decimal("0.5"),
                    disturbance_reason="spring_festival",
                )
            )
        else:
            weighted_points.append(point)
    weighted = replace(
        weighted,
        training_points=tuple(weighted_points),
        holiday_summary={
            "raw_day_count": 10,
            "used_day_count": 10,
            "downweighted_day_count": 1,
            "excluded_day_count": 0,
        },
    )
    unweighted = replace(
        weighted,
        training_points=tuple(replace(item, loss_weight=Decimal("1")) for item in weighted_points),
    )
    reference = _sample(season_code="2025-2026", proxy_peak_day=4)

    weighted_artifacts, _ = _build_group_curves(
        resolved_samples=[weighted, reference],
        config=config,
    )
    unweighted_artifacts, _ = _build_group_curves(
        resolved_samples=[unweighted, reference],
        config=config,
    )

    assert (
        weighted_artifacts["zone:1|variety:1"].density
        != unweighted_artifacts["zone:1|variety:1"].density
    )


def test_shift_model_learns_altitude_direction_when_samples_are_sufficient() -> None:
    config = _config()
    support_days = _support_days(config)
    parent_artifact = GroupCurveArtifact(
        group_key="variety:1",
        level="variety_global",
        density=tuple(Decimal("0.6") if day == 5 else Decimal("0.05") for day in support_days),
        peak_day=Decimal("5.000000"),
        sample_count=4,
        distinct_season_count=4,
        distinct_farm_count=4,
        distinct_subfarm_count=1,
        parent_group_key=None,
        shrinkage=Decimal("1.000000"),
    )
    artifacts = {
        "variety:1": parent_artifact,
        "province:Yunnan|variety:1": replace(
            parent_artifact,
            group_key="province:Yunnan|variety:1",
            parent_group_key="variety:1",
        ),
        "zone:1|variety:1": replace(
            parent_artifact,
            group_key="zone:1|variety:1",
            parent_group_key="province:Yunnan|variety:1",
        ),
    }
    low_alt = _sample(season_code="2024-2025", altitude_m=Decimal("1700"), proxy_peak_day=4)
    high_alt = _sample(season_code="2025-2026", altitude_m=Decimal("1900"), proxy_peak_day=6)
    high_alt_2 = _sample(season_code="2026-2027", altitude_m=Decimal("2000"), proxy_peak_day=7)
    low_alt_2 = _sample(season_code="2027-2028", altitude_m=Decimal("1600"), proxy_peak_day=3)

    shift_model = _build_shift_model(
        resolved_samples=[low_alt, high_alt, high_alt_2, low_alt_2],
        artifacts=artifacts,
        config=config,
    )

    assert shift_model.enabled is True
    assert shift_model.feature_order
    predicted_low = _predict_shift_days(
        shift_model=shift_model,
        feature_values=low_alt.feature_values,
    )
    predicted_high = _predict_shift_days(
        shift_model=shift_model,
        feature_values=high_alt_2.feature_values,
    )
    assert predicted_high > predicted_low


def test_calibration_payload_uses_holdout_seasons() -> None:
    config = _config()
    support_days = _support_days(config)
    artifacts = {
        "variety:1": GroupCurveArtifact(
            group_key="variety:1",
            level="variety_global",
            density=tuple(Decimal("0.5") if day == 5 else Decimal("0.05") for day in support_days),
            peak_day=Decimal("5.000000"),
            sample_count=2,
            distinct_season_count=2,
            distinct_farm_count=2,
            distinct_subfarm_count=1,
            parent_group_key=None,
            shrinkage=Decimal("1.000000"),
        )
    }
    payload = _calibration_payload(
        resolved_samples=[
            _sample(season_code="2024-2025", proxy_peak_day=4),
            _sample(season_code="2025-2026", proxy_peak_day=6),
        ],
        artifacts=artifacts,
        config=config,
    )

    assert payload["interval_semantics"] == "pointwise_marginal"
    assert set(payload["held_out_seasons"]) == {"2024-2025", "2025-2026"}
    assert payload["fold_count"] == 2


def test_model_artifact_payload_keys_base_temperature_by_zone_and_variety() -> None:
    config = _config()
    payload = _model_artifact_payload(
        config=config,
        artifacts={},
        shift_model=ShiftModelArtifact(
            enabled=False,
            intercept_days=Decimal("0"),
            coefficients={},
            category_vocabulary={"facility_type": ("open_field", "unknown")},
            reference_categories={"facility_type": "open_field"},
            feature_order=(),
            scaler_center={},
            scaler_scale={},
            feature_units={},
            missing_value_rules={},
            bounds=(Decimal("-7"), Decimal("7")),
            warnings=(),
        ),
        calibration={
            "p80_margin_share": Decimal("0.1"),
            "p90_margin_share": Decimal("0.2"),
            "warnings": [],
            "interval_semantics": "pointwise_marginal",
            "held_out_seasons": [],
            "fold_count": 0,
        },
        anchor_event="flowering_start_date",
        base_temperature_context={
            "zone:1|variety:1": {
                "run_id": 1,
                "selected_base_temperature": Decimal("4"),
                "feature_version": "task7-v1",
                "config_hash": "weather-cfg",
            },
            "zone:1|variety:2": {
                "run_id": 2,
                "selected_base_temperature": Decimal("6"),
                "feature_version": "task7-v1",
                "config_hash": "weather-cfg",
            },
        },
    )

    assert "zone:1|variety:1" in payload["base_temperature_context"]
    assert "zone:1|variety:2" in payload["base_temperature_context"]


def test_forecast_axis_payload_uses_observed_mode_only_with_complete_history() -> None:
    axis_mode, axis_snapshot, coordinates, warnings = _forecast_axis_payload(
        anchor_date=date(2026, 3, 1),
        as_of_date=date(2026, 3, 3),
        prediction_dates=[date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)],
        base_temperature=Decimal("5"),
        observations_by_date={
            date(2026, 3, 1): type("Obs", (), {"temperature_mean_c": Decimal("8")})(),
            date(2026, 3, 2): type("Obs", (), {"temperature_mean_c": Decimal("9")})(),
            date(2026, 3, 3): type("Obs", (), {"temperature_mean_c": Decimal("10")})(),
        },
    )

    assert axis_mode == "observed_phenology_axis"
    assert warnings == []
    assert axis_snapshot["axis_provenance"] == "observed_weather_complete"
    assert coordinates[date(2026, 3, 3)] == Decimal("12.000000")


def test_forecast_axis_payload_falls_back_when_history_is_incomplete() -> None:
    axis_mode, axis_snapshot, coordinates, warnings = _forecast_axis_payload(
        anchor_date=date(2026, 3, 1),
        as_of_date=date(2026, 3, 3),
        prediction_dates=[date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)],
        base_temperature=Decimal("5"),
        observations_by_date={
            date(2026, 3, 1): type("Obs", (), {"temperature_mean_c": Decimal("8")})(),
            date(2026, 3, 3): type("Obs", (), {"temperature_mean_c": Decimal("10")})(),
        },
    )

    assert axis_mode == "calendar_proxy_axis"
    assert "anchor_weather_incomplete" in warnings
    assert axis_snapshot["coverage_ratio"] == Decimal("0.666667")
    assert axis_snapshot["axis_provenance"] == "calendar_proxy_from_observed_prefix"
    assert coordinates[date(2026, 3, 3)] != Decimal("2")


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
