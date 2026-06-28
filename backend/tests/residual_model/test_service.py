from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.schemas import FeatureValue, ResidualTrainingManifestRow
from backend.tests.residual_model.support import residual_model_config_path


def _training_row(
    *,
    season_id: int,
    factory_id: int,
    target_date: date,
    rainfall: str,
    residual: str,
    split: str = "train",
) -> ResidualTrainingManifestRow:
    features = (
        FeatureValue.model_validate(
            {
                "feature_name": "structural_arrival_p50_kg",
                "value": "100",
                "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                "source_ref": {"task9": 1},
                "source_version": "v1",
                "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            }
        ),
        FeatureValue.model_validate(
            {
                "feature_name": "weather_7d_rainfall",
                "value": rainfall,
                "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                "source_ref": {"weather": rainfall},
                "source_version": "v1",
                "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                "observation_date": date(2026, 2, 28),
            }
        ),
        FeatureValue.model_validate(
            {
                "feature_name": "destination_factory_category",
                "value": "north",
                "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                "source_ref": {"plan": factory_id},
                "source_version": "v1",
                "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            }
        ),
    )
    return ResidualTrainingManifestRow(
        season_id=season_id,
        destination_factory_id=factory_id,
        task9_run_id=100 + season_id,
        task9_result_hash=f"{season_id:064x}"[-64:],
        as_of_date=date(2026, 3, 1),
        target_arrival_local_date=target_date,
        forecast_horizon_days=1,
        label_actual_snapshot={
            "build_run_id": 200 + season_id,
            "source_max_raw_id": 1000 + season_id,
            "aggregation_version": "task3-v1",
            "config_hash": "c" * 64,
            "source_cutoff": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        },
        feature_actual_snapshot={
            "build_run_id": 300 + season_id,
            "source_max_raw_id": 900 + season_id,
            "aggregation_version": "task3-v1",
            "config_hash": "d" * 64,
            "source_cutoff": datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        },
        observed_effective_receipt_kg=Decimal("100") + Decimal(residual),
        structural_p50_kg=Decimal("100"),
        structural_p80_kg=Decimal("110"),
        structural_p90_kg=Decimal("120"),
        residual_label_kg=Decimal(residual),
        feature_values=features,
        feature_vector_hash=canonical_payload_hash(
            [item.model_dump(mode="json") for item in features]
        ),
        feature_visibility_audit_hash="a" * 64,
        split=split,
        include=True,
        sample_weight=Decimal("1"),
        source_refs=("task9", "analytics"),
    )


def test_structural_only_fallback_for_ineligible_model() -> None:
    from backend.app.residual_model.config import load_residual_model_config
    from backend.app.residual_model.service import train_residual_model_from_manifest

    config = load_residual_model_config(residual_model_config_path())
    row = _training_row(
        season_id=1,
        factory_id=1,
        target_date=date(2026, 3, 2),
        rainfall="3",
        residual="5",
    )
    result = train_residual_model_from_manifest(rows=[row], config=config)

    assert result.execution_status == "completed"
    assert result.eligibility_status == "ineligible"
    assert "insufficient_training_rows" in result.eligibility_reasons
    assert result.artifacts == ()


def test_completed_eligible_training_emits_three_quantile_artifacts() -> None:
    from dataclasses import replace

    from backend.app.residual_model.config import load_residual_model_config
    from backend.app.residual_model.service import train_residual_model_from_manifest

    config = load_residual_model_config(residual_model_config_path())
    relaxed = replace(
        config,
        rules=replace(
            config.rules,
            eligibility=replace(
                config.rules.eligibility,
                min_training_rows=1,
                min_seasons=1,
                min_factories=1,
                max_validation_wmape=1.0,
                require_improvement_over_structural=False,
                max_fallback_rate=1.0,
            ),
        ),
    )
    rows = [
        _training_row(
            season_id=(index % 2) + 1 if index < 20 else 3,
            factory_id=(index % 2) + 1,
            target_date=date(2026, 3, 2 + (index % 5)),
            rainfall=str(3 + (index % 4)),
            residual=str(5 + (index % 6)),
            split="train" if index < 20 else "validation",
        )
        for index in range(30)
    ]

    result = train_residual_model_from_manifest(rows=rows, config=relaxed)

    assert result.execution_status == "completed"
    assert result.eligibility_status == "eligible"
    assert [item.quantile_label for item in result.artifacts] == ["P50", "P80", "P90"]


def test_leave_one_season_out_requires_validation_season() -> None:
    from backend.app.residual_model.config import load_residual_model_config
    from backend.app.residual_model.service import train_residual_model_from_manifest

    config = load_residual_model_config(residual_model_config_path())
    rows = [
        _training_row(
            season_id=(index % 3) + 1,
            factory_id=(index % 2) + 1,
            target_date=date(2026, 3, 2 + (index % 5)),
            rainfall=str(3 + (index % 4)),
            residual=str(5 + (index % 6)),
            split="train",
        )
        for index in range(30)
    ]

    result = train_residual_model_from_manifest(rows=rows, config=config)

    assert result.execution_status == "completed"
    assert result.eligibility_status == "ineligible"
    assert "missing_validation_season" in result.eligibility_reasons


def test_leave_one_season_out_rejects_train_test_overlap() -> None:
    from dataclasses import replace

    from backend.app.residual_model.config import load_residual_model_config
    from backend.app.residual_model.service import train_residual_model_from_manifest

    config = load_residual_model_config(residual_model_config_path())
    relaxed = replace(
        config,
        rules=replace(
            config.rules,
            eligibility=replace(
                config.rules.eligibility,
                min_training_rows=1,
                min_seasons=1,
                min_factories=1,
                require_improvement_over_structural=False,
                max_validation_wmape=1.0,
                max_fallback_rate=1.0,
            ),
        ),
    )
    rows = [
        _training_row(
            season_id=1,
            factory_id=1,
            target_date=date(2026, 3, 2),
            rainfall="3",
            residual="5",
            split="train",
        ),
        _training_row(
            season_id=2,
            factory_id=1,
            target_date=date(2026, 3, 3),
            rainfall="4",
            residual="6",
            split="validation",
        ),
        _training_row(
            season_id=1,
            factory_id=2,
            target_date=date(2026, 3, 4),
            rainfall="5",
            residual="7",
            split="test",
        ),
    ]

    result = train_residual_model_from_manifest(rows=rows, config=relaxed)

    assert result.execution_status == "completed"
    assert result.eligibility_status == "ineligible"
    assert "train_test_season_overlap" in result.eligibility_reasons


def test_prediction_input_signature_is_independent_from_output_fields() -> None:
    from backend.app.residual_model.service import structural_only_prediction

    first = structural_only_prediction(
        model_run_id=1,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash="b" * 64,
        structural_rows=[
            {
                "destination_factory_id": 1,
                "arrival_local_date": date(2026, 3, 2),
                "forecast_horizon_days": 1,
                "structural_p50_kg": Decimal("100"),
                "structural_p80_kg": Decimal("110"),
                "structural_p90_kg": Decimal("120"),
            }
        ],
        fallback_reason="model_ineligible",
        warnings=("warning-a",),
    )
    second = structural_only_prediction(
        model_run_id=1,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash="b" * 64,
        structural_rows=[
            {
                "destination_factory_id": 1,
                "arrival_local_date": date(2026, 3, 2),
                "forecast_horizon_days": 1,
                "structural_p50_kg": Decimal("100"),
                "structural_p80_kg": Decimal("110"),
                "structural_p90_kg": Decimal("120"),
            }
        ],
        fallback_reason="artifact_validation_failed",
        warnings=("warning-b",),
    )

    assert first.prediction_input_signature == second.prediction_input_signature
    assert first.prediction_hash != second.prediction_hash


def test_validation_unknown_categories_drive_structural_only_fallback_rate() -> None:
    from dataclasses import replace

    from backend.app.residual_model.config import load_residual_model_config
    from backend.app.residual_model.service import train_residual_model_from_manifest

    config = load_residual_model_config(residual_model_config_path())
    relaxed = replace(
        config,
        rules=replace(
            config.rules,
            eligibility=replace(
                config.rules.eligibility,
                min_training_rows=1,
                min_seasons=1,
                min_factories=1,
                require_improvement_over_structural=False,
                max_validation_wmape=1.0,
                max_fallback_rate=Decimal("0.5"),
            ),
        ),
    )
    rows = [
        _training_row(
            season_id=1,
            factory_id=1,
            target_date=date(2026, 3, 2),
            rainfall="3",
            residual="5",
            split="train",
        ),
        _training_row(
            season_id=1,
            factory_id=2,
            target_date=date(2026, 3, 3),
            rainfall="4",
            residual="6",
            split="train",
        ),
        _training_row(
            season_id=2,
            factory_id=1,
            target_date=date(2026, 3, 4),
            rainfall="5",
            residual="7",
            split="validation",
        ),
        _training_row(
            season_id=2,
            factory_id=2,
            target_date=date(2026, 3, 5),
            rainfall="6",
            residual="8",
            split="validation",
        ),
    ]
    rows[2] = rows[2].model_copy(
        update={
            "feature_values": tuple(
                item.model_copy(update={"value": "validation-only"})
                if item.feature_name == "destination_factory_category"
                else item
                for item in rows[2].feature_values
            )
        }
    )
    rows[3] = rows[3].model_copy(
        update={
            "feature_values": tuple(
                item.model_copy(update={"value": "validation-only"})
                if item.feature_name == "destination_factory_category"
                else item
                for item in rows[3].feature_values
            )
        }
    )

    result = train_residual_model_from_manifest(rows=rows, config=relaxed)

    validation_global = result.metrics["validation"]["global"]
    assert result.execution_status == "completed"
    assert result.eligibility_status == "ineligible"
    assert "fallback_rate_above_threshold" in result.eligibility_reasons
    assert validation_global["fallback_row_count"] == 2
    assert validation_global["evaluated_row_count"] == 2
    assert validation_global["fallback_rate"] == Decimal("1")


def test_structural_only_preserves_structural_values() -> None:
    from backend.app.residual_model.service import structural_only_prediction

    result = structural_only_prediction(
        model_run_id=1,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash="b" * 64,
        structural_rows=[
            {
                "destination_factory_id": 1,
                "arrival_local_date": date(2026, 3, 2),
                "forecast_horizon_days": 1,
                "structural_p50_kg": Decimal("100"),
                "structural_p80_kg": Decimal("110"),
                "structural_p90_kg": Decimal("120"),
            }
        ],
        fallback_reason="model_ineligible",
    )

    assert result.execution_status == "completed"
    assert result.mode == "structural_only"
    assert result.rows[0].raw_residual_p50_kg == Decimal("0")
    assert result.rows[0].corrected_p50_kg == Decimal("100")
    assert result.rows[0].corrected_raw_p50_kg == Decimal("100")
    assert result.rows[0].corrected_raw_p80_kg == Decimal("100")
    assert result.rows[0].corrected_raw_p90_kg == Decimal("100")
    assert result.rows[0].corrected_p80_kg == Decimal("100")
    assert result.rows[0].corrected_p90_kg == Decimal("100")


def test_structural_only_prediction_hash_is_not_index_derived() -> None:
    from backend.app.residual_model.service import structural_only_prediction

    first = structural_only_prediction(
        model_run_id=1,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash="b" * 64,
        structural_rows=[
            {
                "destination_factory_id": 1,
                "arrival_local_date": date(2026, 3, 2),
                "forecast_horizon_days": 1,
                "structural_p50_kg": Decimal("100"),
                "structural_p80_kg": Decimal("110"),
                "structural_p90_kg": Decimal("120"),
            }
        ],
        fallback_reason="model_ineligible",
    )
    second = structural_only_prediction(
        model_run_id=2,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash="b" * 64,
        structural_rows=[
            {
                "destination_factory_id": 1,
                "arrival_local_date": date(2026, 3, 2),
                "forecast_horizon_days": 1,
                "structural_p50_kg": Decimal("100"),
                "structural_p80_kg": Decimal("110"),
                "structural_p90_kg": Decimal("120"),
            }
        ],
        fallback_reason="model_ineligible",
    )

    assert first.rows[0].prediction_hash != "0" * 64
    assert second.rows[0].prediction_hash != "0" * 64
    assert first.prediction_hash != second.prediction_hash
