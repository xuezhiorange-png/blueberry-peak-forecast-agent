"""R3 canonical authority chain tests for S3-B live pairing materialization."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastRunModel,
)
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.residual_model import ResidualModelPredictionRun, ResidualModelTrainingRun
from backend.app.rolling_backtest.persisted_forecast_authority import (
    MATERIAL_S2_FORECAST_AUTHORITY_BUNDLE_FIELDS,
    assert_full_s2_forecast_authority_bundle_equivalence,
    build_canonical_s2_forecast_authority_bundle,
    resolve_canonical_persisted_forecast_authority_sync,
    validate_canonical_persisted_forecast_authority_resolution,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader import (
    load_persisted_forecast_binding_authority,
)
from backend.tests.forecast_quality.authority_loader_fixture import (
    CODE_AUTHORITY_ID,
    CUTOFF_AT,
    FARM_ID,
    PREDICTION_RUN_ID,
    SUBFARM_ID,
    TASK8_RUN_ID,
    TASK9_RUN_ID,
    TRAINING_RUN_ID,
    VARIETY_ID,
    _fixture_hash,
    _prediction_row,
    seed_canonical_authority_fixture,
)

pytest_plugins = ["backend.tests.forecast_quality.authority_loader_fixture"]


def _load_binding_authority(
    session: Session,
    *,
    target_date,
    forecast_quantile: str = "P50",
    horizon_days: int = 7,
):
    return load_persisted_forecast_binding_authority(
        session,
        forecast_cutoff_at=CUTOFF_AT,
        task8_forecast_run_id=TASK8_RUN_ID,
        target_date=target_date,
        forecast_quantile=forecast_quantile,
        horizon_days=horizon_days,
        farm_id=FARM_ID,
        subfarm_id=SUBFARM_ID,
        variety_id=VARIETY_ID,
    )


def _resolve_binding_authority(
    session: Session,
    *,
    target_date,
    forecast_quantile: str = "P50",
    horizon_days: int = 7,
):
    return resolve_canonical_persisted_forecast_authority_sync(
        session,
        forecast_cutoff_at=CUTOFF_AT,
        task8_forecast_run_id=TASK8_RUN_ID,
        target_date=target_date,
        forecast_quantile=forecast_quantile,
        horizon_days=horizon_days,
        farm_id=FARM_ID,
        subfarm_id=SUBFARM_ID,
        variety_id=VARIETY_ID,
    )


def test_real_canonical_acceptance(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    bundle = _load_binding_authority(authority_loader_session, target_date=core_row.date)
    resolution = _resolve_binding_authority(authority_loader_session, target_date=core_row.date)
    assert bundle is not None
    assert resolution is not None
    validate_canonical_persisted_forecast_authority_resolution(
        resolution,
        forecast_cutoff_at=CUTOFF_AT,
        target_date=core_row.date,
        horizon_days=7,
        forecast_authority=bundle,
    )


def test_full_bundle_equivalence(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    bundle = _load_binding_authority(authority_loader_session, target_date=core_row.date)
    resolution = _resolve_binding_authority(authority_loader_session, target_date=core_row.date)
    assert bundle is not None
    assert resolution is not None
    expected = build_canonical_s2_forecast_authority_bundle(resolution)
    assert_full_s2_forecast_authority_bundle_equivalence(bundle, expected)
    for field_name in MATERIAL_S2_FORECAST_AUTHORITY_BUNDLE_FIELDS:
        assert getattr(bundle, field_name) == getattr(expected, field_name)


def test_task9_non_replay_fails_closed(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    task9 = authority_loader_session.get(HarvestStateRun, TASK9_RUN_ID)
    assert task9 is not None
    task9.is_replay = False
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None


def test_task9_replay_metadata_incomplete_fails_closed(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    task9 = authority_loader_session.get(HarvestStateRun, TASK9_RUN_ID)
    assert task9 is not None
    task9.replay_executed_at = None
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None

    task9.replay_executed_at = CUTOFF_AT
    task9.replay_code_version = None
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None

    task9.replay_code_version = "fixture-replay-v1"
    task9.replay_run_correlation_id = None
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None


def test_task9_cutoff_drift_fails_closed(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    task9 = authority_loader_session.get(HarvestStateRun, TASK9_RUN_ID)
    assert task9 is not None
    task9.forecast_effective_cutoff_at = CUTOFF_AT + timedelta(days=1)
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None


def test_task10_ineligible_model_fails_closed(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    training = authority_loader_session.get(ResidualModelTrainingRun, TRAINING_RUN_ID)
    assert training is not None
    training.eligibility_status = "not_evaluated"
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None


def test_task10_training_signature_drift_fails_closed(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    prediction = authority_loader_session.get(ResidualModelPredictionRun, PREDICTION_RUN_ID)
    assert prediction is not None
    prediction.input_snapshot = {"training_signature": _fixture_hash("drifted-training-signature")}
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None


def test_task10_task9_chain_drift_fails_closed(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    prediction = authority_loader_session.get(ResidualModelPredictionRun, PREDICTION_RUN_ID)
    assert prediction is not None
    prediction.task9_result_hash = _fixture_hash("drifted-task9-result-hash")
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None


def test_core_row_chain_drift_fails_closed(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    core_row.task9_result_hash = _fixture_hash("drifted-core-row-task9-hash")
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None


def test_code_authority_visibility_drift_fails_closed(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    code_authority = authority_loader_session.get(CoreForecastCodeAuthorityModel, CODE_AUTHORITY_ID)
    assert code_authority is not None
    code_authority.available_at = CUTOFF_AT + timedelta(days=1)
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None

    code_authority.available_at = CUTOFF_AT
    core_run = authority_loader_session.get(CoreForecastRunModel, core_row.core_forecast_run_id)
    assert core_run is not None
    core_run.code_authority_hash = _fixture_hash("drifted-code-authority-hash")
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None


def test_multiple_task10_runs_no_discovery(authority_loader_session: Session) -> None:
    fixture = seed_canonical_authority_fixture(authority_loader_session)
    core_row = fixture["core_row_p50_a"]
    assert isinstance(core_row, CoreForecastDailyRowModel)
    duplicate_run = ResidualModelPredictionRun(
        id=9999,
        training_run_id=TRAINING_RUN_ID,
        task9_run_id=TASK9_RUN_ID,
        task9_result_hash=fixture["pred_row_h7_a"].task9_result_hash,
        prediction_target_kind="LEGACY_RESIDUAL_CORRECTION",
        execution_status="completed",
        mode="structural_only",
        config_hash=_fixture_hash("duplicate-prediction-run-config"),
        feature_schema_version="task10-features-v1",
        feature_schema_hash=_fixture_hash("duplicate-prediction-run-feature-schema"),
        artifact_hashes=[],
        prediction_input_signature=_fixture_hash("duplicate-prediction-run-input"),
        prediction_hash=_fixture_hash("duplicate-prediction-run-hash"),
        feature_audit={},
        warnings=[],
        blockers=[],
        fallback_reason="fixture-duplicate-structural-only",
        expected_prediction_row_count=1,
        input_snapshot={"training_signature": _fixture_hash("authority-fixture-0")},
        canonical_output={},
        canonical_payload_hash=_fixture_hash("duplicate-prediction-run-payload"),
        completed_at=CUTOFF_AT,
    )
    second_row = _prediction_row(
        row_id=4999,
        prediction_run_id=9999,
        target_date=core_row.date,
        horizon_days=7,
        row_hash=_fixture_hash("prediction-row-duplicate"),
    )
    authority_loader_session.add_all([duplicate_run, second_row])
    authority_loader_session.commit()
    assert _load_binding_authority(authority_loader_session, target_date=core_row.date) is None
