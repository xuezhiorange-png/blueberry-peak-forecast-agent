"""TASK-013 Slice A — frozen enums and Literal types.

All enums are derived directly from the merged design contract
``docs/task-013-minimal-input-deterministic-agent-orchestration-design.md``.

No business policy lives in this module: every value is a typed discriminator
that maps 1:1 to a frozen section in the design contract.

Per the design's ``extra="forbid"`` discipline and the ``unknown enum value
must fail`` rule, every Literal/Enum below is exhaustive.  Any new value
MUST land in a separate amendment to the design contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal


# --- §11 Logical tool registry ---------------------------------------------

LogicalToolName = Literal[
    "RESOLVE_LOCATION",
    "INFER_PARAMETERS",
    "FORECAST_DAILY_CURVE",
    "FORECAST_PEAK",
    "SIMULATE_SCENARIO",
    "RUN_BACKTEST",
    "EXPLAIN_FORECAST",
    "GENERATE_RECOMMENDATIONS",
]


# --- §11 / §29 Tool classification ----------------------------------------

ToolClassification = Literal[
    "DEFERRED_ADVANCED_TOOL",
    "NEW_DETERMINISTIC_RULE_TOOL",
    "READ_ONLY_COMPOSITION_TOOL",
    "READ_ONLY_COMPOSITION_WITH_AUTHORITY_TOOL",
]


# --- §25 / §10 confidence --------------------------------------------------

Confidence = Literal["HIGH", "MEDIUM", "LOW"]


# --- §24 / §26 request status ----------------------------------------------

RequestStatus = Literal["OK", "PARTIAL", "BLOCKED"]


# --- §26.1 Blocker codes (canonical subset implemented in Slice A) --------

class BlockerCode(str, Enum):
    LOCATION_UNRESOLVED = "LOCATION_UNRESOLVED"
    LOCATION_AMBIGUOUS = "LOCATION_AMBIGUOUS"
    LOCATION_CATALOG_STALE = "LOCATION_CATALOG_STALE"
    INPUT_INVALID_LOCATION = "INPUT_INVALID_LOCATION"
    INPUT_INVALID_VARIETIES = "INPUT_INVALID_VARIETIES"
    INPUT_INVALID_AS_OF = "INPUT_INVALID_AS_OF"
    INPUT_INVALID_SEASON = "INPUT_INVALID_SEASON"
    INPUT_INVALID_PLANTING_AREA = "INPUT_INVALID_PLANTING_AREA"
    UNKNOWN_VARIETY = "UNKNOWN_VARIETY"
    VARIETY_PRIOR_NOT_VISIBLE_AT_AS_OF = "VARIETY_PRIOR_NOT_VISIBLE_AT_AS_OF"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    PARAMETER_OVERRIDE_INVALID = "PARAMETER_OVERRIDE_INVALID"
    AUTHORITY_NOT_FOUND = "AUTHORITY_NOT_FOUND"
    AUTHORITY_CONFLICT = "AUTHORITY_CONFLICT"
    TASK8_AUTHORITY_NOT_FOUND = "TASK8_AUTHORITY_NOT_FOUND"
    TASK9_AUTHORITY_NOT_FOUND = "TASK9_AUTHORITY_NOT_FOUND"
    TASK10_AUTHORITY_NOT_FOUND = "TASK10_AUTHORITY_NOT_FOUND"
    TASK11_AUTHORITY_NOT_FOUND = "TASK11_AUTHORITY_NOT_FOUND"
    TASK12_AUTHORITY_NOT_FOUND = "TASK12_AUTHORITY_NOT_FOUND"
    EFFECTIVE_AS_OF_OUT_OF_POLICY = "EFFECTIVE_AS_OF_OUT_OF_POLICY"
    SEASON_CALENDAR_POLICY_MISSING = "SEASON_CALENDAR_POLICY_MISSING"
    UNCERTAINTY_WIDENING_POLICY_MISSING = "UNCERTAINTY_WIDENING_POLICY_MISSING"
    PEAK_POLICY_MISSING = "PEAK_POLICY_MISSING"
    EXECUTION_DEFERRED = "EXECUTION_DEFERRED"
    EXECUTION_NOT_AUTHORIZED = "EXECUTION_NOT_AUTHORIZED"
    SCENARIO_INVALID = "SCENARIO_INVALID"
    SCENARIO_INCOMPATIBLE_WITH_BASE = "SCENARIO_INCOMPATIBLE_WITH_BASE"
    RULE_NOT_APPLICABLE = "RULE_NOT_APPLICABLE"
    RULE_THRESHOLD_MISSING = "RULE_THRESHOLD_MISSING"
    CITATION_MISSING_FIELD_PATH = "CITATION_MISSING_FIELD_PATH"
    CITATION_HASH_MISMATCH = "CITATION_HASH_MISMATCH"
    OVERRIDE_CONFLICT = "OVERRIDE_CONFLICT"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


# --- §26.2 retry hint ------------------------------------------------------

RetryHint = Literal[
    "FIX_INPUT",
    "PROVIDE_OVERRIDE",
    "WAIT_FOR_DATA",
    "CONTACT_OPS",
    "NONE",
]


# --- §13 matched location method ------------------------------------------

MatchedLocationMethod = Literal[
    "REFERENCE_ID",
    "TEXT",
    "COORDINATE",
    "ADMIN_MATCH",
]


# --- §10 / §20 Spring-Festival phase --------------------------------------

SpringFestivalPhase = Literal[
    "NONE",
    "LOW",
    "MEDIUM",
    "HIGH",
]


# --- §8 override kind ------------------------------------------------------

OverrideKind = Literal[
    "PARAMETER_OVERRIDE_KIND",
    "SCENARIO_OVERRIDE_KIND",
    "EXECUTION_OVERRIDE_KIND",
    "AUTHORITY_OVERRIDE_KIND",
    "AS_OF_OVERRIDE",
]


# --- §8 / §22 authority override target ------------------------------------

AuthorityOverrideTarget = Literal[
    "TASK8_FORECAST_RUN",
    "TASK9_HARVEST_STATE_RUN",
    "TASK10_PREDICTION_RUN",
    "TASK10_TRAINING_RUN",
    "TASK11_BACKTEST_RUN",
    "TASK12_PREDICTION_RUN",
]


# --- §9.3 / §19 authority envelope type ------------------------------------

AuthorityEnvelopeType = Literal[
    "TASK_8_AUTHORITY",
    "TASK_9_AUTHORITY",
    "TASK_10_AUTHORITY",
    "TASK_11_AUTHORITY",
    "TASK_12_AUTHORITY",
]


# --- §19.3 / §24 citation source task --------------------------------------

CitationSourceTask = Literal[
    "TASK_008",
    "TASK_009",
    "TASK_010",
    "TASK_011",
    "TASK_012",
    "TASK_013",
]


# --- §19.3 / §24 citation source tool --------------------------------------

CitationSourceTool = LogicalToolName


# --- §20 recommendation category / kind -----------------------------------

RecommendationCategory = Literal[
    "SUSTAINED_PROCESSING_CAPACITY",
    "RECEIVING_PEAK_CAPACITY",
    "SHIFT_STAFFING",
    "SPRING_FESTIVAL_STAFFING",
    "VARIETY_STAGGER",
    "CROSS_PLANT_DISPATCH",
    "MISSING_DATA_IMPACT",
]


RecommendationKind = Literal["OPERATIONAL", "DATA_QUALITY"]


# --- §8.1.2 / §17 scenario target -----------------------------------------

ScenarioTarget = Literal[
    "STAFFING",
    "SPRING_FESTIVAL_INTENSITY",
    "PROCESSOR_CAPACITY",
]


# --- §8.1 parameter target -----------------------------------------------

ParameterTarget = Literal[
    "expected_per_mu_yield",
    "commodity_fruit_rate",
    "first_harvest_date",
    "maturity_curve",
    "spring_festival_harvest_rate",
    "weather_adjustment",
]


# --- §8.1 execution target ------------------------------------------------

ExecutionTarget = Literal[
    "REQUEST_BACKTEST",
    "REQUEST_REPLAY_TRAINED_RUN",
    "REQUEST_SIMULATION",
]


# --- §16 peak window quantile / forecast quantile -------------------------

ForecastQuantile = Literal["P50", "P80", "P90"]


# --- §26.1 execution-deferred status --------------------------------------

ExecutionDeferredStatus = Literal["EXECUTION_DEFERRED"]


__all__ = [
    "LogicalToolName",
    "ToolClassification",
    "Confidence",
    "RequestStatus",
    "BlockerCode",
    "RetryHint",
    "MatchedLocationMethod",
    "SpringFestivalPhase",
    "OverrideKind",
    "AuthorityOverrideTarget",
    "AuthorityEnvelopeType",
    "CitationSourceTask",
    "CitationSourceTool",
    "RecommendationCategory",
    "RecommendationKind",
    "ScenarioTarget",
    "ParameterTarget",
    "ExecutionTarget",
    "ForecastQuantile",
    "ExecutionDeferredStatus",
]
