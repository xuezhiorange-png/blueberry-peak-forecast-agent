"""Round C common-set and daily point comparison contracts."""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.comparison import (
    ComparisonBaselineRecord,
    ComparisonName,
    ComparisonStructuralFailure,
    compute_model_baseline_comparisons,
)
from backend.app.forecast_quality.enums import (
    ComparisonAvailability,
    FrozenVersion,
    MetricStatus,
    ReasonCode,
    SupportedQuantile,
)
from backend.app.forecast_quality.schemas import (
    BaselineRequest,
    BaselineResult,
    BaselineSourceSnapshot,
    BreakdownSpec,
    S3BindingRow,
    S3EvaluationInput,
)

pytestmark = pytest.mark.postgres

_CUTOFF = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
_METRIC_POLICY = FrozenVersion.METRIC_INPUT_MASK_V1
_BASELINE_POLICY = FrozenVersion.NAIVE_BASELINE_POLICY_V1


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _spec(suffix: str = "point") -> BreakdownSpec:
    return BreakdownSpec(
        7,
        f"farm:{suffix}",
        f"subfarm:{suffix}",
        f"variety:{suffix}",
        f"season:{suffix}",
        f"model:{suffix}",
    )


def _inputs(suffix: str = "point", *, count: int = 10) -> tuple[S3EvaluationInput, BreakdownSpec]:
    spec = _spec(suffix)
    rows = tuple(
        S3BindingRow(
            forecast_business_key=f"forecast:{suffix}:{index}",
            actual_physical_key=f"physical:{suffix}:{index}",
            stable_actual_identity=f"actual:{suffix}:{index}",
            forecast_value_kg=Decimal("10"),
            actual_value_kg=Decimal("8"),
            forecast_quantile=SupportedQuantile.P50,
            forecast_horizon_days=7,
            forecast_target_date=date(2026, 3, 1) + timedelta(days=index),
            forecast_cutoff_at=_CUTOFF,
            s2_status="COMPARABLE",
            season_business_key=spec.season_business_key,
            farm_business_key=spec.farm_business_key,
            subfarm_business_key=spec.subfarm_business_key,
            variety_business_key=spec.variety_business_key,
            model_identity=spec.model_identity,
            actual_visibility_timestamp=None,
        )
        for index in range(count)
    )
    return (
        S3EvaluationInput(
            rows=rows,
            s2_run_identity=f"s2-run:{suffix}",
            s2_manifest_identity=f"s2-manifest:{suffix}",
            s2_binding_row_set_hash="a" * 64,
            metric_policy_version=_METRIC_POLICY,
            baseline_policy_version=_BASELINE_POLICY,
        ),
        spec,
    )


def _baseline_record(
    input_data: S3EvaluationInput,
    spec: BreakdownSpec,
    index: int,
    *,
    baseline_value: Decimal = Decimal("9"),
    cutoff: datetime = _CUTOFF,
) -> ComparisonBaselineRecord:
    target = date(2026, 3, 1) + timedelta(days=index)
    request = BaselineRequest(
        current_target_date=target,
        current_season_start=date(2026, 3, 1),
        current_season_end=date(2026, 3, 31),
        prior_season_start=date(2025, 3, 1),
        prior_season_end=date(2025, 3, 31),
        prior_season_identity="season:2025",
        current_forecast_cutoff_at=cutoff,
        farm_business_key=spec.farm_business_key,
        subfarm_business_key=spec.subfarm_business_key,
        variety_business_key=spec.variety_business_key,
        requested_quantile="P50",
        metric_policy_version=input_data.metric_policy_version,
        baseline_policy_version=input_data.baseline_policy_version,
    )
    snapshot = BaselineSourceSnapshot(
        source_snapshot_identity=f"snapshot:{index}",
        source_snapshot_hash=f"{index + 1:064x}",
        source_row_set_hash=f"{index + 101:064x}",
        visibility_manifest_hash=f"{index + 201:064x}",
        visibility_cutoff_at=cutoff,
        season_analog_mapping_policy_version=FrozenVersion.SEASON_ANALOG_MAPPING_V1,
        actual_rows=(),
    )
    result_without_hash = BaselineResult(
        baseline_point_forecast_kg=baseline_value,
        baseline_quantile="P50",
        comparison_availability=ComparisonAvailability.AVAILABLE,
        metric_status=MetricStatus.COMPUTED,
        reason_code=ReasonCode.NONE,
        analog_date=date(2025, 3, 1) + timedelta(days=index),
        source_snapshot_identity=snapshot.source_snapshot_identity,
        source_snapshot_hash=snapshot.source_snapshot_hash,
        source_row_set_hash=snapshot.source_row_set_hash,
        visibility_manifest_hash=snapshot.visibility_manifest_hash,
        canonical_hash="",
    )
    result = dataclasses.replace(
        result_without_hash,
        canonical_hash=_hash(dataclasses.asdict(result_without_hash)),
    )
    return ComparisonBaselineRecord(request, snapshot, result)


def _records(
    suffix: str = "point", count: int = 10
) -> tuple[S3EvaluationInput, BreakdownSpec, tuple[ComparisonBaselineRecord, ...]]:
    input_data, spec = _inputs(suffix, count=count)
    return input_data, spec, tuple(_baseline_record(input_data, spec, i) for i in range(count))


def test_common_set_recomputes_both_sides_and_emits_ten_records() -> None:
    input_data, spec, records = _records()
    results = compute_model_baseline_comparisons(
        evaluation_input=input_data,
        breakdown_spec=spec,
        baseline_records=records,
    )
    assert len(results) == 10
    mae = next(item for item in results if item.comparison_name == ComparisonName.DAILY_MAE_DELTA)
    assert mae.model_value == Decimal("2.000000")
    assert mae.baseline_value == Decimal("1.000000")
    assert mae.delta_value == Decimal("1.000000")
    assert mae.metric_status is MetricStatus.COMPUTED
    assert mae.reason_code is ReasonCode.NONE
    assert mae.comparison_availability is ComparisonAvailability.AVAILABLE
    assert mae.common_comparable_row_count == 10


def test_baseline_member_order_does_not_change_set_hash() -> None:
    input_data, spec, records = _records("order")
    forward = compute_model_baseline_comparisons(
        evaluation_input=input_data, breakdown_spec=spec, baseline_records=records
    )
    reverse = compute_model_baseline_comparisons(
        evaluation_input=input_data, breakdown_spec=spec, baseline_records=tuple(reversed(records))
    )
    assert forward[0].baseline_member_set_hash == reverse[0].baseline_member_set_hash
    assert forward[0].canonical_hash == reverse[0].canonical_hash


def test_cutoff_mismatch_is_rejected_when_daily_identity_is_present() -> None:
    input_data, spec, records = _records("cutoff", count=1)
    mismatched = (_baseline_record(input_data, spec, 0, cutoff=_CUTOFF + timedelta(hours=1)),)
    with pytest.raises(ComparisonStructuralFailure):
        compute_model_baseline_comparisons(
            evaluation_input=input_data, breakdown_spec=spec, baseline_records=mismatched
        )


def test_empty_baseline_member_set_fails_closed() -> None:
    input_data, spec = _inputs("empty", count=1)
    with pytest.raises(ComparisonStructuralFailure):
        compute_model_baseline_comparisons(
            evaluation_input=input_data, breakdown_spec=spec, baseline_records=()
        )
