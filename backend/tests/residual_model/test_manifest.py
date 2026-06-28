from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.schemas import FeatureValue, ResidualTrainingManifestRow


def _row(*, destination_factory_id: int = 1, rainfall: str = "3") -> ResidualTrainingManifestRow:
    feature = FeatureValue.model_validate(
        {
            "feature_name": "weather_7d_rainfall",
            "value": rainfall,
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"row": rainfall},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "observation_date": date(2026, 2, 28),
        }
    )
    feature_hash = canonical_payload_hash([feature.model_dump(mode="json")])
    return ResidualTrainingManifestRow(
        season_id=1,
        destination_factory_id=destination_factory_id,
        task9_run_id=11,
        task9_result_hash="a" * 64,
        as_of_date=date(2026, 3, 1),
        target_arrival_local_date=date(2026, 3, 2),
        forecast_horizon_days=1,
        label_actual_snapshot={
            "build_run_id": 21,
            "source_max_raw_id": 101,
            "aggregation_version": "task3-v1",
            "config_hash": "c" * 64,
            "source_cutoff": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        },
        feature_actual_snapshot={
            "build_run_id": 22,
            "source_max_raw_id": 99,
            "aggregation_version": "task3-v1",
            "config_hash": "d" * 64,
            "source_cutoff": datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        },
        observed_effective_receipt_kg=Decimal("120"),
        structural_p50_kg=Decimal("100"),
        structural_p80_kg=Decimal("110"),
        structural_p90_kg=Decimal("125"),
        residual_label_kg=Decimal("20"),
        feature_values=(feature,),
        feature_vector_hash=feature_hash,
        feature_visibility_audit_hash="b" * 64,
        split="train",
        include=True,
        sample_weight=Decimal("1"),
        exclusion_reason=None,
        source_refs=("task9:11", "analytics:21"),
    )


def test_manifest_hash_is_order_invariant() -> None:
    from backend.app.residual_model.manifest import manifest_hash

    row_a = _row(destination_factory_id=1)
    row_b = _row(destination_factory_id=2)
    assert manifest_hash([row_a, row_b]) == manifest_hash([row_b, row_a])


def test_manifest_hash_changes_when_source_changes() -> None:
    from backend.app.residual_model.manifest import manifest_hash

    row_a = _row(rainfall="3")
    row_b = _row(rainfall="4")
    assert manifest_hash([row_a]) != manifest_hash([row_b])


def test_manifest_hash_changes_when_feature_snapshot_changes() -> None:
    from backend.app.residual_model.manifest import manifest_hash

    row_a = _row()
    row_b = row_a.model_copy(
        update={
            "feature_actual_snapshot": row_a.feature_actual_snapshot.model_copy(
                update={"build_run_id": 23}
            )
        }
    )

    assert manifest_hash([row_a]) != manifest_hash([row_b])
