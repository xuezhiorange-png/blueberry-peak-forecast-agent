from __future__ import annotations

import dataclasses
from decimal import Decimal

from .canonical import canonical_json_bytes, compute_metric_input_mask_hash
from .enums import FrozenVersion, MetricStatus, ReasonCode, SupportedQuantile
from .exceptions import S3ContractInvariantViolationError
from .schemas import BreakdownSpec, DailyMetricResult, MetricValueCell, S3EvaluationInput

_KNOWN_S2_STATUSES = frozenset({"COMPARABLE", "EXCLUDED", "NOT_COMPARABLE", "NOT_COMPUTABLE"})


def _quantize(value: Decimal) -> Decimal:
    from decimal import ROUND_HALF_EVEN

    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)


def _matches_breakdown(row: object, breakdown_spec: BreakdownSpec) -> bool:
    return all(
        getattr(row, field) == getattr(breakdown_spec, field)
        for field in (
            "forecast_horizon_days",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "season_business_key",
            "model_identity",
        )
    )


def _metric_cell(
    name: str,
    value: Decimal | None,
    status: MetricStatus,
    reason: ReasonCode,
    numerator: Decimal | None,
    denominator: Decimal | None,
    eligible: int,
    zero_actual: int,
) -> MetricValueCell:
    return MetricValueCell(
        metric_name=name,
        metric_value=None if value is None else _quantize(value),
        metric_status=status,
        reason_code=reason,
        numerator=numerator,
        denominator=denominator,
        mape_eligible_row_count=eligible,
        mape_zero_actual_row_count=zero_actual,
    )


def compute_daily_metrics(
    evaluation_input: S3EvaluationInput, breakdown_spec: BreakdownSpec
) -> DailyMetricResult:
    cell_rows = [
        row
        for row in evaluation_input.rows
        if row.forecast_quantile == SupportedQuantile.P50
        and _matches_breakdown(row, breakdown_spec)
    ]
    for row in cell_rows:
        if row.s2_status not in _KNOWN_S2_STATUSES:
            raise S3ContractInvariantViolationError(f"unknown S2 status: {row.s2_status}")
    comparable_rows = [row for row in cell_rows if row.s2_status == "COMPARABLE"]
    metric_rows = [
        row
        for row in comparable_rows
        if row.forecast_value_kg is not None and row.actual_value_kg is not None
    ]
    comparable = [
        (row.forecast_value_kg, row.actual_value_kg)
        for row in metric_rows
        if row.forecast_value_kg is not None and row.actual_value_kg is not None
    ]
    errors = [forecast - actual for forecast, actual in comparable]
    absolute_errors = [abs(error) for error in errors]
    actuals = [actual for _, actual in comparable]
    forecasts = [forecast for forecast, _ in comparable]
    total = len(cell_rows)
    comparable_count = len(comparable_rows)
    excluded_count = sum(row.s2_status in {"EXCLUDED", "NOT_COMPARABLE"} for row in cell_rows)
    not_computable_count = sum(row.s2_status == "NOT_COMPUTABLE" for row in cell_rows)
    if total != comparable_count + excluded_count + not_computable_count:
        raise S3ContractInvariantViolationError("S2 status counts do not close")
    coverage = None if total == 0 else Decimal(comparable_count) / Decimal(total)
    sum_abs = sum(absolute_errors, Decimal("0"))
    sum_actual = sum(actuals, Decimal("0"))
    mape_zero_count = sum(value == 0 for value in actuals)
    mape_pairs = [
        (error, actual) for error, actual in zip(errors, actuals, strict=True) if actual > 0
    ]
    mape_eligible_count = len(mape_pairs)
    if sum_actual == 0:
        wape_value = None
        relative_value = None
    else:
        wape_value = sum_abs / sum_actual
        relative_value = sum(errors, Decimal("0")) / sum_actual
    smape_terms = [
        Decimal("0")
        if forecast == 0 and actual == 0
        else Decimal("2") * abs(forecast - actual) / (abs(forecast) + abs(actual))
        for forecast, actual in zip(forecasts, actuals, strict=True)
    ]
    if mape_eligible_count == 0:
        mape_value = None
    else:
        mape_value = sum(
            (abs(error) / abs(actual) for error, actual in mape_pairs), Decimal("0")
        ) / Decimal(mape_eligible_count)
    if not comparable:
        status = MetricStatus.NOT_COMPUTABLE
    else:
        status = MetricStatus.COMPUTED

    def denominator_cell(
        name: str,
        numerator: Decimal,
        denominator: Decimal,
        value: Decimal | None,
        zero_reason: ReasonCode,
    ) -> MetricValueCell:
        if denominator == 0:
            return _metric_cell(
                name,
                None,
                MetricStatus.NOT_COMPUTABLE,
                zero_reason,
                numerator,
                denominator,
                mape_eligible_count,
                mape_zero_count,
            )
        return _metric_cell(
            name,
            value,
            MetricStatus.COMPUTED,
            ReasonCode.NONE,
            numerator,
            denominator,
            mape_eligible_count,
            mape_zero_count,
        )

    cells = [
        _metric_cell(
            "daily_mae",
            None if not comparable else sum_abs / Decimal(len(comparable)),
            status,
            ReasonCode.NONE if comparable else ReasonCode.NO_S2_BINDING_ROWS,
            sum_abs,
            Decimal(len(comparable)),
            mape_eligible_count,
            mape_zero_count,
        ),
        denominator_cell(
            "daily_wape", sum_abs, sum_actual, wape_value, ReasonCode.WAPE_DENOMINATOR_ZERO
        ),
        _metric_cell(
            "daily_smape",
            None if not comparable else sum(smape_terms, Decimal("0")) / Decimal(len(comparable)),
            status,
            ReasonCode.NONE if comparable else ReasonCode.NO_S2_BINDING_ROWS,
            sum(smape_terms, Decimal("0")),
            Decimal(len(comparable)),
            mape_eligible_count,
            mape_zero_count,
        ),
        _metric_cell(
            "daily_mape",
            mape_value,
            MetricStatus.COMPUTED if mape_eligible_count else MetricStatus.NOT_COMPUTABLE,
            ReasonCode.NONE if mape_eligible_count else ReasonCode.NO_MAPE_ELIGIBLE_ROWS,
            None
            if not mape_eligible_count
            else sum((abs(error) / abs(actual) for error, actual in mape_pairs), Decimal("0")),
            Decimal(mape_eligible_count),
            mape_eligible_count,
            mape_zero_count,
        ),
        _metric_cell(
            "daily_bias_kg",
            None if not comparable else sum(errors, Decimal("0")) / Decimal(len(comparable)),
            status,
            ReasonCode.NONE if comparable else ReasonCode.NO_S2_BINDING_ROWS,
            sum(errors, Decimal("0")),
            Decimal(len(comparable)),
            mape_eligible_count,
            mape_zero_count,
        ),
        denominator_cell(
            "daily_relative_bias",
            sum(errors, Decimal("0")),
            sum_actual,
            relative_value,
            ReasonCode.RELATIVE_BIAS_DENOMINATOR_ZERO,
        ),
        _metric_cell(
            "daily_absolute_error_sum_kg",
            sum_abs if comparable else None,
            status,
            ReasonCode.NONE if comparable else ReasonCode.NO_S2_BINDING_ROWS,
            sum_abs,
            Decimal("1") if comparable else Decimal("0"),
            mape_eligible_count,
            mape_zero_count,
        ),
    ]
    breakdown_identity: dict[str, str | int] = {
        "season_business_key": breakdown_spec.season_business_key,
        "farm_business_key": breakdown_spec.farm_business_key,
        "subfarm_business_key": breakdown_spec.subfarm_business_key,
        "variety_business_key": breakdown_spec.variety_business_key,
        "model_identity": breakdown_spec.model_identity,
        "forecast_horizon_days": breakdown_spec.forecast_horizon_days,
    }
    source_row_set = evaluation_input.s2_binding_row_set_hash
    mask = {
        "metric_input_mask_policy_version": FrozenVersion.METRIC_INPUT_MASK_V1.value,
        "s2_status_predicate": "S2_STATUS_COMPARABLE",
        "forecast_quantile_predicate": "P50",
        "actual_pair_predicate": "EXACT_ACTUAL_PAIRED",
        "breakdown_identity": breakdown_identity,
        "source_row_set_identity": source_row_set,
    }
    mask_hash = compute_metric_input_mask_hash(mask)
    unique_actual = len(
        {
            row.actual_physical_key
            for row in metric_rows
            if row.s2_status == "COMPARABLE"
            and row.actual_physical_key is not None
            and row.actual_value_kg is not None
            and row.forecast_value_kg is not None
        }
    )
    result = DailyMetricResult(
        s2_run_identity=evaluation_input.s2_run_identity,
        s2_manifest_identity=evaluation_input.s2_manifest_identity,
        s2_binding_row_set_hash=evaluation_input.s2_binding_row_set_hash,
        metric_policy_version=evaluation_input.metric_policy_version,
        baseline_policy_version=evaluation_input.baseline_policy_version,
        breakdown_identity=breakdown_identity,
        s2_total_binding_row_count=total,
        s2_comparable_binding_row_count=comparable_count,
        s2_excluded_binding_row_count=excluded_count,
        s2_not_computable_binding_row_count=not_computable_count,
        coverage_ratio=coverage,
        metric_input_mask_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
        metric_input_mask_hash=mask_hash,
        metric_input_row_count=len(metric_rows),
        metric_input_quantile=SupportedQuantile.P50,
        unique_actual_physical_row_count=unique_actual,
        mape_eligible_row_count=mape_eligible_count,
        mape_zero_actual_row_count=mape_zero_count,
        mape_zero_actual_reason_code=(
            ReasonCode.MAPE_DENOMINATOR_ZERO if mape_zero_count else None
        ),
        metric_cells=tuple(cells),
        canonical_hash="",
    )
    payload = dataclasses.asdict(result)
    payload["canonical_hash"] = ""
    canonical_hash = __import__("hashlib").sha256(canonical_json_bytes(payload)).hexdigest()
    return dataclasses.replace(result, canonical_hash=canonical_hash)
