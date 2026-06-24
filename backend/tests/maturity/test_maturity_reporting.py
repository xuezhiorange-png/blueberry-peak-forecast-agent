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
            "interval_semantics": "pointwise_marginal",
        },
        artifact={
            "support_days": [0, 1, 2],
            "group_models": {
                "zone:1|variety:1": {
                    "level": "climate_zone_variety",
                    "sample_count": 4,
                    "distinct_season_count": 2,
                    "distinct_farm_count": 2,
                    "distinct_subfarm_count": 1,
                    "parent_group_key": "province:Yunnan|variety:1",
                    "shrinkage": "0.500000",
                    "warnings": [],
                }
            },
            "shift_model": {
                "enabled": True,
                "coefficients": {"altitude_m": "0.100000"},
                "feature_units": {"altitude_m": "m"},
            },
            "calibration": {
                "interval_semantics": "pointwise_marginal",
                "pointwise_p80_coverage": "0.800000",
            },
        },
        input_snapshot={
            "training_cutoff": date(2026, 4, 30),
            "manifest_rows": [
                {
                    "include": True,
                    "season_code": "2025-2026",
                    "holiday_summary": {
                        "raw_day_count": 10,
                        "used_day_count": 9,
                        "downweighted_day_count": 1,
                        "excluded_day_count": 0,
                    },
                },
                {
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
    assert "# Maturity Model Report" in markdown_text
    assert "## Proxy Label" in markdown_text
    assert "## Manifest Audit" in markdown_text
    assert "## Hierarchy" in markdown_text
    assert "## Calibration" in markdown_text


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
