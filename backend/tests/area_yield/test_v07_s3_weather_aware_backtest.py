from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from subprocess import run
from sys import executable
from zoneinfo import ZoneInfo

import pytest

from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import ActualDay, BusinessBoundary
from backend.app.area_yield.weather_aware_backtest import (
    FEATURE_COUNT_A,
    FEATURE_COUNT_B,
    FEATURE_NAMES_A,
    FEATURE_NAMES_B,
    MODEL_A_S3,
    MODEL_B1,
    RollingTargetRow,
    aggregate_scored_rows,
    build_rolling_rows,
    fit_ridge_artifact,
    rows_with_known_labels,
    score_predictions,
    seal_predictions,
    weather_sensitivity,
    weather_sensitivity_prediction_set,
)
from backend.app.area_yield.weather_features import WeatherDailyObservation, build_feature_row

TZ = ZoneInfo("Asia/Shanghai")
DATASET_HASH = "a" * 64
BOUNDARY = BusinessBoundary(
    season="2025-2026",
    start=date(2025, 1, 1),
    end=date(2025, 2, 20),
    authority_source="test-authority",
    authority_hash="b" * 64,
    policy="TEST",
)


def _weather(base_id: str) -> list[WeatherDailyObservation]:
    rows: list[WeatherDailyObservation] = []
    start = BOUNDARY.start - timedelta(days=30)
    for offset in range((BOUNDARY.end - start).days + 1):
        day = start + timedelta(days=offset)
        payload = {"base_id": base_id, "local_date": day.isoformat(), "offset": offset}
        rows.append(
            WeatherDailyObservation(
                base_id=base_id,
                local_date=day,
                mean_temperature_c=Decimal(10 + offset % 17),
                tmin_c=Decimal(2 + offset % 7),
                tmax_c=Decimal(18 + offset % 19),
                precipitation_mm=Decimal(offset % 4),
                solar_energy_j_m2=Decimal(1_000_000 + offset * 10_000),
                wind_speed_m_s=Decimal("2.5") + Decimal(offset % 3),
                source_row_hash=digest(payload),
                source_dataset_hash=DATASET_HASH,
            )
        )
    return rows


def _scope() -> list[dict[str, str]]:
    return [
        {"base_id": "base-a", "canonical_base_name": "A", "productive_area_mu": "100"},
        {"base_id": "base-b", "canonical_base_name": "B", "productive_area_mu": "200"},
    ]


def _actual(scope: list[dict[str, str]]) -> dict[str, list[ActualDay]]:
    result: dict[str, list[ActualDay]] = {}
    for base_index, base in enumerate(scope):
        result[str(base["base_id"])] = [
            ActualDay(
                day=BOUNDARY.start + timedelta(days=offset),
                quantity_kg=Decimal(10 + base_index * 5 + offset),
                status="KNOWN_MAPPED_SUBTOTAL",
                source_hash="c" * 64,
            )
            for offset in range((BOUNDARY.end - BOUNDARY.start).days + 1)
        ]
    return result


def _dataset() -> tuple[tuple[RollingTargetRow, ...], dict[str, list[ActualDay]]]:
    scope = _scope()
    rows, _ = build_rolling_rows(
        season=BOUNDARY.season,
        base_scope=scope,
        observations=_weather("base-a") + _weather("base-b"),
        source_dataset_hash=DATASET_HASH,
        boundary=BOUNDARY,
    )
    return rows, _actual(scope)


@pytest.mark.unit
def test_s3_feature_schema_and_unique_target_rows() -> None:
    rows, _ = _dataset()
    assert FEATURE_COUNT_A == 10
    assert FEATURE_COUNT_B == 28
    assert tuple(FEATURE_NAMES_B[:10]) == tuple(FEATURE_NAMES_A)
    assert len({row.key for row in rows}) == len(rows)
    assert all(0 <= row.lead_day <= 14 for row in rows)


@pytest.mark.unit
def test_models_share_training_rows_and_validation_is_sealed_before_actual() -> None:
    rows, actual = _dataset()
    training = rows_with_known_labels(rows, actual)
    model_a = fit_ridge_artifact(
        model_id=MODEL_A_S3,
        fold_id="FOLD_A",
        rows=training,
        feature_names=FEATURE_NAMES_A,
        training_input_hash="d" * 64,
    )
    model_b = fit_ridge_artifact(
        model_id=MODEL_B1,
        fold_id="FOLD_A",
        rows=training,
        feature_names=FEATURE_NAMES_B,
        training_input_hash="e" * 64,
    )
    sealed = seal_predictions(
        fold_id="FOLD_A",
        validation_season=BOUNDARY.season,
        rows=rows,
        model_a=model_a,
        model_b=model_b,
        boundary=BOUNDARY,
        train_row_keys=model_a.training_row_keys,
    )
    assert model_a.training_row_keys == model_b.training_row_keys
    assert model_a.training_label_hash == model_b.training_label_hash
    assert sealed["manifest"]["validation_labels_read"] is False
    changed = {
        base_id: [
            ActualDay(
                day=item.day,
                quantity_kg=(item.quantity_kg or Decimal(0)) + Decimal(999),
                status=item.status,
                source_hash=item.source_hash,
            )
            for item in values
        ]
        for base_id, values in actual.items()
    }
    changed_score = score_predictions(
        sealed_predictions=sealed["predictions"],
        actual_by_base=changed,
        boundary=BOUNDARY,
    )
    assert sealed["manifest"]["model_a_prediction_hash"] == digest(
        [
            {
                "target_row_key": row["target_row_key"],
                "prediction": row["model_a_predicted_daily_kg"],
            }
            for row in sealed["predictions"]
        ]
    )
    assert changed_score["scored_row_count"] == len(sealed["predictions"])
    assert (
        changed_score["models"]
        != score_predictions(
            sealed_predictions=sealed["predictions"],
            actual_by_base=actual,
            boundary=BOUNDARY,
        )["models"]
    )


@pytest.mark.unit
def test_only_model_b_reacts_to_legal_weather_feature_mutation() -> None:
    rows, actual = _dataset()
    training = rows_with_known_labels(rows, actual)
    model_a = fit_ridge_artifact(
        model_id=MODEL_A_S3,
        fold_id="FOLD_A",
        rows=training,
        feature_names=FEATURE_NAMES_A,
        training_input_hash="h" * 64,
    )
    model_b = fit_ridge_artifact(
        model_id=MODEL_B1,
        fold_id="FOLD_A",
        rows=training,
        feature_names=FEATURE_NAMES_B,
        training_input_hash="i" * 64,
    )
    result = weather_sensitivity(row=rows[100], model_a=model_a, model_b=model_b)
    assert result == {
        "model_b_weather_sensitivity_pass": True,
        "model_a_weather_invariance_pass": True,
    }


@pytest.mark.unit
def test_prediction_set_weather_sensitivity_uses_all_rows_and_hashes() -> None:
    rows, actual = _dataset()
    training = rows_with_known_labels(rows, actual)
    model_a = fit_ridge_artifact(
        model_id=MODEL_A_S3,
        fold_id="FOLD_A",
        rows=training,
        feature_names=FEATURE_NAMES_A,
        training_input_hash="j" * 64,
    )
    model_b = fit_ridge_artifact(
        model_id=MODEL_B1,
        fold_id="FOLD_A",
        rows=training,
        feature_names=FEATURE_NAMES_B,
        training_input_hash="k" * 64,
    )
    result = weather_sensitivity_prediction_set(
        rows=rows,
        model_a=model_a,
        model_b=model_b,
    )
    assert result["row_count"] == len(rows)
    assert result["model_a_weather_invariance_pass"] is True
    assert result["model_b_weather_sensitivity_pass"] is True
    assert (
        result["model_a_baseline_prediction_hash"]
        == result["model_a_mutated_weather_prediction_hash"]
    )
    assert (
        result["model_b_baseline_prediction_hash"]
        != result["model_b_mutated_weather_prediction_hash"]
    )


@pytest.mark.unit
def test_future_weather_mutation_cannot_change_past_feature_row() -> None:
    origin_day = date(2025, 2, 1)
    origin = datetime.combine(origin_day, time.min, tzinfo=TZ)
    observations = _weather("base-a")
    baseline = build_feature_row(
        observations=observations,
        base_id="base-a",
        forecast_origin=origin,
        target_start=origin_day,
        target_end=origin_day,
        source_dataset_hash=DATASET_HASH,
    )
    mutated = [
        replace(
            row,
            mean_temperature_c=Decimal("999"),
            tmin_c=Decimal("999"),
            tmax_c=Decimal("999"),
            precipitation_mm=Decimal("999"),
            solar_energy_j_m2=Decimal("999"),
            wind_speed_m_s=Decimal("999"),
        )
        if row.local_date >= origin_day
        else row
        for row in observations
    ]
    replay = build_feature_row(
        observations=mutated,
        base_id="base-a",
        forecast_origin=origin,
        target_start=origin_day,
        target_end=origin_day,
        source_dataset_hash=DATASET_HASH,
    )
    assert replay.feature_hash == baseline.feature_hash


@pytest.mark.unit
def test_missing_actual_is_not_zero_and_confirmed_zero_is_comparable() -> None:
    rows, actual = _dataset()
    training = rows_with_known_labels(rows, actual)
    model_a = fit_ridge_artifact(
        model_id=MODEL_A_S3,
        fold_id="FOLD_A",
        rows=training,
        feature_names=FEATURE_NAMES_A,
        training_input_hash="f" * 64,
    )
    model_b = fit_ridge_artifact(
        model_id=MODEL_B1,
        fold_id="FOLD_A",
        rows=training,
        feature_names=FEATURE_NAMES_B,
        training_input_hash="g" * 64,
    )
    sealed = seal_predictions(
        fold_id="FOLD_A",
        validation_season=BOUNDARY.season,
        rows=rows,
        model_a=model_a,
        model_b=model_b,
        boundary=BOUNDARY,
        train_row_keys=model_a.training_row_keys,
    )
    first = actual["base-a"][0]
    actual["base-a"][0] = ActualDay(first.day, None, "UNKNOWN_MISSING", first.source_hash)
    second = actual["base-b"][1]
    actual["base-b"][1] = ActualDay(second.day, Decimal(0), "CONFIRMED_ZERO", second.source_hash)
    score = score_predictions(
        sealed_predictions=sealed["predictions"],
        actual_by_base=actual,
        boundary=BOUNDARY,
    )
    assert score["unscored_status_counts"]["UNKNOWN_MISSING"] > 0
    assert score["scored_row_count"] == len(sealed["predictions"]) - 1


@pytest.mark.unit
def test_pooled_wape_is_not_mean_of_run_wapes() -> None:
    rows = [
        {
            "season": BOUNDARY.season,
            "base_id": "base-a",
            "forecast_origin": "2025-01-01T00:00:00+08:00",
            "target_date": "2025-01-01",
            "lead_day": 0,
            "actual_daily_kg": "100",
            "model_a_predicted_daily_kg": "50",
            "model_b_predicted_daily_kg": "50",
        },
        {
            "season": BOUNDARY.season,
            "base_id": "base-b",
            "forecast_origin": "2025-01-01T00:00:00+08:00",
            "target_date": "2025-01-01",
            "lead_day": 0,
            "actual_daily_kg": "1000",
            "model_a_predicted_daily_kg": "1000",
            "model_b_predicted_daily_kg": "1000",
        },
    ]
    result = aggregate_scored_rows(
        scored_predictions=rows,
        boundaries={BOUNDARY.season: BOUNDARY},
    )
    assert (
        result["models"][MODEL_A_S3]["horizons"]["H1"]["pooled_wape"]
        == "0.04545454545454545454545454545"
    )
    assert result["models"][MODEL_A_S3]["horizons"]["H1"]["pooled_wape"] != "0.25"


@pytest.mark.unit
def test_fresh_process_imports_s3_module() -> None:
    completed = run(
        [
            executable,
            "-c",
            (
                "from backend.app.area_yield.weather_aware_backtest import "
                "MODEL_A_S3,MODEL_B1; print(MODEL_A_S3); print(MODEL_B1)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.splitlines() == [MODEL_A_S3, MODEL_B1]
