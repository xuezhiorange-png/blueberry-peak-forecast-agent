from __future__ import annotations

import hashlib
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from .canonical import canonical_json_bytes
from .enums import MetricStatus, ReasonCode
from .exceptions import S3ContractInvariantViolationError
from .schemas import BreakdownSpec, S3BindingRow

MIN_COMPARABLE_ROWS_FOR_REPORTING = 10


def _identity(spec: BreakdownSpec) -> dict[str, Any]:
    return {
        "season_business_key": spec.season_business_key,
        "farm_business_key": spec.farm_business_key,
        "subfarm_business_key": spec.subfarm_business_key,
        "variety_business_key": spec.variety_business_key,
        "model_identity": spec.model_identity,
        "forecast_horizon_days": spec.forecast_horizon_days,
    }


def _matches_breakdown(row: S3BindingRow, spec: BreakdownSpec) -> bool:
    return all(
        getattr(row, field) == getattr(spec, field)
        for field in (
            "forecast_horizon_days",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "season_business_key",
            "model_identity",
        )
    )


def _metric_values(rows: list[S3BindingRow]) -> dict[str, Decimal | None]:
    pairs = [
        (row.forecast_value_kg, row.actual_value_kg)
        for row in rows
        if row.forecast_value_kg is not None and row.actual_value_kg is not None
    ]
    if not pairs:
        return {
            name: None
            for name in (
                "daily_mae",
                "daily_wape",
                "daily_smape",
                "daily_mape",
                "daily_bias_kg",
                "daily_relative_bias",
                "daily_absolute_error_sum_kg",
            )
        }
    errors = [forecast - actual for forecast, actual in pairs]
    absolute_errors = [abs(error) for error in errors]
    actuals = [actual for _, actual in pairs]
    sum_abs = sum(absolute_errors, Decimal("0"))
    sum_actual = sum(actuals, Decimal("0"))
    mape_pairs = [
        (error, actual) for error, actual in zip(errors, actuals, strict=True) if actual > 0
    ]
    smape_terms = [
        Decimal("0")
        if forecast == 0 and actual == 0
        else Decimal("2") * abs(forecast - actual) / (abs(forecast) + abs(actual))
        for forecast, actual in pairs
    ]
    return {
        "daily_mae": sum_abs / Decimal(len(pairs)),
        "daily_wape": None if sum_actual == 0 else sum_abs / sum_actual,
        "daily_smape": sum(smape_terms, Decimal("0")) / Decimal(len(pairs)),
        "daily_mape": (
            None
            if not mape_pairs
            else sum(
                (abs(error) / abs(actual) for error, actual in mape_pairs),
                Decimal("0"),
            )
            / Decimal(len(mape_pairs))
        ),
        "daily_bias_kg": sum(errors, Decimal("0")) / Decimal(len(pairs)),
        "daily_relative_bias": (
            None if sum_actual == 0 else sum(errors, Decimal("0")) / sum_actual
        ),
        "daily_absolute_error_sum_kg": sum_abs,
    }


def calculate_breakdown_cells(
    rows: Iterable[S3BindingRow], breakdown_spec: BreakdownSpec
) -> list[dict[str, Any]]:
    cell_rows = [
        row
        for row in rows
        if row.forecast_quantile.value == "P50" and _matches_breakdown(row, breakdown_spec)
    ]
    known_statuses = {"COMPARABLE", "EXCLUDED", "NOT_COMPARABLE", "NOT_COMPUTABLE"}
    unknown_statuses = {row.s2_status for row in cell_rows} - known_statuses
    if unknown_statuses:
        raise S3ContractInvariantViolationError(f"unknown S2 status: {sorted(unknown_statuses)}")
    comparable_rows = [row for row in cell_rows if row.s2_status == "COMPARABLE"]
    excluded_rows = [row for row in cell_rows if row.s2_status in {"EXCLUDED", "NOT_COMPARABLE"}]
    not_computable_rows = [row for row in cell_rows if row.s2_status == "NOT_COMPUTABLE"]
    total = len(cell_rows)
    if total != len(comparable_rows) + len(excluded_rows) + len(not_computable_rows):
        raise S3ContractInvariantViolationError("S2 status counts do not close")
    identity = _identity(breakdown_spec)
    enough = len(comparable_rows) >= MIN_COMPARABLE_ROWS_FOR_REPORTING
    paired_rows = [
        row
        for row in comparable_rows
        if row.forecast_value_kg is not None and row.actual_value_kg is not None
    ]
    return [
        {
            "cell_identity": identity,
            "cell_identity_hash": hashlib.sha256(canonical_json_bytes(identity)).hexdigest(),
            "metric_status": MetricStatus.COMPUTED if enough else MetricStatus.INSUFFICIENT_SAMPLE,
            "reason_code": ReasonCode.NONE if enough else ReasonCode.BELOW_MINIMUM,
            "s2_total_binding_row_count": total,
            "s2_comparable_row_count": len(comparable_rows),
            "s2_excluded_row_count": len(excluded_rows),
            "s2_not_computable_row_count": len(not_computable_rows),
            "coverage_ratio": (
                None if total == 0 else Decimal(len(comparable_rows)) / Decimal(total)
            ),
            "metric_values": _metric_values(paired_rows),
            "comparable_row_count": len(comparable_rows),
        }
    ]
