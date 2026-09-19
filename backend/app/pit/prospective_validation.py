"""Deterministic V0.6-S4 prospective validation and weather diagnostics.

S4 consumes immutable S1/S2 forecast snapshots and S3 evaluation evidence.  It
does not fit or mutate a forecast model.  The functions in this module are
deliberately independent of SQLAlchemy so fixture acceptance can exercise the
same contracts as the persisted application path.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final

from backend.app.pit.canonical import hash_payload
from backend.app.pit.evaluation import ActualDailyRecord
from backend.app.pit.visibility import weather_forecast_visible_at

PROSPECTIVE_POLICY_VERSION: Final[str] = "V0_6_S4_PROSPECTIVE_VALIDATION_AND_WEATHER_VALUE_V1"
MODEL_A_IDENTITY: Final[str] = "AREA_PLUS_HISTORICAL_HARVEST"
MODEL_A_TOTAL_MODEL: Final[str] = "BASE_AWARE_BASELINE_R1"
MODEL_A_TEMPORAL_MODEL: Final[str] = "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE"
FORECAST_TIME_WEATHER_ONLY: Final[bool] = True
REALIZED_WEATHER_AS_MODEL_INPUT: Final[bool] = False
GDD_INCREMENTAL_VALUE_STATUS: Final[str] = "NOT_EVALUATED_DEFINITION_NOT_FROZEN"
EVIDENCE_SUFFICIENCY_POLICY: Final[str] = "DESCRIPTIVE_NO_FROZEN_MINIMUM_SAMPLE_THRESHOLD"
STABLE_HISTORY_COHORT_STATUS: Final[str] = "NOT_COMPUTABLE_NO_FROZEN_COHORT_AUTHORITY"
HISTORICAL_MODEL_COVERAGE_COHORT_SOURCE: Final[str] = (
    "FORECAST_SNAPSHOT_PRIOR_HISTORY_COVERAGE_STATUS"
)
WEATHER_HORIZONS: Final[tuple[int, ...]] = (24, 72, 168, 360)
WEATHER_INCREMENTAL_CONCLUSIONS: Final[tuple[str, ...]] = (
    "INCONCLUSIVE",
    "NOT_DEMONSTRATED",
    "SUPPORTED_BY_CURRENT_EVIDENCE",
)
V0_7_RECOMMENDATIONS: Final[tuple[str, ...]] = (
    "PROCEED_TO_CONTROLLED_EXPERIMENT",
    "DO_NOT_PROCEED_YET",
    "INSUFFICIENT_EVIDENCE",
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime is required")
    return value.astimezone(UTC)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _sign(value: Decimal) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


@dataclass(frozen=True, slots=True)
class ProspectiveEligibilityRecord:
    """Auditable eligibility decision for one forecast run."""

    forecast_run_id: str
    base_id: str
    target_season: str
    forecast_created_at: datetime
    forecast_input_hash: str
    forecast_result_hash: str
    area_revision_id: str
    area_revision_hash: str | None
    prior_history_identity: dict[str, Any]
    weather_snapshot_ids: tuple[str, ...]
    weather_snapshot_authority_hashes: tuple[str, ...]
    phenology_observation_ids: tuple[str, ...]
    actual_authority_ids: tuple[str, ...]
    actual_authority_hashes: tuple[str, ...]
    first_actual_observed_at: datetime | None
    last_actual_observed_at: datetime | None
    actual_coverage_status: str
    prospective_eligible: bool
    ineligibility_reasons: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "forecast_run_id": self.forecast_run_id,
            "base_id": self.base_id,
            "target_season": self.target_season,
            "forecast_created_at": self.forecast_created_at,
            "forecast_input_hash": self.forecast_input_hash,
            "forecast_result_hash": self.forecast_result_hash,
            "area_revision_id": self.area_revision_id,
            "area_revision_hash": self.area_revision_hash,
            "prior_history_identity": self.prior_history_identity,
            "weather_snapshot_ids": list(self.weather_snapshot_ids),
            "weather_snapshot_authority_hashes": list(self.weather_snapshot_authority_hashes),
            "phenology_observation_ids": list(self.phenology_observation_ids),
            "actual_authority_ids": list(self.actual_authority_ids),
            "actual_authority_hashes": list(self.actual_authority_hashes),
            "first_actual_observed_at": self.first_actual_observed_at,
            "last_actual_observed_at": self.last_actual_observed_at,
            "actual_coverage_status": self.actual_coverage_status,
            "prospective_eligible": self.prospective_eligible,
            "ineligibility_reasons": list(self.ineligibility_reasons),
        }


@dataclass(frozen=True, slots=True)
class WeatherDiagnosticRow:
    """One forecast-time-weather versus observed-timing diagnostic row.

    ``timing_residual_days`` is supplied by the already persisted S3
    forecast/actual evaluation.  It is never used to fit or rewrite Model A.
    """

    forecast_run_id: str
    base_id: str
    horizon_hours: int
    temperature_signal: Decimal | None
    precipitation_signal: Decimal | None
    timing_residual_days: Decimal


@dataclass(frozen=True, slots=True)
class EvaluationDailyEvidence:
    """Persisted S3 child row used for exact pooled daily aggregation."""

    evaluation_date: Any
    predicted_quantity_kg: Decimal
    actual_quantity_kg: Decimal | None
    actual_status: str
    error_kg: Decimal | None
    absolute_error_kg: Decimal | None


@dataclass(frozen=True, slots=True)
class EvaluationEvidence:
    """Read-only projection of one persisted S3 evaluation."""

    evaluation_id: str
    forecast_run_id: str
    base_id: str
    actual_coverage_status: str
    season_total_metrics: Mapping[str, Any]
    daily_metrics: Mapping[str, Any]
    single_day_peak_metrics: Mapping[str, Any]
    rolling_7day_peak_metrics: Mapping[str, Any]
    weather_metrics: Mapping[str, Any]
    historical_model_coverage_status: str | None = None
    daily_rows: tuple[EvaluationDailyEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class S4AssessmentComputation:
    """Immutable S4 registry plus assessment payload and hashes."""

    validation_run_id: str
    assessment_id: str
    created_at: datetime
    policy_version: str
    model_a_identity: str
    model_a_hash: str
    eligibility: tuple[ProspectiveEligibilityRecord, ...]
    s3_evaluation_ids: tuple[str, ...]
    sample_scope: dict[str, Any]
    coverage_summary: dict[str, Any]
    baseline_metrics: dict[str, Any]
    weather_quality_metrics: dict[str, Any]
    weather_incremental_metrics: dict[str, Any]
    evidence_sufficiency: dict[str, Any]
    weather_incremental_value_conclusion: str
    v0_7_recommendation: str
    weather_snapshot_authority_hashes: tuple[str, ...]
    warnings: tuple[str, ...]
    payload_hash: str
    result_hash: str

    def identity_payload(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "model_a_identity": self.model_a_identity,
            "model_a_hash": self.model_a_hash,
            "eligible_forecast_run_ids": sorted(
                item.forecast_run_id for item in self.eligibility if item.prospective_eligible
            ),
            "s3_evaluation_ids": list(self.s3_evaluation_ids),
            "weather_snapshot_authority_hashes": list(self.weather_snapshot_authority_hashes),
            "sample_scope": self.sample_scope,
            "evidence_sufficiency": self.evidence_sufficiency,
        }

    def result_payload(self) -> dict[str, Any]:
        return {
            "eligibility_registry": [item.payload() for item in self.eligibility],
            "coverage_summary": self.coverage_summary,
            "baseline_metrics": self.baseline_metrics,
            "weather_quality_metrics": self.weather_quality_metrics,
            "weather_incremental_metrics": self.weather_incremental_metrics,
            "weather_incremental_value_conclusion": self.weather_incremental_value_conclusion,
            "v0_7_recommendation": self.v0_7_recommendation,
            "warnings": list(self.warnings),
        }

    def payload(self) -> dict[str, Any]:
        return {"identity": self.identity_payload(), "result": self.result_payload()}

    def compute_result_hash(self) -> str:
        return hash_payload(self.result_payload())

    def compute_payload_hash(self) -> str:
        return hash_payload(self.payload())


def weather_snapshot_is_pit_eligible(
    snapshot: Any,
    base_id: str,
    forecast_created_at: datetime,
) -> bool:
    """Require explicit Base binding and the S2 as-issued visibility rule."""

    if getattr(snapshot, "base_id", None) != base_id:
        return False
    provider = getattr(snapshot, "provider", None)
    if not isinstance(provider, str) or not provider:
        return False
    return weather_forecast_visible_at(snapshot, forecast_created_at)


def _actual_records_for_snapshot(
    snapshot: Any,
    actual_records: Sequence[ActualDailyRecord],
    evaluation_created_at: datetime,
) -> tuple[ActualDailyRecord, ...]:
    cutoff = _utc(evaluation_created_at)
    return tuple(
        sorted(
            (
                record
                for record in actual_records
                if record.base_id == snapshot.base_id
                and record.target_season == snapshot.target_season
                and _utc(record.known_at) <= cutoff
            ),
            key=lambda record: (record.harvest_date, record.revision_id),
        )
    )


def build_prospective_eligibility(
    snapshot: Any,
    actual_records: Sequence[ActualDailyRecord],
    *,
    evaluation_created_at: datetime,
    actual_coverage_status: str | None = None,
    area_revision: Any | None = None,
    weather_snapshots: Sequence[Any] = (),
    phenology_observations: Sequence[Any] = (),
) -> ProspectiveEligibilityRecord:
    """Build a fail-closed prospective eligibility decision.

    No date or authority is inferred from a fixture.  In particular, an empty
    actual sequence is always ``ACTUAL_NOT_MATURED`` and cannot become a
    prospective sample merely because the forecast looks historical.
    """

    cutoff = _utc(evaluation_created_at)
    forecast_created_at = _utc(snapshot.forecast_created_at)
    reasons: set[str] = set()
    if forecast_created_at > cutoff:
        reasons.add("FORECAST_CREATED_AFTER_EVALUATION_CUTOFF")
    if getattr(snapshot, "forecast_mode", None) != "SHADOW":
        reasons.add("FORECAST_MODE_NOT_SHADOW")
    if not getattr(snapshot, "input_snapshot_hash", ""):
        reasons.add("FORECAST_INPUT_HASH_MISSING")
    if not getattr(snapshot, "result_hash", ""):
        reasons.add("FORECAST_RESULT_HASH_MISSING")
    if forecast_created_at > _utc(snapshot.created_at):
        reasons.add("FORECAST_SNAPSHOT_NOT_PERSISTED_AFTER_CREATION")

    if area_revision is None:
        reasons.add("AREA_REVISION_NOT_RESOLVED")
    else:
        if getattr(area_revision, "area_revision_id", None) != snapshot.area_revision_id:
            reasons.add("AREA_REVISION_SCOPE_MISMATCH")
        if getattr(area_revision, "base_id", None) != snapshot.base_id:
            reasons.add("AREA_REVISION_SCOPE_MISMATCH")
        if (
            getattr(area_revision, "known_at", None) is None
            or _utc(area_revision.known_at) > forecast_created_at
        ):
            reasons.add("HINDSIGHT_OR_UNBOUND_AREA")
        if (
            getattr(area_revision, "effective_from", None) is None
            or _utc(area_revision.effective_from) > forecast_created_at
        ):
            reasons.add("HINDSIGHT_OR_UNBOUND_AREA")
        effective_to = getattr(area_revision, "effective_to", None)
        if effective_to is not None and _utc(effective_to) < forecast_created_at:
            reasons.add("AREA_REVISION_OUTSIDE_EFFECTIVE_RANGE")
        area_type = getattr(area_revision, "area_type", None)
        if (
            area_type != "REFERENCE_AREA"
            and getattr(area_revision, "season", None) != snapshot.target_season
        ):
            reasons.add("AREA_REVISION_SEASON_MISMATCH")

    actual = _actual_records_for_snapshot(snapshot, actual_records, cutoff)
    if not actual:
        reasons.add("ACTUAL_NOT_MATURED")
    if any(_utc(record.observed_at) <= forecast_created_at for record in actual):
        reasons.add("FORECAST_NOT_BEFORE_ACTUAL_OBSERVATION")

    weather_by_id = {getattr(item, "weather_snapshot_id", None): item for item in weather_snapshots}
    for weather_id in sorted(set(getattr(snapshot, "weather_snapshot_ids", ()) or ())):
        weather = weather_by_id.get(weather_id)
        if weather is None or not weather_snapshot_is_pit_eligible(
            weather, snapshot.base_id, forecast_created_at
        ):
            reasons.add("HINDSIGHT_OR_UNBOUND_WEATHER")

    phenology_by_id = {
        getattr(item, "observation_id", None): item for item in phenology_observations
    }
    for observation_id in sorted(set(getattr(snapshot, "phenology_observation_ids", ()) or ())):
        observation = phenology_by_id.get(observation_id)
        if (
            observation is None
            or getattr(observation, "base_id", None) != snapshot.base_id
            or getattr(observation, "season", None) != snapshot.target_season
            or not getattr(observation, "known_at", None)
            or _utc(observation.known_at) > forecast_created_at
        ):
            reasons.add("HINDSIGHT_OR_SCOPE_MISMATCH_PHENOLOGY")

    referenced_weather = tuple(
        weather_by_id[weather_id]
        for weather_id in sorted(set(getattr(snapshot, "weather_snapshot_ids", ()) or ()))
        if weather_id in weather_by_id
    )
    actual_ids = tuple(sorted({record.authority_id for record in actual if record.authority_id}))
    actual_hashes = tuple(sorted({record.source_hash for record in actual}))
    weather_hashes = tuple(
        sorted(
            {
                str(weather.payload_hash)
                for weather in referenced_weather
                if getattr(weather, "payload_hash", None)
            }
        )
    )
    if actual_coverage_status not in {None, "COMPLETE", "PARTIAL", "EMPTY"}:
        reasons.add("ACTUAL_COVERAGE_STATUS_INVALID")
    if not actual and actual_coverage_status in {"COMPLETE", "PARTIAL"}:
        reasons.add("ACTUAL_COVERAGE_WITHOUT_RECORDS")
    coverage = "EMPTY" if not actual else (actual_coverage_status or "PARTIAL")
    first_observed = min((_utc(record.observed_at) for record in actual), default=None)
    last_observed = max((_utc(record.observed_at) for record in actual), default=None)
    prior_identity = {
        "season": getattr(snapshot, "prior_history_season", None),
        "quantity_kg": getattr(snapshot, "prior_history_quantity_kg", None),
        "source_hash": getattr(snapshot, "prior_history_source_hash", None),
        "identity_mapping_hash": getattr(snapshot, "prior_history_identity_mapping_hash", None),
        "coverage_status": getattr(snapshot, "prior_history_coverage_status", None),
    }
    return ProspectiveEligibilityRecord(
        forecast_run_id=snapshot.forecast_run_id,
        base_id=snapshot.base_id,
        target_season=snapshot.target_season,
        forecast_created_at=forecast_created_at,
        forecast_input_hash=snapshot.input_snapshot_hash,
        forecast_result_hash=snapshot.result_hash,
        area_revision_id=snapshot.area_revision_id,
        area_revision_hash=(
            str(area_revision.payload_hash)
            if area_revision is not None and getattr(area_revision, "payload_hash", None)
            else None
        ),
        prior_history_identity=prior_identity,
        weather_snapshot_ids=tuple(sorted(getattr(snapshot, "weather_snapshot_ids", ()) or ())),
        weather_snapshot_authority_hashes=weather_hashes,
        phenology_observation_ids=tuple(
            sorted(getattr(snapshot, "phenology_observation_ids", ()) or ())
        ),
        actual_authority_ids=actual_ids,
        actual_authority_hashes=actual_hashes,
        first_actual_observed_at=first_observed,
        last_actual_observed_at=last_observed,
        actual_coverage_status=coverage,
        prospective_eligible=not reasons,
        ineligibility_reasons=tuple(sorted(reasons)),
    )


def _rank(values: Sequence[Decimal]) -> list[Decimal]:
    positions: dict[Decimal, list[int]] = defaultdict(list)
    for index, value in enumerate(sorted(values)):
        positions[value].append(index + 1)
    average_rank = {
        value: sum(indexes, 0) / Decimal(len(indexes)) for value, indexes in positions.items()
    }
    return [average_rank[value] for value in values]


def _correlation(x_values: Sequence[Decimal], y_values: Sequence[Decimal]) -> Decimal | None:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    x_mean = sum(x_values, Decimal("0")) / Decimal(len(x_values))
    y_mean = sum(y_values, Decimal("0")) / Decimal(len(y_values))
    numerator = sum(
        ((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=True)),
        Decimal("0"),
    )
    x_variance = sum(((x - x_mean) ** 2 for x in x_values), Decimal("0"))
    y_variance = sum(((y - y_mean) ** 2 for y in y_values), Decimal("0"))
    denominator = (x_variance * y_variance).sqrt()
    return None if denominator == 0 else numerator / denominator


def _direction_consistency(rows: Sequence[WeatherDiagnosticRow], field: str) -> Decimal | None:
    by_base: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
    for row in rows:
        signal = getattr(row, field)
        if signal is not None:
            by_base[row.base_id].append((signal, row.timing_residual_days))
    directions: list[int] = []
    for pairs in by_base.values():
        correlation = _correlation([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        if correlation is not None and _sign(correlation) != 0:
            directions.append(_sign(correlation))
    if not directions:
        return None
    dominant = max(set(directions), key=lambda sign: (directions.count(sign), sign))
    return Decimal(sum(direction == dominant for direction in directions)) / Decimal(
        len(directions)
    )


def _diagnostic_field(rows: Sequence[WeatherDiagnosticRow], field: str) -> dict[str, Any]:
    selected = [row for row in rows if getattr(row, field) is not None]
    x_values = [_decimal(getattr(row, field)) for row in selected]
    y_values = [row.timing_residual_days for row in selected]
    pearson = _correlation(x_values, y_values)
    spearman = _correlation(_rank(x_values), _rank(y_values)) if len(x_values) >= 2 else None
    return {
        "sample_count": len(selected),
        "pearson_correlation": pearson,
        "spearman_correlation": spearman,
    }


def compute_weather_diagnostic(
    rows: Sequence[WeatherDiagnosticRow],
) -> dict[str, Any]:
    """Compute descriptive, non-fitting weather/timing associations."""

    reports: dict[str, Any] = {}
    ordered = sorted(rows, key=lambda row: (row.horizon_hours, row.base_id, row.forecast_run_id))
    for horizon in WEATHER_HORIZONS:
        horizon_rows = [row for row in ordered if row.horizon_hours == horizon]
        temperature = _diagnostic_field(horizon_rows, "temperature_signal")
        precipitation = _diagnostic_field(horizon_rows, "precipitation_signal")
        direction = _direction_consistency(horizon_rows, "temperature_signal")
        reports[f"D{horizon // 24}"] = {
            "horizon_hours": horizon,
            "sample_count": len(horizon_rows),
            "base_count": len({row.base_id for row in horizon_rows}),
            "temperature": temperature,
            "precipitation": precipitation,
            "temperature_direction_consistency": direction,
            "direction_consistency": direction,
            "cross_base_consistent": direction == Decimal("1"),
        }
    signal_found = any(
        report["temperature"]["pearson_correlation"] is not None
        or report["precipitation"]["pearson_correlation"] is not None
        for report in reports.values()
    )
    return {
        **reports,
        "gdd_incremental_value_status": GDD_INCREMENTAL_VALUE_STATUS,
        "realized_weather_as_model_input": REALIZED_WEATHER_AS_MODEL_INPUT,
        "forecast_time_weather_only": FORECAST_TIME_WEATHER_ONLY,
        "weather_signal_found": signal_found,
    }


def _metric_value(metrics: Mapping[str, Any], key: str) -> Decimal | None:
    value = metrics.get(key)
    if not isinstance(value, Mapping) or value.get("status") != "COMPUTABLE":
        return None
    raw = value.get("value")
    return None if raw is None else _decimal(raw)


def _mean_metric(
    values: Sequence[Decimal],
    sample_count: int,
    *,
    aggregation: str = "MEAN_RUN_METRIC",
) -> dict[str, Any]:
    if not values:
        return {
            "status": "NOT_COMPUTABLE",
            "value": None,
            "sample_count": sample_count,
            "aggregation": aggregation,
        }
    return {
        "status": "COMPUTABLE",
        "value": sum(values, Decimal("0")) / Decimal(len(values)),
        "sample_count": len(values),
        "aggregation": aggregation,
    }


def _pooled_ratio(
    numerator: Decimal,
    denominator: Decimal,
    *,
    sample_count: int,
    aggregation: str,
    evaluation_count: int,
) -> dict[str, Any]:
    if denominator == 0:
        return {
            "status": "UNDEFINED_ZERO_DENOMINATOR",
            "value": None,
            "sample_count": sample_count,
            "evaluation_count": evaluation_count,
            "numerator": numerator,
            "denominator": denominator,
            "aggregation": aggregation,
        }
    return {
        "status": "COMPUTABLE",
        "value": numerator / denominator,
        "sample_count": sample_count,
        "evaluation_count": evaluation_count,
        "numerator": numerator,
        "denominator": denominator,
        "aggregation": aggregation,
    }


def _metric_scalar(metrics: Mapping[str, Any], key: str) -> Decimal | None:
    value = metrics.get(key)
    if isinstance(value, Mapping):
        if value.get("status") != "COMPUTABLE":
            return None
        value = value.get("value")
    return None if value is None else _decimal(value)


def _peak_quantity_wape(metrics: Mapping[str, Any]) -> Decimal | None:
    forecast = metrics.get("forecast_peak_quantity_kg")
    actual = metrics.get("actual_peak_quantity_kg")
    if forecast is None or actual is None or _decimal(actual) == 0:
        return None
    return abs(_decimal(forecast) - _decimal(actual)) / abs(_decimal(actual))


def _rolling_quantity_wape(metrics: Mapping[str, Any]) -> Decimal | None:
    forecast = metrics.get("forecast_7day_cumulative_kg")
    actual = metrics.get("actual_7day_cumulative_kg")
    if forecast is None or actual is None or _decimal(actual) == 0:
        return None
    return abs(_decimal(forecast) - _decimal(actual)) / abs(_decimal(actual))


def _season_total_pair(evaluation: EvaluationEvidence) -> tuple[Decimal, Decimal] | None:
    forecast = _metric_scalar(evaluation.season_total_metrics, "predicted_total_kg")
    actual = _metric_scalar(evaluation.season_total_metrics, "actual_total_kg")
    if forecast is None or actual is None:
        return None
    return forecast, actual


def _daily_pooled_totals(
    evaluations: Sequence[EvaluationEvidence],
) -> tuple[Decimal, Decimal, int]:
    numerator = Decimal("0")
    denominator = Decimal("0")
    row_count = 0
    for evaluation in evaluations:
        for row in evaluation.daily_rows:
            if row.actual_quantity_kg is None or row.actual_status == "MISSING":
                continue
            error = row.error_kg
            if error is None:
                error = row.predicted_quantity_kg - row.actual_quantity_kg
            numerator += abs(error)
            denominator += abs(row.actual_quantity_kg)
            row_count += 1
    return numerator, denominator, row_count


def _summarize_group(evaluations: Sequence[EvaluationEvidence]) -> dict[str, Any]:
    sample_count = len(evaluations)
    daily_rows = sum(
        len(evaluation.daily_rows)
        if evaluation.daily_rows
        else int((evaluation.daily_metrics.get("wape") or {}).get("comparable_row_count", 0))
        for evaluation in evaluations
    )
    complete = sum(evaluation.actual_coverage_status == "COMPLETE" for evaluation in evaluations)
    partial = sum(evaluation.actual_coverage_status == "PARTIAL" for evaluation in evaluations)
    season_pairs = [
        pair for evaluation in evaluations if (pair := _season_total_pair(evaluation)) is not None
    ]
    season_numerator = sum(
        (abs(forecast - actual) for forecast, actual in season_pairs), Decimal("0")
    )
    season_denominator = sum((abs(actual) for _forecast, actual in season_pairs), Decimal("0"))
    season_signed_error = sum(
        (forecast - actual for forecast, actual in season_pairs), Decimal("0")
    )
    daily_numerator, daily_denominator, comparable_daily_rows = _daily_pooled_totals(evaluations)

    peak_quantity_pairs = [
        (
            _decimal(item.single_day_peak_metrics["forecast_peak_quantity_kg"]),
            _decimal(item.single_day_peak_metrics["actual_peak_quantity_kg"]),
        )
        for item in evaluations
        if item.single_day_peak_metrics.get("status") == "COMPUTABLE"
        and item.single_day_peak_metrics.get("forecast_peak_quantity_kg") is not None
        and item.single_day_peak_metrics.get("actual_peak_quantity_kg") is not None
    ]
    peak_numerator = sum(
        (abs(forecast - actual) for forecast, actual in peak_quantity_pairs), Decimal("0")
    )
    peak_denominator = sum((abs(actual) for _forecast, actual in peak_quantity_pairs), Decimal("0"))
    rolling_quantity_pairs = [
        (
            _decimal(item.rolling_7day_peak_metrics["forecast_7day_cumulative_kg"]),
            _decimal(item.rolling_7day_peak_metrics["actual_7day_cumulative_kg"]),
        )
        for item in evaluations
        if item.rolling_7day_peak_metrics.get("status") == "COMPUTABLE"
        and item.rolling_7day_peak_metrics.get("forecast_7day_cumulative_kg") is not None
        and item.rolling_7day_peak_metrics.get("actual_7day_cumulative_kg") is not None
    ]
    rolling_numerator = sum(
        (abs(forecast - actual) for forecast, actual in rolling_quantity_pairs), Decimal("0")
    )
    rolling_denominator = sum(
        (abs(actual) for _forecast, actual in rolling_quantity_pairs), Decimal("0")
    )
    peak_date_errors = [
        _decimal(item.single_day_peak_metrics["peak_absolute_date_error_days"])
        for item in evaluations
        if item.single_day_peak_metrics.get("status") == "COMPUTABLE"
        and item.single_day_peak_metrics.get("peak_absolute_date_error_days") is not None
    ]
    rolling_date_errors = [
        _decimal(item.rolling_7day_peak_metrics["rolling_7day_absolute_start_date_error_days"])
        for item in evaluations
        if item.rolling_7day_peak_metrics.get("status") == "COMPUTABLE"
        and item.rolling_7day_peak_metrics.get("rolling_7day_absolute_start_date_error_days")
        is not None
    ]
    return {
        "eligible_forecast_run_count": sample_count,
        "eligible_base_count": len({evaluation.base_id for evaluation in evaluations}),
        "eligible_daily_row_count": daily_rows,
        "complete_season_count": complete,
        "partial_season_count": partial,
        "metrics": {
            "season_total_wape": _pooled_ratio(
                season_numerator,
                season_denominator,
                sample_count=len(season_pairs),
                evaluation_count=sample_count,
                aggregation="POOLED_ABSOLUTE_SEASON_TOTAL_ERROR_OVER_ABSOLUTE_ACTUAL",
            ),
            "daily_wape": _pooled_ratio(
                daily_numerator,
                daily_denominator,
                sample_count=comparable_daily_rows,
                evaluation_count=sample_count,
                aggregation="POOLED_ABSOLUTE_DAILY_ERROR_OVER_ABSOLUTE_ACTUAL",
            ),
            "single_day_peak_quantity_wape": _pooled_ratio(
                peak_numerator,
                peak_denominator,
                sample_count=len(peak_quantity_pairs),
                evaluation_count=sample_count,
                aggregation="POOLED_ABSOLUTE_PEAK_QUANTITY_ERROR_OVER_ABSOLUTE_ACTUAL_PEAK",
            ),
            "single_day_peak_date_mae": _mean_metric(
                peak_date_errors,
                sample_count,
                aggregation="MEAN_ABSOLUTE_DATE_ERROR_OVER_COMPUTABLE_RUNS",
            ),
            "rolling_7day_peak_wape": _pooled_ratio(
                rolling_numerator,
                rolling_denominator,
                sample_count=len(rolling_quantity_pairs),
                evaluation_count=sample_count,
                aggregation="POOLED_ABSOLUTE_7DAY_ERROR_OVER_ABSOLUTE_ACTUAL_7DAY_PEAK",
            ),
            "rolling_7day_start_date_mae": _mean_metric(
                rolling_date_errors,
                sample_count,
                aggregation="MEAN_ABSOLUTE_DATE_ERROR_OVER_COMPUTABLE_RUNS",
            ),
            "bias": (
                {
                    "status": "COMPUTABLE",
                    "value": season_signed_error / Decimal(len(season_pairs)),
                    "sample_count": len(season_pairs),
                    "aggregation": "MEAN_SIGNED_SEASON_TOTAL_ERROR_OVER_RUNS",
                }
                if season_pairs
                else {
                    "status": "NOT_COMPUTABLE",
                    "value": None,
                    "sample_count": 0,
                    "aggregation": "MEAN_SIGNED_SEASON_TOTAL_ERROR_OVER_RUNS",
                }
            ),
        },
        "actual_coverage": {
            "status_semantics": "CURRENT_SEASON_ACTUAL_COVERAGE",
            "complete_count": complete,
            "partial_count": partial,
        },
    }


def _weather_quality(evaluations: Sequence[EvaluationEvidence]) -> dict[str, Any]:
    def values_for(reports: Sequence[Mapping[str, Any]], key: str) -> list[Decimal]:
        values: list[Decimal] = []
        for report in reports:
            value = _metric_value(report, key)
            if value is not None:
                values.append(value)
        return values

    output: dict[str, Any] = {}
    for horizon in WEATHER_HORIZONS:
        name = f"D{horizon // 24}"
        reports: list[Mapping[str, Any]] = [
            report
            for evaluation in evaluations
            for report in [evaluation.weather_metrics.get(name)]
            if isinstance(report, Mapping)
        ]
        output[name] = {
            "sample_count": len(reports),
            "temperature_mae": _mean_metric(
                values_for(reports, "temperature_mae"),
                len(reports),
            ),
            "temperature_bias": _mean_metric(
                values_for(reports, "temperature_bias"),
                len(reports),
            ),
            "precipitation_error": _mean_metric(
                values_for(reports, "precipitation_error"),
                len(reports),
            ),
            "gdd_evaluation_status": GDD_INCREMENTAL_VALUE_STATUS,
        }
    return output


def build_assessment(
    *,
    eligibility: Sequence[ProspectiveEligibilityRecord],
    evaluations: Sequence[EvaluationEvidence],
    weather_diagnostic_rows: Sequence[WeatherDiagnosticRow],
    created_at: datetime,
    stable_history_base_ids: Iterable[str] = (),
    model_a_hash: str | None = None,
    policy_version: str = PROSPECTIVE_POLICY_VERSION,
) -> S4AssessmentComputation:
    """Build the deterministic S4 result without fitting a weather model."""

    created_at = _utc(created_at)
    requested_stable_ids = tuple(sorted(set(stable_history_base_ids)))
    if requested_stable_ids:
        raise ValueError("STABLE_HISTORY_COHORT_AUTHORITY_REQUIRED")
    eligibility = tuple(sorted(eligibility, key=lambda item: item.forecast_run_id))
    eligible_ids = {item.forecast_run_id for item in eligibility if item.prospective_eligible}
    eligibility_by_run = {item.forecast_run_id: item for item in eligibility}
    enriched_evaluations: list[EvaluationEvidence] = []
    for evaluation in evaluations:
        eligibility_record = eligibility_by_run.get(evaluation.forecast_run_id)
        enriched_evaluations.append(
            replace(
                evaluation,
                historical_model_coverage_status=(
                    eligibility_record.prior_history_identity.get("coverage_status")
                    if eligibility_record is not None
                    else evaluation.historical_model_coverage_status
                ),
            )
        )
    evaluations = tuple(enriched_evaluations)
    eligible_evaluations = tuple(
        sorted(
            (
                evaluation
                for evaluation in evaluations
                if evaluation.forecast_run_id in eligible_ids
            ),
            key=lambda evaluation: evaluation.evaluation_id,
        )
    )
    eligible_weather_rows = tuple(
        sorted(
            (row for row in weather_diagnostic_rows if row.forecast_run_id in eligible_ids),
            key=lambda row: (row.forecast_run_id, row.horizon_hours, row.base_id),
        )
    )
    limited_run_ids = {
        evaluation.forecast_run_id
        for evaluation in eligible_evaluations
        if evaluation.historical_model_coverage_status != "COMPLETE"
    }
    coverage_limited = tuple(
        evaluation
        for evaluation in eligible_evaluations
        if evaluation.historical_model_coverage_status != "COMPLETE"
    )
    stable: tuple[EvaluationEvidence, ...] = ()
    all_metrics = _summarize_group(eligible_evaluations)
    stable_metrics = _summarize_group(stable)
    stable_metrics["cohort_status"] = STABLE_HISTORY_COHORT_STATUS
    coverage_limited_metrics = _summarize_group(coverage_limited)
    coverage_limited_metrics["cohort_status"] = "HISTORICAL_MODEL_COVERAGE"
    baseline_metrics = {
        "ALL_ELIGIBLE_BASES": all_metrics,
        "STABLE_HISTORY_BASES": stable_metrics,
        "COVERAGE_LIMITED_BASES": coverage_limited_metrics,
    }
    diagnostic = compute_weather_diagnostic(eligible_weather_rows)
    weather_quality = _weather_quality(eligible_evaluations)
    if not eligible_evaluations or not eligible_weather_rows:
        conclusion = "INCONCLUSIVE"
    elif not diagnostic["weather_signal_found"]:
        conclusion = "NOT_DEMONSTRATED"
    else:
        # No minimum sample or business acceptance threshold is frozen in V0.6;
        # a descriptive signal therefore remains inconclusive until a later
        # authorized prospective policy supplies an evidence gate.
        conclusion = "INCONCLUSIVE"
    recommendation = (
        "INSUFFICIENT_EVIDENCE"
        if conclusion != "SUPPORTED_BY_CURRENT_EVIDENCE"
        else "PROCEED_TO_CONTROLLED_EXPERIMENT"
    )
    evidence = {
        "eligible_forecast_run_count": len(eligible_evaluations),
        "eligible_base_count": len({item.base_id for item in eligible_evaluations}),
        "complete_season_count": sum(
            item.actual_coverage_status == "COMPLETE" for item in eligible_evaluations
        ),
        "partial_season_count": sum(
            item.actual_coverage_status == "PARTIAL" for item in eligible_evaluations
        ),
        "D1_SAMPLE_COUNT": sum(row.horizon_hours == 24 for row in eligible_weather_rows),
        "D3_SAMPLE_COUNT": sum(row.horizon_hours == 72 for row in eligible_weather_rows),
        "D7_SAMPLE_COUNT": sum(row.horizon_hours == 168 for row in eligible_weather_rows),
        "D15_SAMPLE_COUNT": sum(row.horizon_hours == 360 for row in eligible_weather_rows),
        "complete_actual_coverage": bool(eligible_evaluations)
        and all(item.actual_coverage_status == "COMPLETE" for item in eligible_evaluations),
        "stable_history_cohort_status": STABLE_HISTORY_COHORT_STATUS,
        "coverage_limited_semantics": "HISTORICAL_MODEL_COVERAGE",
        "policy": EVIDENCE_SUFFICIENCY_POLICY,
    }
    coverage_summary = {
        "eligible": _summarize_group(eligible_evaluations),
        "stable_history": stable_metrics,
        "coverage_limited": coverage_limited_metrics,
    }
    actual_weather_hashes = tuple(
        sorted(
            {
                weather_hash
                for item in eligibility
                if item.prospective_eligible
                for weather_hash in item.weather_snapshot_authority_hashes
            }
        )
    )
    computed_model_hash = model_a_hash or hash_payload(
        {
            "model_a_identity": MODEL_A_IDENTITY,
            "total_model_id": MODEL_A_TOTAL_MODEL,
            "temporal_model_id": MODEL_A_TEMPORAL_MODEL,
        }
    )
    history_coverage_records = tuple(
        sorted(
            (
                {
                    "run_id": item.forecast_run_id,
                    "base_id": item.base_id,
                    "status": item.prior_history_identity.get("coverage_status") or "UNKNOWN",
                    "source_hash": item.prior_history_identity.get("source_hash"),
                    "identity_mapping_hash": item.prior_history_identity.get(
                        "identity_mapping_hash"
                    ),
                }
                for item in eligibility
                if item.prospective_eligible
            ),
            key=lambda item: str(item["run_id"]),
        )
    )
    sample_scope = {
        "all_eligible": sorted(
            item.forecast_run_id for item in eligibility if item.prospective_eligible
        ),
        "stable_history_cohort": {
            "status": STABLE_HISTORY_COHORT_STATUS,
            "base_ids": [],
            "policy_version": None,
            "policy_hash": None,
            "source_identity": None,
            "source_hash": None,
        },
        "historical_model_coverage_cohort": {
            "semantic": "HISTORICAL_MODEL_COVERAGE",
            "source": HISTORICAL_MODEL_COVERAGE_COHORT_SOURCE,
            "records": list(history_coverage_records),
        },
        "coverage_limited_cohort": {
            "semantic": "HISTORICAL_MODEL_COVERAGE",
            "source": HISTORICAL_MODEL_COVERAGE_COHORT_SOURCE,
            "run_ids": sorted(item.forecast_run_id for item in coverage_limited),
            "base_ids": sorted({item.base_id for item in coverage_limited}),
            "prior_history_statuses": sorted(
                {
                    item.prior_history_identity.get("coverage_status") or "UNKNOWN"
                    for item in eligibility
                    if item.forecast_run_id in limited_run_ids
                }
            ),
            "source_hashes": sorted(
                {
                    str(value)
                    for item in eligibility
                    if item.forecast_run_id in limited_run_ids
                    for value in (
                        item.prior_history_identity.get("source_hash"),
                        item.prior_history_identity.get("identity_mapping_hash"),
                    )
                    if value
                }
            ),
        },
        "actual_coverage": {
            "semantic": "CURRENT_SEASON_ACTUAL_COVERAGE",
            "complete_run_ids": sorted(
                item.forecast_run_id
                for item in eligible_evaluations
                if item.actual_coverage_status == "COMPLETE"
            ),
            "partial_run_ids": sorted(
                item.forecast_run_id
                for item in eligible_evaluations
                if item.actual_coverage_status == "PARTIAL"
            ),
        },
        "coverage_limited": sorted(item.forecast_run_id for item in coverage_limited),
    }
    warnings = ("INSUFFICIENT_MATURED_PIT_EVIDENCE",) if not eligible_evaluations else ()
    provisional = S4AssessmentComputation(
        validation_run_id="pending",
        assessment_id="pending",
        created_at=created_at,
        policy_version=policy_version,
        model_a_identity=MODEL_A_IDENTITY,
        model_a_hash=computed_model_hash,
        eligibility=eligibility,
        s3_evaluation_ids=tuple(item.evaluation_id for item in eligible_evaluations),
        sample_scope=sample_scope,
        coverage_summary=coverage_summary,
        baseline_metrics=baseline_metrics,
        weather_quality_metrics=weather_quality,
        weather_incremental_metrics=diagnostic,
        evidence_sufficiency=evidence,
        weather_incremental_value_conclusion=conclusion,
        v0_7_recommendation=recommendation,
        weather_snapshot_authority_hashes=actual_weather_hashes,
        warnings=warnings,
        payload_hash="pending",
        result_hash="pending",
    )
    identity_hash = hash_payload(provisional.identity_payload())
    result_hash = provisional.compute_result_hash()
    payload_hash = hash_payload(
        {"identity": provisional.identity_payload(), "result": provisional.result_payload()}
    )
    return replace(
        provisional,
        validation_run_id=f"prospective_validation_{identity_hash}",
        assessment_id=f"weather_assessment_{identity_hash}",
        payload_hash=payload_hash,
        result_hash=result_hash,
    )


__all__ = [
    "EVIDENCE_SUFFICIENCY_POLICY",
    "EvaluationDailyEvidence",
    "EvaluationEvidence",
    "FORECAST_TIME_WEATHER_ONLY",
    "GDD_INCREMENTAL_VALUE_STATUS",
    "MODEL_A_IDENTITY",
    "MODEL_A_TEMPORAL_MODEL",
    "MODEL_A_TOTAL_MODEL",
    "PROSPECTIVE_POLICY_VERSION",
    "ProspectiveEligibilityRecord",
    "REALIZED_WEATHER_AS_MODEL_INPUT",
    "S4AssessmentComputation",
    "STABLE_HISTORY_COHORT_STATUS",
    "V0_7_RECOMMENDATIONS",
    "WEATHER_HORIZONS",
    "WeatherDiagnosticRow",
    "build_assessment",
    "build_prospective_eligibility",
    "compute_weather_diagnostic",
    "weather_snapshot_is_pit_eligible",
]
