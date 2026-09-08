from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.maturity.config import MaturityCurveConfig, load_maturity_curve_config
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s4_candidate_execution import (
    CANDIDATE_01_PARAMETER_MANIFEST_HASH_BOUND,
    CandidateRunDefinition,
    build_candidate_01_manifest,
    build_derived_candidate_config,
    validate_candidate_01_manifest,
)
from backend.app.s4_local_engineering import (
    LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS,
    FrozenEngineeringDataset,
    LocalEngineeringContractError,
    LocalPrediction,
    LocalReplayResult,
    _build_predictions,
    _complete_7day_windows,
    _metric_payload,
    _rolling_peak_error,
    _single_day_peak_error,
    compute_metrics,
    load_frozen_engineering_dataset,
    run_local_replay,
    verify_frozen_source_object,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_CUTOFF = date(2026, 1, 9)


@pytest.fixture(scope="module")
def dataset() -> FrozenEngineeringDataset:
    """Load only frozen partition identities; no score is run here."""

    return load_frozen_engineering_dataset(REPO_ROOT)


@pytest.fixture(scope="module")
def synthetic_dataset() -> FrozenEngineeringDataset:
    train_rows = tuple(
        _row(
            harvest_date=date(2026, 1, 1) + timedelta(days=index),
            quantity=Decimal(10 + index),
        )
        for index in range(10)
    )
    validation_rows = tuple(
        _row(
            harvest_date=date(2026, 1, 10) + timedelta(days=index),
            quantity=Decimal(20 + index),
        )
        for index in range(2)
    )
    return FrozenEngineeringDataset(
        train_rows=train_rows,
        validation_rows=validation_rows,
        train_content_sha256="synthetic-train",
        validation_content_sha256="synthetic-validation",
        materialized_dataset_identity_sha256="synthetic-dataset",
        test_row_count=0,
        forecast_cutoff_at=SYNTHETIC_CUTOFF,
    )


@pytest.fixture(scope="module")
def incumbent_config() -> MaturityCurveConfig:
    return load_maturity_curve_config(REPO_ROOT / "configs/maturity_curve.yaml")


def _row(
    *,
    harvest_date: date,
    quantity: Decimal,
    farm: str = "farm-a",
    subfarm: str = "subfarm-a",
    variety: str = "variety-a",
) -> MaterializableRow:
    identity = f"{farm}:{subfarm}:{variety}:{harvest_date.isoformat()}"
    return MaterializableRow(
        season="season-a",
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=harvest_date,
        actual_harvest_quantity_kg=quantity,
        source_row_identity=f"source:{identity}",
        cleaned_row_identity=f"cleaned:{identity}",
        pit_visibility_identity=f"pit:{identity}",
        revision_winner_identity=f"winner:{identity}",
    )


def _prediction(
    *,
    day: date,
    actual: str,
    p50: str,
    farm: str = "farm-a",
    subfarm: str = "subfarm-a",
    variety: str = "variety-a",
) -> LocalPrediction:
    p50_value = Decimal(p50)
    return LocalPrediction(
        season="season-a",
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=day,
        forecast_cutoff_at=date(2026, 1, 1),
        actual_kg=Decimal(actual),
        p50_kg=p50_value,
        p80_kg=p50_value,
        p90_kg=p50_value,
    )


def test_frozen_source_and_partition_identity(dataset: FrozenEngineeringDataset) -> None:
    source_path = Path("/tmp/source-002-original.xls")
    if source_path.is_file():
        source = verify_frozen_source_object(source_path)

        assert source.byte_count == 28_668_416
        assert source.sha256 == "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a"
        assert source.row_count == 233_171

    assert len(dataset.train_rows) == 16_224
    assert len(dataset.validation_rows) == 8_006
    assert (
        dataset.train_content_sha256
        == "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
    )
    assert (
        dataset.validation_content_sha256
        == "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
    )
    assert dataset.test_row_count == 0


def test_incumbent_replay_is_deterministic_and_local_only(
    synthetic_dataset: FrozenEngineeringDataset, incumbent_config: MaturityCurveConfig
) -> None:
    first = run_local_replay(dataset=synthetic_dataset, config=incumbent_config)
    second = run_local_replay(dataset=synthetic_dataset, config=incumbent_config)

    assert first.payload() == second.payload()
    assert first.prediction_identity_sha256 == second.prediction_identity_sha256
    assert first.authority_class == LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS
    assert first.model_id == "V0_2_CURRENT_MODEL"
    assert first.metrics.comparable_row_count == 2


def test_candidate_manifest_is_frozen_to_four_runs() -> None:
    config_path = REPO_ROOT / "configs/maturity_curve.yaml"
    manifest = build_candidate_01_manifest(config_path)
    validate_candidate_01_manifest(manifest, config_path=config_path)

    assert manifest.manifest_hash == CANDIDATE_01_PARAMETER_MANIFEST_HASH_BOUND
    assert manifest.candidate_id == "01_parameter_calibration"
    assert tuple(run.candidate_run_ordinal for run in manifest.runs) == (1, 2, 3, 4)
    assert manifest.planned_run_count == 4


def test_four_candidate_runs_are_paired_to_the_same_validation_labels(
    synthetic_dataset: FrozenEngineeringDataset, incumbent_config: MaturityCurveConfig
) -> None:
    config_path = REPO_ROOT / "configs/maturity_curve.yaml"
    manifest = build_candidate_01_manifest(config_path)
    incumbent = run_local_replay(dataset=synthetic_dataset, config=incumbent_config)

    results: list[tuple[CandidateRunDefinition, LocalReplayResult]] = []
    for ordinal in range(1, 5):
        run, candidate_config = build_derived_candidate_config(manifest, ordinal)
        result = run_local_replay(dataset=synthetic_dataset, config=candidate_config)
        results.append((run, result))

    assert len(results) == 4
    assert all(result.metrics.comparable_row_count == 2 for _, result in results)
    assert all(
        result.actual_label_set_identity_sha256 == incumbent.actual_label_set_identity_sha256
        for _, result in results
    )
    assert all(
        result.business_grain_set_identity_sha256 == incumbent.business_grain_set_identity_sha256
        for _, result in results
    )
    assert {run.random_seed for run, _ in results} == {20_260_624}


def test_result_payload_is_aggregate_only(
    synthetic_dataset: FrozenEngineeringDataset, incumbent_config: MaturityCurveConfig
) -> None:
    result = run_local_replay(dataset=synthetic_dataset, config=incumbent_config)
    payload = result.payload()

    assert "predictions" not in payload
    assert "actual_kg" not in repr(payload)
    assert set(payload["metrics"]["breakdown_metrics"]) == {
        "forecast_horizon_days",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "season_business_key",
        "model_identity",
    }


def test_sustained_7day_exactly_seven_days_has_one_window() -> None:
    predictions = tuple(
        _prediction(day=date(2026, 1, 2) + timedelta(days=index), actual="1", p50="2")
        for index in range(7)
    )
    daily = {item.harvest_business_date: (item.actual_kg, item.p50_kg) for item in predictions}

    assert len(_complete_7day_windows(daily)) == 1
    assert _rolling_peak_error(predictions) == Decimal("7.000000")


def test_sustained_7day_includes_last_legal_window() -> None:
    predictions = tuple(
        _prediction(
            day=date(2026, 1, 2) + timedelta(days=index),
            actual="1",
            p50="1" if index < 7 else "3",
        )
        for index in range(8)
    )

    assert _rolling_peak_error(predictions) == Decimal("2.000000")


def test_sustained_7day_rejects_missing_calendar_day() -> None:
    predictions = tuple(
        _prediction(day=day, actual="1", p50="2")
        for day in (
            date(2026, 1, 2),
            date(2026, 1, 3),
            date(2026, 1, 4),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
            date(2026, 1, 9),
        )
    )

    assert _rolling_peak_error(predictions) is None


def test_sustained_7day_no_complete_window_is_not_computable() -> None:
    predictions = tuple(
        _prediction(day=date(2026, 1, 2) + timedelta(days=index), actual="1", p50="2")
        for index in range(6)
    )
    payload = _metric_payload(predictions)

    assert payload["sustained_7day_quantity_absolute_error_kg_q"] is None
    assert payload["sustained_7day_metric_status"] == "NOT_COMPUTABLE"
    assert payload["sustained_7day_metric_reason_code"] == "NO_COMPLETE_7DAY_WINDOW"


def test_cumulative_absolute_error_is_abs_of_aggregate_difference() -> None:
    predictions = (
        _prediction(day=date(2026, 1, 2), actual="10", p50="20", subfarm="subfarm-a"),
        _prediction(day=date(2026, 1, 2), actual="10", p50="0", subfarm="subfarm-b"),
    )

    assert compute_metrics(predictions).cumulative_absolute_error_kg == Decimal("0.000000")


def test_cumulative_absolute_error_is_not_sum_of_group_absolute_errors() -> None:
    predictions = (
        _prediction(day=date(2026, 1, 2), actual="10", p50="20", subfarm="subfarm-a"),
        _prediction(day=date(2026, 1, 2), actual="10", p50="0", subfarm="subfarm-b"),
    )

    assert compute_metrics(predictions).cumulative_absolute_error_kg != Decimal("20.000000")


def test_farm_single_day_peak_is_computed_after_subfarm_daily_sum() -> None:
    predictions = (
        _prediction(day=date(2026, 1, 2), actual="6", p50="0", subfarm="subfarm-a"),
        _prediction(day=date(2026, 1, 2), actual="6", p50="0", subfarm="subfarm-b"),
        _prediction(day=date(2026, 1, 3), actual="10", p50="0", subfarm="subfarm-c"),
    )

    assert compute_metrics(predictions).single_day_peak_quantity_absolute_error_kg_q == Decimal(
        "12.000000"
    )


def test_single_day_peak_earliest_date_wins_tie() -> None:
    predictions = (
        _prediction(day=date(2026, 1, 2), actual="10", p50="0"),
        _prediction(day=date(2026, 1, 3), actual="10", p50="0"),
    )

    _, actual_peak_date, _, predicted_peak_date = _single_day_peak_error(predictions)
    assert actual_peak_date == date(2026, 1, 2)
    assert predicted_peak_date == date(2026, 1, 2)


def test_forecast_horizon_uses_cutoff_to_target_definition() -> None:
    prediction = _prediction(day=date(2026, 1, 4), actual="1", p50="1")

    assert prediction.horizon_days == 3


def test_missing_forecast_cutoff_authority_fails_closed(
    synthetic_dataset: FrozenEngineeringDataset, incumbent_config: MaturityCurveConfig
) -> None:
    missing_cutoff_dataset = replace(synthetic_dataset, forecast_cutoff_at=None)

    with pytest.raises(
        LocalEngineeringContractError, match="FORECAST_HORIZON_AUTHORITY_UNAVAILABLE"
    ):
        run_local_replay(dataset=missing_cutoff_dataset, config=incumbent_config)


def test_validation_actual_is_never_used_as_prediction_fallback(
    synthetic_dataset: FrozenEngineeringDataset, incumbent_config: MaturityCurveConfig
) -> None:
    first_row = synthetic_dataset.validation_rows[0]
    changed_actual = replace(
        first_row,
        actual_harvest_quantity_kg=Decimal("999999"),
    )
    first = _build_predictions(
        train_rows=synthetic_dataset.train_rows,
        validation_rows=(first_row,),
        config=incumbent_config,
        forecast_cutoff_at=SYNTHETIC_CUTOFF,
    )
    second = _build_predictions(
        train_rows=synthetic_dataset.train_rows,
        validation_rows=(changed_actual,),
        config=incumbent_config,
        forecast_cutoff_at=SYNTHETIC_CUTOFF,
    )

    assert first[0].p50_kg == second[0].p50_kg


def test_unseen_validation_support_fails_closed(
    synthetic_dataset: FrozenEngineeringDataset, incumbent_config: MaturityCurveConfig
) -> None:
    unseen = replace(synthetic_dataset.validation_rows[0], variety="unseen-variety")

    with pytest.raises(
        LocalEngineeringContractError, match="LOCAL_VALIDATION_TRAIN_SUPPORT_UNAVAILABLE"
    ):
        _build_predictions(
            train_rows=synthetic_dataset.train_rows,
            validation_rows=(unseen,),
            config=incumbent_config,
            forecast_cutoff_at=SYNTHETIC_CUTOFF,
        )
