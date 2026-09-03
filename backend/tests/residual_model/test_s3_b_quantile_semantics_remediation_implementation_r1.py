"""S3-B final-target direct quantile remediation implementation R1 tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.config import (
    FINAL_TARGET_ARTIFACT_SCHEMA_VERSION,
    FINAL_TARGET_MODEL_FAMILY,
    FINAL_TARGET_MODEL_VERSION,
    load_final_target_quantile_config,
    load_residual_model_config,
)
from backend.app.residual_model.enums import PredictionTargetKind, ResidualSplit
from backend.app.residual_model.manifest import (
    final_target_manifest_hash,
    final_target_manifest_row_from_payload,
    final_target_manifest_row_payload,
)
from backend.app.residual_model.model import (
    ResidualArtifactTargetKindError,
    validate_artifact_target_kind,
)
from backend.app.residual_model.projection import project_final_target_quantiles
from backend.app.residual_model.schemas import (
    FeatureValue,
    FinalTargetActualsAuthoritySnapshot,
    FinalTargetTrainingManifestRow,
)
from backend.app.residual_model.service import (
    predict_final_target_quantiles,
    train_final_target_model_from_manifest,
    train_residual_model_from_manifest,
)
from backend.tests.residual_model.support import residual_model_config_path

LINEAGE_HASH = "a" * 64


def _final_target_row(
    *,
    season_id: int,
    farm_id: int,
    subfarm_id: int,
    variety_id: int,
    harvest_date: date,
    actual_kg: str,
    rainfall: str = "3",
    split: str = "train",
    forecast_cutoff_at: datetime | None = None,
) -> FinalTargetTrainingManifestRow:
    cutoff = forecast_cutoff_at or datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    features = (
        FeatureValue.model_validate(
            {
                "feature_name": "forecast_horizon_days",
                "value": 1,
                "known_at": cutoff,
                "source_ref": {"horizon": 1},
                "source_version": "v1",
                "source_available_at": cutoff,
            }
        ),
        FeatureValue.model_validate(
            {
                "feature_name": "weather_7d_rainfall",
                "value": rainfall,
                "known_at": cutoff,
                "source_ref": {"weather": rainfall},
                "source_version": "v1",
                "source_available_at": cutoff,
                "observation_date": date(2026, 2, 28),
            }
        ),
    )
    return FinalTargetTrainingManifestRow(
        season_id=season_id,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
        harvest_business_date=harvest_date,
        forecast_cutoff_at=cutoff,
        forecast_horizon_days=1,
        actual_harvest_quantity_kg=Decimal(actual_kg),
        actuals_authority=FinalTargetActualsAuthoritySnapshot(
            authority="V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION",
            partition_identity="TRAIN",
            source_row_identity=f"src-{harvest_date.isoformat()}",
            lineage_hash=LINEAGE_HASH,
        ),
        feature_values=features,
        feature_vector_hash=canonical_payload_hash(
            [item.model_dump(mode="json") for item in features]
        ),
        feature_visibility_audit_hash="b" * 64,
        split=split,
        include=True,
        sample_weight=Decimal("1"),
        source_refs=(
            "V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION",
            "actual_harvest_quantity_kg",
        ),
    )


def _training_rows(count: int = 30) -> list[FinalTargetTrainingManifestRow]:
    rows: list[FinalTargetTrainingManifestRow] = []
    for index in range(count):
        rows.append(
            _final_target_row(
                season_id=(index % 2) + 1 if index < 20 else 3,
                farm_id=(index % 2) + 1,
                subfarm_id=1,
                variety_id=1,
                harvest_date=date(2026, 3, 2 + (index % 5)),
                actual_kg=str(80 + (index % 7)),
                rainfall=str(3 + (index % 4)),
                split="train" if index < 20 else "validation",
            )
        )
    return rows


def test_final_target_config_identity_and_legacy_yaml_unchanged() -> None:
    legacy = load_residual_model_config(residual_model_config_path())
    assert legacy.rules.prediction_target_kind == PredictionTargetKind.LEGACY_RESIDUAL_CORRECTION
    final_config = load_final_target_quantile_config(
        min_training_rows=1,
        min_seasons=1,
        min_grains=1,
    )
    assert final_config.rules.prediction_target_kind == PredictionTargetKind.FINAL_TARGET_QUANTILE
    assert final_config.rules.model_family == FINAL_TARGET_MODEL_FAMILY
    assert final_config.rules.model_version == FINAL_TARGET_MODEL_VERSION
    assert final_config.rules.artifact_schema_version == FINAL_TARGET_ARTIFACT_SCHEMA_VERSION


def test_legacy_training_rejects_final_target_config() -> None:
    from backend.tests.residual_model.test_service import _training_row

    config = load_final_target_quantile_config(min_training_rows=1, min_seasons=1, min_grains=1)
    row = _training_row(
        season_id=1,
        factory_id=1,
        target_date=date(2026, 3, 2),
        rainfall="3",
        residual="5",
    )
    try:
        train_residual_model_from_manifest(rows=[row], config=config)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "train_final_target_model_from_manifest" in str(exc)


def test_final_target_training_uses_actual_harvest_label_not_residual() -> None:
    config = load_final_target_quantile_config(
        min_training_rows=1,
        min_seasons=1,
        min_grains=1,
    )
    rows = _training_rows(30)
    result = train_final_target_model_from_manifest(rows=rows, config=config)
    assert result.execution_status == "completed"
    assert result.eligibility_status == "eligible"
    assert result.metrics["label_field"] == "actual_harvest_quantity_kg"
    assert result.metrics["prediction_target_kind"] == "FINAL_TARGET_QUANTILE"
    assert [item.quantile_label for item in result.artifacts] == ["P50", "P80", "P90"]
    for artifact in result.artifacts:
        assert (
            artifact.metadata.prediction_target_kind == PredictionTargetKind.FINAL_TARGET_QUANTILE
        )
        assert artifact.metadata.estimator_parameters["quantile"] in (0.5, 0.8, 0.9)


def test_legacy_artifact_rejected_for_final_target_mode() -> None:
    from backend.app.residual_model.schemas import ResidualArtifactMetadata

    legacy_metadata = ResidualArtifactMetadata(
        quantile_label="P50",
        artifact_schema_version="task10-artifact-v1",
        model_family="hist_gradient_boosting_quantile",
        model_version="task10-residual-v1",
        feature_schema_version="task10-features-v1",
        feature_schema_hash="e" * 64,
        category_encoding_version="task10-categorical-v1",
        projection_version="task10-projection-v1",
        config_hash="f" * 64,
        training_signature="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        manifest_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        quantiles=[0.5, 0.8, 0.9],
        prediction_target_kind=PredictionTargetKind.LEGACY_RESIDUAL_CORRECTION,
        python_version="3.12",
        numpy_version="1.0",
        sklearn_version="1.0",
        created_by_service_version="task10-residual-v1",
        binary_format="joblib_bundle",
        binary_sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        metadata_sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        estimator_parameters={"quantile": 0.5},
        category_encodings=[],
    )
    try:
        validate_artifact_target_kind(
            legacy_metadata,
            required=PredictionTargetKind.FINAL_TARGET_QUANTILE,
        )
        raise AssertionError("expected ResidualArtifactTargetKindError")
    except ResidualArtifactTargetKindError:
        pass


def test_manifest_snapshot_round_trip_and_zero_legacy_child_policy() -> None:
    rows = _training_rows(30)
    digest = final_target_manifest_hash(rows)
    payloads = [final_target_manifest_row_payload(row) for row in rows]
    rebuilt = [final_target_manifest_row_from_payload(payload) for payload in payloads]
    assert final_target_manifest_hash(rebuilt) == digest
    for payload in payloads:
        assert "destination_factory_id" not in payload
        assert "residual_label_kg" not in payload
        assert "observed_effective_receipt_kg" not in payload
        assert payload["prediction_target_kind"] == "FINAL_TARGET_QUANTILE"


def test_projection_monotonic_and_crossing_audit() -> None:
    projection = project_final_target_quantiles(
        predicted_p50_kg=Decimal("100"),
        predicted_p80_kg=Decimal("90"),
        predicted_p90_kg=Decimal("120"),
    )
    assert projection.corrected_p50_kg <= projection.corrected_p80_kg <= projection.corrected_p90_kg
    assert projection.raw_crossing_count == 1
    assert projection.final_crossing_count == 0
    assert projection.raw_p80_kg == Decimal("90")


def test_test_split_rows_blocked() -> None:
    config = load_final_target_quantile_config(min_training_rows=1, min_seasons=1, min_grains=1)
    rows = _training_rows(5)
    rows.append(
        _final_target_row(
            season_id=9,
            farm_id=1,
            subfarm_id=1,
            variety_id=1,
            harvest_date=date(2026, 3, 10),
            actual_kg="50",
            split="test",
        )
    )
    result = train_final_target_model_from_manifest(rows=rows, config=config)
    assert result.execution_status == "blocked"
    assert "test_split_rows_forbidden" in result.blockers


def test_deterministic_prediction_same_input_same_artifact() -> None:
    config = load_final_target_quantile_config(min_training_rows=1, min_seasons=1, min_grains=1)
    rows = _training_rows(30)
    result = train_final_target_model_from_manifest(rows=rows, config=config)
    feature_names = list(result.metrics["feature_names"])
    from backend.app.residual_model.dataset import build_final_target_training_matrix
    from backend.app.residual_model.model import (
        train_quantile_estimators,
    )

    matrix, labels, weights, _, category_encodings = build_final_target_training_matrix(
        rows,
        config=config,
    )
    estimators = train_quantile_estimators(
        config=config,
        features=matrix,
        labels=labels,
        sample_weight=weights,
    )
    predict_rows = [row for row in rows if row.include and row.split == ResidualSplit.TRAIN][:3]
    first = predict_final_target_quantiles(
        rows=predict_rows,
        config=config,
        estimators=estimators,
        feature_names=feature_names,
        category_encodings=category_encodings,
    )
    second = predict_final_target_quantiles(
        rows=predict_rows,
        config=config,
        estimators=estimators,
        feature_names=feature_names,
        category_encodings=category_encodings,
    )
    assert [row.prediction_hash for row in first] == [row.prediction_hash for row in second]
    assert all(
        row.prediction_target_kind == PredictionTargetKind.FINAL_TARGET_QUANTILE for row in first
    )


def test_core_forecast_binding_uses_final_target_output() -> None:
    from backend.app.core_forecast.schemas import CompleteDailyMarketableCurveRow
    from backend.app.core_forecast.service import (
        apply_final_target_quantile_to_marketable_curve_rows,
    )

    base_row = CompleteDailyMarketableCurveRow.model_validate(
        {
            "date": date(2026, 3, 2),
            "forecast_quantile": "P50",
            "farm_id": 1,
            "subfarm_id": 1,
            "variety_id": 1,
            "destination_factory_id": 1,
            "natural_maturity_supply_kg": "1.000000",
            "opening_mature_inventory_kg": "1.000000",
            "available_mature_quantity_kg": "1.000000",
            "mature_inventory_loss_quantity_kg": "0.000000",
            "harvestable_mature_quantity_kg": "1.000000",
            "effective_harvest_capacity_kg": "1.000000",
            "model_harvested_marketable_quantity_kg": "99.000000",
            "closing_mature_inventory_kg": "0.000000",
            "unharvested_backlog_kg": "0.000000",
            "sorting_retention_rate": "1.000000",
            "postharvest_retention_rate": "1.000000",
            "effective_marketable_quantity_kg": "1.000000",
            "task8_forecast_run_id": 1,
            "task9_harvest_state_run_id": 1,
            "task8_artifact_hash": "a" * 64,
            "task9_result_hash": "b" * 64,
            "marketable_policy_version": "v1",
            "marketable_policy_hash": "c" * 64,
            "row_hash": "d" * 64,
        }
    )
    updated = apply_final_target_quantile_to_marketable_curve_rows(
        (base_row,),
        predictions_by_key={(1, 1, 1, date(2026, 3, 2), "P50"): "42.500000"},
    )
    assert updated[0].model_harvested_marketable_quantity_kg == "42.500000"
    assert updated[0].forecast_quantile == "P50"
