from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.maturity.reporting import write_forecast_reports, write_model_reports
from backend.app.maturity.schemas import (
    MaturityDailyPrediction,
    MaturityForecastExecutionResult,
    MaturityModelExecutionResult,
)


def test_write_model_reports_creates_json_and_markdown(tmp_path: Path) -> None:
    result = MaturityModelExecutionResult(
        status="completed",
        run_id=11,
        source_signature="train-sig",
        config_hash="cfg",
        model_version="task8-v1",
        model_family="shared_spline_partial_pooling",
        sample_count=4,
        distinct_season_count=2,
        distinct_farm_count=2,
        distinct_subfarm_count=1,
        warnings=("proxy_label",),
        blockers=(),
        training_metrics={"wmape": Decimal("0.123456")},
        calibration_metrics={
            "pointwise_p80_coverage": Decimal("0.8"),
            "pointwise_p90_coverage": Decimal("0.9"),
            "interval_semantics": "pointwise_marginal",
            "held_out_seasons": ["2025-2026"],
            "fold_count": 1,
            "peak_date_mae_days": Decimal("1.500000"),
            "curve_wmape": Decimal("0.123456"),
        },
        artifact={
            "support_days": [0, 1, 2],
            "reference_phase_rates": {
                "zone:1|variety:1": {
                    "effective_temperature_per_day": "4.200000",
                    "sample_count": 2,
                }
            },
            "phase_adjustment_bounds_days": ["-14", "14"],
            "group_models": {
                "zone:1|variety:1": {
                    "level": "climate_zone_variety",
                    "sample_count": 4,
                    "distinct_season_count": 2,
                    "distinct_farm_count": 2,
                    "distinct_subfarm_count": 1,
                    "parent_group_key": "province:Yunnan|variety:1",
                    "shrinkage": "0.500000",
                    "peak_day": "1.000000",
                    "fallback_reason": None,
                    "warnings": [],
                }
            },
            "shift_model": {
                "enabled": True,
                "intercept_days": "0.250000",
                "feature_order": ["altitude_m"],
                "coefficients": {"altitude_m": "0.100000"},
                "scaler_center": {"altitude_m": "1800.000000"},
                "scaler_scale": {"altitude_m": "100.000000"},
                "feature_units": {"altitude_m": "m"},
                "reference_categories": {"facility_type": "open_field"},
                "category_vocabulary": {"facility_type": ["open_field", "unknown"]},
                "missing_value_rules": {"altitude_m": "mean_impute"},
                "bounds": ["-14", "14"],
            },
            "calibration": {
                "interval_semantics": "pointwise_marginal",
                "pointwise_p80_coverage": "0.800000",
            },
        },
        input_snapshot={
            "training_cutoff": date(2026, 4, 30),
            "artifact_hash": "artifact-hash-1",
            "random_seed": 20260624,
            "code_version": "deadbeef",
            "config_snapshot": {
                "curve": {"spline_degree": 3, "spline_knot_count": 6, "ridge_alpha": "0.10"},
                "pooling": {
                    "minimum_samples": 2,
                    "minimum_seasons": 2,
                    "minimum_farms": 1,
                    "minimum_subfarms": 1,
                    "full_pooling_sample_target": 4,
                },
            },
            "leakage_checks": {
                "analytics_completed_finished_visibility": "pass",
                "fact_visibility": "pass",
            },
            "base_temperature_context": {"zone:1|variety:1": {"run_id": 301}},
            "manifest_rows": [
                {
                    "status": "included",
                    "include": True,
                    "season_code": "2025-2026",
                    "plan_row_hash": "plan-hash-1",
                    "analytics_provenance": {"source_max_raw_id": 200},
                    "base_temperature_run": {"run_id": 301},
                    "holiday_summary": {
                        "raw_day_count": 10,
                        "used_day_count": 9,
                        "downweighted_day_count": 1,
                        "excluded_day_count": 0,
                        "raw_proxy_weight": "1000.000000",
                        "effective_training_weight": "900.000000",
                        "reason_code_breakdown": {"spring_festival": 1},
                    },
                },
                {
                    "status": "excluded",
                    "include": False,
                    "season_code": "2024-2025",
                    "resolved_exclusion_reason": "manual",
                },
            ],
        },
    )

    json_path, markdown_path = write_model_reports(result, output_dir=tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    json_text = json_path.read_text(encoding="utf-8")
    markdown_text = markdown_path.read_text(encoding="utf-8")
    assert '"wmape": "0.123456"' in json_text
    assert '"label_proxy"' in json_text
    assert '"manifest_audit"' in json_text
    assert '"hierarchy"' in json_text
    assert '"reproducibility"' in json_text
    assert '"reference_phase_rates"' in json_text
    assert '"artifact_hash": "artifact-hash-1"' in json_text
    assert "# Maturity Model Report" in markdown_text
    assert "## Proxy Label" in markdown_text
    assert "## Manifest Audit" in markdown_text
    assert "## Hierarchy" in markdown_text
    assert "## Calibration" in markdown_text
    assert "group_key=zone:1|variety:1" in markdown_text
    assert "parent_group=province:Yunnan|variety:1" in markdown_text
    assert "shrinkage=0.500000" in markdown_text
    assert "coefficients: {'altitude_m': '0.100000'}" in markdown_text
    assert "scaler_center: {'altitude_m': '1800.000000'}" in markdown_text
    assert "peak_date_mae_days: 1.500000" in markdown_text
    assert "curve_wmape: 0.123456" in markdown_text
    assert "held_out_seasons: ['2025-2026']" in markdown_text
    assert "source_max_raw_id=200" in markdown_text
    assert "plan_row_hash=plan-hash-1" in markdown_text
    assert "base_temperature_run_id=301" in markdown_text
    assert "random_seed: 20260624" in markdown_text
    assert "code_version: deadbeef" in markdown_text
    assert "analytics_completed_finished_visibility: pass" in markdown_text


def test_write_forecast_reports_creates_json_and_markdown(tmp_path: Path) -> None:
    result = MaturityForecastExecutionResult(
        status="completed",
        run_id=22,
        model_run_id=11,
        source_signature="forecast-sig",
        config_hash="cfg",
        model_version="task8-v1",
        axis_mode="calendar_proxy_axis",
        expected_marketable_total_kg=Decimal("96000"),
        expected_total_source="explicit",
        daily_predictions=(
            MaturityDailyPrediction(
                prediction_date=date(2026, 3, 1),
                phenology_coordinate_day=Decimal("0"),
                p50_kg=Decimal("100"),
                p80_kg=Decimal("120"),
                p90_kg=Decimal("140"),
                cumulative_p50_kg=Decimal("100"),
                cumulative_p80_kg=Decimal("120"),
                cumulative_p90_kg=Decimal("140"),
                curve_share=Decimal("0.1"),
                confidence_level="medium",
                quality_flags=("calendar_proxy_axis",),
            ),
        ),
        warnings=("calendar_proxy_axis",),
        blockers=(),
        input_snapshot={"prediction_start_date": date(2026, 3, 1)},
    )

    json_path, markdown_path = write_forecast_reports(result, output_dir=tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    assert '"expected_marketable_total_kg": "96000"' in json_path.read_text(
        encoding="utf-8"
    )
    assert "# Natural Maturity Forecast Report" in markdown_path.read_text(
        encoding="utf-8"
    )
