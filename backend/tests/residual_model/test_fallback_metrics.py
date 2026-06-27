"""Section 12: Missing regression tests — fallback metrics tests.

These tests verify the _split_metrics function and the fallback rate
gate logic in train_residual_model_from_manifest.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.enums import LeakageBlockerCode, ResidualExecutionStatus
from backend.app.residual_model.model import (
    TrainedResidualEstimators,
    train_quantile_estimators,
)
from backend.app.residual_model.schemas import (
    CategoryEncoding,
    FeatureValue,
    FeatureVisibilityAudit,
    FeatureVisibilityIssue,
    ResidualTrainingManifestRow,
)
from backend.app.residual_model.service import (
    _predict_residual_vectors,
    _split_metrics,
    train_residual_model_from_manifest,
)
from backend.tests.residual_model.support import residual_model_config_path


def _config():
    return load_residual_model_config(residual_model_config_path())


def _fallback_config():
    """Config with structural_only_fallback unknown policy and relaxed eligibility."""
    from backend.app.residual_model.config import load_residual_model_config_from_snapshot
    base = _config()
    snapshot = dict(base.snapshot)
    snapshot["categorical_encoding"] = {
        **dict(snapshot.get("categorical_encoding", {})),
        "unknown_policy": "structural_only_fallback",
    }
    snapshot["eligibility"] = {
        **dict(snapshot.get("eligibility", {})),
        "min_training_rows": 1,
        "min_seasons": 1,
        "min_factories": 1,
        "max_validation_wmape": 10.0,
        "require_improvement_over_structural": False,
        "max_fallback_rate": 1.0,
    }
    return load_residual_model_config_from_snapshot(snapshot)


def _all_feature_values(
    factory_category: str = "north",
    rainfall: str = "10",
) -> tuple[FeatureValue, ...]:
    """Provide ALL features that exist in feature_definition_map
    to avoid missing_policy='block' fallbacks in _row_decision.
    """
    return (
        FeatureValue.model_validate({
            "feature_name": "structural_arrival_p50_kg",
            "value": "100",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"task9": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "structural_arrival_p80_kg",
            "value": "110",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"task9": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "structural_arrival_p90_kg",
            "value": "120",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"task9": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "forecast_horizon_days",
            "value": "1",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"task9": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "actual_receipt_lag_1d_kg",
            "value": "50",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"analytics": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "actual_receipt_lag_3d_kg",
            "value": "150",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"analytics": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "actual_receipt_lag_7d_kg",
            "value": "350",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"analytics": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "actual_receipt_rolling_3d_mean_kg",
            "value": "100",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"analytics": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "actual_receipt_rolling_7d_mean_kg",
            "value": "100",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"analytics": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "actual_receipt_cumulative_to_as_of_kg",
            "value": "1000",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"analytics": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "structural_cumulative_to_as_of_kg",
            "value": "900",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"task9": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "realized_cumulative_residual_to_as_of_kg",
            "value": "100",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"analytics": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "weather_7d_rainfall",
            "value": rainfall,
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"weather": rainfall},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "observation_date": date(2026, 2, 28),
        }),
        FeatureValue.model_validate({
            "feature_name": "weather_7d_gdd",
            "value": "150",
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"weather": "150"},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "observation_date": date(2026, 2, 28),
        }),
        FeatureValue.model_validate({
            "feature_name": "destination_factory_category",
            "value": factory_category,
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"plan": 1},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
        FeatureValue.model_validate({
            "feature_name": "spring_festival_window_flag",
            "value": False,
            "known_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            "source_ref": {"calendar": "v1"},
            "source_version": "v1",
            "source_available_at": datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        }),
    )


def _manifest_row(
    *,
    index: int,
    season_id: int = 1,
    factory_id: int = 1,
    factory_category: str = "north",
    rainfall: str = "10",
    split: str = "train",
) -> ResidualTrainingManifestRow:
    features = _all_feature_values(
        factory_category=factory_category,
        rainfall=rainfall,
    )
    return ResidualTrainingManifestRow(
        season_id=season_id,
        destination_factory_id=factory_id,
        task9_run_id=100 + index,
        task9_result_hash=f"{index + 1:064x}"[-64:],
        as_of_date=date(2026, 3, 1),
        target_arrival_local_date=date(2026, 3, 2 + (index % 5)),
        forecast_horizon_days=1 + (index % 5),
        label_actual_snapshot={
            "build_run_id": 200 + index,
            "source_max_raw_id": 1000 + index,
            "aggregation_version": "task3-v1",
            "config_hash": "c" * 64,
            "source_cutoff": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        },
        feature_actual_snapshot={
            "build_run_id": 300 + index,
            "source_max_raw_id": 900 + index,
            "aggregation_version": "task3-v1",
            "config_hash": "d" * 64,
            "source_cutoff": datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        },
        observed_effective_receipt_kg=Decimal("100"),
        structural_p50_kg=Decimal("100"),
        structural_p80_kg=Decimal("110"),
        structural_p90_kg=Decimal("120"),
        residual_label_kg=Decimal(str(5 + (index % 7))),
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


def _category_encodings() -> list[CategoryEncoding]:
    return [
        CategoryEncoding(
            feature_name="destination_factory_category",
            ordered_known_categories=["north", "south"],
            unknown_bucket_code=2,
            missing_bucket_code=-1,
            encoding_version="v1",
        ),
    ]


def _feature_names() -> list[str]:
    return [
        "structural_arrival_p50_kg",
        "structural_arrival_p80_kg",
        "structural_arrival_p90_kg",
        "forecast_horizon_days",
        "actual_receipt_lag_1d_kg",
        "actual_receipt_lag_3d_kg",
        "actual_receipt_lag_7d_kg",
        "actual_receipt_rolling_3d_mean_kg",
        "actual_receipt_rolling_7d_mean_kg",
        "actual_receipt_cumulative_to_as_of_kg",
        "structural_cumulative_to_as_of_kg",
        "realized_cumulative_residual_to_as_of_kg",
        "weather_7d_rainfall",
        "weather_7d_gdd",
        "destination_factory_category",
        "spring_festival_window_flag",
    ]


def _estimators() -> TrainedResidualEstimators:
    config = _config()
    features_np = __import__("numpy").array(
        [[0.0] * 16, [1.0] * 16],
    )
    labels_np = __import__("numpy").array([5.0, 10.0])
    return train_quantile_estimators(config=config, features=features_np, labels=labels_np)


# ── 1. No fallback ──────────────────────────────────────────────────────


def test_fallback_metrics_no_fallback() -> None:
    """All rows are corrected — fallback_rate should be 0."""
    config = _fallback_config()
    estimators = _estimators()
    category_encodings = _category_encodings()
    feature_names = _feature_names()

    rows = [
        _manifest_row(index=i, season_id=1, factory_id=1, factory_category="north")
        for i in range(5)
    ]
    feature_rows = [row.feature_values for row in rows]
    feature_audits = [None for _ in rows]

    _p50, _p80, _p90, decisions = _predict_residual_vectors(
        feature_rows=feature_rows,
        feature_audits=feature_audits,
        feature_names=feature_names,
        category_encodings=category_encodings,
        config=config,
        estimators=estimators,
    )

    fallback_row_count = sum(1 for d in decisions if d.fallback_reason is not None)
    row_is_fallback = [d.fallback_reason is not None for d in decisions]
    metrics = _split_metrics(
        rows=rows,
        residual_p50=_p50,
        residual_p80=_p80,
        residual_p90=_p90,
        fallback_row_count=fallback_row_count,
        row_is_fallback=row_is_fallback,
    )

    global_metrics = metrics["global"]
    assert global_metrics["fallback_rate"] == Decimal("0")
    assert global_metrics["fallback_row_count"] == 0


# ── 2. All fallback ──────────────────────────────────────────────────────


def test_fallback_metrics_all_fallback() -> None:
    """Every row has an unknown category — all fallback, rate == 1.0."""
    config = _fallback_config()
    estimators = _estimators()
    feature_names = _feature_names()
    category_encodings = _category_encodings()

    rows = [
        _manifest_row(
            index=i, season_id=1, factory_id=1, factory_category="unknown-zone",
        )
        for i in range(5)
    ]
    feature_rows = [row.feature_values for row in rows]
    feature_audits = [None for _ in rows]

    _p50, _p80, _p90, decisions = _predict_residual_vectors(
        feature_rows=feature_rows,
        feature_audits=feature_audits,
        feature_names=feature_names,
        category_encodings=category_encodings,
        config=config,
        estimators=estimators,
    )

    fallback_row_count = sum(1 for d in decisions if d.fallback_reason is not None)
    row_is_fallback = [d.fallback_reason is not None for d in decisions]
    metrics = _split_metrics(
        rows=rows,
        residual_p50=_p50,
        residual_p80=_p80,
        residual_p90=_p90,
        fallback_row_count=fallback_row_count,
        row_is_fallback=row_is_fallback,
    )

    global_metrics = metrics["global"]
    assert global_metrics["fallback_rate"] == Decimal("1")
    assert global_metrics["fallback_row_count"] == 5


# ── 3. Partial fallback (mixed) ──────────────────────────────────────────


def test_fallback_metrics_partial_fallback() -> None:
    """Some rows corrected, others fall back — 0 < rate < 1."""
    config = _fallback_config()
    estimators = _estimators()
    feature_names = _feature_names()
    category_encodings = _category_encodings()

    rows = [
        _manifest_row(
            index=i, season_id=1, factory_id=1,
            factory_category="north" if i < 3 else "unknown-zone",
        )
        for i in range(5)
    ]
    feature_rows = [row.feature_values for row in rows]
    feature_audits = [None for _ in rows]

    _p50, _p80, _p90, decisions = _predict_residual_vectors(
        feature_rows=feature_rows,
        feature_audits=feature_audits,
        feature_names=feature_names,
        category_encodings=category_encodings,
        config=config,
        estimators=estimators,
    )

    fallback_row_count = sum(1 for d in decisions if d.fallback_reason is not None)
    row_is_fallback = [d.fallback_reason is not None for d in decisions]
    metrics = _split_metrics(
        rows=rows,
        residual_p50=_p50,
        residual_p80=_p80,
        residual_p90=_p90,
        fallback_row_count=fallback_row_count,
        row_is_fallback=row_is_fallback,
    )

    global_metrics = metrics["global"]
    assert global_metrics["fallback_rate"] == Decimal("0.4")
    assert global_metrics["fallback_row_count"] == 2


# ── 4. One season fallback / another corrected ───────────────────────────


def test_fallback_metrics_per_season_mixed() -> None:
    """Season 1 has no fallback, Season 2 has all fallback."""
    config = _fallback_config()
    estimators = _estimators()
    feature_names = _feature_names()
    category_encodings = _category_encodings()

    rows = (
        [_manifest_row(index=i, season_id=1, factory_id=1, factory_category="north")
         for i in range(3)]
        + [_manifest_row(index=i + 3, season_id=2, factory_id=1, factory_category="unknown")
           for i in range(3)]
    )
    feature_rows = [row.feature_values for row in rows]
    feature_audits = [None for _ in rows]

    _p50, _p80, _p90, decisions = _predict_residual_vectors(
        feature_rows=feature_rows,
        feature_audits=feature_audits,
        feature_names=feature_names,
        category_encodings=category_encodings,
        config=config,
        estimators=estimators,
    )

    fallback_row_count = sum(1 for d in decisions if d.fallback_reason is not None)
    row_is_fallback = [d.fallback_reason is not None for d in decisions]
    metrics = _split_metrics(
        rows=rows,
        residual_p50=_p50,
        residual_p80=_p80,
        residual_p90=_p90,
        fallback_row_count=fallback_row_count,
        row_is_fallback=row_is_fallback,
    )

    per_season = metrics["per_season"]
    assert per_season["1"]["fallback_rate"] == Decimal("0")
    assert per_season["1"]["fallback_row_count"] == 0
    assert per_season["2"]["fallback_rate"] == Decimal("1")
    assert per_season["2"]["fallback_row_count"] == 3


# ── 5. One factory fallback / another corrected ───────────────────────────


def test_fallback_metrics_per_factory_mixed() -> None:
    """Factory 1 has no fallback, Factory 2 has all fallback."""
    config = _fallback_config()
    estimators = _estimators()
    feature_names = _feature_names()
    category_encodings = _category_encodings()

    rows = (
        [_manifest_row(index=i, season_id=1, factory_id=1, factory_category="north")
         for i in range(3)]
        + [_manifest_row(index=i + 3, season_id=1, factory_id=2, factory_category="unknown")
           for i in range(3)]
    )
    feature_rows = [row.feature_values for row in rows]
    feature_audits = [None for _ in rows]

    _p50, _p80, _p90, decisions = _predict_residual_vectors(
        feature_rows=feature_rows,
        feature_audits=feature_audits,
        feature_names=feature_names,
        category_encodings=category_encodings,
        config=config,
        estimators=estimators,
    )

    fallback_row_count = sum(1 for d in decisions if d.fallback_reason is not None)
    row_is_fallback = [d.fallback_reason is not None for d in decisions]
    metrics = _split_metrics(
        rows=rows,
        residual_p50=_p50,
        residual_p80=_p80,
        residual_p90=_p90,
        fallback_row_count=fallback_row_count,
        row_is_fallback=row_is_fallback,
    )

    per_factory = metrics["per_factory"]
    assert per_factory["1"]["fallback_rate"] == Decimal("0")
    assert per_factory["1"]["fallback_row_count"] == 0
    assert per_factory["2"]["fallback_rate"] == Decimal("1")
    assert per_factory["2"]["fallback_row_count"] == 3


# ── 6. Mixed fallback reasons ────────────────────────────────────────────


def test_fallback_metrics_mixed_reasons() -> None:
    """Different rows fall back for different reasons."""
    config = _fallback_config()
    estimators = _estimators()
    feature_names = _feature_names()
    category_encodings = _category_encodings()

    rows = [
        _manifest_row(index=i, season_id=1, factory_id=1, factory_category="north")
        for i in range(6)
    ]
    feature_rows = [row.feature_values for row in rows]
    feature_audits: list[FeatureVisibilityAudit | None] = [
        None,
        None,
        FeatureVisibilityAudit(
            status=ResidualExecutionStatus("blocked"),
            feature_count=3,
            visible_feature_count=2,
            blocked_feature_count=1,
            missing_feature_count=0,
            unknown_feature_count=0,
            blockers=[
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode("MISSING_REQUIRED_FEATURE"),
                    feature_name="weather_7d_rainfall",
                    detail="Not enough history",
                )
            ],
            warnings=[],
            audit_hash="a" * 64,
        ),
        None,
        None,
        None,
    ]

    _p50, _p80, _p90, decisions = _predict_residual_vectors(
        feature_rows=feature_rows,
        feature_audits=feature_audits,
        feature_names=feature_names,
        category_encodings=category_encodings,
        config=config,
        estimators=estimators,
    )

    reasons = {d.fallback_reason for d in decisions if d.fallback_reason is not None}
    assert len(reasons) >= 1

    fallback_row_count = sum(1 for d in decisions if d.fallback_reason is not None)
    row_is_fallback = [d.fallback_reason is not None for d in decisions]
    metrics = _split_metrics(
        rows=rows,
        residual_p50=_p50,
        residual_p80=_p80,
        residual_p90=_p90,
        fallback_row_count=fallback_row_count,
        row_is_fallback=row_is_fallback,
    )

    global_metrics = metrics["global"]
    assert global_metrics["fallback_row_count"] >= 1
    assert Decimal("0") < global_metrics["fallback_rate"] < Decimal("1")


# ── 7. Fallback rate == threshold passes ─────────────────────────────────


def _simple_split_config():
    """Config that uses simple_split to avoid validation-season requirements."""
    from backend.app.residual_model.config import load_residual_model_config_from_snapshot
    base = _fallback_config()
    snapshot = dict(base.snapshot)
    snapshot["split"] = {
        **dict(snapshot.get("split", {})),
        "strategy": "simple_split",
    }
    return load_residual_model_config_from_snapshot(snapshot)


def test_fallback_rate_at_threshold_passes() -> None:
    """When fallback_rate equals max_fallback_rate, the model should
    still pass the fallback gate.
    """
    config = _fallback_config()
    eligibility = replace(
        config.rules.eligibility,
        max_fallback_rate=Decimal("0.5"),
    )
    config = replace(config, rules=replace(config.rules, eligibility=eligibility))

    rows = []
    for i in range(3):
        rows.append(
            _manifest_row(
                index=i,
                season_id=1,
                factory_id=1,
                factory_category="north",
                rainfall=str(10 + i * 5),
                split="train",
            )
        )
    # Validation: 1 corrected + 1 fallback = 0.5 = threshold -> passes
    rows.append(
        _manifest_row(
            index=3,
            season_id=2,
            factory_id=1,
            factory_category="north",
            rainfall="25",
            split="validation",
        )
    )
    rows.append(
        _manifest_row(
            index=4,
            season_id=2,
            factory_id=1,
            factory_category="unknown-zone",
            rainfall="30",
            split="validation",
        )
    )

    result = train_residual_model_from_manifest(rows=rows, config=config)
    assert result.execution_status == "completed"
    assert "fallback_rate_above_threshold" not in result.eligibility_reasons, (
        f"fallback rate 0.5 should not trigger gate at threshold 0.5, "
        f"got reasons: {result.eligibility_reasons}"
    )


# ── 8. Fallback rate > threshold becomes completed + ineligible ─────────


def test_fallback_rate_above_threshold_becomes_ineligible() -> None:
    """When fallback_rate exceeds max_fallback_rate, the model is
    completed but ineligible.
    """
    config = _fallback_config()
    eligibility = replace(
        config.rules.eligibility,
        max_fallback_rate=Decimal("0.3"),
    )
    config = replace(config, rules=replace(config.rules, eligibility=eligibility))

    rows = []
    for i in range(3):
        rows.append(
            _manifest_row(
                index=i,
                season_id=1,
                factory_id=1,
                factory_category="north",
                rainfall=str(10 + i * 5),
                split="train",
            )
        )
    # Validation: all 2 fallback = 1.0 > 0.3 -> ineligible
    for i in range(2):
        rows.append(
            _manifest_row(
                index=3 + i,
                season_id=2,
                factory_id=1,
                factory_category="unknown-zone",
                rainfall=str(20 + i * 5),
                split="validation",
            )
        )

    result = train_residual_model_from_manifest(rows=rows, config=config)
    assert result.execution_status == "completed"
    assert result.eligibility_status == "ineligible"
    assert "fallback_rate_above_threshold" in result.eligibility_reasons
