from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.maturity.config import load_maturity_curve_config
from backend.app.maturity.model import reconcile_p50_mass
from backend.app.maturity.reporting import write_model_reports
from backend.app.maturity.schemas import (
    MaturityManifestRow,
    MaturityModelExecutionResult,
    ResolvedTrainingSample,
    TrainingDensityPoint,
)
from backend.app.maturity.service import (
    _build_group_curves,
    _build_shift_model,
    _calibration_payload,
    _forecast_axis_payload,
    _model_artifact_payload,
    _predict_shift_days,
    _support_days,
)
from backend.app.models.planning import Base


def _config():
    repo_root = Path(__file__).resolve().parents[3]
    return load_maturity_curve_config(repo_root / "configs/maturity_curve.yaml")


def _golden_sample(
    *,
    season_code: str,
    season_id: int,
    farm_id: int,
    subfarm_id: int | None,
    subfarm_key: str,
    climate_zone_id: int,
    province: str,
    variety_id: int,
    facility_type: str,
    altitude_m: Decimal,
    proxy_peak_day: int,
    base_temperature: Decimal,
) -> ResolvedTrainingSample:
    manifest_row = MaturityManifestRow(
        season_id=season_id,
        analytics_build_run_id=1000 + season_id,
        farm_key=f"farm-{farm_id}",
        farm_id=farm_id,
        subfarm_key=subfarm_key,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
        location_reference_id=500 + farm_id,
        production_plan_id=700 + season_id,
        base_temperature_search_run_id=900 + climate_zone_id + variety_id,
        anchor_event="flowering_start_date",
        facility_type=facility_type,
        include=True,
        sample_weight=Decimal("1"),
    )
    training_points = []
    for rel_day in range(0, 12):
        share = Decimal("0.03")
        if rel_day == proxy_peak_day:
            share = Decimal("0.55")
        elif rel_day in {proxy_peak_day - 1, proxy_peak_day + 1}:
            share = Decimal("0.12")
        training_points.append(
            TrainingDensityPoint(
                relative_day=rel_day,
                proxy_share=share,
                loss_weight=Decimal("1"),
                disturbance_reason="spring_festival" if rel_day == proxy_peak_day + 1 else None,
                included_in_loss=True,
            )
        )
    return ResolvedTrainingSample(
        manifest_row=manifest_row,
        season_code=season_code,
        season_end_date=date(int(season_code[:4]) + 1, 4, 30),
        climate_zone_id=climate_zone_id,
        province=province,
        altitude_m=altitude_m,
        tree_age_years=Decimal("3"),
        anchor_date=date(int(season_code[:4]) + 1, 2, 1),
        expected_total_kg=Decimal("96000"),
        expected_total_source="explicit",
        plan_id=700 + season_id,
        plan_version=1,
        plan_row_hash=f"plan-{season_code}-{farm_id}",
        plan_available_at=date(int(season_code[:4]), 12, 1),
        plan_effective_from=date(int(season_code[:4]) + 1, 1, 1),
        plan_effective_to=None,
        mapping_row_hash=f"mapping-{climate_zone_id}-{farm_id}",
        location_reference_source_hash=f"loc-{farm_id}-{subfarm_key}",
        analytics_build_run_finished_at=date(int(season_code[:4]) + 1, 4, 30),
        analytics_provenance={"source_max_raw_id": 100 + season_id},
        fact_row_fingerprint=(
            {
                "id": season_id,
                "receipt_date": date(int(season_code[:4]) + 1, 2, 1),
                "factory_id": 1,
                "farm_key": manifest_row.farm_key,
                "subfarm_key": manifest_row.subfarm_key,
                "variety_id": variety_id,
                "weight_kg": Decimal("100"),
                "source_row_count": 1,
                "holiday_codes": ["spring_festival"],
                "is_spring_festival": True,
                "created_at": date(int(season_code[:4]) + 1, 4, 30),
            },
        ),
        base_temperature_source_signature=f"bt-{climate_zone_id}-{variety_id}",
        base_temperature_training_cutoff=date(int(season_code[:4]) + 1, 4, 30),
        base_temperature_feature_version="task7-v1",
        base_temperature_config_hash="weather-cfg",
        selected_base_temperature=base_temperature,
        reference_effective_temperature_per_day=Decimal("4.500000"),
        observation_fingerprint=(
            {
                "observation_date": date(int(season_code[:4]) + 1, 2, 1),
                "observation_id": season_id,
                "row_hash": f"obs-{season_code}-{farm_id}",
                "available_at": date(int(season_code[:4]) + 1, 4, 30),
                "source_version": f"wx-{season_code}",
                "weather_source_location_id": 300 + climate_zone_id,
            },
        ),
        holiday_summary={
            "raw_day_count": 12,
            "used_day_count": 12,
            "downweighted_day_count": 1,
            "excluded_day_count": 0,
            "raw_proxy_weight": Decimal("1"),
            "effective_training_weight": Decimal("11.5"),
            "downweighted_weight_share": Decimal("0.043478"),
            "excluded_reason_codes": [],
            "reason_code_breakdown": {"spring_festival": 1},
        },
        density_points=tuple((item.relative_day, item.proxy_share) for item in training_points),
        training_points=tuple(training_points),
        feature_values={
            "altitude_m": altitude_m,
            "tree_age_years": Decimal("3"),
            "facility_type_raw": facility_type,
            "facility_type": facility_type,
            "pruning_offset_days": Decimal("0"),
            "flowering_peak_offset_days": Decimal("36"),
            "first_pick_offset_days": Decimal("63"),
        },
    )


def _golden_samples() -> list[ResolvedTrainingSample]:
    return [
        _golden_sample(
            season_code="2024-2025",
            season_id=1,
            farm_id=1,
            subfarm_id=11,
            subfarm_key="sf-11",
            climate_zone_id=1,
            province="Yunnan",
            variety_id=1,
            facility_type="open_field",
            altitude_m=Decimal("1700"),
            proxy_peak_day=4,
            base_temperature=Decimal("4"),
        ),
        _golden_sample(
            season_code="2025-2026",
            season_id=2,
            farm_id=2,
            subfarm_id=22,
            subfarm_key="sf-22",
            climate_zone_id=1,
            province="Yunnan",
            variety_id=1,
            facility_type="tunnel",
            altitude_m=Decimal("1900"),
            proxy_peak_day=7,
            base_temperature=Decimal("4"),
        ),
        _golden_sample(
            season_code="2026-2027",
            season_id=3,
            farm_id=3,
            subfarm_id=33,
            subfarm_key="sf-33",
            climate_zone_id=1,
            province="Yunnan",
            variety_id=1,
            facility_type="tunnel",
            altitude_m=Decimal("2000"),
            proxy_peak_day=8,
            base_temperature=Decimal("4"),
        ),
        _golden_sample(
            season_code="2024-2025",
            season_id=4,
            farm_id=4,
            subfarm_id=44,
            subfarm_key="sf-44",
            climate_zone_id=2,
            province="Sichuan",
            variety_id=1,
            facility_type="open_field",
            altitude_m=Decimal("1600"),
            proxy_peak_day=5,
            base_temperature=Decimal("5"),
        ),
        _golden_sample(
            season_code="2025-2026",
            season_id=5,
            farm_id=4,
            subfarm_id=45,
            subfarm_key="sf-45",
            climate_zone_id=2,
            province="Sichuan",
            variety_id=1,
            facility_type="open_field",
            altitude_m=Decimal("1650"),
            proxy_peak_day=5,
            base_temperature=Decimal("5"),
        ),
        _golden_sample(
            season_code="2024-2025",
            season_id=6,
            farm_id=5,
            subfarm_id=55,
            subfarm_key="sf-55",
            climate_zone_id=1,
            province="Yunnan",
            variety_id=2,
            facility_type="open_field",
            altitude_m=Decimal("1750"),
            proxy_peak_day=6,
            base_temperature=Decimal("6"),
        ),
        _golden_sample(
            season_code="2025-2026",
            season_id=7,
            farm_id=6,
            subfarm_id=66,
            subfarm_key="sf-66",
            climate_zone_id=1,
            province="Yunnan",
            variety_id=2,
            facility_type="unknown",
            altitude_m=Decimal("1800"),
            proxy_peak_day=6,
            base_temperature=Decimal("6"),
        ),
    ]


def test_maturity_golden_order_invariance_and_mass_conservation() -> None:
    config = _config()
    samples = _golden_samples()

    artifacts_a, metrics_a = _build_group_curves(
        resolved_samples=samples,
        config=config,
    )
    artifacts_b, metrics_b = _build_group_curves(
        resolved_samples=list(reversed(samples)),
        config=config,
    )

    assert artifacts_a["zone:1|variety:1"].density == artifacts_b["zone:1|variety:1"].density
    assert metrics_a["reference_phase_rates"] == metrics_b["reference_phase_rates"]
    assert sum(artifacts_a["zone:1|variety:1"].density, Decimal("0")).quantize(
        Decimal("0.000001")
    ) == Decimal("1.000000")
    assert all(value >= 0 for value in artifacts_a["zone:1|variety:1"].density)
    daily_p50 = reconcile_p50_mass(
        expected_total_kg=Decimal("96000"),
        density=artifacts_a["zone:1|variety:1"].density,
    )
    assert sum(daily_p50, Decimal("0")) == Decimal("96000.000000")


def test_maturity_golden_shift_direction_and_sparse_group_fallback() -> None:
    config = _config()
    stricter = replace(
        config,
        rules=replace(
            config.rules,
            pooling=replace(
                config.rules.pooling,
                minimum_samples=3,
                minimum_seasons=3,
                minimum_farms=3,
                minimum_subfarms=3,
            ),
        ),
    )
    samples = _golden_samples()
    artifacts, metrics = _build_group_curves(
        resolved_samples=samples,
        config=stricter,
    )
    shift_model = _build_shift_model(
        resolved_samples=samples,
        artifacts=artifacts,
        config=stricter,
    )

    assert shift_model.enabled is True
    low_shift = _predict_shift_days(
        shift_model=shift_model,
        feature_values=samples[0].feature_values,
    )
    high_shift = _predict_shift_days(
        shift_model=shift_model,
        feature_values=samples[2].feature_values,
    )
    assert high_shift > low_shift
    assert artifacts["zone:2|variety:1"].fallback_reason == "insufficient_training_samples"
    assert artifacts["zone:2|variety:1"].density == artifacts["province:Sichuan|variety:1"].density
    assert "variety:2" not in artifacts
    assert metrics["group_levels"]["variety:2"]["available"] is False
    assert (
        metrics["group_levels"]["variety:2"]["fallback_reason"] == "insufficient_training_samples"
    )
    assert (
        metrics["group_levels"]["zone:1|variety:2"]["fallback_reason"] == "parent_group_unavailable"
    )


def test_maturity_golden_observed_axis_hot_cold_bounds_and_proxy_fallback() -> None:
    hot_mode, hot_snapshot, hot_coordinates, _ = _forecast_axis_payload(
        anchor_date=date(2026, 3, 1),
        as_of_date=date(2026, 3, 3),
        prediction_dates=[date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)],
        base_temperature=Decimal("5"),
        observations_by_date={
            date(2026, 3, 1): type("Obs", (), {"temperature_mean_c": Decimal("13")})(),
            date(2026, 3, 2): type("Obs", (), {"temperature_mean_c": Decimal("14")})(),
            date(2026, 3, 3): type("Obs", (), {"temperature_mean_c": Decimal("15")})(),
        },
        reference_effective_temperature_per_day=Decimal("4"),
        support_min_day=-30,
        support_max_day=7,
        maximum_abs_adjustment_days=Decimal("2"),
        minimum_observed_axis_coverage_ratio=Decimal("1"),
    )
    cold_mode, _, cold_coordinates, _ = _forecast_axis_payload(
        anchor_date=date(2026, 3, 1),
        as_of_date=date(2026, 3, 3),
        prediction_dates=[date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)],
        base_temperature=Decimal("5"),
        observations_by_date={
            date(2026, 3, 1): type("Obs", (), {"temperature_mean_c": Decimal("6")})(),
            date(2026, 3, 2): type("Obs", (), {"temperature_mean_c": Decimal("6")})(),
            date(2026, 3, 3): type("Obs", (), {"temperature_mean_c": Decimal("6")})(),
        },
        reference_effective_temperature_per_day=Decimal("4"),
        support_min_day=-30,
        support_max_day=7,
        maximum_abs_adjustment_days=Decimal("2"),
        minimum_observed_axis_coverage_ratio=Decimal("1"),
    )
    proxy_mode, proxy_snapshot, _, proxy_warnings = _forecast_axis_payload(
        anchor_date=date(2026, 3, 1),
        as_of_date=date(2026, 3, 3),
        prediction_dates=[date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)],
        base_temperature=Decimal("5"),
        observations_by_date={
            date(2026, 3, 1): type("Obs", (), {"temperature_mean_c": Decimal("13")})(),
            date(2026, 3, 3): type("Obs", (), {"temperature_mean_c": Decimal("15")})(),
        },
        reference_effective_temperature_per_day=Decimal("4"),
        support_min_day=-30,
        support_max_day=7,
        maximum_abs_adjustment_days=Decimal("2"),
        minimum_observed_axis_coverage_ratio=Decimal("1"),
    )

    assert hot_mode == "observed_phenology_axis"
    assert cold_mode == "observed_phenology_axis"
    assert hot_snapshot["coordinate_unit"] == "day"
    assert hot_coordinates[date(2026, 3, 3)] > Decimal("2.000000")
    assert cold_coordinates[date(2026, 3, 3)] < Decimal("2.000000")
    assert abs(hot_snapshot["bounded_phase_adjustment_days"]) <= Decimal("2.000000")
    assert proxy_mode == "calendar_proxy_axis"
    assert "anchor_weather_incomplete" in proxy_warnings
    assert proxy_snapshot["axis_provenance"] == "calendar_proxy_from_observed_prefix"


def test_maturity_golden_calibration_and_base_temperature_context_are_separated() -> None:
    config = _config()
    samples = _golden_samples()
    artifacts, metrics = _build_group_curves(
        resolved_samples=samples,
        config=config,
    )
    shift_model = _build_shift_model(
        resolved_samples=samples,
        artifacts=artifacts,
        config=config,
    )
    calibration = _calibration_payload(
        resolved_samples=samples,
        artifacts=artifacts,
        config=config,
    )
    payload = _model_artifact_payload(
        config=config,
        artifacts=artifacts,
        group_audit=metrics["group_levels"],
        shift_model=shift_model,
        calibration=calibration,
        anchor_event="flowering_start_date",
        base_temperature_context={
            "zone:1|variety:1": {
                "run_id": 101,
                "selected_base_temperature": Decimal("4"),
                "feature_version": "task7-v1",
                "config_hash": "weather-cfg",
            },
            "zone:1|variety:2": {
                "run_id": 202,
                "selected_base_temperature": Decimal("6"),
                "feature_version": "task7-v1",
                "config_hash": "weather-cfg",
            },
        },
        reference_phase_rates=metrics["reference_phase_rates"],
    )

    assert payload["base_temperature_context"]["zone:1|variety:1"][
        "selected_base_temperature"
    ] == Decimal("4")
    assert payload["base_temperature_context"]["zone:1|variety:2"][
        "selected_base_temperature"
    ] == Decimal("6")
    assert calibration["interval_semantics"] == "pointwise_marginal"
    assert set(calibration["held_out_seasons"]) >= {"2024-2025", "2025-2026", "2026-2027"}
    assert calibration["p80_margin_share"] >= Decimal("0")
    assert calibration["p90_margin_share"] >= calibration["p80_margin_share"]
    support_days = _support_days(config)
    assert artifacts["zone:1|variety:1"].peak_day in {
        Decimal(str(day)).quantize(Decimal("0.000001")) for day in support_days
    }


def test_maturity_golden_reports_include_representative_values(tmp_path: Path) -> None:
    config = _config()
    samples = _golden_samples()
    artifacts, metrics = _build_group_curves(
        resolved_samples=samples,
        config=config,
    )
    shift_model = _build_shift_model(
        resolved_samples=samples,
        artifacts=artifacts,
        config=config,
    )
    calibration = _calibration_payload(
        resolved_samples=samples,
        artifacts=artifacts,
        config=config,
    )
    artifact_payload = _model_artifact_payload(
        config=config,
        artifacts=artifacts,
        group_audit=metrics["group_levels"],
        shift_model=shift_model,
        calibration=calibration,
        anchor_event="flowering_start_date",
        base_temperature_context={
            "zone:1|variety:1": {
                "run_id": 101,
                "selected_base_temperature": Decimal("4"),
                "feature_version": "task7-v1",
                "config_hash": "weather-cfg",
            }
        },
        reference_phase_rates=metrics["reference_phase_rates"],
    )
    result = MaturityModelExecutionResult(
        status="completed",
        run_id=77,
        source_signature="golden-sig",
        config_hash=config.config_hash,
        model_version=config.rules.curve.version,
        model_family=config.rules.model_family,
        sample_count=len(samples),
        distinct_season_count=len({item.season_code for item in samples}),
        distinct_farm_count=len({item.manifest_row.farm_id for item in samples}),
        distinct_subfarm_count=len(
            {(item.manifest_row.farm_id, item.manifest_row.subfarm_key) for item in samples}
        ),
        warnings=(),
        blockers=(),
        training_metrics=metrics,
        calibration_metrics=calibration,
        artifact=artifact_payload,
        input_snapshot={
            "training_cutoff": date(2026, 4, 30),
            "artifact_hash": "golden-artifact",
            "config_snapshot": config.snapshot,
            "random_seed": config.rules.random_seed,
            "code_version": "golden-sha",
            "base_temperature_context": artifact_payload["base_temperature_context"],
            "manifest_rows": [
                {
                    "status": "included",
                    "season_code": item.season_code,
                    "analytics_provenance": item.analytics_provenance,
                    "plan_row_hash": item.plan_row_hash,
                    "base_temperature_run": {
                        "run_id": item.manifest_row.base_temperature_search_run_id
                    },
                    "holiday_summary": item.holiday_summary,
                }
                for item in samples
            ],
            "leakage_checks": {
                "fact_visibility": {
                    "status": "warn",
                    "checked_row_count": len(samples) + 1,
                    "passed_row_count": len(samples),
                    "excluded_row_count": 1,
                    "failed_row_count": 0,
                    "reason_code_breakdown": {"fact_rows_not_visible_at_cutoff": 1},
                    "affected_manifest_rows": [
                        {
                            "index": 99,
                            "season_id": 99,
                            "season_code": "2027-2028",
                            "farm_id": 99,
                            "farm_key": "farm-leak",
                            "subfarm_id": None,
                            "subfarm_key": "__UNKNOWN_SUBFARM__",
                            "variety_id": 1,
                            "production_plan_id": 999,
                            "analytics_build_run_id": 999,
                            "resolved_exclusion_reason": "fact_rows_not_visible_at_cutoff",
                        }
                    ],
                }
            },
        },
    )

    json_path, markdown_path = write_model_reports(result, output_dir=tmp_path)
    json_text = json_path.read_text(encoding="utf-8")
    markdown_text = markdown_path.read_text(encoding="utf-8")
    assert "zone:1|variety:1" in json_text
    assert "province:Yunnan|variety:1" in markdown_text
    assert "shrinkage=" in markdown_text
    assert "coefficients:" in markdown_text
    assert "pointwise_p80_coverage" in markdown_text
    assert "source_max_raw_id=" in markdown_text
    assert '"status": "warn"' in json_text
    assert '"fact_rows_not_visible_at_cutoff": 1' in json_text
    assert "fact_visibility: status=warn" in markdown_text
    assert "checked=8" in markdown_text
    assert "excluded=1" in markdown_text
    assert "zone:1|variety:1" in markdown_text
    assert "available=True" in markdown_text
    assert "variety:2" in markdown_text
    assert "reference_phase_rates" in markdown_text
    assert "golden-artifact" in markdown_text


def test_maturity_golden_forbidden_task9_tables_absent() -> None:
    forbidden_tables = {
        "harvest_capacity_run",
        "harvest_capacity_daily",
        "arrival_state_run",
        "arrival_state_daily",
        "maturity_backlog_run",
        "maturity_backlog_daily",
        "factory_peak_forecast_run",
    }
    assert forbidden_tables.isdisjoint(Base.metadata.tables)


def test_maturity_golden_order_invariance_preserves_reference_phase_rates_and_calibration() -> None:
    config = _config()
    samples = _golden_samples()

    artifacts_a, metrics_a = _build_group_curves(
        resolved_samples=samples,
        config=config,
    )
    artifacts_b, metrics_b = _build_group_curves(
        resolved_samples=list(reversed(samples)),
        config=config,
    )
    calibration_a = _calibration_payload(
        resolved_samples=samples,
        artifacts=artifacts_a,
        config=config,
    )
    calibration_b = _calibration_payload(
        resolved_samples=list(reversed(samples)),
        artifacts=artifacts_b,
        config=config,
    )

    assert metrics_a["reference_phase_rates"] == metrics_b["reference_phase_rates"]
    assert calibration_a == calibration_b
