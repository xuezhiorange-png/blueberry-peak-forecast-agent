from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal


def _feature(
    *,
    feature_name: str,
    value: Decimal | int | str | bool | None = Decimal("1"),
    known_at: datetime | None = None,
    source_available_at: datetime | None = None,
    observation_date: date | None = None,
) -> dict[str, object]:
    return {
        "feature_name": feature_name,
        "value": value,
        "known_at": known_at or datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        "source_ref": {"source": feature_name},
        "source_version": "v1",
        "source_available_at": source_available_at or datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        "observation_date": observation_date,
    }


def test_allowlisted_features_pass_visibility_audit() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    audit = audit_feature_visibility(
        features=[
            FeatureValue.model_validate(
                _feature(
                    feature_name="structural_arrival_p50_kg",
                    known_at=datetime(2026, 3, 1, 11, 0, tzinfo=UTC),
                    source_available_at=datetime(2026, 3, 1, 11, 0, tzinfo=UTC),
                )
            ),
            FeatureValue.model_validate(
                _feature(
                    feature_name="actual_receipt_lag_1d_kg",
                    observation_date=date(2026, 2, 28),
                )
            ),
        ],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        for_training=True,
    )

    assert audit.status == "completed"
    assert not audit.blockers


def test_unknown_feature_is_blocked() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    audit = audit_feature_visibility(
        features=[FeatureValue.model_validate(_feature(feature_name="mystery_feature"))],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        for_training=True,
    )

    assert audit.status == "blocked"
    assert audit.blockers[0].code == "UNKNOWN_FEATURE"


def test_blocklisted_feature_is_blocked() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    audit = audit_feature_visibility(
        features=[
            FeatureValue.model_validate(_feature(feature_name="target_date_actual_receipt_kg"))
        ],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        for_training=True,
    )

    assert audit.status == "blocked"
    assert audit.blockers[0].code == "BLOCKLISTED_FEATURE"


def test_future_available_at_is_blocked() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    audit = audit_feature_visibility(
        features=[
            FeatureValue.model_validate(
                _feature(
                    feature_name="weather_7d_rainfall",
                    source_available_at=datetime(2026, 3, 2, 0, 0, tzinfo=UTC),
                )
            )
        ],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        for_training=True,
    )

    assert audit.status == "blocked"
    assert audit.blockers[0].code == "FUTURE_AVAILABLE_AT"


def test_mixed_naive_and_aware_datetimes_are_normalized_for_visibility() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    audit = audit_feature_visibility(
        features=[
            FeatureValue.model_validate(
                _feature(
                    feature_name="weather_7d_rainfall",
                    known_at=datetime(2026, 3, 1, 12, 0),
                    source_available_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
                )
            ),
            FeatureValue.model_validate(
                _feature(
                    feature_name="weather_7d_gdd",
                    known_at=datetime(2026, 3, 1, 11, 0, tzinfo=UTC),
                    source_available_at=datetime(2026, 3, 1, 11, 0),
                )
            ),
        ],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        for_training=True,
    )

    assert audit.status == "completed"
    assert not audit.blockers


def test_target_date_actual_is_blocked_for_historical_lag_feature() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    audit = audit_feature_visibility(
        features=[
            FeatureValue.model_validate(
                _feature(
                    feature_name="actual_receipt_lag_1d_kg",
                    observation_date=date(2026, 3, 1),
                )
            )
        ],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        for_training=True,
    )

    assert audit.status == "blocked"
    assert audit.blockers[0].code == "TARGET_DATE_ACTUAL_FEATURE"


def test_same_day_post_cutoff_known_at_is_blocked() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    audit = audit_feature_visibility(
        features=[
            FeatureValue.model_validate(
                _feature(
                    feature_name="weather_7d_rainfall",
                    known_at=datetime(2026, 3, 1, 5, 0, tzinfo=UTC),
                    source_available_at=datetime(2026, 3, 1, 3, 0, tzinfo=UTC),
                )
            )
        ],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 4, 0, tzinfo=UTC),
        for_training=True,
    )

    assert audit.status == "blocked"
    assert audit.blockers[0].code == "FUTURE_KNOWN_AT"


def test_same_day_post_cutoff_available_at_is_blocked() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    audit = audit_feature_visibility(
        features=[
            FeatureValue.model_validate(
                _feature(
                    feature_name="weather_7d_rainfall",
                    known_at=datetime(2026, 3, 1, 3, 0, tzinfo=UTC),
                    source_available_at=datetime(2026, 3, 1, 5, 0, tzinfo=UTC),
                )
            )
        ],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 4, 0, tzinfo=UTC),
        for_training=True,
    )

    assert audit.status == "blocked"
    assert audit.blockers[0].code == "FUTURE_AVAILABLE_AT"


def test_cutoff_equality_is_inclusive_for_known_and_available_at() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    exact_cutoff = datetime(2026, 3, 15, 4, 0, tzinfo=UTC)
    audit = audit_feature_visibility(
        features=[
            FeatureValue.model_validate(
                _feature(
                    feature_name="weather_7d_rainfall",
                    known_at=exact_cutoff,
                    source_available_at=exact_cutoff,
                )
            )
        ],
        as_of_date=date(2026, 3, 15),
        forecast_cutoff_at=exact_cutoff,
        for_training=True,
    )

    assert audit.status == "completed"
    assert not audit.blockers


def test_audit_hash_binds_exact_forecast_cutoff() -> None:
    from backend.app.residual_model.schemas import FeatureValue
    from backend.app.residual_model.visibility import audit_feature_visibility

    feature = FeatureValue.model_validate(
        _feature(
            feature_name="weather_7d_rainfall",
            known_at=datetime(2026, 3, 1, 3, 0, tzinfo=UTC),
            source_available_at=datetime(2026, 3, 1, 3, 0, tzinfo=UTC),
        )
    )
    first = audit_feature_visibility(
        features=[feature],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 4, 0, tzinfo=UTC),
        for_training=True,
    )
    second = audit_feature_visibility(
        features=[feature],
        as_of_date=date(2026, 3, 1),
        forecast_cutoff_at=datetime(2026, 3, 1, 5, 0, tzinfo=UTC),
        for_training=True,
    )

    assert first.status == "completed"
    assert second.status == "completed"
    assert first.audit_hash != second.audit_hash
