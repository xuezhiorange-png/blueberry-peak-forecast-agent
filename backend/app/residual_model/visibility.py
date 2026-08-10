from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

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
from backend.app.residual_model.forecast_cutoff import normalize_forecast_cutoff_at
from backend.app.residual_model.schemas import (
    FeatureValue,
    FeatureVisibilityAudit,
    FeatureVisibilityIssue,
)


def audit_feature_visibility(
    *,
    features: Sequence[FeatureValue],
    as_of_date: date,
    forecast_cutoff_at: datetime,
    for_training: bool,
) -> FeatureVisibilityAudit:
    definitions = feature_definition_map()
    blockers: list[FeatureVisibilityIssue] = []
    warnings: list[str] = []
    visible_feature_count = 0
    unknown_feature_count = 0
    missing_feature_count = 0
    blocked_feature_count = 0
    cutoff = normalize_forecast_cutoff_at(forecast_cutoff_at)

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
        known_at = normalize_forecast_cutoff_at(feature.known_at)
        source_available_at = normalize_forecast_cutoff_at(feature.source_available_at)
        if known_at > cutoff:
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.FUTURE_KNOWN_AT,
                    feature_name=feature.feature_name,
                    detail="Feature known_at is later than the forecast cutoff.",
                )
            )
            blocked_feature_count += 1
            continue
        if source_available_at > cutoff:
            blockers.append(
                FeatureVisibilityIssue(
                    code=LeakageBlockerCode.FUTURE_AVAILABLE_AT,
                    feature_name=feature.feature_name,
                    detail="Feature source_available_at is later than the forecast cutoff.",
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
        "forecast_cutoff_at": cutoff.isoformat(),
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
