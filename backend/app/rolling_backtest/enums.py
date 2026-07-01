from __future__ import annotations

from enum import StrEnum


class ExecutionMode(StrEnum):
    HISTORICAL_OBSERVED = "historical_observed"
    RETROSPECTIVE_REPLAY = "retrospective_replay"


class ForecastStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class EvaluationStatus(StrEnum):
    NOT_READY = "not_ready"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class RunDerivedStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    FORECAST_COMPLETED = "forecast_completed"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class UpstreamSelectionMode(StrEnum):
    PINNED = "pinned"
    HISTORICAL_RESOLUTION = "historical_resolution"


class ScopeMode(StrEnum):
    ALL = "all"
    INCLUDE_IDS = "include_ids"


class DefaultNodeKey(StrEnum):
    FEBRUARY_END = "february_end"
    MARCH_15 = "march_15"
    MARCH_31 = "march_31"
    APRIL_07 = "april_07"


class AvailabilitySourceType(StrEnum):
    TASK3_ANALYTICS_BUILD = "task3_analytics_build"
    TASK6_PLAN_VERSION = "task6_plan_version"
    TASK7_WEATHER_FEATURE_RUN = "task7_weather_feature_run"
    TASK7_LOCATION_WEATHER_MAPPING = "task7_location_weather_mapping"
    TASK7_WEATHER_OBSERVATION = "task7_weather_observation"
    TASK8_MODEL_RUN = "task8_model_run"
    TASK8_MODEL_ARTIFACT = "task8_model_artifact"
    TASK8_FORECAST_RUN = "task8_forecast_run"
    TASK8_DAILY_PREDICTION = "task8_daily_prediction"
    TASK9_HARVEST_STATE_RUN = "task9_harvest_state_run"
    TASK10_TRAINING_RUN = "task10_training_run"
    TASK10_MODEL_ARTIFACT = "task10_model_artifact"
    TASK10_PREDICTION_RUN = "task10_prediction_run"


class AvailabilityBlockerCode(StrEnum):
    STATUS_NOT_ALLOWED = "STATUS_NOT_ALLOWED"
    MISSING_AUTHORITATIVE_TIMESTAMP = "MISSING_AUTHORITATIVE_TIMESTAMP"
    AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF = "AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF"
    MISSING_SOURCE_CUTOFF = "MISSING_SOURCE_CUTOFF"
    SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF = "SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF"
    OBSERVATION_DATE_AFTER_CUTOFF = "OBSERVATION_DATE_AFTER_CUTOFF"
    PARENT_AUTHORITY_REQUIRED = "PARENT_AUTHORITY_REQUIRED"
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
    FORBIDDEN_FIELD_PRESENT = "FORBIDDEN_FIELD_PRESENT"
    SOURCE_VISIBILITY_MISSING = "SOURCE_VISIBILITY_MISSING"
    SOURCE_VISIBILITY_POLICY_MISMATCH = "SOURCE_VISIBILITY_POLICY_MISMATCH"
    AVAILABLE_ON_LOCAL_DATE_AFTER_AS_OF = "AVAILABLE_ON_LOCAL_DATE_AFTER_AS_OF"
    NODE_LOCAL_DATE_AFTER_AS_OF = "NODE_LOCAL_DATE_AFTER_AS_OF"


class AvailabilityRuleKind(StrEnum):
    AUTHORITATIVE_TIMESTAMP = "authoritative_timestamp"
    LOCAL_AVAILABLE_DATE = "local_available_date"
    TASK3_SOURCE_VISIBILITY = "task3_source_visibility"
    AUTHORITATIVE_WITH_OBSERVATION_DATE = "authoritative_with_observation_date"
    LOCAL_AVAILABLE_DATE_WITH_OBSERVATION_DATE = "local_available_date_with_observation_date"


class Task10ModelPolicy(StrEnum):
    HISTORICALLY_AVAILABLE_MODEL = "historically_available_model"
    REPLAY_TRAINED_MODEL = "replay_trained_model"


ROLLING_SCHEMA_VERSION = "task11-rolling-v1"
CANONICAL_SERIALIZATION_VERSION = "task11-canonical-v1"
AVAILABILITY_REGISTRY_VERSION = "task11-availability-v1"
NODE_CALENDAR_VERSION = "task11-calendar-v1"
FORECAST_HORIZON_POLICY_VERSION = "task11-horizon-v1"
UPSTREAM_SELECTION_POLICY_VERSION = "task11-selection-v1"
METRIC_POLICY_VERSION = "task11-metrics-v1"
CALENDAR_PHASE_POLICY_VERSION = "task11-calendar-phase-v1"
CUTOFF_POLICY_VERSION = "task11-cutoff-v1"
