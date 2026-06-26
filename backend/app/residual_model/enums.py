from __future__ import annotations

from enum import StrEnum


class ResidualExecutionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class ResidualEligibilityStatus(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"


class ResidualPredictionMode(StrEnum):
    RESIDUAL_CORRECTED = "residual_corrected"
    STRUCTURAL_ONLY = "structural_only"
    BLOCKED = "blocked"


class ResidualSplit(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class FeatureSourceDomain(StrEnum):
    TASK9 = "task9"
    ANALYTICS = "analytics"
    WEATHER = "weather"
    PLANNING = "planning"
    CALENDAR = "calendar"


class FeatureDType(StrEnum):
    DECIMAL = "decimal"
    INTEGER = "integer"
    STRING = "string"
    BOOLEAN = "boolean"


class AvailabilityRule(StrEnum):
    AS_OF_VISIBLE = "as_of_visible"
    HISTORICAL_ONLY = "historical_only"
    TARGET_INVARIANT = "target_invariant"


class MissingPolicy(StrEnum):
    BLOCK = "block"
    ALLOW_NAN = "allow_nan"
    EXPLICIT_BUCKET = "explicit_bucket"


class EncodingPolicy(StrEnum):
    PASSTHROUGH = "passthrough"
    DETERMINISTIC_ORDINAL = "deterministic_ordinal"


class LeakageBlockerCode(StrEnum):
    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"
    BLOCKLISTED_FEATURE = "BLOCKLISTED_FEATURE"
    FUTURE_KNOWN_AT = "FUTURE_KNOWN_AT"
    FUTURE_AVAILABLE_AT = "FUTURE_AVAILABLE_AT"
    FUTURE_OBSERVATION_DATE = "FUTURE_OBSERVATION_DATE"
    TARGET_DATE_ACTUAL_FEATURE = "TARGET_DATE_ACTUAL_FEATURE"
    MISSING_REQUIRED_FEATURE = "MISSING_REQUIRED_FEATURE"
    FEATURE_NOT_ALLOWED_FOR_TRAINING = "FEATURE_NOT_ALLOWED_FOR_TRAINING"
    FEATURE_NOT_ALLOWED_FOR_PREDICTION = "FEATURE_NOT_ALLOWED_FOR_PREDICTION"


class ProjectionReason(StrEnum):
    NONNEGATIVE_CLAMP = "nonnegative_clamp"
    QUANTILE_MONOTONIC = "quantile_monotonic"
