from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from .canonical import canonical_json_bytes
from .enums import ComparisonAvailability, FrozenVersion, MetricStatus, ReasonCode
from .schemas import BaselineRequest, BaselineResult, BaselineSourceSnapshot
from .season_calendar import resolve_prior_season_analog_date


def _result(
    *,
    point: Decimal | None,
    quantile: str,
    availability: ComparisonAvailability,
    status: MetricStatus,
    reason: ReasonCode,
    analog_date: date | None,
    snapshot: BaselineSourceSnapshot,
) -> BaselineResult:
    result = BaselineResult(
        baseline_point_forecast_kg=point,
        baseline_quantile=quantile,
        comparison_availability=availability,
        metric_status=status,
        reason_code=reason,
        analog_date=analog_date,
        source_snapshot_identity=snapshot.source_snapshot_identity,
        source_snapshot_hash=snapshot.source_snapshot_hash,
        source_row_set_hash=snapshot.source_row_set_hash,
        visibility_manifest_hash=snapshot.visibility_manifest_hash,
        canonical_hash="",
    )
    payload = dataclasses.asdict(result)
    payload["canonical_hash"] = ""
    return dataclasses.replace(
        result,
        canonical_hash=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    )


def _row_matches(row: Mapping[str, Any], request: BaselineRequest) -> bool:
    return all(
        row.get(field) == getattr(request, field)
        for field in ("farm_business_key", "subfarm_business_key", "variety_business_key")
    )


def resolve_baseline_point_forecast(
    request: BaselineRequest, source_snapshot: BaselineSourceSnapshot
) -> BaselineResult:
    analog_date = resolve_prior_season_analog_date(
        current_target_date=request.current_target_date,
        current_season_start=request.current_season_start,
        current_season_end=request.current_season_end,
        prior_season_start=request.prior_season_start,
        prior_season_end=request.prior_season_end,
        policy_version=FrozenVersion.SEASON_ANALOG_MAPPING_V1.value,
    )
    if request.requested_quantile in {"P80", "P90"}:
        return _result(
            point=None,
            quantile=request.requested_quantile,
            availability=ComparisonAvailability.BLOCKED,
            status=MetricStatus.NOT_COMPUTABLE,
            reason=ReasonCode.BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED,
            analog_date=analog_date,
            snapshot=source_snapshot,
        )
    if analog_date is None:
        return _result(
            point=None,
            quantile=request.requested_quantile,
            availability=ComparisonAvailability.AVAILABLE,
            status=MetricStatus.NOT_COMPUTABLE,
            reason=ReasonCode.NO_PRIOR_SEASON_ANALOG_DAY,
            analog_date=None,
            snapshot=source_snapshot,
        )
    candidates = [
        row
        for row in source_snapshot.actual_rows
        if row.get("target_date") == analog_date and _row_matches(row, request)
    ]
    if not candidates:
        return _result(
            point=None,
            quantile=request.requested_quantile,
            availability=ComparisonAvailability.AVAILABLE,
            status=MetricStatus.NOT_COMPUTABLE,
            reason=ReasonCode.NO_PRIOR_SEASON_ANALOG_ACTUAL,
            analog_date=analog_date,
            snapshot=source_snapshot,
        )
    visible = [
        row
        for row in candidates
        if row.get("source_kind") == "FARM_PICK"
        and row.get("visibility_timestamp") is not None
        and row["visibility_timestamp"] <= request.current_forecast_cutoff_at
        and row["visibility_timestamp"] <= source_snapshot.visibility_cutoff_at
    ]
    if not visible:
        return _result(
            point=None,
            quantile=request.requested_quantile,
            availability=ComparisonAvailability.AVAILABLE,
            status=MetricStatus.NOT_COMPUTABLE,
            reason=ReasonCode.BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF,
            analog_date=analog_date,
            snapshot=source_snapshot,
        )
    physical_keys: set[str] = set()
    values: list[Decimal] = []
    for row in visible:
        physical_key = str(row.get("physical_key"))
        if physical_key in physical_keys:
            continue
        physical_keys.add(physical_key)
        value = row.get("actual_value_kg")
        if not isinstance(value, Decimal) or not value.is_finite():
            return _result(
                point=None,
                quantile=request.requested_quantile,
                availability=ComparisonAvailability.AVAILABLE,
                status=MetricStatus.NOT_COMPUTABLE,
                reason=ReasonCode.NO_PRIOR_SEASON_ANALOG_ACTUAL,
                analog_date=analog_date,
                snapshot=source_snapshot,
            )
        values.append(value)
    if not values:
        reason = ReasonCode.NO_PRIOR_SEASON_ANALOG_ACTUAL
        point = None
        status = MetricStatus.NOT_COMPUTABLE
    else:
        reason = ReasonCode.NONE
        point = sum(values, Decimal("0"))
        status = MetricStatus.COMPUTED
    return _result(
        point=point,
        quantile="P50",
        availability=ComparisonAvailability.AVAILABLE,
        status=status,
        reason=reason,
        analog_date=analog_date,
        snapshot=source_snapshot,
    )
