"""V0.3 S4 Candidate 04 historical-only yield-amplitude scorer.

Candidate 04 is deliberately separate from the production planning model.  It
derives a quantity-amplitude multiplier from chronological inner folds of the
accepted SOURCE-002 TRAIN partition and applies that multiplier to the
existing ``prediction_total * curve_share`` historical prediction math.  The
module has no TEST reader, no weather/plan dependency, no scoring callback,
and no durable-budget mutation path.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Final

from backend.app.maturity.config import MaturityCurveConfig, load_maturity_curve_config
from backend.app.maturity.model import fit_shared_curve
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    INCUMBENT_MODEL_ID,
    METRIC_CONTRACT_IDENTITY,
    METRIC_CONTRACT_VERSION,
    V2_FORECAST_HORIZONS,
    V2_GUARDRAIL_POLICY_HASH,
    V2_GUARDRAIL_POLICY_VERSION,
    CandidateExecutionGateRequest,
    CandidateExecutionGateResult,
    CandidateRegistration,
    check_candidate_execution_gate,
)
from backend.app.s4_local_engineering import (
    V2HistoricalEvaluationAuthority,
    v2_training_rows,
    validate_v2_forecast_horizon,
)

C04_CANDIDATE_ID: Final[str] = "04_yield_parameter"
C04_CANDIDATE_FAMILY: Final[str] = "PARAMETER_CALIBRATION"
C04_PARENT_MODEL_ID: Final[str] = INCUMBENT_MODEL_ID
C04_HYPOTHESIS: Final[str] = "versioned_yield_parameter_calibration_reduces_quantity_error"
C04_PARAMETER_MANIFEST_VERSION: Final[str] = "v0.3-s4-c04-yield-parameter-manifest-v1"
C04_PARAMETER_SEMANTIC: Final[str] = "TRAIN_DERIVED_POINT_FORECAST_YIELD_AMPLITUDE_MULTIPLIER"
C04_PARAMETER_UNIT: Final[str] = "RATIO"
C04_PARAMETER_PATH: Final[str] = "yield_amplitude_multiplier"
C04_ALLOWED_PARAMETER_PATHS: Final[tuple[str, ...]] = (C04_PARAMETER_PATH,)
C04_BASELINE_MULTIPLIER: Final[Decimal] = Decimal("1.0")
C04_PARAMETER_DERIVATION_POLICY: Final[str] = (
    "TRAIN_ONLY_CHRONOLOGICAL_INNER_FOLDS_MEDIAN_AMPLITUDE_RATIO_V1"
)
C04_RANDOM_SEED_POLICY: Final[str] = "FIXED_AND_RECORDED_PER_RUN"
C04_RANDOM_SEED: Final[int] = 20260624
C04_PLANNED_RUN_COUNT: Final[int] = 4
C04_INCUMBENT_CONFIG_PATH: Final[str] = "configs/maturity_curve.yaml"
C04_INCUMBENT_CONFIG_FILE_SHA256: Final[str] = (
    "fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace"
)
C04_INCUMBENT_CONFIG_HASH: Final[str] = (
    "3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c"
)
C04_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS: Final[Decimal] = Decimal("21")
C04_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES: Final[int] = 3
C04_INCUMBENT_FORECAST_OBSERVED_PHASE_ADJUSTMENT_MAX_DAYS: Final[Decimal] = Decimal("14")
C04_MODEL_IDENTITY: Final[str] = INCUMBENT_MODEL_ID
C04_AUTHORITY_CLASS: Final[str] = "S4_V2_HISTORICAL_ONLY_CANDIDATE_04"
C04_HISTORICAL_ONLY_SCORING_PATH_EXISTS: Final[bool] = True
C04_PARAMETER_REACHES_PREDICTION_MATH: Final[bool] = True
C04_PARAMETER_CHANGE_CAN_CHANGE_PREDICTION: Final[bool] = True
C04_TEST_REMAINS_SEALED: Final[bool] = True
C04_VALIDATION_USED_FOR_PARAMETER_DERIVATION: Final[bool] = False
C04_TEST_USED: Final[bool] = False
C04_WEATHER_USED: Final[bool] = False
C04_PRODUCTION_PLAN_USED: Final[bool] = False
C04_TASK8_USED: Final[bool] = False
C04_TASK9_USED: Final[bool] = False
C04_FORECAST_HORIZONS: Final[tuple[int, ...]] = V2_FORECAST_HORIZONS
C04_COMPLETE_WINDOW_GUARDRAIL_BLOCKER: Final[str] = "COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE"
C04_FUTURE_EXECUTION_PRIMARY_METRIC_COMPUTABLE: Final[bool] = True
C04_FUTURE_EXECUTION_FULL_GUARDRAIL_COMPUTABLE: Final[bool] = False
_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_DECIMAL_QUANTUM: Final[Decimal] = Decimal("0.000001")
_MIN_CURVE_POINTS: Final[int] = 4

GroupKey = tuple[str, str, str, str]
FoldDates = tuple[tuple[date, ...], tuple[date, ...]]


class C04HistoricalScorerError(ValueError):
    """Sanitized, machine-readable C04 contract failure."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _q(value: Decimal) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise C04HistoricalScorerError("C04_NONFINITE_DECIMAL")
    return value.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)


def _median(values: list[Decimal]) -> Decimal:
    if not values:
        raise C04HistoricalScorerError("C04_TRAIN_CALIBRATION_INSUFFICIENT")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return _q(ordered[midpoint])
    return _q((ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2"))


def _group_key(row: MaterializableRow) -> GroupKey:
    return (row.season, row.farm, row.subfarm, row.variety)


def _row_key(row: MaterializableRow) -> tuple[str, str, str, str, date]:
    return (*_group_key(row), row.harvest_business_date)


def _contains_native_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_native_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_native_float(item) for item in value)
    return False


def _decimalize(value: object) -> object:
    """Normalize config numerics before they enter a canonical manifest."""

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise C04HistoricalScorerError("C04_NONFINITE_DECIMAL")
        return value
    if isinstance(value, Mapping):
        return {str(key): _decimalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimalize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_decimalize(item) for item in value)
    return value


def _flatten_paths(value: object, prefix: str = "") -> dict[str, object]:
    if isinstance(value, Mapping):
        flattened: dict[str, object] = {}
        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_paths(value[key], child_prefix))
        return flattened
    return {prefix: value}


@dataclass(frozen=True, slots=True)
class C04ParameterDiff:
    changed_paths: tuple[str, ...]
    unauthorized_paths: tuple[str, ...]
    native_float_present: bool

    @property
    def unauthorized_parameter_diff_count(self) -> int:
        return len(self.unauthorized_paths)


def verify_c04_parameter_allowlist(
    *,
    incumbent_snapshot: Mapping[str, object],
    candidate_snapshot: Mapping[str, object],
) -> C04ParameterDiff:
    """Prove that a candidate snapshot changes only the C04 amplitude."""

    incumbent = _decimalize(incumbent_snapshot)
    candidate = _decimalize(candidate_snapshot)
    if not isinstance(incumbent, Mapping) or not isinstance(candidate, Mapping):
        raise C04HistoricalScorerError("C04_PARAMETER_SNAPSHOT_INVALID")
    incumbent_flat = _flatten_paths(incumbent)
    candidate_flat = _flatten_paths(candidate)
    all_paths = sorted(set(incumbent_flat) | set(candidate_flat))
    changed_paths = tuple(
        path for path in all_paths if incumbent_flat.get(path) != candidate_flat.get(path)
    )
    unauthorized_paths = tuple(
        path for path in changed_paths if path not in C04_ALLOWED_PARAMETER_PATHS
    )
    return C04ParameterDiff(
        changed_paths=changed_paths,
        unauthorized_paths=unauthorized_paths,
        native_float_present=(
            _contains_native_float(incumbent_snapshot) or _contains_native_float(candidate_snapshot)
        ),
    )


def _config_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_incumbent_config_values(config: MaturityCurveConfig) -> None:
    if config.config_hash != C04_INCUMBENT_CONFIG_HASH:
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_IDENTITY_MISMATCH")
    if (
        config.rules.offset.maximum_abs_shift_days != C04_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS
        or config.rules.offset.minimum_training_samples
        != C04_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES
        or config.rules.forecast.observed_phase_adjustment_max_days
        != C04_INCUMBENT_FORECAST_OBSERVED_PHASE_ADJUSTMENT_MAX_DAYS
    ):
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_SEMANTIC_MISMATCH")


def _validate_incumbent_config(path: Path, config: MaturityCurveConfig) -> None:
    if _config_file_sha256(path) != C04_INCUMBENT_CONFIG_FILE_SHA256:
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_IDENTITY_MISMATCH")
    _validate_incumbent_config_values(config)


def _snapshot_value(snapshot: Mapping[str, object], path: str) -> object:
    current: object = snapshot
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_SNAPSHOT_INVALID")
        current = current[segment]
    return current


def _validate_incumbent_snapshot(snapshot: Mapping[str, object]) -> None:
    if (
        _decimalize(_snapshot_value(snapshot, "offset.maximum_abs_shift_days"))
        != C04_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS
        or _snapshot_value(snapshot, "offset.minimum_training_samples")
        != C04_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES
        or _decimalize(_snapshot_value(snapshot, "forecast.observed_phase_adjustment_max_days"))
        != C04_INCUMBENT_FORECAST_OBSERVED_PHASE_ADJUSTMENT_MAX_DAYS
    ):
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_SEMANTIC_MISMATCH")


@dataclass(frozen=True, slots=True)
class C04InnerFoldCalibration:
    """One chronological TRAIN-only calibration fold."""

    fold_ordinal: int
    fit_start_date: date
    fit_end_date: date
    holdout_start_date: date
    holdout_end_date: date
    fit_row_count: int
    holdout_row_count: int
    comparable_group_count: int
    amplitude_ratio: Decimal

    def payload(self) -> dict[str, object]:
        return {
            "fold_ordinal": self.fold_ordinal,
            "fit_start_date": self.fit_start_date,
            "fit_end_date": self.fit_end_date,
            "holdout_start_date": self.holdout_start_date,
            "holdout_end_date": self.holdout_end_date,
            "fit_row_count": self.fit_row_count,
            "holdout_row_count": self.holdout_row_count,
            "comparable_group_count": self.comparable_group_count,
            "amplitude_ratio": self.amplitude_ratio,
        }


@dataclass(frozen=True, slots=True)
class C04ParameterDerivation:
    """Deterministic four-value parameter derivation from TRAIN only."""

    policy: str
    folds: tuple[C04InnerFoldCalibration, ...]
    parameter_values: tuple[Decimal, ...]
    validation_used_for_parameter_derivation: bool
    test_used: bool

    def payload(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "folds": [fold.payload() for fold in self.folds],
            "parameter_values": self.parameter_values,
            "validation_used_for_parameter_derivation": (
                self.validation_used_for_parameter_derivation
            ),
            "test_used": self.test_used,
        }


def _fold_dates(train_rows: tuple[MaterializableRow, ...]) -> tuple[FoldDates, ...]:
    dates = tuple(sorted({row.harvest_business_date for row in train_rows}))
    if len(dates) < 5:
        raise C04HistoricalScorerError("C04_TRAIN_CALIBRATION_INSUFFICIENT")
    boundaries = tuple((len(dates) * index) // 5 for index in range(6))
    result: list[FoldDates] = []
    for index in range(1, 5):
        fit_dates = dates[: boundaries[index]]
        holdout_dates = dates[boundaries[index] : boundaries[index + 1]]
        if not fit_dates or not holdout_dates or fit_dates[-1] >= holdout_dates[0]:
            raise C04HistoricalScorerError("C04_INNER_FOLD_TIME_ORDER_INVALID")
        result.append((fit_dates + holdout_dates, fit_dates))
    return tuple(result)


def _derive_fold_ratio(
    fit_rows: tuple[MaterializableRow, ...],
    holdout_rows: tuple[MaterializableRow, ...],
) -> tuple[Decimal, int]:
    fit_totals: dict[GroupKey, Decimal] = defaultdict(lambda: Decimal("0"))
    holdout_totals: dict[GroupKey, Decimal] = defaultdict(lambda: Decimal("0"))
    fit_dates: dict[GroupKey, set[date]] = defaultdict(set)
    holdout_dates: dict[GroupKey, set[date]] = defaultdict(set)
    for row in fit_rows:
        key = _group_key(row)
        fit_totals[key] += row.actual_harvest_quantity_kg
        fit_dates[key].add(row.harvest_business_date)
    for row in holdout_rows:
        key = _group_key(row)
        holdout_totals[key] += row.actual_harvest_quantity_kg
        holdout_dates[key].add(row.harvest_business_date)

    ratios: list[Decimal] = []
    for key in sorted(holdout_totals):
        fit_total = fit_totals.get(key, Decimal("0"))
        fit_day_count = len(fit_dates.get(key, set()))
        holdout_day_count = len(holdout_dates[key])
        if fit_total <= 0 or fit_day_count <= 0 or holdout_day_count <= 0:
            continue
        base_total = fit_total * Decimal(holdout_day_count) / Decimal(fit_day_count)
        if base_total <= 0:
            continue
        observed_total = holdout_totals[key]
        if observed_total < 0:
            raise C04HistoricalScorerError("C04_NEGATIVE_TRAIN_QUANTITY")
        ratios.append(observed_total / base_total)
    if not ratios:
        raise C04HistoricalScorerError("C04_TRAIN_CALIBRATION_INSUFFICIENT")
    return _median(ratios), len(ratios)


def derive_c04_parameter_calibration(
    train_rows: tuple[MaterializableRow, ...],
) -> C04ParameterDerivation:
    """Derive exactly four positive multipliers from chronological TRAIN folds."""

    if not train_rows or any(
        type(row.actual_harvest_quantity_kg) is not Decimal for row in train_rows
    ):
        raise C04HistoricalScorerError("C04_TRAIN_INPUT_INVALID")
    ordered = tuple(sorted(train_rows, key=_row_key))
    fold_specs = _fold_dates(ordered)
    folds: list[C04InnerFoldCalibration] = []
    values: list[Decimal] = []
    for ordinal, (all_dates, fit_dates) in enumerate(fold_specs, start=1):
        fit_date_set = set(fit_dates)
        holdout_date_set = set(all_dates).difference(fit_date_set)
        fit_rows = tuple(row for row in ordered if row.harvest_business_date in fit_date_set)
        holdout_rows = tuple(
            row for row in ordered if row.harvest_business_date in holdout_date_set
        )
        ratio, comparable_groups = _derive_fold_ratio(fit_rows, holdout_rows)
        folds.append(
            C04InnerFoldCalibration(
                fold_ordinal=ordinal,
                fit_start_date=fit_dates[0],
                fit_end_date=fit_dates[-1],
                holdout_start_date=min(holdout_date_set),
                holdout_end_date=max(holdout_date_set),
                fit_row_count=len(fit_rows),
                holdout_row_count=len(holdout_rows),
                comparable_group_count=comparable_groups,
                amplitude_ratio=ratio,
            )
        )
        values.append(ratio)
    parameter_values = tuple(values)
    if len(parameter_values) != C04_PLANNED_RUN_COUNT:
        raise C04HistoricalScorerError("C04_PARAMETER_VALUE_COUNT_INVALID")
    if len(set(parameter_values)) != C04_PLANNED_RUN_COUNT:
        raise C04HistoricalScorerError("C04_PARAMETER_VALUES_NOT_UNIQUE")
    if any(value <= 0 or not value.is_finite() for value in parameter_values):
        raise C04HistoricalScorerError("C04_PARAMETER_VALUES_INVALID")
    return C04ParameterDerivation(
        policy=C04_PARAMETER_DERIVATION_POLICY,
        folds=tuple(folds),
        parameter_values=parameter_values,
        validation_used_for_parameter_derivation=C04_VALIDATION_USED_FOR_PARAMETER_DERIVATION,
        test_used=C04_TEST_USED,
    )


def _fit_curve(
    samples: tuple[tuple[int, Decimal], ...],
    *,
    config: MaturityCurveConfig,
    support_days: tuple[int, ...],
) -> tuple[Decimal, ...] | None:
    samples_by_day: dict[int, list[Decimal]] = defaultdict(list)
    for relative_day, value in samples:
        samples_by_day[relative_day].append(value)
    total = sum((value for _, value in samples), Decimal("0"))
    if total <= 0:
        return None
    if len(samples_by_day) < max(config.rules.curve.spline_degree + 1, _MIN_CURVE_POINTS):
        return None
    relative_days = tuple(sorted(samples_by_day))
    shares = tuple(
        (sum(samples_by_day[day], Decimal("0")) / total).quantize(_DECIMAL_QUANTUM)
        for day in relative_days
    )
    weights = tuple(
        Decimal(len(samples_by_day[day])).quantize(_DECIMAL_QUANTUM) for day in relative_days
    )
    try:
        return fit_shared_curve(
            relative_days=relative_days,
            shares=shares,
            sample_weights=weights,
            support_days=support_days,
            spline_degree=config.rules.curve.spline_degree,
            spline_knot_count=config.rules.curve.spline_knot_count,
            ridge_alpha=config.rules.curve.ridge_alpha,
        )
    except (ValueError, RuntimeError):
        return None


@dataclass(frozen=True, slots=True)
class _C04TrainingModel:
    support_days: tuple[int, ...]
    group_anchors: Mapping[GroupKey, date]
    variety_anchors: Mapping[str, date]
    group_totals: Mapping[GroupKey, Decimal]
    variety_total_medians: Mapping[str, Decimal]
    group_curves: Mapping[GroupKey, tuple[Decimal, ...] | None]
    variety_curves: Mapping[str, tuple[Decimal, ...] | None]


def _build_training_model(
    train_rows: tuple[MaterializableRow, ...],
    target_rows: tuple[MaterializableRow, ...],
    config: MaturityCurveConfig,
) -> _C04TrainingModel:
    by_group: dict[GroupKey, list[MaterializableRow]] = defaultdict(list)
    by_variety: dict[str, list[MaterializableRow]] = defaultdict(list)
    for row in train_rows:
        by_group[_group_key(row)].append(row)
        by_variety[row.variety].append(row)
    group_anchors = {
        key: min(row.harvest_business_date for row in rows) for key, rows in by_group.items()
    }
    variety_anchors = {
        variety: min(row.harvest_business_date for row in rows)
        for variety, rows in by_variety.items()
    }
    group_totals = {
        key: sum((row.actual_harvest_quantity_kg for row in rows), Decimal("0"))
        for key, rows in by_group.items()
    }
    variety_total_medians = {
        variety: _median([group_totals[key] for key in sorted(group_totals) if key[3] == variety])
        for variety in sorted(by_variety)
    }
    relative_max = config.rules.curve.support_max_day
    for row in target_rows:
        key = _group_key(row)
        anchor = group_anchors.get(key) or variety_anchors.get(row.variety)
        if anchor is not None:
            relative_max = max(relative_max, (row.harvest_business_date - anchor).days)
    support_days = tuple(range(config.rules.curve.support_min_day, relative_max + 1))
    group_curves = {
        key: _fit_curve(
            tuple(
                (
                    (row.harvest_business_date - group_anchors[key]).days,
                    row.actual_harvest_quantity_kg,
                )
                for row in rows
            ),
            config=config,
            support_days=support_days,
        )
        for key, rows in by_group.items()
    }
    variety_curves: dict[str, tuple[Decimal, ...] | None] = {}
    for variety in sorted(by_variety):
        normalized_samples: list[tuple[int, Decimal]] = []
        for key in sorted(by_group):
            if key[3] != variety:
                continue
            group_total = group_totals[key]
            if group_total <= 0:
                continue
            anchor = group_anchors[key]
            normalized_samples.extend(
                (
                    (row.harvest_business_date - anchor).days,
                    row.actual_harvest_quantity_kg / group_total,
                )
                for row in sorted(by_group[key], key=_row_key)
            )
        variety_curves[variety] = _fit_curve(
            tuple(normalized_samples),
            config=config,
            support_days=support_days,
        )
    return _C04TrainingModel(
        support_days=support_days,
        group_anchors=group_anchors,
        variety_anchors=variety_anchors,
        group_totals=group_totals,
        variety_total_medians=variety_total_medians,
        group_curves=group_curves,
        variety_curves=variety_curves,
    )


@dataclass(frozen=True, slots=True)
class C04Prediction:
    """Prediction projection without copying target actual values."""

    season: str
    farm: str
    subfarm: str
    variety: str
    harvest_business_date: date
    forecast_cutoff_at: date
    horizon_days: int
    multiplier: Decimal
    base_prediction_total_kg: Decimal
    curve_share: Decimal
    base_p50_kg: Decimal
    candidate_p50_kg: Decimal
    candidate_p80_kg: Decimal
    candidate_p90_kg: Decimal
    model_identity: str = C04_MODEL_IDENTITY

    def payload(self) -> dict[str, object]:
        return {
            "season": self.season,
            "farm": self.farm,
            "subfarm": self.subfarm,
            "variety": self.variety,
            "harvest_business_date": self.harvest_business_date,
            "forecast_cutoff_at": self.forecast_cutoff_at,
            "horizon_days": self.horizon_days,
            "multiplier": self.multiplier,
            "base_prediction_total_kg": self.base_prediction_total_kg,
            "curve_share": self.curve_share,
            "base_p50_kg": self.base_p50_kg,
            "candidate_p50_kg": self.candidate_p50_kg,
            "candidate_p80_kg": self.candidate_p80_kg,
            "candidate_p90_kg": self.candidate_p90_kg,
            "model_identity": self.model_identity,
        }


@dataclass(frozen=True, slots=True)
class C04ParameterEffectProof:
    baseline_multiplier: Decimal
    alternate_multiplier: Decimal
    baseline_prediction_identity: str
    alternate_prediction_identity: str
    changed_prediction_count: int
    base_replay_exact: bool

    @property
    def parameter_reaches_prediction_math(self) -> bool:
        return self.changed_prediction_count > 0

    @property
    def parameter_change_can_change_prediction(self) -> bool:
        return self.parameter_reaches_prediction_math


@dataclass(frozen=True, slots=True)
class C04HistoricalYieldScorer:
    """SOURCE-002-only production-facing candidate prediction path."""

    train_rows: tuple[MaterializableRow, ...]
    forecast_cutoff_at: date
    train_dataset_identity: str
    config: MaturityCurveConfig

    @classmethod
    def from_v2_authority(
        cls,
        authority: V2HistoricalEvaluationAuthority,
        config: MaturityCurveConfig,
    ) -> C04HistoricalYieldScorer:
        if authority.test_remains_sealed is not True:
            raise C04HistoricalScorerError("C04_TEST_MUST_REMAIN_SEALED")
        train_rows = v2_training_rows(authority)
        if authority.source_id != "SOURCE_002" or authority.train_row_count != len(train_rows):
            raise C04HistoricalScorerError("C04_SOURCE_002_TRAIN_IDENTITY_MISMATCH")
        _validate_incumbent_config_values(config)
        return cls(
            train_rows=train_rows,
            forecast_cutoff_at=authority.forecast_cutoff_at,
            train_dataset_identity=authority.train_dataset_identity,
            config=config,
        )

    def predict_rows(
        self,
        target_rows: tuple[MaterializableRow, ...],
        multiplier: Decimal,
    ) -> tuple[C04Prediction, ...]:
        if type(multiplier) is not Decimal or not multiplier.is_finite() or multiplier <= 0:
            raise C04HistoricalScorerError("C04_PARAMETER_VALUES_INVALID")
        if not target_rows:
            raise C04HistoricalScorerError("C04_TARGET_ROWS_EMPTY")
        for row in target_rows:
            horizon_days = (row.harvest_business_date - self.forecast_cutoff_at).days
            try:
                validate_v2_forecast_horizon(horizon_days)
            except ValueError as exc:
                raise C04HistoricalScorerError("C04_HORIZON_NOT_IN_FROZEN_SET") from exc
        model = _build_training_model(self.train_rows, target_rows, self.config)
        p80_multiplier = Decimal("1") + self.config.rules.intervals.p80_quantile / Decimal("2")
        p90_multiplier = Decimal("1") + self.config.rules.intervals.p90_quantile
        predictions: list[C04Prediction] = []
        for row in sorted(target_rows, key=_row_key):
            horizon_days = (row.harvest_business_date - self.forecast_cutoff_at).days
            key = _group_key(row)
            anchor = model.group_anchors.get(key) or model.variety_anchors.get(row.variety)
            curve = model.group_curves.get(key) or model.variety_curves.get(row.variety)
            base_total = model.group_totals.get(key) or model.variety_total_medians.get(row.variety)
            if anchor is None or curve is None or base_total is None:
                raise C04HistoricalScorerError("C04_TRAIN_SUPPORT_UNAVAILABLE")
            relative_day = (row.harvest_business_date - anchor).days
            if relative_day < model.support_days[0] or relative_day > model.support_days[-1]:
                raise C04HistoricalScorerError("C04_TRAIN_SUPPORT_UNAVAILABLE")
            curve_share = _q(curve[relative_day - model.support_days[0]])
            base_p50 = _q(base_total * curve_share)
            candidate_p50 = _q(base_total * multiplier * curve_share)
            candidate_p80 = max(_q(candidate_p50 * p80_multiplier), candidate_p50)
            candidate_p90 = max(_q(candidate_p50 * p90_multiplier), candidate_p80, candidate_p50)
            predictions.append(
                C04Prediction(
                    season=row.season,
                    farm=row.farm,
                    subfarm=row.subfarm,
                    variety=row.variety,
                    harvest_business_date=row.harvest_business_date,
                    forecast_cutoff_at=self.forecast_cutoff_at,
                    horizon_days=horizon_days,
                    multiplier=multiplier,
                    base_prediction_total_kg=_q(base_total),
                    curve_share=curve_share,
                    base_p50_kg=base_p50,
                    candidate_p50_kg=candidate_p50,
                    candidate_p80_kg=candidate_p80,
                    candidate_p90_kg=candidate_p90,
                )
            )
        return tuple(predictions)

    @staticmethod
    def prediction_identity(predictions: tuple[C04Prediction, ...]) -> str:
        return sha256_payload([prediction.payload() for prediction in predictions])

    def prove_parameter_effect(
        self,
        target_rows: tuple[MaterializableRow, ...],
        *,
        alternate_multiplier: Decimal = Decimal("2.0"),
    ) -> C04ParameterEffectProof:
        baseline = self.predict_rows(target_rows, C04_BASELINE_MULTIPLIER)
        alternate = self.predict_rows(target_rows, alternate_multiplier)
        changed = sum(
            left.candidate_p50_kg != right.candidate_p50_kg
            for left, right in zip(baseline, alternate, strict=True)
        )
        return C04ParameterEffectProof(
            baseline_multiplier=C04_BASELINE_MULTIPLIER,
            alternate_multiplier=alternate_multiplier,
            baseline_prediction_identity=self.prediction_identity(baseline),
            alternate_prediction_identity=self.prediction_identity(alternate),
            changed_prediction_count=changed,
            base_replay_exact=all(item.base_p50_kg == item.candidate_p50_kg for item in baseline),
        )

    def predict_manifest_run(
        self,
        manifest: C04ParameterManifest,
        candidate_run_ordinal: int,
        target_rows: tuple[MaterializableRow, ...],
    ) -> tuple[C04Prediction, ...]:
        """Predict only the frozen multiplier bound to a manifest run."""

        validate_c04_parameter_manifest(manifest)
        if (
            self.train_dataset_identity != manifest.train_dataset_identity
            or self.config.config_hash != manifest.incumbent_config_hash
        ):
            raise C04HistoricalScorerError("C04_SCORER_BINDING_MISMATCH")
        return self.predict_rows(target_rows, manifest.run(candidate_run_ordinal).parameter_value)


def build_c04_historical_yield_scorer(
    *,
    authority: V2HistoricalEvaluationAuthority,
    config_path: Path,
) -> C04HistoricalYieldScorer:
    """Bind the C04 predictor to verified V2 authority and incumbent config."""

    if not config_path.is_file():
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_UNAVAILABLE")
    config = load_maturity_curve_config(config_path)
    _validate_incumbent_config(config_path, config)
    return C04HistoricalYieldScorer.from_v2_authority(authority, config)


@dataclass(frozen=True, slots=True)
class C04RunDefinition:
    candidate_run_ordinal: int
    parameter_value: Decimal
    derivation_fold_ordinal: int
    authorized_parameter_delta: Mapping[str, object]
    full_parameter_snapshot: Mapping[str, object]
    candidate_config_hash: str
    parameter_manifest_hash: str
    random_seed: int
    unauthorized_parameter_diff_count: int

    def payload(self) -> dict[str, object]:
        return {
            "candidate_run_ordinal": self.candidate_run_ordinal,
            "parameter_value": self.parameter_value,
            "derivation_fold_ordinal": self.derivation_fold_ordinal,
            "authorized_parameter_delta": deepcopy(dict(self.authorized_parameter_delta)),
            "full_parameter_snapshot": deepcopy(dict(self.full_parameter_snapshot)),
            "candidate_config_hash": self.candidate_config_hash,
            "parameter_manifest_hash": self.parameter_manifest_hash,
            "random_seed": self.random_seed,
            "unauthorized_parameter_diff_count": self.unauthorized_parameter_diff_count,
        }

    @property
    def run_parameter_hash(self) -> str:
        """Backward-compatible name for the run-level manifest hash."""

        return self.parameter_manifest_hash


@dataclass(frozen=True, slots=True)
class C04ParameterManifest:
    version: str
    candidate_id: str
    candidate_family: str
    parent_model_id: str
    hypothesis: str
    parameter_semantic: str
    parameter_unit: str
    parameter_path: str
    baseline_multiplier: Decimal
    parameter_derivation_policy: str
    parameter_values: tuple[Decimal, ...]
    calibration_folds: tuple[C04InnerFoldCalibration, ...]
    experiment_plan_version: str
    experiment_plan_hash: str
    guardrail_policy_version: str
    guardrail_policy_hash: str
    train_dataset_identity: str
    validation_dataset_identity: str
    actual_label_set_identity: str
    cutoff_policy_identity: str
    forecast_horizon_set_identity: str
    business_grain_set_identity: str
    common_comparable_set_identity: str
    incumbent_config_path: str
    incumbent_config_file_sha256: str
    incumbent_config_hash: str
    incumbent_parameter_snapshot: Mapping[str, object]
    materialized_dataset_identity: str
    allowed_parameter_paths: tuple[str, ...]
    code_commit_binding: str
    random_seed_policy: str
    random_seed: int
    planned_run_count: int
    adaptive_search_allowed: bool
    post_validation_parameter_substitution_allowed: bool
    validation_used_for_parameter_derivation: bool
    test_used: bool
    test_remains_sealed: bool
    uses_weather: bool
    uses_production_plan: bool
    uses_task8: bool
    uses_task9: bool
    runs: tuple[C04RunDefinition, ...]

    def payload(self) -> dict[str, object]:
        return {
            "manifest_version": self.version,
            "candidate_id": self.candidate_id,
            "candidate_family": self.candidate_family,
            "parent_model_id": self.parent_model_id,
            "hypothesis": self.hypothesis,
            "parameter_semantic": self.parameter_semantic,
            "parameter_unit": self.parameter_unit,
            "parameter_path": self.parameter_path,
            "baseline_multiplier": self.baseline_multiplier,
            "parameter_derivation_policy": self.parameter_derivation_policy,
            "parameter_values": self.parameter_values,
            "calibration_folds": [fold.payload() for fold in self.calibration_folds],
            "experiment_plan_version": self.experiment_plan_version,
            "experiment_plan_hash": self.experiment_plan_hash,
            "guardrail_policy_version": self.guardrail_policy_version,
            "guardrail_policy_hash": self.guardrail_policy_hash,
            "train_dataset_identity": self.train_dataset_identity,
            "validation_dataset_identity": self.validation_dataset_identity,
            "actual_label_set_identity": self.actual_label_set_identity,
            "cutoff_policy_identity": self.cutoff_policy_identity,
            "forecast_horizon_set_identity": self.forecast_horizon_set_identity,
            "business_grain_set_identity": self.business_grain_set_identity,
            "common_comparable_set_identity": self.common_comparable_set_identity,
            "incumbent_config_path": self.incumbent_config_path,
            "incumbent_config_file_sha256": self.incumbent_config_file_sha256,
            "incumbent_config_hash": self.incumbent_config_hash,
            "incumbent_parameter_snapshot": deepcopy(dict(self.incumbent_parameter_snapshot)),
            "materialized_dataset_identity": self.materialized_dataset_identity,
            "allowed_parameter_paths": self.allowed_parameter_paths,
            "code_commit_binding": self.code_commit_binding,
            "random_seed_policy": self.random_seed_policy,
            "random_seed": self.random_seed,
            "planned_run_count": self.planned_run_count,
            "adaptive_search_allowed": self.adaptive_search_allowed,
            "post_validation_parameter_substitution_allowed": (
                self.post_validation_parameter_substitution_allowed
            ),
            "validation_used_for_parameter_derivation": (
                self.validation_used_for_parameter_derivation
            ),
            "test_used": self.test_used,
            "test_remains_sealed": self.test_remains_sealed,
            "uses_weather": self.uses_weather,
            "uses_production_plan": self.uses_production_plan,
            "uses_task8": self.uses_task8,
            "uses_task9": self.uses_task9,
            "runs": [run.payload() for run in self.runs],
        }

    @property
    def manifest_hash(self) -> str:
        return sha256_payload(self.payload())

    @property
    def parameter_value_count(self) -> int:
        return len(self.parameter_values)

    def run(self, ordinal: int) -> C04RunDefinition:
        if ordinal < 1 or ordinal > len(self.runs):
            raise C04HistoricalScorerError("C04_RUN_ORDINAL_INVALID")
        return self.runs[ordinal - 1]


def _candidate_config_hash(snapshot: Mapping[str, object]) -> str:
    return sha256_payload(snapshot)


def _run_parameter_hash(
    *,
    ordinal: int,
    parameter_delta: Mapping[str, object],
    full_snapshot: Mapping[str, object],
    candidate_config_hash: str,
    random_seed: int,
) -> str:
    return sha256_payload(
        {
            "candidate_id": C04_CANDIDATE_ID,
            "candidate_run_ordinal": ordinal,
            "authorized_parameter_delta": parameter_delta,
            "full_parameter_snapshot": full_snapshot,
            "candidate_config_hash": candidate_config_hash,
            "random_seed": random_seed,
        }
    )


def _registered_c04() -> CandidateRegistration:
    registration = next(
        (item for item in FROZEN_CANDIDATE_REGISTRY if item.candidate_id == C04_CANDIDATE_ID),
        None,
    )
    if registration is None:
        raise C04HistoricalScorerError("C04_CANDIDATE_REGISTRY_MISMATCH")
    expected = CandidateRegistration(
        C04_CANDIDATE_ID,
        C04_CANDIDATE_FAMILY,
        C04_PARENT_MODEL_ID,
        C04_HYPOTHESIS,
        "NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION",
        C04_PLANNED_RUN_COUNT,
        C04_RANDOM_SEED_POLICY,
        "REGISTERED_AND_GUARDRAIL_ELIGIBLE",
    )
    if registration != expected:
        raise C04HistoricalScorerError("C04_CANDIDATE_REGISTRY_MISMATCH")
    return registration


def _validate_sha256_identity(value: str, reason: str) -> None:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise C04HistoricalScorerError(reason)


def build_c04_parameter_manifest(
    *,
    authority: V2HistoricalEvaluationAuthority,
    config_path: Path,
    code_commit_binding: str,
) -> C04ParameterManifest:
    """Build the V2-bound C04 manifest without scoring or budget mutation."""

    _registered_c04()
    if not _COMMIT_PATTERN.fullmatch(code_commit_binding):
        raise C04HistoricalScorerError("C04_CODE_COMMIT_BINDING_INVALID")
    if (
        authority.source_id != "SOURCE_002"
        or authority.train_row_count != 16_224
        or authority.validation_row_count != 8_006
        or authority.test_remains_sealed is not True
        or authority.requested_forecast_horizons != C04_FORECAST_HORIZONS
    ):
        raise C04HistoricalScorerError("C04_SOURCE_002_AUTHORITY_MISMATCH")
    for _, identity in authority.identity_values():
        _validate_sha256_identity(identity, "C04_PAIRING_IDENTITY_INVALID")
    if authority.validation_dataset_identity == authority.train_dataset_identity:
        raise C04HistoricalScorerError("C04_PAIRING_IDENTITY_COLLISION")
    if not config_path.is_file():
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_UNAVAILABLE")
    config = load_maturity_curve_config(config_path)
    _validate_incumbent_config(config_path, config)
    derivation = derive_c04_parameter_calibration(authority.train_rows)
    incumbent_snapshot_value = _decimalize(config.snapshot)
    if not isinstance(incumbent_snapshot_value, Mapping):
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_SNAPSHOT_INVALID")
    incumbent_snapshot = deepcopy(dict(incumbent_snapshot_value))
    config_file_sha256 = _config_file_sha256(config_path)
    runs_list: list[C04RunDefinition] = []
    for fold, value in zip(derivation.folds, derivation.parameter_values, strict=True):
        candidate_snapshot = deepcopy(incumbent_snapshot)
        candidate_snapshot[C04_PARAMETER_PATH] = value
        parameter_delta = {C04_PARAMETER_PATH: value}
        diff = verify_c04_parameter_allowlist(
            incumbent_snapshot=incumbent_snapshot,
            candidate_snapshot=candidate_snapshot,
        )
        if diff.native_float_present or diff.changed_paths != C04_ALLOWED_PARAMETER_PATHS:
            raise C04HistoricalScorerError("C04_UNAUTHORIZED_PARAMETER_PATH")
        candidate_config_hash = _candidate_config_hash(candidate_snapshot)
        runs_list.append(
            C04RunDefinition(
                candidate_run_ordinal=fold.fold_ordinal,
                parameter_value=value,
                derivation_fold_ordinal=fold.fold_ordinal,
                authorized_parameter_delta=parameter_delta,
                full_parameter_snapshot=candidate_snapshot,
                candidate_config_hash=candidate_config_hash,
                parameter_manifest_hash=_run_parameter_hash(
                    ordinal=fold.fold_ordinal,
                    parameter_delta=parameter_delta,
                    full_snapshot=candidate_snapshot,
                    candidate_config_hash=candidate_config_hash,
                    random_seed=C04_RANDOM_SEED,
                ),
                random_seed=C04_RANDOM_SEED,
                unauthorized_parameter_diff_count=diff.unauthorized_parameter_diff_count,
            )
        )
    runs = tuple(runs_list)
    manifest = C04ParameterManifest(
        version=C04_PARAMETER_MANIFEST_VERSION,
        candidate_id=C04_CANDIDATE_ID,
        candidate_family=C04_CANDIDATE_FAMILY,
        parent_model_id=C04_PARENT_MODEL_ID,
        hypothesis=C04_HYPOTHESIS,
        parameter_semantic=C04_PARAMETER_SEMANTIC,
        parameter_unit=C04_PARAMETER_UNIT,
        parameter_path=C04_PARAMETER_PATH,
        baseline_multiplier=C04_BASELINE_MULTIPLIER,
        parameter_derivation_policy=derivation.policy,
        parameter_values=derivation.parameter_values,
        calibration_folds=derivation.folds,
        experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        guardrail_policy_version=V2_GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=V2_GUARDRAIL_POLICY_HASH,
        train_dataset_identity=authority.train_dataset_identity,
        validation_dataset_identity=authority.validation_dataset_identity,
        actual_label_set_identity=authority.actual_label_set_identity,
        cutoff_policy_identity=authority.cutoff_policy_identity,
        forecast_horizon_set_identity=authority.forecast_horizon_set_identity,
        business_grain_set_identity=authority.business_grain_set_identity,
        common_comparable_set_identity=authority.common_comparable_set_identity,
        incumbent_config_path=C04_INCUMBENT_CONFIG_PATH,
        incumbent_config_file_sha256=config_file_sha256,
        incumbent_config_hash=config.config_hash,
        incumbent_parameter_snapshot=incumbent_snapshot,
        materialized_dataset_identity=authority.materialized_dataset_identity_sha256,
        allowed_parameter_paths=C04_ALLOWED_PARAMETER_PATHS,
        code_commit_binding=code_commit_binding,
        random_seed_policy=C04_RANDOM_SEED_POLICY,
        random_seed=C04_RANDOM_SEED,
        planned_run_count=C04_PLANNED_RUN_COUNT,
        adaptive_search_allowed=False,
        post_validation_parameter_substitution_allowed=False,
        validation_used_for_parameter_derivation=derivation.validation_used_for_parameter_derivation,
        test_used=derivation.test_used,
        test_remains_sealed=C04_TEST_REMAINS_SEALED,
        uses_weather=C04_WEATHER_USED,
        uses_production_plan=C04_PRODUCTION_PLAN_USED,
        uses_task8=C04_TASK8_USED,
        uses_task9=C04_TASK9_USED,
        runs=runs,
    )
    validate_c04_parameter_manifest(manifest)
    return manifest


def validate_c04_parameter_manifest(manifest: C04ParameterManifest) -> None:
    """Validate registry, V2 identity, derivation, and four-run invariants."""

    _registered_c04()
    if manifest.version != C04_PARAMETER_MANIFEST_VERSION:
        raise C04HistoricalScorerError("C04_PARAMETER_MANIFEST_VERSION_MISMATCH")
    if (
        manifest.candidate_id,
        manifest.candidate_family,
        manifest.parent_model_id,
        manifest.hypothesis,
    ) != (C04_CANDIDATE_ID, C04_CANDIDATE_FAMILY, C04_PARENT_MODEL_ID, C04_HYPOTHESIS):
        raise C04HistoricalScorerError("C04_CANDIDATE_REGISTRY_MISMATCH")
    if (
        manifest.parameter_semantic,
        manifest.parameter_unit,
        manifest.parameter_path,
        manifest.baseline_multiplier,
    ) != (
        C04_PARAMETER_SEMANTIC,
        C04_PARAMETER_UNIT,
        C04_PARAMETER_PATH,
        C04_BASELINE_MULTIPLIER,
    ):
        raise C04HistoricalScorerError("C04_PARAMETER_SEMANTIC_MISMATCH")
    if (
        manifest.experiment_plan_version != EXPERIMENT_PLAN_V2_VERSION
        or manifest.experiment_plan_hash != EXPERIMENT_PLAN_V2_HASH
        or manifest.guardrail_policy_version != V2_GUARDRAIL_POLICY_VERSION
        or manifest.guardrail_policy_hash != V2_GUARDRAIL_POLICY_HASH
    ):
        raise C04HistoricalScorerError("C04_V2_EXECUTION_IDENTITY_MISMATCH")
    if (
        manifest.random_seed_policy != C04_RANDOM_SEED_POLICY
        or manifest.random_seed != C04_RANDOM_SEED
    ):
        raise C04HistoricalScorerError("C04_RANDOM_SEED_POLICY_MISMATCH")
    if manifest.planned_run_count != C04_PLANNED_RUN_COUNT:
        raise C04HistoricalScorerError("C04_PLANNED_RUN_COUNT_MISMATCH")
    if manifest.allowed_parameter_paths != C04_ALLOWED_PARAMETER_PATHS:
        raise C04HistoricalScorerError("C04_PARAMETER_ALLOWLIST_MISMATCH")
    if manifest.adaptive_search_allowed or manifest.post_validation_parameter_substitution_allowed:
        raise C04HistoricalScorerError("C04_ADAPTIVE_SEARCH_FORBIDDEN")
    if manifest.parameter_derivation_policy != C04_PARAMETER_DERIVATION_POLICY:
        raise C04HistoricalScorerError("C04_PARAMETER_DERIVATION_POLICY_MISMATCH")
    if manifest.validation_used_for_parameter_derivation or manifest.test_used:
        raise C04HistoricalScorerError("C04_FORBIDDEN_DERIVATION_INPUT")
    if (
        manifest.test_remains_sealed is not True
        or manifest.uses_weather
        or manifest.uses_production_plan
        or manifest.uses_task8
        or manifest.uses_task9
    ):
        raise C04HistoricalScorerError("C04_HISTORICAL_ONLY_INPUT_POLICY_MISMATCH")
    if _COMMIT_PATTERN.fullmatch(manifest.code_commit_binding) is None:
        raise C04HistoricalScorerError("C04_CODE_COMMIT_BINDING_INVALID")
    for identity in (
        manifest.train_dataset_identity,
        manifest.validation_dataset_identity,
        manifest.actual_label_set_identity,
        manifest.cutoff_policy_identity,
        manifest.forecast_horizon_set_identity,
        manifest.business_grain_set_identity,
        manifest.common_comparable_set_identity,
        manifest.incumbent_config_file_sha256,
        manifest.incumbent_config_hash,
        manifest.materialized_dataset_identity,
    ):
        _validate_sha256_identity(identity, "C04_MANIFEST_IDENTITY_INVALID")
    if manifest.incumbent_config_path != C04_INCUMBENT_CONFIG_PATH:
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_IDENTITY_MISMATCH")
    if (
        manifest.incumbent_config_file_sha256 != C04_INCUMBENT_CONFIG_FILE_SHA256
        or manifest.incumbent_config_hash != C04_INCUMBENT_CONFIG_HASH
    ):
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_IDENTITY_MISMATCH")
    if not isinstance(manifest.incumbent_parameter_snapshot, Mapping):
        raise C04HistoricalScorerError("C04_INCUMBENT_CONFIG_SNAPSHOT_INVALID")
    if _contains_native_float(manifest.incumbent_parameter_snapshot):
        raise C04HistoricalScorerError("C04_NATIVE_FLOAT_FORBIDDEN")
    _validate_incumbent_snapshot(manifest.incumbent_parameter_snapshot)
    if len(manifest.parameter_values) != C04_PLANNED_RUN_COUNT:
        raise C04HistoricalScorerError("C04_PARAMETER_VALUE_COUNT_INVALID")
    if len(set(manifest.parameter_values)) != C04_PLANNED_RUN_COUNT:
        raise C04HistoricalScorerError("C04_PARAMETER_VALUES_NOT_UNIQUE")
    if any(
        type(value) is not Decimal or not value.is_finite() or value <= 0
        for value in manifest.parameter_values
    ):
        raise C04HistoricalScorerError("C04_PARAMETER_VALUES_INVALID")
    if _contains_native_float(manifest.payload()):
        raise C04HistoricalScorerError("C04_NATIVE_FLOAT_FORBIDDEN")
    if len(manifest.runs) != C04_PLANNED_RUN_COUNT:
        raise C04HistoricalScorerError("C04_RUN_COUNT_INVALID")
    if tuple(run.candidate_run_ordinal for run in manifest.runs) != (1, 2, 3, 4):
        raise C04HistoricalScorerError("C04_RUN_ORDER_NOT_FROZEN")
    if len(manifest.calibration_folds) != C04_PLANNED_RUN_COUNT:
        raise C04HistoricalScorerError("C04_CALIBRATION_FOLD_COUNT_INVALID")
    for run, fold, value in zip(
        manifest.runs, manifest.calibration_folds, manifest.parameter_values, strict=True
    ):
        if run.derivation_fold_ordinal != fold.fold_ordinal or run.parameter_value != value:
            raise C04HistoricalScorerError("C04_RUN_DERIVATION_BINDING_MISMATCH")
        if fold.fit_end_date >= fold.holdout_start_date:
            raise C04HistoricalScorerError("C04_INNER_FOLD_TIME_ORDER_INVALID")
        if not isinstance(run.full_parameter_snapshot, Mapping):
            raise C04HistoricalScorerError("C04_PARAMETER_SNAPSHOT_INVALID")
        if run.full_parameter_snapshot.get(C04_PARAMETER_PATH) != value:
            raise C04HistoricalScorerError("C04_RUN_VALUE_MISMATCH")
        diff = verify_c04_parameter_allowlist(
            incumbent_snapshot=manifest.incumbent_parameter_snapshot,
            candidate_snapshot=run.full_parameter_snapshot,
        )
        if diff.native_float_present or diff.changed_paths != C04_ALLOWED_PARAMETER_PATHS:
            raise C04HistoricalScorerError("C04_UNAUTHORIZED_PARAMETER_PATH")
        expected_delta = {C04_PARAMETER_PATH: value}
        stored_delta = _decimalize(run.authorized_parameter_delta)
        if not isinstance(stored_delta, Mapping) or dict(stored_delta) != expected_delta:
            raise C04HistoricalScorerError("C04_PARAMETER_DELTA_MISMATCH")
        if run.unauthorized_parameter_diff_count != 0:
            raise C04HistoricalScorerError("C04_UNAUTHORIZED_PARAMETER_PATH")
        if run.random_seed != C04_RANDOM_SEED:
            raise C04HistoricalScorerError("C04_RANDOM_SEED_MISMATCH")
        expected_config_hash = _candidate_config_hash(run.full_parameter_snapshot)
        if run.candidate_config_hash != expected_config_hash:
            raise C04HistoricalScorerError("C04_CANDIDATE_CONFIG_HASH_MISMATCH")
        expected_run_hash = _run_parameter_hash(
            ordinal=run.candidate_run_ordinal,
            parameter_delta=expected_delta,
            full_snapshot=run.full_parameter_snapshot,
            candidate_config_hash=expected_config_hash,
            random_seed=C04_RANDOM_SEED,
        )
        if run.run_parameter_hash != expected_run_hash:
            raise C04HistoricalScorerError("C04_RUN_PARAMETER_HASH_MISMATCH")
    try:
        canonical_json_dumps(manifest.payload())
    except (TypeError, ValueError) as exc:
        raise C04HistoricalScorerError("C04_MANIFEST_NOT_CANONICAL") from exc


def build_c04_derived_config(
    manifest: C04ParameterManifest,
    candidate_run_ordinal: int,
) -> C04DerivedConfig:
    """Return immutable candidate config metadata; incumbent config is untouched."""

    validate_c04_parameter_manifest(manifest)
    run = manifest.run(candidate_run_ordinal)
    return C04DerivedConfig(
        candidate_id=C04_CANDIDATE_ID,
        candidate_run_ordinal=run.candidate_run_ordinal,
        yield_amplitude_multiplier=run.parameter_value,
        authorized_parameter_delta=deepcopy(dict(run.authorized_parameter_delta)),
        full_parameter_snapshot=deepcopy(dict(run.full_parameter_snapshot)),
        incumbent_config_hash=manifest.incumbent_config_hash,
        candidate_config_hash=run.candidate_config_hash,
        parameter_manifest_hash=manifest.manifest_hash,
    )


@dataclass(frozen=True, slots=True)
class C04DerivedConfig:
    candidate_id: str
    candidate_run_ordinal: int
    yield_amplitude_multiplier: Decimal
    authorized_parameter_delta: Mapping[str, object]
    full_parameter_snapshot: Mapping[str, object]
    incumbent_config_hash: str
    candidate_config_hash: str
    parameter_manifest_hash: str


def build_c04_gate_request(
    *,
    manifest: C04ParameterManifest,
    candidate_run_ordinal: int,
    code_commit_sha: str,
    evaluation_id: str,
    candidate_actual_run_count: int = 0,
    global_actual_evaluation_count: int = 4,
    retry_of_evaluation_id: str | None = None,
) -> CandidateExecutionGateRequest:
    """Build a V2 gate request without invoking the durable execution adapter."""

    validate_c04_parameter_manifest(manifest)
    if not code_commit_sha or not evaluation_id:
        raise C04HistoricalScorerError("C04_EXECUTION_IDENTITY_MISSING")
    run = manifest.run(candidate_run_ordinal)
    policy_payload = {
        "candidate_id": C04_CANDIDATE_ID,
        "manifest_hash": manifest.manifest_hash,
        "parameter_manifest_hash": run.parameter_manifest_hash,
        "candidate_config_hash": run.candidate_config_hash,
        "parameter_path": C04_PARAMETER_PATH,
        "parameter_value": run.parameter_value,
        "parameter_semantic": C04_PARAMETER_SEMANTIC,
        "historical_data_only": True,
        "validation_used_for_parameter_derivation": False,
        "test_used": False,
    }
    try:
        canonical_json_dumps(policy_payload)
    except (TypeError, ValueError) as exc:
        raise C04HistoricalScorerError("C04_GATE_PAYLOAD_NOT_CANONICAL") from exc
    return CandidateExecutionGateRequest(
        experiment_plan_version=EXPERIMENT_PLAN_V2_VERSION,
        experiment_plan_hash=EXPERIMENT_PLAN_V2_HASH,
        guardrail_policy_version=V2_GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=V2_GUARDRAIL_POLICY_HASH,
        candidate_id=C04_CANDIDATE_ID,
        candidate_run_ordinal=candidate_run_ordinal,
        candidate_planned_run_count=C04_PLANNED_RUN_COUNT,
        candidate_actual_run_count=candidate_actual_run_count,
        global_actual_evaluation_count=global_actual_evaluation_count,
        train_dataset_identity=manifest.train_dataset_identity,
        validation_dataset_identity=manifest.validation_dataset_identity,
        metric_contract_version=METRIC_CONTRACT_VERSION,
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash=run.parameter_manifest_hash,
        code_commit_sha=code_commit_sha,
        random_seed=run.random_seed,
        evaluation_id=evaluation_id,
        retry_of_evaluation_id=retry_of_evaluation_id,
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
        policy_payload=policy_payload,
        actual_label_set_identity=manifest.actual_label_set_identity,
        exclusion_policy_identity=manifest.common_comparable_set_identity,
        cutoff_policy_identity=manifest.cutoff_policy_identity,
        forecast_horizon_set_identity=manifest.forecast_horizon_set_identity,
        metric_contract_identity=METRIC_CONTRACT_IDENTITY,
        business_grain_set_identity=manifest.business_grain_set_identity,
        common_comparable_set_identity=manifest.common_comparable_set_identity,
        invocation_type="NORMAL_RUN",
    )


def check_c04_execution_gate(
    request: CandidateExecutionGateRequest,
) -> CandidateExecutionGateResult:
    """Expose the shared version-aware V2 gate for pure readiness tests."""

    return check_candidate_execution_gate(request)


# Compatibility aliases make the candidate-specific public surface explicit.
derive_c04_parameter_values = derive_c04_parameter_calibration
build_candidate_04_derived_config = build_c04_derived_config
build_candidate_04_manifest = build_c04_parameter_manifest
validate_candidate_04_manifest = validate_c04_parameter_manifest

__all__ = [
    "C04_ALLOWED_PARAMETER_PATHS",
    "C04_AUTHORITY_CLASS",
    "C04_BASELINE_MULTIPLIER",
    "C04_CANDIDATE_FAMILY",
    "C04_CANDIDATE_ID",
    "C04_COMPLETE_WINDOW_GUARDRAIL_BLOCKER",
    "C04_FORECAST_HORIZONS",
    "C04_FUTURE_EXECUTION_FULL_GUARDRAIL_COMPUTABLE",
    "C04_FUTURE_EXECUTION_PRIMARY_METRIC_COMPUTABLE",
    "C04_HYPOTHESIS",
    "C04_HISTORICAL_ONLY_SCORING_PATH_EXISTS",
    "C04_INCUMBENT_CONFIG_FILE_SHA256",
    "C04_INCUMBENT_CONFIG_HASH",
    "C04_INCUMBENT_CONFIG_PATH",
    "C04_INCUMBENT_FORECAST_OBSERVED_PHASE_ADJUSTMENT_MAX_DAYS",
    "C04_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS",
    "C04_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES",
    "C04_PARAMETER_DERIVATION_POLICY",
    "C04_PARAMETER_MANIFEST_VERSION",
    "C04_PARAMETER_PATH",
    "C04_PARAMETER_SEMANTIC",
    "C04_PARAMETER_UNIT",
    "C04_PARAMETER_CHANGE_CAN_CHANGE_PREDICTION",
    "C04_PARAMETER_REACHES_PREDICTION_MATH",
    "C04_PLANNED_RUN_COUNT",
    "C04_RANDOM_SEED",
    "C04_RANDOM_SEED_POLICY",
    "C04DerivedConfig",
    "C04HistoricalScorerError",
    "C04HistoricalYieldScorer",
    "C04InnerFoldCalibration",
    "C04ParameterDerivation",
    "C04ParameterDiff",
    "C04ParameterEffectProof",
    "C04ParameterManifest",
    "C04RunDefinition",
    "C04Prediction",
    "build_c04_derived_config",
    "build_c04_gate_request",
    "build_c04_historical_yield_scorer",
    "build_c04_parameter_manifest",
    "build_candidate_04_derived_config",
    "build_candidate_04_manifest",
    "check_c04_execution_gate",
    "derive_c04_parameter_calibration",
    "derive_c04_parameter_values",
    "verify_c04_parameter_allowlist",
    "validate_c04_parameter_manifest",
    "validate_candidate_04_manifest",
]
