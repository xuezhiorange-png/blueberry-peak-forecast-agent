"""Local-only S4 engineering replay for the frozen Candidate 01 contract.

This module is intentionally separate from production forecast authority.  It
consumes the already accepted SOURCE-002 TRAIN/VALIDATION partition bytes and
uses the repository's shared curve-fitting primitives to make a deterministic
engineering comparison.  It never reads TEST, writes production authority, or
claims historical PIT provenance.
"""

from __future__ import annotations

import gzip
import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from statistics import median
from typing import Any, Final, Literal

from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.maturity.config import MaturityCurveConfig
from backend.app.maturity.model import fit_shared_curve
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SOURCE_002_BYTE_COUNT,
    SOURCE_002_OBJECT_SHA256,
)
from backend.app.s2_materialized_dataset.lane_a.source_artifact import (
    verify_source_002_frozen_object_identity,
)
from backend.app.s2_materialized_dataset.lane_d.canonical import parse_partition_bytes
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
    OFFICIAL_VALIDATION_ROW_COUNT,
)
from backend.app.s4_experiment import (
    V2_FORECAST_HORIZONS,
    BreakdownAxisEvidence,
    BreakdownCellEvidence,
    CoverageQualityEvidence,
    MetricObservation,
    evaluate_candidate_guardrails,
)

DECIMAL_QUANTUM = Decimal("0.000001")
SUSTAINED_7DAY_WINDOW_DAYS = 7
SUSTAINED_7DAY_WINDOW_POLICY = "REJECT_INCOMPLETE_WINDOW"
MISSING_DAY_ZERO_FILL = False
SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256 = (
    "f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785"
)
SOURCE_002_TRAIN_BYTE_COUNT = 9_087_071
SOURCE_002_VALIDATION_BYTE_COUNT = 4_484_905
LOCAL_ENGINEERING_REPLAY_MODEL_ID = "V0_2_CURRENT_MODEL"
LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS = "LOCAL_ENGINEERING_REPLAY"
LOCAL_CUTOFF_POLICY_IDENTITY = "LOCAL_ENGINEERING_TRAIN_BEFORE_VALIDATION_V1"
LOCAL_FORECAST_HORIZON_POLICY_IDENTITY = "LOCAL_ENGINEERING_DAILY_VALIDATION_HORIZON_V1"
LOCAL_INTERVAL_POLICY_IDENTITY = "LOCAL_ENGINEERING_UNCALIBRATED_INTERVAL_PROXY_V1"
FROZEN_FORECAST_HORIZONS: Final[frozenset[int]] = frozenset({7, 14, 21})
COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE = "COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE"
FORECAST_HORIZON_NOT_IN_FROZEN_SET = "FORECAST_HORIZON_NOT_IN_FROZEN_SET"
WAPE_ACTUAL_DENOMINATOR_ZERO = "WAPE_ACTUAL_DENOMINATOR_ZERO"
LOCAL_FARM_PEAK_FORECAST_QUANTILE = "P50"
REQUIRED_BREAKDOWN_AXES = (
    "forecast_horizon_days",
    "farm_business_key",
    "subfarm_business_key",
    "variety_business_key",
    "season_business_key",
    "model_identity",
)
MetricStatus = Literal["COMPUTED", "NOT_COMPUTABLE"]


class LocalEngineeringContractError(ValueError):
    """Raised for a deterministic local engineering contract violation."""


@dataclass(frozen=True, slots=True)
class FrozenSourceObject:
    path: Path
    byte_count: int
    sha256: str
    row_count: int


@dataclass(frozen=True, slots=True)
class CompleteWindowAuthority:
    """Explicit authority for metrics requiring a complete daily window."""

    daily_rowset_authority: bool
    daily_rowset_identity: str | None
    daily_rowset_completeness: bool
    evaluation_window_start: date | None
    evaluation_window_end: date | None
    evaluation_window_days: int | None
    forecast_cutoff_identity: str | None
    forecast_horizon_identity: str | None
    no_missing_days: bool

    def is_valid_for(self, predictions: tuple[LocalPrediction, ...]) -> bool:
        if not (
            self.daily_rowset_authority
            and self.daily_rowset_completeness
            and self.no_missing_days
            and self.daily_rowset_identity
            and self.forecast_cutoff_identity
            and self.forecast_horizon_identity
        ):
            return False
        if (
            self.evaluation_window_start is None
            or self.evaluation_window_end is None
            or self.evaluation_window_days is None
            or self.evaluation_window_days <= 0
            or self.evaluation_window_end < self.evaluation_window_start
        ):
            return False
        expected_days = (self.evaluation_window_end - self.evaluation_window_start).days + 1
        if expected_days != self.evaluation_window_days:
            return False
        dates = {item.harvest_business_date for item in predictions}
        expected_date_set = {
            self.evaluation_window_start + timedelta(days=offset)
            for offset in range(self.evaluation_window_days)
        }
        if dates != expected_date_set:
            return False
        cutoff_values = {item.forecast_cutoff_at for item in predictions}
        if not cutoff_values or None in cutoff_values:
            return False
        try:
            horizons = {item.horizon_days for item in predictions}
        except LocalEngineeringContractError:
            return False
        return horizons.issubset(FROZEN_FORECAST_HORIZONS)


@dataclass(frozen=True, slots=True)
class FrozenEngineeringDataset:
    train_rows: tuple[MaterializableRow, ...]
    validation_rows: tuple[MaterializableRow, ...]
    train_content_sha256: str
    validation_content_sha256: str
    materialized_dataset_identity_sha256: str
    test_row_count: int
    forecast_cutoff_at: date | None = None
    complete_window_authority: CompleteWindowAuthority | None = None


@dataclass(frozen=True, slots=True)
class LocalPrediction:
    season: str
    farm: str
    subfarm: str
    variety: str
    harvest_business_date: date
    forecast_cutoff_at: date | None
    actual_kg: Decimal
    p50_kg: Decimal
    p80_kg: Decimal
    p90_kg: Decimal
    model_identity: str = LOCAL_ENGINEERING_REPLAY_MODEL_ID

    @property
    def horizon_days(self) -> int:
        if self.forecast_cutoff_at is None:
            raise LocalEngineeringContractError("FORECAST_HORIZON_AUTHORITY_UNAVAILABLE")
        horizon_days = (self.harvest_business_date - self.forecast_cutoff_at).days
        if horizon_days not in FROZEN_FORECAST_HORIZONS:
            raise LocalEngineeringContractError(FORECAST_HORIZON_NOT_IN_FROZEN_SET)
        return horizon_days

    @property
    def business_key(self) -> tuple[str, str, str, str, date]:
        return (
            self.season,
            self.farm,
            self.subfarm,
            self.variety,
            self.harvest_business_date,
        )


@dataclass(frozen=True, slots=True)
class LocalMetricSet:
    daily_wape: Decimal | None
    daily_wape_metric_status: MetricStatus
    daily_wape_metric_reason_code: str
    daily_mae: Decimal
    cumulative_absolute_error_kg: Decimal | None
    cumulative_metric_status: MetricStatus
    cumulative_metric_reason_code: str
    single_day_peak_quantity_absolute_error_kg_q: Decimal | None
    single_day_peak_metric_status: MetricStatus
    single_day_peak_metric_reason_code: str
    sustained_7day_quantity_absolute_error_kg_q: Decimal | None
    sustained_7day_metric_status: MetricStatus
    sustained_7day_metric_reason_code: str
    p80_coverage: Decimal
    p90_coverage: Decimal
    comparable_row_count: int
    breakdown_metrics: Mapping[str, Mapping[str, Mapping[str, str | int | None]]]

    def payload(self) -> dict[str, Any]:
        return {
            "daily_wape": (_decimal_text(self.daily_wape) if self.daily_wape is not None else None),
            "daily_wape_status": self.daily_wape_metric_status,
            "daily_wape_reason_code": self.daily_wape_metric_reason_code,
            "daily_wape_metric_status": self.daily_wape_metric_status,
            "daily_wape_metric_reason_code": self.daily_wape_metric_reason_code,
            "daily_mae": _decimal_text(self.daily_mae),
            "cumulative_absolute_error_kg": (
                _decimal_text(self.cumulative_absolute_error_kg)
                if self.cumulative_absolute_error_kg is not None
                else None
            ),
            "cumulative_status": self.cumulative_metric_status,
            "cumulative_reason_code": self.cumulative_metric_reason_code,
            "cumulative_metric_status": self.cumulative_metric_status,
            "cumulative_metric_reason_code": self.cumulative_metric_reason_code,
            "single_day_peak_quantity_absolute_error_kg_q": _decimal_text(
                self.single_day_peak_quantity_absolute_error_kg_q
            )
            if self.single_day_peak_quantity_absolute_error_kg_q is not None
            else None,
            "single_day_peak_status": self.single_day_peak_metric_status,
            "single_day_peak_reason_code": self.single_day_peak_metric_reason_code,
            "single_day_peak_metric_status": self.single_day_peak_metric_status,
            "single_day_peak_metric_reason_code": self.single_day_peak_metric_reason_code,
            "sustained_7day_quantity_absolute_error_kg_q": (
                _decimal_text(self.sustained_7day_quantity_absolute_error_kg_q)
                if self.sustained_7day_quantity_absolute_error_kg_q is not None
                else None
            ),
            "sustained_7day_metric_status": self.sustained_7day_metric_status,
            "sustained_7day_metric_reason_code": self.sustained_7day_metric_reason_code,
            "P80_COVERAGE": _decimal_text(self.p80_coverage),
            "P90_COVERAGE": _decimal_text(self.p90_coverage),
            "comparable_row_count": self.comparable_row_count,
            "breakdown_metrics": self.breakdown_metrics,
        }


@dataclass(frozen=True, slots=True)
class LocalReplayResult:
    model_id: str
    authority_class: str
    config_hash: str
    prediction_identity_sha256: str
    actual_label_set_identity_sha256: str
    business_grain_set_identity_sha256: str
    metrics: LocalMetricSet
    predictions: tuple[LocalPrediction, ...]
    train_dataset_sha256: str
    validation_dataset_sha256: str

    def payload(self, *, include_predictions: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model_id": self.model_id,
            "authority_class": self.authority_class,
            "config_hash": self.config_hash,
            "prediction_identity_sha256": self.prediction_identity_sha256,
            "actual_label_set_identity_sha256": self.actual_label_set_identity_sha256,
            "business_grain_set_identity_sha256": self.business_grain_set_identity_sha256,
            "metrics": self.metrics.payload(),
            "train_dataset_sha256": self.train_dataset_sha256,
            "validation_dataset_sha256": self.validation_dataset_sha256,
        }
        if include_predictions:
            payload["predictions"] = [_prediction_payload(item) for item in self.predictions]
        return payload


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN), "f")


def _q(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise LocalEngineeringContractError("local engineering values must be finite Decimal")
    return value.quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)


def _sha(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _prediction_payload(item: LocalPrediction) -> dict[str, Any]:
    return {
        "season": item.season,
        "farm": item.farm,
        "subfarm": item.subfarm,
        "variety": item.variety,
        "harvest_business_date": item.harvest_business_date,
        "forecast_cutoff_at": item.forecast_cutoff_at,
        "actual_kg": _decimal_text(item.actual_kg),
        "p50_kg": _decimal_text(item.p50_kg),
        "p80_kg": _decimal_text(item.p80_kg),
        "p90_kg": _decimal_text(item.p90_kg),
        "model_identity": item.model_identity,
    }


def verify_frozen_source_object(path: Path) -> FrozenSourceObject:
    if not path.is_file():
        record, _, resolved = verify_source_002_frozen_object_identity(
            search_roots=(path.parent,),
        )
        if resolved is None or record.source_object_sha256 != SOURCE_002_OBJECT_SHA256:
            raise LocalEngineeringContractError("SOURCE_002_RAW_OBJECT_UNAVAILABLE")
        path = resolved
    byte_count = path.stat().st_size
    if byte_count != SOURCE_002_BYTE_COUNT:
        raise LocalEngineeringContractError("SOURCE_002_RAW_OBJECT_BYTE_COUNT_MISMATCH")
    artifact_bytes = path.read_bytes()
    sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    if sha256 != SOURCE_002_OBJECT_SHA256:
        raise LocalEngineeringContractError("SOURCE_002_RAW_OBJECT_SHA256_MISMATCH")
    record, _, _ = verify_source_002_frozen_object_identity(search_roots=(path.parent,))
    if record.status.value != "PASS" or record.declared_source_row_count != 233_171:
        raise LocalEngineeringContractError("SOURCE_002_RAW_OBJECT_SCHEMA_OR_ROW_COUNT_MISMATCH")
    return FrozenSourceObject(
        path=path,
        byte_count=byte_count,
        sha256=sha256,
        row_count=record.declared_source_row_count,
    )


def _load_partition(
    path: Path, *, expected_sha256: str, expected_rows: int
) -> tuple[MaterializableRow, ...]:
    content = gzip.open(path, "rb").read()
    observed_sha256 = hashlib.sha256(content).hexdigest()
    if observed_sha256 != expected_sha256:
        raise LocalEngineeringContractError(f"OFFICIAL_PARTITION_HASH_MISMATCH:{path.name}")
    rows = parse_partition_bytes(content)
    if len(rows) != expected_rows:
        raise LocalEngineeringContractError(f"OFFICIAL_PARTITION_ROW_COUNT_MISMATCH:{path.name}")
    return rows


def load_frozen_engineering_dataset(repo_root: Path) -> FrozenEngineeringDataset:
    fixture_root = repo_root / "backend/tests/fixtures/s3_a2_official_s2_partitions"
    train_path = fixture_root / "train.content.gz"
    validation_path = fixture_root / "validation.content.gz"
    train_rows = _load_partition(
        train_path,
        expected_sha256=OFFICIAL_TRAIN_CONTENT_SHA256,
        expected_rows=OFFICIAL_TRAIN_ROW_COUNT,
    )
    validation_rows = _load_partition(
        validation_path,
        expected_sha256=OFFICIAL_VALIDATION_CONTENT_SHA256,
        expected_rows=OFFICIAL_VALIDATION_ROW_COUNT,
    )
    return FrozenEngineeringDataset(
        train_rows=train_rows,
        validation_rows=validation_rows,
        train_content_sha256=OFFICIAL_TRAIN_CONTENT_SHA256,
        validation_content_sha256=OFFICIAL_VALIDATION_CONTENT_SHA256,
        materialized_dataset_identity_sha256=SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256,
        test_row_count=0,
    )


def _row_key(row: MaterializableRow) -> tuple[str, str, str, str, date]:
    return (row.season, row.farm, row.subfarm, row.variety, row.harvest_business_date)


def _actual_label_set_hash(rows: Iterable[MaterializableRow]) -> str:
    return _sha(
        [
            {
                "season": row.season,
                "farm": row.farm,
                "subfarm": row.subfarm,
                "variety": row.variety,
                "harvest_business_date": row.harvest_business_date,
                "actual_kg": row.actual_harvest_quantity_kg,
            }
            for row in sorted(rows, key=_row_key)
        ]
    )


def _business_grain_set_hash(rows: Iterable[MaterializableRow]) -> str:
    return _sha(
        [
            {
                "season": row.season,
                "farm": row.farm,
                "subfarm": row.subfarm,
                "variety": row.variety,
                "harvest_business_date": row.harvest_business_date,
            }
            for row in sorted(rows, key=_row_key)
        ]
    )


def _fit_curve(
    samples: list[tuple[int, Decimal]],
    *,
    config: MaturityCurveConfig,
    support_days: tuple[int, ...],
) -> tuple[Decimal, ...] | None:
    by_day: dict[int, list[Decimal]] = defaultdict(list)
    for relative_day, value in samples:
        by_day[relative_day].append(value)
    if len(by_day) < max(config.rules.curve.spline_degree + 1, 4):
        return None
    total = sum((value for _, value in samples), Decimal("0"))
    if total <= 0:
        return None
    relative_days = tuple(sorted(by_day))
    shares = tuple(
        (sum(by_day[day], Decimal("0")) / total).quantize(DECIMAL_QUANTUM) for day in relative_days
    )
    weights = tuple(Decimal(len(by_day[day])).quantize(DECIMAL_QUANTUM) for day in relative_days)
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


def _curve_support(
    train_rows: tuple[MaterializableRow, ...], validation_rows: tuple[MaterializableRow, ...]
) -> tuple[int, ...]:
    anchors: dict[tuple[str, str, str], date] = {}
    for row in train_rows:
        key = (row.farm, row.subfarm, row.variety)
        anchors[key] = min(anchors.get(key, row.harvest_business_date), row.harvest_business_date)
    relative_max = 90
    for row in validation_rows:
        key = (row.farm, row.subfarm, row.variety)
        anchor = anchors.get(key)
        if anchor is not None:
            relative_max = max(relative_max, (row.harvest_business_date - anchor).days)
    return tuple(range(-30, relative_max + 1))


def _quantile_multiplier(config: MaturityCurveConfig, quantile: str) -> Decimal:
    if quantile == "p80":
        return Decimal("1") + (config.rules.intervals.p80_quantile / Decimal("2"))
    return Decimal("1") + config.rules.intervals.p90_quantile


def _build_predictions(
    *,
    train_rows: tuple[MaterializableRow, ...],
    validation_rows: tuple[MaterializableRow, ...],
    config: MaturityCurveConfig,
    forecast_cutoff_at: date | None,
) -> tuple[LocalPrediction, ...]:
    if forecast_cutoff_at is None:
        raise LocalEngineeringContractError("FORECAST_HORIZON_AUTHORITY_UNAVAILABLE")
    support_days = _curve_support(train_rows, validation_rows)
    by_group: dict[tuple[str, str, str], list[MaterializableRow]] = defaultdict(list)
    by_variety: dict[str, list[MaterializableRow]] = defaultdict(list)
    for row in train_rows:
        by_group[(row.farm, row.subfarm, row.variety)].append(row)
        by_variety[row.variety].append(row)

    group_anchors = {
        key: min(row.harvest_business_date for row in rows) for key, rows in by_group.items()
    }
    group_totals = {
        key: sum((row.actual_harvest_quantity_kg for row in rows), Decimal("0"))
        for key, rows in by_group.items()
    }
    variety_totals: dict[str, list[Decimal]] = defaultdict(list)
    for key, total in group_totals.items():
        variety_totals[key[2]].append(total)

    group_curves: dict[tuple[str, str, str], tuple[Decimal, ...] | None] = {}
    variety_curves: dict[str, tuple[Decimal, ...] | None] = {}
    for key, rows in by_group.items():
        anchor = group_anchors[key]
        samples = [
            ((row.harvest_business_date - anchor).days, row.actual_harvest_quantity_kg)
            for row in rows
        ]
        group_curves[key] = _fit_curve(samples, config=config, support_days=support_days)
    for variety, _rows in by_variety.items():
        grouped_samples = _variety_curve_samples(
            variety=variety,
            by_group=by_group,
            group_anchors=group_anchors,
            group_totals=group_totals,
        )
        variety_curves[variety] = _fit_curve(
            list(grouped_samples), config=config, support_days=support_days
        )
    fallback_total = {
        variety: _q(Decimal(str(median(values))))
        for variety, values in variety_totals.items()
        if values
    }

    predictions: list[LocalPrediction] = []
    p80_multiplier = _quantile_multiplier(config, "p80")
    p90_multiplier = _quantile_multiplier(config, "p90")
    for row in sorted(validation_rows, key=_row_key):
        key = (row.farm, row.subfarm, row.variety)
        if key in group_anchors:
            anchor = group_anchors[key]
        elif row.variety in by_variety:
            anchor = min(item.harvest_business_date for item in by_variety[row.variety])
        else:
            raise LocalEngineeringContractError("LOCAL_VALIDATION_TRAIN_SUPPORT_UNAVAILABLE")
        relative_day = (row.harvest_business_date - anchor).days
        curve = group_curves.get(key) or variety_curves.get(row.variety)
        prediction_total: Decimal | None = group_totals.get(key, fallback_total.get(row.variety))
        if curve is None or prediction_total is None or prediction_total <= 0:
            raise LocalEngineeringContractError("LOCAL_VALIDATION_TRAIN_SUPPORT_UNAVAILABLE")
        if relative_day < support_days[0] or relative_day > support_days[-1]:
            raise LocalEngineeringContractError("LOCAL_VALIDATION_TRAIN_SUPPORT_UNAVAILABLE")
        p50 = _q(prediction_total * curve[relative_day - support_days[0]])
        p80 = _q(p50 * p80_multiplier)
        p90 = _q(p50 * p90_multiplier)
        prediction = LocalPrediction(
            season=row.season,
            farm=row.farm,
            subfarm=row.subfarm,
            variety=row.variety,
            harvest_business_date=row.harvest_business_date,
            forecast_cutoff_at=forecast_cutoff_at,
            actual_kg=_q(row.actual_harvest_quantity_kg),
            p50_kg=p50,
            p80_kg=max(p80, p50),
            p90_kg=max(p90, p80, p50),
        )
        _ = prediction.horizon_days
        predictions.append(prediction)
    return tuple(predictions)


def _daily_totals(predictions: Iterable[LocalPrediction]) -> dict[date, tuple[Decimal, Decimal]]:
    totals: dict[date, list[Decimal]] = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    for item in predictions:
        totals[item.harvest_business_date][0] += item.actual_kg
        totals[item.harvest_business_date][1] += item.p50_kg
    return {day: (values[0], values[1]) for day, values in totals.items()}


def _variety_curve_samples(
    *,
    variety: str,
    by_group: Mapping[tuple[str, str, str], list[MaterializableRow]],
    group_anchors: Mapping[tuple[str, str, str], date],
    group_totals: Mapping[tuple[str, str, str], Decimal],
) -> tuple[tuple[int, Decimal], ...]:
    """Build deterministic per-group-normalized samples for one variety."""

    grouped_samples: list[tuple[int, Decimal]] = []
    for key in sorted(by_group):
        if key[2] != variety:
            continue
        group_total = group_totals[key]
        if group_total <= 0:
            continue
        anchor = group_anchors[key]
        grouped_samples.extend(
            (
                (row.harvest_business_date - anchor).days,
                row.actual_harvest_quantity_kg / group_total,
            )
            for row in sorted(by_group[key], key=_row_key)
        )
    return tuple(sorted(grouped_samples, key=lambda sample: (sample[0], sample[1])))


FarmPeakKey = tuple[str, str, str, date, date, str, str]
FarmSeriesKey = tuple[str, str, str, date, str, str]


def _farm_variety_daily_series(
    predictions: Iterable[LocalPrediction],
) -> dict[FarmSeriesKey, dict[date, tuple[Decimal, Decimal]]]:
    """Sum subfarms while preserving each canonical farm-variety series grain."""

    totals: dict[FarmSeriesKey, dict[date, list[Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: [Decimal("0"), Decimal("0")])
    )
    for item in predictions:
        if item.forecast_cutoff_at is None:
            raise LocalEngineeringContractError("FORECAST_HORIZON_AUTHORITY_UNAVAILABLE")
        key: FarmSeriesKey = (
            item.season,
            item.farm,
            item.variety,
            item.forecast_cutoff_at,
            item.model_identity,
            LOCAL_FARM_PEAK_FORECAST_QUANTILE,
        )
        totals[key][item.harvest_business_date][0] += item.actual_kg
        totals[key][item.harvest_business_date][1] += item.p50_kg
    return {
        key: {target_date: (values[0], values[1]) for target_date, values in daily.items()}
        for key, daily in totals.items()
    }


def _farm_daily_totals(
    predictions: Iterable[LocalPrediction],
) -> dict[FarmPeakKey, tuple[Decimal, Decimal]]:
    """Sum subfarms while retaining the frozen farm/variety forecast grain."""

    totals: dict[FarmPeakKey, tuple[Decimal, Decimal]] = {}
    for series_key, daily in _farm_variety_daily_series(predictions).items():
        season, farm, variety, cutoff, model_identity, quantile = series_key
        for target_date, values in daily.items():
            totals[(season, farm, variety, target_date, cutoff, model_identity, quantile)] = values
    return totals


def _farm_peak_daily_totals(
    predictions: Iterable[LocalPrediction],
) -> dict[date, tuple[Decimal, Decimal]]:
    """Return peak candidates per date without summing different varieties."""

    candidates: dict[date, list[Decimal]] = {}
    for key, (actual, predicted) in _farm_daily_totals(predictions).items():
        target_date = key[3]
        current = candidates.setdefault(target_date, [Decimal("0"), Decimal("0")])
        current[0] = max(current[0], actual)
        current[1] = max(current[1], predicted)
    return {day: (values[0], values[1]) for day, values in candidates.items()}


def _earliest_daily_peak(
    daily: Mapping[date, tuple[Decimal, Decimal]], index: int
) -> tuple[Decimal, date | None]:
    if not daily:
        return Decimal("0"), None
    peak_value = Decimal("0")
    peak_date: date | None = None
    for current_date in sorted(daily):
        current_value = daily[current_date][index]
        if peak_date is None or current_value > peak_value:
            peak_value = current_value
            peak_date = current_date
    return peak_value, peak_date


def _single_day_peak_error(
    predictions: tuple[LocalPrediction, ...],
) -> tuple[Decimal, date | None, Decimal, date | None]:
    daily = _farm_peak_daily_totals(predictions)
    actual_peak, actual_peak_date = _earliest_daily_peak(daily, 0)
    predicted_peak, predicted_peak_date = _earliest_daily_peak(daily, 1)
    return (
        _q(abs(predicted_peak - actual_peak)),
        actual_peak_date,
        predicted_peak,
        predicted_peak_date,
    )


def _complete_7day_windows(
    daily: Mapping[date, tuple[Decimal, Decimal]],
) -> tuple[tuple[date, tuple[Decimal, Decimal]], ...]:
    if not daily:
        return ()
    start = min(daily)
    last_start = max(daily) - timedelta(days=SUSTAINED_7DAY_WINDOW_DAYS - 1)
    windows: list[tuple[date, tuple[Decimal, Decimal]]] = []
    window_start = start
    while window_start <= last_start:
        window_days = tuple(
            window_start + timedelta(days=offset) for offset in range(SUSTAINED_7DAY_WINDOW_DAYS)
        )
        if all(day in daily for day in window_days):
            windows.append(
                (
                    window_start,
                    (
                        sum((daily[day][0] for day in window_days), Decimal("0")),
                        sum((daily[day][1] for day in window_days), Decimal("0")),
                    ),
                )
            )
        window_start += timedelta(days=1)
    return tuple(windows)


def _rolling_peak_error(predictions: tuple[LocalPrediction, ...]) -> Decimal | None:
    windows = [
        window
        for daily in _farm_variety_daily_series(predictions).values()
        for window in _complete_7day_windows(daily)
    ]
    if not windows:
        return None
    actual_peak = Decimal("0")
    predicted_peak = Decimal("0")
    for _, (actual, predicted) in windows:
        actual_peak = max(actual_peak, actual)
        predicted_peak = max(predicted_peak, predicted)
    return _q(abs(predicted_peak - actual_peak))


def _complete_window_reason(
    predictions: tuple[LocalPrediction, ...],
    authority: CompleteWindowAuthority | None,
) -> str | None:
    if authority is None or not authority.is_valid_for(predictions):
        return COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
    return None


def _metric_payload(
    predictions: tuple[LocalPrediction, ...],
    *,
    complete_window_authority: CompleteWindowAuthority | None = None,
) -> dict[str, str | int | None]:
    if not predictions:
        raise LocalEngineeringContractError("LOCAL_VALIDATION_EMPTY")
    absolute_errors = [abs(item.p50_kg - item.actual_kg) for item in predictions]
    actual_total = sum((item.actual_kg for item in predictions), Decimal("0"))
    if actual_total == 0:
        daily_wape: Decimal | None = None
        daily_wape_status: MetricStatus = "NOT_COMPUTABLE"
        daily_wape_reason_code = WAPE_ACTUAL_DENOMINATOR_ZERO
    else:
        daily_wape = _q(sum(absolute_errors, Decimal("0")) / actual_total)
        daily_wape_status = "COMPUTED"
        daily_wape_reason_code = "NONE"
    daily_mae = _q(sum(absolute_errors, Decimal("0")) / Decimal(len(predictions)))
    complete_reason = _complete_window_reason(predictions, complete_window_authority)
    if complete_reason is None:
        cumulative_error: Decimal | None = _q(
            abs(
                sum((item.p50_kg for item in predictions), Decimal("0"))
                - sum((item.actual_kg for item in predictions), Decimal("0"))
            )
        )
        cumulative_status: MetricStatus = "COMPUTED"
        cumulative_reason_code = "NONE"
        peak_error: Decimal | None = _single_day_peak_error(predictions)[0]
        peak_status: MetricStatus = "COMPUTED"
        peak_reason_code = "NONE"
        sustained_error = _rolling_peak_error(predictions)
        sustained_status: MetricStatus = (
            "COMPUTED" if sustained_error is not None else "NOT_COMPUTABLE"
        )
        sustained_reason_code = "NONE" if sustained_error is not None else "NO_COMPLETE_7DAY_WINDOW"
    else:
        cumulative_error = None
        cumulative_status = "NOT_COMPUTABLE"
        cumulative_reason_code = complete_reason
        peak_error = None
        peak_status = "NOT_COMPUTABLE"
        peak_reason_code = complete_reason
        sustained_error = None
        sustained_status = "NOT_COMPUTABLE"
        sustained_reason_code = complete_reason
    p80_coverage = _q(
        Decimal(sum(item.actual_kg <= item.p80_kg for item in predictions))
        / Decimal(len(predictions))
    )
    p90_coverage = _q(
        Decimal(sum(item.actual_kg <= item.p90_kg for item in predictions))
        / Decimal(len(predictions))
    )
    return {
        "daily_wape": _decimal_text(daily_wape) if daily_wape is not None else None,
        "daily_wape_status": daily_wape_status,
        "daily_wape_reason_code": daily_wape_reason_code,
        "daily_wape_metric_status": daily_wape_status,
        "daily_wape_metric_reason_code": daily_wape_reason_code,
        "daily_mae": _decimal_text(daily_mae),
        "cumulative_absolute_error_kg": (
            _decimal_text(cumulative_error) if cumulative_error is not None else None
        ),
        "cumulative_metric_status": cumulative_status,
        "cumulative_metric_reason_code": cumulative_reason_code,
        "cumulative_status": cumulative_status,
        "cumulative_reason_code": cumulative_reason_code,
        "single_day_peak_quantity_absolute_error_kg_q": (
            _decimal_text(peak_error) if peak_error is not None else None
        ),
        "single_day_peak_metric_status": peak_status,
        "single_day_peak_metric_reason_code": peak_reason_code,
        "single_day_peak_status": peak_status,
        "single_day_peak_reason_code": peak_reason_code,
        "sustained_7day_quantity_absolute_error_kg_q": (
            _decimal_text(sustained_error) if sustained_error is not None else None
        ),
        "sustained_7day_metric_status": sustained_status,
        "sustained_7day_metric_reason_code": sustained_reason_code,
        "P80_COVERAGE": _decimal_text(p80_coverage),
        "P90_COVERAGE": _decimal_text(p90_coverage),
        "comparable_row_count": len(predictions),
    }


def _breakdown_metrics(
    predictions: tuple[LocalPrediction, ...],
    *,
    complete_window_authority: CompleteWindowAuthority | None = None,
) -> dict[str, dict[str, dict[str, str | int | None]]]:
    result: dict[str, dict[str, dict[str, str | int | None]]] = {}
    for axis in REQUIRED_BREAKDOWN_AXES:
        buckets: dict[str, list[LocalPrediction]] = defaultdict(list)
        for item in predictions:
            if axis == "forecast_horizon_days":
                key = str(item.horizon_days)
            elif axis == "farm_business_key":
                key = item.farm
            elif axis == "subfarm_business_key":
                key = item.subfarm
            elif axis == "variety_business_key":
                key = item.variety
            elif axis == "season_business_key":
                key = item.season
            else:
                key = LOCAL_ENGINEERING_REPLAY_MODEL_ID
            buckets[key].append(item)
        result[axis] = {
            key: _metric_payload(tuple(rows), complete_window_authority=complete_window_authority)
            for key, rows in sorted(buckets.items())
        }
    return result


def compute_metrics(
    predictions: tuple[LocalPrediction, ...],
    *,
    complete_window_authority: CompleteWindowAuthority | None = None,
) -> LocalMetricSet:
    values = _metric_payload(predictions, complete_window_authority=complete_window_authority)
    daily_wape_status = _payload_status(values, "daily_wape_metric_status")
    cumulative_status = _payload_status(values, "cumulative_metric_status")
    peak_status = _payload_status(values, "single_day_peak_metric_status")
    sustained_value = values["sustained_7day_quantity_absolute_error_kg_q"]
    normalized_sustained_status = _payload_status(values, "sustained_7day_metric_status")
    return LocalMetricSet(
        daily_wape=_payload_optional_decimal(values, "daily_wape"),
        daily_wape_metric_status=daily_wape_status,
        daily_wape_metric_reason_code=str(values["daily_wape_metric_reason_code"]),
        daily_mae=_payload_decimal(values, "daily_mae"),
        cumulative_absolute_error_kg=_payload_optional_decimal(
            values, "cumulative_absolute_error_kg"
        ),
        cumulative_metric_status=cumulative_status,
        cumulative_metric_reason_code=str(values["cumulative_metric_reason_code"]),
        single_day_peak_quantity_absolute_error_kg_q=_payload_optional_decimal(
            values, "single_day_peak_quantity_absolute_error_kg_q"
        ),
        single_day_peak_metric_status=peak_status,
        single_day_peak_metric_reason_code=str(values["single_day_peak_metric_reason_code"]),
        sustained_7day_quantity_absolute_error_kg_q=(
            Decimal(sustained_value) if isinstance(sustained_value, str) else None
        ),
        sustained_7day_metric_status=normalized_sustained_status,
        sustained_7day_metric_reason_code=str(values["sustained_7day_metric_reason_code"]),
        p80_coverage=_payload_decimal(values, "P80_COVERAGE"),
        p90_coverage=_payload_decimal(values, "P90_COVERAGE"),
        comparable_row_count=_payload_int(values, "comparable_row_count"),
        breakdown_metrics=_breakdown_metrics(
            predictions, complete_window_authority=complete_window_authority
        ),
    )


def _payload_decimal(values: Mapping[str, str | int | None], key: str) -> Decimal:
    value = values[key]
    if not isinstance(value, str):
        raise LocalEngineeringContractError(f"METRIC_PAYLOAD_DECIMAL_MISSING:{key}")
    return Decimal(value)


def _payload_optional_decimal(values: Mapping[str, str | int | None], key: str) -> Decimal | None:
    value = values[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise LocalEngineeringContractError(f"METRIC_PAYLOAD_DECIMAL_INVALID:{key}")
    return Decimal(value)


def _payload_status(values: Mapping[str, str | int | None], key: str) -> MetricStatus:
    value = values[key]
    if value == "COMPUTED":
        return "COMPUTED"
    if value == "NOT_COMPUTABLE":
        return "NOT_COMPUTABLE"
    raise LocalEngineeringContractError(f"METRIC_PAYLOAD_STATUS_INVALID:{key}")


def _payload_int(values: Mapping[str, str | int | None], key: str) -> int:
    value = values[key]
    if not isinstance(value, int):
        raise LocalEngineeringContractError(f"METRIC_PAYLOAD_INTEGER_MISSING:{key}")
    return value


def _breakdown_comparable_rows(cell: Mapping[str, str | int | None]) -> int:
    return _payload_int(cell, "comparable_row_count")


def _metric_observation(
    metric_name: str,
    value: Decimal | None,
    status: MetricStatus,
) -> MetricObservation:
    if status != "COMPUTED" or value is None:
        return MetricObservation.not_computable(metric_name)
    return MetricObservation.computed(metric_name, value)


def run_local_replay(
    *,
    dataset: FrozenEngineeringDataset,
    config: MaturityCurveConfig,
) -> LocalReplayResult:
    if dataset.forecast_cutoff_at is None:
        raise LocalEngineeringContractError("FORECAST_HORIZON_AUTHORITY_UNAVAILABLE")
    predictions = _build_predictions(
        train_rows=dataset.train_rows,
        validation_rows=dataset.validation_rows,
        config=config,
        forecast_cutoff_at=dataset.forecast_cutoff_at,
    )
    if len(predictions) != len(dataset.validation_rows):
        raise LocalEngineeringContractError("LOCAL_VALIDATION_PREDICTION_ROW_COUNT_MISMATCH")
    prediction_identity = _sha(
        {
            "authority_class": LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS,
            "model_id": LOCAL_ENGINEERING_REPLAY_MODEL_ID,
            "config_hash": config.config_hash,
            "predictions": [_prediction_payload(item) for item in predictions],
        }
    )
    return LocalReplayResult(
        model_id=LOCAL_ENGINEERING_REPLAY_MODEL_ID,
        authority_class=LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS,
        config_hash=config.config_hash,
        prediction_identity_sha256=prediction_identity,
        actual_label_set_identity_sha256=_actual_label_set_hash(dataset.validation_rows),
        business_grain_set_identity_sha256=_business_grain_set_hash(dataset.validation_rows),
        metrics=compute_metrics(
            predictions, complete_window_authority=dataset.complete_window_authority
        ),
        predictions=predictions,
        train_dataset_sha256=dataset.train_content_sha256,
        validation_dataset_sha256=dataset.validation_content_sha256,
    )


def guardrail_payload(
    *,
    candidate: LocalReplayResult,
    incumbent: LocalReplayResult,
) -> dict[str, Any]:
    candidate_metrics = candidate.metrics
    incumbent_metrics = incumbent.metrics
    axes = tuple(
        BreakdownAxisEvidence(
            axis_name=axis,
            cells=tuple(
                BreakdownCellEvidence(
                    cell_id=f"{axis}:{cell_id}",
                    comparable_rows=_breakdown_comparable_rows(cell),
                )
                for cell_id, cell in candidate_metrics.breakdown_metrics[axis].items()
            ),
        )
        for axis in REQUIRED_BREAKDOWN_AXES
    )
    coverage = CoverageQualityEvidence(
        coverage_ratio=MetricObservation.computed("coverage_ratio", Decimal("1.000000")),
        valid_included_canonical_group_coverage=MetricObservation.computed(
            "valid_included_canonical_group_coverage", Decimal("1.000000")
        ),
        missing_data_proportion=MetricObservation.computed(
            "missing_data_proportion", Decimal("0.000000")
        ),
        breakdown_axes=axes,
        no_silent_exclusion=True,
    )
    lower: dict[str, tuple[MetricObservation, MetricObservation]] = {
        "daily_mae": (
            MetricObservation.computed("daily_mae", candidate_metrics.daily_mae),
            MetricObservation.computed("daily_mae", incumbent_metrics.daily_mae),
        ),
        "cumulative_absolute_error_kg": (
            _metric_observation(
                "cumulative_absolute_error_kg",
                candidate_metrics.cumulative_absolute_error_kg,
                candidate_metrics.cumulative_metric_status,
            ),
            _metric_observation(
                "cumulative_absolute_error_kg",
                incumbent_metrics.cumulative_absolute_error_kg,
                incumbent_metrics.cumulative_metric_status,
            ),
        ),
        "single_day_peak_quantity_absolute_error_kg_q": (
            _metric_observation(
                "single_day_peak_quantity_absolute_error_kg_q",
                candidate_metrics.single_day_peak_quantity_absolute_error_kg_q,
                candidate_metrics.single_day_peak_metric_status,
            ),
            _metric_observation(
                "single_day_peak_quantity_absolute_error_kg_q",
                incumbent_metrics.single_day_peak_quantity_absolute_error_kg_q,
                incumbent_metrics.single_day_peak_metric_status,
            ),
        ),
        "sustained_7day_quantity_absolute_error_kg_q": (
            _metric_observation(
                "sustained_7day_quantity_absolute_error_kg_q",
                candidate_metrics.sustained_7day_quantity_absolute_error_kg_q,
                candidate_metrics.sustained_7day_metric_status,
            ),
            _metric_observation(
                "sustained_7day_quantity_absolute_error_kg_q",
                incumbent_metrics.sustained_7day_quantity_absolute_error_kg_q,
                incumbent_metrics.sustained_7day_metric_status,
            ),
        ),
    }
    eligibility = evaluate_candidate_guardrails(
        candidate_primary_metric=_metric_observation(
            "daily_wape",
            candidate_metrics.daily_wape,
            candidate_metrics.daily_wape_metric_status,
        ),
        incumbent_primary_metric=_metric_observation(
            "daily_wape",
            incumbent_metrics.daily_wape,
            incumbent_metrics.daily_wape_metric_status,
        ),
        lower_is_better_metrics=lower,
        candidate_p80_coverage=MetricObservation.computed(
            "P80_COVERAGE", candidate_metrics.p80_coverage
        ),
        incumbent_p80_coverage=MetricObservation.computed(
            "P80_COVERAGE", incumbent_metrics.p80_coverage
        ),
        candidate_p90_coverage=MetricObservation.computed(
            "P90_COVERAGE", candidate_metrics.p90_coverage
        ),
        incumbent_p90_coverage=MetricObservation.computed(
            "P90_COVERAGE", incumbent_metrics.p90_coverage
        ),
        coverage_quality=coverage,
    )
    return {
        "status": eligibility.status,
        "candidate_eligible": eligibility.candidate_eligible,
        "reason_codes": list(eligibility.reason_codes),
        "guardrails": [
            {
                "guardrail_id": item.guardrail_id,
                "status": item.status,
                "reason_code": item.reason_code,
                "candidate_value": _decimal_text(item.candidate_value)
                if item.candidate_value is not None
                else None,
                "incumbent_value": _decimal_text(item.incumbent_value)
                if item.incumbent_value is not None
                else None,
            }
            for item in eligibility.guardrails
        ],
    }


def relation_to_incumbent(candidate: LocalReplayResult, incumbent: LocalReplayResult) -> str:
    if candidate.metrics.daily_wape is None or incumbent.metrics.daily_wape is None:
        return "NOT_COMPUTABLE"
    if candidate.metrics.daily_wape < incumbent.metrics.daily_wape:
        return "IMPROVED"
    if candidate.metrics.daily_wape == incumbent.metrics.daily_wape:
        return "NOT_IMPROVED"
    return "WORSE"


V2_SOURCE_ID: Final[str] = "SOURCE_002"
V2_CUTOFF_POLICY_IDENTITY: Final[str] = (
    "V0_3_S4_V2_CUTOFF_MAX_TRAIN_HARVEST_DATE_BEFORE_VALIDATION_V1"
)
V2_FORECAST_HORIZON_SET_POLICY_IDENTITY: Final[str] = "V0_3_S4_V2_FORECAST_HORIZON_SET_7_14_21_V1"
V2_BUSINESS_GRAIN_POLICY_IDENTITY: Final[str] = (
    "V0_3_S4_V2_BUSINESS_GRAIN_SEASON_FARM_SUBFARM_VARIETY_DATE_V1"
)
V2_COMMON_COMPARABLE_POLICY_IDENTITY: Final[str] = "V0_3_S4_V2_COMMON_COMPARABLE_TARGET_ROWS_V1"
V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE: Final[str] = COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
V2_POST_CUTOFF_FEATURE_FORBIDDEN: Final[str] = "POST_CUTOFF_FEATURE_FORBIDDEN"
V2_HISTORICAL_TARGET_SET_EMPTY: Final[str] = "HISTORICAL_TARGET_SET_EMPTY"
V2_HISTORICAL_HORIZON_SET_INCOMPLETE: Final[str] = "V2_HISTORICAL_HORIZON_SET_INCOMPLETE"
V2_PARTITION_BOUNDARY_INVALID: Final[str] = "V2_TRAIN_VALIDATION_BOUNDARY_INVALID"


@dataclass(frozen=True, slots=True)
class V2HistoricalEvaluationAuthority:
    """Bound SOURCE-002 TRAIN/VALIDATION authority for future offline runs.

    This object contains dataset and target-row identities only.  Constructing
    it verifies partition bytes and derives the cutoff; it does not fit a
    model, score a candidate, read TEST, or append a budget event.
    """

    source_id: str
    materialized_dataset_identity_sha256: str
    train_dataset_identity: str
    validation_dataset_identity: str
    actual_label_set_identity: str
    cutoff_policy_identity: str
    forecast_horizon_set_identity: str
    business_grain_set_identity: str
    common_comparable_set_identity: str
    forecast_cutoff_at: date
    requested_forecast_horizons: tuple[int, ...]
    observed_forecast_horizons: tuple[int, ...]
    train_row_count: int
    validation_row_count: int
    evaluation_row_count: int
    train_rows: tuple[MaterializableRow, ...]
    validation_rows: tuple[MaterializableRow, ...]
    evaluation_rows: tuple[MaterializableRow, ...]
    complete_window_authority: CompleteWindowAuthority | None
    test_remains_sealed: bool

    def identity_values(self) -> tuple[tuple[str, str], ...]:
        return (
            ("train_dataset_identity", self.train_dataset_identity),
            ("validation_dataset_identity", self.validation_dataset_identity),
            ("actual_label_set_identity", self.actual_label_set_identity),
            ("cutoff_policy_identity", self.cutoff_policy_identity),
            ("forecast_horizon_set_identity", self.forecast_horizon_set_identity),
            ("business_grain_set_identity", self.business_grain_set_identity),
            ("common_comparable_set_identity", self.common_comparable_set_identity),
        )

    def payload(self) -> dict[str, object]:
        """Return the compact, row-free authority projection."""

        return {
            "source_id": self.source_id,
            "materialized_dataset_identity_sha256": self.materialized_dataset_identity_sha256,
            "train_dataset_identity": self.train_dataset_identity,
            "validation_dataset_identity": self.validation_dataset_identity,
            "actual_label_set_identity": self.actual_label_set_identity,
            "cutoff_policy_identity": self.cutoff_policy_identity,
            "forecast_horizon_set_identity": self.forecast_horizon_set_identity,
            "business_grain_set_identity": self.business_grain_set_identity,
            "common_comparable_set_identity": self.common_comparable_set_identity,
            "forecast_cutoff_at": self.forecast_cutoff_at,
            "requested_forecast_horizons": self.requested_forecast_horizons,
            "observed_forecast_horizons": self.observed_forecast_horizons,
            "train_row_count": self.train_row_count,
            "validation_row_count": self.validation_row_count,
            "evaluation_row_count": self.evaluation_row_count,
            "complete_window_authority": self.complete_window_authority is not None,
            "complete_window_metrics_reason": V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE,
            "test_remains_sealed": self.test_remains_sealed,
        }


def derive_v2_historical_cutoff(
    train_rows: tuple[MaterializableRow, ...],
    validation_rows: tuple[MaterializableRow, ...],
) -> date:
    """Derive the cutoff from the governed partition dates, never a literal."""

    if not train_rows or not validation_rows:
        raise LocalEngineeringContractError(V2_PARTITION_BOUNDARY_INVALID)
    train_end = max(row.harvest_business_date for row in train_rows)
    validation_start = min(row.harvest_business_date for row in validation_rows)
    if train_end >= validation_start:
        raise LocalEngineeringContractError(V2_PARTITION_BOUNDARY_INVALID)
    return train_end


def _v2_target_rows(
    validation_rows: tuple[MaterializableRow, ...],
    *,
    forecast_cutoff_at: date,
) -> tuple[MaterializableRow, ...]:
    targets = tuple(
        sorted(
            (
                row
                for row in validation_rows
                if (row.harvest_business_date - forecast_cutoff_at).days in V2_FORECAST_HORIZONS
            ),
            key=_row_key,
        )
    )
    if not targets:
        raise LocalEngineeringContractError(V2_HISTORICAL_TARGET_SET_EMPTY)
    observed_horizons = {(row.harvest_business_date - forecast_cutoff_at).days for row in targets}
    if observed_horizons != set(V2_FORECAST_HORIZONS):
        raise LocalEngineeringContractError(V2_HISTORICAL_HORIZON_SET_INCOMPLETE)
    return targets


def _v2_common_comparable_set_hash(
    rows: tuple[MaterializableRow, ...], *, forecast_cutoff_at: date
) -> str:
    return _sha(
        {
            "policy": V2_COMMON_COMPARABLE_POLICY_IDENTITY,
            "rows": [
                {
                    "season": row.season,
                    "farm": row.farm,
                    "subfarm": row.subfarm,
                    "variety": row.variety,
                    "harvest_business_date": row.harvest_business_date,
                    "forecast_horizon_days": (row.harvest_business_date - forecast_cutoff_at).days,
                }
                for row in rows
            ],
        }
    )


def _v2_business_grain_set_hash(rows: tuple[MaterializableRow, ...]) -> str:
    return _sha(
        {
            "policy": V2_BUSINESS_GRAIN_POLICY_IDENTITY,
            "rows": [
                {
                    "season": row.season,
                    "farm": row.farm,
                    "subfarm": row.subfarm,
                    "variety": row.variety,
                    "harvest_business_date": row.harvest_business_date,
                }
                for row in rows
            ],
        }
    )


def build_v2_historical_evaluation_authority(
    dataset: FrozenEngineeringDataset,
) -> V2HistoricalEvaluationAuthority:
    """Verify and bind the accepted SOURCE-002 historical evaluation surface."""

    if (
        len(dataset.train_rows) != OFFICIAL_TRAIN_ROW_COUNT
        or len(dataset.validation_rows) != OFFICIAL_VALIDATION_ROW_COUNT
        or dataset.train_content_sha256 != OFFICIAL_TRAIN_CONTENT_SHA256
        or dataset.validation_content_sha256 != OFFICIAL_VALIDATION_CONTENT_SHA256
        or dataset.test_row_count != 0
    ):
        raise LocalEngineeringContractError("SOURCE_002_V2_PARTITION_IDENTITY_MISMATCH")
    cutoff = derive_v2_historical_cutoff(dataset.train_rows, dataset.validation_rows)
    evaluation_rows = _v2_target_rows(dataset.validation_rows, forecast_cutoff_at=cutoff)
    observed_horizons = tuple(
        sorted({(row.harvest_business_date - cutoff).days for row in evaluation_rows})
    )
    cutoff_identity = _sha(
        {
            "policy": V2_CUTOFF_POLICY_IDENTITY,
            "train_end_derived_from_rows": cutoff,
            "validation_start_derived_from_rows": min(
                row.harvest_business_date for row in dataset.validation_rows
            ),
        }
    )
    horizon_identity = _sha(
        {
            "policy": V2_FORECAST_HORIZON_SET_POLICY_IDENTITY,
            "horizons": V2_FORECAST_HORIZONS,
        }
    )
    return V2HistoricalEvaluationAuthority(
        source_id=V2_SOURCE_ID,
        materialized_dataset_identity_sha256=dataset.materialized_dataset_identity_sha256,
        train_dataset_identity=dataset.train_content_sha256,
        validation_dataset_identity=dataset.validation_content_sha256,
        actual_label_set_identity=_actual_label_set_hash(evaluation_rows),
        cutoff_policy_identity=cutoff_identity,
        forecast_horizon_set_identity=horizon_identity,
        business_grain_set_identity=_v2_business_grain_set_hash(evaluation_rows),
        common_comparable_set_identity=_v2_common_comparable_set_hash(
            evaluation_rows, forecast_cutoff_at=cutoff
        ),
        forecast_cutoff_at=cutoff,
        requested_forecast_horizons=V2_FORECAST_HORIZONS,
        observed_forecast_horizons=observed_horizons,
        train_row_count=len(dataset.train_rows),
        validation_row_count=len(dataset.validation_rows),
        evaluation_row_count=len(evaluation_rows),
        train_rows=dataset.train_rows,
        validation_rows=dataset.validation_rows,
        evaluation_rows=evaluation_rows,
        complete_window_authority=None,
        test_remains_sealed=True,
    )


def validate_v2_feature_dates(feature_dates: Iterable[date], *, forecast_cutoff_at: date) -> None:
    """Reject any feature observed after the derived historical cutoff."""

    for feature_date in feature_dates:
        if type(feature_date) is not date or feature_date > forecast_cutoff_at:
            raise LocalEngineeringContractError(V2_POST_CUTOFF_FEATURE_FORBIDDEN)


def v2_training_rows(
    authority: V2HistoricalEvaluationAuthority,
) -> tuple[MaterializableRow, ...]:
    """Return only rows allowed to participate in historical fitting."""

    validate_v2_feature_dates(
        (row.harvest_business_date for row in authority.train_rows),
        forecast_cutoff_at=authority.forecast_cutoff_at,
    )
    return authority.train_rows


def validate_v2_forecast_horizon(horizon_days: int) -> int:
    if type(horizon_days) is not int or horizon_days not in V2_FORECAST_HORIZONS:
        raise LocalEngineeringContractError(FORECAST_HORIZON_NOT_IN_FROZEN_SET)
    return horizon_days


def v2_metric_availability() -> dict[str, str]:
    """Expose computability without weakening the inherited S4-B policy."""

    return {
        "daily_wape": "COMPUTABLE_AFTER_HISTORICAL_ONLY_SCORING_PATH",
        "daily_mae": "COMPUTABLE_AFTER_HISTORICAL_ONLY_SCORING_PATH",
        "p80_coverage": "COMPUTABLE_AFTER_HISTORICAL_ONLY_SCORING_PATH",
        "p90_coverage": "COMPUTABLE_AFTER_HISTORICAL_ONLY_SCORING_PATH",
        "cumulative_absolute_error_kg": V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE,
        "single_day_peak_quantity_absolute_error_kg_q": V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE,
        "sustained_7day_quantity_absolute_error_kg_q": V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE,
        "s4_b_guardrail_disposition": (
            "BLOCKED_UNDER_INHERITED_POLICY_WHEN_REQUIRED_COMPLETE_WINDOW_METRICS_UNAVAILABLE"
        ),
    }


__all__ = [
    "COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE",
    "CompleteWindowAuthority",
    "FROZEN_FORECAST_HORIZONS",
    "FORECAST_HORIZON_NOT_IN_FROZEN_SET",
    "FrozenEngineeringDataset",
    "FrozenSourceObject",
    "LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS",
    "LOCAL_ENGINEERING_REPLAY_MODEL_ID",
    "LocalEngineeringContractError",
    "LocalMetricSet",
    "LocalPrediction",
    "LocalReplayResult",
    "SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256",
    "V2_BUSINESS_GRAIN_POLICY_IDENTITY",
    "V2_COMMON_COMPARABLE_POLICY_IDENTITY",
    "V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE",
    "V2_CUTOFF_POLICY_IDENTITY",
    "V2_FORECAST_HORIZON_SET_POLICY_IDENTITY",
    "V2_HISTORICAL_TARGET_SET_EMPTY",
    "V2_HISTORICAL_HORIZON_SET_INCOMPLETE",
    "V2_POST_CUTOFF_FEATURE_FORBIDDEN",
    "V2_SOURCE_ID",
    "V2HistoricalEvaluationAuthority",
    "WAPE_ACTUAL_DENOMINATOR_ZERO",
    "build_v2_historical_evaluation_authority",
    "compute_metrics",
    "derive_v2_historical_cutoff",
    "guardrail_payload",
    "load_frozen_engineering_dataset",
    "relation_to_incumbent",
    "run_local_replay",
    "validate_v2_feature_dates",
    "validate_v2_forecast_horizon",
    "verify_frozen_source_object",
    "v2_metric_availability",
    "v2_training_rows",
]
