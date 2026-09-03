"""S3-B final-target direct quantile remediation implementation R1 tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.config import (
    FINAL_TARGET_ARTIFACT_SCHEMA_VERSION,
    FINAL_TARGET_MODEL_FAMILY,
    FINAL_TARGET_MODEL_VERSION,
    LEGACY_MODEL_FAMILY,
    PredictionTargetKind,
    load_final_target_quantile_config,
    load_residual_model_config,
)
from backend.app.residual_model.enums import ResidualSplit
from backend.app.residual_model.model import (
    ResidualArtifactTargetKindError,
    validate_artifact_target_kind,
)
from backend.app.residual_model.projection import project_final_target_quantiles
from backend.app.residual_model.schemas import (
    FeatureValue,
    FinalTargetActualsAuthoritySnapshot,
    FinalTargetPredictionRequest,
    FinalTargetTrainingManifestRow,
    GovernedGrainIdentityBinding,
    ResidualPredictionExecutionResult,
    build_final_target_prediction_authority,
)
from backend.app.residual_model.service import (
    predict_final_target_quantiles,
    train_final_target_model_from_manifest,
    train_residual_model_from_manifest,
)
from backend.app.residual_model.training_manifest import (
    final_target_manifest_hash,
    final_target_manifest_row_from_payload,
    final_target_manifest_row_payload,
)
from backend.tests.residual_model.support import residual_model_config_path

BASE_ENUMS_BLOB = "736df29dc8c128333ccc3c944ba4b7669124ab45"
BASE_MANIFEST_BLOB = "2f94ec0a5daa2db7843ad07175590d97dfae4ac3"
BASE_CANONICAL_BLOB = "1550da6e887d48a54ef355af1b976bad4f2c54b8"
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


def test_grant_allowlist_unauthorized_files_remain_at_base_blob() -> None:
    import subprocess

    enums_blob = subprocess.check_output(
        ["git", "hash-object", "backend/app/residual_model/enums.py"],
        text=True,
    ).strip()
    manifest_blob = subprocess.check_output(
        ["git", "hash-object", "backend/app/residual_model/manifest.py"],
        text=True,
    ).strip()
    canonical_blob = subprocess.check_output(
        ["git", "hash-object", "backend/app/residual_model/canonical.py"],
        text=True,
    ).strip()
    assert enums_blob == BASE_ENUMS_BLOB
    assert manifest_blob == BASE_MANIFEST_BLOB
    assert canonical_blob == BASE_CANONICAL_BLOB


def test_legacy_and_final_target_model_families_are_distinct() -> None:
    legacy = load_residual_model_config(residual_model_config_path())
    final_config = load_final_target_quantile_config(
        min_training_rows=1,
        min_seasons=1,
        min_grains=1,
    )
    assert legacy.rules.model_family == LEGACY_MODEL_FAMILY
    assert final_config.rules.model_family == FINAL_TARGET_MODEL_FAMILY
    assert LEGACY_MODEL_FAMILY != FINAL_TARGET_MODEL_FAMILY
    unchanged_legacy = load_residual_model_config(residual_model_config_path())
    assert unchanged_legacy.config_hash == legacy.config_hash


def test_final_target_eligibility_uses_min_grains_not_min_factories() -> None:
    config = load_final_target_quantile_config(
        min_training_rows=1,
        min_seasons=1,
        min_grains=3,
    )
    assert config.rules.eligibility.min_grains == 3
    rows = _training_rows(10)
    result = train_final_target_model_from_manifest(rows=rows, config=config)
    assert result.eligibility_status == "ineligible"
    assert "insufficient_training_grains" in result.eligibility_reasons


def test_source_row_grain_mismatch_rejected() -> None:
    from backend.app.residual_model.training_manifest import (
        ResidualManifestBuildError,
        build_final_target_manifest_from_materializable_rows,
    )
    from backend.app.s2_materialized_dataset.shared.contracts import (
        MaterializableRow,
        PartitionName,
    )

    cutoff = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    binding = GovernedGrainIdentityBinding(
        season_id=1,
        season="2025~2026",
        farm_id=1,
        farm="farm-a",
        subfarm_id=1,
        subfarm="subfarm-1",
        variety_id=1,
        variety="variety-x",
    )
    row_a = MaterializableRow(
        season="2025~2026",
        farm="farm-a",
        subfarm="subfarm-1",
        variety="variety-x",
        harvest_business_date=date(2026, 3, 2),
        actual_harvest_quantity_kg=Decimal("80"),
        source_row_identity="src-a",
        cleaned_row_identity="cln-a",
        pit_visibility_identity="pit-a",
        revision_winner_identity="rev-a",
    )
    row_b = MaterializableRow(
        season="2025~2026",
        farm="farm-b",
        subfarm="subfarm-1",
        variety="variety-x",
        harvest_business_date=date(2026, 3, 3),
        actual_harvest_quantity_kg=Decimal("70"),
        source_row_identity="src-b",
        cleaned_row_identity="cln-b",
        pit_visibility_identity="pit-b",
        revision_winner_identity="rev-b",
    )
    try:
        build_final_target_manifest_from_materializable_rows(
            (row_a, row_b),
            grain_identity=binding,
            partition=PartitionName.TRAIN,
            forecast_cutoff_at=cutoff,
            partition_identity="TRAIN",
            lineage_hash=LINEAGE_HASH,
        )
        raise AssertionError("expected ResidualManifestBuildError")
    except ResidualManifestBuildError as exc:
        assert "source_row_grain_mismatch" in str(exc)


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
        assert (
            "FINAL_TARGET_QUANTILE config requires train_final_target_model_from_manifest"
            in str(exc)
        )


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

    cutoff = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    config = load_final_target_quantile_config(min_training_rows=1, min_seasons=1, min_grains=1)
    rows = _training_rows(30)
    train_result = train_final_target_model_from_manifest(rows=rows, config=config)
    from backend.app.residual_model.dataset import build_final_target_training_matrix
    from backend.app.residual_model.model import train_quantile_estimators

    matrix, labels, weights, feature_names, category_encodings = build_final_target_training_matrix(
        rows,
        config=config,
    )
    estimators = train_quantile_estimators(
        config=config,
        features=matrix,
        labels=labels,
        sample_weight=weights,
    )
    predict_rows = [row for row in rows if row.include and row.split == ResidualSplit.TRAIN][:1]
    final_preds = predict_final_target_quantiles(
        rows=predict_rows,
        config=config,
        estimators=estimators,
        feature_names=list(feature_names),
        category_encodings=category_encodings,
        model_run_id=42,
        prediction_run_id=99,
    )
    p50_preds = tuple(row for row in final_preds if row.forecast_quantile == "P50")
    prediction_result = ResidualPredictionExecutionResult(
        execution_status="completed",
        mode="residual_corrected",
        model_run_id=42,
        task9_run_id=0,
        task9_result_hash="0" * 64,
        config_hash=train_result.config_hash,
        prediction_input_signature="0" * 64,
        prediction_hash="0" * 64,
        warnings=(),
        blockers=(),
        rows=(),
        final_target_rows=p50_preds,
        input_snapshot={
            "prediction_target_kind": "FINAL_TARGET_QUANTILE",
            "forecast_cutoff_at": cutoff.isoformat(),
        },
    )
    authority = build_final_target_prediction_authority(
        training_result=train_result,
        prediction_result=prediction_result,
        prediction_run_id=99,
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
        authority=authority,
    )
    from backend.app.core_forecast.schemas import OUTPUT_QUANTUM

    p50_marketable_kg = p50_preds[0].model_harvested_marketable_quantity_kg
    expected_marketable = f"{Decimal(p50_marketable_kg).quantize(OUTPUT_QUANTUM):.6f}"
    assert updated[0].model_harvested_marketable_quantity_kg == expected_marketable
    assert updated[0].forecast_quantile == "P50"


def test_core_forecast_rejects_naked_prediction_dict() -> None:
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
    try:
        apply_final_target_quantile_to_marketable_curve_rows(
            (base_row,),
            authority={"predictions_by_key": {(1, 1, 1, date(2026, 3, 2), "P50"): "1"}},
        )
        raise AssertionError("expected ValueError")
    except (ValueError, TypeError):
        pass


def test_post_cutoff_feature_leakage_blocked() -> None:
    config = load_final_target_quantile_config(min_training_rows=1, min_seasons=1, min_grains=1)
    cutoff = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    late_known = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    row = _final_target_row(
        season_id=1,
        farm_id=1,
        subfarm_id=1,
        variety_id=1,
        harvest_date=date(2026, 3, 2),
        actual_kg="80",
        forecast_cutoff_at=cutoff,
    )
    leaked_features = (
        FeatureValue.model_validate(
            {
                "feature_name": "weather_7d_rainfall",
                "value": "9",
                "known_at": late_known,
                "source_ref": {"weather": "9"},
                "source_version": "v1",
                "source_available_at": late_known,
                "observation_date": date(2026, 2, 28),
            }
        ),
    )
    leaked_row = row.model_copy(update={"feature_values": leaked_features})
    result = train_final_target_model_from_manifest(rows=[leaked_row], config=config)
    assert result.execution_status == "blocked"
    assert "post_cutoff_feature_leakage" in result.blockers


@pytest.fixture
async def residual_sqlite_session() -> AsyncSession:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.app.models.residual_model import (
        ResidualModelArtifact,
        ResidualModelExecutionAttempt,
        ResidualModelManifestRow,
        ResidualModelPredictionRow,
        ResidualModelPredictionRun,
        ResidualModelTrainingRun,
    )

    tables = [
        ResidualModelTrainingRun.__table__,
        ResidualModelManifestRow.__table__,
        ResidualModelArtifact.__table__,
        ResidualModelPredictionRun.__table__,
        ResidualModelPredictionRow.__table__,
        ResidualModelExecutionAttempt.__table__,
    ]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ResidualModelTrainingRun.metadata.create_all(
                sync_conn,
                tables=tables,
            )
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def stub_task9_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    async def _fake_load_harvest_state_output_by_id(
        session: AsyncSession,
        *,
        run_id: int,
    ) -> object | None:
        return SimpleNamespace(status="completed", result_hash="a" * 64)

    monkeypatch.setattr(
        "backend.app.residual_model.persistence.load_harvest_state_output_by_id",
        _fake_load_harvest_state_output_by_id,
    )


@pytest.mark.asyncio
async def test_final_target_training_persistence_zero_legacy_child_rows(
    residual_sqlite_session: AsyncSession,
) -> None:
    from sqlalchemy import func, select

    from backend.app.models.residual_model import ResidualModelManifestRow
    from backend.app.residual_model.persistence import (
        load_residual_training_run_by_id,
        save_residual_training_run,
    )

    config = load_final_target_quantile_config(min_training_rows=1, min_seasons=1, min_grains=1)
    rows = _training_rows(30)
    result = train_final_target_model_from_manifest(rows=rows, config=config)
    run = await save_residual_training_run(
        residual_sqlite_session,
        result=result,
        final_target_manifest_rows=rows,
    )
    assert run.manifest_row_count == 0
    child_count = await residual_sqlite_session.scalar(
        select(func.count()).select_from(ResidualModelManifestRow)
    )
    assert child_count == 0
    loaded = await load_residual_training_run_by_id(
        residual_sqlite_session,
        run_id=run.id,
    )
    assert loaded is not None
    assert loaded.input_snapshot.get("prediction_target_kind") == "FINAL_TARGET_QUANTILE"


@pytest.mark.asyncio
async def test_final_target_prediction_canonical_json_round_trip(
    residual_sqlite_session: AsyncSession,
) -> None:
    from sqlalchemy import func, select

    from backend.app.models.residual_model import ResidualModelPredictionRow
    from backend.app.repositories.residual_model import list_residual_artifacts
    from backend.app.residual_model.canonical import prediction_input_signature_hash
    from backend.app.residual_model.dataset import build_final_target_training_matrix
    from backend.app.residual_model.enums import ResidualPredictionMode
    from backend.app.residual_model.model import train_quantile_estimators
    from backend.app.residual_model.persistence import (
        _prediction_hash_from_result,
        load_residual_prediction_run_by_id,
        save_residual_prediction_run,
        save_residual_training_run,
    )

    config = load_final_target_quantile_config(min_training_rows=1, min_seasons=1, min_grains=1)
    rows = _training_rows(30)
    train_result = train_final_target_model_from_manifest(rows=rows, config=config)
    training_run = await save_residual_training_run(
        residual_sqlite_session,
        result=train_result,
        final_target_manifest_rows=rows,
    )
    artifacts = await list_residual_artifacts(
        residual_sqlite_session,
        training_run_id=training_run.id,
    )
    artifact_hashes = [artifact.artifact_sha256 for artifact in artifacts]
    feature_names = list(train_result.metrics["feature_names"])
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
    predict_rows = [row for row in rows if row.include and row.split == "train"][:2]
    final_preds = predict_final_target_quantiles(
        rows=predict_rows,
        config=config,
        estimators=estimators,
        feature_names=feature_names,
        category_encodings=category_encodings,
    )
    input_snapshot = {
        "prediction_target_kind": "FINAL_TARGET_QUANTILE",
        "training_signature": training_run.training_signature,
        "feature_schema_version": training_run.feature_schema_version,
        "feature_schema_hash": training_run.feature_schema_hash,
        "projection_version": config.rules.projection_version,
        "fallback_policy": "structural_only_fallback",
        "artifact_hashes": artifact_hashes,
        "final_target_prediction_row_count": len(final_preds),
        "supplemental_feature_values": [],
        "feature_audit_hashes": [],
        "feature_rows": [],
    }
    prediction_input_signature = prediction_input_signature_hash(
        model_run_id=training_run.id,
        training_signature=training_run.training_signature,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        feature_analytics_build_run_id=None,
        feature_actual_snapshot=None,
        supplemental_feature_values=[],
        feature_audit_hashes=[],
        feature_rows=[],
        artifact_hashes=artifact_hashes,
        config_hash=training_run.config_hash,
        feature_schema_version=training_run.feature_schema_version,
        feature_schema_hash=training_run.feature_schema_hash,
        projection_version=config.rules.projection_version,
        fallback_policy_version="structural_only_fallback",
    )
    prediction_hash = _prediction_hash_from_result(
        ResidualPredictionExecutionResult(
            execution_status="completed",
            mode=ResidualPredictionMode.RESIDUAL_CORRECTED,
            model_run_id=training_run.id,
            task9_run_id=10,
            task9_result_hash="a" * 64,
            config_hash=training_run.config_hash,
            prediction_input_signature=prediction_input_signature,
            prediction_hash="0" * 64,
            warnings=(),
            blockers=(),
            rows=(),
            final_target_rows=tuple(final_preds),
            input_snapshot=input_snapshot,
        )
    )
    prediction_result = ResidualPredictionExecutionResult(
        execution_status="completed",
        mode=ResidualPredictionMode.RESIDUAL_CORRECTED,
        model_run_id=training_run.id,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash=training_run.config_hash,
        prediction_input_signature=prediction_input_signature,
        prediction_hash=prediction_hash,
        warnings=(),
        blockers=(),
        rows=(),
        final_target_rows=tuple(final_preds),
        input_snapshot=input_snapshot,
    )
    run = await save_residual_prediction_run(
        residual_sqlite_session,
        result=prediction_result,
        feature_schema_version=training_run.feature_schema_version,
        feature_schema_hash=training_run.feature_schema_hash,
        artifact_hashes=artifact_hashes,
    )
    child_count = await residual_sqlite_session.scalar(
        select(func.count()).select_from(ResidualModelPredictionRow)
    )
    assert child_count == 0
    assert run.expected_prediction_row_count == 0
    loaded = await load_residual_prediction_run_by_id(
        residual_sqlite_session,
        run_id=run.id,
    )
    assert loaded is not None
    assert loaded.input_snapshot.get("prediction_target_kind") == "FINAL_TARGET_QUANTILE"
    assert len(loaded.final_target_rows) == len(final_preds)
    assert all(
        row.prediction_target_kind.value == "FINAL_TARGET_QUANTILE"
        for row in loaded.final_target_rows
    )
    assert all(row.model_run_id == training_run.id for row in loaded.final_target_rows)
    assert all(row.prediction_run_id == run.id for row in loaded.final_target_rows)


@pytest.mark.asyncio
async def test_execute_final_target_prediction_application_end_to_end(
    residual_sqlite_session: AsyncSession,
) -> None:
    from backend.app.residual_model.application import (
        execute_final_target_prediction,
        execute_final_target_training,
    )

    config = load_final_target_quantile_config(min_training_rows=1, min_seasons=1, min_grains=1)
    rows = _training_rows(30)
    _, model_run_id = await execute_final_target_training(
        residual_sqlite_session,
        final_target_rows=rows,
        config=config,
    )
    cutoff = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    predict_rows = tuple(row for row in rows if row.include and row.split == ResidualSplit.TRAIN)[
        :2
    ]
    request = FinalTargetPredictionRequest(
        model_run_id=model_run_id,
        forecast_cutoff_at=cutoff,
        prediction_rows=predict_rows,
    )
    loaded, prediction_run_id = await execute_final_target_prediction(
        residual_sqlite_session,
        request=request,
    )
    assert prediction_run_id > 0
    assert loaded.input_snapshot.get("prediction_target_kind") == "FINAL_TARGET_QUANTILE"
    assert len(loaded.final_target_rows) == len(predict_rows) * 3
    assert all(row.model_run_id == model_run_id for row in loaded.final_target_rows)
    assert all(row.prediction_run_id == prediction_run_id for row in loaded.final_target_rows)
