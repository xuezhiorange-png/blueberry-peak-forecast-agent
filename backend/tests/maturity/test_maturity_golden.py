from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.maturity.config import load_maturity_curve_config
from backend.app.maturity.schemas import (
    MaturityManifestRow,
    ResolvedTrainingSample,
    TrainingDensityPoint,
)
from backend.app.maturity.service import (
    _build_group_curves,
    _build_shift_model,
    _calibration_payload,
    _model_artifact_payload,
    _predict_shift_days,
    _support_days,
)


def _config():
    repo_root = Path(__file__).resolve().parents[3]
    return load_maturity_curve_config(
        repo_root / "configs/maturity_curve.yaml"
    )


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
    assert (
        sum(artifacts_a["zone:1|variety:1"].density, Decimal("0")).quantize(
            Decimal("0.000001")
        )
        == Decimal("1.000000")
    )
    assert all(value >= 0 for value in artifacts_a["zone:1|variety:1"].density)


def test_maturity_golden_shift_direction_and_sparse_group_fallback() -> None:
    config = _config()
    stricter = replace(
        config,
        rules=replace(
            config.rules,
            pooling=replace(config.rules.pooling, minimum_farms=2, minimum_subfarms=2),
        ),
    )
    samples = _golden_samples()
    artifacts, _ = _build_group_curves(
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
    assert (
        artifacts["zone:2|variety:1"].fallback_reason
        == "insufficient_training_farms"
    )
    assert (
        artifacts["zone:2|variety:1"].density
        == artifacts["province:Sichuan|variety:1"].density
    )


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

    assert (
        payload["base_temperature_context"]["zone:1|variety:1"][
            "selected_base_temperature"
        ]
        == Decimal("4")
    )
    assert (
        payload["base_temperature_context"]["zone:1|variety:2"][
            "selected_base_temperature"
        ]
        == Decimal("6")
    )
    assert calibration["interval_semantics"] == "pointwise_marginal"
    assert set(calibration["held_out_seasons"]) >= {"2024-2025", "2025-2026", "2026-2027"}
    assert calibration["p80_margin_share"] >= Decimal("0")
    assert calibration["p90_margin_share"] >= calibration["p80_margin_share"]
    support_days = _support_days(config)
    assert artifacts["zone:1|variety:1"].peak_day in {
        Decimal(str(day)).quantize(Decimal("0.000001")) for day in support_days
    }
