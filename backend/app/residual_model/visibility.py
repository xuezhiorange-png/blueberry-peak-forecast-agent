from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.enums import (
    AvailabilityRule,
    LeakageBlockerCode,
    ResidualExecutionStatus,
)
from backend.app.residual_model.feature_registry import (
    blocklisted_features,
    feature_definition_map,
)
from backend.app.residual_model.schemas import (
    FeatureValue,
    FeatureVisibilityAudit,
    FeatureVisibilityIssue,
)


def _cutoff_end_of_day(as_of_date: date) -> datetime:
    return datetime.combine(as_of_date, time.max, tzinfo=UTC)


def _normalize_visibility_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def audit_feature_visibility(
    *,
    features: Sequence[FeatureValue],
    as_of_date: date,
    for_training: bool,
) -> FeatureVisibilityAudit:
    definitions = feature_definition_map()
    blockers: list[FeatureVisibilityIssue] = []
    warnings: list[str] = []
    visible_feature_count = 0
    unknown_feature_count = 0
    missing_feature_count = 0
    blocked_feature_count = 0
    cutoff = _cutoff_end_of_day(as_of_date)

    for feature in features:
        definition = definitions.get(feature.feature_name)
        if feature.feature_name in blocklisted_features():
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.BLOCKLISTED_FEATURE,
                    feature_name=feature.feature_name,
                    detail="Feature is explicitly blocklisted for Task 10.",
                )
            )
            blocked_feature_count += 1
            continue
        if definition is None:
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.UNKNOWN_FEATURE,
                    feature_name=feature.feature_name,
                    detail="Feature is not registered in the Task 10 allowlist.",
                )
            )
            unknown_feature_count += 1
            blocked_feature_count += 1
            continue
        if for_training and not definition.allow_for_training:
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.FEATURE_NOT_ALLOWED_FOR_TRAINING,
                    feature_name=feature.feature_name,
                    detail="Feature is not allowed for residual-model training.",
                )
            )
            blocked_feature_count += 1
            continue
        if not for_training and not definition.allow_for_prediction:
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.FEATURE_NOT_ALLOWED_FOR_PREDICTION,
                    feature_name=feature.feature_name,
                    detail="Feature is not allowed for residual-model prediction.",
                )
            )
            blocked_feature_count += 1
            continue
        if feature.value is None and definition.missing_policy.value == "block":
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.MISSING_REQUIRED_FEATURE,
                    feature_name=feature.feature_name,
                    detail="Required feature value is missing.",
                )
            )
            missing_feature_count += 1
            blocked_feature_count += 1
            continue
        known_at = _normalize_visibility_datetime(feature.known_at)
        source_available_at = _normalize_visibility_datetime(feature.source_available_at)
        if known_at > cutoff:
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.FUTURE_KNOWN_AT,
                    feature_name=feature.feature_name,
                    detail="Feature known_at is later than the as_of cutoff.",
                )
            )
            blocked_feature_count += 1
            continue
        if source_available_at > cutoff:
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.FUTURE_AVAILABLE_AT,
                    feature_name=feature.feature_name,
                    detail="Feature source_available_at is later than the as_of cutoff.",
                )
            )
            blocked_feature_count += 1
            continue
        if (
            definition.availability_rule == AvailabilityRule.HISTORICAL_ONLY
            and feature.observation_date is not None
            and feature.observation_date >= as_of_date
        ):
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.TARGET_DATE_ACTUAL_FEATURE,
                    feature_name=feature.feature_name,
                    detail="Historical actual feature reaches the target date or later.",
                )
            )
            blocked_feature_count += 1
            continue
        if (
            definition.availability_rule == AvailabilityRule.AS_OF_VISIBLE
            and feature.observation_date is not None
            and feature.observation_date > as_of_date
        ):
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.FUTURE_OBSERVATION_DATE,
                    feature_name=feature.feature_name,
                    detail="Observation date is later than the as_of date.",
                )
            )
            blocked_feature_count += 1
            continue
        visible_feature_count += 1

    payload = {
        "as_of_date": as_of_date.isoformat(),
        "for_training": for_training,
        "features": [feature.model_dump(mode="json") for feature in features],
        "blockers": [item.model_dump(mode="json") for item in blockers],
        "warnings": warnings,
    }
    status = ResidualExecutionStatus.BLOCKED if blockers else ResidualExecutionStatus.COMPLETED
    return FeatureVisibilityAudit(
        status=status,
        feature_count=len(features),
        visible_feature_count=visible_feature_count,
        blocked_feature_count=blocked_feature_count,
        missing_feature_count=missing_feature_count,
        unknown_feature_count=unknown_feature_count,
        blockers=blockers,
        warnings=warnings,
        audit_hash=canonical_payload_hash(payload),
    )
